from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
from datetime import datetime

from fastapi import HTTPException, Request

from .schemas import AuthUser
from .settings import AUTH_SECRET, DATABASE_PATH, SESSION_TTL_SECONDS, USERS_PATH, load_settings, save_settings


DATABASE_READY = False


def utc_now() -> int:
    return int(time.time())


def iso_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def auth_secret() -> str:
    if AUTH_SECRET:
        return AUTH_SECRET
    fallback = load_settings().get("auth_secret", "")
    if fallback:
        return fallback
    fallback = secrets.token_urlsafe(48)
    settings = load_settings()
    settings["auth_secret"] = fallback
    save_settings(settings)
    return fallback


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
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS invites (
                id TEXT PRIMARY KEY,
                token TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL DEFAULT 'member',
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                used_at TEXT NOT NULL DEFAULT '',
                invited_by TEXT NOT NULL DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
            CREATE INDEX IF NOT EXISTS idx_invites_token ON invites(token);
            CREATE INDEX IF NOT EXISTS idx_invites_used_at ON invites(used_at);
            """
        )
        migrate_legacy_user_store(connection)
    try:
        DATABASE_PATH.chmod(0o600)
    except OSError:
        pass
    DATABASE_READY = True


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
                (id, username, display_name, role, theme, password_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(item.get("id") or secrets.token_urlsafe(10)),
                str(item.get("username") or ""),
                str(item.get("display_name") or item.get("username") or ""),
                str(item.get("role") or "member"),
                str(item.get("theme") or "pink"),
                str(item.get("password_hash") or ""),
                str(item.get("created_at") or iso_now()),
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
                (id, token, role, created_at, expires_at, used_at, invited_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(item.get("id") or secrets.token_urlsafe(8)),
                str(item.get("token") or ""),
                str(item.get("role") or "member"),
                str(item.get("created_at") or iso_now()),
                str(item.get("expires_at") or iso_now()),
                str(item.get("used_at") or ""),
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
                SELECT id, username, display_name, role, theme, password_hash, created_at
                FROM users
                ORDER BY created_at ASC
                """
            )
        ]
        invites = [
            row_to_dict(row)
            for row in connection.execute(
                """
                SELECT id, token, role, created_at, expires_at, used_at, invited_by
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
                (id, username, display_name, role, theme, password_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    str(item.get("id") or secrets.token_urlsafe(10)),
                    str(item.get("username") or ""),
                    str(item.get("display_name") or item.get("username") or ""),
                    str(item.get("role") or "member"),
                    str(item.get("theme") or "pink"),
                    str(item.get("password_hash") or ""),
                    str(item.get("created_at") or iso_now()),
                )
                for item in users
            ],
        )
        connection.executemany(
            """
            INSERT INTO invites
                (id, token, role, created_at, expires_at, used_at, invited_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    str(item.get("id") or secrets.token_urlsafe(8)),
                    str(item.get("token") or ""),
                    str(item.get("role") or "member"),
                    str(item.get("created_at") or iso_now()),
                    str(item.get("expires_at") or iso_now()),
                    str(item.get("used_at") or ""),
                    str(item.get("invited_by") or ""),
                )
                for item in invites
            ],
        )


def stored_users() -> list[dict]:
    return [item for item in load_user_store().get("users", []) if isinstance(item, dict)]


def user_public(user: dict) -> AuthUser:
    return AuthUser(
        id=str(user.get("id") or ""),
        username=str(user.get("username") or ""),
        display_name=str(user.get("display_name") or user.get("username") or ""),
        role=str(user.get("role") or "member"),  # type: ignore[arg-type]
        theme=str(user.get("theme") or "pink"),  # type: ignore[arg-type]
        created_at=str(user.get("created_at") or ""),
    )


def normalize_username(username: str) -> str:
    value = username.strip().lower()
    if not re.fullmatch(r"[a-z0-9_.-]{3,32}", value):
        raise HTTPException(status_code=400, detail="Username must be 3-32 latin characters")
    return value


def validate_password(password: str) -> None:
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must contain at least 8 characters")


def hash_password(password: str, salt: str | None = None) -> str:
    salt_bytes = base64.urlsafe_b64decode(salt.encode()) if salt else secrets.token_bytes(18)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt_bytes, 210_000)
    salt_value = base64.urlsafe_b64encode(salt_bytes).decode()
    digest_value = base64.urlsafe_b64encode(digest).decode()
    return f"pbkdf2_sha256${salt_value}${digest_value}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, salt, digest = stored_hash.split("$", 2)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    expected = hash_password(password, salt).split("$", 2)[2]
    return hmac.compare_digest(expected, digest)


def create_token(user_id: str) -> str:
    expires_at = utc_now() + SESSION_TTL_SECONDS
    nonce = secrets.token_urlsafe(12)
    payload = f"{user_id}.{expires_at}.{nonce}"
    signature = hmac.new(auth_secret().encode(), payload.encode(), hashlib.sha256).digest()
    return f"{payload}.{base64.urlsafe_b64encode(signature).decode().rstrip('=')}"


def user_from_token(token: str) -> dict | None:
    parts = token.split(".")
    if len(parts) != 4:
        return None
    user_id, expires_at_raw, nonce, signature = parts
    payload = f"{user_id}.{expires_at_raw}.{nonce}"
    expected = base64.urlsafe_b64encode(
        hmac.new(auth_secret().encode(), payload.encode(), hashlib.sha256).digest()
    ).decode().rstrip("=")
    if not hmac.compare_digest(expected, signature):
        return None
    try:
        expires_at = int(expires_at_raw)
    except ValueError:
        return None
    if expires_at < utc_now():
        return None
    return next((user for user in stored_users() if str(user.get("id")) == user_id), None)


def current_user_from_request(request: Request) -> dict | None:
    auth_header = request.headers.get("authorization", "")
    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return user_from_token(token)


def require_current_user(request: Request) -> dict:
    user = getattr(request.state, "user", None) or current_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def require_admin_user(request: Request) -> dict:
    user = require_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin permissions required")
    return user
