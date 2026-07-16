from __future__ import annotations

import os
import json
import re
import shutil
import socket
import subprocess
import tarfile
import time
import urllib.error
import urllib.request
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


class StoredServer(BaseModel):
    id: str
    name: str
    type: Literal["legacy", "vanilla", "paper", "purpur"]
    pack: str
    version: str
    port: int
    service: str
    path: str
    backup_path: str
    address: str
    created_at: str
    managed: bool = False


class CreateAgentServerRequest(BaseModel):
    name: str
    type: Literal["vanilla", "paper", "purpur"]
    version: str = "1.20.1"


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
DATA_DIR = Path(os.getenv("KSYLIAN_DATA_DIR", "/var/lib/ksylian-agent"))
DISABLED_SERVERS_FILE = DATA_DIR / "disabled-servers.json"
SERVERS_FILE = DATA_DIR / "servers.json"
SERVER_ROOT = Path(os.getenv("KSYLIAN_SERVER_ROOT", "/opt/ksylian/servers"))
TOKEN = os.getenv("KSYLIAN_AGENT_TOKEN", "")
MINECRAFT_VERSION_MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
PAPER_API_URL = "https://api.papermc.io/v2/projects/paper"
SYSTEMD_DIR = Path("/etc/systemd/system")

app = FastAPI(title="Ksylian Host Agent", version="0.1.0")


def require_token(x_ksylian_token: str | None = Header(default=None)) -> None:
    if TOKEN and x_ksylian_token != TOKEN:
        raise HTTPException(status_code=401, detail="Invalid agent token")


def run(command: list[str], timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)


def disabled_server_ids() -> set[str]:
    if not DISABLED_SERVERS_FILE.exists():
        return set()
    try:
        data = json.loads(DISABLED_SERVERS_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return set()
    if not isinstance(data, list):
        return set()
    return {item for item in data if isinstance(item, str)}


def save_disabled_server_ids(server_ids: set[str]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DISABLED_SERVERS_FILE.write_text(json.dumps(sorted(server_ids), indent=2))


def legacy_server_store() -> dict[str, StoredServer]:
    result: dict[str, StoredServer] = {}
    for server_id, config in SERVERS.items():
        port = int(str(config["address"]).rsplit(":", 1)[-1])
        result[server_id] = StoredServer(
            id=server_id,
            name=str(config["name"]),
            type="legacy",
            pack=str(config["pack"]),
            version=str(config["version"]),
            port=port,
            service=str(config["service"]),
            path=str(config["path"]),
            backup_path=str(config["backup_path"]),
            address=str(config["address"]),
            created_at="legacy",
            managed=False,
        )
    return result


def load_server_store() -> dict[str, StoredServer]:
    if not SERVERS_FILE.exists():
        return legacy_server_store()

    try:
        data = json.loads(SERVERS_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return legacy_server_store()

    if not isinstance(data, list):
        return legacy_server_store()

    result: dict[str, StoredServer] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            server = StoredServer(**item)
        except Exception:
            continue
        result[server.id] = server
    return result


def save_server_store(servers: dict[str, StoredServer]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = [server.model_dump() for server in sorted(servers.values(), key=lambda item: item.created_at)]
    SERVERS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2))


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", value.lower().strip())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "server"


def host_primary_ip() -> str:
    for ip in host_ips():
        if not ip.startswith("127.") and not ip.startswith("172."):
            return ip
    return "127.0.0.1"


def is_port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("0.0.0.0", port))
        except OSError:
            return False
    return True


def allocate_port(servers: dict[str, StoredServer], start: int = 25565) -> int:
    used_ports = {server.port for server in servers.values()}
    for port in range(start, start + 200):
        if port not in used_ports and is_port_available(port):
            return port
    raise HTTPException(status_code=507, detail="No free Minecraft ports available")


def server_type_label(server_type: str) -> str:
    if server_type == "vanilla":
        return "Vanilla"
    if server_type == "paper":
        return "Paper"
    if server_type == "purpur":
        return "Purpur"
    return server_type


def write_server_scaffold(server: StoredServer) -> None:
    server_path = Path(server.path)
    server_path.mkdir(parents=True, exist_ok=True)
    (server_path / "mods").mkdir(exist_ok=True)
    (server_path / "logs").mkdir(exist_ok=True)
    (server_path / "world").mkdir(exist_ok=True)
    eula_path = server_path / "eula.txt"
    if not eula_path.exists():
        eula_path.write_text("eula=true\n")

    properties_path = server_path / "server.properties"
    if not properties_path.exists():
        properties_path.write_text(
            "\n".join(
                [
                    f"server-port={server.port}",
                    f"motd={server.name}",
                    "enable-query=false",
                    "online-mode=true",
                    "max-players=20",
                    "view-distance=10",
                    "simulation-distance=10",
                    "",
                ]
            )
        )
    (server_path / "ksylian.json").write_text(json.dumps(server.model_dump(), ensure_ascii=False, indent=2))


def request_json(url: str, timeout: int = 30) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "Ksylian-Agent/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise HTTPException(status_code=502, detail=f"Download metadata request failed: HTTP {error.code}") from error
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=502, detail=f"Download metadata request failed: {error}") from error


