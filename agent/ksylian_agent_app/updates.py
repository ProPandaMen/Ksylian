from __future__ import annotations

import re
import shlex
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException

from .config import APP_COMPOSE_FILE, APP_DIR, APP_ENV_FILE, DATA_DIR, UPDATE_LOG


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


