from __future__ import annotations

import subprocess
from collections.abc import Callable

from fastapi import APIRouter, Header

from ..activity import append_action_log
from ..config import ACTION_LOG, PROXY_DOMAIN, PROXY_PORT, PUBLIC_DOMAIN, TOKEN, UPDATE_LOG
from ..monitoring_history import collect_host_monitoring, history_payload
from ..schemas import AppUpdateRequest, AppUpdateResult, HostMonitoring, MonitoringHistoryPayload
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
        return collect_host_monitoring(
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

    @router.get("/monitoring/history", response_model=MonitoringHistoryPayload)
    def monitoring_history(window: str = "1h", x_ksylian_token: str | None = Header(default=None)) -> MonitoringHistoryPayload:
        require_token(x_ksylian_token)
        return history_payload(window)

    return router
