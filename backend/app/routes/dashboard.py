from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException

from ..schemas import (
    AgentStatus,
    BackupItem,
    DashboardPayload,
    FileItem,
    GameServer,
    HostMonitoring,
    MetricUsage,
    MinecraftVersionsPayload,
    MonitoringHistoryPayload,
    ModItem,
)


def create_dashboard_router(
    *,
    current_agent_status: Callable[[], AgentStatus],
    load_agent_servers: Callable[[], list[GameServer] | None],
    load_agent_backups: Callable[[], list[BackupItem] | None],
    load_agent_logs: Callable[[str], list[str]],
    load_agent_monitoring: Callable[[], HostMonitoring | None],
    require_agent_available: Callable[[], None],
    load_minecraft_versions: Callable[[], MinecraftVersionsPayload],
    agent_client: Any,
    logs: list[str],
    backups: list[BackupItem],
    mods: list[ModItem],
    files: list[FileItem],
    servers: dict[str, GameServer],
    append_log: Callable[[str], None],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/dashboard", response_model=DashboardPayload)
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


    @router.get("/api/servers", response_model=list[GameServer])
    def list_servers() -> list[GameServer]:
        agent_servers = load_agent_servers()
        if agent_servers is not None:
            return agent_servers
        require_agent_available()
        return list(servers.values())


    @router.get("/api/monitoring", response_model=HostMonitoring)
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

    @router.get("/api/monitoring/history", response_model=MonitoringHistoryPayload)
    def host_monitoring_history(window: str = "1h") -> MonitoringHistoryPayload:
        if window not in {"1h", "6h", "24h"}:
            window = "1h"
        try:
            return agent_client.monitoring_history(window)
        except Exception as error:
            append_log(f"agent monitoring history failed: {error}")
            require_agent_available()
            return MonitoringHistoryPayload(window=window, sample_seconds=30, retention_hours=24, points=[])


    @router.get("/api/minecraft/versions", response_model=MinecraftVersionsPayload)
    def minecraft_versions() -> MinecraftVersionsPayload:
        return load_minecraft_versions()


    @router.get("/api/agent/status", response_model=AgentStatus)
    def agent_status() -> AgentStatus:
        return current_agent_status()


    @router.post("/api/agent/restart", response_model=AgentStatus)
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
            agent_client.restart()
        except Exception as error:
            append_log(f"agent restart failed: {error}")
            raise HTTPException(status_code=502, detail="Host agent restart failed") from error

        return current_agent_status()

    return router