def download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(f"{destination.suffix}.tmp")
    request = urllib.request.Request(url, headers={"User-Agent": "Ksylian-Agent/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=180) as response, temporary.open("wb") as file:
            shutil.copyfileobj(response, file)
        temporary.replace(destination)
    except urllib.error.HTTPError as error:
        temporary.unlink(missing_ok=True)
        raise HTTPException(status_code=502, detail=f"Server jar download failed: HTTP {error.code}") from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        temporary.unlink(missing_ok=True)
        raise HTTPException(status_code=502, detail=f"Server jar download failed: {error}") from error


def download_vanilla_server_jar(version: str, destination: Path) -> None:
    manifest = request_json(MINECRAFT_VERSION_MANIFEST_URL)
    versions = manifest.get("versions")
    if not isinstance(versions, list):
        raise HTTPException(status_code=502, detail="Minecraft version manifest is invalid")

    version_url = ""
    for item in versions:
        if isinstance(item, dict) and item.get("id") == version:
            version_url = str(item.get("url") or "")
            break
    if not version_url:
        raise HTTPException(status_code=404, detail=f"Minecraft version {version} was not found")

    metadata = request_json(version_url)
    server_download = metadata.get("downloads", {}).get("server", {})
    server_url = str(server_download.get("url") or "")
    if not server_url:
        raise HTTPException(status_code=404, detail=f"Server jar for Minecraft {version} was not found")

    download_file(server_url, destination)


def download_paper_server_jar(version: str, destination: Path) -> None:
    builds_metadata = request_json(f"{PAPER_API_URL}/versions/{version}/builds")
    builds = builds_metadata.get("builds")
    if not isinstance(builds, list) or not builds:
        raise HTTPException(status_code=404, detail=f"Paper build for Minecraft {version} was not found")

    build = max(
        (item for item in builds if isinstance(item, dict) and isinstance(item.get("build"), int)),
        key=lambda item: item["build"],
        default=None,
    )
    if not build:
        raise HTTPException(status_code=404, detail=f"Paper build for Minecraft {version} was not found")

    file_name = build.get("downloads", {}).get("application", {}).get("name")
    build_number = build.get("build")
    if not isinstance(file_name, str):
        raise HTTPException(status_code=502, detail="Paper build metadata is invalid")

    download_file(f"{PAPER_API_URL}/versions/{version}/builds/{build_number}/downloads/{file_name}", destination)


def download_server_jar(server: StoredServer) -> None:
    destination = Path(server.path) / "server.jar"
    if server.type == "vanilla":
        download_vanilla_server_jar(server.version, destination)
        return
    if server.type in {"paper", "purpur"}:
        download_paper_server_jar(server.version, destination)
        return
    raise HTTPException(status_code=400, detail=f"Server type {server.type} cannot be provisioned")


def java_binary() -> str:
    binary = shutil.which("java")
    if not binary:
        raise HTTPException(status_code=500, detail="Java is not installed on this host")
    return binary


def write_systemd_unit(server: StoredServer) -> None:
    unit_path = SYSTEMD_DIR / server.service
    content = "\n".join(
        [
            "[Unit]",
            f"Description=Ksylian Minecraft Server {server.name}",
            "After=network.target",
            "",
            "[Service]",
            "Type=simple",
            "User=root",
            f"WorkingDirectory={server.path}",
            f"ExecStart={java_binary()} -Xms1G -Xmx2G -jar server.jar nogui",
            "Restart=on-failure",
            "RestartSec=10",
            "SuccessExitStatus=0 143",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "",
        ]
    )
    unit_path.write_text(content)

    daemon_reload = run(["systemctl", "daemon-reload"], timeout=30)
    if daemon_reload.returncode != 0:
        raise HTTPException(status_code=500, detail=daemon_reload.stderr.strip() or "systemctl daemon-reload failed")

    enable = run(["systemctl", "enable", server.service], timeout=30)
    if enable.returncode != 0:
        raise HTTPException(status_code=500, detail=enable.stderr.strip() or "systemctl enable failed")


def ensure_server_provisioned(server: StoredServer) -> None:
    if not server.managed:
        return

    write_server_scaffold(server)
    jar_path = Path(server.path) / "server.jar"
    if not jar_path.exists():
        download_server_jar(server)

    unit_path = SYSTEMD_DIR / server.service
    if not unit_path.exists():
        write_systemd_unit(server)


def systemctl_issue_can_be_ignored(result: subprocess.CompletedProcess[str]) -> bool:
    message = f"{result.stdout}\n{result.stderr}".lower()
    return "not loaded" in message or "not found" in message or "does not exist" in message


def active_server_ids() -> list[str]:
    disabled = disabled_server_ids()
    return [server_id for server_id in load_server_store() if server_id not in disabled]


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
    cpu = min(round(sum(float(value) for value in result.stdout.split() if value)), 100)
    return cpu, format_bytes(memory) if memory else "0 MB"


def folder_size(path: Path) -> str:
    if not path.exists():
        return "0 MB"

    result = run(["du", "-sh", str(path)], timeout=60)
    if result.returncode != 0:
        return "unknown"
    return result.stdout.split()[0]


def to_agent_server(server_id: str) -> AgentServer:
    config = load_server_store()[server_id]
    cpu, ram = service_usage(config.service)

    return AgentServer(
        id=server_id,
        name=config.name,
        pack=config.pack,
        version=config.version,
        state=service_state(config.service),
        players="-",
        ram=ram,
        cpu=cpu,
        disk=folder_size(Path(config.path)),
        address=config.address,
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "ksylian-agent"}


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
    server_path = SERVER_ROOT / server_id
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
    )
    ensure_server_provisioned(server)
    store[server.id] = server
    save_server_store(store)
    return to_agent_server(server.id)


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


@app.post("/servers/{server_id}/actions/{action}", response_model=AgentActionResult)
def action(
    server_id: str,
    action: Literal["start", "restart", "stop", "backup"],
    x_ksylian_token: str | None = Header(default=None),
) -> AgentActionResult:
    require_token(x_ksylian_token)
    config = load_server_store().get(server_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Server not found")

    if action in {"start", "restart"}:
        ensure_server_provisioned(config)

    if action in {"start", "restart", "stop"}:
        result = run(["systemctl", action, config.service], timeout=60)
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=result.stderr.strip() or f"systemctl {action} failed")
        message = f"{config.name}: {action} completed"
    else:
        source = Path(config.backup_path)
        if not source.exists():
            raise HTTPException(status_code=404, detail=f"Backup source not found: {source}")

        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        archive = BACKUP_DIR / f"{server_id}-{stamp}.tar.gz"

        with tarfile.open(archive, "w:gz") as tar:
            tar.add(source, arcname=source.name)

        message = f"{config.name}: backup created at {archive}"

    return AgentActionResult(ok=True, message=message, server=to_agent_server(server_id))


@app.delete("/servers/{server_id}")
def delete_server(server_id: str, x_ksylian_token: str | None = Header(default=None)) -> dict[str, bool]:
    require_token(x_ksylian_token)
    config = load_server_store().get(server_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Server not found")

    stop_result = run(["systemctl", "stop", config.service], timeout=60)
    if stop_result.returncode != 0 and not (config.managed and systemctl_issue_can_be_ignored(stop_result)):
        raise HTTPException(status_code=500, detail=stop_result.stderr.strip() or "Failed to stop service")

    disable_result = run(["systemctl", "disable", config.service], timeout=60)
    if disable_result.returncode != 0 and not (config.managed and systemctl_issue_can_be_ignored(disable_result)):
        raise HTTPException(status_code=500, detail=disable_result.stderr.strip() or "Failed to disable service")

    disabled = disabled_server_ids()
    disabled.add(server_id)
    save_disabled_server_ids(disabled)
    return {"ok": True}


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
