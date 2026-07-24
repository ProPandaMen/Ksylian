from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException


from .schemas import (
    AgentServer,
    StoredServer,
)
from .config import (
    BACKUP_DIR,
    TOKEN,
    ACTION_LOG,
    PUBLIC_DOMAIN,
    SYSTEMD_DIR,
)
app = FastAPI(title="Ksylian Host Agent", version="0.1.0")


@app.on_event("startup")
def ensure_agent_token_configured() -> None:
    if not TOKEN:
        raise RuntimeError("KSYLIAN_AGENT_TOKEN is required")


from .security import (
    managed_server_path,
    require_token,
    server_base_path,
)
from .processes import (
    apply_server_permissions,
    run,
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
    minecraft_player_status,
    normalize_cpu_limit,
    normalize_jvm_args,
    normalize_ram,
    rcon_available,
    server_players_label,
    server_type_label,
    server_warnings,
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
    load_server_or_404,
    load_server_store,
    save_disabled_server_ids,
    save_server_store,
    slugify,
)
from .runtime import server_runtime_states
from .backups import (
    backup_to_item,
    create_backup_archive,
    restore_backup,
    rollback_last_update,
)
from .files import (
    list_server_files,
    operate_server_file,
    read_server_file,
    search_server_files,
    write_server_file,
)
from .mods import (
    bulk_install_mods,
    bulk_operate_mods,
    install_mod,
    operate_mod,
    scan_installed_mods,
)
from .manifest import (
    build_manifest,
    diff_manifests,
    export_build,
    import_build,
    manifest_history_dir,
    read_manifest,
    save_manifest,
)
from .imports import import_existing_server, import_server_archive, preview_existing_server
from .safe_updates import safe_update_modpack
from .players import list_players, run_player_action


from .loaders import (
    SERVER_LOADERS,
    fabric_installer_versions,
    fabric_loader_versions,
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
from .monitoring_history import collect_host_monitoring, start_monitoring_sampler
from .routes.system import create_system_router
from .routes.servers import create_servers_router
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



@app.on_event("startup")
def start_monitoring_history_sampler() -> None:
    start_monitoring_sampler(
        lambda: collect_host_monitoring(
            active_server_ids=active_server_ids,
            load_server_store=load_server_store,
            memory_usage=memory_usage,
            service_usage=service_usage,
            service_state=service_state,
            host_ips=host_ips,
            format_duration=format_duration,
            cpu_percent=cpu_percent,
            disk_usage=disk_usage,
            top_processes=top_processes,
            temperature_label=temperature_label,
        )
    )


app.include_router(create_system_router(
    active_server_ids=active_server_ids,
    load_server_store=load_server_store,
    memory_usage=memory_usage,
    service_usage=service_usage,
    service_state=service_state,
    host_ips=host_ips,
    format_duration=format_duration,
    cpu_percent=cpu_percent,
    disk_usage=disk_usage,
    top_processes=top_processes,
    temperature_label=temperature_label,
))
app.include_router(create_servers_router(
    active_server_ids=active_server_ids,
    allocate_port=allocate_port,
    append_action_log=append_action_log,
    apply_server_permissions=apply_server_permissions,
    bulk_install_mods=bulk_install_mods,
    bulk_operate_mods=bulk_operate_mods,
    create_backup_archive=create_backup_archive,
    ensure_disk_space_for_server=ensure_disk_space_for_server,
    ensure_server_provisioned=ensure_server_provisioned,
    execute_rcon=execute_rcon,
    fabric_installer_versions=fabric_installer_versions,
    fabric_loader_versions=fabric_loader_versions,
    folder_size=folder_size,
    host_primary_ip=host_primary_ip,
    install_mod=install_mod,
    import_build=import_build,
    import_existing_server=import_existing_server,
    import_server_archive=import_server_archive,
    list_server_files=list_server_files,
    list_players=list_players,
    load_server_or_404=load_server_or_404,
    load_server_store=load_server_store,
    managed_server_path=managed_server_path,
    normalize_cpu_limit=normalize_cpu_limit,
    normalize_jvm_args=normalize_jvm_args,
    normalize_ram=normalize_ram,
    operate_mod=operate_mod,
    operate_server_file=operate_server_file,
    provision_server_in_background=provision_server_in_background,
    rcon_available=rcon_available,
    read_server_file=read_server_file,
    require_token=require_token,
    restore_backup=restore_backup,
    rollback_last_update=rollback_last_update,
    build_manifest=build_manifest,
    diff_manifests=diff_manifests,
    export_build=export_build,
    manifest_history_dir=manifest_history_dir,
    preview_existing_server=preview_existing_server,
    read_manifest=read_manifest,
    run_player_action=run_player_action,
    safe_update_modpack=safe_update_modpack,
    save_manifest=save_manifest,
    run=run,
    save_disabled_server_ids=save_disabled_server_ids,
    save_server_store=save_server_store,
    scan_installed_mods=scan_installed_mods,
    search_server_files=search_server_files,
    server_base_path=server_base_path,
    server_is_installing=server_is_installing,
    server_runtime_states=server_runtime_states,
    server_type_label=server_type_label,
    service_state=service_state,
    slugify=slugify,
    systemctl_issue_can_be_ignored=systemctl_issue_can_be_ignored,
    to_agent_server=to_agent_server,
    update_server_files=update_server_files,
    write_server_file=write_server_file,
    backup_to_item=backup_to_item,
    disabled_server_ids=disabled_server_ids,
    SERVER_LOADERS=SERVER_LOADERS,
    BACKUP_DIR=BACKUP_DIR,
    SYSTEMD_DIR=SYSTEMD_DIR,
))
