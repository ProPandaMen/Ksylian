from __future__ import annotations

import os
import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


class ServerState(str, Enum):
    online = "online"
    deploying = "deploying"
    offline = "offline"


class ServerAction(str, Enum):
    start = "start"
    restart = "restart"
    stop = "stop"
    backup = "backup"


class GameServer(BaseModel):
    id: str
    name: str
    pack: str
    version: str
    state: ServerState
    players: str
    ram: str
    cpu: int
    disk: str
    address: str


class BackupItem(BaseModel):
    id: str
    name: str
    size: str
    created: str
    server_id: str


class CreateServerRequest(BaseModel):
    name: str
    pack: str
    version: str = "1.20.1"
    address: str = ""


class SettingsPayload(BaseModel):
    has_curseforge_api_key: bool
    curseforge_api_key_mask: str = ""


class UpdateSettingsRequest(BaseModel):
    curseforge_api_key: str = ""


class ModItem(BaseModel):
    id: str
    name: str
    status: str
    tag: Literal["required", "update", "review"]


class CurseForgeProject(BaseModel):
    id: int
    name: str
    slug: str
    summary: str = ""
    type: Literal["mods", "modpacks"]
    downloads: int = 0
    date_modified: str = ""
    icon_url: str = ""
    website_url: str = ""
    latest_file_id: int | None = None
    game_versions: list[str] = []
    loaders: list[str] = []


class CurseForgeSearchPayload(BaseModel):
    items: list[CurseForgeProject]
    total_count: int = 0
    has_api_key: bool


class FileItem(BaseModel):
    name: str
    meta: str
    kind: Literal["folder", "file"]


class ActionResult(BaseModel):
    ok: bool
    message: str
    server: GameServer


class MetricUsage(BaseModel):
    used: int
    total: int
    percent: int
    used_label: str
    total_label: str


class DiskUsage(BaseModel):
    mount: str
    filesystem: str
    used: int
    total: int
    percent: int
    used_label: str
    total_label: str


class ProcessUsage(BaseModel):
    pid: int
    name: str
    cpu: float
    memory: float
    command: str


class ServiceUsage(BaseModel):
    id: str
    name: str
    state: ServerState
    cpu: int
    ram: str


class HostMonitoring(BaseModel):
    hostname: str
    ip_addresses: list[str]
    uptime: str
    load_average: list[float]
    cpu_percent: int
    cpu_cores: int
    memory: MetricUsage
    swap: MetricUsage
    disks: list[DiskUsage]
    top_processes: list[ProcessUsage]
    services: list[ServiceUsage]
    temperature: str
    collected_at: str


class DashboardPayload(BaseModel):
    servers: list[GameServer]
    logs: list[str]
    backups: list[BackupItem]
    mods: list[ModItem]
    files: list[FileItem]


