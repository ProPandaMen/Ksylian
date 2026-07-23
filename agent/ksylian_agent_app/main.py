from __future__ import annotations

import os
import base64
import io
import json
import hashlib
import re
import secrets
import shutil
import shlex
import socket
import subprocess
import tarfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, Header, HTTPException

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    tomllib = None  # type: ignore[assignment]


from .schemas import (
    AgentServer,
    StoredServer,
    CreateAgentServerRequest,
    AgentActionResult,
    ServerConfigPayload,
    RconCommandPayload,
    RconCommandResult,
    BackupRequest,
    RestoreRequest,
    BackupItem,
    FileEntry,
    FileListPayload,
    FileWriteRequest,
    FileOperationRequest,
    FileContentPayload,
    FileSearchResult,
    ModDependency,
    InstalledModItem,
    ModInstallRequest,
    ModOperationRequest,
    ModBulkInstallRequest,
    ModBulkActionRequest,
    CrashReportItem,
    AppUpdateRequest,
    AppUpdateResult,
    MetricUsage,
    DiskUsage,
    ProcessUsage,
    ServiceUsage,
    HostMonitoring,
)
from .config import (
    SERVERS,
    BACKUP_DIR,
    BACKUP_KEEP_LAST,
    BACKUP_KEEP_DAILY,
    BACKUP_KEEP_WEEKLY,
    BACKUP_KEEP_MONTHLY,
    BACKUP_MAX_BYTES,
    BACKUP_S3_URI,
    DATA_DIR,
    DISABLED_SERVERS_FILE,
    SERVERS_FILE,
    SERVER_ROOT,
    APP_DIR,
    APP_ENV_FILE,
    APP_COMPOSE_FILE,
    UPDATE_LOG,
    TOKEN,
    ACTION_LOG,
    PUBLIC_DOMAIN,
    PROXY_DOMAIN,
    PROXY_PORT,
    MINECRAFT_USER,
    RATE_LIMIT_REQUESTS,
    RATE_LIMIT_WINDOW_SECONDS,
    MINECRAFT_VERSION_MANIFEST_URL,
    FABRIC_META_API_URL,
    MODRINTH_API_URL,
    FORGE_MAVEN_URL,
    NEOFORGE_MAVEN_URL,
    PAPER_API_URL,
    PURPUR_API_URL,
    AGENT_USER_AGENT,
    SYSTEMD_DIR,
)
app = FastAPI(title="Ksylian Host Agent", version="0.1.0")


@app.on_event("startup")
def ensure_agent_token_configured() -> None:
    if not TOKEN:
        raise RuntimeError("KSYLIAN_AGENT_TOKEN is required")


from .security import (
    ensure_child_path,
    is_relative_path,
    managed_server_path,
    relative_server_path,
    require_token,
    server_base_path,
    server_child_path,
)
from .processes import (
    apply_server_permissions,
    ensure_minecraft_user_exists,
    run,
    run_in,
    service_state,
    systemctl_issue_can_be_ignored,
)
from .minecraft import (
    allocate_port,
    configured_max_players,
    execute_rcon,
    host_primary_ip,
    is_port_available,
    java_binary,
    java_candidates,
    java_major_version,
    minecraft_player_status,
    minecraft_version_key,
    normalize_cpu_limit,
    normalize_jvm_args,
    normalize_ram,
    ram_to_bytes,
    rcon_available,
    required_java_major,
    server_players_label,
    server_type_label,
    server_warnings,
    start_command_for_server,
    write_server_scaffold,
    ensure_disk_space_for_server,
)
from .updates import (
    append_update_log,
    ensure_updater_configured,
    update_script_path,
    validate_update_target,
)
from .activity import append_action_log
from .storage import (
    active_server_ids,
    disabled_server_ids,
    legacy_server_store,
    load_server_or_404,
    load_server_store,
    save_disabled_server_ids,
    save_server_store,
    slugify,
)
from .runtime import server_runtime_states
from .backups import (
    apply_backup_retention,
    backup_archive_path,
    backup_manifest,
    backup_manifest_path,
    backup_part_paths,
    backup_to_item,
    backup_total_bytes,
    create_backup_archive,
    iter_backup_files,
    latest_restore_candidate,
    remove_backup_file,
    restore_backup,
    rollback_last_update,
    sync_backup_to_s3,
    verify_backup_archive,
)
from .files import (
    file_entry,
    file_syntax,
    list_server_files,
    operate_server_file,
    quick_file_label,
    read_server_file,
    search_server_files,
    write_server_file,
)
from .mods import (
    bulk_install_mods,
    bulk_operate_mods,
    install_mod,
    mod_metadata_from_fabric,
    mod_metadata_from_toml,
    normalize_dependency,
    operate_mod,
    parse_mod_toml_fallback,
    read_mod_metadata,
    scan_installed_mods,
)
from .hashing import file_digest


