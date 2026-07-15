from __future__ import annotations

import os
import subprocess
import tarfile
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
