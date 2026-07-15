from __future__ import annotations

import os
import socket
import subprocess
import tarfile
import time
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel


class AgentServer(BaseModel):
    id: str
    name: str
    pack: str
    version: str
    state: Literal["online", "deploying", "offline"]
    players: str
    ram: str
    cpu: int
    disk: str
    address: str


class AgentActionResult(BaseModel):
    ok: bool
    message: str
    server: AgentServer


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
    state: Literal["online", "deploying", "offline"]
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


SERVERS = {
    "minecraft": {
        "service": "minecraft.service",
        "name": "Minecraft Fabric",
        "pack": "Dungeon and Beer",
        "version": "1.20.1",
        "address": "192.168.31.254:25566",
        "path": Path("/home/ilya/Server"),
        "backup_path": Path("/home/ilya/Server/world"),
    },
    "velocity": {
        "service": "velocity.service",
        "name": "Velocity Proxy",
        "pack": "Proxy",
        "version": "3.4.0",
        "address": "192.168.31.254:25565",
        "path": Path("/mnt/hdd/MinecraftServer/proxyServer"),
        "backup_path": Path("/mnt/hdd/MinecraftServer/proxyServer"),
    },
}

BACKUP_DIR = Path(os.getenv("KSYLIAN_BACKUP_DIR", "/mnt/hdd/ksylian-backups"))
TOKEN = os.getenv("KSYLIAN_AGENT_TOKEN", "")

app = FastAPI(title="Ksylian Host Agent", version="0.1.0")


def require_token(x_ksylian_token: str | None = Header(default=None)) -> None:
    if TOKEN and x_ksylian_token != TOKEN:
        raise HTTPException(status_code=401, detail="Invalid agent token")


def run(command: list[str], timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)


def service_state(service: str) -> Literal["online", "deploying", "offline"]:
    result = run(["systemctl", "is-active", service])
    if result.stdout.strip() == "active":
        return "online"
    if result.stdout.strip() in {"activating", "reloading"}:
        return "deploying"
    return "offline"


def format_bytes(value: int) -> str:
    if value >= 1024**3:
        return f"{value / 1024**3:.1f} GB"
    return f"{round(value / 1024**2)} MB"