from .loaders import (
    FabricLoader,
    ForgeLoader,
    JarServerLoader,
    NeoForgeLoader,
    SERVER_LOADERS,
    ServerLoader,
    download_fabric_server_jar,
    download_paper_server_jar,
    download_purpur_server_jar,
    download_vanilla_server_jar,
    fabric_installer_versions,
    fabric_loader_versions,
    forge_versions,
    install_fabric_api,
    install_forge_server,
    install_neoforge_server,
    latest_fabric_component,
    latest_forge_version,
    latest_neoforge_version,
    neoforge_versions,
    provision_server_files,
    update_server_files,
    ensure_server_provisioned,
)

from .monitoring import (
    cpu_percent,
    disk_usage,
    folder_size,
    format_bytes,
    format_duration,
    host_ips,
    memory_usage,
    service_exit_code,
    service_usage,
    temperature_label,
    top_processes,
)
def last_server_event(server_id: str) -> str:
    if not ACTION_LOG.exists():
        return ""
    try:
        lines = ACTION_LOG.read_text().splitlines()
    except OSError:
        return ""
    for line in reversed(lines):
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if item.get("server_id") == server_id:
            action = str(item.get("action") or "")
            at = str(item.get("at") or "")
            return f"{at} · {action}" if at and action else action
    return ""


def crash_report_summary(path: Path) -> str:
    try:
        for line in path.read_text(errors="replace").splitlines()[:80]:
            stripped = line.strip()
            if stripped.startswith("Description:"):
                return stripped
            if "Exception" in stripped or "Error" in stripped:
                return stripped[:180]
    except OSError:
        return ""
    return ""


def recent_server_changes(server_id: str, limit: int = 5) -> list[str]:
    if not ACTION_LOG.exists():
        return []
    try:
        lines = ACTION_LOG.read_text().splitlines()
    except OSError:
        return []
    changes: list[str] = []
    for line in reversed(lines):
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if item.get("server_id") == server_id:
            at = str(item.get("at") or "")
            action = str(item.get("action") or "")
            detail = str(item.get("detail") or "")
            changes.append(" · ".join(part for part in (at, action, detail) if part))
        if len(changes) >= limit:
            break
    return changes


def analyze_crash_report(path: Path, server_id: str) -> dict[str, Any]:
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        lines = []
    joined = "\n".join(lines)
    stack_trace = [line for line in lines if line.lstrip().startswith("at ") or "Caused by:" in line][:30]
    probable = next((line.strip() for line in lines if line.strip().startswith("Description:")), "")
    if not probable:
        probable = next((line.strip() for line in lines if "Caused by:" in line), "")

    missing_dependency = ""
    missing_match = re.search(r"(requires [^\n]+|Missing [^\n]+|depends on [^\n]+)", joined, re.IGNORECASE)
    if missing_match:
        missing_dependency = missing_match.group(1).strip()[:180]

    client_only_mod = ""
    if re.search(r"client[- ]only|net\.minecraft\.client|DistExecutor|FMLEnvironment\.dist", joined, re.IGNORECASE):
        client_only_mod = "В отчёте есть признаки client-only кода на сервере"

    conflicting_mod = ""
    mod_match = re.search(r"(Suspected Mod[s]?:[^\n]+|Mod File:[^\n]+|Mod [A-Za-z0-9_.-]+)", joined, re.IGNORECASE)
    if mod_match:
        conflicting_mod = mod_match.group(1).strip()[:180]

    return {
        "probable_cause": probable[:220],
        "conflicting_mod": conflicting_mod,
        "missing_dependency": missing_dependency,
        "client_only_mod": client_only_mod,
        "stack_trace": stack_trace,
        "recent_changes": recent_server_changes(server_id),
    }


