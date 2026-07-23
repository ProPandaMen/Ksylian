from __future__ import annotations

import httpx

from .schemas import (
    ActionResult,
    AgentStatus,
    BackupItem,
    BackupRequest,
    BuildImportRequest,
    BuildManifest,
    BuildManifestDiff,
    CreateServerRequest,
    CrashReportItem,
    FileContentPayload,
    FileEntry,
    FileListPayload,
    FileOperationRequest,
    FileSearchResult,
    FileWriteRequest,
    GameServer,
    HostMonitoring,
    InstalledModItem,
    ModBulkActionRequest,
    ModBulkInstallRequest,
    ModInstallRequest,
    ModOperationRequest,
    PlayerActionRequest,
    PlayerActionResult,
    PlayerListPayload,
    RconCommandResult,
    RestoreRequest,
    ImportServerPreview,
    ImportServerRequest,
    SafeUpdateRequest,
    SafeUpdateResult,
    ServerAction,
    ServerConfigPayload,
)


class AgentClient:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    @property
    def configured(self) -> bool:
        return bool(self.base_url)

    def headers(self) -> dict[str, str]:
        if not self.token:
            return {}
        return {"x-ksylian-token": self.token}

    def get(self, path: str, params: dict[str, str] | None = None) -> httpx.Response:
        self.require_configured()
        return httpx.get(f"{self.base_url}{path}", headers=self.headers(), params=params, timeout=10)

    def post(self, path: str, json: dict | None = None) -> httpx.Response:
        self.require_configured()
        return httpx.post(f"{self.base_url}{path}", headers=self.headers(), json=json, timeout=240)

    def put(self, path: str, json: dict | None = None) -> httpx.Response:
        self.require_configured()
        return httpx.put(f"{self.base_url}{path}", headers=self.headers(), json=json, timeout=30)

    def delete(self, path: str) -> httpx.Response:
        self.require_configured()
        return httpx.delete(f"{self.base_url}{path}", headers=self.headers(), timeout=90)

    def require_configured(self) -> None:
        if not self.configured:
            raise RuntimeError("Agent is not configured")

    def status(self) -> AgentStatus:
        if not self.configured:
            return AgentStatus(
                configured=False,
                available=False,
                status="not_configured",
                message="Host agent is not configured",
            )

        try:
            response = self.get("/health")
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

    def servers(self) -> list[GameServer]:
        response = self.get("/servers")
        response.raise_for_status()
        return [GameServer(**item) for item in response.json()]

    def logs(self, server_id: str, *, full: bool = False) -> list[str]:
        suffix = "/logs/full" if full else "/logs"
        response = self.get(f"/servers/{server_id}{suffix}")
        response.raise_for_status()
        return [str(line) for line in response.json()]

    def crash_reports(self, server_id: str) -> list[CrashReportItem]:
        response = self.get(f"/servers/{server_id}/crash-reports")
        response.raise_for_status()
        return [CrashReportItem(**item) for item in response.json()]

    def rcon_status(self, server_id: str) -> dict[str, bool]:
        response = self.get(f"/servers/{server_id}/rcon/status")
        response.raise_for_status()
        data = response.json()
        return {"available": bool(data.get("available"))}

    def rcon_command(self, server_id: str, command: str) -> RconCommandResult:
        response = self.post(f"/servers/{server_id}/rcon/command", json={"command": command})
        response.raise_for_status()
        return RconCommandResult(**response.json())

    def players(self, server_id: str) -> PlayerListPayload:
        response = self.get(f"/servers/{server_id}/players")
        response.raise_for_status()
        return PlayerListPayload(**response.json())

    def player_action(self, server_id: str, payload: PlayerActionRequest) -> PlayerActionResult:
        response = self.post(f"/servers/{server_id}/players/actions", json=payload.model_dump())
        response.raise_for_status()
        return PlayerActionResult(**response.json())

    def backups(self) -> list[BackupItem]:
        response = self.get("/backups")
        response.raise_for_status()
        return [BackupItem(**item) for item in response.json()]

    def create_backup(self, server_id: str, payload: BackupRequest) -> BackupItem:
        response = self.post(f"/servers/{server_id}/backups", json=payload.model_dump())
        response.raise_for_status()
        return BackupItem(**response.json())

    def restore_backup(self, server_id: str, payload: RestoreRequest) -> ActionResult:
        response = self.post(f"/servers/{server_id}/restore", json=payload.model_dump())
        response.raise_for_status()
        return ActionResult(**response.json())

    def files(self, server_id: str, path: str = "") -> FileListPayload:
        response = self.get(f"/servers/{server_id}/files", params={"path": path})
        response.raise_for_status()
        return FileListPayload(**response.json())

    def read_file(self, server_id: str, path: str) -> FileContentPayload:
        response = self.get(f"/servers/{server_id}/files/content", params={"path": path})
        response.raise_for_status()
        return FileContentPayload(**response.json())

    def search_files(self, server_id: str, query: str, path: str = "") -> list[FileSearchResult]:
        response = self.get(f"/servers/{server_id}/files/search", params={"query": query, "path": path})
        response.raise_for_status()
        return [FileSearchResult(**item) for item in response.json()]

    def write_file(self, server_id: str, payload: FileWriteRequest) -> FileEntry:
        response = self.put(f"/servers/{server_id}/files", json=payload.model_dump())
        response.raise_for_status()
        return FileEntry(**response.json())

    def file_action(self, server_id: str, payload: FileOperationRequest) -> FileEntry | dict[str, bool]:
        response = self.post(f"/servers/{server_id}/files/actions", json=payload.model_dump())
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict) and data.get("name"):
            return FileEntry(**data)
        return {"ok": True}

    def mods(self, server_id: str) -> list[InstalledModItem]:
        response = self.get(f"/servers/{server_id}/mods")
        response.raise_for_status()
        return [InstalledModItem(**item) for item in response.json()]

    def install_mod(self, server_id: str, payload: ModInstallRequest) -> InstalledModItem:
        response = self.post(f"/servers/{server_id}/mods", json=payload.model_dump())
        response.raise_for_status()
        return InstalledModItem(**response.json())

    def bulk_install_mods(self, server_id: str, payload: ModBulkInstallRequest) -> list[InstalledModItem]:
        response = self.post(f"/servers/{server_id}/mods/bulk", json=payload.model_dump())
        response.raise_for_status()
        return [InstalledModItem(**item) for item in response.json()]

    def mod_action(self, server_id: str, payload: ModOperationRequest) -> dict[str, bool]:
        response = self.post(f"/servers/{server_id}/mods/actions", json=payload.model_dump())
        response.raise_for_status()
        return {"ok": True}

    def bulk_mod_action(self, server_id: str, payload: ModBulkActionRequest) -> dict[str, int]:
        response = self.post(f"/servers/{server_id}/mods/bulk-actions", json=payload.model_dump())
        response.raise_for_status()
        return {"completed": int(response.json().get("completed", 0))}

    def loader_versions(self, loader_type: str) -> list[str]:
        response = self.get(f"/loaders/{loader_type}/versions")
        response.raise_for_status()
        return [str(item) for item in response.json()]

    def fabric_installer_versions(self) -> list[str]:
        response = self.get("/loaders/fabric/installers")
        response.raise_for_status()
        return [str(item) for item in response.json()]

    def monitoring(self) -> HostMonitoring:
        response = self.get("/monitoring")
        response.raise_for_status()
        return HostMonitoring(**response.json())

    def restart(self) -> None:
        response = self.post("/agent/actions/restart")
        response.raise_for_status()

    def create_server(self, payload: CreateServerRequest) -> GameServer:
        response = self.post(
            "/servers",
            json={
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
            },
        )
        response.raise_for_status()
        return GameServer(**response.json())

    def preview_import_server(self, payload: ImportServerRequest) -> ImportServerPreview:
        response = self.post("/servers/import/preview", json=payload.model_dump())
        response.raise_for_status()
        return ImportServerPreview(**response.json())

    def import_server(self, payload: ImportServerRequest) -> ActionResult:
        response = self.post("/servers/import", json=payload.model_dump())
        response.raise_for_status()
        return ActionResult(**response.json())

    def delete_server(self, server_id: str) -> dict[str, bool]:
        response = self.delete(f"/servers/{server_id}")
        response.raise_for_status()
        data = response.json()
        return {"ok": bool(data.get("ok", True))} if isinstance(data, dict) else {"ok": True}

    def server_action(self, server_id: str, action: ServerAction) -> ActionResult:
        response = self.post(f"/servers/{server_id}/actions/{action.value}")
        response.raise_for_status()
        return ActionResult(**response.json())

    def manifest(self, server_id: str) -> BuildManifest:
        response = self.get(f"/servers/{server_id}/manifest")
        response.raise_for_status()
        return BuildManifest(**response.json())

    def refresh_manifest(self, server_id: str) -> BuildManifest:
        response = self.post(f"/servers/{server_id}/manifest/refresh")
        response.raise_for_status()
        return BuildManifest(**response.json())

    def manifest_history(self, server_id: str) -> list[str]:
        response = self.get(f"/servers/{server_id}/manifest/history")
        response.raise_for_status()
        return [str(item) for item in response.json()]

    def diff_manifest(self, server_id: str, payload: BuildManifest) -> BuildManifestDiff:
        response = self.post(f"/servers/{server_id}/manifest/diff", json=payload.model_dump(by_alias=True))
        response.raise_for_status()
        return BuildManifestDiff(**response.json())

    def import_manifest(self, server_id: str, payload: BuildImportRequest) -> BuildManifest:
        response = self.post(f"/servers/{server_id}/manifest/import", json=payload.model_dump(by_alias=True))
        response.raise_for_status()
        return BuildManifest(**response.json())

    def export_manifest(self, server_id: str) -> dict[str, str]:
        response = self.post(f"/servers/{server_id}/manifest/export")
        response.raise_for_status()
        data = response.json()
        return {"path": str(data.get("path") or ""), "name": str(data.get("name") or "")}

    def plan_safe_update(self, server_id: str) -> SafeUpdateResult:
        response = self.post(f"/servers/{server_id}/updates/plan")
        response.raise_for_status()
        return SafeUpdateResult(**response.json())

    def apply_safe_update(self, server_id: str, payload: SafeUpdateRequest) -> SafeUpdateResult:
        response = self.post(f"/servers/{server_id}/updates/apply", json=payload.model_dump(by_alias=True))
        response.raise_for_status()
        return SafeUpdateResult(**response.json())

    def server_config(self, server_id: str) -> ServerConfigPayload:
        response = self.get(f"/servers/{server_id}/config")
        response.raise_for_status()
        return ServerConfigPayload(**response.json())

    def update_server_config(self, server_id: str, payload: ServerConfigPayload) -> ServerConfigPayload:
        response = self.put(f"/servers/{server_id}/config", json=payload.model_dump())
        response.raise_for_status()
        return ServerConfigPayload(**response.json())

    def apply_update(self, target_version: str) -> dict:
        response = self.post("/app/update", json={"target_version": target_version})
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {}
