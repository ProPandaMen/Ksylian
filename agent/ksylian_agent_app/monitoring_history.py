from __future__ import annotations

import json
import os
import socket
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from .config import MONITORING_HISTORY_FILE, MONITORING_RETENTION_HOURS, MONITORING_SAMPLE_SECONDS
from .schemas import (
    HostMonitoring,
    MonitoringDiskPoint,
    MonitoringHistoryPayload,
    MonitoringHistoryPoint,
    MonitoringServicesPoint,
    MonitoringTopProcessPoint,
    ServiceUsage,
)


WINDOW_SECONDS = {
    "1h": 60 * 60,
    "6h": 6 * 60 * 60,
    "24h": 24 * 60 * 60,
}


def temperature_value(label: str) -> float | None:
    cleaned = label.replace(",", ".")
    number = ""
    for char in cleaned:
        if char.isdigit() or char in {"-", "."}:
            number += char
        elif number:
            break
    try:
        return float(number) if number else None
    except ValueError:
        return None


def collect_host_monitoring(
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
) -> HostMonitoring:
    memory, swap = memory_usage()
    load_average = [round(value, 2) for value in os.getloadavg()]

    try:
        uptime_seconds = float(Path("/proc/uptime").read_text().split()[0])
    except (OSError, ValueError, IndexError):
        uptime_seconds = 0

    services: list[ServiceUsage] = []
    store = load_server_store()
    for server_id in active_server_ids():
        config = store[server_id]
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


def history_point(snapshot: HostMonitoring) -> MonitoringHistoryPoint:
    running_services = [service for service in snapshot.services if service.state == "running"]
    unhealthy_services = [service.name for service in snapshot.services if service.state != "running"]
    top = snapshot.top_processes[0] if snapshot.top_processes else None
    return MonitoringHistoryPoint(
        timestamp=int(time.time()),
        collected_at=snapshot.collected_at,
        cpu=snapshot.cpu_percent,
        memory=snapshot.memory.percent,
        swap=snapshot.swap.percent,
        temperature=temperature_value(snapshot.temperature),
        load_average=snapshot.load_average,
        disks=[
            MonitoringDiskPoint(mount=disk.mount, percent=disk.percent, used=disk.used, total=disk.total)
            for disk in snapshot.disks
        ],
        services=MonitoringServicesPoint(
            running=len(running_services),
            total=len(snapshot.services),
            unhealthy=unhealthy_services,
        ),
        top_process=MonitoringTopProcessPoint(
            pid=top.pid,
            name=top.name,
            cpu=top.cpu,
            memory=top.memory,
        )
        if top
        else None,
    )


def read_history_points() -> list[MonitoringHistoryPoint]:
    if not MONITORING_HISTORY_FILE.exists():
        return []
    points: list[MonitoringHistoryPoint] = []
    try:
        lines = MONITORING_HISTORY_FILE.read_text().splitlines()
    except OSError:
        return []
    for line in lines:
        try:
            points.append(MonitoringHistoryPoint(**json.loads(line)))
        except Exception:
            continue
    return points


def write_history_points(points: list[MonitoringHistoryPoint]) -> None:
    MONITORING_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = MONITORING_HISTORY_FILE.with_suffix(".jsonl.tmp")
    payload = "\n".join(point.model_dump_json() for point in points)
    tmp_path.write_text(f"{payload}\n" if payload else "")
    tmp_path.chmod(0o600)
    tmp_path.replace(MONITORING_HISTORY_FILE)


def trim_history(points: list[MonitoringHistoryPoint], now: int | None = None) -> list[MonitoringHistoryPoint]:
    cutoff = (now or int(time.time())) - MONITORING_RETENTION_HOURS * 3600
    return [point for point in points if point.timestamp >= cutoff]


def append_monitoring_snapshot(snapshot: HostMonitoring) -> None:
    points = trim_history(read_history_points())
    points.append(history_point(snapshot))
    write_history_points(trim_history(points))


def history_payload(window: str) -> MonitoringHistoryPayload:
    if window not in WINDOW_SECONDS:
        window = "1h"
    cutoff = int(time.time()) - WINDOW_SECONDS[window]
    points = [point for point in trim_history(read_history_points()) if point.timestamp >= cutoff]
    return MonitoringHistoryPayload(
        window=window,
        sample_seconds=MONITORING_SAMPLE_SECONDS,
        retention_hours=MONITORING_RETENTION_HOURS,
        points=points,
    )


def start_monitoring_sampler(collect_snapshot: Callable[[], HostMonitoring]) -> None:
    def run_sampler() -> None:
        while True:
            try:
                append_monitoring_snapshot(collect_snapshot())
            except Exception:
                pass
            time.sleep(MONITORING_SAMPLE_SECONDS)

    thread = threading.Thread(target=run_sampler, name="ksylian-monitoring-sampler", daemon=True)
    thread.start()
