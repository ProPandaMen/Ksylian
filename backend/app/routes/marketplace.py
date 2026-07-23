from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from fastapi import APIRouter, Query

from ..schemas import CurseForgeProject, CurseForgeSearchPayload, FileItem, ModItem
from ..settings import CURSEFORGE_CLASS_IDS, CURSEFORGE_LOADER_TYPES, CURSEFORGE_SORT_FIELDS, MINECRAFT_GAME_ID


def create_marketplace_router(
    *,
    mods: list[ModItem],
    files: list[FileItem],
    curseforge_api_key: Callable[[], str],
    curseforge_get: Callable[[str, dict[str, int | str]], dict],
    transform_curseforge_project: Callable[[dict, Literal["mods", "modpacks"]], CurseForgeProject],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/mods", response_model=list[ModItem])
    def list_mods() -> list[ModItem]:
        return mods


    @router.post("/api/mods/check")
    def check_mod_updates() -> dict[str, str]:
        append_log("CurseForge update check requested")
        return {"status": "queued"}


    @router.get("/api/curseforge/search", response_model=CurseForgeSearchPayload)
    def search_curseforge(
        kind: Literal["mods", "modpacks"] = "modpacks",
        query: str = "",
        minecraft_version: str = "",
        loader: Literal["any", "forge", "fabric", "quilt", "neoforge"] = "any",
        sort: Literal["popularity", "updated", "name", "downloads"] = "popularity",
        page_size: int = Query(default=20, ge=1, le=50),
        index: int = Query(default=0, ge=0, le=9950),
    ) -> CurseForgeSearchPayload:
        params: dict[str, int | str] = {
            "gameId": MINECRAFT_GAME_ID,
            "classId": CURSEFORGE_CLASS_IDS[kind],
            "pageSize": page_size,
            "index": index,
            "sortField": CURSEFORGE_SORT_FIELDS[sort],
            "sortOrder": "desc",
        }

        search_filter = query.strip()
        if search_filter:
            params["searchFilter"] = search_filter

        game_version = minecraft_version.strip()
        if game_version:
            params["gameVersion"] = game_version

        mod_loader_type = CURSEFORGE_LOADER_TYPES[loader]
        if mod_loader_type is not None:
            params["modLoaderType"] = mod_loader_type

        data = curseforge_get("/v1/mods/search", params)
        raw_items = data.get("data") or []
        pagination = data.get("pagination") or {}
        items = [
            transform_curseforge_project(item, kind)
            for item in raw_items
            if isinstance(item, dict)
        ]

        return CurseForgeSearchPayload(
            items=items,
            total_count=int(pagination.get("totalCount") or len(items)),
            has_api_key=True,
        )


    @router.get("/api/files", response_model=list[FileItem])
    def list_files() -> list[FileItem]:
        return files

    return router
