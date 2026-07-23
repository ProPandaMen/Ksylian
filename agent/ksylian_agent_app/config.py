from __future__ import annotations

import os
from pathlib import Path


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
BACKUP_KEEP_LAST = int(os.getenv("KSYLIAN_BACKUP_KEEP_LAST", "12"))
BACKUP_KEEP_DAILY = int(os.getenv("KSYLIAN_BACKUP_KEEP_DAILY", "7"))
BACKUP_KEEP_WEEKLY = int(os.getenv("KSYLIAN_BACKUP_KEEP_WEEKLY", "4"))
BACKUP_KEEP_MONTHLY = int(os.getenv("KSYLIAN_BACKUP_KEEP_MONTHLY", "6"))
BACKUP_MAX_BYTES = int(os.getenv("KSYLIAN_BACKUP_MAX_BYTES", str(250 * 1024**3)))
BACKUP_S3_URI = os.getenv("KSYLIAN_BACKUP_S3_URI", "").rstrip("/")
DATA_DIR = Path(os.getenv("KSYLIAN_DATA_DIR", "/var/lib/ksylian-agent"))
MONITORING_HISTORY_FILE = DATA_DIR / "monitoring-history.jsonl"
MONITORING_SAMPLE_SECONDS = max(5, int(os.getenv("KSYLIAN_MONITORING_SAMPLE_SECONDS", "30")))
MONITORING_RETENTION_HOURS = max(1, int(os.getenv("KSYLIAN_MONITORING_RETENTION_HOURS", "24")))
DISABLED_SERVERS_FILE = DATA_DIR / "disabled-servers.json"
SERVERS_FILE = DATA_DIR / "servers.json"
SERVER_ROOT = Path(os.getenv("KSYLIAN_SERVER_ROOT", "/opt/ksylian/servers"))
APP_DIR = Path(os.getenv("KSYLIAN_APP_DIR", "/opt/ksylian"))
APP_ENV_FILE = Path(os.getenv("KSYLIAN_ENV_FILE", str(APP_DIR / "deploy/.env")))
APP_COMPOSE_FILE = Path(os.getenv("KSYLIAN_COMPOSE_FILE", str(APP_DIR / "deploy/docker-compose.yml")))
APP_UPDATE_SCRIPT = Path(os.getenv("KSYLIAN_UPDATE_SCRIPT", str(APP_DIR / "deploy/scripts/update-ksylian.sh")))
UPDATE_LOG = DATA_DIR / "update.log"
TOKEN = os.getenv("KSYLIAN_AGENT_TOKEN", "")
ACTION_LOG = DATA_DIR / "actions.log"
PUBLIC_DOMAIN = os.getenv("KSYLIAN_PUBLIC_DOMAIN", os.getenv("KSYLIAN_PROXY_DOMAIN", "")).strip().lower().strip(".")
PROXY_DOMAIN = os.getenv("KSYLIAN_PROXY_DOMAIN", PUBLIC_DOMAIN).strip().lower().strip(".")
PROXY_PORT = os.getenv("KSYLIAN_PROXY_PORT", "25565")
MINECRAFT_USER = os.getenv("KSYLIAN_MINECRAFT_USER", "ksylian-minecraft")
RATE_LIMIT_REQUESTS = int(os.getenv("KSYLIAN_AGENT_RATE_LIMIT_REQUESTS", "240"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("KSYLIAN_AGENT_RATE_LIMIT_WINDOW_SECONDS", "60"))
MINECRAFT_VERSION_MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
FABRIC_META_API_URL = "https://meta.fabricmc.net/v2"
MODRINTH_API_URL = "https://api.modrinth.com/v2"
FORGE_MAVEN_URL = "https://maven.minecraftforge.net/net/minecraftforge/forge"
NEOFORGE_MAVEN_URL = "https://maven.neoforged.net/releases/net/neoforged/neoforge"
PAPER_API_URL = "https://fill.papermc.io/v3/projects/paper"
PURPUR_API_URL = "https://api.purpurmc.org/v2/purpur"
AGENT_USER_AGENT = "Ksylian/0.1 (https://github.com/ProPandaMen/Ksylian)"
SYSTEMD_DIR = Path("/etc/systemd/system")
