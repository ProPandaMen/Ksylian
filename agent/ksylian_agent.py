from __future__ import annotations

import os
import json
import re
import shutil
import shlex
import socket
import subprocess
import tarfile
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field


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
    type: Literal["legacy", "vanilla", "fabric", "forge"]
    pack: str
    version: str
    port: int
    service: str
    path: str
    backup_path: str
    address: str
    created_at: str
    managed: bool = False
    start_command: list[str] = Field(default_factory=list)


class CreateAgentServerRequest(BaseModel):
    name: str
    type: Literal["vanilla", "fabric", "forge"]
    version: str = "1.20.1"


class AgentActionResult(BaseModel):
    ok: bool
    message: str
    server: AgentServer


class ServerConfigPayload(BaseModel):
    content: str


class AppUpdateRequest(BaseModel):
    target_version: str


class AppUpdateResult(BaseModel):
    ok: bool
    message: str
    target_version: str


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
APP_DIR = Path(os.getenv("KSYLIAN_APP_DIR", "/opt/ksylian"))
APP_ENV_FILE = Path(os.getenv("KSYLIAN_ENV_FILE", str(APP_DIR / "deploy/.env")))
APP_COMPOSE_FILE = Path(os.getenv("KSYLIAN_COMPOSE_FILE", str(APP_DIR / "deploy/docker-compose.yml")))
UPDATE_LOG = DATA_DIR / "update.log"
TOKEN = os.getenv("KSYLIAN_AGENT_TOKEN", "")
PUBLIC_DOMAIN = os.getenv("KSYLIAN_PUBLIC_DOMAIN", os.getenv("KSYLIAN_PROXY_DOMAIN", "")).strip().lower().strip(".")
PROXY_DOMAIN = os.getenv("KSYLIAN_PROXY_DOMAIN", PUBLIC_DOMAIN).strip().lower().strip(".")
PROXY_PORT = os.getenv("KSYLIAN_PROXY_PORT", "25565")
MINECRAFT_VERSION_MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
FABRIC_META_API_URL = "https://meta.fabricmc.net/v2"
FORGE_MAVEN_URL = "https://maven.minecraftforge.net/net/minecraftforge/forge"
SYSTEMD_DIR = Path("/etc/systemd/system")

app = FastAPI(title="Ksylian Host Agent", version="0.1.0")


def require_token(x_ksylian_token: str | None = Header(default=None)) -> None:
    if TOKEN and x_ksylian_token != TOKEN:
        raise HTTPException(status_code=401, detail="Invalid agent token")


def run(command: list[str], timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)


def run_in(command: list[str], cwd: Path, timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False)


def encode_varint(value: int) -> bytes:
    result = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        result.append(byte | 0x80 if value else byte)
        if not value:
            return bytes(result)


def read_socket_varint(sock: socket.socket) -> int:
    value = 0
    for position in range(5):
        byte = sock.recv(1)
        if not byte:
            raise OSError("Socket closed while reading varint")
        value |= (byte[0] & 0x7F) << (7 * position)
        if not byte[0] & 0x80:
            return value
    raise OSError("Varint is too large")


def minecraft_packet(packet_id: int, payload: bytes = b"") -> bytes:
    body = encode_varint(packet_id) + payload
    return encode_varint(len(body)) + body


