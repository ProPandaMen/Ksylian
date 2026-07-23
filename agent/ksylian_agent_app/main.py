from __future__ import annotations

import os
import base64
import io
import json
import hashlib
import re
import secrets
import shutil
import shlex
import socket
import subprocess
import tarfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, Header, HTTPException

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    tomllib = None  # type: ignore[assignment]


from .schemas import (
    AgentServer,
    StoredServer,
    CreateAgentServerRequest,
    AgentActionResult,
    ServerConfigPayload,
    RconCommandPayload,
    RconCommandResult,
    BackupRequest,
    RestoreRequest,
    BackupItem,
    FileEntry,
    FileListPayload,
    FileWriteRequest,
    FileOperationRequest,
    FileContentPayload,
    FileSearchResult,
    ModDependency,
    InstalledModItem,
    ModInstallRequest,
    ModOperationRequest,
    ModBulkInstallRequest,
    ModBulkActionRequest,
    CrashReportItem,
    AppUpdateRequest,
    AppUpdateResult,
    MetricUsage,
    DiskUsage,
    ProcessUsage,
    ServiceUsage,
    HostMonitoring,
)
from .config import (
    SERVERS,
    BACKUP_DIR,
    BACKUP_KEEP_LAST,
    BACKUP_KEEP_DAILY,
    BACKUP_KEEP_WEEKLY,
    BACKUP_KEEP_MONTHLY,
    BACKUP_MAX_BYTES,
    BACKUP_S3_URI,
    DATA_DIR,
    DISABLED_SERVERS_FILE,
    SERVERS_FILE,
    SERVER_ROOT,
    APP_DIR,
    APP_ENV_FILE,
    APP_COMPOSE_FILE,
    UPDATE_LOG,
    TOKEN,
    ACTION_LOG,
    PUBLIC_DOMAIN,
    PROXY_DOMAIN,
    PROXY_PORT,
    MINECRAFT_USER,
    RATE_LIMIT_REQUESTS,
    RATE_LIMIT_WINDOW_SECONDS,
    MINECRAFT_VERSION_MANIFEST_URL,
    FABRIC_META_API_URL,
    MODRINTH_API_URL,
    FORGE_MAVEN_URL,
    NEOFORGE_MAVEN_URL,
    PAPER_API_URL,
    PURPUR_API_URL,
    AGENT_USER_AGENT,
    SYSTEMD_DIR,
)
app = FastAPI(title="Ksylian Host Agent", version="0.1.0")
server_runtime_states: dict[str, str] = {}


@app.on_event("startup")
def ensure_agent_token_configured() -> None:
    if not TOKEN:
        raise RuntimeError("KSYLIAN_AGENT_TOKEN is required")


from .security import (
    ensure_child_path,
    is_relative_path,
    managed_server_path,
    relative_server_path,
    require_token,
    server_base_path,
    server_child_path,
)
from .processes import (
    apply_server_permissions,
    ensure_minecraft_user_exists,
    run,
    run_in,
    systemctl_issue_can_be_ignored,
)
def encode_varint(value: int) -> bytes:
    result = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        result.append(byte | 0x80 if value else byte)
        if not value:
            return bytes(result)


def read_socket_varint(sock: socket.socket) -> int:
    value = 0
    for position in range(5):
        byte = sock.recv(1)
        if not byte:
            raise OSError("Socket closed while reading varint")
        value |= (byte[0] & 0x7F) << (7 * position)
        if not byte[0] & 0x80:
            return value
    raise OSError("Varint is too large")


def minecraft_packet(packet_id: int, payload: bytes = b"") -> bytes:
    body = encode_varint(packet_id) + payload
    return encode_varint(len(body)) + body


def rcon_packet(request_id: int, packet_type: int, payload: str) -> bytes:
    body = (
        request_id.to_bytes(4, "little", signed=True)
        + packet_type.to_bytes(4, "little", signed=True)
        + payload.encode("utf-8")
        + b"\x00\x00"
    )
    return len(body).to_bytes(4, "little", signed=True) + body


def read_rcon_packet(sock: socket.socket) -> tuple[int, int, str]:
    length_bytes = read_exact(sock, 4)
    length = int.from_bytes(length_bytes, "little", signed=True)
    if length < 10 or length > 4 * 1024 * 1024:
        raise OSError("Invalid RCON packet length")
    body = read_exact(sock, length)
    request_id = int.from_bytes(body[0:4], "little", signed=True)
    packet_type = int.from_bytes(body[4:8], "little", signed=True)
    payload = body[8:-2].decode("utf-8", errors="replace")
    return request_id, packet_type, payload


def minecraft_utf(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return encode_varint(len(encoded)) + encoded


from .updates import (
    append_update_log,
    ensure_updater_configured,
    update_script_path,
    validate_update_target,
)
def append_action_log(action: str, server_id: str = "-", detail: str = "") -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "at": datetime.now().isoformat(timespec="seconds"),
        "action": action,
        "server_id": server_id,
        "detail": detail,
    }
    with ACTION_LOG.open("a") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")


from .storage import (
    active_server_ids,
    disabled_server_ids,
    legacy_server_store,
    load_server_or_404,
    load_server_store,
    save_disabled_server_ids,
    save_server_store,
    slugify,
)
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


def restore_backup(server: StoredServer, request: RestoreRequest) -> AgentActionResult:
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
    return AgentActionResult(ok=True, message=f"{server.name}: restored {request.target}", server=to_agent_server(server.id))


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


def rollback_last_update(server: StoredServer) -> AgentActionResult:
    was_running = service_state(server.service) == "running"
    if was_running:
        result = run(["systemctl", "stop", server.service], timeout=90)
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=result.stderr.strip() or "Failed to stop server")
    try:
        backup_id = latest_restore_candidate(server)
        result = restore_backup(server, RestoreRequest(backup_id=backup_id, target="all", insurance_backup=True))
    finally:
        if was_running:
            run(["systemctl", "start", server.service], timeout=90)
    append_action_log("server_rollback", server.id, backup_id)
    return result


def quick_file_label(path: Path) -> str:
    name = path.name
    if name in {"mods", "config", "world", "logs", "crash-reports"}:
        return name
    if name in {"server.properties", "whitelist.json", "ops.json", "banned-players.json"}:
        return name
    return ""


def file_entry(server: StoredServer, path: Path) -> FileEntry:
    stat = path.stat()
    return FileEntry(
        name=path.name,
        path=relative_server_path(server, path),
        kind="folder" if path.is_dir() else "file",
        size=folder_size(path) if path.is_dir() else format_bytes(stat.st_size),
        modified=datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
        quick=quick_file_label(path),
    )


def file_syntax(path: Path) -> Literal["json", "yaml", "toml", "properties", "text", "binary"]:
    name = path.name.lower()
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix in {".yml", ".yaml"}:
        return "yaml"
    if suffix == ".toml":
        return "toml"
    if suffix == ".properties" or name.endswith(".properties"):
        return "properties"
    if suffix in {".txt", ".log", ".conf", ".cfg", ".md"} or "." not in name:
        return "text"
    return "text"


def search_server_files(server: StoredServer, query: str, relative_path: str = "") -> list[FileSearchResult]:
    search = query.strip().lower()
    if len(search) < 2:
        raise HTTPException(status_code=400, detail="Search query must contain at least 2 characters")
    root = server_child_path(server, relative_path)
    if not root.exists():
        raise HTTPException(status_code=404, detail="Search path not found")
    files = [root] if root.is_file() else [item for item in root.rglob("*") if item.is_file()]
    results: list[FileSearchResult] = []
    for path in files:
        if path.stat().st_size > 2 * 1024 * 1024:
            continue
        try:
            lines = path.read_text(errors="strict").splitlines()
        except UnicodeDecodeError:
            continue
        for index, line in enumerate(lines, start=1):
            if search in line.lower():
                results.append(
                    FileSearchResult(
                        path=relative_server_path(server, path),
                        line=index,
                        preview=line.strip()[:220],
                        syntax=file_syntax(path),
                    ),
                )
                if len(results) >= 100:
                    return results
    return results


def list_server_files(server: StoredServer, relative_path: str = "") -> FileListPayload:
    directory = server_child_path(server, relative_path)
    if not directory.exists():
        raise HTTPException(status_code=404, detail="Path not found")
    if not directory.is_dir():
        raise HTTPException(status_code=400, detail="Path is not a directory")
    entries = [file_entry(server, item) for item in sorted(directory.iterdir(), key=lambda item: (item.is_file(), item.name.lower()))]
    return FileListPayload(path=relative_server_path(server, directory) if directory != server_base_path(server) else "", entries=entries)


def read_server_file(server: StoredServer, relative_path: str) -> FileContentPayload:
    path = server_child_path(server, relative_path)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    if path.stat().st_size > 2 * 1024 * 1024:
        return FileContentPayload(
            path=relative_server_path(server, path),
            name=path.name,
            content=base64.b64encode(path.read_bytes()).decode("ascii"),
            encoding="base64",
            syntax="binary",
        )
    try:
        return FileContentPayload(
            path=relative_server_path(server, path),
            name=path.name,
            content=path.read_text(),
            encoding="text",
            syntax=file_syntax(path),
        )
    except UnicodeDecodeError:
        return FileContentPayload(
            path=relative_server_path(server, path),
            name=path.name,
            content=base64.b64encode(path.read_bytes()).decode("ascii"),
            encoding="base64",
            syntax="binary",
        )


