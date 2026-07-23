from __future__ import annotations

import base64
import json
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any, Literal

from fastapi import HTTPException

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    tomllib = None  # type: ignore[assignment]

from .activity import append_action_log
from .files import operate_server_file
from .hashing import file_digest
from .monitoring import format_bytes
from .processes import apply_server_permissions
from .schemas import (
    FileOperationRequest,
    InstalledModItem,
    ModBulkActionRequest,
    ModBulkInstallRequest,
    ModDependency,
    ModInstallRequest,
    ModOperationRequest,
    StoredServer,
)
from .security import ensure_child_path, relative_server_path, server_child_path


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
