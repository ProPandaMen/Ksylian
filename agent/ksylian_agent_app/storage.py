from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import HTTPException

from .config import DATA_DIR, DISABLED_SERVERS_FILE, SERVER_ROOT, SERVERS, SERVERS_FILE
from .schemas import StoredServer
from .security import is_relative_path


def load_server_or_404(server_id: str) -> StoredServer:
    config = load_server_store().get(server_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Server not found")
    return config


def disabled_server_ids() -> set[str]:
    if not DISABLED_SERVERS_FILE.exists():
        return set()
    try:
        data = json.loads(DISABLED_SERVERS_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return set()
    if not isinstance(data, list):
        return set()
    return {item for item in data if isinstance(item, str)}


def save_disabled_server_ids(server_ids: set[str]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DISABLED_SERVERS_FILE.write_text(json.dumps(sorted(server_ids), indent=2))


def legacy_server_store() -> dict[str, StoredServer]:
    result: dict[str, StoredServer] = {}
    for server_id, config in SERVERS.items():
        port = int(str(config["address"]).rsplit(":", 1)[-1])
        result[server_id] = StoredServer(
            id=server_id,
            name=str(config["name"]),
            type="legacy",
            pack=str(config["pack"]),
            version=str(config["version"]),
            port=port,
            service=str(config["service"]),
            path=str(config["path"]),
            backup_path=str(config["backup_path"]),
            address=str(config["address"]),
            created_at="legacy",
            managed=False,
        )
    return result


def load_server_store() -> dict[str, StoredServer]:
    if not SERVERS_FILE.exists():
        return legacy_server_store()

    try:
        data = json.loads(SERVERS_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return legacy_server_store()

    if not isinstance(data, list):
        return legacy_server_store()

    result: dict[str, StoredServer] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            server = StoredServer(**item)
        except Exception:
            continue
        if server.managed and not is_relative_path(Path(server.path), SERVER_ROOT):
            continue
        result[server.id] = server
    return result


def save_server_store(servers: dict[str, StoredServer]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = [server.model_dump() for server in sorted(servers.values(), key=lambda item: item.created_at)]
    SERVERS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    SERVERS_FILE.chmod(0o600)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", value.lower().strip())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "server"


def active_server_ids() -> list[str]:
    disabled = disabled_server_ids()
    return [server_id for server_id in load_server_store() if server_id not in disabled]


