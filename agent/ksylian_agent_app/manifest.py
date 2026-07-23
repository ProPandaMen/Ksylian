from __future__ import annotations

import shutil
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException

from .activity import append_action_log
from .config import DATA_DIR
from .hashing import file_digest
from .mod_sources import read_mod_sources
from .mods import scan_installed_mods
from .schemas import (
    BuildImportRequest,
    BuildManifest,
    BuildManifestDiff,
    BuildManifestMod,
    InstalledModItem,
    StoredServer,
)
from .security import server_base_path, server_child_path


MANIFEST_FILENAME = "ksylian-manifest.json"


def manifest_path(server: StoredServer) -> Path:
    return server_child_path(server, MANIFEST_FILENAME)


def manifest_history_dir(server: StoredServer) -> Path:
    return DATA_DIR / "manifest-history" / server.id


def manifest_mod_from_installed(item: InstalledModItem, sources: dict[str, dict[str, str]]) -> BuildManifestMod:
    source = sources.get(item.filename, {})
    source_name = str(source.get("source") or "manual")
    if source_name not in {"curseforge", "manual", "imported", "unknown"}:
        source_name = "unknown"
    return BuildManifestMod(
        id=item.id,
        name=item.name,
        version=item.version,
        loader=item.loader,
        side=item.side,
        filename=item.filename,
        path=item.path,
        sha256=item.sha256,
        source=source_name,  # type: ignore[arg-type]
        project_id=str(source.get("project_id") or ""),
        file_id=str(source.get("file_id") or ""),
        installed_at=str(source.get("installed_at") or ""),
        dependencies=item.dependencies,
    )


def build_manifest(server: StoredServer) -> BuildManifest:
    sources = read_mod_sources(server)
    mods = [manifest_mod_from_installed(item, sources) for item in scan_installed_mods(server)]
    previous = read_manifest(server)
    manifest = BuildManifest(
        server_id=server.id,
        server_name=server.name,
        minecraft_version=server.version,
        loader=server.type,
        loader_version=server.loader_version,
        java_runtime=server.java_runtime,
        generated_at=datetime.now().isoformat(timespec="seconds"),
        mods=mods,
        manual_changes=detect_manual_changes(previous, mods),
    )
    return manifest


def read_manifest(server: StoredServer) -> BuildManifest | None:
    path = manifest_path(server)
    if not path.exists():
        return None
    try:
        return BuildManifest.model_validate_json(path.read_text())
    except (OSError, ValueError):
        return None


def save_manifest(server: StoredServer, manifest: BuildManifest | None = None) -> BuildManifest:
    payload = manifest or build_manifest(server)
    path = manifest_path(server)
    path.write_text(payload.model_dump_json(indent=2, by_alias=True))
    path.chmod(0o600)

    history = manifest_history_dir(server)
    history.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (history / f"{stamp}.json").write_text(payload.model_dump_json(indent=2, by_alias=True))
    append_action_log("server_manifest_update", server.id, f"{len(payload.mods)} mods")
    return payload


def detect_manual_changes(previous: BuildManifest | None, current: list[BuildManifestMod]) -> list[str]:
    if previous is None:
        return []
    previous_by_path = {item.path: item for item in previous.mods}
    changes: list[str] = []
    for item in current:
        previous_item = previous_by_path.get(item.path)
        if previous_item is None:
            changes.append(f"added:{item.path}")
        elif previous_item.sha256 != item.sha256:
            changes.append(f"changed:{item.path}")
    current_paths = {item.path for item in current}
    for item in previous.mods:
        if item.path not in current_paths:
            changes.append(f"removed:{item.path}")
    return changes


def diff_manifests(left: BuildManifest, right: BuildManifest) -> BuildManifestDiff:
    left_by_path = {item.path: item for item in left.mods}
    right_by_path = {item.path: item for item in right.mods}
    added = [item for path, item in right_by_path.items() if path not in left_by_path]
    removed = [item for path, item in left_by_path.items() if path not in right_by_path]
    changed = [
        {"before": left_by_path[path], "after": right_by_path[path]}
        for path in sorted(set(left_by_path) & set(right_by_path))
        if left_by_path[path].sha256 != right_by_path[path].sha256
    ]
    return BuildManifestDiff(added=added, removed=removed, changed=changed)


def export_build(server: StoredServer) -> Path:
    manifest = save_manifest(server)
    export_dir = DATA_DIR / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    archive = export_dir / f"{server.id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.tar.gz"
    root = server_base_path(server)
    with tarfile.open(archive, "w:gz") as tar:
        manifest_file = manifest_path(server)
        tar.add(manifest_file, arcname=MANIFEST_FILENAME)
        for folder in ("mods", "config"):
            path = root / folder
            if path.exists():
                tar.add(path, arcname=folder)
        for filename in ("server.properties", "eula.txt"):
            path = root / filename
            if path.exists():
                tar.add(path, arcname=filename)
    sidecar = archive.with_suffix(archive.suffix + ".sha256")
    sidecar.write_text(file_digest(archive, "sha256"))
    append_action_log("server_manifest_export", server.id, archive.name)
    return archive


def import_build(server: StoredServer, request: BuildImportRequest) -> BuildManifest:
    if request.mode == "replace":
        mods_dir = server_child_path(server, "mods")
        if mods_dir.exists():
            shutil.rmtree(mods_dir)
        mods_dir.mkdir(parents=True, exist_ok=True)
    save_manifest(server, request.manifest)
    append_action_log("server_manifest_import", server.id, request.mode)
    return request.manifest


def clone_server_for_test(server: StoredServer) -> Path:
    root = server_base_path(server)
    tmp_root = DATA_DIR / "tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    test_root = Path(tempfile.mkdtemp(prefix=f"{server.id}-test-", dir=str(tmp_root)))
    for name in ("mods", "config", "libraries", "server.properties", "eula.txt", "run.sh", "start.sh"):
        source = root / name
        if not source.exists():
            continue
        target = test_root / name
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)
    for jar in root.glob("*.jar"):
        shutil.copy2(jar, test_root / jar.name)
    return test_root
