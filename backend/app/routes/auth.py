from __future__ import annotations

import secrets
import time
from collections.abc import Callable
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from ..auth import (
    create_token,
    hash_password,
    load_user_store,
    normalize_username,
    require_admin_user,
    require_current_user,
    save_user_store,
    stored_users,
    user_public,
    validate_password,
    verify_password,
    iso_now,
)
from ..schemas import (
    AuthRequest,
    AuthSessionPayload,
    AuthStatusPayload,
    AuthUser,
    BootstrapAdminRequest,
    CreateInviteRequest,
    InviteRegistrationRequest,
    ThemeUpdateRequest,
    UserInvite,
)


def create_auth_router(append_log: Callable[[str], None]) -> APIRouter:
    router = APIRouter()

    @router.get("/api/auth/status", response_model=AuthStatusPayload)
    def auth_status() -> AuthStatusPayload:
        has_users = bool(stored_users())
        return AuthStatusPayload(has_users=has_users, bootstrap_required=not has_users)


    @router.post("/api/auth/bootstrap", response_model=AuthSessionPayload)
    def bootstrap_admin(payload: BootstrapAdminRequest) -> AuthSessionPayload:
        store = load_user_store()
        if store.get("users"):
            raise HTTPException(status_code=409, detail="Admin account already exists")

        username = normalize_username(payload.username)
        validate_password(payload.password)
        user = {
            "id": secrets.token_urlsafe(10),
            "username": username,
            "display_name": payload.display_name.strip() or username,
            "role": "admin",
            "theme": payload.theme,
            "password_hash": hash_password(payload.password),
            "created_at": iso_now(),
        }
        store["users"] = [user]
        store["invites"] = []
        save_user_store(store)
        append_log(f"auth: admin account created for {username}")
        return AuthSessionPayload(token=create_token(user["id"]), user=user_public(user))


    @router.post("/api/auth/login", response_model=AuthSessionPayload)
    def login(payload: AuthRequest) -> AuthSessionPayload:
        username = normalize_username(payload.username)
        user = next((item for item in stored_users() if item.get("username") == username), None)
        if not user or not verify_password(payload.password, str(user.get("password_hash") or "")):
            raise HTTPException(status_code=401, detail="Invalid username or password")
        return AuthSessionPayload(token=create_token(str(user["id"])), user=user_public(user))


    @router.get("/api/auth/me", response_model=AuthUser)
    def me(user: dict = Depends(require_current_user)) -> AuthUser:
        return user_public(user)


    @router.put("/api/auth/me/theme", response_model=AuthUser)
    def update_my_theme(payload: ThemeUpdateRequest, user: dict = Depends(require_current_user)) -> AuthUser:
        store = load_user_store()
        for item in store.get("users", []):
            if isinstance(item, dict) and item.get("id") == user.get("id"):
                item["theme"] = payload.theme
                save_user_store(store)
                return user_public(item)
        raise HTTPException(status_code=404, detail="User not found")


    @router.post("/api/auth/register-invite", response_model=AuthSessionPayload)
    def register_invite(payload: InviteRegistrationRequest) -> AuthSessionPayload:
        store = load_user_store()
        invite = next(
            (
                item
                for item in store.get("invites", [])
                if isinstance(item, dict) and item.get("token") == payload.token and not item.get("used_at")
            ),
            None,
        )
        if not invite:
            raise HTTPException(status_code=404, detail="Invite was not found")
        try:
            expires_at = datetime.fromisoformat(str(invite.get("expires_at") or ""))
        except ValueError as error:
            raise HTTPException(status_code=400, detail="Invite is invalid") from error
        if expires_at < datetime.now():
            raise HTTPException(status_code=410, detail="Invite has expired")

        username = normalize_username(payload.username)
        validate_password(payload.password)
        if any(user.get("username") == username for user in store.get("users", []) if isinstance(user, dict)):
            raise HTTPException(status_code=409, detail="Username already exists")

        user = {
            "id": secrets.token_urlsafe(10),
            "username": username,
            "display_name": payload.display_name.strip() or username,
            "role": invite.get("role") or "member",
            "theme": payload.theme,
            "password_hash": hash_password(payload.password),
            "created_at": iso_now(),
        }
        store["users"].append(user)
        invite["used_at"] = iso_now()
        save_user_store(store)
        append_log(f"auth: invite accepted by {username}")
        return AuthSessionPayload(token=create_token(user["id"]), user=user_public(user))


    @router.get("/api/users", response_model=list[AuthUser])
    def list_users(_: dict = Depends(require_admin_user)) -> list[AuthUser]:
        return [user_public(user) for user in stored_users()]


    @router.get("/api/users/invites", response_model=list[UserInvite])
    def list_invites(_: dict = Depends(require_admin_user)) -> list[UserInvite]:
        invites = []
        for item in load_user_store().get("invites", []):
            if isinstance(item, dict):
                invites.append(UserInvite(**item))
        return invites


    @router.post("/api/users/invites", response_model=UserInvite)
    def create_invite(payload: CreateInviteRequest, user: dict = Depends(require_admin_user)) -> UserInvite:
        ttl_hours = min(max(payload.ttl_hours, 1), 24 * 14)
        invite = UserInvite(
            id=secrets.token_urlsafe(8),
            token=secrets.token_urlsafe(24),
            role=payload.role,
            created_at=iso_now(),
            expires_at=datetime.fromtimestamp(time.time() + ttl_hours * 3600).isoformat(timespec="seconds"),
            invited_by=str(user.get("id") or ""),
        )
        store = load_user_store()
        store.setdefault("invites", []).insert(0, invite.model_dump())
        save_user_store(store)
        append_log(f"auth: invite created by {user.get('username')}")
        return invite

    return router
