from __future__ import annotations

import os
from datetime import datetime
from enum import Enum
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException
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


class ModItem(BaseModel):
    id: str
    name: str
    status: str
    tag: Literal["required", "update", "review"]


class FileItem(BaseModel):
    name: str
    meta: str
    kind: Literal["folder", "file"]


class ActionResult(BaseModel):
    ok: bool
    message: str
    server: GameServer


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


def append_log(message: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    logs.append(f"[{timestamp}] Ksylian/API {message}")
    del logs[:-80]


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


@app.get("/api/mods", response_model=list[ModItem])
def list_mods() -> list[ModItem]:
    return mods


@app.post("/api/mods/check")
def check_mod_updates() -> dict[str, str]:
    append_log("CurseForge update check requested")
    return {"status": "queued"}


@app.get("/api/files", response_model=list[FileItem])
def list_files() -> list[FileItem]:
    return files
