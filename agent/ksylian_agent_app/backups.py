from __future__ import annotations

import io
import json
import re
import shutil
import tarfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from fastapi import HTTPException

from .activity import append_action_log
from .config import (
    BACKUP_DIR,
    BACKUP_KEEP_DAILY,
    BACKUP_KEEP_LAST,
    BACKUP_KEEP_MONTHLY,
    BACKUP_KEEP_WEEKLY,
    BACKUP_MAX_BYTES,
    BACKUP_S3_URI,
)
from .hashing import file_digest
from .minecraft import execute_rcon
from .monitoring import folder_size
from .processes import apply_server_permissions, run, service_state
from .runtime import server_runtime_states
from .schemas import AgentActionResult, AgentServer, BackupItem, BackupRequest, RestoreRequest, StoredServer
from .security import ensure_child_path, server_base_path


def backup_manifest_path(archive: Path) -> Path:
    return archive.with_suffix(archive.suffix + ".manifest.json")


def backup_archive_path(backup_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", backup_id):
        raise HTTPException(status_code=400, detail="Invalid backup id")
    archive = ensure_child_path(BACKUP_DIR, f"{backup_id}.tar.gz")
    if not archive.exists():
        raise HTTPException(status_code=404, detail="Backup not found")
    return archive


def backup_part_paths(server: StoredServer, parts: list[str]) -> list[Path]:
    root = server_base_path(server)
    selected: list[Path] = []
    root_files = ["server.properties", "whitelist.json", "ops.json", "banned-players.json", "eula.txt"]
    if "world" in parts:
        selected.append(root / "world")
    if "mods" in parts:
        selected.append(root / "mods")
    if "config" in parts:
        selected.append(root / "config")
    if "root" in parts:
        selected.extend(root / name for name in root_files)
    return [path for path in selected if path.exists()]


def iter_backup_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(item for item in path.rglob("*") if item.is_file())
    return sorted(files)


def execute_save_command(server: StoredServer, command: str) -> None:
    if not server.rcon_password:
        return
    try:
        execute_rcon(server, command)
    except HTTPException as error:
        append_action_log("backup_rcon_warning", server.id, f"{command}: {error.detail}")


def create_backup_archive(server: StoredServer, request: BackupRequest, reason: str = "manual") -> BackupItem:
    root = server_base_path(server)
    paths = backup_part_paths(server, request.parts)
    if not paths:
        raise HTTPException(status_code=404, detail="No backup sources found")

    was_running = service_state(server.service) == "running"
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    server_runtime_states[server.id] = "backing_up"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_id = f"{server.id}-{stamp}"
    archive = BACKUP_DIR / f"{backup_id}.tar.gz"

    try:
        if request.mode == "stopped" and was_running:
            result = run(["systemctl", "stop", server.service], timeout=90)
            if result.returncode != 0:
                raise HTTPException(status_code=500, detail=result.stderr.strip() or "Failed to stop server")
        elif request.mode == "live" and was_running:
            execute_save_command(server, "save-off")
            execute_save_command(server, "save-all flush")

        files = iter_backup_files(paths)
        manifest = {
            "schema": 1,
            "server_id": server.id,
            "server_name": server.name,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "mode": request.mode,
            "reason": reason,
            "description": request.description,
            "parts": request.parts,
            "files": [
                {
                    "path": file.relative_to(root).as_posix(),
                    "size": file.stat().st_size,
                    "sha256": file_digest(file, "sha256"),
                }
                for file in files
            ],
        }

        manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        with tarfile.open(archive, "w:gz") as tar:
            for path in paths:
                tar.add(path, arcname=f"server/{path.relative_to(root).as_posix()}")
            info = tarfile.TarInfo("ksylian-backup-manifest.json")
            info.size = len(manifest_bytes)
            info.mtime = time.time()
            tar.addfile(info, io.BytesIO(manifest_bytes))

        manifest["archive_sha256"] = file_digest(archive, "sha256")
        manifest_path = backup_manifest_path(archive)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
        manifest_path.chmod(0o600)
        append_action_log("server_backup", server.id, str(archive))
        sync_backup_to_s3(archive)
        apply_backup_retention(server.id)
        return backup_to_item(archive)
    finally:
        if request.mode == "live" and was_running:
            execute_save_command(server, "save-on")
        if request.mode == "stopped" and was_running:
            run(["systemctl", "start", server.service], timeout=90)
        server_runtime_states.pop(server.id, None)


def backup_to_item(path: Path) -> BackupItem:
    manifest_path = backup_manifest_path(path)
    manifest: dict[str, Any] = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
        except (OSError, json.JSONDecodeError):
            manifest = {}
    return BackupItem(
        id=path.name.removesuffix(".tar.gz"),
        name=path.name,
        size=folder_size(path),
        created=datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
        server_id=str(manifest.get("server_id") or path.name.split("-", 1)[0]),
        checksum=str(manifest.get("archive_sha256") or ""),
        description=str(manifest.get("description") or ""),
        manifest=manifest_path.name if manifest_path.exists() else "",
    )


def backup_manifest(path: Path) -> dict[str, Any]:
    manifest_path = backup_manifest_path(path)
    if not manifest_path.exists():
        return {}
    try:
        return json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def backup_total_bytes() -> int:
    if not BACKUP_DIR.exists():
        return 0
    return sum(path.stat().st_size for path in BACKUP_DIR.glob("*.tar.gz") if path.exists())


def remove_backup_file(path: Path) -> None:
    path.unlink(missing_ok=True)
    backup_manifest_path(path).unlink(missing_ok=True)


def apply_backup_retention(server_id: str) -> None:
    if not BACKUP_DIR.exists():
        return
    backups = sorted(
        [path for path in BACKUP_DIR.glob(f"{server_id}-*.tar.gz")],
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    keep: set[Path] = set(backups[:BACKUP_KEEP_LAST])
    daily: set[str] = set()
    weekly: set[str] = set()
    monthly: set[str] = set()
    for path in backups:
        created = datetime.fromtimestamp(path.stat().st_mtime)
        day_key = created.strftime("%Y-%m-%d")
        week_key = f"{created.isocalendar().year}-W{created.isocalendar().week:02d}"
        month_key = created.strftime("%Y-%m")
        if len(daily) < BACKUP_KEEP_DAILY and day_key not in daily:
            daily.add(day_key)
            keep.add(path)
        if len(weekly) < BACKUP_KEEP_WEEKLY and week_key not in weekly:
            weekly.add(week_key)
            keep.add(path)
        if len(monthly) < BACKUP_KEEP_MONTHLY and month_key not in monthly:
            monthly.add(month_key)
            keep.add(path)

    for path in backups:
        if path not in keep:
            remove_backup_file(path)
            append_action_log("backup_retention_delete", server_id, path.name)

    while BACKUP_MAX_BYTES > 0 and backup_total_bytes() > BACKUP_MAX_BYTES:
        current = sorted(BACKUP_DIR.glob("*.tar.gz"), key=lambda item: item.stat().st_mtime)
        removable = [path for path in current if path not in keep] or current
        if not removable:
            break
        path = removable[0]
        remove_backup_file(path)
        append_action_log("backup_storage_cap_delete", server_id, path.name)


def sync_backup_to_s3(path: Path) -> None:
    if not BACKUP_S3_URI:
        return
    target = f"{BACKUP_S3_URI}/{path.name}"
    result = run(["aws", "s3", "cp", str(path), target], timeout=600)
    if result.returncode != 0:
        append_action_log("backup_s3_failed", "-", result.stderr.strip() or result.stdout.strip())
        return
    manifest = backup_manifest_path(path)
    if manifest.exists():
        run(["aws", "s3", "cp", str(manifest), f"{BACKUP_S3_URI}/{manifest.name}"], timeout=600)
    append_action_log("backup_s3_uploaded", "-", target)


def verify_backup_archive(path: Path) -> None:
    manifest_path = backup_manifest_path(path)
    if not manifest_path.exists():
        return
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=409, detail="Backup manifest is invalid") from error
    expected = str(manifest.get("archive_sha256") or "")
    if expected and file_digest(path, "sha256") != expected:
        raise HTTPException(status_code=409, detail="Backup checksum mismatch")


def restore_backup(
    server: StoredServer,
    request: RestoreRequest,
    server_snapshot: Callable[[str], AgentServer],
) -> AgentActionResult:
    archive = backup_archive_path(request.backup_id)
    verify_backup_archive(archive)
    if service_state(server.service) == "running":
        raise HTTPException(status_code=409, detail="Stop the server before restoring a backup")

    if request.insurance_backup:
        create_backup_archive(
            server,
            BackupRequest(mode="stopped", parts=["world", "mods", "config", "root"], description="Before restore"),
            reason="restore-insurance",
        )

    prefixes = {
        "all": ["server/"],
        "world": ["server/world/"],
        "mods": ["server/mods/"],
        "config": ["server/config/", "server/server.properties", "server/whitelist.json", "server/ops.json", "server/banned-players.json"],
    }[request.target]
    root = server_base_path(server)
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            if not member.name.startswith("server/") or member.isdir():
                continue
            if not any(member.name == prefix or member.name.startswith(prefix) for prefix in prefixes):
                continue
            relative_name = member.name.removeprefix("server/")
            destination = ensure_child_path(root, *Path(relative_name).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            source = tar.extractfile(member)
            if source is None:
                continue
            with destination.open("wb") as file:
                shutil.copyfileobj(source, file)
    if server.managed:
        apply_server_permissions(server)
    append_action_log("server_restore", server.id, f"{archive.name}:{request.target}")
    return AgentActionResult(ok=True, message=f"{server.name}: restored {request.target}", server=server_snapshot(server.id))


def latest_restore_candidate(server: StoredServer) -> str:
    if not BACKUP_DIR.exists():
        raise HTTPException(status_code=404, detail="No backups available")
    candidates = sorted(
        [path for path in BACKUP_DIR.glob(f"{server.id}-*.tar.gz")],
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    for preferred_reason in ("pre-update", "restore-insurance", "manual"):
        for path in candidates:
            manifest = backup_manifest(path)
            if str(manifest.get("reason") or "") == preferred_reason:
                return path.name.removesuffix(".tar.gz")
    if candidates:
        return candidates[0].name.removesuffix(".tar.gz")
    raise HTTPException(status_code=404, detail="No backups available")


def rollback_last_update(server: StoredServer, server_snapshot: Callable[[str], AgentServer]) -> AgentActionResult:
    was_running = service_state(server.service) == "running"
    if was_running:
        result = run(["systemctl", "stop", server.service], timeout=90)
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=result.stderr.strip() or "Failed to stop server")
    try:
        backup_id = latest_restore_candidate(server)
        result = restore_backup(server, RestoreRequest(backup_id=backup_id, target="all", insurance_backup=True), server_snapshot)
    finally:
        if was_running:
            run(["systemctl", "start", server.service], timeout=90)
    append_action_log("server_rollback", server.id, backup_id)
    return result
