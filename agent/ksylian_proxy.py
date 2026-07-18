from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path


LISTEN_HOST = os.getenv("KSYLIAN_PROXY_HOST", "0.0.0.0")
LISTEN_PORT = int(os.getenv("KSYLIAN_PROXY_PORT", "25565"))
PUBLIC_DOMAIN = os.getenv("KSYLIAN_PROXY_DOMAIN", "").strip().lower().strip(".")
DATA_DIR = Path(os.getenv("KSYLIAN_DATA_DIR", "/var/lib/ksylian-agent"))
SERVERS_FILE = Path(os.getenv("KSYLIAN_SERVERS_FILE", str(DATA_DIR / "servers.json")))
DISABLED_SERVERS_FILE = Path(os.getenv("KSYLIAN_DISABLED_SERVERS_FILE", str(DATA_DIR / "disabled-servers.json")))
BACKEND_HOST = os.getenv("KSYLIAN_PROXY_BACKEND_HOST", "127.0.0.1")
MAX_PACKET_SIZE = 4096

logging.basicConfig(level=os.getenv("KSYLIAN_PROXY_LOG_LEVEL", "INFO"))
logger = logging.getLogger("ksylian-proxy")


class ProxyError(Exception):
    pass


def read_varint(buffer: bytes, offset: int = 0) -> tuple[int, int]:
    value = 0
    for position in range(5):
        if offset + position >= len(buffer):
            raise ProxyError("Incomplete varint")
        byte = buffer[offset + position]
        value |= (byte & 0x7F) << (7 * position)
        if not byte & 0x80:
            return value, offset + position + 1
    raise ProxyError("Varint is too large")


def read_utf(buffer: bytes, offset: int) -> tuple[str, int]:
    length, offset = read_varint(buffer, offset)
    end = offset + length
    if end > len(buffer):
        raise ProxyError("Incomplete string")
    return buffer[offset:end].decode("utf-8", errors="replace"), end


async def read_first_packet(reader: asyncio.StreamReader) -> bytes:
    prefix = bytearray()
    for _ in range(5):
        byte = await reader.readexactly(1)
        prefix.extend(byte)
        if not byte[0] & 0x80:
            packet_length, _ = read_varint(bytes(prefix))
            if packet_length > MAX_PACKET_SIZE:
                raise ProxyError("Handshake packet is too large")
            return bytes(prefix) + await reader.readexactly(packet_length)
    raise ProxyError("Handshake length is too large")


def hostname_from_handshake(packet: bytes) -> str:
    _packet_length, offset = read_varint(packet)
    packet_id, offset = read_varint(packet, offset)
    if packet_id != 0:
        raise ProxyError("First packet is not a handshake")

    _protocol_version, offset = read_varint(packet, offset)
    hostname, _offset = read_utf(packet, offset)
    return hostname.split("\x00", 1)[0].lower().strip().rstrip(".")


def disabled_server_ids() -> set[str]:
    if not DISABLED_SERVERS_FILE.exists():
        return set()
    try:
        data = json.loads(DISABLED_SERVERS_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return set()
    if not isinstance(data, list):
        return set()
    return {str(item) for item in data}


def load_servers() -> list[dict]:
    if not SERVERS_FILE.exists():
        return []
    try:
        data = json.loads(SERVERS_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def server_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", value.lower().strip())
    return re.sub(r"-+", "-", slug).strip("-")


def route_name(hostname: str) -> str:
    host = hostname.split(":", 1)[0].lower().strip().rstrip(".")
    if PUBLIC_DOMAIN and host.endswith(f".{PUBLIC_DOMAIN}"):
        return host[: -(len(PUBLIC_DOMAIN) + 1)]
    return host


def target_for_hostname(hostname: str) -> tuple[str, int] | None:
    name = route_name(hostname)
    if not name:
        return None

    disabled = disabled_server_ids()
    for server in load_servers():
        server_id = str(server.get("id") or "")
        if not server_id or server_id in disabled:
            continue
        aliases = {
            server_id,
            server_slug(str(server.get("name") or "")),
        }
        if name in aliases:
            try:
                return BACKEND_HOST, int(server["port"])
            except (KeyError, TypeError, ValueError):
                return None
    return None


async def pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while not reader.at_eof():
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    finally:
        writer.close()


async def handle_client(client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter) -> None:
    peer = client_writer.get_extra_info("peername")
    try:
        first_packet = await read_first_packet(client_reader)
        hostname = hostname_from_handshake(first_packet)
        target = target_for_hostname(hostname)
        if not target:
            logger.info("No route for %s from %s", hostname, peer)
            client_writer.close()
            await client_writer.wait_closed()
            return

        backend_reader, backend_writer = await asyncio.open_connection(*target)
        backend_writer.write(first_packet)
        await backend_writer.drain()
        logger.info("Proxy %s from %s to %s:%s", hostname, peer, target[0], target[1])

        await asyncio.gather(
            pipe(client_reader, backend_writer),
            pipe(backend_reader, client_writer),
        )
    except (asyncio.IncompleteReadError, ConnectionError, OSError, ProxyError) as error:
        logger.info("Connection from %s closed: %s", peer, error)
        client_writer.close()
        await client_writer.wait_closed()


async def main() -> None:
    if not PUBLIC_DOMAIN:
        logger.warning("KSYLIAN_PROXY_DOMAIN is empty; routes will use raw hostnames only")
    server = await asyncio.start_server(handle_client, LISTEN_HOST, LISTEN_PORT)
    logger.info("Ksylian proxy listening on %s:%s", LISTEN_HOST, LISTEN_PORT)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
