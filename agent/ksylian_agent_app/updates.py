from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException

from .config import APP_COMPOSE_FILE, APP_DIR, APP_ENV_FILE, APP_UPDATE_SCRIPT, DATA_DIR, UPDATE_LOG


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
    if not APP_UPDATE_SCRIPT.exists():
        raise HTTPException(status_code=409, detail=f"Update script was not found: {APP_UPDATE_SCRIPT}")


def update_script_path() -> Path:
    return APP_UPDATE_SCRIPT

