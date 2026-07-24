from __future__ import annotations

import json
import os
import re
import secrets
import shlex
import shutil
import socket
from pathlib import Path

from fastapi import HTTPException

from .config import SERVER_ROOT
from .monitoring import format_bytes, host_ips
from .processes import run, service_state
from .schemas import StoredServer
from .security import server_base_path


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


def rcon_packet(request_id: int, packet_type: int, payload: str) -> bytes:
    body = (
        request_id.to_bytes(4, "little", signed=True)
        + packet_type.to_bytes(4, "little", signed=True)
        + payload.encode("utf-8")
        + b"\x00\x00"
    )
    return len(body).to_bytes(4, "little", signed=True) + body


def read_rcon_packet(sock: socket.socket) -> tuple[int, int, str]:
    length_bytes = read_exact(sock, 4)
    length = int.from_bytes(length_bytes, "little", signed=True)
    if length < 10 or length > 4 * 1024 * 1024:
        raise OSError("Invalid RCON packet length")
    body = read_exact(sock, length)
    request_id = int.from_bytes(body[0:4], "little", signed=True)
    packet_type = int.from_bytes(body[4:8], "little", signed=True)
    payload = body[8:-2].decode("utf-8", errors="replace")
    return request_id, packet_type, payload


def minecraft_utf(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return encode_varint(len(encoded)) + encoded




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
    if server_type == "fabric":
        return "Fabric"
    if server_type == "forge":
        return "Forge"
    if server_type == "neoforge":
        return "NeoForge"
    return server_type


def normalize_ram(value: str, fallback: str) -> str:
    candidate = value.strip().upper().replace(" ", "")
    if re.fullmatch(r"[1-9][0-9]*(M|G)", candidate):
        return candidate
    return fallback


def ram_to_bytes(value: str) -> int:
    normalized = normalize_ram(value, "0M")
    amount = int(normalized[:-1])
    return amount * (1024**3 if normalized.endswith("G") else 1024**2)


def normalize_cpu_limit(value: int) -> int:
    return max(10, min(int(value or 100), 400))


def normalize_jvm_args(value: str) -> list[str]:
    try:
        args = shlex.split(value)
    except ValueError:
        return []
    forbidden_prefixes = ("-jar", "-cp", "-classpath", "@")
    return [arg for arg in args if not arg.startswith(forbidden_prefixes) and "\x00" not in arg][:24]


def ensure_disk_space_for_server(server: StoredServer) -> None:
    SERVER_ROOT.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(SERVER_ROOT)
    required = max(2 * 1024**3, ram_to_bytes(server.max_ram))
    if usage.free < required:
        raise HTTPException(
            status_code=507,
            detail=f"Not enough free disk space. Need at least {format_bytes(required)}, available {format_bytes(usage.free)}",
        )


def server_warnings(server: StoredServer) -> list[str]:
    warnings: list[str] = []
    try:
        usage = shutil.disk_usage(server_base_path(server) if Path(server.path).exists() else SERVER_ROOT)
        if usage.free < max(2 * 1024**3, ram_to_bytes(server.max_ram)):
            warnings.append("Мало свободного места на диске")
    except OSError:
        warnings.append("Не удалось проверить свободное место")
    if ram_to_bytes(server.max_ram) > shutil.disk_usage(SERVER_ROOT).free:
        warnings.append("Лимит RAM больше текущего свободного места на диске")
    if service_state(server.service) == "running" and minecraft_player_status(server.port) == "-":
        warnings.append("Процесс запущен, но Minecraft status ping не отвечает")
    return warnings


def start_command_for_server(server: StoredServer, java: str) -> list[str]:
    min_ram = normalize_ram(server.min_ram, "1G")
    max_ram = normalize_ram(server.max_ram, "2G")
    return [java, f"-Xms{min_ram}", f"-Xmx{max_ram}", *server.jvm_args, "-jar", "server.jar", "nogui"]


def write_server_scaffold(server: StoredServer) -> None:
    server_path = server_base_path(server)
    if not server.rcon_password:
        server.rcon_password = secrets.token_urlsafe(24)
    if not server.rcon_port:
        server.rcon_port = min(server.port + 10000, 65535)
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
                    "enable-rcon=true",
                    f"rcon.port={server.rcon_port}",
                    f"rcon.password={server.rcon_password}",
                    "max-players=20",
                    "view-distance=10",
                    "simulation-distance=10",
                    "",
                ]
            )
        )
    (server_path / "ksylian.json").write_text(json.dumps(server.model_dump(), ensure_ascii=False, indent=2))