app = FastAPI(title="Ksylian API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

AGENT_URL = os.getenv("KSYLIAN_AGENT_URL", "").rstrip("/")
AGENT_TOKEN = os.getenv("KSYLIAN_AGENT_TOKEN", "")
SETTINGS_PATH = Path(os.getenv("KSYLIAN_SETTINGS_PATH", "/data/settings.json"))
CURSEFORGE_BASE_URL = "https://api.curseforge.com"
MINECRAFT_GAME_ID = 432
CURSEFORGE_CLASS_IDS = {"mods": 6, "modpacks": 4471}
CURSEFORGE_SORT_FIELDS = {"popularity": 2, "updated": 3, "name": 4, "downloads": 6}
CURSEFORGE_LOADER_TYPES = {"any": None, "forge": 1, "fabric": 4, "quilt": 5, "neoforge": 6}
CURSEFORGE_LOADER_LABELS = {1: "Forge", 4: "Fabric", 5: "Quilt", 6: "NeoForge"}

servers: dict[str, GameServer] = {
    "ksy-vanilla": GameServer(
        id="ksy-vanilla",
        name="Ksy Vanilla+",
        pack="Better MC Fabric",
        version="1.20.1",
        state=ServerState.online,
        players="12 / 48",
        ram="8.2 / 16 GB",
        cpu=34,
        disk="42 GB",
        address="play.ksylian.local:25565",
    ),
    "pink-nether": GameServer(
        id="pink-nether",
        name="Pink Nether",
        pack="Prominence II",
        version="1.20.1",
        state=ServerState.deploying,
        players="0 / 32",
        ram="2.1 / 12 GB",
        cpu=18,
        disk="18 GB",
        address="pink.ksylian.local:25566",
    ),
    "archive-realm": GameServer(
        id="archive-realm",
        name="Archive Realm",
        pack="Create: Perfect World",
        version="1.19.2",
        state=ServerState.offline,
        players="0 / 24",
        ram="0 / 10 GB",
        cpu=0,
        disk="31 GB",
        address="archive.ksylian.local:25567",
    ),
}

logs: list[str] = [
    "[23:04:11] Server thread/INFO Starting Minecraft server version 1.20.1",
    "[23:04:19] Loader/INFO Loaded 143 mods from CurseForge manifest",
    "[23:04:28] Backup/INFO Snapshot world-2026-07-15 completed",
    "[23:05:02] Proxy/INFO Velocity route registered: pink.ksylian.local",
    "[23:05:35] Mods/INFO 4 updates available for review",
]

backups: list[BackupItem] = [
    BackupItem(id="backup-1", name="world-before-update", size="6.8 GB", created="Сегодня, 22:40", server_id="ksy-vanilla"),
    BackupItem(id="backup-2", name="pink-nether-auto", size="3.1 GB", created="Сегодня, 20:15", server_id="pink-nether"),
    BackupItem(id="backup-3", name="archive-realm-monthly", size="12.4 GB", created="13 июля", server_id="archive-realm"),
]

mods: list[ModItem] = [
    ModItem(id="fabric-api", name="Fabric API", status="Обновлён", tag="required"),
    ModItem(id="voice-chat", name="Simple Voice Chat", status="Есть апдейт", tag="update"),
    ModItem(id="world-edit", name="WorldEdit", status="Обновлён", tag="required"),
    ModItem(id="dynmap", name="Dynmap", status="Проверить", tag="review"),
]

files: list[FileItem] = [
    FileItem(name="world", meta="Папка мира", kind="folder"),
    FileItem(name="mods", meta="143 файла", kind="folder"),
    FileItem(name="server.properties", meta="1.2 KB", kind="file"),
    FileItem(name="latest.log", meta="284 KB", kind="file"),
]


def agent_headers() -> dict[str, str]:
    if not AGENT_TOKEN:
        return {}
    return {"x-ksylian-token": AGENT_TOKEN}


def agent_get(path: str) -> httpx.Response:
    if not AGENT_URL:
        raise RuntimeError("Agent is not configured")
    return httpx.get(f"{AGENT_URL}{path}", headers=agent_headers(), timeout=10)


def agent_post(path: str) -> httpx.Response:
    if not AGENT_URL:
        raise RuntimeError("Agent is not configured")
    return httpx.post(f"{AGENT_URL}{path}", headers=agent_headers(), timeout=90)


def load_agent_servers() -> list[GameServer] | None:
    try:
        response = agent_get("/servers")
        response.raise_for_status()
        return [GameServer(**item) for item in response.json()]
    except Exception as error:
        append_log(f"agent unavailable: {error}")
        return None


def load_agent_logs(server_id: str) -> list[str]:
    try:
        response = agent_get(f"/servers/{server_id}/logs")
        response.raise_for_status()
        return response.json()
    except Exception as error:
        append_log(f"agent logs unavailable for {server_id}: {error}")
        return []


def load_agent_backups() -> list[BackupItem] | None:
    try:
        response = agent_get("/backups")
        response.raise_for_status()
        return [BackupItem(**item) for item in response.json()]
    except Exception as error:
        append_log(f"agent backups unavailable: {error}")
        return None


def load_agent_monitoring() -> HostMonitoring | None:
    try:
        response = agent_get("/monitoring")
        response.raise_for_status()
        return HostMonitoring(**response.json())
    except Exception as error:
        append_log(f"agent monitoring unavailable: {error}")
        return None


def append_log(message: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    logs.append(f"[{timestamp}] Ksylian/API {message}")
    del logs[:-80]


def load_settings() -> dict[str, str]:
    if not SETTINGS_PATH.exists():
        return {}

    try:
        data = json.loads(SETTINGS_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}

    if not isinstance(data, dict):
        return {}
    return {str(key): str(value) for key, value in data.items() if isinstance(value, str)}


def save_settings(data: dict[str, str]) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    SETTINGS_PATH.chmod(0o600)


def curseforge_api_key() -> str:
    return os.getenv("CURSEFORGE_API_KEY", "") or load_settings().get("curseforge_api_key", "")


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "••••"
    return f"{value[:4]}••••{value[-4:]}"


def curseforge_headers() -> dict[str, str]:
    key = curseforge_api_key()
    if not key:
        raise HTTPException(status_code=400, detail="CurseForge API key is not configured")
    return {"Accept": "application/json", "x-api-key": key}


def curseforge_get(path: str, params: dict[str, int | str]) -> dict:
    try:
        response = httpx.get(
            f"{CURSEFORGE_BASE_URL}{path}",
            headers=curseforge_headers(),
            params=params,
            timeout=20,
        )
        response.raise_for_status()
    except HTTPException:
        raise
    except httpx.HTTPStatusError as error:
        status_code = error.response.status_code
        if status_code in {401, 403}:
            detail = "CurseForge API key was rejected"
        else:
            detail = f"CurseForge API returned {status_code}"
        raise HTTPException(status_code=502, detail=detail) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="CurseForge API is unavailable") from error

    data = response.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="CurseForge API returned an unexpected response")
    return data


