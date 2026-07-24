from __future__ import annotations

import secrets
import time
from pathlib import Path

from fastapi import Header, HTTPException

from .config import RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW_SECONDS, SERVER_ROOT, TOKEN
from .schemas import StoredServer


rate_limit_buckets: dict[str, list[float]] = {}


def require_token(x_ksylian_token: str | None = Header(default=None)) -> None:
    if not TOKEN:
        raise HTTPException(status_code=503, detail="Agent token is not configured")
    if not x_ksylian_token or not secrets.compare_digest(x_ksylian_token, TOKEN):
        raise HTTPException(status_code=401, detail="Invalid agent token")


def enforce_rate_limit(key: str) -> None:
    now = time.monotonic()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS
    bucket = [timestamp for timestamp in rate_limit_buckets.get(key, []) if timestamp >= window_start]
    if len(bucket) >= RATE_LIMIT_REQUESTS:
        rate_limit_buckets[key] = bucket
        raise HTTPException(status_code=429, detail="Too many requests")
    bucket.append(now)
    rate_limit_buckets[key] = bucket


def is_relative_path(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def ensure_child_path(root: Path, *parts: str) -> Path:
    candidate = root.joinpath(*parts).resolve()
    if candidate != root.resolve() and is_relative_path(candidate, root):
        return candidate
    raise HTTPException(status_code=400, detail="Path is outside allowed directory")


def managed_server_path(server_id: str) -> Path:
    return ensure_child_path(SERVER_ROOT, server_id)


def server_base_path(server: StoredServer) -> Path:
    path = Path(server.path).resolve()
    if server.managed and not is_relative_path(path, SERVER_ROOT):
        raise HTTPException(status_code=409, detail="Managed server path is outside allowed directory")
    return path


def server_child_path(server: StoredServer, relative_path: str = "") -> Path:
    root = server_base_path(server)
    cleaned = relative_path.strip().lstrip("/")
    if not cleaned or cleaned == ".":
        return root
    return ensure_child_path(root, *Path(cleaned).parts)


def relative_server_path(server: StoredServer, path: Path) -> str:
    return path.resolve().relative_to(server_base_path(server).resolve()).as_posix()

