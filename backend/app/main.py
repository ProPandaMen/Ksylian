from __future__ import annotations

import os
import asyncio
import json
import re
import base64
import hashlib
import hmac
import secrets
import sqlite3
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Literal

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field


class ServerState(str, Enum):
    installing = "installing"
    stopped = "stopped"
    starting = "starting"
    running = "running"
    stopping = "stopping"
    crashed = "crashed"
    updating = "updating"
    backing_up = "backing_up"


class ServerAction(str, Enum):
    start = "start"
    restart = "restart"
    stop = "stop"
    kill = "kill"
    update = "update"
    rollback = "rollback"
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
    exit_code: int | None = None
    last_event: str = ""
    warnings: list[str] = Field(default_factory=list)


class BackupItem(BaseModel):
    id: str
    name: str
    size: str
    created: str
    server_id: str
    checksum: str = ""
    description: str = ""
    manifest: str = ""


class CreateServerRequest(BaseModel):
    name: str
    type: Literal["vanilla", "paper", "purpur", "fabric", "forge", "neoforge"] = "vanilla"
    pack: str
    version: str = "1.20.1"
    address: str = ""
    min_ram: str = "1G"
    max_ram: str = "2G"
    java_runtime: str = "auto"
    jvm_args: str = ""
    cpu_limit: int = 100
    loader_version: str = ""
    installer_version: str = ""
    install_fabric_api: bool = False


class MinecraftVersion(BaseModel):
    id: str
    type: Literal["release", "snapshot", "old_beta", "old_alpha"]
    label: str
    released_at: str = ""


class MinecraftVersionsPayload(BaseModel):
    latest_release: str = ""
    latest_snapshot: str = ""
    versions: list[MinecraftVersion]


class AgentStatus(BaseModel):
    configured: bool
    available: bool
    status: Literal["online", "offline", "not_configured"]
    message: str = ""
    public_domain: str = ""
    proxy_domain: str = ""
    proxy_port: str = ""


class SettingsPayload(BaseModel):
    has_curseforge_api_key: bool
    curseforge_api_key_mask: str = ""
    agent: AgentStatus


class UpdateSettingsRequest(BaseModel):
    curseforge_api_key: str = ""


ThemeName = Literal["pink", "black", "white", "green"]
UserRole = Literal["admin", "member"]


class AuthStatusPayload(BaseModel):
    has_users: bool
    bootstrap_required: bool


class AuthRequest(BaseModel):
    username: str
    password: str


class BootstrapAdminRequest(AuthRequest):
    display_name: str = ""
    theme: ThemeName = "pink"


class InviteRegistrationRequest(AuthRequest):
    token: str
    display_name: str = ""
    theme: ThemeName = "pink"


class AuthUser(BaseModel):
    id: str
    username: str
    display_name: str
    role: UserRole
    theme: ThemeName = "pink"
    created_at: str


class AuthSessionPayload(BaseModel):
    token: str
    user: AuthUser


class ThemeUpdateRequest(BaseModel):
    theme: ThemeName


class UserInvite(BaseModel):
    id: str
    token: str
    role: UserRole = "member"
    created_at: str
    expires_at: str
    used_at: str = ""
    invited_by: str = ""


class CreateInviteRequest(BaseModel):
    role: UserRole = "member"
    ttl_hours: int = 24


class UpdateStatusPayload(BaseModel):
    current_version: str
    current_sha: str
    latest_version: str = ""
    latest_sha: str = ""
    update_available: bool = False
    checked_at: str
    release_url: str = ""
    notes: str = ""
    can_update: bool = False
    updater_status: Literal["ready", "agent_unavailable", "not_configured", "unknown"] = "unknown"


class ApplyUpdateRequest(BaseModel):
    target_version: str = ""


class ApplyUpdateResult(BaseModel):
    ok: bool
    message: str
    target_version: str = ""


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


class BackupRequest(BaseModel):
    mode: Literal["live", "stopped"] = "live"
    parts: list[Literal["world", "mods", "config", "root"]] = Field(
        default_factory=lambda: ["world", "mods", "config", "root"],
    )
    description: str = ""


class RestoreRequest(BaseModel):
    backup_id: str
    target: Literal["all", "world", "mods", "config"] = "all"
    insurance_backup: bool = True


class FileEntry(BaseModel):
    name: str
    path: str
    kind: Literal["folder", "file"]
    size: str
    modified: str
    quick: str = ""


class FileListPayload(BaseModel):
    path: str
    entries: list[FileEntry]


class FileWriteRequest(BaseModel):
    path: str
    content: str
    encoding: Literal["text", "base64"] = "text"


class FileOperationRequest(BaseModel):
    action: Literal["mkdir", "delete", "move", "rename", "extract"]
    path: str
    target_path: str = ""


class FileContentPayload(BaseModel):
    path: str
    name: str
    content: str
    encoding: Literal["text", "base64"]
    syntax: Literal["json", "yaml", "toml", "properties", "text", "binary"] = "text"


class FileSearchResult(BaseModel):
    path: str
    line: int
    preview: str
    syntax: Literal["json", "yaml", "toml", "properties", "text", "binary"] = "text"


class ModDependency(BaseModel):
    id: str
    version: str = ""
    required: bool = True


class InstalledModItem(BaseModel):
    id: str
    name: str
    version: str = ""
    loader: Literal["fabric", "forge", "neoforge", "unknown"] = "unknown"
    side: Literal["client", "server", "both", "unknown"] = "unknown"
    filename: str
    path: str
    size: str
    enabled: bool = True
    sha1: str
    sha256: str
    sha512: str
    dependencies: list[ModDependency] = Field(default_factory=list)
    duplicate: bool = False
    multiple_versions: bool = False
    warnings: list[str] = Field(default_factory=list)


