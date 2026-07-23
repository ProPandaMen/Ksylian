from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import time
from datetime import datetime

from fastapi import HTTPException, Request

from .schemas import AuthUser
from .db import load_user_store
from .settings import AUTH_SECRET, SESSION_TTL_SECONDS, load_settings, save_settings


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
        disabled_at=str(user.get("disabled_at") or ""),
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
    user = next((user for user in stored_users() if str(user.get("id")) == user_id), None)
    if user and user.get("disabled_at"):
        return None
    return user


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
