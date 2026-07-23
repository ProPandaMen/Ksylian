from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .schemas import StoredServer
from .security import server_child_path


def mod_source_sidecar(server: StoredServer):
    return server_child_path(server, "mods/.ksylian-sources.json")


def read_mod_sources(server: StoredServer) -> dict[str, dict[str, str]]:
    path = mod_source_sidecar(server)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): value for key, value in data.items() if isinstance(value, dict)}


def write_mod_source(
    server: StoredServer,
    filename: str,
    *,
    source: str,
    project_id: str = "",
    file_id: str = "",
) -> None:
    path = mod_source_sidecar(server)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = read_mod_sources(server)
    data[Path(filename).name] = {
        "source": source,
        "project_id": str(project_id),
        "file_id": str(file_id),
        "installed_at": datetime.now().isoformat(timespec="seconds"),
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    path.chmod(0o600)
