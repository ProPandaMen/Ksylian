from __future__ import annotations

import socket
import time
from pathlib import Path

from .processes import run
from .schemas import DiskUsage, MetricUsage, ProcessUsage


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
    cpu = min(round(sum(float(value) for value in result.stdout.split() if value)), 100)
    return cpu, format_bytes(memory) if memory else "0 MB"


def service_exit_code(service: str) -> int | None:
    result = run(["systemctl", "show", service, "-p", "ExecMainStatus", "--value"], timeout=10)
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None


def folder_size(path: Path) -> str:
    if not path.exists():
        return "0 MB"

    result = run(["du", "-sh", str(path)], timeout=60)
    if result.returncode != 0:
        return "unknown"
    return result.stdout.split()[0]


