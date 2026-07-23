from __future__ import annotations

import json
from datetime import datetime

from .config import ACTION_LOG, DATA_DIR


def append_action_log(action: str, server_id: str = "-", detail: str = "") -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "at": datetime.now().isoformat(timespec="seconds"),
        "action": action,
        "server_id": server_id,
        "detail": detail,
    }
    with ACTION_LOG.open("a") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")
