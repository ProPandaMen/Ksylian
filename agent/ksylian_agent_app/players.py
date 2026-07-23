from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from .config import DATA_DIR
from .minecraft import execute_rcon
from .schemas import GamePlayer, PlayerActionRequest, PlayerActionResult, PlayerHistoryItem, PlayerListPayload, StoredServer
from .security import server_base_path


PLAYER_NAME_RE = re.compile(r"^[A-Za-z0-9_]{1,16}$")


def player_history_path(server: StoredServer) -> Path:
    return DATA_DIR / "player-history" / f"{server.id}.jsonl"


def normalize_player_name(value: str) -> str:
    name = value.strip()
    if not PLAYER_NAME_RE.fullmatch(name):
        raise HTTPException(status_code=400, detail="Invalid Minecraft player name")
    return name


def read_json_file(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(errors="replace"))
    except (OSError, json.JSONDecodeError):
        return fallback


def read_player_objects(server: StoredServer, filename: str) -> list[dict[str, Any]]:
    data = read_json_file(server_base_path(server) / filename, [])
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def read_usercache(server: StoredServer) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for item in read_player_objects(server, "usercache.json"):
        name = str(item.get("name") or "")
        if not name:
            continue
        result[name.lower()] = {
            "name": name,
            "uuid": str(item.get("uuid") or ""),
            "last_seen": str(item.get("expiresOn") or ""),
        }
    return result


def read_named_set(server: StoredServer, filename: str) -> set[str]:
    return {str(item.get("name") or "").lower() for item in read_player_objects(server, filename) if item.get("name")}


def read_ip_bans(server: StoredServer) -> set[str]:
    result: set[str] = set()
    for item in read_player_objects(server, "banned-ips.json"):
        ip = str(item.get("ip") or "")
        if ip:
            result.add(ip)
    return result


def latest_stats_times(server: StoredServer) -> dict[str, str]:
    stats_dir = server_base_path(server) / "world" / "stats"
    if not stats_dir.exists():
        return {}
    result = {}
    for path in stats_dir.glob("*.json"):
        try:
            result[path.stem.lower()] = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        except OSError:
            continue
    return result


def parse_online_players(output: str) -> list[str]:
    if ":" not in output:
        return []
    tail = output.split(":", 1)[1].strip()
    if not tail:
        return []
    return [item.strip() for item in tail.split(",") if item.strip()]


def try_rcon(server: StoredServer, command: str) -> str:
    try:
        return execute_rcon(server, command)
    except HTTPException:
        return ""


def game_time(server: StoredServer) -> str:
    output = try_rcon(server, "time query gametime")
    match = re.search(r"(\d+)", output)
    return match.group(1) if match else ""


def luckperms_groups(server: StoredServer, player: str) -> list[str]:
    output = try_rcon(server, f"lp user {player} info")
    groups = re.findall(r"(?:Primary Group|Parent Groups?)[:\s]+([A-Za-z0-9_, -]+)", output, re.IGNORECASE)
    result: list[str] = []
    for group in groups:
        for item in re.split(r"[, ]+", group):
            value = item.strip()
            if value and value.lower() not in {"none", "primary", "group", "parents"}:
                result.append(value)
    return list(dict.fromkeys(result))[:12]


def known_players(server: StoredServer) -> list[GamePlayer]:
    cache = read_usercache(server)
    whitelist = read_named_set(server, "whitelist.json")
    operators = read_named_set(server, "ops.json")
    banned = read_named_set(server, "banned-players.json")
    stats = latest_stats_times(server)
    online_names = {name.lower() for name in parse_online_players(try_rcon(server, "list"))}
    players: list[GamePlayer] = []
    for key, item in cache.items():
        uuid = item["uuid"]
        last_seen = stats.get(uuid.lower()) or item["last_seen"]
        players.append(
            GamePlayer(
                name=item["name"],
                uuid=uuid,
                online=key in online_names,
                game_time=game_time(server) if key in online_names else "",
                last_seen=last_seen,
                whitelisted=key in whitelist,
                operator=key in operators,
                banned=key in banned,
                ip_banned=False,
                luckperms_groups=luckperms_groups(server, item["name"]) if key in online_names else [],
            ),
        )
    for name in online_names:
        if name not in cache:
            players.append(GamePlayer(name=name, online=True, game_time=game_time(server), luckperms_groups=luckperms_groups(server, name)))
    return sorted(players, key=lambda item: (not item.online, item.name.lower()))