def minecraft_utf(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return encode_varint(len(encoded)) + encoded


def append_update_log(message: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with UPDATE_LOG.open("a") as file:
        file.write(f"[{timestamp}] {message}\n")


def validate_update_target(target_version: str) -> str:
    target = target_version.strip()
    if not re.fullmatch(r"v[0-9][0-9A-Za-z._-]*", target):
        raise HTTPException(status_code=400, detail="Target version must be a release tag like v0.6.0")
    return target


def ensure_updater_configured() -> None:
    if not APP_DIR.exists() or not (APP_DIR / ".git").exists():
        raise HTTPException(
            status_code=409,
            detail=f"Ksylian app directory is not configured or is not a git repository: {APP_DIR}",
        )
    if not APP_COMPOSE_FILE.exists():
        raise HTTPException(status_code=409, detail=f"Docker compose file was not found: {APP_COMPOSE_FILE}")


def update_script_path() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    script_path = DATA_DIR / "apply-update.sh"
    script_path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                'TARGET_VERSION="$1"',
                f"APP_DIR={shlex.quote(str(APP_DIR))}",
                f"ENV_FILE={shlex.quote(str(APP_ENV_FILE))}",
                f"COMPOSE_FILE={shlex.quote(str(APP_COMPOSE_FILE))}",
                f"LOG_FILE={shlex.quote(str(UPDATE_LOG))}",
                'log() { printf "[%s] %s\\n" "$(date +%F\\ %T)" "$*" >> "$LOG_FILE"; }',
                'log "Starting update to ${TARGET_VERSION}"',
                'cd "$APP_DIR"',
                "git fetch --tags origin",
                'git checkout --force "$TARGET_VERSION"',
                'SHA="$(git rev-parse --short HEAD)"',
                'test -f "$ENV_FILE" || cp deploy/.env.example "$ENV_FILE"',
                'sed -i "s/^KSYLIAN_BUILD_VERSION=.*/KSYLIAN_BUILD_VERSION=${TARGET_VERSION}/" "$ENV_FILE"',
                'sed -i "s/^KSYLIAN_BUILD_SHA=.*/KSYLIAN_BUILD_SHA=${SHA}/" "$ENV_FILE"',
                'docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --build',
                "docker image prune -f >/dev/null || true",
                'log "Update to ${TARGET_VERSION} completed (${SHA})"',
                "",
            ]
        )
    )
    script_path.chmod(0o700)
    return script_path


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
    if server_type == "fabric":
        return "Fabric"
    if server_type == "forge":
        return "Forge"
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


def request_json(url: str, timeout: int = 30) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "Ksylian-Agent/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise HTTPException(status_code=502, detail=f"Download metadata request failed: HTTP {error.code}") from error
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=502, detail=f"Download metadata request failed: {error}") from error


def request_text(url: str, timeout: int = 30) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Ksylian-Agent/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        raise HTTPException(status_code=502, detail=f"Download metadata request failed: HTTP {error.code}") from error
    except (urllib.error.URLError, TimeoutError, UnicodeDecodeError) as error:
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


def latest_fabric_component(path: str, label: str) -> str:
    items = request_json(f"{FABRIC_META_API_URL}{path}")
    if not isinstance(items, list):
        raise HTTPException(status_code=502, detail=f"Fabric {label} metadata is invalid")
    for item in items:
        if isinstance(item, dict) and item.get("stable") is True and item.get("version"):
            return str(item["version"])
    for item in items:
        if isinstance(item, dict) and item.get("version"):
            return str(item["version"])
    raise HTTPException(status_code=404, detail=f"Fabric {label} version was not found")


def download_fabric_server_jar(version: str, destination: Path) -> None:
    loaders = request_json(f"{FABRIC_META_API_URL}/versions/loader/{version}")
    if not isinstance(loaders, list) or not loaders:
        raise HTTPException(status_code=404, detail=f"Fabric loader for Minecraft {version} was not found")

    loader_version = ""
    for item in loaders:
        loader = item.get("loader") if isinstance(item, dict) else None
        if isinstance(loader, dict) and loader.get("stable") is True and loader.get("version"):
            loader_version = str(loader["version"])
            break
    if not loader_version:
        loader = loaders[0].get("loader") if isinstance(loaders[0], dict) else None
        loader_version = str(loader.get("version") or "") if isinstance(loader, dict) else ""
    if not loader_version:
        raise HTTPException(status_code=404, detail=f"Fabric loader for Minecraft {version} was not found")

    installer_version = latest_fabric_component("/versions/installer", "installer")
    download_file(
        f"{FABRIC_META_API_URL}/versions/loader/{version}/{loader_version}/{installer_version}/server/jar",
        destination,
    )


