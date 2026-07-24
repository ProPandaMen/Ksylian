from __future__ import annotations

from enum import Enum
from typing import Literal

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


class ServerOperationProgress(BaseModel):
    kind: Literal["curseforge_install"] = "curseforge_install"
    label: str = "Установка"
    current: int = 0
    total: int = 0
    percent: int = 0
    current_item: str = ""
    message: str = ""


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
    operation: ServerOperationProgress | None = None


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
    curseforge_api_key_status: Literal["missing", "valid", "invalid", "unchecked"] = "missing"
    curseforge_api_key_message: str = ""
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
    disabled_at: str = ""


class MonitoringLayoutPreference(BaseModel):
    version: int = 1
    blocks: list[str] = []


class UserPreferences(BaseModel):
    monitoring_layout: MonitoringLayoutPreference | None = None


class AuthSessionPayload(BaseModel):
    token: str
    user: AuthUser


class ThemeUpdateRequest(BaseModel):
    theme: ThemeName


class PreferencesUpdateRequest(BaseModel):
    monitoring_layout: MonitoringLayoutPreference | None = None


class UserInvite(BaseModel):
    id: str
    token: str
    role: UserRole = "member"
    created_at: str
    expires_at: str
    used_at: str = ""
    revoked_at: str = ""
    invited_by: str = ""


class CreateInviteRequest(BaseModel):
    role: UserRole = "member"
    ttl_hours: int = 24


class UpdateUserRequest(BaseModel):
    role: UserRole | None = None
    disabled_at: str | None = None


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


class CurseForgeFileDependency(BaseModel):
    mod_id: int
    relation_type: int
    required: bool = True


class CurseForgeFile(BaseModel):
    id: int
    mod_id: int
    display_name: str
    file_name: str
    download_url: str = ""
    release_type: Literal["release", "beta", "alpha", "unknown"] = "unknown"
    game_versions: list[str] = Field(default_factory=list)
    dependencies: list[CurseForgeFileDependency] = Field(default_factory=list)
    file_date: str = ""
    file_length: int = 0
    hashes: dict[str, str] = Field(default_factory=dict)
    restricted: bool = False


class CurseForgeFilesPayload(BaseModel):
    items: list[CurseForgeFile]
    has_api_key: bool


class CurseForgeModpackSummary(BaseModel):
    mod_count: int = 0
    available: bool = False


class CurseForgeInstallRequest(BaseModel):
    server_id: str
    project_id: int
    file_id: int
    include_dependencies: bool = True


class CurseForgeInstallResult(BaseModel):
    ok: bool
    message: str
    installed: list[InstalledModItem] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)


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
    source: Literal["curseforge", "manual", "imported", "unknown"] = "manual"
    project_id: str = ""
    file_id: str = ""


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


class BuildManifestMod(BaseModel):
    id: str
    name: str
    version: str = ""
    loader: Literal["fabric", "forge", "neoforge", "unknown"] = "unknown"
    side: Literal["client", "server", "both", "unknown"] = "unknown"
    filename: str
    path: str
    sha256: str
    source: Literal["curseforge", "manual", "imported", "unknown"] = "unknown"
    project_id: str = ""
    file_id: str = ""
    installed_at: str = ""
    dependencies: list[ModDependency] = Field(default_factory=list)


class BuildManifest(BaseModel):
    schema_version: int = Field(default=1, alias="schema")
    server_id: str
    server_name: str
    minecraft_version: str
    loader: Literal["legacy", "vanilla", "paper", "purpur", "fabric", "forge", "neoforge"]
    loader_version: str = ""
    java_runtime: str = "auto"
    generated_at: str
    mods: list[BuildManifestMod] = Field(default_factory=list)
    manual_changes: list[str] = Field(default_factory=list)


class BuildManifestDiff(BaseModel):
    added: list[BuildManifestMod] = Field(default_factory=list)
    removed: list[BuildManifestMod] = Field(default_factory=list)
    changed: list[dict[str, BuildManifestMod]] = Field(default_factory=list)


class BuildImportRequest(BaseModel):
    manifest: BuildManifest
    mode: Literal["merge", "replace"] = "merge"


