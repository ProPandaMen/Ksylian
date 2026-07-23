from __future__ import annotations

import os
import socket
import subprocess
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Header

from ..activity import append_action_log
from ..config import ACTION_LOG, PROXY_DOMAIN, PROXY_PORT, PUBLIC_DOMAIN, TOKEN, UPDATE_LOG
from ..schemas import AppUpdateRequest, AppUpdateResult, HostMonitoring, ServiceUsage
from ..security import require_token
from ..updates import append_update_log, ensure_updater_configured, update_script_path, validate_update_target


def create_system_router(
    *,
    active_server_ids: Callable[[], list[str]],
    load_server_store,
    memory_usage,
    service_usage,
    service_state,
    host_ips,
    format_duration,
    cpu_percent,
    disk_usage,
    top_processes,
    temperature_label,
) -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "ksylian-agent",
            "public_domain": PUBLIC_DOMAIN,
            "proxy_domain": PROXY_DOMAIN,
            "proxy_port": PROXY_PORT,
        }


    @router.post("/agent/actions/restart")
    def restart_agent(x_ksylian_token: str | None = Header(default=None)) -> dict[str, bool]:
        require_token(x_ksylian_token)
        subprocess.Popen(["systemctl", "restart", "ksylian-agent.service"])
        return {"ok": True}


    @router.get("/app/update/log", response_model=list[str])
    def app_update_log(x_ksylian_token: str | None = Header(default=None)) -> list[str]:
        require_token(x_ksylian_token)
        if not UPDATE_LOG.exists():
            return []
        return UPDATE_LOG.read_text().splitlines()[-120:]


    @router.get("/agent/actions/log", response_model=list[str])
    def agent_action_log(x_ksylian_token: str | None = Header(default=None)) -> list[str]:
        require_token(x_ksylian_token)
        if not ACTION_LOG.exists():
            return []
        return ACTION_LOG.read_text().splitlines()[-200:]


    @router.post("/app/update", response_model=AppUpdateResult)
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


    @router.get("/monitoring", response_model=HostMonitoring)
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

    return router