def write_server_file(server: StoredServer, request: FileWriteRequest) -> FileEntry:
    path = server_child_path(server, request.path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if request.encoding == "base64":
        data = base64.b64decode(request.content)
        if len(data) > 128 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="File is too large")
        path.write_bytes(data)
    else:
        if len(request.content.encode("utf-8")) > 4 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Text file is too large")
        path.write_text(request.content)
    if server.managed:
        apply_server_permissions(server)
    append_action_log("server_file_write", server.id, relative_server_path(server, path))
    return file_entry(server, path)


def operate_server_file(server: StoredServer, request: FileOperationRequest) -> FileEntry | dict[str, bool]:
    path = server_child_path(server, request.path)
    root = server_base_path(server)
    if request.action == "mkdir":
        path.mkdir(parents=True, exist_ok=True)
        append_action_log("server_file_mkdir", server.id, relative_server_path(server, path))
        return file_entry(server, path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Path not found")
    if request.action == "delete":
        trash_dir = root / ".ksylian-trash"
        trash_dir.mkdir(exist_ok=True)
        target = ensure_child_path(trash_dir, f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{path.name}")
        shutil.move(str(path), str(target))
        append_action_log("server_file_delete", server.id, relative_server_path(server, path))
        return {"ok": True}
    if request.action in {"move", "rename"}:
        if not request.target_path.strip():
            raise HTTPException(status_code=400, detail="Target path is required")
        target = server_child_path(server, request.target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(target))
        append_action_log("server_file_move", server.id, f"{relative_server_path(server, path)} -> {relative_server_path(server, target)}")
        return file_entry(server, target)
    if request.action == "extract":
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as archive:
                for member in archive.infolist():
                    destination = ensure_child_path(path.parent, *Path(member.filename).parts)
                    if member.is_dir():
                        destination.mkdir(parents=True, exist_ok=True)
                    else:
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(member) as source, destination.open("wb") as output:
                            shutil.copyfileobj(source, output)
        elif path.name.endswith(".tar.gz"):
            with tarfile.open(path, "r:gz") as archive:
                for member in archive.getmembers():
                    destination = ensure_child_path(path.parent, *Path(member.name).parts)
                    if member.isdir():
                        destination.mkdir(parents=True, exist_ok=True)
                    else:
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        source = archive.extractfile(member)
                        if source is not None:
                            with destination.open("wb") as output:
                                shutil.copyfileobj(source, output)
        else:
            raise HTTPException(status_code=400, detail="Only ZIP and TAR.GZ archives can be extracted")
        append_action_log("server_file_extract", server.id, relative_server_path(server, path))
        return file_entry(server, path.parent)
    raise HTTPException(status_code=400, detail="Unsupported file action")


def normalize_dependency(value: Any) -> list[ModDependency]:
    dependencies: list[ModDependency] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, str):
                dependencies.append(ModDependency(id=str(key), version=item))
            elif isinstance(item, dict):
                dependencies.append(
                    ModDependency(
                        id=str(key),
                        version=str(item.get("version") or item.get("versionRange") or ""),
                        required=str(item.get("type") or "").lower() != "optional",
                    ),
                )
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                dependencies.append(
                    ModDependency(
                        id=str(item.get("modId") or item.get("id") or ""),
                        version=str(item.get("versionRange") or item.get("version") or ""),
                        required=not bool(item.get("optional", False)),
                    ),
                )
    return [dependency for dependency in dependencies if dependency.id]


def mod_metadata_from_fabric(data: dict[str, Any]) -> dict[str, Any]:
    environment = str(data.get("environment") or "*")
    side = "both"
    if environment == "client":
        side = "client"
    elif environment == "server":
        side = "server"
    return {
        "id": str(data.get("id") or ""),
        "name": str(data.get("name") or data.get("id") or ""),
        "version": str(data.get("version") or ""),
        "loader": "fabric",
        "side": side,
        "dependencies": normalize_dependency(data.get("depends")),
    }


def mod_metadata_from_toml(data: dict[str, Any], loader: Literal["forge", "neoforge"]) -> dict[str, Any]:
    mods = data.get("mods")
    first = mods[0] if isinstance(mods, list) and mods else {}
    mod_id = str(first.get("modId") or first.get("modid") or "") if isinstance(first, dict) else ""
    dependencies = normalize_dependency(data.get("dependencies", {}).get(mod_id) if isinstance(data.get("dependencies"), dict) else [])
    return {
        "id": mod_id,
        "name": str(first.get("displayName") or first.get("display_name") or mod_id) if isinstance(first, dict) else mod_id,
        "version": str(first.get("version") or "") if isinstance(first, dict) else "",
        "loader": loader,
        "side": "both",
        "dependencies": dependencies,
    }


def parse_mod_toml_fallback(content: str) -> dict[str, Any]:
    mod_match = re.search(r"\[\[mods]](?P<body>.*?)(?:\n\[|\Z)", content, re.DOTALL)
    body = mod_match.group("body") if mod_match else content

    def find_string(key: str) -> str:
        match = re.search(rf"^\s*{re.escape(key)}\s*=\s*[\"']([^\"']+)[\"']", body, re.MULTILINE)
        return match.group(1).strip() if match else ""

    mod_id = find_string("modId") or find_string("modid")
    dependencies: list[dict[str, str]] = []
    for block in re.finditer(r"\[\[dependencies\.[^\]]+]](?P<body>.*?)(?:\n\[|\Z)", content, re.DOTALL):
        dep_body = block.group("body")
        dep_id = re.search(r"^\s*modId\s*=\s*[\"']([^\"']+)[\"']", dep_body, re.MULTILINE)
        dep_version = re.search(r"^\s*versionRange\s*=\s*[\"']([^\"']+)[\"']", dep_body, re.MULTILINE)
        if dep_id:
            dependencies.append(
                {
                    "modId": dep_id.group(1).strip(),
                    "versionRange": dep_version.group(1).strip() if dep_version else "",
                },
            )

    return {
        "mods": [
            {
                "modId": mod_id,
                "displayName": find_string("displayName") or mod_id,
                "version": find_string("version"),
            },
        ],
        "dependencies": {mod_id: dependencies} if mod_id else {},
    }


def read_mod_metadata(path: Path) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "id": path.stem.removesuffix(".jar"),
        "name": path.stem.removesuffix(".jar"),
        "version": "",
        "loader": "unknown",
        "side": "unknown",
        "dependencies": [],
    }
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if "fabric.mod.json" in names:
                data = json.loads(archive.read("fabric.mod.json").decode("utf-8"))
                if isinstance(data, dict):
                    metadata.update(mod_metadata_from_fabric(data))
            for toml_name, loader in (
                ("META-INF/neoforge.mods.toml", "neoforge"),
                ("META-INF/mods.toml", "forge"),
            ):
                if toml_name in names:
                    content = archive.read(toml_name).decode("utf-8")
                    data = tomllib.loads(content) if tomllib is not None else parse_mod_toml_fallback(content)
                    if isinstance(data, dict):
                        metadata.update(mod_metadata_from_toml(data, loader))
                    break
    except (OSError, zipfile.BadZipFile, KeyError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        pass
    return metadata


def scan_installed_mods(server: StoredServer) -> list[InstalledModItem]:
    mods_dir = server_child_path(server, "mods")
    if not mods_dir.exists():
        return []
    candidates = sorted(
        [path for path in mods_dir.iterdir() if path.is_file() and (path.name.endswith(".jar") or path.name.endswith(".jar.disabled"))],
        key=lambda item: item.name.lower(),
    )
    raw_items: list[InstalledModItem] = []
    for path in candidates:
        enabled = path.name.endswith(".jar")
        metadata = read_mod_metadata(path)
        warnings: list[str] = []
        if metadata["loader"] == "unknown":
            warnings.append("Неизвестный JAR: metadata не найдена")
        if metadata["side"] == "client":
            warnings.append("Похоже на client-only мод")
        raw_items.append(
            InstalledModItem(
                id=str(metadata["id"] or path.stem),
                name=str(metadata["name"] or path.stem),
                version=str(metadata["version"] or ""),
                loader=metadata["loader"],
                side=metadata["side"],
                filename=path.name,
                path=relative_server_path(server, path),
                size=format_bytes(path.stat().st_size),
                enabled=enabled,
                sha1=file_digest(path, "sha1"),
                sha256=file_digest(path, "sha256"),
                sha512=file_digest(path, "sha512"),
                dependencies=metadata["dependencies"],
                warnings=warnings,
            ),
        )
    counts: dict[str, int] = {}
    versions: dict[str, set[str]] = {}
    for item in raw_items:
        counts[item.id] = counts.get(item.id, 0) + 1
        versions.setdefault(item.id, set()).add(item.version)
    for item in raw_items:
        item.duplicate = counts.get(item.id, 0) > 1
        item.multiple_versions = len(versions.get(item.id, set())) > 1
        if server.type in {"fabric", "forge", "neoforge"} and item.loader not in {server.type, "unknown"}:
            item.warnings.append(f"Загрузчик {item.loader} не совпадает с сервером {server.type}")
        if item.loader == "unknown":
            item.warnings.append("Нельзя проверить совместимость загрузчика")
        installed_ids = set(counts)
        for dependency in item.dependencies:
            if dependency.required and dependency.id not in installed_ids and dependency.id not in {"minecraft", "java", "fabricloader", "forge", "neoforge"}:
                item.warnings.append(f"Не найдена зависимость {dependency.id}")
        if item.duplicate:
            item.warnings.append("Найден дубликат mod ID")
        if item.multiple_versions:
            item.warnings.append("Найдено несколько версий одного мода")
    return raw_items


def install_mod(server: StoredServer, request: ModInstallRequest) -> InstalledModItem:
    filename = Path(request.filename).name
    if not filename.endswith(".jar"):
        raise HTTPException(status_code=400, detail="Only .jar mods can be installed")
    mods_dir = server_child_path(server, "mods")
    mods_dir.mkdir(exist_ok=True)
    data = base64.b64decode(request.content)
    if len(data) > 128 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Mod file is too large")
    destination = ensure_child_path(mods_dir, filename)
    destination.write_bytes(data)
    if request.pinned:
        (mods_dir / ".ksylian-pins.json").write_text(json.dumps({filename: request.release_channel}, ensure_ascii=False, indent=2))
    if server.managed:
        apply_server_permissions(server)
    append_action_log("server_mod_install", server.id, filename)
    return next(item for item in scan_installed_mods(server) if item.filename == filename)


def operate_mod(server: StoredServer, request: ModOperationRequest) -> dict[str, bool]:
    path = server_child_path(server, request.path)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Mod not found")
    if request.action == "delete":
        operate_server_file(server, FileOperationRequest(action="delete", path=relative_server_path(server, path)))
    elif request.action == "disable":
        if path.name.endswith(".jar.disabled"):
            return {"ok": True}
        target = path.with_name(f"{path.name}.disabled")
        shutil.move(str(path), str(target))
    elif request.action == "enable":
        if not path.name.endswith(".jar.disabled"):
            return {"ok": True}
        target = path.with_name(path.name.removesuffix(".disabled"))
        shutil.move(str(path), str(target))
    elif request.action == "pin":
        pins_path = server_child_path(server, "mods/.ksylian-pins.json")
        pins: dict[str, bool] = {}
        if pins_path.exists():
            try:
                pins = json.loads(pins_path.read_text())
            except (OSError, json.JSONDecodeError):
                pins = {}
        pins[path.name] = True
        pins_path.write_text(json.dumps(pins, ensure_ascii=False, indent=2))
    elif request.action == "update":
        if not request.content:
            raise HTTPException(status_code=400, detail="Updated mod content is required")
        filename = Path(request.filename or path.name.removesuffix(".disabled")).name
        if not filename.endswith(".jar"):
            raise HTTPException(status_code=400, detail="Updated mod must be a .jar")
        target = path.with_name(filename)
        data = base64.b64decode(request.content)
        if len(data) > 128 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Mod file is too large")
        path.unlink(missing_ok=True)
        target.write_bytes(data)
    append_action_log(f"server_mod_{request.action}", server.id, relative_server_path(server, path))
    return {"ok": True}


def bulk_install_mods(server: StoredServer, request: ModBulkInstallRequest) -> list[InstalledModItem]:
    if len(request.items) > 50:
        raise HTTPException(status_code=413, detail="Too many mods in one request")
    installed: list[InstalledModItem] = []
    for item in request.items:
        installed.append(install_mod(server, item))
    append_action_log("server_mod_bulk_install", server.id, str(len(installed)))
    return installed


def bulk_operate_mods(server: StoredServer, request: ModBulkActionRequest) -> dict[str, int]:
    if len(request.items) > 100:
        raise HTTPException(status_code=413, detail="Too many mod operations in one request")
    completed = 0
    for item in request.items:
        if not item.path:
            continue
        operation = ModOperationRequest(
            action=request.action,
            path=item.path,
            filename=item.filename,
            content=item.content,
            release_channel=item.release_channel,
        )
        operate_mod(server, operation)
        completed += 1
    append_action_log(f"server_mod_bulk_{request.action}", server.id, str(completed))
    return {"completed": completed}


def host_primary_ip() -> str:
    for ip in host_ips():
        if not ip.startswith("127.") and not ip.startswith("172."):
            return ip
    return "127.0.0.1"


def is_port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("0.0.0.0", port))
        except OSError:
            return False
    return True


