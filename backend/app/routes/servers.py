from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse

from ..auth import user_from_token
from ..schemas import (
    ActionResult,
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
    InstalledModItem,
    ModBulkActionRequest,
    ModBulkInstallRequest,
    ModInstallRequest,
    ModOperationRequest,
    PlayerActionRequest,
    PlayerActionResult,
    PlayerListPayload,
    RconCommandPayload,
    RconCommandResult,
    RestoreRequest,
    ImportServerPreview,
    ImportServerRequest,
    SafeUpdateRequest,
    SafeUpdateResult,
    ServerAction,
    ServerConfigPayload,
    ServerState,
)
from ..settings import AGENT_URL


def create_servers_router(
    *,
    append_log: Callable[[str], None],
    get_server: Callable[[str], GameServer],
    require_agent_available: Callable[[], None],
    load_agent_servers: Callable[[], list[GameServer] | None],
    load_agent_logs: Callable[[str], list[str]],
    load_agent_full_logs: Callable[[str], list[str]],
    load_agent_crash_reports: Callable[[str], list[CrashReportItem]],
    load_agent_backups: Callable[[], list[BackupItem] | None],
    agent_rcon_status: Callable[[str], dict[str, bool]],
    agent_rcon_command: Callable[[str, str], RconCommandResult],
    agent_create_backup: Callable[[str, BackupRequest], BackupItem],
    agent_restore_backup: Callable[[str, RestoreRequest], ActionResult],
    agent_list_files: Callable[[str, str], FileListPayload],
    agent_read_file: Callable[[str, str], FileContentPayload],
    agent_search_files: Callable[[str, str, str], list[FileSearchResult]],
    agent_write_file: Callable[[str, FileWriteRequest], FileEntry],
    agent_file_action: Callable[[str, FileOperationRequest], FileEntry | dict[str, bool]],
    agent_list_mods: Callable[[str], list[InstalledModItem]],
    agent_install_mod: Callable[[str, ModInstallRequest], InstalledModItem],
    agent_bulk_install_mods: Callable[[str, ModBulkInstallRequest], list[InstalledModItem]],
    agent_mod_action: Callable[[str, ModOperationRequest], dict[str, bool]],
    agent_bulk_mod_action: Callable[[str, ModBulkActionRequest], dict[str, int]],
    agent_loader_versions: Callable[[str], list[str]],
    agent_fabric_installer_versions: Callable[[], list[str]],
    agent_client,
    logs: list[str],
    backups: list[BackupItem],
    servers: dict[str, GameServer],
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/servers", response_model=GameServer)
    def create_server(payload: CreateServerRequest) -> GameServer:
        if AGENT_URL:
            try:
                server = agent_client.create_server(payload)
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


    @router.post("/api/servers/import/preview", response_model=ImportServerPreview)
    def preview_import_server(payload: ImportServerRequest) -> ImportServerPreview:
        if not AGENT_URL:
            raise HTTPException(status_code=409, detail="Host agent is required for server import")
        try:
            return agent_client.preview_import_server(payload)
        except Exception as error:
            append_log(f"agent import preview failed for {payload.path}: {error}")
            raise HTTPException(status_code=502, detail="Host agent import preview failed") from error


    @router.post("/api/servers/import", response_model=ActionResult)
    def import_existing_server(payload: ImportServerRequest) -> ActionResult:
        if not AGENT_URL:
            raise HTTPException(status_code=409, detail="Host agent is required for server import")
        try:
            result = agent_client.import_server(payload)
            append_log(result.message)
            return result
        except Exception as error:
            append_log(f"agent import failed for {payload.path}: {error}")
            raise HTTPException(status_code=502, detail="Host agent import failed") from error

    @router.post("/api/servers/import/archive", response_model=ActionResult)
    async def import_server_archive(
        name: str = Form(default=""),
        min_ram: str = Form(default="1G"),
        max_ram: str = Form(default="2G"),
        java_runtime: str = Form(default="auto"),
        jvm_args: str = Form(default=""),
        cpu_limit: int = Form(default=100),
        loader_version: str = Form(default=""),
        archive: UploadFile = File(...),
    ) -> ActionResult:
        if not AGENT_URL:
            raise HTTPException(status_code=409, detail="Host agent is required for server import")
        payload = ImportServerRequest(
            name=name,
            path="",
            keep_current_path=False,
            min_ram=min_ram,
            max_ram=max_ram,
            java_runtime=java_runtime,
            jvm_args=jvm_args,
            cpu_limit=cpu_limit,
            loader_version=loader_version,
        )
        try:
            result = agent_client.import_server_archive(payload, archive.filename or "server.tar", archive.file)
            append_log(result.message)
            return result
        except Exception as error:
            append_log(f"agent archive import failed for {archive.filename}: {error}")
            raise HTTPException(status_code=502, detail="Host agent archive import failed") from error
        finally:
            await archive.close()


    @router.delete("/api/servers/{server_id}")
    def delete_server(server_id: str) -> dict[str, bool]:
        if AGENT_URL:
            try:
                result = agent_client.delete_server(server_id)
                append_log(f"{server_id}: server stopped, disabled and deleted with files")
                return result
            except Exception as error:
                append_log(f"agent delete failed for {server_id}: {error}")
                raise HTTPException(status_code=502, detail="Host agent delete failed") from error

        if server_id not in servers:
            raise HTTPException(status_code=404, detail="Server not found")
        del servers[server_id]
        append_log(f"{server_id}: server draft deleted")
        return {"ok": True}


    @router.post("/api/servers/{server_id}/actions/{action}", response_model=ActionResult)
    def run_server_action(server_id: str, action: ServerAction) -> ActionResult:
        if AGENT_URL:
            try:
                result = agent_client.server_action(server_id, action)
                append_log(result.message)
                return result
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


    @router.get("/api/logs", response_model=list[str])
    def list_logs() -> list[str]:
        agent_servers = load_agent_servers()
        if agent_servers:
            real_logs: list[str] = []
            for server in agent_servers:
                real_logs.extend(load_agent_logs(server.id)[-40:])
            return real_logs[-80:] if real_logs else logs[-80:]
        require_agent_available()
        return logs[-80:]


    @router.get("/api/servers/{server_id}/logs", response_model=list[str])
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


    @router.get("/api/servers/{server_id}/logs/download")
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


    @router.websocket("/api/servers/{server_id}/logs/ws")
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


    @router.get("/api/servers/{server_id}/crash-reports", response_model=list[CrashReportItem])
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


    @router.get("/api/servers/{server_id}/config", response_model=ServerConfigPayload)
    def get_server_config(server_id: str) -> ServerConfigPayload:
        if AGENT_URL:
            try:
                return agent_client.server_config(server_id)
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


    @router.put("/api/servers/{server_id}/config", response_model=ServerConfigPayload)
    def update_server_config(server_id: str, payload: ServerConfigPayload) -> ServerConfigPayload:
        if AGENT_URL:
            try:
                updated = agent_client.update_server_config(server_id, payload)
                append_log(f"{server_id}: server.properties updated")
                return updated
            except Exception as error:
                append_log(f"agent config save failed for {server_id}: {error}")
                raise HTTPException(status_code=502, detail="Host agent config save failed") from error

        get_server(server_id)
        append_log(f"{server_id}: server.properties draft updated")
        return payload


    @router.get("/api/servers/{server_id}/rcon/status")
    def get_server_rcon_status(server_id: str) -> dict[str, bool]:
        if AGENT_URL:
            return agent_rcon_status(server_id)
        get_server(server_id)
        return {"available": False}


    @router.post("/api/servers/{server_id}/rcon/command", response_model=RconCommandResult)
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


    @router.get("/api/servers/{server_id}/players", response_model=PlayerListPayload)
    def list_game_players(server_id: str) -> PlayerListPayload:
        if not AGENT_URL:
            get_server(server_id)
            return PlayerListPayload(online=[], known=[], history=[], rcon_available=False)
        try:
            return agent_client.players(server_id)
        except Exception as error:
            append_log(f"agent players unavailable for {server_id}: {error}")
            raise HTTPException(status_code=502, detail="Host agent player manager failed") from error


    @router.post("/api/servers/{server_id}/players/actions", response_model=PlayerActionResult)
    def run_player_action(server_id: str, payload: PlayerActionRequest) -> PlayerActionResult:
        if not AGENT_URL:
            raise HTTPException(status_code=409, detail="Host agent is required for player actions")
        try:
            result = agent_client.player_action(server_id, payload)
            append_log(f"{server_id}: player action {payload.action} for {payload.player}")
            return result
        except Exception as error:
            append_log(f"agent player action failed for {server_id}: {error}")
            raise HTTPException(status_code=502, detail="Host agent player action failed") from error


    @router.get("/api/backups", response_model=list[BackupItem])
    def list_backups() -> list[BackupItem]:
        agent_backups = load_agent_backups()
        if agent_backups is not None:
            return agent_backups
        require_agent_available()
        return backups


    @router.post("/api/backups", response_model=BackupItem)
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


    @router.post("/api/servers/{server_id}/restore", response_model=ActionResult)
    def restore_backup(server_id: str, payload: RestoreRequest) -> ActionResult:
        if not AGENT_URL:
            raise HTTPException(status_code=409, detail="Host agent is required for restore")
        try:
            return agent_restore_backup(server_id, payload)
        except Exception as error:
            append_log(f"agent restore failed for {server_id}: {error}")
            raise HTTPException(status_code=502, detail="Host agent restore failed") from error


    @router.get("/api/servers/{server_id}/files", response_model=FileListPayload)
    def list_server_files(server_id: str, path: str = "") -> FileListPayload:
        if not AGENT_URL:
            return FileListPayload(path=path, entries=[])
        try:
            return agent_list_files(server_id, path)
        except Exception as error:
            append_log(f"agent files unavailable for {server_id}: {error}")
            raise HTTPException(status_code=502, detail="Host agent file manager failed") from error


    @router.get("/api/servers/{server_id}/files/content", response_model=FileContentPayload)
    def read_server_file(server_id: str, path: str) -> FileContentPayload:
        if not AGENT_URL:
            raise HTTPException(status_code=409, detail="Host agent is required for file content")
        try:
            return agent_read_file(server_id, path)
        except Exception as error:
            append_log(f"agent file read failed for {server_id}: {error}")
            raise HTTPException(status_code=502, detail="Host agent file read failed") from error


    @router.get("/api/servers/{server_id}/files/search", response_model=list[FileSearchResult])
    def search_server_files(server_id: str, query: str, path: str = "") -> list[FileSearchResult]:
        if not AGENT_URL:
            return []
        try:
            return agent_search_files(server_id, query, path)
        except Exception as error:
            append_log(f"agent file search failed for {server_id}: {error}")
            raise HTTPException(status_code=502, detail="Host agent file search failed") from error


    @router.put("/api/servers/{server_id}/files", response_model=FileEntry)
    def write_server_file(server_id: str, payload: FileWriteRequest) -> FileEntry:
        if not AGENT_URL:
            raise HTTPException(status_code=409, detail="Host agent is required for file writes")
        try:
            return agent_write_file(server_id, payload)
        except Exception as error:
            append_log(f"agent file write failed for {server_id}: {error}")
            raise HTTPException(status_code=502, detail="Host agent file write failed") from error


    @router.post("/api/servers/{server_id}/files/actions")
    def server_file_action(server_id: str, payload: FileOperationRequest) -> FileEntry | dict[str, bool]:
        if not AGENT_URL:
            raise HTTPException(status_code=409, detail="Host agent is required for file actions")
        try:
            return agent_file_action(server_id, payload)
        except Exception as error:
            append_log(f"agent file action failed for {server_id}: {error}")
            raise HTTPException(status_code=502, detail="Host agent file action failed") from error


    @router.get("/api/servers/{server_id}/mods", response_model=list[InstalledModItem])
    def list_server_mods(server_id: str) -> list[InstalledModItem]:
        if not AGENT_URL:
            return []
        try:
            return agent_list_mods(server_id)
        except Exception as error:
            append_log(f"agent mods unavailable for {server_id}: {error}")
            raise HTTPException(status_code=502, detail="Host agent mod scanner failed") from error


    @router.get("/api/servers/{server_id}/manifest", response_model=BuildManifest)
    def get_server_manifest(server_id: str) -> BuildManifest:
        if not AGENT_URL:
            raise HTTPException(status_code=409, detail="Host agent is required for manifests")
        try:
            return agent_client.manifest(server_id)
        except Exception as error:
            append_log(f"agent manifest failed for {server_id}: {error}")
            raise HTTPException(status_code=502, detail="Host agent manifest failed") from error


    @router.post("/api/servers/{server_id}/manifest/refresh", response_model=BuildManifest)
    def refresh_server_manifest(server_id: str) -> BuildManifest:
        if not AGENT_URL:
            raise HTTPException(status_code=409, detail="Host agent is required for manifests")
        try:
            manifest = agent_client.refresh_manifest(server_id)
            append_log(f"{server_id}: manifest refreshed")
            return manifest
        except Exception as error:
            append_log(f"agent manifest refresh failed for {server_id}: {error}")
            raise HTTPException(status_code=502, detail="Host agent manifest refresh failed") from error


    @router.get("/api/servers/{server_id}/manifest/history", response_model=list[str])
    def get_server_manifest_history(server_id: str) -> list[str]:
        if not AGENT_URL:
            return []
        try:
            return agent_client.manifest_history(server_id)
        except Exception as error:
            append_log(f"agent manifest history failed for {server_id}: {error}")
            raise HTTPException(status_code=502, detail="Host agent manifest history failed") from error


    @router.post("/api/servers/{server_id}/manifest/diff", response_model=BuildManifestDiff)
    def diff_server_manifest(server_id: str, payload: BuildManifest) -> BuildManifestDiff:
        if not AGENT_URL:
            raise HTTPException(status_code=409, detail="Host agent is required for manifests")
        try:
            return agent_client.diff_manifest(server_id, payload)
        except Exception as error:
            append_log(f"agent manifest diff failed for {server_id}: {error}")
            raise HTTPException(status_code=502, detail="Host agent manifest diff failed") from error


    @router.post("/api/servers/{server_id}/manifest/import", response_model=BuildManifest)
    def import_server_manifest(server_id: str, payload: BuildImportRequest) -> BuildManifest:
        if not AGENT_URL:
            raise HTTPException(status_code=409, detail="Host agent is required for manifests")
        try:
            return agent_client.import_manifest(server_id, payload)
        except Exception as error:
            append_log(f"agent manifest import failed for {server_id}: {error}")
            raise HTTPException(status_code=502, detail="Host agent manifest import failed") from error


    @router.post("/api/servers/{server_id}/manifest/export")
    def export_server_manifest(server_id: str) -> dict[str, str]:
        if not AGENT_URL:
            raise HTTPException(status_code=409, detail="Host agent is required for manifests")
        try:
            return agent_client.export_manifest(server_id)
        except Exception as error:
            append_log(f"agent manifest export failed for {server_id}: {error}")
            raise HTTPException(status_code=502, detail="Host agent manifest export failed") from error


    @router.post("/api/servers/{server_id}/updates/plan", response_model=SafeUpdateResult)
    def plan_safe_update(server_id: str) -> SafeUpdateResult:
        if not AGENT_URL:
            raise HTTPException(status_code=409, detail="Host agent is required for safe updates")
        try:
            return agent_client.plan_safe_update(server_id)
        except Exception as error:
            append_log(f"agent safe update plan failed for {server_id}: {error}")
            raise HTTPException(status_code=502, detail="Host agent safe update plan failed") from error


    @router.post("/api/servers/{server_id}/updates/apply", response_model=SafeUpdateResult)
    def apply_safe_update(server_id: str, payload: SafeUpdateRequest) -> SafeUpdateResult:
        if not AGENT_URL:
            raise HTTPException(status_code=409, detail="Host agent is required for safe updates")
        try:
            return agent_client.apply_safe_update(server_id, payload)
        except Exception as error:
            append_log(f"agent safe update apply failed for {server_id}: {error}")
            raise HTTPException(status_code=502, detail="Host agent safe update apply failed") from error


    @router.post("/api/servers/{server_id}/mods", response_model=InstalledModItem)
    def install_server_mod(server_id: str, payload: ModInstallRequest) -> InstalledModItem:
        if not AGENT_URL:
            raise HTTPException(status_code=409, detail="Host agent is required for mod install")
        try:
            return agent_install_mod(server_id, payload)
        except Exception as error:
            append_log(f"agent mod install failed for {server_id}: {error}")
            raise HTTPException(status_code=502, detail="Host agent mod install failed") from error


    @router.post("/api/servers/{server_id}/mods/bulk", response_model=list[InstalledModItem])
    def bulk_install_server_mods(server_id: str, payload: ModBulkInstallRequest) -> list[InstalledModItem]:
        if not AGENT_URL:
            raise HTTPException(status_code=409, detail="Host agent is required for bulk mod install")
        try:
            return agent_bulk_install_mods(server_id, payload)
        except Exception as error:
            append_log(f"agent bulk mod install failed for {server_id}: {error}")
            raise HTTPException(status_code=502, detail="Host agent bulk mod install failed") from error


    @router.post("/api/servers/{server_id}/mods/actions")
    def server_mod_action(server_id: str, payload: ModOperationRequest) -> dict[str, bool]:
        if not AGENT_URL:
            raise HTTPException(status_code=409, detail="Host agent is required for mod actions")
        try:
            return agent_mod_action(server_id, payload)
        except Exception as error:
            append_log(f"agent mod action failed for {server_id}: {error}")
            raise HTTPException(status_code=502, detail="Host agent mod action failed") from error


    @router.post("/api/servers/{server_id}/mods/bulk-actions")
    def server_mod_bulk_action(server_id: str, payload: ModBulkActionRequest) -> dict[str, int]:
        if not AGENT_URL:
            raise HTTPException(status_code=409, detail="Host agent is required for bulk mod actions")
        try:
            return agent_bulk_mod_action(server_id, payload)
        except Exception as error:
            append_log(f"agent bulk mod action failed for {server_id}: {error}")
            raise HTTPException(status_code=502, detail="Host agent bulk mod action failed") from error


    @router.get("/api/loaders/{loader_type}/versions", response_model=list[str])
    def loader_versions(loader_type: Literal["forge", "neoforge", "fabric", "vanilla", "paper", "purpur"]) -> list[str]:
        if not AGENT_URL:
            return []
        try:
            return agent_loader_versions(loader_type)
        except Exception as error:
            append_log(f"agent loader versions failed for {loader_type}: {error}")
            raise HTTPException(status_code=502, detail="Host agent loader versions failed") from error


    @router.get("/api/loaders/fabric/installers", response_model=list[str])
    def fabric_installer_versions() -> list[str]:
        if not AGENT_URL:
            return []
        try:
            return agent_fabric_installer_versions()
        except Exception as error:
            append_log(f"agent fabric installer versions failed: {error}")
            raise HTTPException(status_code=502, detail="Host agent fabric installer versions failed") from error

    return router