def read_history(server: StoredServer, limit: int = 80) -> list[PlayerHistoryItem]:
    path = player_history_path(server)
    if not path.exists():
        return []
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return []
    items: list[PlayerHistoryItem] = []
    for line in reversed(lines):
        try:
            items.append(PlayerHistoryItem(**json.loads(line)))
        except (json.JSONDecodeError, ValueError):
            continue
        if len(items) >= limit:
            break
    return items


def append_history(server: StoredServer, player: str, action: str, detail: str = "") -> None:
    path = player_history_path(server)
    path.parent.mkdir(parents=True, exist_ok=True)
    item = PlayerHistoryItem(
        at=datetime.now().isoformat(timespec="seconds"),
        player=player,
        action=action,
        detail=detail,
    )
    with path.open("a") as file:
        file.write(item.model_dump_json() + "\n")


def list_players(server: StoredServer) -> PlayerListPayload:
    players = known_players(server)
    return PlayerListPayload(
        online=[item for item in players if item.online],
        known=players,
        history=read_history(server),
        rcon_available=bool(try_rcon(server, "list")),
        game_time=game_time(server),
    )


def player_action_command(request: PlayerActionRequest) -> str:
    name = normalize_player_name(request.player)
    value = request.value.strip()
    reason = request.reason.strip()
    if request.action == "whitelist_add":
        return f"whitelist add {name}"
    if request.action == "whitelist_remove":
        return f"whitelist remove {name}"
    if request.action == "op":
        return f"op {name}"
    if request.action == "deop":
        return f"deop {name}"
    if request.action == "ban":
        return f"ban {name} {reason}".strip()
    if request.action == "pardon":
        return f"pardon {name}"
    if request.action == "ban_ip":
        return f"ban-ip {value or name} {reason}".strip()
    if request.action == "pardon_ip":
        return f"pardon-ip {value or name}"
    if request.action == "kick":
        return f"kick {name} {reason}".strip()
    if request.action == "message":
        if not value:
            raise HTTPException(status_code=400, detail="Message is required")
        safe_message = value.replace("\\", "\\\\").replace('"', '\\"')[:512]
        return f'tellraw {name} {{"text":"{safe_message}"}}'
    if request.action == "luckperms_group_add":
        if not value:
            raise HTTPException(status_code=400, detail="LuckPerms group is required")
        return f"lp user {name} parent add {value}"
    if request.action == "luckperms_group_remove":
        if not value:
            raise HTTPException(status_code=400, detail="LuckPerms group is required")
        return f"lp user {name} parent remove {value}"
    if request.action == "luckperms_permission_set":
        if not value:
            raise HTTPException(status_code=400, detail="LuckPerms permission is required")
        return f"lp user {name} permission set {value} true"
    if request.action == "luckperms_permission_unset":
        if not value:
            raise HTTPException(status_code=400, detail="LuckPerms permission is required")
        return f"lp user {name} permission unset {value}"
    raise HTTPException(status_code=400, detail="Unsupported player action")


def run_player_action(server: StoredServer, request: PlayerActionRequest) -> PlayerActionResult:
    command = player_action_command(request)
    output = execute_rcon(server, command)
    append_history(server, request.player, request.action, request.reason or request.value)
    return PlayerActionResult(
        ok=True,
        message=f"{request.action} выполнено для {request.player}",
        output=output,
        players=list_players(server),
    )