class ModInstallRequest(BaseModel):
    filename: str
    content: str
    encoding: Literal["base64"] = "base64"
    pinned: bool = False
    release_channel: Literal["release", "beta", "alpha"] = "release"


class ModOperationRequest(BaseModel):
    action: Literal["delete", "disable", "enable", "pin", "update"]
    path: str
    filename: str = ""
    content: str = ""
    release_channel: Literal["release", "beta", "alpha"] = "release"


class ModBulkInstallRequest(BaseModel):
    items: list[ModInstallRequest]


class ModBulkActionRequest(BaseModel):
    action: Literal["update", "delete", "disable", "enable", "pin"]
    items: list[ModOperationRequest]


class ActionResult(BaseModel):
    ok: bool
    message: str
    server: GameServer


class ServerConfigPayload(BaseModel):
    content: str


class RconCommandPayload(BaseModel):
    command: str


class RconCommandResult(BaseModel):
    ok: bool
    output: str


class CrashReportItem(BaseModel):
    name: str
    size: str
    created: str
    summary: str
    probable_cause: str = ""
    conflicting_mod: str = ""
    missing_dependency: str = ""
    client_only_mod: str = ""
    stack_trace: list[str] = Field(default_factory=list)
    recent_changes: list[str] = Field(default_factory=list)


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
    agent: AgentStatus


