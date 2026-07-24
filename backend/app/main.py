from __future__ import annotations

import os
import hashlib
import json
import re
import time
from datetime import datetime
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .agent_client import AgentClient
from .operation_state import apply_server_operation_states
from .schemas import (
    AgentStatus,
    BackupItem,
    CurseForgeProject,
    DashboardPayload,
    FileItem,
    GameServer,
    HostMonitoring,
    MinecraftVersion,
    MinecraftVersionsPayload,
    ModItem,
    ServerState,
    UpdateStatusPayload,
)


from .settings import (
    AGENT_TOKEN,
    AGENT_URL,
    BUILD_SHA,
    BUILD_VERSION,
    CURSEFORGE_BASE_URL,
    CURSEFORGE_LOADER_LABELS,
    GITHUB_API_BASE_URL,
    GITHUB_TOKEN,
    MINECRAFT_VERSION_CACHE_SECONDS,
    MINECRAFT_VERSION_MANIFEST_URL,
    PUBLIC_API_PATHS,
    RELEASE_REPOSITORY,
)
from .settings import load_settings, save_settings
from .auth import (
    current_user_from_request,
    require_admin_user,
    require_current_user,
    stored_users,
)
from .db import init_database
from .routes.auth import create_auth_router
from .routes.dashboard import create_dashboard_router
from .routes.marketplace import create_marketplace_router
from .routes.settings import create_settings_router
from .routes.servers import create_servers_router