def allocate_port(servers: dict[str, StoredServer], start: int = 25565) -> int:
    used_ports = {server.port for server in servers.values()}
    for port in range(start, start + 200):
        if port not in used_ports and is_port_available(port):
            return port
    raise HTTPException(status_code=507, detail="No free Minecraft ports available")


def server_type_label(server_type: str) -> str:
    if server_type == "vanilla":
        return "Vanilla"
    if server_type == "paper":
        return "Paper"
    if server_type == "purpur":
        return "Purpur"
    if server_type == "fabric":
        return "Fabric"
    if server_type == "forge":
        return "Forge"
    if server_type == "neoforge":
        return "NeoForge"
    return server_type


def normalize_ram(value: str, fallback: str) -> str:
    candidate = value.strip().upper().replace(" ", "")
    if re.fullmatch(r"[1-9][0-9]*(M|G)", candidate):
        return candidate
    return fallback


def ram_to_bytes(value: str) -> int:
    normalized = normalize_ram(value, "0M")
    amount = int(normalized[:-1])
    return amount * (1024**3 if normalized.endswith("G") else 1024**2)


def normalize_cpu_limit(value: int) -> int:
    return max(10, min(int(value or 100), 400))


def normalize_jvm_args(value: str) -> list[str]:
    try:
        args = shlex.split(value)
    except ValueError:
        return []
    forbidden_prefixes = ("-jar", "-cp", "-classpath", "@")
    return [arg for arg in args if not arg.startswith(forbidden_prefixes) and "\x00" not in arg][:24]


def ensure_disk_space_for_server(server: StoredServer) -> None:
    SERVER_ROOT.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(SERVER_ROOT)
    required = max(2 * 1024**3, ram_to_bytes(server.max_ram))
    if usage.free < required:
        raise HTTPException(
            status_code=507,
            detail=f"Not enough free disk space. Need at least {format_bytes(required)}, available {format_bytes(usage.free)}",
        )


def server_warnings(server: StoredServer) -> list[str]:
    warnings: list[str] = []
    try:
        usage = shutil.disk_usage(server_base_path(server) if Path(server.path).exists() else SERVER_ROOT)
        if usage.free < max(2 * 1024**3, ram_to_bytes(server.max_ram)):
            warnings.append("Мало свободного места на диске")
    except OSError:
        warnings.append("Не удалось проверить свободное место")
    if ram_to_bytes(server.max_ram) > shutil.disk_usage(SERVER_ROOT).free:
        warnings.append("Лимит RAM больше текущего свободного места на диске")
    if service_state(server.service) == "running" and minecraft_player_status(server.port) == "-":
        warnings.append("Процесс запущен, но Minecraft status ping не отвечает")
    return warnings


def start_command_for_server(server: StoredServer, java: str) -> list[str]:
    min_ram = normalize_ram(server.min_ram, "1G")
    max_ram = normalize_ram(server.max_ram, "2G")
    return [java, f"-Xms{min_ram}", f"-Xmx{max_ram}", *server.jvm_args, "-jar", "server.jar", "nogui"]


def write_server_scaffold(server: StoredServer) -> None:
    server_path = server_base_path(server)
    if not server.rcon_password:
        server.rcon_password = secrets.token_urlsafe(24)
    if not server.rcon_port:
        server.rcon_port = min(server.port + 10000, 65535)
    server_path.mkdir(parents=True, exist_ok=True)
    (server_path / "mods").mkdir(exist_ok=True)
    (server_path / "logs").mkdir(exist_ok=True)
    (server_path / "world").mkdir(exist_ok=True)
    eula_path = server_path / "eula.txt"
    if not eula_path.exists():
        eula_path.write_text("eula=true\n")

    properties_path = server_path / "server.properties"
    if not properties_path.exists():
        properties_path.write_text(
            "\n".join(
                [
                    f"server-port={server.port}",
                    f"motd={server.name}",
                    "enable-query=false",
                    "online-mode=true",
                    "enable-rcon=true",
                    f"rcon.port={server.rcon_port}",
                    f"rcon.password={server.rcon_password}",
                    "max-players=20",
                    "view-distance=10",
                    "simulation-distance=10",
                    "",
                ]
            )
        )
    (server_path / "ksylian.json").write_text(json.dumps(server.model_dump(), ensure_ascii=False, indent=2))


def request_json(url: str, timeout: int = 30) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": AGENT_USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise HTTPException(status_code=502, detail=f"Download metadata request failed: HTTP {error.code}") from error
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=502, detail=f"Download metadata request failed: {error}") from error


def request_text(url: str, timeout: int = 30) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": AGENT_USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        raise HTTPException(status_code=502, detail=f"Download metadata request failed: HTTP {error.code}") from error
    except (urllib.error.URLError, TimeoutError, UnicodeDecodeError) as error:
        raise HTTPException(status_code=502, detail=f"Download metadata request failed: {error}") from error


