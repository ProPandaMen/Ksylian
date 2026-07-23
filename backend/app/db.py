from __future__ import annotations

import json
import secrets
import sqlite3
from datetime import datetime

from .settings import DATABASE_PATH, USERS_PATH


def iso_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


DATABASE_READY = False


def load_legacy_user_store() -> dict:
    if not USERS_PATH.exists():
        return {"users": [], "invites": []}
    try:
        data = json.loads(USERS_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {"users": [], "invites": []}
    if not isinstance(data, dict):
        return {"users": [], "invites": []}
    users = data.get("users") if isinstance(data.get("users"), list) else []
    invites = data.get("invites") if isinstance(data.get("invites"), list) else []
    return {"users": users, "invites": invites}


def database() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def row_to_dict(row: sqlite3.Row) -> dict:
    return {key: row[key] for key in row.keys()}


def init_database() -> None:
    global DATABASE_READY
    if DATABASE_READY:
        return
    with database() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'member',
                theme TEXT NOT NULL DEFAULT 'pink',
                preferences TEXT NOT NULL DEFAULT '{}',
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                disabled_at TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS invites (
                id TEXT PRIMARY KEY,
                token TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL DEFAULT 'member',
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                used_at TEXT NOT NULL DEFAULT '',
                revoked_at TEXT NOT NULL DEFAULT '',
                invited_by TEXT NOT NULL DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
            CREATE INDEX IF NOT EXISTS idx_invites_token ON invites(token);
            CREATE INDEX IF NOT EXISTS idx_invites_used_at ON invites(used_at);
            """
        )
        ensure_auth_columns(connection)
        migrate_legacy_user_store(connection)
    try:
        DATABASE_PATH.chmod(0o600)
    except OSError:
        pass
    DATABASE_READY = True


def ensure_auth_columns(connection: sqlite3.Connection) -> None:
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(users)")}
    if "preferences" not in columns:
        connection.execute("ALTER TABLE users ADD COLUMN preferences TEXT NOT NULL DEFAULT '{}'")
    if "disabled_at" not in columns:
        connection.execute("ALTER TABLE users ADD COLUMN disabled_at TEXT NOT NULL DEFAULT ''")

    invite_columns = {row["name"] for row in connection.execute("PRAGMA table_info(invites)")}
    if "revoked_at" not in invite_columns:
        connection.execute("ALTER TABLE invites ADD COLUMN revoked_at TEXT NOT NULL DEFAULT ''")


def migrate_legacy_user_store(connection: sqlite3.Connection) -> None:
    legacy_store = load_legacy_user_store()
    for item in legacy_store.get("users", []):
        if not isinstance(item, dict):
            continue
        if not item.get("username") or not item.get("password_hash"):
            continue
        connection.execute(
            """
            INSERT OR IGNORE INTO users
                (id, username, display_name, role, theme, preferences, password_hash, created_at, disabled_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(item.get("id") or secrets.token_urlsafe(10)),
                str(item.get("username") or ""),
                str(item.get("display_name") or item.get("username") or ""),
                str(item.get("role") or "member"),
                str(item.get("theme") or "pink"),
                json.dumps(item.get("preferences") if isinstance(item.get("preferences"), dict) else {}),
                str(item.get("password_hash") or ""),
                str(item.get("created_at") or iso_now()),
                str(item.get("disabled_at") or ""),
            ),
        )
    for item in legacy_store.get("invites", []):
        if not isinstance(item, dict):
            continue
        if not item.get("token"):
            continue
        connection.execute(
            """
            INSERT OR IGNORE INTO invites
                (id, token, role, created_at, expires_at, used_at, revoked_at, invited_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(item.get("id") or secrets.token_urlsafe(8)),
                str(item.get("token") or ""),
                str(item.get("role") or "member"),
                str(item.get("created_at") or iso_now()),
                str(item.get("expires_at") or iso_now()),
                str(item.get("used_at") or ""),
                str(item.get("revoked_at") or ""),
                str(item.get("invited_by") or ""),
            ),
        )


def load_user_store() -> dict:
    init_database()
    with database() as connection:
        users = [
            row_to_dict(row)
            for row in connection.execute(
                """
                SELECT id, username, display_name, role, theme, preferences, password_hash, created_at, disabled_at
                FROM users
                ORDER BY created_at ASC
                """
            )
        ]
        invites = [
            row_to_dict(row)
            for row in connection.execute(
                """
                SELECT id, token, role, created_at, expires_at, used_at, revoked_at, invited_by
                FROM invites
                ORDER BY created_at DESC
                """
            )
        ]
    return {"users": users, "invites": invites}


def save_user_store(data: dict) -> None:
    init_database()
    users = [item for item in data.get("users", []) if isinstance(item, dict)]
    invites = [item for item in data.get("invites", []) if isinstance(item, dict)]
    with database() as connection:
        connection.execute("DELETE FROM invites")
        connection.execute("DELETE FROM users")
        connection.executemany(
            """
            INSERT INTO users
                (id, username, display_name, role, theme, preferences, password_hash, created_at, disabled_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    str(item.get("id") or secrets.token_urlsafe(10)),
                    str(item.get("username") or ""),
                    str(item.get("display_name") or item.get("username") or ""),
                    str(item.get("role") or "member"),
                    str(item.get("theme") or "pink"),
                    json.dumps(item.get("preferences") if isinstance(item.get("preferences"), dict) else {}),
                    str(item.get("password_hash") or ""),
                    str(item.get("created_at") or iso_now()),
                    str(item.get("disabled_at") or ""),
                )
                for item in users
            ],
        )
        connection.executemany(
            """
            INSERT INTO invites
                (id, token, role, created_at, expires_at, used_at, revoked_at, invited_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    str(item.get("id") or secrets.token_urlsafe(8)),
                    str(item.get("token") or ""),
                    str(item.get("role") or "member"),
                    str(item.get("created_at") or iso_now()),
                    str(item.get("expires_at") or iso_now()),
                    str(item.get("used_at") or ""),
                    str(item.get("revoked_at") or ""),
                    str(item.get("invited_by") or ""),
                )
                for item in invites
            ],
        )