def format_duration(seconds: float) -> str:
    minutes = int(seconds // 60)
    days, minutes = divmod(minutes, 60 * 24)
    hours, minutes = divmod(minutes, 60)
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def read_cpu_totals() -> tuple[int, int]:
    line = Path("/proc/stat").read_text().splitlines()[0]
    values = [int(value) for value in line.split()[1:]]
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    total = sum(values)
    return idle, total


def cpu_percent() -> int:
    idle_a, total_a = read_cpu_totals()
    time.sleep(0.2)
    idle_b, total_b = read_cpu_totals()
    total_delta = total_b - total_a
    idle_delta = idle_b - idle_a
    if total_delta <= 0:
        return 0
    return round((1 - idle_delta / total_delta) * 100)


def meminfo() -> dict[str, int]:
    result: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, raw_value = line.split(":", 1)
        value = raw_value.strip().split()[0]
        result[key] = int(value) * 1024
    return result


def metric_usage(used: int, total: int) -> MetricUsage:
    percent = round((used / total) * 100) if total else 0
    return MetricUsage(
        used=used,
        total=total,
        percent=percent,
        used_label=format_bytes(used),
        total_label=format_bytes(total),
    )


def memory_usage() -> tuple[MetricUsage, MetricUsage]:
    info = meminfo()
    memory_total = info.get("MemTotal", 0)
    memory_available = info.get("MemAvailable", 0)
    swap_total = info.get("SwapTotal", 0)
    swap_free = info.get("SwapFree", 0)
    return (
        metric_usage(memory_total - memory_available, memory_total),
        metric_usage(swap_total - swap_free, swap_total),
    )


def disk_usage() -> list[DiskUsage]:
    mounts = ["/", "/home", "/mnt/hdd"]
    existing_mounts = [mount for mount in mounts if Path(mount).exists()]
    result = run(["df", "-B1", "-P", *existing_mounts])
    disks: list[DiskUsage] = []
    seen: set[str] = set()

    for line in result.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 6:
            continue
        filesystem, total, used, _available, percent, mount = parts[:6]
        if mount in seen:
            continue
        seen.add(mount)
        total_bytes = int(total)
        used_bytes = int(used)
        disks.append(
            DiskUsage(
                mount=mount,
                filesystem=filesystem,
                used=used_bytes,
                total=total_bytes,
                percent=int(percent.rstrip("%")),
                used_label=format_bytes(used_bytes),
                total_label=format_bytes(total_bytes),
            )
        )

    return disks


def top_processes() -> list[ProcessUsage]:
    result = run(["ps", "-eo", "pid,comm,%cpu,%mem,args", "--sort=-%cpu"], timeout=20)
    processes: list[ProcessUsage] = []
    for line in result.stdout.splitlines()[1:8]:
        parts = line.split(maxsplit=4)
        if len(parts) < 5:
            continue
        pid, name, cpu, memory, command = parts
        processes.append(
            ProcessUsage(
                pid=int(pid),
                name=name,
                cpu=round(float(cpu), 1),
                memory=round(float(memory), 1),
                command=command[:120],
            )
        )
    return processes


def host_ips() -> list[str]:
    result = run(["hostname", "-I"])
    ips = [item for item in result.stdout.split() if item]
    if ips:
        return ips
    try:
        return [socket.gethostbyname(socket.gethostname())]
    except OSError:
        return []


def temperature_label() -> str:
    for path in Path("/sys/class/thermal").glob("thermal_zone*/temp"):
        try:
            value = int(path.read_text().strip())
        except ValueError:
            continue
        if value > 0:
            return f"{value / 1000:.0f}°C"
    return "n/a"


def service_cgroup_path(service: str) -> Path | None:
    result = run(["systemctl", "show", service, "-p", "ControlGroup", "--value"])
    cgroup = result.stdout.strip().lstrip("/")
    if not cgroup:
        return None
    return Path("/sys/fs/cgroup") / cgroup


def service_pids(service: str) -> list[str]:
    cgroup_path = service_cgroup_path(service)
    if cgroup_path:
        proc_file = cgroup_path / "cgroup.procs"
        if proc_file.exists():
            return [line.strip() for line in proc_file.read_text().splitlines() if line.strip()]

    result = run(["systemctl", "show", service, "-p", "MainPID", "--value"])
    pid = result.stdout.strip()
    return [pid] if pid and pid != "0" else []


def service_usage(service: str) -> tuple[int, str]:
    memory_result = run(["systemctl", "show", service, "-p", "MemoryCurrent", "--value"])
    try:
        memory = int(memory_result.stdout.strip())
    except ValueError:
        memory = 0

    pids = service_pids(service)
    if not pids:
        return 0, format_bytes(memory) if memory else "0 MB"

    result = run(["ps", "-p", ",".join(pids), "-o", "%cpu="])
    cpu = round(sum(float(value) for value in result.stdout.split() if value))
    return cpu, format_bytes(memory) if memory else "0 MB"


def folder_size(path: Path) -> str:
    if not path.exists():
        return "0 MB"

    result = run(["du", "-sh", str(path)], timeout=60)
    if result.returncode != 0:
        return "unknown"
    return result.stdout.split()[0]


def to_agent_server(server_id: str) -> AgentServer:
    config = SERVERS[server_id]
    cpu, ram = service_usage(config["service"])

    return AgentServer(
        id=server_id,
        name=config["name"],
        pack=config["pack"],
        version=config["version"],
        state=service_state(config["service"]),
        players="-",
        ram=ram,
        cpu=cpu,
        disk=folder_size(config["path"]),
        address=config["address"],
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "ksylian-agent"}


@app.get("/servers", response_model=list[AgentServer])
def servers(x_ksylian_token: str | None = Header(default=None)) -> list[AgentServer]:
    require_token(x_ksylian_token)
    return [to_agent_server(server_id) for server_id in SERVERS]


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
    for server_id, config in SERVERS.items():
        cpu, ram = service_usage(config["service"])
        services.append(
            ServiceUsage(
                id=server_id,
                name=config["name"],
                state=service_state(config["service"]),
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
    config = SERVERS.get(server_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Server not found")

    result = run(["journalctl", "-u", config["service"], "-n", "80", "--no-pager", "-o", "short-iso"], timeout=30)
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=result.stderr.strip() or "Failed to read logs")
    return [line for line in result.stdout.splitlines() if line]


@app.post("/servers/{server_id}/actions/{action}", response_model=AgentActionResult)
def action(
    server_id: str,
    action: Literal["start", "restart", "stop", "backup"],
    x_ksylian_token: str | None = Header(default=None),
) -> AgentActionResult:
    require_token(x_ksylian_token)
    config = SERVERS.get(server_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Server not found")

    if action in {"start", "restart", "stop"}:
        result = run(["systemctl", action, config["service"]], timeout=60)
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=result.stderr.strip() or f"systemctl {action} failed")
        message = f"{config['name']}: {action} completed"
    else:
        source = config["backup_path"]
        if not source.exists():
            raise HTTPException(status_code=404, detail=f"Backup source not found: {source}")

        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        archive = BACKUP_DIR / f"{server_id}-{stamp}.tar.gz"

        with tarfile.open(archive, "w:gz") as tar:
            tar.add(source, arcname=source.name)

        message = f"{config['name']}: backup created at {archive}"

    return AgentActionResult(ok=True, message=message, server=to_agent_server(server_id))


@app.get("/backups")
def backups(x_ksylian_token: str | None = Header(default=None)) -> list[dict[str, str]]:
    require_token(x_ksylian_token)
    if not BACKUP_DIR.exists():
        return []

    items = []
    for path in sorted(BACKUP_DIR.glob("*.tar.gz"), key=lambda item: item.stat().st_mtime, reverse=True):
        server_id = path.name.split("-", 1)[0]
        items.append(
            {
                "id": path.stem,
                "name": path.name,
                "size": folder_size(path),
                "created": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
                "server_id": server_id,
            }
        )
    return items
