from __future__ import annotations

import subprocess
from typing import Literal
from pathlib import Path

from fastapi import HTTPException

from .config import MINECRAFT_USER, SERVER_ROOT
from .schemas import StoredServer
from .security import server_base_path


def run(command: list[str], timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)


def run_in(command: list[str], cwd: Path, timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False)


def ensure_minecraft_user_exists() -> None:
    result = run(["id", "-u", MINECRAFT_USER], timeout=10)
    if result.returncode == 0:
        return

    create = run(
        [
            "useradd",
            "--system",
            "--home-dir",
            str(SERVER_ROOT),
            "--shell",
            "/usr/sbin/nologin",
            MINECRAFT_USER,
        ],
        timeout=30,
    )
    if create.returncode != 0:
        raise HTTPException(status_code=500, detail=create.stderr.strip() or "Failed to create Minecraft user")


def apply_server_permissions(server: StoredServer) -> None:
    server_path = server_base_path(server)
    ensure_minecraft_user_exists()
    result = run(["chown", "-R", f"{MINECRAFT_USER}:{MINECRAFT_USER}", str(server_path)], timeout=120)
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=result.stderr.strip() or "Failed to set server directory owner")


def systemctl_issue_can_be_ignored(result: subprocess.CompletedProcess[str]) -> bool:
    message = f"{result.stdout}\n{result.stderr}".lower()
    return "not loaded" in message or "not found" in message or "does not exist" in message


def service_state(
    service: str,
) -> Literal["installing", "stopped", "starting", "running", "stopping", "crashed", "updating", "backing_up"]:
    result = run(["systemctl", "is-active", service])
    if result.stdout.strip() == "active":
        return "running"
    if result.stdout.strip() in {"activating", "reloading"}:
        return "starting"
    if result.stdout.strip() == "deactivating":
        return "stopping"
    if result.stdout.strip() == "failed":
        return "crashed"
    return "stopped"