def compact_unique(values: list[str], limit: int = 6) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = value.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
        if len(result) >= limit:
            break
    return result


def transform_curseforge_project(item: dict, kind: Literal["mods", "modpacks"]) -> CurseForgeProject:
    latest_indexes = item.get("latestFilesIndexes") or []
    latest_files = item.get("latestFiles") or []
    logo = item.get("logo") or {}
    links = item.get("links") or {}
    versions: list[str] = []
    loader_ids: list[int] = []

    if isinstance(latest_indexes, list):
        for latest in latest_indexes:
            if not isinstance(latest, dict):
                continue
            game_version = latest.get("gameVersion")
            mod_loader = latest.get("modLoader")
            if isinstance(game_version, str):
                versions.append(game_version)
            if isinstance(mod_loader, int):
                loader_ids.append(mod_loader)

    if not versions and isinstance(latest_files, list):
        for latest in latest_files[:3]:
            if not isinstance(latest, dict):
                continue
            for game_version in latest.get("gameVersions") or []:
                if isinstance(game_version, str):
                    versions.append(game_version)

    latest_file_id = None
    if isinstance(latest_indexes, list) and latest_indexes:
        latest_file_id = latest_indexes[0].get("fileId")
    if latest_file_id is None and isinstance(latest_files, list) and latest_files:
        latest_file_id = latest_files[0].get("id")

    return CurseForgeProject(
        id=int(item.get("id") or 0),
        name=str(item.get("name") or "Untitled project"),
        slug=str(item.get("slug") or ""),
        summary=str(item.get("summary") or ""),
        type=kind,
        downloads=int(item.get("downloadCount") or 0),
        date_modified=str(item.get("dateModified") or ""),
        icon_url=str(logo.get("thumbnailUrl") or logo.get("url") or ""),
        website_url=str(links.get("websiteUrl") or ""),
        latest_file_id=latest_file_id if isinstance(latest_file_id, int) else None,
        game_versions=compact_unique(versions),
        loaders=compact_unique([CURSEFORGE_LOADER_LABELS.get(loader_id, "") for loader_id in loader_ids], 4),
    )


def get_server(server_id: str) -> GameServer:
    server = servers.get(server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Server not found")
    return server


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "ksylian-backend"}


@app.get("/api/dashboard", response_model=DashboardPayload)
def dashboard() -> DashboardPayload:
    agent_servers = load_agent_servers()
    current_servers = agent_servers if agent_servers is not None else list(servers.values())
    agent_backups = load_agent_backups()
    current_backups = agent_backups if agent_backups is not None else backups
    current_logs = logs[-20:]

    if agent_servers:
        real_logs: list[str] = []
        for server in agent_servers:
            real_logs.extend(load_agent_logs(server.id)[-12:])
        current_logs = real_logs[-40:] if real_logs else logs[-20:]

    return DashboardPayload(
        servers=current_servers,
        logs=current_logs,
        backups=current_backups,
        mods=mods,
        files=files,
    )


@app.get("/api/servers", response_model=list[GameServer])
def list_servers() -> list[GameServer]:
    agent_servers = load_agent_servers()
    if agent_servers is not None:
        return agent_servers
    return list(servers.values())


