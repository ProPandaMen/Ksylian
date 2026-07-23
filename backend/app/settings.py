from __future__ import annotations

import json
import os
from pathlib import Path


PUBLIC_API_PATHS = {
    "/api/auth/status",
    "/api/auth/bootstrap",
    "/api/auth/login",
    "/api/auth/register-invite",
}

AGENT_URL = os.getenv("KSYLIAN_AGENT_URL", "").rstrip("/")
AGENT_TOKEN = os.getenv("KSYLIAN_AGENT_TOKEN", "")
SETTINGS_PATH = Path(os.getenv("KSYLIAN_SETTINGS_PATH", "/data/settings.json"))
USERS_PATH = Path(os.getenv("KSYLIAN_USERS_PATH", "/data/users.json"))
DATABASE_PATH = Path(os.getenv("KSYLIAN_DATABASE_PATH", "/data/ksylian.db"))
AUTH_SECRET = os.getenv("KSYLIAN_AUTH_SECRET", "")
SESSION_TTL_SECONDS = int(os.getenv("KSYLIAN_SESSION_TTL_SECONDS", str(60 * 60 * 24 * 14)))
VERSION_FILE = Path(__file__).resolve().parents[2] / "VERSION"
DEFAULT_BUILD_VERSION = VERSION_FILE.read_text().strip() if VERSION_FILE.exists() else "dev"
BUILD_VERSION = os.getenv("KSYLIAN_BUILD_VERSION", DEFAULT_BUILD_VERSION)
BUILD_SHA = os.getenv("KSYLIAN_BUILD_SHA", "local")
RELEASE_REPOSITORY = os.getenv("KSYLIAN_RELEASE_REPOSITORY", "ProPandaMen/Ksylian")
GITHUB_API_BASE_URL = os.getenv("KSYLIAN_GITHUB_API_URL", "https://api.github.com").rstrip("/")
GITHUB_TOKEN = os.getenv("KSYLIAN_GITHUB_TOKEN", "")
CURSEFORGE_BASE_URL = "https://api.curseforge.com"
MINECRAFT_GAME_ID = 432
CURSEFORGE_CLASS_IDS = {"mods": 6, "modpacks": 4471}
CURSEFORGE_SORT_FIELDS = {"popularity": 2, "updated": 3, "name": 4, "downloads": 6}
CURSEFORGE_LOADER_TYPES = {"any": None, "forge": 1, "fabric": 4, "quilt": 5, "neoforge": 6}
CURSEFORGE_LOADER_LABELS = {1: "Forge", 4: "Fabric", 5: "Quilt", 6: "NeoForge"}
MINECRAFT_VERSION_MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
MINECRAFT_VERSION_CACHE_SECONDS = 60 * 60


def load_settings() -> dict[str, str]:
    if not SETTINGS_PATH.exists():
        return {}

    try:
        data = json.loads(SETTINGS_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}

    if not isinstance(data, dict):
        return {}
    return {str(key): str(value) for key, value in data.items() if isinstance(value, str)}


def save_settings(data: dict[str, str]) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    SETTINGS_PATH.chmod(0o600)