app = FastAPI(title="Ksylian API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

agent_client = AgentClient(AGENT_URL, AGENT_TOKEN)
MINECRAFT_VERSION_CACHE: dict[str, object] = {"loaded_at": None, "payload": None}
CURSEFORGE_CACHE_SECONDS = 60
CURSEFORGE_CACHE: dict[str, tuple[float, dict]] = {}
DATABASE_READY = False

servers: dict[str, GameServer] = {
    "ksy-vanilla": GameServer(
        id="ksy-vanilla",
        name="Ksy Vanilla+",
        pack="Better MC Fabric",
        version="1.20.1",
        state=ServerState.running,
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
        state=ServerState.starting,
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
        state=ServerState.stopped,
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


@app.on_event("startup")
def startup() -> None:
    init_database()


@app.middleware("http")
async def require_auth_for_api(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api/") or path in PUBLIC_API_PATHS:
        return await call_next(request)

    if not stored_users():
        return JSONResponse(status_code=401, content={"detail": "Bootstrap admin account is required"})

    user = current_user_from_request(request)
    if user is None:
        return JSONResponse(status_code=401, content={"detail": "Authentication required"})

    request.state.user = user
    return await call_next(request)


def current_agent_status() -> AgentStatus:
    return agent_client.status()


def require_agent_available() -> None:
    status = current_agent_status()
    if status.configured and not status.available:
        raise HTTPException(status_code=503, detail="Host agent is unavailable")


def load_agent_servers() -> list[GameServer] | None:
    try:
        return apply_server_operation_states(agent_client.servers())
    except Exception as error:
        append_log(f"agent unavailable: {error}")
        return None


def load_agent_logs(server_id: str) -> list[str]:
    try:
        return agent_client.logs(server_id)
    except Exception as error:
        append_log(f"agent logs unavailable for {server_id}: {error}")
        return []


def load_agent_full_logs(server_id: str) -> list[str]:
    try:
        return agent_client.logs(server_id, full=True)
    except Exception as error:
        append_log(f"agent full logs unavailable for {server_id}: {error}")
        return []


def load_agent_crash_reports(server_id: str) -> list[CrashReportItem]:
    try:
        return agent_client.crash_reports(server_id)
    except Exception as error:
        append_log(f"agent crash reports unavailable for {server_id}: {error}")
        return []


def agent_rcon_status(server_id: str) -> dict[str, bool]:
    try:
        return agent_client.rcon_status(server_id)
    except Exception as error:
        append_log(f"agent rcon status unavailable for {server_id}: {error}")
        return {"available": False}


def agent_rcon_command(server_id: str, command: str) -> RconCommandResult:
    return agent_client.rcon_command(server_id, command)


def load_agent_backups() -> list[BackupItem] | None:
    try:
        return agent_client.backups()
    except Exception as error:
        append_log(f"agent backups unavailable: {error}")
        return None


def agent_create_backup(server_id: str, payload: BackupRequest) -> BackupItem:
    return agent_client.create_backup(server_id, payload)


def agent_restore_backup(server_id: str, payload: RestoreRequest) -> ActionResult:
    return agent_client.restore_backup(server_id, payload)


def agent_list_files(server_id: str, path: str = "") -> FileListPayload:
    return agent_client.files(server_id, path)


def agent_read_file(server_id: str, path: str) -> FileContentPayload:
    return agent_client.read_file(server_id, path)


def agent_search_files(server_id: str, query: str, path: str = "") -> list[FileSearchResult]:
    return agent_client.search_files(server_id, query, path)


def agent_write_file(server_id: str, payload: FileWriteRequest) -> FileEntry:
    return agent_client.write_file(server_id, payload)


def agent_file_action(server_id: str, payload: FileOperationRequest) -> FileEntry | dict[str, bool]:
    return agent_client.file_action(server_id, payload)


def agent_list_mods(server_id: str) -> list[InstalledModItem]:
    return agent_client.mods(server_id)


def agent_install_mod(server_id: str, payload: ModInstallRequest) -> InstalledModItem:
    return agent_client.install_mod(server_id, payload)


def agent_bulk_install_mods(server_id: str, payload: ModBulkInstallRequest) -> list[InstalledModItem]:
    return agent_client.bulk_install_mods(server_id, payload)


def agent_mod_action(server_id: str, payload: ModOperationRequest) -> dict[str, bool]:
    return agent_client.mod_action(server_id, payload)


def agent_bulk_mod_action(server_id: str, payload: ModBulkActionRequest) -> dict[str, int]:
    return agent_client.bulk_mod_action(server_id, payload)


def agent_loader_versions(loader_type: str) -> list[str]:
    return agent_client.loader_versions(loader_type)


def agent_fabric_installer_versions() -> list[str]:
    return agent_client.fabric_installer_versions()


def load_agent_monitoring() -> HostMonitoring | None:
    try:
        return agent_client.monitoring()
    except Exception as error:
        append_log(f"agent monitoring unavailable: {error}")
        return None


def load_minecraft_versions() -> MinecraftVersionsPayload:
    loaded_at = MINECRAFT_VERSION_CACHE.get("loaded_at")
    cached_payload = MINECRAFT_VERSION_CACHE.get("payload")
    if isinstance(loaded_at, datetime) and isinstance(cached_payload, MinecraftVersionsPayload):
        if (datetime.now() - loaded_at).total_seconds() < MINECRAFT_VERSION_CACHE_SECONDS:
            return cached_payload

    try:
        response = httpx.get(MINECRAFT_VERSION_MANIFEST_URL, timeout=20)
        response.raise_for_status()
        data = response.json()
    except Exception as error:
        append_log(f"minecraft versions unavailable: {error}")
        raise HTTPException(status_code=502, detail="Minecraft versions are unavailable") from error

    latest = data.get("latest") if isinstance(data, dict) else {}
    raw_versions = data.get("versions") if isinstance(data, dict) else []
    if not isinstance(latest, dict) or not isinstance(raw_versions, list):
        raise HTTPException(status_code=502, detail="Minecraft version manifest is invalid")

    versions: list[MinecraftVersion] = []
    for item in raw_versions:
        if not isinstance(item, dict):
            continue
        version_id = str(item.get("id") or "")
        version_type = str(item.get("type") or "")
        if version_type not in {"release", "snapshot", "old_beta", "old_alpha"} or not version_id:
            continue

        versions.append(
            MinecraftVersion(
                id=version_id,
                type=version_type,  # type: ignore[arg-type]
                label=version_id,
                released_at=str(item.get("releaseTime") or item.get("time") or ""),
            )
        )

    payload = MinecraftVersionsPayload(
        latest_release=str(latest.get("release") or ""),
        latest_snapshot=str(latest.get("snapshot") or ""),
        versions=versions,
    )
    MINECRAFT_VERSION_CACHE["loaded_at"] = datetime.now()
    MINECRAFT_VERSION_CACHE["payload"] = payload
    return payload


def append_log(message: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    logs.append(f"[{timestamp}] Ksylian/API {message}")
    del logs[:-80]



app.include_router(create_auth_router(append_log))

def curseforge_api_key() -> str:
    return os.getenv("CURSEFORGE_API_KEY", "") or load_settings().get("curseforge_api_key", "")


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "••••"
    return f"{value[:4]}••••{value[-4:]}"


def normalize_version(value: str) -> str:
    version = value.strip()
    return version if version.startswith("v") or version == "dev" else f"v{version}"


def version_key(value: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", value)
    return tuple(int(number) for number in numbers[:4]) or (0,)


def is_newer_version(candidate: str, current: str) -> bool:
    if not candidate or current == "dev":
        return bool(candidate)
    return version_key(candidate) > version_key(current)


def github_get(path: str) -> dict | list:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Ksylian-Backend/0.1",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    try:
        response = httpx.get(
            f"{GITHUB_API_BASE_URL}{path}",
            headers=headers,
            timeout=20,
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as error:
        raise HTTPException(status_code=502, detail=f"GitHub API returned {error.response.status_code}") from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="GitHub API is unavailable") from error


def latest_github_tag() -> tuple[str, str]:
    data = github_get(f"/repos/{RELEASE_REPOSITORY}/tags?per_page=50")
    if not isinstance(data, list):
        raise HTTPException(status_code=502, detail="GitHub tags response is invalid")

    tags: list[tuple[str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        commit = item.get("commit") or {}
        sha = str(commit.get("sha") or "") if isinstance(commit, dict) else ""
        if name.startswith("v"):
            tags.append((name, sha[:7]))

    if not tags:
        return "", ""

    return sorted(tags, key=lambda item: version_key(item[0]), reverse=True)[0]


def release_notes(tag: str) -> tuple[str, str]:
    if not tag:
        return "", ""
    try:
        data = github_get(f"/repos/{RELEASE_REPOSITORY}/releases/tags/{tag}")
    except HTTPException:
        return "", f"https://github.com/{RELEASE_REPOSITORY}/releases/tag/{tag}"

    if not isinstance(data, dict):
        return "", f"https://github.com/{RELEASE_REPOSITORY}/releases/tag/{tag}"
    return str(data.get("body") or ""), str(data.get("html_url") or f"https://github.com/{RELEASE_REPOSITORY}/releases/tag/{tag}")


def update_status_payload() -> UpdateStatusPayload:
    current_version = normalize_version(BUILD_VERSION)
    check_error = ""
    try:
        latest_version, latest_sha = latest_github_tag()
        notes, release_url = release_notes(latest_version)
    except HTTPException as error:
        latest_version = ""
        latest_sha = ""
        release_url = f"https://github.com/{RELEASE_REPOSITORY}/releases"
        notes = "Не удалось проверить GitHub releases. Если репозиторий приватный, укажи KSYLIAN_GITHUB_TOKEN для backend."
        check_error = str(error.detail)

    agent = current_agent_status()
    update_available = is_newer_version(latest_version, current_version)

    if not AGENT_URL:
        updater_status: Literal["ready", "agent_unavailable", "not_configured", "unknown"] = "not_configured"
    elif check_error:
        updater_status = "unknown"
    elif not agent.available:
        updater_status = "agent_unavailable"
    else:
        updater_status = "ready"

    return UpdateStatusPayload(
        current_version=current_version,
        current_sha=BUILD_SHA,
        latest_version=latest_version,
        latest_sha=latest_sha,
        update_available=update_available,
        checked_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        release_url=release_url,
        notes=notes[:1600],
        can_update=update_available and updater_status == "ready",
        updater_status=updater_status,
    )


def curseforge_headers() -> dict[str, str]:
    key = curseforge_api_key()
    if not key:
        raise HTTPException(status_code=400, detail="CurseForge API key is not configured")
    return {"Accept": "application/json", "x-api-key": key}


def curseforge_get(path: str, params: dict[str, int | str] | None = None) -> dict:
    query = params or {}
    key_hash = hashlib.sha256(curseforge_api_key().encode()).hexdigest()[:16]
    cache_key = json.dumps([key_hash, path, sorted(query.items())], ensure_ascii=False)
    cached = CURSEFORGE_CACHE.get(cache_key)
    if cached and time.monotonic() - cached[0] < CURSEFORGE_CACHE_SECONDS:
        return cached[1]
    try:
        response = httpx.get(
            f"{CURSEFORGE_BASE_URL}{path}",
            headers=curseforge_headers(),
            params=query,
            timeout=20,
        )
        response.raise_for_status()
    except HTTPException:
        raise
    except httpx.HTTPStatusError as error:
        status_code = error.response.status_code
        if status_code in {401, 403}:
            detail = "CurseForge API key was rejected"
        elif status_code == 429:
            retry_after = error.response.headers.get("Retry-After", "")
            detail = f"CurseForge rate limit reached{f', retry after {retry_after}s' if retry_after else ''}"
        else:
            detail = f"CurseForge API returned {status_code}"
        raise HTTPException(status_code=502, detail=detail) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="CurseForge API is unavailable") from error

    data = response.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="CurseForge API returned an unexpected response")
    CURSEFORGE_CACHE[cache_key] = (time.monotonic(), data)
    return data


def curseforge_key_status() -> tuple[str, str]:
    if not curseforge_api_key():
        return "missing", "CurseForge API key is not configured"
    try:
        data = curseforge_get("/v1/games", {"pageSize": 1})
    except HTTPException as error:
        return "invalid", str(error.detail)
    if data.get("data") is None:
        return "invalid", "CurseForge API key returned an unexpected response"
    return "valid", "CurseForge API key is valid"


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
    if server is not None:
        return server
    agent_servers = load_agent_servers()
    if agent_servers is not None:
        for agent_server in agent_servers:
            if agent_server.id == server_id:
                return agent_server
    raise HTTPException(status_code=404, detail="Server not found")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "ksylian-backend"}



app.include_router(create_dashboard_router(
    current_agent_status=current_agent_status,
    load_agent_servers=load_agent_servers,
    load_agent_backups=load_agent_backups,
    load_agent_logs=load_agent_logs,
    load_agent_monitoring=load_agent_monitoring,
    require_agent_available=require_agent_available,
    load_minecraft_versions=load_minecraft_versions,
    agent_client=agent_client,
    logs=logs,
    backups=backups,
    mods=mods,
    files=files,
    servers=servers,
    append_log=append_log,
))


app.include_router(create_servers_router(
    append_log=append_log,
    get_server=get_server,
    require_agent_available=require_agent_available,
    load_agent_servers=load_agent_servers,
    load_agent_logs=load_agent_logs,
    load_agent_full_logs=load_agent_full_logs,
    load_agent_crash_reports=load_agent_crash_reports,
    load_agent_backups=load_agent_backups,
    agent_rcon_status=agent_rcon_status,
    agent_rcon_command=agent_rcon_command,
    agent_create_backup=agent_create_backup,
    agent_restore_backup=agent_restore_backup,
    agent_list_files=agent_list_files,
    agent_read_file=agent_read_file,
    agent_search_files=agent_search_files,
    agent_write_file=agent_write_file,
    agent_file_action=agent_file_action,
    agent_list_mods=agent_list_mods,
    agent_install_mod=agent_install_mod,
    agent_bulk_install_mods=agent_bulk_install_mods,
    agent_mod_action=agent_mod_action,
    agent_bulk_mod_action=agent_bulk_mod_action,
    agent_loader_versions=agent_loader_versions,
    agent_fabric_installer_versions=agent_fabric_installer_versions,
    agent_client=agent_client,
    logs=logs,
    backups=backups,
    servers=servers,
))

app.include_router(create_settings_router(
    append_log=append_log,
    current_agent_status=current_agent_status,
    curseforge_api_key=curseforge_api_key,
    curseforge_key_status=curseforge_key_status,
    mask_secret=mask_secret,
    update_status_payload=update_status_payload,
    agent_client=agent_client,
))
app.include_router(create_marketplace_router(
    mods=mods,
    files=files,
    curseforge_api_key=curseforge_api_key,
    curseforge_get=curseforge_get,
    transform_curseforge_project=transform_curseforge_project,
    append_log=append_log,
    agent_client=agent_client,
    get_server=get_server,
))