def minecraft_version_key(version: str) -> tuple[int, int, int]:
    match = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?", version)
    if not match:
        return (0, 0, 0)
    return tuple(int(part or 0) for part in match.groups())


def required_java_major(minecraft_version: str) -> int:
    version = minecraft_version_key(minecraft_version)
    if version >= (1, 20, 5):
        return 21
    if version >= (1, 18, 0):
        return 17
    return 8


def java_major_version(binary: str) -> int | None:
    result = run([binary, "-version"], timeout=10)
    output = f"{result.stdout}\n{result.stderr}"
    match = re.search(r'version "([^"]+)"', output)
    if not match:
        return None
    version = match.group(1)
    if version.startswith("1."):
        parts = version.split(".")
        return int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
    major = version.split(".", 1)[0]
    return int(major) if major.isdigit() else None


def java_candidates(required_major: int, selected_runtime: str = "auto") -> list[str]:
    candidates: list[str] = []
    if selected_runtime in {"8", "17", "21"}:
        selected_value = os.getenv(f"KSYLIAN_JAVA_{selected_runtime}", "")
        if selected_value:
            candidates.append(selected_value)
        candidates.extend(common_java_paths(int(selected_runtime)))
    env_value = os.getenv(f"KSYLIAN_JAVA_{required_major}", "")
    if env_value:
        candidates.append(env_value)
    candidates.extend(common_java_paths(required_major))
    for major in (required_major, 21, 17, 8):
        env_candidate = os.getenv(f"KSYLIAN_JAVA_{major}", "")
        if env_candidate:
            candidates.append(env_candidate)
        candidates.extend(common_java_paths(major))
    default = shutil.which("java")
    if default:
        candidates.append(default)
    return list(dict.fromkeys(candidates))


def common_java_paths(major: int) -> list[str]:
    return [
        f"/usr/lib/jvm/java-{major}-openjdk-amd64/bin/java",
        f"/usr/lib/jvm/java-1.{major}.0-openjdk-amd64/bin/java",
        f"/usr/lib/jvm/temurin-{major}-jdk-amd64/bin/java",
        f"/usr/lib/jvm/jdk-{major}/bin/java",
    ]


def java_binary(minecraft_version: str = "", selected_runtime: str = "auto") -> str:
    required_major = required_java_major(minecraft_version) if minecraft_version else 8
    if selected_runtime in {"8", "17", "21"}:
        required_major = max(required_major, int(selected_runtime))
    checked: list[str] = []
    compatible: str | None = None
    for candidate in java_candidates(required_major, selected_runtime):
        major = java_major_version(candidate)
        checked.append(f"{candidate} ({major or 'unknown'})")
        if major == required_major:
            return candidate
        if major and major > required_major and compatible is None:
            compatible = candidate
    if compatible and selected_runtime in {"21"}:
        return compatible
    if not checked:
        raise HTTPException(status_code=500, detail="Java is not installed on this host")
    raise HTTPException(
        status_code=409,
        detail=f"Minecraft {minecraft_version} requires Java {required_major}+. Checked: {', '.join(checked)}",
    )




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


def execute_rcon(server: StoredServer, command: str) -> str:
    if not server.rcon_port or not server.rcon_password:
        raise HTTPException(status_code=409, detail="RCON is not configured for this server")
    if len(command.encode("utf-8")) > 4096:
        raise HTTPException(status_code=413, detail="RCON command is too large")

    try:
        with socket.create_connection(("127.0.0.1", server.rcon_port), timeout=4) as sock:
            sock.settimeout(4)
            sock.sendall(rcon_packet(1, 3, server.rcon_password))
            request_id, _, _ = read_rcon_packet(sock)
            if request_id == -1:
                raise HTTPException(status_code=401, detail="RCON authentication failed")
            sock.sendall(rcon_packet(2, 2, command))
            _, _, output = read_rcon_packet(sock)
            return output
    except HTTPException:
        raise
    except OSError as error:
        raise HTTPException(status_code=502, detail=f"RCON is unavailable: {error}") from error


def rcon_available(server: StoredServer) -> bool:
    try:
        execute_rcon(server, "list")
        return True
    except HTTPException:
        return False


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
    server_path = server_base_path(config) if config.managed else Path(config.path)
    maximum = configured_max_players(server_path)
    if state != "running":
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