def forge_versions() -> list[str]:
    metadata = request_text(f"{FORGE_MAVEN_URL}/maven-metadata.xml")
    try:
        root = ET.fromstring(metadata)
    except ET.ParseError as error:
        raise HTTPException(status_code=502, detail="Forge metadata is invalid") from error
    return [item.text.strip() for item in root.findall(".//version") if item.text and item.text.strip()]


def latest_forge_version(minecraft_version: str) -> str:
    prefix = f"{minecraft_version}-"
    matches = [version for version in forge_versions() if version.startswith(prefix)]
    if not matches:
        raise HTTPException(status_code=404, detail=f"Forge build for Minecraft {minecraft_version} was not found")
    return matches[-1]


def install_forge_server(server: StoredServer) -> list[str]:
    server_path = Path(server.path)
    forge_version = latest_forge_version(server.version)
    installer = server_path / f"forge-{forge_version}-installer.jar"
    download_file(f"{FORGE_MAVEN_URL}/{forge_version}/forge-{forge_version}-installer.jar", installer)

    result = run_in([java_binary(), "-jar", str(installer), "--installServer"], cwd=server_path, timeout=600)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "Forge installer failed"
        raise HTTPException(status_code=502, detail=detail)

    unix_args = server_path / "libraries" / "net" / "minecraftforge" / "forge" / forge_version / "unix_args.txt"
    if unix_args.exists():
        return [
            java_binary(),
            "-Xms1G",
            "-Xmx2G",
            "@libraries/net/minecraftforge/forge/{forge_version}/unix_args.txt".format(forge_version=forge_version),
            "nogui",
        ]

    forge_jar = next(server_path.glob(f"forge-{forge_version}*.jar"), None)
    if forge_jar:
        return [java_binary(), "-Xms1G", "-Xmx2G", "-jar", forge_jar.name, "nogui"]

    raise HTTPException(status_code=502, detail="Forge installer did not produce a runnable server")


def default_start_command() -> list[str]:
    return [java_binary(), "-Xms1G", "-Xmx2G", "-jar", "server.jar", "nogui"]


def provision_server_files(server: StoredServer) -> StoredServer:
    destination = Path(server.path) / "server.jar"
    if server.type == "vanilla":
        if not destination.exists():
            download_vanilla_server_jar(server.version, destination)
        server.start_command = default_start_command()
        return server
    if server.type == "fabric":
        if not destination.exists():
            download_fabric_server_jar(server.version, destination)
        server.start_command = default_start_command()
        return server
    if server.type == "forge":
        if not server.start_command:
            server.start_command = install_forge_server(server)
        return server
    raise HTTPException(status_code=400, detail=f"Server type {server.type} cannot be provisioned")


def java_binary() -> str:
    binary = shutil.which("java")
    if not binary:
        raise HTTPException(status_code=500, detail="Java is not installed on this host")
    return binary


def write_systemd_unit(server: StoredServer) -> None:
    unit_path = SYSTEMD_DIR / server.service
    start_command = server.start_command or default_start_command()
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
            f"ExecStart={shlex.join(start_command)}",
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


def ensure_server_provisioned(server: StoredServer) -> StoredServer:
    if not server.managed:
        return server

    write_server_scaffold(server)
    server = provision_server_files(server)

    unit_path = SYSTEMD_DIR / server.service
    if not unit_path.exists():
        write_systemd_unit(server)
    return server


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