app = FastAPI(title="Ksylian API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

PUBLIC_API_PATHS = {
    "/api/auth/status",
    "/api/auth/bootstrap",
    "/api/auth/login",
    "/api/auth/register-invite",
}

AGENT_URL = os.getenv("KSYLIAN_AGENT_URL", "").rstrip("/")
AGENT_TOKEN = os.getenv("KSYLIAN_AGENT_TOKEN", "")
SETTINGS_PATH = Path(os.getenv("KSYLIAN_SETTINGS_PATH", "/data/settings.json"))
USERS_PATH = Path(os.getenv("KSYLIAN_USERS_PATH", "/data/users.json"))
DATABASE_PATH = Path(os.getenv("KSYLIAN_DATABASE_PATH", "/data/ksylian.db"))
AUTH_SECRET = os.getenv("KSYLIAN_AUTH_SECRET", "")
SESSION_TTL_SECONDS = int(os.getenv("KSYLIAN_SESSION_TTL_SECONDS", str(60 * 60 * 24 * 14)))
BUILD_VERSION = os.getenv("KSYLIAN_BUILD_VERSION", "dev")
BUILD_SHA = os.getenv("KSYLIAN_BUILD_SHA", "local")
RELEASE_REPOSITORY = os.getenv("KSYLIAN_RELEASE_REPOSITORY", "ProPandaMen/Ksylian")
GITHUB_API_BASE_URL = os.getenv("KSYLIAN_GITHUB_API_URL", "https://api.github.com").rstrip("/")
GITHUB_TOKEN = os.getenv("KSYLIAN_GITHUB_TOKEN", "")
CURSEFORGE_BASE_URL = "https://api.curseforge.com"
MINECRAFT_GAME_ID = 432
CURSEFORGE_CLASS_IDS = {"mods": 6, "modpacks": 4471}
CURSEFORGE_SORT_FIELDS = {"popularity": 2, "updated": 3, "name": 4, "downloads": 6}
CURSEFORGE_LOADER_TYPES = {"any": None, "forge": 1, "fabric": 4, "quilt": 5, "neoforge": 6}
CURSEFORGE_LOADER_LABELS = {1: "Forge", 4: "Fabric", 5: "Quilt", 6: "NeoForge"}
MINECRAFT_VERSION_MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
MINECRAFT_VERSION_CACHE: dict[str, object] = {"loaded_at": None, "payload": None}
MINECRAFT_VERSION_CACHE_SECONDS = 60 * 60
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


def utc_now() -> int:
    return int(time.time())


def iso_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def auth_secret() -> str:
    if AUTH_SECRET:
        return AUTH_SECRET
    fallback = load_settings().get("auth_secret", "")
    if fallback:
        return fallback
    fallback = secrets.token_urlsafe(48)
    settings = load_settings()
    settings["auth_secret"] = fallback
    save_settings(settings)
    return fallback


def load_legacy_user_store() -> dict:
    if not USERS_PATH.exists():
        return {"users": [], "invites": []}
    try:
        data = json.loads(USERS_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {"users": [], "invites": []}
    if not isinstance(data, dict):
        return {"users": [], "invites": []}
    users = data.get("users") if isinstance(data.get("users"), list) else []
    invites = data.get("invites") if isinstance(data.get("invites"), list) else []
    return {"users": users, "invites": invites}


def database() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def row_to_dict(row: sqlite3.Row) -> dict:
    return {key: row[key] for key in row.keys()}


def init_database() -> None:
    global DATABASE_READY
    if DATABASE_READY:
        return
    with database() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'member',
                theme TEXT NOT NULL DEFAULT 'pink',
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS invites (
                id TEXT PRIMARY KEY,
                token TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL DEFAULT 'member',
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                used_at TEXT NOT NULL DEFAULT '',
                invited_by TEXT NOT NULL DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
            CREATE INDEX IF NOT EXISTS idx_invites_token ON invites(token);
            CREATE INDEX IF NOT EXISTS idx_invites_used_at ON invites(used_at);
            """
        )
        migrate_legacy_user_store(connection)
    try:
        DATABASE_PATH.chmod(0o600)
    except OSError:
        pass
    DATABASE_READY = True


def migrate_legacy_user_store(connection: sqlite3.Connection) -> None:
    legacy_store = load_legacy_user_store()
    for item in legacy_store.get("users", []):
        if not isinstance(item, dict):
            continue
        if not item.get("username") or not item.get("password_hash"):
            continue
        connection.execute(
            """
            INSERT OR IGNORE INTO users
                (id, username, display_name, role, theme, password_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(item.get("id") or secrets.token_urlsafe(10)),
                str(item.get("username") or ""),
                str(item.get("display_name") or item.get("username") or ""),
                str(item.get("role") or "member"),
                str(item.get("theme") or "pink"),
                str(item.get("password_hash") or ""),
                str(item.get("created_at") or iso_now()),
            ),
        )
    for item in legacy_store.get("invites", []):
        if not isinstance(item, dict):
            continue
        if not item.get("token"):
            continue
        connection.execute(
            """
            INSERT OR IGNORE INTO invites
                (id, token, role, created_at, expires_at, used_at, invited_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(item.get("id") or secrets.token_urlsafe(8)),
                str(item.get("token") or ""),
                str(item.get("role") or "member"),
                str(item.get("created_at") or iso_now()),
                str(item.get("expires_at") or iso_now()),
                str(item.get("used_at") or ""),
                str(item.get("invited_by") or ""),
            ),
        )


@app.on_event("startup")
def startup() -> None:
    init_database()


def load_user_store() -> dict:
    init_database()
    with database() as connection:
        users = [
            row_to_dict(row)
            for row in connection.execute(
                """
                SELECT id, username, display_name, role, theme, password_hash, created_at
                FROM users
                ORDER BY created_at ASC
                """
            )
        ]
        invites = [
            row_to_dict(row)
            for row in connection.execute(
                """
                SELECT id, token, role, created_at, expires_at, used_at, invited_by
                FROM invites
                ORDER BY created_at DESC
                """
            )
        ]
    return {"users": users, "invites": invites}


def save_user_store(data: dict) -> None:
    init_database()
    users = [item for item in data.get("users", []) if isinstance(item, dict)]
    invites = [item for item in data.get("invites", []) if isinstance(item, dict)]
    with database() as connection:
        connection.execute("DELETE FROM invites")
        connection.execute("DELETE FROM users")
        connection.executemany(
            """
            INSERT INTO users
                (id, username, display_name, role, theme, password_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    str(item.get("id") or secrets.token_urlsafe(10)),
                    str(item.get("username") or ""),
                    str(item.get("display_name") or item.get("username") or ""),
                    str(item.get("role") or "member"),
                    str(item.get("theme") or "pink"),
                    str(item.get("password_hash") or ""),
                    str(item.get("created_at") or iso_now()),
                )
                for item in users
            ],
        )
        connection.executemany(
            """
            INSERT INTO invites
                (id, token, role, created_at, expires_at, used_at, invited_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    str(item.get("id") or secrets.token_urlsafe(8)),
                    str(item.get("token") or ""),
                    str(item.get("role") or "member"),
                    str(item.get("created_at") or iso_now()),
                    str(item.get("expires_at") or iso_now()),
                    str(item.get("used_at") or ""),
                    str(item.get("invited_by") or ""),
                )
                for item in invites
            ],
        )


def stored_users() -> list[dict]:
    return [item for item in load_user_store().get("users", []) if isinstance(item, dict)]


def user_public(user: dict) -> AuthUser:
    return AuthUser(
        id=str(user.get("id") or ""),
        username=str(user.get("username") or ""),
        display_name=str(user.get("display_name") or user.get("username") or ""),
        role=str(user.get("role") or "member"),  # type: ignore[arg-type]
        theme=str(user.get("theme") or "pink"),  # type: ignore[arg-type]
        created_at=str(user.get("created_at") or ""),
    )


def normalize_username(username: str) -> str:
    value = username.strip().lower()
    if not re.fullmatch(r"[a-z0-9_.-]{3,32}", value):
        raise HTTPException(status_code=400, detail="Username must be 3-32 latin characters")
    return value


def validate_password(password: str) -> None:
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must contain at least 8 characters")


def hash_password(password: str, salt: str | None = None) -> str:
    salt_bytes = base64.urlsafe_b64decode(salt.encode()) if salt else secrets.token_bytes(18)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt_bytes, 210_000)
    salt_value = base64.urlsafe_b64encode(salt_bytes).decode()
    digest_value = base64.urlsafe_b64encode(digest).decode()
    return f"pbkdf2_sha256${salt_value}${digest_value}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, salt, digest = stored_hash.split("$", 2)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    expected = hash_password(password, salt).split("$", 2)[2]
    return hmac.compare_digest(expected, digest)


def create_token(user_id: str) -> str:
    expires_at = utc_now() + SESSION_TTL_SECONDS
    nonce = secrets.token_urlsafe(12)
    payload = f"{user_id}.{expires_at}.{nonce}"
    signature = hmac.new(auth_secret().encode(), payload.encode(), hashlib.sha256).digest()
    return f"{payload}.{base64.urlsafe_b64encode(signature).decode().rstrip('=')}"


def user_from_token(token: str) -> dict | None:
    parts = token.split(".")
    if len(parts) != 4:
        return None
    user_id, expires_at_raw, nonce, signature = parts
    payload = f"{user_id}.{expires_at_raw}.{nonce}"
    expected = base64.urlsafe_b64encode(
        hmac.new(auth_secret().encode(), payload.encode(), hashlib.sha256).digest()
    ).decode().rstrip("=")
    if not hmac.compare_digest(expected, signature):
        return None
    try:
        expires_at = int(expires_at_raw)
    except ValueError:
        return None
    if expires_at < utc_now():
        return None
    return next((user for user in stored_users() if str(user.get("id")) == user_id), None)


def current_user_from_request(request: Request) -> dict | None:
    auth_header = request.headers.get("authorization", "")
    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return user_from_token(token)


def require_current_user(request: Request) -> dict:
    user = getattr(request.state, "user", None) or current_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def require_admin_user(request: Request) -> dict:
    user = require_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin permissions required")
    return user


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


def agent_headers() -> dict[str, str]:
    if not AGENT_TOKEN:
        return {}
    return {"x-ksylian-token": AGENT_TOKEN}


def agent_get(path: str, params: dict[str, str] | None = None) -> httpx.Response:
    if not AGENT_URL:
        raise RuntimeError("Agent is not configured")
    return httpx.get(f"{AGENT_URL}{path}", headers=agent_headers(), params=params, timeout=10)


def agent_post(path: str, json: dict | None = None) -> httpx.Response:
    if not AGENT_URL:
        raise RuntimeError("Agent is not configured")
    return httpx.post(f"{AGENT_URL}{path}", headers=agent_headers(), json=json, timeout=240)


def agent_put(path: str, json: dict | None = None) -> httpx.Response:
    if not AGENT_URL:
        raise RuntimeError("Agent is not configured")
    return httpx.put(f"{AGENT_URL}{path}", headers=agent_headers(), json=json, timeout=30)


def agent_delete(path: str) -> httpx.Response:
    if not AGENT_URL:
        raise RuntimeError("Agent is not configured")
    return httpx.delete(f"{AGENT_URL}{path}", headers=agent_headers(), timeout=90)


def current_agent_status() -> AgentStatus:
    if not AGENT_URL:
        return AgentStatus(
            configured=False,
            available=False,
            status="not_configured",
            message="Host agent is not configured",
        )

    try:
        response = agent_get("/health")
        response.raise_for_status()
        data = response.json()
        return AgentStatus(
            configured=True,
            available=True,
            status="online",
            message="Host agent is online",
            public_domain=str(data.get("public_domain") or "") if isinstance(data, dict) else "",
            proxy_domain=str(data.get("proxy_domain") or "") if isinstance(data, dict) else "",
            proxy_port=str(data.get("proxy_port") or "") if isinstance(data, dict) else "",
        )
    except Exception as error:
        return AgentStatus(
            configured=True,
            available=False,
            status="offline",
            message=str(error),
        )


def require_agent_available() -> None:
    status = current_agent_status()
    if status.configured and not status.available:
        raise HTTPException(status_code=503, detail="Host agent is unavailable")


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


def load_agent_full_logs(server_id: str) -> list[str]:
    try:
        response = agent_get(f"/servers/{server_id}/logs/full")
        response.raise_for_status()
        return [str(line) for line in response.json()]
    except Exception as error:
        append_log(f"agent full logs unavailable for {server_id}: {error}")
        return []


def load_agent_crash_reports(server_id: str) -> list[CrashReportItem]:
    try:
        response = agent_get(f"/servers/{server_id}/crash-reports")
        response.raise_for_status()
        return [CrashReportItem(**item) for item in response.json()]
    except Exception as error:
        append_log(f"agent crash reports unavailable for {server_id}: {error}")
        return []


def agent_rcon_status(server_id: str) -> dict[str, bool]:
    try:
        response = agent_get(f"/servers/{server_id}/rcon/status")
        response.raise_for_status()
        data = response.json()
        return {"available": bool(data.get("available"))}
    except Exception as error:
        append_log(f"agent rcon status unavailable for {server_id}: {error}")
        return {"available": False}


def agent_rcon_command(server_id: str, command: str) -> RconCommandResult:
    response = agent_post(f"/servers/{server_id}/rcon/command", json={"command": command})
    response.raise_for_status()
    return RconCommandResult(**response.json())


def load_agent_backups() -> list[BackupItem] | None:
    try:
        response = agent_get("/backups")
        response.raise_for_status()
        return [BackupItem(**item) for item in response.json()]
    except Exception as error:
        append_log(f"agent backups unavailable: {error}")
        return None


def agent_create_backup(server_id: str, payload: BackupRequest) -> BackupItem:
    response = agent_post(f"/servers/{server_id}/backups", json=payload.model_dump())
    response.raise_for_status()
    return BackupItem(**response.json())


def agent_restore_backup(server_id: str, payload: RestoreRequest) -> ActionResult:
    response = agent_post(f"/servers/{server_id}/restore", json=payload.model_dump())
    response.raise_for_status()
    return ActionResult(**response.json())


def agent_list_files(server_id: str, path: str = "") -> FileListPayload:
    response = agent_get(f"/servers/{server_id}/files", params={"path": path})
    response.raise_for_status()
    return FileListPayload(**response.json())


def agent_read_file(server_id: str, path: str) -> FileContentPayload:
    response = agent_get(f"/servers/{server_id}/files/content", params={"path": path})
    response.raise_for_status()
    return FileContentPayload(**response.json())


def agent_search_files(server_id: str, query: str, path: str = "") -> list[FileSearchResult]:
    response = agent_get(f"/servers/{server_id}/files/search", params={"query": query, "path": path})
    response.raise_for_status()
    return [FileSearchResult(**item) for item in response.json()]


def agent_write_file(server_id: str, payload: FileWriteRequest) -> FileEntry:
    response = agent_put(f"/servers/{server_id}/files", json=payload.model_dump())
    response.raise_for_status()
    return FileEntry(**response.json())


def agent_file_action(server_id: str, payload: FileOperationRequest) -> FileEntry | dict[str, bool]:
    response = agent_post(f"/servers/{server_id}/files/actions", json=payload.model_dump())
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict) and data.get("name"):
        return FileEntry(**data)
    return {"ok": True}


def agent_list_mods(server_id: str) -> list[InstalledModItem]:
    response = agent_get(f"/servers/{server_id}/mods")
    response.raise_for_status()
    return [InstalledModItem(**item) for item in response.json()]


def agent_install_mod(server_id: str, payload: ModInstallRequest) -> InstalledModItem:
    response = agent_post(f"/servers/{server_id}/mods", json=payload.model_dump())
    response.raise_for_status()
    return InstalledModItem(**response.json())


def agent_bulk_install_mods(server_id: str, payload: ModBulkInstallRequest) -> list[InstalledModItem]:
    response = agent_post(f"/servers/{server_id}/mods/bulk", json=payload.model_dump())
    response.raise_for_status()
    return [InstalledModItem(**item) for item in response.json()]


def agent_mod_action(server_id: str, payload: ModOperationRequest) -> dict[str, bool]:
    response = agent_post(f"/servers/{server_id}/mods/actions", json=payload.model_dump())
    response.raise_for_status()
    return {"ok": True}


def agent_bulk_mod_action(server_id: str, payload: ModBulkActionRequest) -> dict[str, int]:
    response = agent_post(f"/servers/{server_id}/mods/bulk-actions", json=payload.model_dump())
    response.raise_for_status()
    return {"completed": int(response.json().get("completed", 0))}


def agent_loader_versions(loader_type: str) -> list[str]:
    response = agent_get(f"/loaders/{loader_type}/versions")
    response.raise_for_status()
    return [str(item) for item in response.json()]


def agent_fabric_installer_versions() -> list[str]:
    response = agent_get("/loaders/fabric/installers")
    response.raise_for_status()
    return [str(item) for item in response.json()]


def load_agent_monitoring() -> HostMonitoring | None:
    try:
        response = agent_get("/monitoring")
        response.raise_for_status()
        return HostMonitoring(**response.json())
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


@app.get("/api/auth/status", response_model=AuthStatusPayload)
def auth_status() -> AuthStatusPayload:
    has_users = bool(stored_users())
    return AuthStatusPayload(has_users=has_users, bootstrap_required=not has_users)


@app.post("/api/auth/bootstrap", response_model=AuthSessionPayload)
def bootstrap_admin(payload: BootstrapAdminRequest) -> AuthSessionPayload:
    store = load_user_store()
    if store.get("users"):
        raise HTTPException(status_code=409, detail="Admin account already exists")

    username = normalize_username(payload.username)
    validate_password(payload.password)
    user = {
        "id": secrets.token_urlsafe(10),
        "username": username,
        "display_name": payload.display_name.strip() or username,
        "role": "admin",
        "theme": payload.theme,
        "password_hash": hash_password(payload.password),
        "created_at": iso_now(),
    }
    store["users"] = [user]
    store["invites"] = []
    save_user_store(store)
    append_log(f"auth: admin account created for {username}")
    return AuthSessionPayload(token=create_token(user["id"]), user=user_public(user))


@app.post("/api/auth/login", response_model=AuthSessionPayload)
def login(payload: AuthRequest) -> AuthSessionPayload:
    username = normalize_username(payload.username)
    user = next((item for item in stored_users() if item.get("username") == username), None)
    if not user or not verify_password(payload.password, str(user.get("password_hash") or "")):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return AuthSessionPayload(token=create_token(str(user["id"])), user=user_public(user))


@app.get("/api/auth/me", response_model=AuthUser)
def me(user: dict = Depends(require_current_user)) -> AuthUser:
    return user_public(user)


@app.put("/api/auth/me/theme", response_model=AuthUser)
def update_my_theme(payload: ThemeUpdateRequest, user: dict = Depends(require_current_user)) -> AuthUser:
    store = load_user_store()
    for item in store.get("users", []):
        if isinstance(item, dict) and item.get("id") == user.get("id"):
            item["theme"] = payload.theme
            save_user_store(store)
            return user_public(item)
    raise HTTPException(status_code=404, detail="User not found")


@app.post("/api/auth/register-invite", response_model=AuthSessionPayload)
def register_invite(payload: InviteRegistrationRequest) -> AuthSessionPayload:
    store = load_user_store()
    invite = next(
        (
            item
            for item in store.get("invites", [])
            if isinstance(item, dict) and item.get("token") == payload.token and not item.get("used_at")
        ),
        None,
    )
    if not invite:
        raise HTTPException(status_code=404, detail="Invite was not found")
    try:
        expires_at = datetime.fromisoformat(str(invite.get("expires_at") or ""))
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Invite is invalid") from error
    if expires_at < datetime.now():
        raise HTTPException(status_code=410, detail="Invite has expired")

    username = normalize_username(payload.username)
    validate_password(payload.password)
    if any(user.get("username") == username for user in store.get("users", []) if isinstance(user, dict)):
        raise HTTPException(status_code=409, detail="Username already exists")

    user = {
        "id": secrets.token_urlsafe(10),
        "username": username,
        "display_name": payload.display_name.strip() or username,
        "role": invite.get("role") or "member",
        "theme": payload.theme,
        "password_hash": hash_password(payload.password),
        "created_at": iso_now(),
    }
    store["users"].append(user)
    invite["used_at"] = iso_now()
    save_user_store(store)
    append_log(f"auth: invite accepted by {username}")
    return AuthSessionPayload(token=create_token(user["id"]), user=user_public(user))


@app.get("/api/users", response_model=list[AuthUser])
def list_users(_: dict = Depends(require_admin_user)) -> list[AuthUser]:
    return [user_public(user) for user in stored_users()]


@app.get("/api/users/invites", response_model=list[UserInvite])
def list_invites(_: dict = Depends(require_admin_user)) -> list[UserInvite]:
    invites = []
    for item in load_user_store().get("invites", []):
        if isinstance(item, dict):
            invites.append(UserInvite(**item))
    return invites


@app.post("/api/users/invites", response_model=UserInvite)
def create_invite(payload: CreateInviteRequest, user: dict = Depends(require_admin_user)) -> UserInvite:
    ttl_hours = min(max(payload.ttl_hours, 1), 24 * 14)
    invite = UserInvite(
        id=secrets.token_urlsafe(8),
        token=secrets.token_urlsafe(24),
        role=payload.role,
        created_at=iso_now(),
        expires_at=datetime.fromtimestamp(time.time() + ttl_hours * 3600).isoformat(timespec="seconds"),
        invited_by=str(user.get("id") or ""),
    )
    store = load_user_store()
    store.setdefault("invites", []).insert(0, invite.model_dump())
    save_user_store(store)
    append_log(f"auth: invite created by {user.get('username')}")
    return invite


@app.get("/api/dashboard", response_model=DashboardPayload)
def dashboard() -> DashboardPayload:
    agent = current_agent_status()
    agent_servers = load_agent_servers()
    current_servers = agent_servers if agent_servers is not None else ([] if agent.configured else list(servers.values()))
    agent_backups = load_agent_backups()
    current_backups = agent_backups if agent_backups is not None else ([] if agent.configured else backups)
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
        agent=agent,
    )


@app.get("/api/servers", response_model=list[GameServer])
def list_servers() -> list[GameServer]:
    agent_servers = load_agent_servers()
    if agent_servers is not None:
        return agent_servers
    require_agent_available()
    return list(servers.values())


@app.get("/api/monitoring", response_model=HostMonitoring)
def host_monitoring() -> HostMonitoring:
    agent_monitoring = load_agent_monitoring()
    if agent_monitoring is not None:
        return agent_monitoring
    require_agent_available()

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


@app.get("/api/minecraft/versions", response_model=MinecraftVersionsPayload)
def minecraft_versions() -> MinecraftVersionsPayload:
    return load_minecraft_versions()


@app.get("/api/agent/status", response_model=AgentStatus)
def agent_status() -> AgentStatus:
    return current_agent_status()


@app.post("/api/agent/restart", response_model=AgentStatus)
def restart_agent() -> AgentStatus:
    status = current_agent_status()
    if not status.configured:
        raise HTTPException(status_code=409, detail="Host agent is not configured")
    if not status.available:
        raise HTTPException(
            status_code=503,
            detail="Host agent is unavailable. Start ksylian-agent.service on the host.",
        )

    try:
        response = agent_post("/agent/actions/restart")
        response.raise_for_status()
    except Exception as error:
        append_log(f"agent restart failed: {error}")
        raise HTTPException(status_code=502, detail="Host agent restart failed") from error

    return current_agent_status()


@app.post("/api/servers", response_model=GameServer)
def create_server(payload: CreateServerRequest) -> GameServer:
    if AGENT_URL:
        try:
            response = agent_post("/servers", json={
                "name": payload.name,
                "type": payload.type,
                "version": payload.version,
                "min_ram": payload.min_ram,
                "max_ram": payload.max_ram,
                "java_runtime": payload.java_runtime,
                "jvm_args": payload.jvm_args,
                "cpu_limit": payload.cpu_limit,
                "loader_version": payload.loader_version,
                "installer_version": payload.installer_version,
                "install_fabric_api": payload.install_fabric_api,
            })
            response.raise_for_status()
            server = GameServer(**response.json())
            append_log(f"{server.name}: server provisioned by agent")
            return server
        except Exception as error:
            append_log(f"agent create failed for {payload.name}: {error}")
            raise HTTPException(status_code=502, detail="Host agent create failed") from error

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
        state=ServerState.stopped,
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
        try:
            response = agent_delete(f"/servers/{server_id}")
            response.raise_for_status()
            append_log(f"{server_id}: server stopped, disabled and hidden from panel")
            return response.json()
        except Exception as error:
            append_log(f"agent delete failed for {server_id}: {error}")
            raise HTTPException(status_code=502, detail="Host agent delete failed") from error

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
        server.state = ServerState.running
        server.cpu = max(server.cpu, 12)
        server.ram = server.ram if not server.ram.startswith("0 /") else "1.4 / 10 GB"
        message = f"{server.name}: start requested"
    elif action == ServerAction.restart:
        server.state = ServerState.starting
        server.cpu = max(server.cpu, 22)
        message = f"{server.name}: restart requested"
    elif action == ServerAction.stop:
        server.state = ServerState.stopped
        server.players = "0 / 48" if server.id == "ksy-vanilla" else "0 / 32"
        server.cpu = 0
        message = f"{server.name}: stop requested"
    elif action == ServerAction.kill:
        server.state = ServerState.stopped
        server.players = "0 / 48" if server.id == "ksy-vanilla" else "0 / 32"
        server.cpu = 0
        message = f"{server.name}: force stop requested"
    elif action == ServerAction.update:
        server.state = ServerState.updating
        message = f"{server.name}: update requested"
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
    require_agent_available()
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
        require_agent_available()
        return []

    get_server(server_id)
    return [line for line in logs[-80:] if server_id in line or "Server thread" in line]


@app.get("/api/servers/{server_id}/logs/download")
def download_server_logs(server_id: str) -> PlainTextResponse:
    if AGENT_URL:
        full_logs = load_agent_full_logs(server_id)
        if full_logs:
            return PlainTextResponse(
                "\n".join(full_logs) + "\n",
                headers={"Content-Disposition": f'attachment; filename="{server_id}-logs.txt"'},
            )
        agent_servers = load_agent_servers()
        if agent_servers is not None and all(server.id != server_id for server in agent_servers):
            raise HTTPException(status_code=404, detail="Server not found")
        require_agent_available()
        return PlainTextResponse("", headers={"Content-Disposition": f'attachment; filename="{server_id}-logs.txt"'})

    get_server(server_id)
    content = "\n".join(line for line in logs if server_id in line or "Server thread" in line)
    return PlainTextResponse(
        content + ("\n" if content else ""),
        headers={"Content-Disposition": f'attachment; filename="{server_id}-logs.txt"'},
    )


@app.websocket("/api/servers/{server_id}/logs/ws")
async def stream_server_logs(websocket: WebSocket, server_id: str, token: str = "") -> None:
    if not user_from_token(token):
        await websocket.close(code=1008)
        return

    await websocket.accept()
    sent: list[str] = []
    try:
        while True:
            current_logs = load_agent_logs(server_id) if AGENT_URL else [
                line for line in logs[-120:] if server_id in line or "Server thread" in line
            ]
            if current_logs != sent:
                await websocket.send_json({"lines": current_logs[-240:]})
                sent = current_logs
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        return


@app.get("/api/servers/{server_id}/crash-reports", response_model=list[CrashReportItem])
def list_server_crash_reports(server_id: str) -> list[CrashReportItem]:
    if AGENT_URL:
        agent_reports = load_agent_crash_reports(server_id)
        if agent_reports:
            return agent_reports
        agent_servers = load_agent_servers()
        if agent_servers is not None and all(server.id != server_id for server in agent_servers):
            raise HTTPException(status_code=404, detail="Server not found")
        require_agent_available()
        return []

    get_server(server_id)
    return []


@app.get("/api/servers/{server_id}/config", response_model=ServerConfigPayload)
def get_server_config(server_id: str) -> ServerConfigPayload:
    if AGENT_URL:
        try:
            response = agent_get(f"/servers/{server_id}/config")
            response.raise_for_status()
            return ServerConfigPayload(**response.json())
        except Exception as error:
            append_log(f"agent config read failed for {server_id}: {error}")
            raise HTTPException(status_code=502, detail="Host agent config read failed") from error

    server = get_server(server_id)
    return ServerConfigPayload(
        content="\n".join(
            [
                f"server-port={server.address.rsplit(':', 1)[-1]}",
                f"motd={server.name}",
                "online-mode=true",
                "max-players=20",
                "view-distance=10",
                "",
            ]
        )
    )


@app.put("/api/servers/{server_id}/config", response_model=ServerConfigPayload)
def update_server_config(server_id: str, payload: ServerConfigPayload) -> ServerConfigPayload:
    if AGENT_URL:
        try:
            response = agent_put(f"/servers/{server_id}/config", json=payload.model_dump())
            response.raise_for_status()
            append_log(f"{server_id}: server.properties updated")
            return ServerConfigPayload(**response.json())
        except Exception as error:
            append_log(f"agent config save failed for {server_id}: {error}")
            raise HTTPException(status_code=502, detail="Host agent config save failed") from error

    get_server(server_id)
    append_log(f"{server_id}: server.properties draft updated")
    return payload


@app.get("/api/servers/{server_id}/rcon/status")
def get_server_rcon_status(server_id: str) -> dict[str, bool]:
    if AGENT_URL:
        return agent_rcon_status(server_id)
    get_server(server_id)
    return {"available": False}


@app.post("/api/servers/{server_id}/rcon/command", response_model=RconCommandResult)
def send_server_rcon_command(server_id: str, payload: RconCommandPayload) -> RconCommandResult:
    command = payload.command.strip()
    if not command:
        raise HTTPException(status_code=400, detail="RCON command is required")
    if AGENT_URL:
        try:
            result = agent_rcon_command(server_id, command)
            append_log(f"{server_id}: rcon command executed")
            return result
        except Exception as error:
            append_log(f"agent rcon command failed for {server_id}: {error}")
            raise HTTPException(status_code=502, detail="Host agent RCON command failed") from error
    get_server(server_id)
    return RconCommandResult(ok=False, output="RCON is unavailable in local demo mode")


@app.get("/api/backups", response_model=list[BackupItem])
def list_backups() -> list[BackupItem]:
    agent_backups = load_agent_backups()
    if agent_backups is not None:
        return agent_backups
    require_agent_available()
    return backups


@app.post("/api/backups", response_model=BackupItem)
def create_backup(server_id: str = "ksy-vanilla", payload: BackupRequest | None = None) -> BackupItem:
    if AGENT_URL:
        try:
            backup = agent_create_backup(server_id, payload or BackupRequest())
            append_log(f"{server_id}: backup created")
            return backup
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


@app.post("/api/servers/{server_id}/restore", response_model=ActionResult)
def restore_backup(server_id: str, payload: RestoreRequest) -> ActionResult:
    if not AGENT_URL:
        raise HTTPException(status_code=409, detail="Host agent is required for restore")
    try:
        return agent_restore_backup(server_id, payload)
    except Exception as error:
        append_log(f"agent restore failed for {server_id}: {error}")
        raise HTTPException(status_code=502, detail="Host agent restore failed") from error


@app.get("/api/servers/{server_id}/files", response_model=FileListPayload)
def list_server_files(server_id: str, path: str = "") -> FileListPayload:
    if not AGENT_URL:
        return FileListPayload(path=path, entries=[])
    try:
        return agent_list_files(server_id, path)
    except Exception as error:
        append_log(f"agent files unavailable for {server_id}: {error}")
        raise HTTPException(status_code=502, detail="Host agent file manager failed") from error


@app.get("/api/servers/{server_id}/files/content", response_model=FileContentPayload)
def read_server_file(server_id: str, path: str) -> FileContentPayload:
    if not AGENT_URL:
        raise HTTPException(status_code=409, detail="Host agent is required for file content")
    try:
        return agent_read_file(server_id, path)
    except Exception as error:
        append_log(f"agent file read failed for {server_id}: {error}")
        raise HTTPException(status_code=502, detail="Host agent file read failed") from error


@app.get("/api/servers/{server_id}/files/search", response_model=list[FileSearchResult])
def search_server_files(server_id: str, query: str, path: str = "") -> list[FileSearchResult]:
    if not AGENT_URL:
        return []
    try:
        return agent_search_files(server_id, query, path)
    except Exception as error:
        append_log(f"agent file search failed for {server_id}: {error}")
        raise HTTPException(status_code=502, detail="Host agent file search failed") from error


@app.put("/api/servers/{server_id}/files", response_model=FileEntry)
def write_server_file(server_id: str, payload: FileWriteRequest) -> FileEntry:
    if not AGENT_URL:
        raise HTTPException(status_code=409, detail="Host agent is required for file writes")
    try:
        return agent_write_file(server_id, payload)
    except Exception as error:
        append_log(f"agent file write failed for {server_id}: {error}")
        raise HTTPException(status_code=502, detail="Host agent file write failed") from error


@app.post("/api/servers/{server_id}/files/actions")
def server_file_action(server_id: str, payload: FileOperationRequest) -> FileEntry | dict[str, bool]:
    if not AGENT_URL:
        raise HTTPException(status_code=409, detail="Host agent is required for file actions")
    try:
        return agent_file_action(server_id, payload)
    except Exception as error:
        append_log(f"agent file action failed for {server_id}: {error}")
        raise HTTPException(status_code=502, detail="Host agent file action failed") from error


@app.get("/api/servers/{server_id}/mods", response_model=list[InstalledModItem])
def list_server_mods(server_id: str) -> list[InstalledModItem]:
    if not AGENT_URL:
        return []
    try:
        return agent_list_mods(server_id)
    except Exception as error:
        append_log(f"agent mods unavailable for {server_id}: {error}")
        raise HTTPException(status_code=502, detail="Host agent mod scanner failed") from error


@app.post("/api/servers/{server_id}/mods", response_model=InstalledModItem)
def install_server_mod(server_id: str, payload: ModInstallRequest) -> InstalledModItem:
    if not AGENT_URL:
        raise HTTPException(status_code=409, detail="Host agent is required for mod install")
    try:
        return agent_install_mod(server_id, payload)
    except Exception as error:
        append_log(f"agent mod install failed for {server_id}: {error}")
        raise HTTPException(status_code=502, detail="Host agent mod install failed") from error


@app.post("/api/servers/{server_id}/mods/bulk", response_model=list[InstalledModItem])
def bulk_install_server_mods(server_id: str, payload: ModBulkInstallRequest) -> list[InstalledModItem]:
    if not AGENT_URL:
        raise HTTPException(status_code=409, detail="Host agent is required for bulk mod install")
    try:
        return agent_bulk_install_mods(server_id, payload)
    except Exception as error:
        append_log(f"agent bulk mod install failed for {server_id}: {error}")
        raise HTTPException(status_code=502, detail="Host agent bulk mod install failed") from error


@app.post("/api/servers/{server_id}/mods/actions")
def server_mod_action(server_id: str, payload: ModOperationRequest) -> dict[str, bool]:
    if not AGENT_URL:
        raise HTTPException(status_code=409, detail="Host agent is required for mod actions")
    try:
        return agent_mod_action(server_id, payload)
    except Exception as error:
        append_log(f"agent mod action failed for {server_id}: {error}")
        raise HTTPException(status_code=502, detail="Host agent mod action failed") from error


@app.post("/api/servers/{server_id}/mods/bulk-actions")
def server_mod_bulk_action(server_id: str, payload: ModBulkActionRequest) -> dict[str, int]:
    if not AGENT_URL:
        raise HTTPException(status_code=409, detail="Host agent is required for bulk mod actions")
    try:
        return agent_bulk_mod_action(server_id, payload)
    except Exception as error:
        append_log(f"agent bulk mod action failed for {server_id}: {error}")
        raise HTTPException(status_code=502, detail="Host agent bulk mod action failed") from error


@app.get("/api/loaders/{loader_type}/versions", response_model=list[str])
def loader_versions(loader_type: Literal["forge", "neoforge", "fabric", "vanilla", "paper", "purpur"]) -> list[str]:
    if not AGENT_URL:
        return []
    try:
        return agent_loader_versions(loader_type)
    except Exception as error:
        append_log(f"agent loader versions failed for {loader_type}: {error}")
        raise HTTPException(status_code=502, detail="Host agent loader versions failed") from error


@app.get("/api/loaders/fabric/installers", response_model=list[str])
def fabric_installer_versions() -> list[str]:
    if not AGENT_URL:
        return []
    try:
        return agent_fabric_installer_versions()
    except Exception as error:
        append_log(f"agent fabric installer versions failed: {error}")
        raise HTTPException(status_code=502, detail="Host agent fabric installer versions failed") from error


@app.get("/api/settings", response_model=SettingsPayload)
def get_settings() -> SettingsPayload:
    key = curseforge_api_key()
    return SettingsPayload(
        has_curseforge_api_key=bool(key),
        curseforge_api_key_mask=mask_secret(key),
        agent=current_agent_status(),
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
        agent=current_agent_status(),
    )


@app.get("/api/update/status", response_model=UpdateStatusPayload)
def get_update_status() -> UpdateStatusPayload:
    return update_status_payload()


@app.post("/api/update/apply", response_model=ApplyUpdateResult)
def apply_update(payload: ApplyUpdateRequest) -> ApplyUpdateResult:
    status = update_status_payload()
    target_version = payload.target_version.strip() or status.latest_version
    if not target_version:
        raise HTTPException(status_code=409, detail="No release tag is available")
    if not AGENT_URL:
        raise HTTPException(status_code=409, detail="Host agent is not configured")
    if status.updater_status != "ready":
        raise HTTPException(status_code=503, detail="Updater is not ready")

    try:
        response = agent_post("/app/update", json={"target_version": target_version})
        response.raise_for_status()
        data = response.json()
    except Exception as error:
        append_log(f"app update failed: {error}")
        raise HTTPException(status_code=502, detail="Host agent update failed") from error

    append_log(f"app update queued: {target_version}")
    return ApplyUpdateResult(
        ok=bool(data.get("ok", True)) if isinstance(data, dict) else True,
        message=str(data.get("message") or "Обновление запущено") if isinstance(data, dict) else "Обновление запущено",
        target_version=target_version,
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
