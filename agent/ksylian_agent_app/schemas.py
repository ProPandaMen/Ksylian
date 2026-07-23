from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AgentServer(BaseModel):
    id: str
    name: str
    pack: str
    version: str
    state: Literal["installing", "stopped", "starting", "running", "stopping", "crashed", "updating", "backing_up"]
    players: str
    ram: str
    cpu: int
    disk: str
    address: str
    exit_code: int | None = None
    last_event: str = ""
    warnings: list[str] = Field(default_factory=list)


class StoredServer(BaseModel):
    id: str
    name: str
    type: Literal["legacy", "vanilla", "paper", "purpur", "fabric", "forge", "neoforge"]
    pack: str
    version: str
    port: int
    service: str
    path: str
    backup_path: str
    address: str
    created_at: str
    managed: bool = False
    start_command: list[str] = Field(default_factory=list)
    min_ram: str = "1G"
    max_ram: str = "2G"
    java_runtime: str = "auto"
    jvm_args: list[str] = Field(default_factory=list)
    cpu_limit: int = 100
    loader_version: str = ""
    installer_version: str = ""
    install_fabric_api: bool = False
    rcon_port: int = 0
    rcon_password: str = ""


class CreateAgentServerRequest(BaseModel):
    name: str
    type: Literal["vanilla", "paper", "purpur", "fabric", "forge", "neoforge"]
    version: str = "1.20.1"
    min_ram: str = "1G"
    max_ram: str = "2G"
    java_runtime: str = "auto"
    jvm_args: str = ""
    cpu_limit: int = 100
    loader_version: str = ""
    installer_version: str = ""
    install_fabric_api: bool = False


class AgentActionResult(BaseModel):
    ok: bool
    message: str
    server: AgentServer


class ServerConfigPayload(BaseModel):
    content: str


class RconCommandPayload(BaseModel):
    command: str


class RconCommandResult(BaseModel):
    ok: bool
    output: str


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


class BackupItem(BaseModel):
    id: str
    name: str
    size: str
    created: str
    server_id: str
    checksum: str = ""
    description: str = ""
    manifest: str = ""


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


class AppUpdateRequest(BaseModel):
    target_version: str


class AppUpdateResult(BaseModel):
    ok: bool
    message: str
    target_version: str


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
    state: Literal["installing", "stopped", "starting", "running", "stopping", "crashed", "updating", "backing_up"]
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
