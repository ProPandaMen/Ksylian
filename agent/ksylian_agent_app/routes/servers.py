from __future__ import annotations

import shutil
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Header, HTTPException

from ..schemas import (
    AgentActionResult,
    AgentServer,
    BackupItem,
    BackupRequest,
    BuildImportRequest,
    BuildManifest,
    BuildManifestDiff,
    CreateAgentServerRequest,
    CrashReportItem,
    FileContentPayload,
    FileEntry,
    FileListPayload,
    FileOperationRequest,
    FileSearchResult,
    FileWriteRequest,
    InstalledModItem,
    ModBulkActionRequest,
    ModBulkInstallRequest,
    ModInstallRequest,
    ModOperationRequest,
    RconCommandPayload,
    RconCommandResult,
    RestoreRequest,
    SafeUpdateRequest,
    SafeUpdateResult,
    ServerConfigPayload,
    StoredServer,
    ImportServerPreview,
    ImportServerRequest,
)


def create_servers_router(**deps) -> APIRouter:
    router = APIRouter()
    active_server_ids = deps["active_server_ids"]
    allocate_port = deps["allocate_port"]
    append_action_log = deps["append_action_log"]
    apply_server_permissions = deps["apply_server_permissions"]
    bulk_install_mods = deps["bulk_install_mods"]
    bulk_operate_mods = deps["bulk_operate_mods"]
    create_backup_archive = deps["create_backup_archive"]
    ensure_disk_space_for_server = deps["ensure_disk_space_for_server"]
    ensure_server_provisioned = deps["ensure_server_provisioned"]
    execute_rcon = deps["execute_rcon"]
    fabric_installer_versions = deps["fabric_installer_versions"]
    fabric_loader_versions = deps["fabric_loader_versions"]
    folder_size = deps["folder_size"]
    host_primary_ip = deps["host_primary_ip"]
    install_mod = deps["install_mod"]
    import_build = deps["import_build"]
    import_existing_server = deps["import_existing_server"]
    list_server_files = deps["list_server_files"]
    load_server_or_404 = deps["load_server_or_404"]
    load_server_store = deps["load_server_store"]
    managed_server_path = deps["managed_server_path"]
    normalize_cpu_limit = deps["normalize_cpu_limit"]
    normalize_jvm_args = deps["normalize_jvm_args"]
    normalize_ram = deps["normalize_ram"]
    operate_mod = deps["operate_mod"]
    operate_server_file = deps["operate_server_file"]
    provision_server_in_background = deps["provision_server_in_background"]
    rcon_available = deps["rcon_available"]
    read_server_file = deps["read_server_file"]
    require_token = deps["require_token"]
    restore_backup = deps["restore_backup"]
    rollback_last_update = deps["rollback_last_update"]
    build_manifest = deps["build_manifest"]
    diff_manifests = deps["diff_manifests"]
    export_build = deps["export_build"]
    manifest_history_dir = deps["manifest_history_dir"]
    preview_existing_server = deps["preview_existing_server"]
    read_manifest = deps["read_manifest"]
    safe_update_modpack = deps["safe_update_modpack"]
    save_manifest = deps["save_manifest"]
    run = deps["run"]
    save_disabled_server_ids = deps["save_disabled_server_ids"]
    save_server_store = deps["save_server_store"]
    scan_installed_mods = deps["scan_installed_mods"]
    search_server_files = deps["search_server_files"]
    server_base_path = deps["server_base_path"]
    server_is_installing = deps["server_is_installing"]
    server_runtime_states = deps["server_runtime_states"]
    server_type_label = deps["server_type_label"]
    service_state = deps["service_state"]
    slugify = deps["slugify"]
    systemctl_issue_can_be_ignored = deps["systemctl_issue_can_be_ignored"]
    to_agent_server = deps["to_agent_server"]
    update_server_files = deps["update_server_files"]
    write_server_file = deps["write_server_file"]
    backup_to_item = deps["backup_to_item"]
    disabled_server_ids = deps["disabled_server_ids"]
    SERVER_LOADERS = deps["SERVER_LOADERS"]
    BACKUP_DIR = deps["BACKUP_DIR"]

    @router.get("/servers", response_model=list[AgentServer])
    def servers(x_ksylian_token: str | None = Header(default=None)) -> list[AgentServer]:
        require_token(x_ksylian_token)
        return [to_agent_server(server_id) for server_id in active_server_ids()]


    @router.post("/servers", response_model=AgentServer)
    def create_server(payload: CreateAgentServerRequest, x_ksylian_token: str | None = Header(default=None)) -> AgentServer:
        require_token(x_ksylian_token)
        store = load_server_store()
        server_id_base = slugify(payload.name)
        server_id = server_id_base
        counter = 2
        while server_id in store:
            server_id = f"{server_id_base}-{counter}"
            counter += 1

        port = allocate_port(store)
        service = f"ksylian-{server_id}.service"
        server_path = managed_server_path(server_id)
        server = StoredServer(
            id=server_id,
            name=payload.name.strip(),
            type=payload.type,
            pack=server_type_label(payload.type),
            version=payload.version,
            port=port,
            service=service,
            path=str(server_path),
            backup_path=str(server_path / "world"),
            address=f"{host_primary_ip()}:{port}",
            created_at=datetime.now().isoformat(timespec="seconds"),
            managed=True,
            min_ram=normalize_ram(payload.min_ram, "1G"),
            max_ram=normalize_ram(payload.max_ram, "2G"),
            java_runtime=payload.java_runtime if payload.java_runtime in {"auto", "8", "17", "21"} else "auto",
            jvm_args=normalize_jvm_args(payload.jvm_args),
            cpu_limit=normalize_cpu_limit(payload.cpu_limit),
            loader_version=payload.loader_version.strip(),
            installer_version=payload.installer_version.strip(),
            install_fabric_api=payload.install_fabric_api if payload.type == "fabric" else False,
        )
        ensure_disk_space_for_server(server)
        store[server.id] = server
        save_server_store(store)
        append_action_log("server_create_queued", server.id, f"{server.type} {server.version}")
        threading.Thread(target=provision_server_in_background, args=(server.id,), daemon=True).start()
        return to_agent_server(server.id)


    @router.post("/servers/import/preview", response_model=ImportServerPreview)
    def preview_import_server(
        payload: ImportServerRequest,
        x_ksylian_token: str | None = Header(default=None),
    ) -> ImportServerPreview:
        require_token(x_ksylian_token)
        return preview_existing_server(payload.path, payload.name)


    @router.post("/servers/import", response_model=AgentActionResult)
    def import_server(
        payload: ImportServerRequest,
        x_ksylian_token: str | None = Header(default=None),
    ) -> AgentActionResult:
        require_token(x_ksylian_token)
        return import_existing_server(payload, server_snapshot=to_agent_server)


    @router.get("/loaders/{loader_type}/versions", response_model=list[str])
    def loader_versions(
        loader_type: Literal["forge", "neoforge", "fabric", "vanilla", "paper", "purpur"],
        x_ksylian_token: str | None = Header(default=None),
    ) -> list[str]:
        require_token(x_ksylian_token)
        loader = SERVER_LOADERS.get(loader_type)
        if loader is None:
            raise HTTPException(status_code=404, detail="Loader not found")
        if loader_type == "fabric":
            return fabric_loader_versions()
        return loader.versions()


    @router.get("/loaders/fabric/installers", response_model=list[str])
    def fabric_installers(x_ksylian_token: str | None = Header(default=None)) -> list[str]:
        require_token(x_ksylian_token)
        return fabric_installer_versions()


    @router.get("/servers/{server_id}/logs", response_model=list[str])
    def logs(server_id: str, x_ksylian_token: str | None = Header(default=None)) -> list[str]:
        require_token(x_ksylian_token)
        config = load_server_store().get(server_id)
        if config is None:
            raise HTTPException(status_code=404, detail="Server not found")

        result = run(["journalctl", "-u", config.service, "-n", "80", "--no-pager", "-o", "short-iso"], timeout=30)
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=result.stderr.strip() or "Failed to read logs")
        return [line for line in result.stdout.splitlines() if line]


    @router.get("/servers/{server_id}/logs/full", response_model=list[str])
    def full_logs(server_id: str, x_ksylian_token: str | None = Header(default=None)) -> list[str]:
        require_token(x_ksylian_token)
        config = load_server_store().get(server_id)
        if config is None:
            raise HTTPException(status_code=404, detail="Server not found")

        result = run(["journalctl", "-u", config.service, "-n", "5000", "--no-pager", "-o", "short-iso"], timeout=60)
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=result.stderr.strip() or "Failed to read full logs")
        return [line for line in result.stdout.splitlines() if line]


    @router.get("/servers/{server_id}/crash-reports", response_model=list[CrashReportItem])
    def crash_reports(server_id: str, x_ksylian_token: str | None = Header(default=None)) -> list[CrashReportItem]:
        require_token(x_ksylian_token)
        config = load_server_store().get(server_id)
        if config is None:
            raise HTTPException(status_code=404, detail="Server not found")

        reports_dir = server_base_path(config) / "crash-reports" if config.managed else Path(config.path) / "crash-reports"
        if not reports_dir.exists():
            return []

        reports = []
        for path in sorted(reports_dir.glob("*.txt"), key=lambda item: item.stat().st_mtime, reverse=True)[:20]:
            analysis = analyze_crash_report(path, server_id)
            reports.append(
                CrashReportItem(
                    name=path.name,
                    size=folder_size(path),
                    created=datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
                    summary=crash_report_summary(path),
                    **analysis,
                )
            )
        return reports


    @router.get("/servers/{server_id}/config", response_model=ServerConfigPayload)
    def server_config(server_id: str, x_ksylian_token: str | None = Header(default=None)) -> ServerConfigPayload:
        require_token(x_ksylian_token)
        config = load_server_store().get(server_id)
        if config is None:
            raise HTTPException(status_code=404, detail="Server not found")

        properties_path = server_base_path(config) / "server.properties"
        if not properties_path.exists():
            ensure_server_provisioned(config)
        if not properties_path.exists():
            raise HTTPException(status_code=404, detail="server.properties was not found")

        try:
            content = properties_path.read_text()
        except OSError as error:
            raise HTTPException(status_code=500, detail="Failed to read server.properties") from error

        return ServerConfigPayload(content=content)


    @router.get("/servers/{server_id}/rcon/status")
    def rcon_status(server_id: str, x_ksylian_token: str | None = Header(default=None)) -> dict[str, bool]:
        require_token(x_ksylian_token)
        config = load_server_store().get(server_id)
        if config is None:
            raise HTTPException(status_code=404, detail="Server not found")
        return {"available": rcon_available(config)}


    @router.post("/servers/{server_id}/rcon/command", response_model=RconCommandResult)
    def rcon_command(
        server_id: str,
        payload: RconCommandPayload,
        x_ksylian_token: str | None = Header(default=None),
    ) -> RconCommandResult:
        require_token(x_ksylian_token)
        config = load_server_store().get(server_id)
        if config is None:
            raise HTTPException(status_code=404, detail="Server not found")
        command = payload.command.strip()
        if not command:
            raise HTTPException(status_code=400, detail="RCON command is required")
        output = execute_rcon(config, command)
        append_action_log("server_rcon_command", server_id, command)
        return RconCommandResult(ok=True, output=output)


    @router.put("/servers/{server_id}/config", response_model=ServerConfigPayload)
    def update_server_config(
        server_id: str,
        payload: ServerConfigPayload,
        x_ksylian_token: str | None = Header(default=None),
    ) -> ServerConfigPayload:
        require_token(x_ksylian_token)
        config = load_server_store().get(server_id)
        if config is None:
            raise HTTPException(status_code=404, detail="Server not found")
        if len(payload.content.encode("utf-8")) > 256 * 1024:
            raise HTTPException(status_code=413, detail="server.properties is too large")

        server_path = server_base_path(config)
        server_path.mkdir(parents=True, exist_ok=True)
        properties_path = server_path / "server.properties"
        content = payload.content.replace("\r\n", "\n").replace("\r", "\n")
        if not content.endswith("\n"):
            content += "\n"

        try:
            properties_path.write_text(content)
        except OSError as error:
            raise HTTPException(status_code=500, detail="Failed to write server.properties") from error

        if config.managed:
            apply_server_permissions(config)
        append_action_log("server_config_update", server_id, "server.properties")
        return ServerConfigPayload(content=content)


    @router.get("/servers/{server_id}/files", response_model=FileListPayload)
    def server_files(
        server_id: str,
        path: str = "",
        x_ksylian_token: str | None = Header(default=None),
    ) -> FileListPayload:
        require_token(x_ksylian_token)
        return list_server_files(load_server_or_404(server_id), path)


    @router.get("/servers/{server_id}/files/content", response_model=FileContentPayload)
    def server_file_content(
        server_id: str,
        path: str,
        x_ksylian_token: str | None = Header(default=None),
    ) -> FileContentPayload:
        require_token(x_ksylian_token)
        return read_server_file(load_server_or_404(server_id), path)


    @router.get("/servers/{server_id}/files/search", response_model=list[FileSearchResult])
    def server_file_search(
        server_id: str,
        query: str,
        path: str = "",
        x_ksylian_token: str | None = Header(default=None),
    ) -> list[FileSearchResult]:
        require_token(x_ksylian_token)
        return search_server_files(load_server_or_404(server_id), query, path)


    @router.put("/servers/{server_id}/files", response_model=FileEntry)
    def server_file_write(
        server_id: str,
        payload: FileWriteRequest,
        x_ksylian_token: str | None = Header(default=None),
    ) -> FileEntry:
        require_token(x_ksylian_token)
        return write_server_file(load_server_or_404(server_id), payload)


    @router.post("/servers/{server_id}/files/actions")
    def server_file_action(
        server_id: str,
        payload: FileOperationRequest,
        x_ksylian_token: str | None = Header(default=None),
    ) -> FileEntry | dict[str, bool]:
        require_token(x_ksylian_token)
        return operate_server_file(load_server_or_404(server_id), payload)


    @router.get("/servers/{server_id}/mods", response_model=list[InstalledModItem])
    def server_mods(server_id: str, x_ksylian_token: str | None = Header(default=None)) -> list[InstalledModItem]:
        require_token(x_ksylian_token)
        return scan_installed_mods(load_server_or_404(server_id))


    @router.get("/servers/{server_id}/manifest", response_model=BuildManifest)
    def server_manifest(server_id: str, x_ksylian_token: str | None = Header(default=None)) -> BuildManifest:
        require_token(x_ksylian_token)
        server = load_server_or_404(server_id)
        return read_manifest(server) or save_manifest(server)


    @router.post("/servers/{server_id}/manifest/refresh", response_model=BuildManifest)
    def refresh_server_manifest(server_id: str, x_ksylian_token: str | None = Header(default=None)) -> BuildManifest:
        require_token(x_ksylian_token)
        return save_manifest(load_server_or_404(server_id))


    @router.get("/servers/{server_id}/manifest/history", response_model=list[str])
    def server_manifest_history(server_id: str, x_ksylian_token: str | None = Header(default=None)) -> list[str]:
        require_token(x_ksylian_token)
        server = load_server_or_404(server_id)
        history = manifest_history_dir(server)
        if not history.exists():
            return []
        return [path.name for path in sorted(history.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)]


    @router.post("/servers/{server_id}/manifest/diff", response_model=BuildManifestDiff)
    def diff_server_manifest(
        server_id: str,
        payload: BuildManifest,
        x_ksylian_token: str | None = Header(default=None),
    ) -> BuildManifestDiff:
        require_token(x_ksylian_token)
        return diff_manifests(payload, build_manifest(load_server_or_404(server_id)))


    @router.post("/servers/{server_id}/manifest/import", response_model=BuildManifest)
    def import_server_manifest(
        server_id: str,
        payload: BuildImportRequest,
        x_ksylian_token: str | None = Header(default=None),
    ) -> BuildManifest:
        require_token(x_ksylian_token)
        return import_build(load_server_or_404(server_id), payload)


    @router.post("/servers/{server_id}/manifest/export")
    def export_server_manifest(server_id: str, x_ksylian_token: str | None = Header(default=None)) -> dict[str, str]:
        require_token(x_ksylian_token)
        archive = export_build(load_server_or_404(server_id))
        return {"path": str(archive), "name": archive.name}


    @router.post("/servers/{server_id}/updates/plan", response_model=SafeUpdateResult)
    def plan_safe_server_update(
        server_id: str,
        x_ksylian_token: str | None = Header(default=None),
    ) -> SafeUpdateResult:
        require_token(x_ksylian_token)
        return safe_update_modpack(load_server_or_404(server_id), SafeUpdateRequest(apply=False), to_agent_server)


    @router.post("/servers/{server_id}/updates/apply", response_model=SafeUpdateResult)
    def apply_safe_server_update(
        server_id: str,
        payload: SafeUpdateRequest,
        x_ksylian_token: str | None = Header(default=None),
    ) -> SafeUpdateResult:
        require_token(x_ksylian_token)
        return safe_update_modpack(load_server_or_404(server_id), payload, to_agent_server)


    @router.post("/servers/{server_id}/mods", response_model=InstalledModItem)
    def server_mod_install(
        server_id: str,
        payload: ModInstallRequest,
        x_ksylian_token: str | None = Header(default=None),
    ) -> InstalledModItem:
        require_token(x_ksylian_token)
        server = load_server_or_404(server_id)
        item = install_mod(server, payload)
        save_manifest(server)
        return item


    @router.post("/servers/{server_id}/mods/bulk", response_model=list[InstalledModItem])
    def server_mod_bulk_install(
        server_id: str,
        payload: ModBulkInstallRequest,
        x_ksylian_token: str | None = Header(default=None),
    ) -> list[InstalledModItem]:
        require_token(x_ksylian_token)
        server = load_server_or_404(server_id)
        items = bulk_install_mods(server, payload)
        save_manifest(server)
        return items


    @router.post("/servers/{server_id}/mods/actions")
    def server_mod_action(
        server_id: str,
        payload: ModOperationRequest,
        x_ksylian_token: str | None = Header(default=None),
    ) -> dict[str, bool]:
        require_token(x_ksylian_token)
        server = load_server_or_404(server_id)
        result = operate_mod(server, payload)
        save_manifest(server)
        return result


    @router.post("/servers/{server_id}/mods/bulk-actions")
    def server_mod_bulk_action(
        server_id: str,
        payload: ModBulkActionRequest,
        x_ksylian_token: str | None = Header(default=None),
    ) -> dict[str, int]:
        require_token(x_ksylian_token)
        server = load_server_or_404(server_id)
        result = bulk_operate_mods(server, payload)
        save_manifest(server)
        return result


    @router.post("/servers/{server_id}/backups", response_model=BackupItem)
    def server_backup(
        server_id: str,
        payload: BackupRequest,
        x_ksylian_token: str | None = Header(default=None),
    ) -> BackupItem:
        require_token(x_ksylian_token)
        return create_backup_archive(load_server_or_404(server_id), payload)


    @router.post("/servers/{server_id}/restore", response_model=AgentActionResult)
    def server_restore(
        server_id: str,
        payload: RestoreRequest,
        x_ksylian_token: str | None = Header(default=None),
    ) -> AgentActionResult:
        require_token(x_ksylian_token)
        return restore_backup(load_server_or_404(server_id), payload, to_agent_server)


    @router.post("/servers/{server_id}/actions/{action}", response_model=AgentActionResult)
    def action(
        server_id: str,
        action: Literal["start", "restart", "stop", "kill", "update", "rollback", "backup"],
        x_ksylian_token: str | None = Header(default=None),
    ) -> AgentActionResult:
        require_token(x_ksylian_token)
        config = load_server_or_404(server_id)

        if action in {"start", "restart", "update", "rollback"}:
            if server_is_installing(config):
                raise HTTPException(status_code=409, detail="Server is still installing")
            if action != "update":
                ensure_server_provisioned(config)

        if action == "update":
            server_runtime_states[server_id] = "updating"
            was_running = service_state(config.service) == "running"
            try:
                create_backup_archive(
                    config,
                    BackupRequest(mode="stopped" if was_running else "live", parts=["world", "mods", "config", "root"], description="Before server file update"),
                    reason="pre-update",
                )
                if was_running:
                    stop_result = run(["systemctl", "stop", config.service], timeout=60)
                    if stop_result.returncode != 0:
                        raise HTTPException(status_code=500, detail=stop_result.stderr.strip() or "systemctl stop failed")
                updated = update_server_files(config)
                store = load_server_store()
                store[server_id] = updated
                save_server_store(store)
                if was_running:
                    start_result = run(["systemctl", "start", updated.service], timeout=60)
                    if start_result.returncode != 0:
                        raise HTTPException(status_code=500, detail=start_result.stderr.strip() or "systemctl start failed")
                message = f"{config.name}: update completed"
                append_action_log("server_update", server_id, message)
            finally:
                server_runtime_states.pop(server_id, None)
        elif action == "rollback":
            result = rollback_last_update(config, to_agent_server)
            message = result.message
        elif action in {"start", "restart", "stop", "kill"}:
            command = ["systemctl", "kill", config.service] if action == "kill" else ["systemctl", action, config.service]
            result = run(command, timeout=60)
            if result.returncode != 0:
                append_action_log(f"server_{action}_failed", server_id, result.stderr.strip())
                raise HTTPException(status_code=500, detail=result.stderr.strip() or f"{' '.join(command)} failed")
            if action == "kill":
                run(["systemctl", "stop", config.service], timeout=60)
            message = f"{config.name}: {action} completed"
            append_action_log(f"server_{action}", server_id, message)
        else:
            backup = create_backup_archive(config, BackupRequest(mode="live", parts=["world", "mods", "config", "root"]))
            message = f"{config.name}: backup created at {backup.name}"

        return AgentActionResult(ok=True, message=message, server=to_agent_server(server_id))


    @router.delete("/servers/{server_id}")
    def delete_server(server_id: str, x_ksylian_token: str | None = Header(default=None)) -> dict[str, bool]:
        require_token(x_ksylian_token)
        store = load_server_store()
        config = store.get(server_id)
        if config is None:
            raise HTTPException(status_code=404, detail="Server not found")

        stop_result = run(["systemctl", "stop", config.service], timeout=60)
        if stop_result.returncode != 0 and not (config.managed and systemctl_issue_can_be_ignored(stop_result)):
            raise HTTPException(status_code=500, detail=stop_result.stderr.strip() or "Failed to stop service")

        disable_result = run(["systemctl", "disable", config.service], timeout=60)
        if disable_result.returncode != 0 and not (config.managed and systemctl_issue_can_be_ignored(disable_result)):
            raise HTTPException(status_code=500, detail=disable_result.stderr.strip() or "Failed to disable service")

        disabled = disabled_server_ids()
        if config.managed:
            unit_path = SYSTEMD_DIR / config.service
            unit_path.unlink(missing_ok=True)
            run(["systemctl", "daemon-reload"], timeout=30)
            shutil.rmtree(server_base_path(config), ignore_errors=True)
            store.pop(server_id, None)
            disabled.discard(server_id)
            save_server_store(store)
        else:
            disabled.add(server_id)
        save_disabled_server_ids(disabled)
        append_action_log("server_delete", server_id, config.name)
        return {"ok": True}


    @router.get("/backups")
    def backups(x_ksylian_token: str | None = Header(default=None)) -> list[BackupItem]:
        require_token(x_ksylian_token)
        if not BACKUP_DIR.exists():
            return []

        items: list[BackupItem] = []
        for path in sorted(BACKUP_DIR.glob("*.tar.gz"), key=lambda item: item.stat().st_mtime, reverse=True):
            items.append(backup_to_item(path))
        return items

    return router