class ModUpdatePlanItem(BaseModel):
    current: BuildManifestMod
    candidate: BuildManifestMod
    action: Literal["update", "keep"] = "keep"
    reason: str = ""
    content: str = ""
    encoding: Literal["base64"] = "base64"


class ModUpdatePlan(BaseModel):
    server_id: str
    created_at: str
    items: list[ModUpdatePlanItem] = Field(default_factory=list)
    diff: BuildManifestDiff = Field(default_factory=BuildManifestDiff)
    warnings: list[str] = Field(default_factory=list)


class SafeUpdateRequest(BaseModel):
    plan: ModUpdatePlan | None = None
    timeout_seconds: int = 180
    apply: bool = False


class SafeUpdateResult(BaseModel):
    ok: bool
    message: str
    plan: ModUpdatePlan
    backup_id: str = ""
    test_instance_path: str = ""
    log_findings: list[str] = Field(default_factory=list)


class ImportServerRequest(BaseModel):
    name: str
    path: str
    keep_current_path: bool = True
    min_ram: str = "1G"
    max_ram: str = "2G"
    java_runtime: str = "auto"
    jvm_args: str = ""
    cpu_limit: int = 100
    loader_version: str = ""


class ImportServerPreview(BaseModel):
    ok: bool
    name: str
    path: str
    type: Literal["legacy", "vanilla", "paper", "purpur", "fabric", "forge", "neoforge"]
    version: str = ""
    loader_version: str = ""
    java_runtime: str = "auto"
    port: int = 25565
    has_server_properties: bool = False
    mod_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class ServerConfigPayload(BaseModel):
    content: str


class RconCommandPayload(BaseModel):
    command: str


class RconCommandResult(BaseModel):
    ok: bool
    output: str


class GamePlayer(BaseModel):
    name: str
    uuid: str = ""
    online: bool = False
    ping: str = ""
    game_time: str = ""
    last_seen: str = ""
    whitelisted: bool = False
    operator: bool = False
    banned: bool = False
    ip_banned: bool = False
    luckperms_groups: list[str] = Field(default_factory=list)


class PlayerHistoryItem(BaseModel):
    at: str
    player: str
    action: str
    detail: str = ""
    actor: str = "ksylian"


class PlayerListPayload(BaseModel):
    online: list[GamePlayer]
    known: list[GamePlayer]
    history: list[PlayerHistoryItem]
    rcon_available: bool
    game_time: str = ""


class PlayerActionRequest(BaseModel):
    action: Literal[
        "whitelist_add",
        "whitelist_remove",
        "op",
        "deop",
        "ban",
        "pardon",
        "ban_ip",
        "pardon_ip",
        "kick",
        "message",
        "luckperms_group_add",
        "luckperms_group_remove",
        "luckperms_permission_set",
        "luckperms_permission_unset",
    ]
    player: str
    value: str = ""
    reason: str = ""


class PlayerActionResult(BaseModel):
    ok: bool
    message: str
    output: str = ""
    players: PlayerListPayload


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


class MonitoringDiskPoint(BaseModel):
    mount: str
    percent: int
    used: int
    total: int


class MonitoringServicesPoint(BaseModel):
    running: int
    total: int
    unhealthy: list[str] = []


class MonitoringTopProcessPoint(BaseModel):
    pid: int
    name: str
    cpu: float
    memory: float


class MonitoringHistoryPoint(BaseModel):
    timestamp: int
    collected_at: str
    cpu: int
    memory: int
    swap: int
    temperature: float | None = None
    load_average: list[float]
    disks: list[MonitoringDiskPoint] = []
    services: MonitoringServicesPoint
    top_process: MonitoringTopProcessPoint | None = None


class MonitoringHistoryPayload(BaseModel):
    window: str
    sample_seconds: int
    retention_hours: int
    points: list[MonitoringHistoryPoint]
    error: str | None = None


class DashboardPayload(BaseModel):
    servers: list[GameServer]
    logs: list[str]
    backups: list[BackupItem]
    mods: list[ModItem]
    files: list[FileItem]
    agent: AgentStatus
