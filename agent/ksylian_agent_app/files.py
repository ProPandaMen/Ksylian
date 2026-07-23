from __future__ import annotations

import base64
import shutil
import tarfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import HTTPException

from .activity import append_action_log
from .monitoring import folder_size, format_bytes
from .processes import apply_server_permissions
from .schemas import FileContentPayload, FileEntry, FileListPayload, FileOperationRequest, FileSearchResult, FileWriteRequest, StoredServer
from .security import ensure_child_path, relative_server_path, server_base_path, server_child_path


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