def public_server_address(config: StoredServer) -> str:
    if config.managed and PUBLIC_DOMAIN:
        return f"{config.id}.{PUBLIC_DOMAIN}"
    return config.address


def cleanup_managed_server(server: StoredServer) -> None:
    if not server.managed:
        return
    run(["systemctl", "stop", server.service], timeout=60)
    run(["systemctl", "disable", server.service], timeout=60)
    unit_path = SYSTEMD_DIR / server.service
    unit_path.unlink(missing_ok=True)
    run(["systemctl", "daemon-reload"], timeout=30)
    try:
        shutil.rmtree(server_base_path(server), ignore_errors=True)
    except HTTPException:
        pass


def server_is_installing(server: StoredServer) -> bool:
    return server.managed and not (SYSTEMD_DIR / server.service).exists()


def provision_server_in_background(server_id: str) -> None:
    try:
        store = load_server_store()
        server = store.get(server_id)
        if server is None:
            return
        server = ensure_server_provisioned(server)
        store = load_server_store()
        store[server.id] = server
        save_server_store(store)
        append_action_log("server_install_complete", server.id, f"{server.type} {server.version}")
    except Exception as error:
        store = load_server_store()
        server = store.get(server_id)
        if server is not None:
            cleanup_managed_server(server)
            store.pop(server_id, None)
            save_server_store(store)
        append_action_log("server_install_failed", server_id, str(error))


def to_agent_server(server_id: str) -> AgentServer:
    config = load_server_store()[server_id]
    cpu, ram = service_usage(config.service)
    state = server_runtime_states.get(server_id) or service_state(config.service)
    if server_is_installing(config):
        state = "installing"

    return AgentServer(
        id=server_id,
        name=config.name,
        pack=config.pack,
        version=config.version,
        state=state,
        players=server_players_label(config, state),
        ram=ram,
        cpu=cpu,
        disk=folder_size(Path(config.path)),
        address=public_server_address(config),
        exit_code=service_exit_code(config.service),
        last_event=last_server_event(server_id),
        warnings=server_warnings(config),
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "ksylian-agent",
        "public_domain": PUBLIC_DOMAIN,
        "proxy_domain": PROXY_DOMAIN,
        "proxy_port": PROXY_PORT,
    }


@app.post("/agent/actions/restart")
def restart_agent(x_ksylian_token: str | None = Header(default=None)) -> dict[str, bool]:
    require_token(x_ksylian_token)
    subprocess.Popen(["systemctl", "restart", "ksylian-agent.service"])
    return {"ok": True}


@app.get("/app/update/log", response_model=list[str])
def app_update_log(x_ksylian_token: str | None = Header(default=None)) -> list[str]:
    require_token(x_ksylian_token)
    if not UPDATE_LOG.exists():
        return []
    return UPDATE_LOG.read_text().splitlines()[-120:]


@app.get("/agent/actions/log", response_model=list[str])
def agent_action_log(x_ksylian_token: str | None = Header(default=None)) -> list[str]:
    require_token(x_ksylian_token)
    if not ACTION_LOG.exists():
        return []
    return ACTION_LOG.read_text().splitlines()[-200:]