def file_digest(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_file(
    url: str,
    destination: Path,
    *,
    md5: str = "",
    sha1: str = "",
    sha256: str = "",
    sha512: str = "",
    minimum_size: int = 1024,
) -> None:
    if not is_relative_path(destination, SERVER_ROOT):
        raise HTTPException(status_code=400, detail="Download destination is outside allowed directory")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(f"{destination.suffix}.tmp")
    last_error: Exception | None = None

    for attempt in range(3):
        request = urllib.request.Request(url, headers={"User-Agent": AGENT_USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=180) as response, temporary.open("wb") as file:
                shutil.copyfileobj(response, file)
            if temporary.stat().st_size < minimum_size:
                raise OSError("downloaded file is unexpectedly small")
            if md5 and file_digest(temporary, "md5").lower() != md5.lower():
                raise OSError("downloaded file md5 checksum mismatch")
            if sha1 and file_digest(temporary, "sha1").lower() != sha1.lower():
                raise OSError("downloaded file sha1 checksum mismatch")
            if sha256 and file_digest(temporary, "sha256").lower() != sha256.lower():
                raise OSError("downloaded file sha256 checksum mismatch")
            if sha512 and file_digest(temporary, "sha512").lower() != sha512.lower():
                raise OSError("downloaded file sha512 checksum mismatch")
            temporary.replace(destination)
            return
        except urllib.error.HTTPError as error:
            temporary.unlink(missing_ok=True)
            last_error = error
            if error.code < 500:
                break
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            temporary.unlink(missing_ok=True)
            last_error = error
        if attempt < 2:
            time.sleep(1 + attempt)

    if isinstance(last_error, urllib.error.HTTPError):
        raise HTTPException(status_code=502, detail=f"Server jar download failed: HTTP {last_error.code}") from last_error
    raise HTTPException(status_code=502, detail=f"Server jar download failed: {last_error}") from last_error


def download_vanilla_server_jar(version: str, destination: Path) -> None:
    manifest = request_json(MINECRAFT_VERSION_MANIFEST_URL)
    versions = manifest.get("versions")
    if not isinstance(versions, list):
        raise HTTPException(status_code=502, detail="Minecraft version manifest is invalid")

    version_url = ""
    for item in versions:
        if isinstance(item, dict) and item.get("id") == version:
            version_url = str(item.get("url") or "")
            break
    if not version_url:
        raise HTTPException(status_code=404, detail=f"Minecraft version {version} was not found")

    metadata = request_json(version_url)
    server_download = metadata.get("downloads", {}).get("server", {})
    server_url = str(server_download.get("url") or "")
    server_sha1 = str(server_download.get("sha1") or "")
    if not server_url:
        raise HTTPException(status_code=404, detail=f"Server jar for Minecraft {version} was not found")

    download_file(server_url, destination, sha1=server_sha1)


def download_paper_server_jar(version: str, destination: Path) -> None:
    builds = request_json(f"{PAPER_API_URL}/versions/{version}/builds")
    if not isinstance(builds, list) or not builds:
        raise HTTPException(status_code=404, detail=f"Paper build for Minecraft {version} was not found")

    selected = next((item for item in builds if isinstance(item, dict) and item.get("channel") == "STABLE"), None)
    if selected is None:
        selected = next((item for item in builds if isinstance(item, dict)), None)
    if selected is None:
        raise HTTPException(status_code=404, detail=f"Paper build for Minecraft {version} was not found")

    download = selected.get("downloads", {}).get("server:default", {})
    download_url = str(download.get("url") or "")
    checksum = str(download.get("checksums", {}).get("sha256") or "")
    if not download_url:
        raise HTTPException(status_code=404, detail=f"Paper server jar for Minecraft {version} was not found")

    download_file(download_url, destination, sha256=checksum)


def download_purpur_server_jar(version: str, destination: Path) -> None:
    metadata = request_json(f"{PURPUR_API_URL}/{version}")
    builds = metadata.get("builds") if isinstance(metadata, dict) else None
    latest = str(builds.get("latest") or "") if isinstance(builds, dict) else ""
    if not latest:
        raise HTTPException(status_code=404, detail=f"Purpur build for Minecraft {version} was not found")

    build_metadata = request_json(f"{PURPUR_API_URL}/{version}/{latest}")
    checksum = str(build_metadata.get("md5") or "") if isinstance(build_metadata, dict) else ""
    download_file(f"{PURPUR_API_URL}/{version}/{latest}/download", destination, md5=checksum)


def latest_fabric_component(path: str, label: str) -> str:
    items = request_json(f"{FABRIC_META_API_URL}{path}")
    if not isinstance(items, list):
        raise HTTPException(status_code=502, detail=f"Fabric {label} metadata is invalid")
    for item in items:
        if isinstance(item, dict) and item.get("stable") is True and item.get("version"):
            return str(item["version"])
    for item in items:
        if isinstance(item, dict) and item.get("version"):
            return str(item["version"])
    raise HTTPException(status_code=404, detail=f"Fabric {label} version was not found")


def fabric_loader_versions(minecraft_version: str = "") -> list[str]:
    path = f"/versions/loader/{minecraft_version}" if minecraft_version else "/versions/loader"
    items = request_json(f"{FABRIC_META_API_URL}{path}")
    if not isinstance(items, list):
        raise HTTPException(status_code=502, detail="Fabric loader metadata is invalid")
    versions: list[str] = []
    for item in items:
        loader = item.get("loader") if isinstance(item, dict) and minecraft_version else item
        if isinstance(loader, dict) and loader.get("version"):
            versions.append(str(loader["version"]))
    return list(dict.fromkeys(versions))


def fabric_installer_versions() -> list[str]:
    items = request_json(f"{FABRIC_META_API_URL}/versions/installer")
    if not isinstance(items, list):
        raise HTTPException(status_code=502, detail="Fabric installer metadata is invalid")
    return [str(item["version"]) for item in items if isinstance(item, dict) and item.get("version")]


def download_fabric_server_jar(
    version: str,
    destination: Path,
    loader_version: str = "",
    installer_version: str = "",
) -> None:
    loaders = request_json(f"{FABRIC_META_API_URL}/versions/loader/{version}")
    if not isinstance(loaders, list) or not loaders:
        raise HTTPException(status_code=404, detail=f"Fabric loader for Minecraft {version} was not found")

    selected_loader_version = loader_version.strip()
    if selected_loader_version and selected_loader_version not in fabric_loader_versions(version):
        raise HTTPException(status_code=404, detail=f"Fabric loader {selected_loader_version} for Minecraft {version} was not found")
    loader_version = selected_loader_version
    for item in loaders:
        loader = item.get("loader") if isinstance(item, dict) else None
        if not loader_version and isinstance(loader, dict) and loader.get("stable") is True and loader.get("version"):
            loader_version = str(loader["version"])
            break
    if not loader_version:
        loader = loaders[0].get("loader") if isinstance(loaders[0], dict) else None
        loader_version = str(loader.get("version") or "") if isinstance(loader, dict) else ""
    if not loader_version:
        raise HTTPException(status_code=404, detail=f"Fabric loader for Minecraft {version} was not found")

    installer_versions = fabric_installer_versions()
    selected_installer_version = installer_version.strip()
    if selected_installer_version and selected_installer_version not in installer_versions:
        raise HTTPException(status_code=404, detail=f"Fabric installer {selected_installer_version} was not found")
    installer_version = selected_installer_version or latest_fabric_component("/versions/installer", "installer")
    download_file(
        f"{FABRIC_META_API_URL}/versions/loader/{version}/{loader_version}/{installer_version}/server/jar",
        destination,
    )


def install_fabric_api(server: StoredServer) -> None:
    mods_dir = server_base_path(server) / "mods"
    mods_dir.mkdir(parents=True, exist_ok=True)
    query = urllib.parse.urlencode({"loaders": '["fabric"]', "game_versions": json.dumps([server.version])})
    versions = request_json(f"{MODRINTH_API_URL}/project/fabric-api/version?{query}")
    if not isinstance(versions, list) or not versions:
        raise HTTPException(status_code=404, detail=f"Fabric API for Minecraft {server.version} was not found")
    selected = next((item for item in versions if isinstance(item, dict) and item.get("version_type") == "release"), None)
    selected = selected or next((item for item in versions if isinstance(item, dict)), None)
    files = selected.get("files") if isinstance(selected, dict) else None
    primary = next((item for item in files if isinstance(item, dict) and item.get("primary")), None) if isinstance(files, list) else None
    file_item = primary or (files[0] if isinstance(files, list) and files else None)
    if not isinstance(file_item, dict):
        raise HTTPException(status_code=404, detail="Fabric API download was not found")
    filename = Path(str(file_item.get("filename") or "fabric-api.jar")).name
    url = str(file_item.get("url") or "")
    sha512 = str(file_item.get("hashes", {}).get("sha512") or "")
    if not url:
        raise HTTPException(status_code=404, detail="Fabric API download URL was not found")
    download_file(url, mods_dir / filename, sha512=sha512)


def forge_versions() -> list[str]:
    metadata = request_text(f"{FORGE_MAVEN_URL}/maven-metadata.xml")
    try:
        root = ET.fromstring(metadata)
    except ET.ParseError as error:
        raise HTTPException(status_code=502, detail="Forge metadata is invalid") from error
    return [item.text.strip() for item in root.findall(".//version") if item.text and item.text.strip()]


def latest_forge_version(minecraft_version: str, selected_version: str = "") -> str:
    if selected_version.strip():
        versions = forge_versions()
        if selected_version.strip() not in versions:
            raise HTTPException(status_code=404, detail=f"Forge build {selected_version} was not found")
        return selected_version.strip()
    prefix = f"{minecraft_version}-"
    matches = [version for version in forge_versions() if version.startswith(prefix)]
    if not matches:
        raise HTTPException(status_code=404, detail=f"Forge build for Minecraft {minecraft_version} was not found")
    return matches[-1]


def neoforge_versions() -> list[str]:
    metadata = request_text(f"{NEOFORGE_MAVEN_URL}/maven-metadata.xml")
    try:
        root = ET.fromstring(metadata)
    except ET.ParseError as error:
        raise HTTPException(status_code=502, detail="NeoForge metadata is invalid") from error
    return [item.text.strip() for item in root.findall(".//version") if item.text and item.text.strip()]


def latest_neoforge_version(minecraft_version: str, selected_version: str = "") -> str:
    versions = neoforge_versions()
    if selected_version.strip():
        if selected_version.strip() not in versions:
            raise HTTPException(status_code=404, detail=f"NeoForge build {selected_version} was not found")
        return selected_version.strip()
    # NeoForge 1.20.2+ versions are commonly published as 20.2.x, 20.4.x, etc.
    version = minecraft_version_key(minecraft_version)
    prefix = f"{version[1]}.{version[2]}." if version[0] == 1 and version[1] >= 20 else minecraft_version
    matches = [item for item in versions if item.startswith(prefix)]
    if not matches:
        matches = [item for item in versions if minecraft_version in item]
    if not matches:
        raise HTTPException(status_code=404, detail=f"NeoForge build for Minecraft {minecraft_version} was not found")
    return matches[-1]


def minecraft_version_key(version: str) -> tuple[int, int, int]:
    match = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?", version)
    if not match:
        return (0, 0, 0)
    return tuple(int(part or 0) for part in match.groups())


def required_java_major(minecraft_version: str) -> int:
    version = minecraft_version_key(minecraft_version)
    if version >= (1, 20, 5):
        return 21
    if version >= (1, 18, 0):
        return 17
    return 8


def java_major_version(binary: str) -> int | None:
    result = run([binary, "-version"], timeout=10)
    output = f"{result.stdout}\n{result.stderr}"
    match = re.search(r'version "([^"]+)"', output)
    if not match:
        return None
    version = match.group(1)
    if version.startswith("1."):
        parts = version.split(".")
        return int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
    major = version.split(".", 1)[0]
    return int(major) if major.isdigit() else None


def java_candidates(required_major: int, selected_runtime: str = "auto") -> list[str]:
    candidates: list[str] = []
    if selected_runtime in {"8", "17", "21"}:
        selected_value = os.getenv(f"KSYLIAN_JAVA_{selected_runtime}", "")
        if selected_value:
            candidates.append(selected_value)
    env_value = os.getenv(f"KSYLIAN_JAVA_{required_major}", "")
    if env_value:
        candidates.append(env_value)
    for major in (21, 17, 8):
        env_candidate = os.getenv(f"KSYLIAN_JAVA_{major}", "")
        if env_candidate:
            candidates.append(env_candidate)
    default = shutil.which("java")
    if default:
        candidates.append(default)
    return list(dict.fromkeys(candidates))


def java_binary(minecraft_version: str = "", selected_runtime: str = "auto") -> str:
    required_major = required_java_major(minecraft_version) if minecraft_version else 8
    if selected_runtime in {"8", "17", "21"}:
        required_major = max(required_major, int(selected_runtime))
    checked: list[str] = []
    for candidate in java_candidates(required_major, selected_runtime):
        major = java_major_version(candidate)
        checked.append(f"{candidate} ({major or 'unknown'})")
        if major and major >= required_major:
            return candidate
    if not checked:
        raise HTTPException(status_code=500, detail="Java is not installed on this host")
    raise HTTPException(
        status_code=409,
        detail=f"Minecraft {minecraft_version} requires Java {required_major}+. Checked: {', '.join(checked)}",
    )


def install_forge_server(server: StoredServer) -> list[str]:
    server_path = server_base_path(server)
    forge_version = latest_forge_version(server.version, server.loader_version)
    installer = server_path / f"forge-{forge_version}-installer.jar"
    download_file(f"{FORGE_MAVEN_URL}/{forge_version}/forge-{forge_version}-installer.jar", installer)

    java = java_binary(server.version, server.java_runtime)
    min_ram = normalize_ram(server.min_ram, "1G")
    max_ram = normalize_ram(server.max_ram, "2G")
    result = run_in([java, "-jar", str(installer), "--installServer"], cwd=server_path, timeout=600)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "Forge installer failed"
        raise HTTPException(status_code=502, detail=detail)

    unix_args = server_path / "libraries" / "net" / "minecraftforge" / "forge" / forge_version / "unix_args.txt"
    if unix_args.exists():
        return [
            java,
            f"-Xms{min_ram}",
            f"-Xmx{max_ram}",
            *server.jvm_args,
            "@libraries/net/minecraftforge/forge/{forge_version}/unix_args.txt".format(forge_version=forge_version),
            "nogui",
        ]

    forge_jar = next(server_path.glob(f"forge-{forge_version}*.jar"), None)
    if forge_jar:
        return [java, f"-Xms{min_ram}", f"-Xmx{max_ram}", *server.jvm_args, "-jar", forge_jar.name, "nogui"]

    raise HTTPException(status_code=502, detail="Forge installer did not produce a runnable server")


def install_neoforge_server(server: StoredServer) -> list[str]:
    server_path = server_base_path(server)
    neoforge_version = latest_neoforge_version(server.version, server.loader_version)
    installer = server_path / f"neoforge-{neoforge_version}-installer.jar"
    download_file(f"{NEOFORGE_MAVEN_URL}/{neoforge_version}/neoforge-{neoforge_version}-installer.jar", installer)

    java = java_binary(server.version, server.java_runtime)
    min_ram = normalize_ram(server.min_ram, "1G")
    max_ram = normalize_ram(server.max_ram, "2G")
    result = run_in([java, "-jar", str(installer), "--installServer"], cwd=server_path, timeout=600)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "NeoForge installer failed"
        raise HTTPException(status_code=502, detail=detail)

    unix_args = server_path / "libraries" / "net" / "neoforged" / "neoforge" / neoforge_version / "unix_args.txt"
    if unix_args.exists():
        return [
            java,
            f"-Xms{min_ram}",
            f"-Xmx{max_ram}",
            *server.jvm_args,
            f"@libraries/net/neoforged/neoforge/{neoforge_version}/unix_args.txt",
            "nogui",
        ]

    neoforge_jar = next(server_path.glob(f"neoforge-{neoforge_version}*.jar"), None)
    if neoforge_jar:
        return [java, f"-Xms{min_ram}", f"-Xmx{max_ram}", *server.jvm_args, "-jar", neoforge_jar.name, "nogui"]

    raise HTTPException(status_code=502, detail="NeoForge installer did not produce a runnable server")


class ServerLoader:
    loader_type = "vanilla"

    def versions(self) -> list[str]:
        return []

    def install(self, server: StoredServer) -> StoredServer:
        return server

    def update(self, server: StoredServer) -> StoredServer:
        return self.install(server)

    def required_java(self, server: StoredServer) -> int:
        return required_java_major(server.version)

    def command(self, server: StoredServer) -> list[str]:
        return server.start_command

    def installed_version(self, server: StoredServer) -> str:
        return server.version


class JarServerLoader(ServerLoader):
    def __init__(self, loader_type: str, downloader: Any):
        self.loader_type = loader_type
        self.downloader = downloader

    def install(self, server: StoredServer) -> StoredServer:
        java = java_binary(server.version, server.java_runtime)
        destination = server_base_path(server) / "server.jar"
        if not destination.exists():
            self.downloader(server.version, destination)
        server.start_command = start_command_for_server(server, java)
        return server


class FabricLoader(JarServerLoader):
    def __init__(self):
        super().__init__("fabric", download_fabric_server_jar)

    def command(self, server: StoredServer) -> list[str]:
        return default_start_command()

    def install(self, server: StoredServer) -> StoredServer:
        destination = server_base_path(server) / "server.jar"
        if not destination.exists():
            download_fabric_server_jar(server.version, destination, server.loader_version, server.installer_version)
        if server.install_fabric_api:
            install_fabric_api(server)
        server.start_command = default_start_command()
        return server


class ForgeLoader(ServerLoader):
    loader_type = "forge"

    def versions(self) -> list[str]:
        return forge_versions()

    def install(self, server: StoredServer) -> StoredServer:
        if not server.start_command:
            server.start_command = install_forge_server(server)
        return server


class NeoForgeLoader(ServerLoader):
    loader_type = "neoforge"

    def versions(self) -> list[str]:
        return neoforge_versions()

    def install(self, server: StoredServer) -> StoredServer:
        if not server.start_command:
            server.start_command = install_neoforge_server(server)
        return server


SERVER_LOADERS: dict[str, ServerLoader] = {
    "vanilla": JarServerLoader("vanilla", download_vanilla_server_jar),
    "paper": JarServerLoader("paper", download_paper_server_jar),
    "purpur": JarServerLoader("purpur", download_purpur_server_jar),
    "fabric": FabricLoader(),
    "forge": ForgeLoader(),
    "neoforge": NeoForgeLoader(),
}


def provision_server_files(server: StoredServer) -> StoredServer:
    loader = SERVER_LOADERS.get(server.type)
    if loader:
        return loader.install(server)
    raise HTTPException(status_code=400, detail=f"Server type {server.type} cannot be provisioned")


def update_server_files(server: StoredServer) -> StoredServer:
    if not server.managed:
        raise HTTPException(status_code=409, detail="Legacy servers cannot be updated by Ksylian")
    server_path = server_base_path(server)
    if server.type in {"vanilla", "paper", "purpur", "fabric"}:
        (server_path / "server.jar").unlink(missing_ok=True)
    if server.type == "forge":
        server.start_command = []
    if server.type == "neoforge":
        server.start_command = []
    return ensure_server_provisioned(server)


def write_systemd_unit(server: StoredServer) -> None:
    unit_path = SYSTEMD_DIR / server.service
    start_command = server.start_command or start_command_for_server(server, java_binary(server.version, server.java_runtime))
    server_path = server_base_path(server)
    max_ram = normalize_ram(server.max_ram, "2G")
    cpu_quota = f"{normalize_cpu_limit(server.cpu_limit)}%"
    content = "\n".join(
        [
            "[Unit]",
            f"Description=Ksylian Minecraft Server {server.name}",
            "After=network.target",
            "",
            "[Service]",
            "Type=simple",
            f"User={MINECRAFT_USER}",
            f"Group={MINECRAFT_USER}",
            f"WorkingDirectory={server_path}",
            f"ExecStart={shlex.join(start_command)}",
            "Restart=on-failure",
            "RestartSec=10",
            "SuccessExitStatus=0 143",
            f"MemoryMax={max_ram}",
            f"CPUQuota={cpu_quota}",
            "NoNewPrivileges=true",
            "PrivateTmp=true",
            "ProtectSystem=full",
            "ProtectHome=true",
            f"ReadWritePaths={server_path}",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "",
        ]
    )
    unit_path.write_text(content)

    daemon_reload = run(["systemctl", "daemon-reload"], timeout=30)
    if daemon_reload.returncode != 0:
        raise HTTPException(status_code=500, detail=daemon_reload.stderr.strip() or "systemctl daemon-reload failed")

    enable = run(["systemctl", "enable", server.service], timeout=30)
    if enable.returncode != 0:
        raise HTTPException(status_code=500, detail=enable.stderr.strip() or "systemctl enable failed")


def ensure_server_provisioned(server: StoredServer) -> StoredServer:
    if not server.managed:
        return server

    write_server_scaffold(server)
    server = provision_server_files(server)
    apply_server_permissions(server)

    write_systemd_unit(server)
    return server


def service_state(
    service: str,
) -> Literal["installing", "stopped", "starting", "running", "stopping", "crashed", "updating", "backing_up"]:
    result = run(["systemctl", "is-active", service])
    if result.stdout.strip() == "active":
        return "running"
    if result.stdout.strip() in {"activating", "reloading"}:
        return "starting"
    if result.stdout.strip() == "deactivating":
        return "stopping"
    if result.stdout.strip() == "failed":
        return "crashed"
    return "stopped"


def read_exact(sock: socket.socket, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        chunk = sock.recv(size - len(chunks))
        if not chunk:
            raise OSError("Socket closed while reading packet")
        chunks.extend(chunk)
    return bytes(chunks)


def minecraft_player_status(port: int, host: str = "127.0.0.1") -> str:
    try:
        with socket.create_connection((host, port), timeout=1.5) as sock:
            sock.settimeout(1.5)
            handshake = b"".join(
                [
                    encode_varint(765),
                    minecraft_utf(host),
                    port.to_bytes(2, "big"),
                    encode_varint(1),
                ]
            )
            sock.sendall(minecraft_packet(0, handshake))
            sock.sendall(minecraft_packet(0))

            packet_length = read_socket_varint(sock)
            packet = read_exact(sock, packet_length)
            packet_id_offset = 0
            packet_id, packet_id_offset = read_response_varint(packet, packet_id_offset)
            if packet_id != 0:
                return "-"
            response_length, offset = read_response_varint(packet, packet_id_offset)
            response = read_exact_from_buffer(packet, offset, response_length).decode("utf-8")
            data = json.loads(response)
            players = data.get("players") if isinstance(data, dict) else None
            if not isinstance(players, dict):
                return "-"
            online = int(players.get("online", 0))
            maximum = int(players.get("max", 0))
            return f"{online} / {maximum}" if maximum else str(online)
    except (OSError, TimeoutError, ValueError, json.JSONDecodeError):
        return "-"


def execute_rcon(server: StoredServer, command: str) -> str:
    if not server.rcon_port or not server.rcon_password:
        raise HTTPException(status_code=409, detail="RCON is not configured for this server")
    if len(command.encode("utf-8")) > 4096:
        raise HTTPException(status_code=413, detail="RCON command is too large")

    try:
        with socket.create_connection(("127.0.0.1", server.rcon_port), timeout=4) as sock:
            sock.settimeout(4)
            sock.sendall(rcon_packet(1, 3, server.rcon_password))
            request_id, _, _ = read_rcon_packet(sock)
            if request_id == -1:
                raise HTTPException(status_code=401, detail="RCON authentication failed")
            sock.sendall(rcon_packet(2, 2, command))
            _, _, output = read_rcon_packet(sock)
            return output
    except HTTPException:
        raise
    except OSError as error:
        raise HTTPException(status_code=502, detail=f"RCON is unavailable: {error}") from error


def rcon_available(server: StoredServer) -> bool:
    try:
        execute_rcon(server, "list")
        return True
    except HTTPException:
        return False


def configured_max_players(server_path: Path) -> int:
    properties_path = server_path / "server.properties"
    if not properties_path.exists():
        return 20
    try:
        for line in properties_path.read_text().splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "max-players":
                return max(int(value.strip()), 0)
    except (OSError, ValueError):
        return 20
    return 20


def server_players_label(config: StoredServer, state: str) -> str:
    server_path = server_base_path(config) if config.managed else Path(config.path)
    maximum = configured_max_players(server_path)
    if state != "running":
        return f"0 / {maximum}"

    status = minecraft_player_status(config.port)
    if status == "-":
        return f"0 / {maximum}"
    return status


def read_response_varint(buffer: bytes, offset: int = 0) -> tuple[int, int]:
    value = 0
    for position in range(5):
        if offset + position >= len(buffer):
            raise ValueError("Incomplete varint")
        byte = buffer[offset + position]
        value |= (byte & 0x7F) << (7 * position)
        if not byte & 0x80:
            return value, offset + position + 1
    raise ValueError("Varint is too large")


def read_exact_from_buffer(buffer: bytes, offset: int, size: int) -> bytes:
    end = offset + size
    if end > len(buffer):
        raise ValueError("Incomplete packet")
    return buffer[offset:end]


from .monitoring import (
    cpu_percent,
    disk_usage,
    folder_size,
    format_bytes,
    format_duration,
    host_ips,
    memory_usage,
    service_exit_code,
    service_usage,
    temperature_label,
    top_processes,
)
def last_server_event(server_id: str) -> str:
    if not ACTION_LOG.exists():
        return ""
    try:
        lines = ACTION_LOG.read_text().splitlines()
    except OSError:
        return ""
    for line in reversed(lines):
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if item.get("server_id") == server_id:
            action = str(item.get("action") or "")
            at = str(item.get("at") or "")
            return f"{at} · {action}" if at and action else action
    return ""


def crash_report_summary(path: Path) -> str:
    try:
        for line in path.read_text(errors="replace").splitlines()[:80]:
            stripped = line.strip()
            if stripped.startswith("Description:"):
                return stripped
            if "Exception" in stripped or "Error" in stripped:
                return stripped[:180]
    except OSError:
        return ""
    return ""


def recent_server_changes(server_id: str, limit: int = 5) -> list[str]:
    if not ACTION_LOG.exists():
        return []
    try:
        lines = ACTION_LOG.read_text().splitlines()
    except OSError:
        return []
    changes: list[str] = []
    for line in reversed(lines):
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if item.get("server_id") == server_id:
            at = str(item.get("at") or "")
            action = str(item.get("action") or "")
            detail = str(item.get("detail") or "")
            changes.append(" · ".join(part for part in (at, action, detail) if part))
        if len(changes) >= limit:
            break
    return changes


def analyze_crash_report(path: Path, server_id: str) -> dict[str, Any]:
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        lines = []
    joined = "\n".join(lines)
    stack_trace = [line for line in lines if line.lstrip().startswith("at ") or "Caused by:" in line][:30]
    probable = next((line.strip() for line in lines if line.strip().startswith("Description:")), "")
    if not probable:
        probable = next((line.strip() for line in lines if "Caused by:" in line), "")

    missing_dependency = ""
    missing_match = re.search(r"(requires [^\n]+|Missing [^\n]+|depends on [^\n]+)", joined, re.IGNORECASE)
    if missing_match:
        missing_dependency = missing_match.group(1).strip()[:180]

    client_only_mod = ""
    if re.search(r"client[- ]only|net\.minecraft\.client|DistExecutor|FMLEnvironment\.dist", joined, re.IGNORECASE):
        client_only_mod = "В отчёте есть признаки client-only кода на сервере"

    conflicting_mod = ""
    mod_match = re.search(r"(Suspected Mod[s]?:[^\n]+|Mod File:[^\n]+|Mod [A-Za-z0-9_.-]+)", joined, re.IGNORECASE)
    if mod_match:
        conflicting_mod = mod_match.group(1).strip()[:180]

    return {
        "probable_cause": probable[:220],
        "conflicting_mod": conflicting_mod,
        "missing_dependency": missing_dependency,
        "client_only_mod": client_only_mod,
        "stack_trace": stack_trace,
        "recent_changes": recent_server_changes(server_id),
    }


def public_server_address(config: StoredServer) -> str:
    if config.managed and PUBLIC_DOMAIN:
        return f"{config.id}.{PUBLIC_DOMAIN}"
    return config.address


def cleanup_managed_server(server: StoredServer) -> None:
    if not server.managed:
        return
    run(["systemctl", "stop", server.service], timeout=60)
    run(["systemctl", "disable", server.service], timeout=60)
    unit_path = SYSTEMD_DIR / server.service
    unit_path.unlink(missing_ok=True)
    run(["systemctl", "daemon-reload"], timeout=30)
    try:
        shutil.rmtree(server_base_path(server), ignore_errors=True)
    except HTTPException:
        pass


def server_is_installing(server: StoredServer) -> bool:
    return server.managed and not (SYSTEMD_DIR / server.service).exists()


def provision_server_in_background(server_id: str) -> None:
    try:
        store = load_server_store()
        server = store.get(server_id)
        if server is None:
            return
        server = ensure_server_provisioned(server)
        store = load_server_store()
        store[server.id] = server
        save_server_store(store)
        append_action_log("server_install_complete", server.id, f"{server.type} {server.version}")
    except Exception as error:
        store = load_server_store()
        server = store.get(server_id)
        if server is not None:
            cleanup_managed_server(server)
            store.pop(server_id, None)
            save_server_store(store)
        append_action_log("server_install_failed", server_id, str(error))


def to_agent_server(server_id: str) -> AgentServer:
    config = load_server_store()[server_id]
    cpu, ram = service_usage(config.service)
    state = server_runtime_states.get(server_id) or service_state(config.service)
    if server_is_installing(config):
        state = "installing"

    return AgentServer(
        id=server_id,
        name=config.name,
        pack=config.pack,
        version=config.version,
        state=state,
        players=server_players_label(config, state),
        ram=ram,
        cpu=cpu,
        disk=folder_size(Path(config.path)),
        address=public_server_address(config),
        exit_code=service_exit_code(config.service),
        last_event=last_server_event(server_id),
        warnings=server_warnings(config),
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "ksylian-agent",
        "public_domain": PUBLIC_DOMAIN,
        "proxy_domain": PROXY_DOMAIN,
        "proxy_port": PROXY_PORT,
    }


@app.post("/agent/actions/restart")
def restart_agent(x_ksylian_token: str | None = Header(default=None)) -> dict[str, bool]:
    require_token(x_ksylian_token)
    subprocess.Popen(["systemctl", "restart", "ksylian-agent.service"])
    return {"ok": True}


@app.get("/app/update/log", response_model=list[str])
def app_update_log(x_ksylian_token: str | None = Header(default=None)) -> list[str]:
    require_token(x_ksylian_token)
    if not UPDATE_LOG.exists():
        return []
    return UPDATE_LOG.read_text().splitlines()[-120:]


@app.get("/agent/actions/log", response_model=list[str])
def agent_action_log(x_ksylian_token: str | None = Header(default=None)) -> list[str]:
    require_token(x_ksylian_token)
    if not ACTION_LOG.exists():
        return []
    return ACTION_LOG.read_text().splitlines()[-200:]


@app.post("/app/update", response_model=AppUpdateResult)
def update_app(payload: AppUpdateRequest, x_ksylian_token: str | None = Header(default=None)) -> AppUpdateResult:
    require_token(x_ksylian_token)
    target_version = validate_update_target(payload.target_version)
    ensure_updater_configured()
    script_path = update_script_path()
    append_update_log(f"Queued update to {target_version}")
    append_action_log("app_update", detail=target_version)
    subprocess.Popen(
        ["bash", str(script_path), target_version],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return AppUpdateResult(
        ok=True,
        message="Обновление запущено. Панель перезапустится после сборки контейнеров.",
        target_version=target_version,
    )


@app.get("/servers", response_model=list[AgentServer])
def servers(x_ksylian_token: str | None = Header(default=None)) -> list[AgentServer]:
    require_token(x_ksylian_token)
    return [to_agent_server(server_id) for server_id in active_server_ids()]


@app.post("/servers", response_model=AgentServer)
def create_server(payload: CreateAgentServerRequest, x_ksylian_token: str | None = Header(default=None)) -> AgentServer:
    require_token(x_ksylian_token)
    store = load_server_store()
    server_id_base = slugify(payload.name)
    server_id = server_id_base
    counter = 2
    while server_id in store:
        server_id = f"{server_id_base}-{counter}"
        counter += 1

    port = allocate_port(store)
    service = f"ksylian-{server_id}.service"
    server_path = managed_server_path(server_id)
    server = StoredServer(
        id=server_id,
        name=payload.name.strip(),
        type=payload.type,
        pack=server_type_label(payload.type),
        version=payload.version,
        port=port,
        service=service,
        path=str(server_path),
        backup_path=str(server_path / "world"),
        address=f"{host_primary_ip()}:{port}",
        created_at=datetime.now().isoformat(timespec="seconds"),
        managed=True,
        min_ram=normalize_ram(payload.min_ram, "1G"),
        max_ram=normalize_ram(payload.max_ram, "2G"),
        java_runtime=payload.java_runtime if payload.java_runtime in {"auto", "8", "17", "21"} else "auto",
        jvm_args=normalize_jvm_args(payload.jvm_args),
        cpu_limit=normalize_cpu_limit(payload.cpu_limit),
        loader_version=payload.loader_version.strip(),
        installer_version=payload.installer_version.strip(),
        install_fabric_api=payload.install_fabric_api if payload.type == "fabric" else False,
    )
    ensure_disk_space_for_server(server)
    store[server.id] = server
    save_server_store(store)
    append_action_log("server_create_queued", server.id, f"{server.type} {server.version}")
    threading.Thread(target=provision_server_in_background, args=(server.id,), daemon=True).start()
    return to_agent_server(server.id)


@app.get("/loaders/{loader_type}/versions", response_model=list[str])
def loader_versions(
    loader_type: Literal["forge", "neoforge", "fabric", "vanilla", "paper", "purpur"],
    x_ksylian_token: str | None = Header(default=None),
) -> list[str]:
    require_token(x_ksylian_token)
    loader = SERVER_LOADERS.get(loader_type)
    if loader is None:
        raise HTTPException(status_code=404, detail="Loader not found")
    if loader_type == "fabric":
        return fabric_loader_versions()
    return loader.versions()


@app.get("/loaders/fabric/installers", response_model=list[str])
def fabric_installers(x_ksylian_token: str | None = Header(default=None)) -> list[str]:
    require_token(x_ksylian_token)
    return fabric_installer_versions()


@app.get("/monitoring", response_model=HostMonitoring)
def monitoring(x_ksylian_token: str | None = Header(default=None)) -> HostMonitoring:
    require_token(x_ksylian_token)
    memory, swap = memory_usage()
    load_average = [round(value, 2) for value in os.getloadavg()]

    try:
        uptime_seconds = float(Path("/proc/uptime").read_text().split()[0])
    except (OSError, ValueError, IndexError):
        uptime_seconds = 0

    services = []
    for server_id in active_server_ids():
        config = load_server_store()[server_id]
        cpu, ram = service_usage(config.service)
        services.append(
            ServiceUsage(
                id=server_id,
                name=config.name,
                state=service_state(config.service),
                cpu=cpu,
                ram=ram,
            )
        )

    agent_cpu, agent_ram = service_usage("ksylian-agent.service")
    services.append(
        ServiceUsage(
            id="ksylian-agent",
            name="Ksylian Agent",
            state=service_state("ksylian-agent.service"),
            cpu=agent_cpu,
            ram=agent_ram,
        )
    )

    return HostMonitoring(
        hostname=socket.gethostname(),
        ip_addresses=host_ips(),
        uptime=format_duration(uptime_seconds),
        load_average=load_average,
        cpu_percent=cpu_percent(),
        cpu_cores=os.cpu_count() or 1,
        memory=memory,
        swap=swap,
        disks=disk_usage(),
        top_processes=top_processes(),
        services=services,
        temperature=temperature_label(),
        collected_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


@app.get("/servers/{server_id}/logs", response_model=list[str])
def logs(server_id: str, x_ksylian_token: str | None = Header(default=None)) -> list[str]:
    require_token(x_ksylian_token)
    config = load_server_store().get(server_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Server not found")

    result = run(["journalctl", "-u", config.service, "-n", "80", "--no-pager", "-o", "short-iso"], timeout=30)
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=result.stderr.strip() or "Failed to read logs")
    return [line for line in result.stdout.splitlines() if line]


@app.get("/servers/{server_id}/logs/full", response_model=list[str])
def full_logs(server_id: str, x_ksylian_token: str | None = Header(default=None)) -> list[str]:
    require_token(x_ksylian_token)
    config = load_server_store().get(server_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Server not found")

    result = run(["journalctl", "-u", config.service, "-n", "5000", "--no-pager", "-o", "short-iso"], timeout=60)
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=result.stderr.strip() or "Failed to read full logs")
    return [line for line in result.stdout.splitlines() if line]


@app.get("/servers/{server_id}/crash-reports", response_model=list[CrashReportItem])
def crash_reports(server_id: str, x_ksylian_token: str | None = Header(default=None)) -> list[CrashReportItem]:
    require_token(x_ksylian_token)
    config = load_server_store().get(server_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Server not found")

    reports_dir = server_base_path(config) / "crash-reports" if config.managed else Path(config.path) / "crash-reports"
    if not reports_dir.exists():
        return []

    reports = []
    for path in sorted(reports_dir.glob("*.txt"), key=lambda item: item.stat().st_mtime, reverse=True)[:20]:
        analysis = analyze_crash_report(path, server_id)
        reports.append(
            CrashReportItem(
                name=path.name,
                size=folder_size(path),
                created=datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
                summary=crash_report_summary(path),
                **analysis,
            )
        )
    return reports


@app.get("/servers/{server_id}/config", response_model=ServerConfigPayload)
def server_config(server_id: str, x_ksylian_token: str | None = Header(default=None)) -> ServerConfigPayload:
    require_token(x_ksylian_token)
    config = load_server_store().get(server_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Server not found")

    properties_path = server_base_path(config) / "server.properties"
    if not properties_path.exists():
        ensure_server_provisioned(config)
    if not properties_path.exists():
        raise HTTPException(status_code=404, detail="server.properties was not found")

    try:
        content = properties_path.read_text()
    except OSError as error:
        raise HTTPException(status_code=500, detail="Failed to read server.properties") from error

    return ServerConfigPayload(content=content)


@app.get("/servers/{server_id}/rcon/status")
def rcon_status(server_id: str, x_ksylian_token: str | None = Header(default=None)) -> dict[str, bool]:
    require_token(x_ksylian_token)
    config = load_server_store().get(server_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Server not found")
    return {"available": rcon_available(config)}


@app.post("/servers/{server_id}/rcon/command", response_model=RconCommandResult)
def rcon_command(
    server_id: str,
    payload: RconCommandPayload,
    x_ksylian_token: str | None = Header(default=None),
) -> RconCommandResult:
    require_token(x_ksylian_token)
    config = load_server_store().get(server_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Server not found")
    command = payload.command.strip()
    if not command:
        raise HTTPException(status_code=400, detail="RCON command is required")
    output = execute_rcon(config, command)
    append_action_log("server_rcon_command", server_id, command)
    return RconCommandResult(ok=True, output=output)


@app.put("/servers/{server_id}/config", response_model=ServerConfigPayload)
def update_server_config(
    server_id: str,
    payload: ServerConfigPayload,
    x_ksylian_token: str | None = Header(default=None),
) -> ServerConfigPayload:
    require_token(x_ksylian_token)
    config = load_server_store().get(server_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Server not found")
    if len(payload.content.encode("utf-8")) > 256 * 1024:
        raise HTTPException(status_code=413, detail="server.properties is too large")

    server_path = server_base_path(config)
    server_path.mkdir(parents=True, exist_ok=True)
    properties_path = server_path / "server.properties"
    content = payload.content.replace("\r\n", "\n").replace("\r", "\n")
    if not content.endswith("\n"):
        content += "\n"

    try:
        properties_path.write_text(content)
    except OSError as error:
        raise HTTPException(status_code=500, detail="Failed to write server.properties") from error

    if config.managed:
        apply_server_permissions(config)
    append_action_log("server_config_update", server_id, "server.properties")
    return ServerConfigPayload(content=content)


@app.get("/servers/{server_id}/files", response_model=FileListPayload)
def server_files(
    server_id: str,
    path: str = "",
    x_ksylian_token: str | None = Header(default=None),
) -> FileListPayload:
    require_token(x_ksylian_token)
    return list_server_files(load_server_or_404(server_id), path)


@app.get("/servers/{server_id}/files/content", response_model=FileContentPayload)
def server_file_content(
    server_id: str,
    path: str,
    x_ksylian_token: str | None = Header(default=None),
) -> FileContentPayload:
    require_token(x_ksylian_token)
    return read_server_file(load_server_or_404(server_id), path)


@app.get("/servers/{server_id}/files/search", response_model=list[FileSearchResult])
def server_file_search(
    server_id: str,
    query: str,
    path: str = "",
    x_ksylian_token: str | None = Header(default=None),
) -> list[FileSearchResult]:
    require_token(x_ksylian_token)
    return search_server_files(load_server_or_404(server_id), query, path)


@app.put("/servers/{server_id}/files", response_model=FileEntry)
def server_file_write(
    server_id: str,
    payload: FileWriteRequest,
    x_ksylian_token: str | None = Header(default=None),
) -> FileEntry:
    require_token(x_ksylian_token)
    return write_server_file(load_server_or_404(server_id), payload)


@app.post("/servers/{server_id}/files/actions")
def server_file_action(
    server_id: str,
    payload: FileOperationRequest,
    x_ksylian_token: str | None = Header(default=None),
) -> FileEntry | dict[str, bool]:
    require_token(x_ksylian_token)
    return operate_server_file(load_server_or_404(server_id), payload)


@app.get("/servers/{server_id}/mods", response_model=list[InstalledModItem])
def server_mods(server_id: str, x_ksylian_token: str | None = Header(default=None)) -> list[InstalledModItem]:
    require_token(x_ksylian_token)
    return scan_installed_mods(load_server_or_404(server_id))


@app.post("/servers/{server_id}/mods", response_model=InstalledModItem)
def server_mod_install(
    server_id: str,
    payload: ModInstallRequest,
    x_ksylian_token: str | None = Header(default=None),
) -> InstalledModItem:
    require_token(x_ksylian_token)
    return install_mod(load_server_or_404(server_id), payload)


@app.post("/servers/{server_id}/mods/bulk", response_model=list[InstalledModItem])
def server_mod_bulk_install(
    server_id: str,
    payload: ModBulkInstallRequest,
    x_ksylian_token: str | None = Header(default=None),
) -> list[InstalledModItem]:
    require_token(x_ksylian_token)
    return bulk_install_mods(load_server_or_404(server_id), payload)


@app.post("/servers/{server_id}/mods/actions")
def server_mod_action(
    server_id: str,
    payload: ModOperationRequest,
    x_ksylian_token: str | None = Header(default=None),
) -> dict[str, bool]:
    require_token(x_ksylian_token)
    return operate_mod(load_server_or_404(server_id), payload)


@app.post("/servers/{server_id}/mods/bulk-actions")
def server_mod_bulk_action(
    server_id: str,
    payload: ModBulkActionRequest,
    x_ksylian_token: str | None = Header(default=None),
) -> dict[str, int]:
    require_token(x_ksylian_token)
    return bulk_operate_mods(load_server_or_404(server_id), payload)


@app.post("/servers/{server_id}/backups", response_model=BackupItem)
def server_backup(
    server_id: str,
    payload: BackupRequest,
    x_ksylian_token: str | None = Header(default=None),
) -> BackupItem:
    require_token(x_ksylian_token)
    return create_backup_archive(load_server_or_404(server_id), payload)


@app.post("/servers/{server_id}/restore", response_model=AgentActionResult)
def server_restore(
    server_id: str,
    payload: RestoreRequest,
    x_ksylian_token: str | None = Header(default=None),
) -> AgentActionResult:
    require_token(x_ksylian_token)
    return restore_backup(load_server_or_404(server_id), payload)


@app.post("/servers/{server_id}/actions/{action}", response_model=AgentActionResult)
def action(
    server_id: str,
    action: Literal["start", "restart", "stop", "kill", "update", "rollback", "backup"],
    x_ksylian_token: str | None = Header(default=None),
) -> AgentActionResult:
    require_token(x_ksylian_token)
    config = load_server_or_404(server_id)

    if action in {"start", "restart", "update", "rollback"}:
        if server_is_installing(config):
            raise HTTPException(status_code=409, detail="Server is still installing")
        if action != "update":
            ensure_server_provisioned(config)

    if action == "update":
        server_runtime_states[server_id] = "updating"
        was_running = service_state(config.service) == "running"
        try:
            create_backup_archive(
                config,
                BackupRequest(mode="stopped" if was_running else "live", parts=["world", "mods", "config", "root"], description="Before server file update"),
                reason="pre-update",
            )
            if was_running:
                stop_result = run(["systemctl", "stop", config.service], timeout=60)
                if stop_result.returncode != 0:
                    raise HTTPException(status_code=500, detail=stop_result.stderr.strip() or "systemctl stop failed")
            updated = update_server_files(config)
            store = load_server_store()
            store[server_id] = updated
            save_server_store(store)
            if was_running:
                start_result = run(["systemctl", "start", updated.service], timeout=60)
                if start_result.returncode != 0:
                    raise HTTPException(status_code=500, detail=start_result.stderr.strip() or "systemctl start failed")
            message = f"{config.name}: update completed"
            append_action_log("server_update", server_id, message)
        finally:
            server_runtime_states.pop(server_id, None)
    elif action == "rollback":
        result = rollback_last_update(config)
        message = result.message
    elif action in {"start", "restart", "stop", "kill"}:
        command = ["systemctl", "kill", config.service] if action == "kill" else ["systemctl", action, config.service]
        result = run(command, timeout=60)
        if result.returncode != 0:
            append_action_log(f"server_{action}_failed", server_id, result.stderr.strip())
            raise HTTPException(status_code=500, detail=result.stderr.strip() or f"{' '.join(command)} failed")
        if action == "kill":
            run(["systemctl", "stop", config.service], timeout=60)
        message = f"{config.name}: {action} completed"
        append_action_log(f"server_{action}", server_id, message)
    else:
        backup = create_backup_archive(config, BackupRequest(mode="live", parts=["world", "mods", "config", "root"]))
        message = f"{config.name}: backup created at {backup.name}"

    return AgentActionResult(ok=True, message=message, server=to_agent_server(server_id))


@app.delete("/servers/{server_id}")
def delete_server(server_id: str, x_ksylian_token: str | None = Header(default=None)) -> dict[str, bool]:
    require_token(x_ksylian_token)
    store = load_server_store()
    config = store.get(server_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Server not found")

    stop_result = run(["systemctl", "stop", config.service], timeout=60)
    if stop_result.returncode != 0 and not (config.managed and systemctl_issue_can_be_ignored(stop_result)):
        raise HTTPException(status_code=500, detail=stop_result.stderr.strip() or "Failed to stop service")

    disable_result = run(["systemctl", "disable", config.service], timeout=60)
    if disable_result.returncode != 0 and not (config.managed and systemctl_issue_can_be_ignored(disable_result)):
        raise HTTPException(status_code=500, detail=disable_result.stderr.strip() or "Failed to disable service")

    disabled = disabled_server_ids()
    if config.managed:
        unit_path = SYSTEMD_DIR / config.service
        unit_path.unlink(missing_ok=True)
        run(["systemctl", "daemon-reload"], timeout=30)
        shutil.rmtree(server_base_path(config), ignore_errors=True)
        store.pop(server_id, None)
        disabled.discard(server_id)
        save_server_store(store)
    else:
        disabled.add(server_id)
    save_disabled_server_ids(disabled)
    append_action_log("server_delete", server_id, config.name)
    return {"ok": True}


@app.get("/backups")
def backups(x_ksylian_token: str | None = Header(default=None)) -> list[BackupItem]:
    require_token(x_ksylian_token)
    if not BACKUP_DIR.exists():
        return []

    items: list[BackupItem] = []
    for path in sorted(BACKUP_DIR.glob("*.tar.gz"), key=lambda item: item.stat().st_mtime, reverse=True):
        items.append(backup_to_item(path))
    return items