@app.get("/api/monitoring", response_model=HostMonitoring)
def host_monitoring() -> HostMonitoring:
    agent_monitoring = load_agent_monitoring()
    if agent_monitoring is not None:
        return agent_monitoring

    return HostMonitoring(
        hostname="demo-host",
        ip_addresses=["192.168.31.254"],
        uptime="0m",
        load_average=[0, 0, 0],
        cpu_percent=0,
        cpu_cores=1,
        memory=MetricUsage(used=0, total=1, percent=0, used_label="0 MB", total_label="0 MB"),
        swap=MetricUsage(used=0, total=0, percent=0, used_label="0 MB", total_label="0 MB"),
        disks=[],
        top_processes=[],
        services=[],
        temperature="n/a",
        collected_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


@app.post("/api/servers", response_model=GameServer)
def create_server(payload: CreateServerRequest) -> GameServer:
    if AGENT_URL:
        raise HTTPException(
            status_code=501,
            detail="Creating real servers is not implemented yet. Ksylian needs a provisioner first.",
        )

    server_id = payload.name.lower().strip().replace(" ", "-")
    if not server_id:
        raise HTTPException(status_code=400, detail="Server name is required")
    if server_id in servers:
        raise HTTPException(status_code=409, detail="Server already exists")

    server = GameServer(
        id=server_id,
        name=payload.name,
        pack=payload.pack,
        version=payload.version,
        state=ServerState.offline,
        players="0 / 24",
        ram="0 MB",
        cpu=0,
        disk="0 MB",
        address=payload.address or f"{server_id}.ksylian.local:25565",
    )
    servers[server.id] = server
    append_log(f"{server.name}: server draft created")
    return server


@app.delete("/api/servers/{server_id}")
def delete_server(server_id: str) -> dict[str, bool]:
    if AGENT_URL:
        raise HTTPException(
            status_code=501,
            detail="Deleting real systemd servers is not implemented yet. Stop and detach policy is required first.",
        )

    if server_id not in servers:
        raise HTTPException(status_code=404, detail="Server not found")
    del servers[server_id]
    append_log(f"{server_id}: server draft deleted")
    return {"ok": True}


@app.post("/api/servers/{server_id}/actions/{action}", response_model=ActionResult)
def run_server_action(server_id: str, action: ServerAction) -> ActionResult:
    if AGENT_URL:
        try:
            response = agent_post(f"/servers/{server_id}/actions/{action.value}")
            response.raise_for_status()
            data = response.json()
            server = GameServer(**data["server"])
            append_log(data["message"])
            return ActionResult(ok=True, message=data["message"], server=server)
        except Exception as error:
            append_log(f"agent action failed for {server_id}: {error}")
            raise HTTPException(status_code=502, detail="Host agent action failed") from error

    server = get_server(server_id)

    if action == ServerAction.start:
        server.state = ServerState.online
        server.cpu = max(server.cpu, 12)
        server.ram = server.ram if not server.ram.startswith("0 /") else "1.4 / 10 GB"
        message = f"{server.name}: start requested"
    elif action == ServerAction.restart:
        server.state = ServerState.deploying
        server.cpu = max(server.cpu, 22)
        message = f"{server.name}: restart requested"
    elif action == ServerAction.stop:
        server.state = ServerState.offline
        server.players = "0 / 48" if server.id == "ksy-vanilla" else "0 / 32"
        server.cpu = 0
        message = f"{server.name}: stop requested"
    else:
        backup = BackupItem(
            id=f"backup-{len(backups) + 1}",
            name=f"{server.id}-{datetime.now().strftime('%Y%m%d-%H%M')}",
            size="pending",
            created="Только что",
            server_id=server.id,
        )
        backups.insert(0, backup)
        message = f"{server.name}: backup queued"

    servers[server.id] = server
    append_log(message)
    return ActionResult(ok=True, message=message, server=server)


@app.get("/api/logs", response_model=list[str])
def list_logs() -> list[str]:
    agent_servers = load_agent_servers()
    if agent_servers:
        real_logs: list[str] = []
        for server in agent_servers:
            real_logs.extend(load_agent_logs(server.id)[-40:])
        return real_logs[-80:] if real_logs else logs[-80:]
    return logs[-80:]


@app.get("/api/servers/{server_id}/logs", response_model=list[str])
def list_server_logs(server_id: str) -> list[str]:
    if AGENT_URL:
        agent_logs = load_agent_logs(server_id)
        if agent_logs:
            return agent_logs[-120:]
        agent_servers = load_agent_servers()
        if agent_servers is not None and all(server.id != server_id for server in agent_servers):
            raise HTTPException(status_code=404, detail="Server not found")
        return []

    get_server(server_id)
    return [line for line in logs[-80:] if server_id in line or "Server thread" in line]


@app.get("/api/backups", response_model=list[BackupItem])
def list_backups() -> list[BackupItem]:
    agent_backups = load_agent_backups()
    if agent_backups is not None:
        return agent_backups
    return backups


@app.post("/api/backups", response_model=BackupItem)
def create_backup(server_id: str = "ksy-vanilla") -> BackupItem:
    if AGENT_URL:
        try:
            response = agent_post(f"/servers/{server_id}/actions/backup")
            response.raise_for_status()
            append_log(response.json()["message"])
            agent_backups = load_agent_backups()
            if agent_backups:
                return agent_backups[0]
        except Exception as error:
            append_log(f"agent backup failed for {server_id}: {error}")
            raise HTTPException(status_code=502, detail="Host agent backup failed") from error

    server = get_server(server_id)
    backup = BackupItem(
        id=f"backup-{len(backups) + 1}",
        name=f"{server.id}-{datetime.now().strftime('%Y%m%d-%H%M')}",
        size="pending",
        created="Только что",
        server_id=server.id,
    )
    backups.insert(0, backup)
    append_log(f"{server.name}: manual backup queued")
    return backup


@app.get("/api/settings", response_model=SettingsPayload)
def get_settings() -> SettingsPayload:
    key = curseforge_api_key()
    return SettingsPayload(
        has_curseforge_api_key=bool(key),
        curseforge_api_key_mask=mask_secret(key),
    )


@app.put("/api/settings", response_model=SettingsPayload)
def update_settings(payload: UpdateSettingsRequest) -> SettingsPayload:
    settings = load_settings()
    key = payload.curseforge_api_key.strip()

    if key:
        settings["curseforge_api_key"] = key
        append_log("settings: CurseForge API key updated")
    else:
        settings.pop("curseforge_api_key", None)
        append_log("settings: CurseForge API key cleared")

    save_settings(settings)
    key = curseforge_api_key()
    return SettingsPayload(
        has_curseforge_api_key=bool(key),
        curseforge_api_key_mask=mask_secret(key),
    )


@app.get("/api/mods", response_model=list[ModItem])
def list_mods() -> list[ModItem]:
    return mods


@app.post("/api/mods/check")
def check_mod_updates() -> dict[str, str]:
    append_log("CurseForge update check requested")
    return {"status": "queued"}


@app.get("/api/curseforge/search", response_model=CurseForgeSearchPayload)
def search_curseforge(
    kind: Literal["mods", "modpacks"] = "modpacks",
    query: str = "",
    minecraft_version: str = "",
    loader: Literal["any", "forge", "fabric", "quilt", "neoforge"] = "any",
    sort: Literal["popularity", "updated", "name", "downloads"] = "popularity",
    page_size: int = Query(default=20, ge=1, le=50),
    index: int = Query(default=0, ge=0, le=9950),
) -> CurseForgeSearchPayload:
    params: dict[str, int | str] = {
        "gameId": MINECRAFT_GAME_ID,
        "classId": CURSEFORGE_CLASS_IDS[kind],
        "pageSize": page_size,
        "index": index,
        "sortField": CURSEFORGE_SORT_FIELDS[sort],
        "sortOrder": "desc",
    }

    search_filter = query.strip()
    if search_filter:
        params["searchFilter"] = search_filter

    game_version = minecraft_version.strip()
    if game_version:
        params["gameVersion"] = game_version

    mod_loader_type = CURSEFORGE_LOADER_TYPES[loader]
    if mod_loader_type is not None:
        params["modLoaderType"] = mod_loader_type

    data = curseforge_get("/v1/mods/search", params)
    raw_items = data.get("data") or []
    pagination = data.get("pagination") or {}
    items = [
        transform_curseforge_project(item, kind)
        for item in raw_items
        if isinstance(item, dict)
    ]

    return CurseForgeSearchPayload(
        items=items,
        total_count=int(pagination.get("totalCount") or len(items)),
        has_api_key=True,
    )


@app.get("/api/files", response_model=list[FileItem])
def list_files() -> list[FileItem]:
    return files
