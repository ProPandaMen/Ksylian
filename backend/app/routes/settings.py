from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException

from ..schemas import (
    AgentStatus,
    ApplyUpdateRequest,
    ApplyUpdateResult,
    SettingsPayload,
    UpdateSettingsRequest,
    UpdateStatusPayload,
)
from ..settings import AGENT_URL, load_settings, save_settings


def create_settings_router(
    *,
    append_log: Callable[[str], None],
    current_agent_status: Callable[[], AgentStatus],
    curseforge_api_key: Callable[[], str],
    curseforge_key_status: Callable[[], tuple[str, str]],
    mask_secret: Callable[[str], str],
    update_status_payload: Callable[[], UpdateStatusPayload],
    agent_client: Any,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/settings", response_model=SettingsPayload)
    def get_settings() -> SettingsPayload:
        key = curseforge_api_key()
        key_status, key_message = curseforge_key_status()
        return SettingsPayload(
            has_curseforge_api_key=bool(key),
            curseforge_api_key_mask=mask_secret(key),
            curseforge_api_key_status=key_status,  # type: ignore[arg-type]
            curseforge_api_key_message=key_message,
            agent=current_agent_status(),
        )


    @router.put("/api/settings", response_model=SettingsPayload)
    def update_settings(payload: UpdateSettingsRequest) -> SettingsPayload:
        settings = load_settings()
        key = payload.curseforge_api_key.strip()

        if key:
            settings["curseforge_api_key"] = key
            append_log("settings: CurseForge API key updated")
        else:
            settings.pop("curseforge_api_key", None)
            append_log("settings: CurseForge API key cleared")

        save_settings(settings)
        key = curseforge_api_key()
        key_status, key_message = curseforge_key_status()
        return SettingsPayload(
            has_curseforge_api_key=bool(key),
            curseforge_api_key_mask=mask_secret(key),
            curseforge_api_key_status=key_status,  # type: ignore[arg-type]
            curseforge_api_key_message=key_message,
            agent=current_agent_status(),
        )


    @router.get("/api/update/status", response_model=UpdateStatusPayload)
    def get_update_status() -> UpdateStatusPayload:
        return update_status_payload()


    @router.post("/api/update/apply", response_model=ApplyUpdateResult)
    def apply_update(payload: ApplyUpdateRequest) -> ApplyUpdateResult:
        status = update_status_payload()
        target_version = payload.target_version.strip() or status.latest_version
        if not target_version:
            raise HTTPException(status_code=409, detail="No release tag is available")
        if not AGENT_URL:
            raise HTTPException(status_code=409, detail="Host agent is not configured")
        if status.updater_status != "ready":
            raise HTTPException(status_code=503, detail="Updater is not ready")

        try:
            data = agent_client.apply_update(target_version)
        except Exception as error:
            append_log(f"app update failed: {error}")
            raise HTTPException(status_code=502, detail="Host agent update failed") from error

        append_log(f"app update queued: {target_version}")
        return ApplyUpdateResult(
            ok=bool(data.get("ok", True)) if isinstance(data, dict) else True,
            message=str(data.get("message") or "Обновление запущено") if isinstance(data, dict) else "Обновление запущено",
            target_version=target_version,
        )

    return router