def read_exact(sock: socket.socket, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        chunk = sock.recv(size - len(chunks))
        if not chunk:
            raise OSError("Socket closed while reading packet")
        chunks.extend(chunk)
    return bytes(chunks)


def minecraft_player_status(port: int, host: str = "127.0.0.1") -> str:
    try:
        with socket.create_connection((host, port), timeout=1.5) as sock:
            sock.settimeout(1.5)
            handshake = b"".join(
                [
                    encode_varint(765),
                    minecraft_utf(host),
                    port.to_bytes(2, "big"),
                    encode_varint(1),
                ]
            )
            sock.sendall(minecraft_packet(0, handshake))
            sock.sendall(minecraft_packet(0))

            packet_length = read_socket_varint(sock)
            packet = read_exact(sock, packet_length)
            packet_id_offset = 0
            packet_id, packet_id_offset = read_response_varint(packet, packet_id_offset)
            if packet_id != 0:
                return "-"
            response_length, offset = read_response_varint(packet, packet_id_offset)
            response = read_exact_from_buffer(packet, offset, response_length).decode("utf-8")
            data = json.loads(response)
            players = data.get("players") if isinstance(data, dict) else None
            if not isinstance(players, dict):
                return "-"
            online = int(players.get("online", 0))
            maximum = int(players.get("max", 0))
            return f"{online} / {maximum}" if maximum else str(online)
    except (OSError, TimeoutError, ValueError, json.JSONDecodeError):
        return "-"


def configured_max_players(server_path: Path) -> int:
    properties_path = server_path / "server.properties"
    if not properties_path.exists():
        return 20
    try:
        for line in properties_path.read_text().splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "max-players":
                return max(int(value.strip()), 0)
    except (OSError, ValueError):
        return 20
    return 20


def server_players_label(config: StoredServer, state: str) -> str:
    server_path = Path(config.path)
    maximum = configured_max_players(server_path)
    if state != "online":
        return f"0 / {maximum}"

    status = minecraft_player_status(config.port)
    if status == "-":
        return f"0 / {maximum}"
    return status


def read_response_varint(buffer: bytes, offset: int = 0) -> tuple[int, int]:
    value = 0
    for position in range(5):
        if offset + position >= len(buffer):
            raise ValueError("Incomplete varint")
        byte = buffer[offset + position]
        value |= (byte & 0x7F) << (7 * position)
        if not byte & 0x80:
            return value, offset + position + 1
    raise ValueError("Varint is too large")


def read_exact_from_buffer(buffer: bytes, offset: int, size: int) -> bytes:
    end = offset + size
    if end > len(buffer):
        raise ValueError("Incomplete packet")
    return buffer[offset:end]


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


def public_server_address(config: StoredServer) -> str:
    if config.managed and PUBLIC_DOMAIN:
        return f"{config.id}.{PUBLIC_DOMAIN}"
    return config.address


def to_agent_server(server_id: str) -> AgentServer:
    config = load_server_store()[server_id]
    cpu, ram = service_usage(config.service)
    state = service_state(config.service)

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


@app.post("/app/update", response_model=AppUpdateResult)
def update_app(payload: AppUpdateRequest, x_ksylian_token: str | None = Header(default=None)) -> AppUpdateResult:
    require_token(x_ksylian_token)
    target_version = validate_update_target(payload.target_version)
    ensure_updater_configured()
    script_path = update_script_path()
    append_update_log(f"Queued update to {target_version}")
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
    server = ensure_server_provisioned(server)
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


@app.get("/servers/{server_id}/config", response_model=ServerConfigPayload)
def server_config(server_id: str, x_ksylian_token: str | None = Header(default=None)) -> ServerConfigPayload:
    require_token(x_ksylian_token)
    config = load_server_store().get(server_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Server not found")

    properties_path = Path(config.path) / "server.properties"
    if not properties_path.exists():
        ensure_server_provisioned(config)
    if not properties_path.exists():
        raise HTTPException(status_code=404, detail="server.properties was not found")

    try:
        content = properties_path.read_text()
    except OSError as error:
        raise HTTPException(status_code=500, detail="Failed to read server.properties") from error

    return ServerConfigPayload(content=content)


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

    server_path = Path(config.path)
    server_path.mkdir(parents=True, exist_ok=True)
    properties_path = server_path / "server.properties"
    content = payload.content.replace("\r\n", "\n").replace("\r", "\n")
    if not content.endswith("\n"):
        content += "\n"

    try:
        properties_path.write_text(content)
    except OSError as error:
        raise HTTPException(status_code=500, detail="Failed to write server.properties") from error

    return ServerConfigPayload(content=content)


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
        shutil.rmtree(config.path, ignore_errors=True)
        store.pop(server_id, None)
        disabled.discard(server_id)
        save_server_store(store)
    else:
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