@app.post("/app/update", response_model=AppUpdateResult)
def update_app(payload: AppUpdateRequest, x_ksylian_token: str | None = Header(default=None)) -> AppUpdateResult:
    require_token(x_ksylian_token)
    target_version = validate_update_target(payload.target_version)
    ensure_updater_configured()
    script_path = update_script_path()
    append_update_log(f"Queued update to {target_version}")
    append_action_log("app_update", detail=target_version)
    subprocess.Popen(
        ["bash", str(script_path), target_version],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return AppUpdateResult(
        ok=True,
        message="Обновление запущено. Панель перезапустится после сборки контейнеров.",
        target_version=target_version,
    )


@app.get("/servers", response_model=list[AgentServer])
def servers(x_ksylian_token: str | None = Header(default=None)) -> list[AgentServer]:
    require_token(x_ksylian_token)
    return [to_agent_server(server_id) for server_id in active_server_ids()]


@app.post("/servers", response_model=AgentServer)
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


@app.get("/loaders/{loader_type}/versions", response_model=list[str])
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


@app.get("/loaders/fabric/installers", response_model=list[str])
def fabric_installers(x_ksylian_token: str | None = Header(default=None)) -> list[str]:
    require_token(x_ksylian_token)
    return fabric_installer_versions()


@app.get("/monitoring", response_model=HostMonitoring)
def monitoring(x_ksylian_token: str | None = Header(default=None)) -> HostMonitoring:
    require_token(x_ksylian_token)
    memory, swap = memory_usage()
    load_average = [round(value, 2) for value in os.getloadavg()]

    try:
        uptime_seconds = float(Path("/proc/uptime").read_text().split()[0])
    except (OSError, ValueError, IndexError):
        uptime_seconds = 0

    services = []
    for server_id in active_server_ids():
        config = load_server_store()[server_id]
        cpu, ram = service_usage(config.service)
        services.append(
            ServiceUsage(
                id=server_id,
                name=config.name,
                state=service_state(config.service),
                cpu=cpu,
                ram=ram,
            )
        )

    agent_cpu, agent_ram = service_usage("ksylian-agent.service")
    services.append(
        ServiceUsage(
            id="ksylian-agent",
            name="Ksylian Agent",
            state=service_state("ksylian-agent.service"),
            cpu=agent_cpu,
            ram=agent_ram,
        )
    )

    return HostMonitoring(
        hostname=socket.gethostname(),
        ip_addresses=host_ips(),
        uptime=format_duration(uptime_seconds),
        load_average=load_average,
        cpu_percent=cpu_percent(),
        cpu_cores=os.cpu_count() or 1,
        memory=memory,
        swap=swap,
        disks=disk_usage(),
        top_processes=top_processes(),
        services=services,
        temperature=temperature_label(),
        collected_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


@app.get("/servers/{server_id}/logs", response_model=list[str])
def logs(server_id: str, x_ksylian_token: str | None = Header(default=None)) -> list[str]:
    require_token(x_ksylian_token)
    config = load_server_store().get(server_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Server not found")

    result = run(["journalctl", "-u", config.service, "-n", "80", "--no-pager", "-o", "short-iso"], timeout=30)
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=result.stderr.strip() or "Failed to read logs")
    return [line for line in result.stdout.splitlines() if line]


@app.get("/servers/{server_id}/logs/full", response_model=list[str])
def full_logs(server_id: str, x_ksylian_token: str | None = Header(default=None)) -> list[str]:
    require_token(x_ksylian_token)
    config = load_server_store().get(server_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Server not found")

    result = run(["journalctl", "-u", config.service, "-n", "5000", "--no-pager", "-o", "short-iso"], timeout=60)
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=result.stderr.strip() or "Failed to read full logs")
    return [line for line in result.stdout.splitlines() if line]


@app.get("/servers/{server_id}/crash-reports", response_model=list[CrashReportItem])
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


@app.get("/servers/{server_id}/config", response_model=ServerConfigPayload)
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


@app.get("/servers/{server_id}/rcon/status")
def rcon_status(server_id: str, x_ksylian_token: str | None = Header(default=None)) -> dict[str, bool]:
    require_token(x_ksylian_token)
    config = load_server_store().get(server_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Server not found")
    return {"available": rcon_available(config)}


@app.post("/servers/{server_id}/rcon/command", response_model=RconCommandResult)
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


@app.put("/servers/{server_id}/config", response_model=ServerConfigPayload)
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


@app.get("/servers/{server_id}/files", response_model=FileListPayload)
def server_files(
    server_id: str,
    path: str = "",
    x_ksylian_token: str | None = Header(default=None),
) -> FileListPayload:
    require_token(x_ksylian_token)
    return list_server_files(load_server_or_404(server_id), path)


@app.get("/servers/{server_id}/files/content", response_model=FileContentPayload)
def server_file_content(
    server_id: str,
    path: str,
    x_ksylian_token: str | None = Header(default=None),
) -> FileContentPayload:
    require_token(x_ksylian_token)
    return read_server_file(load_server_or_404(server_id), path)


@app.get("/servers/{server_id}/files/search", response_model=list[FileSearchResult])
def server_file_search(
    server_id: str,
    query: str,
    path: str = "",
    x_ksylian_token: str | None = Header(default=None),
) -> list[FileSearchResult]:
    require_token(x_ksylian_token)
    return search_server_files(load_server_or_404(server_id), query, path)


@app.put("/servers/{server_id}/files", response_model=FileEntry)
def server_file_write(
    server_id: str,
    payload: FileWriteRequest,
    x_ksylian_token: str | None = Header(default=None),
) -> FileEntry:
    require_token(x_ksylian_token)
    return write_server_file(load_server_or_404(server_id), payload)


@app.post("/servers/{server_id}/files/actions")
def server_file_action(
    server_id: str,
    payload: FileOperationRequest,
    x_ksylian_token: str | None = Header(default=None),
) -> FileEntry | dict[str, bool]:
    require_token(x_ksylian_token)
    return operate_server_file(load_server_or_404(server_id), payload)


@app.get("/servers/{server_id}/mods", response_model=list[InstalledModItem])
def server_mods(server_id: str, x_ksylian_token: str | None = Header(default=None)) -> list[InstalledModItem]:
    require_token(x_ksylian_token)
    return scan_installed_mods(load_server_or_404(server_id))


@app.post("/servers/{server_id}/mods", response_model=InstalledModItem)
def server_mod_install(
    server_id: str,
    payload: ModInstallRequest,
    x_ksylian_token: str | None = Header(default=None),
) -> InstalledModItem:
    require_token(x_ksylian_token)
    return install_mod(load_server_or_404(server_id), payload)


@app.post("/servers/{server_id}/mods/bulk", response_model=list[InstalledModItem])
def server_mod_bulk_install(
    server_id: str,
    payload: ModBulkInstallRequest,
    x_ksylian_token: str | None = Header(default=None),
) -> list[InstalledModItem]:
    require_token(x_ksylian_token)
    return bulk_install_mods(load_server_or_404(server_id), payload)


@app.post("/servers/{server_id}/mods/actions")
def server_mod_action(
    server_id: str,
    payload: ModOperationRequest,
    x_ksylian_token: str | None = Header(default=None),
) -> dict[str, bool]:
    require_token(x_ksylian_token)
    return operate_mod(load_server_or_404(server_id), payload)


@app.post("/servers/{server_id}/mods/bulk-actions")
def server_mod_bulk_action(
    server_id: str,
    payload: ModBulkActionRequest,
    x_ksylian_token: str | None = Header(default=None),
) -> dict[str, int]:
    require_token(x_ksylian_token)
    return bulk_operate_mods(load_server_or_404(server_id), payload)


@app.post("/servers/{server_id}/backups", response_model=BackupItem)
def server_backup(
    server_id: str,
    payload: BackupRequest,
    x_ksylian_token: str | None = Header(default=None),
) -> BackupItem:
    require_token(x_ksylian_token)
    return create_backup_archive(load_server_or_404(server_id), payload)


@app.post("/servers/{server_id}/restore", response_model=AgentActionResult)
def server_restore(
    server_id: str,
    payload: RestoreRequest,
    x_ksylian_token: str | None = Header(default=None),
) -> AgentActionResult:
    require_token(x_ksylian_token)
    return restore_backup(load_server_or_404(server_id), payload, to_agent_server)


@app.post("/servers/{server_id}/actions/{action}", response_model=AgentActionResult)
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


@app.delete("/servers/{server_id}")
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


@app.get("/backups")
def backups(x_ksylian_token: str | None = Header(default=None)) -> list[BackupItem]:
    require_token(x_ksylian_token)
    if not BACKUP_DIR.exists():
        return []

    items: list[BackupItem] = []
    for path in sorted(BACKUP_DIR.glob("*.tar.gz"), key=lambda item: item.stat().st_mtime, reverse=True):
        items.append(backup_to_item(path))
    return items
