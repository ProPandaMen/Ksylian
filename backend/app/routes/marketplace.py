from __future__ import annotations

import base64
import io
import json
import zipfile
from collections.abc import Callable
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, Query

from ..schemas import (
    CurseForgeFile,
    CurseForgeFileDependency,
    CurseForgeFilesPayload,
    CurseForgeInstallRequest,
    CurseForgeInstallResult,
    CurseForgeProject,
    CurseForgeSearchPayload,
    FileItem,
    FileWriteRequest,
    ModInstallRequest,
    ModItem,
)
from ..settings import CURSEFORGE_CLASS_IDS, CURSEFORGE_LOADER_TYPES, CURSEFORGE_SORT_FIELDS, MINECRAFT_GAME_ID


def create_marketplace_router(
    *,
    mods: list[ModItem],
    files: list[FileItem],
    curseforge_api_key: Callable[[], str],
    curseforge_get: Callable[[str, dict[str, int | str]], dict],
    transform_curseforge_project: Callable[[dict, Literal["mods", "modpacks"]], CurseForgeProject],
    append_log: Callable[[str], None],
    agent_client,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/mods", response_model=list[ModItem])
    def list_mods() -> list[ModItem]:
        return mods


    @router.post("/api/mods/check")
    def check_mod_updates() -> dict[str, str]:
        append_log("CurseForge update check requested")
        return {"status": "queued"}


    @router.post("/api/curseforge/key/check")
    def check_curseforge_key() -> dict[str, bool | str]:
        if not curseforge_api_key():
            return {"ok": False, "message": "CurseForge API key is not configured"}
        data = curseforge_get("/v1/games", {"pageSize": 1})
        return {"ok": bool(data.get("data") is not None), "message": "CurseForge API key is valid"}


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


    def transform_file(project_id: int, item: dict) -> CurseForgeFile:
        release_map = {1: "release", 2: "beta", 3: "alpha"}
        hashes = {}
        for value in item.get("hashes") or []:
            if isinstance(value, dict):
                algo = str(value.get("algo") or "")
                digest = str(value.get("value") or "")
                if algo and digest:
                    hashes[algo] = digest
        dependencies = []
        for dependency in item.get("dependencies") or []:
            if not isinstance(dependency, dict):
                continue
            relation_type = int(dependency.get("relationType") or 0)
            dependencies.append(
                CurseForgeFileDependency(
                    mod_id=int(dependency.get("modId") or 0),
                    relation_type=relation_type,
                    required=relation_type == 3,
                ),
            )
        download_url = str(item.get("downloadUrl") or "")
        return CurseForgeFile(
            id=int(item.get("id") or 0),
            mod_id=int(item.get("modId") or project_id),
            display_name=str(item.get("displayName") or item.get("fileName") or ""),
            file_name=str(item.get("fileName") or ""),
            download_url=download_url,
            release_type=release_map.get(int(item.get("releaseType") or 0), "unknown"),  # type: ignore[arg-type]
            game_versions=[str(value) for value in item.get("gameVersions") or [] if isinstance(value, str)],
            dependencies=dependencies,
            file_date=str(item.get("fileDate") or ""),
            file_length=int(item.get("fileLength") or 0),
            hashes=hashes,
            restricted=not bool(download_url),
        )


    def get_curseforge_file(project_id: int, file_id: int) -> CurseForgeFile:
        data = curseforge_get(f"/v1/mods/{project_id}/files/{file_id}", {})
        item = data.get("data")
        if not isinstance(item, dict):
            raise HTTPException(status_code=502, detail="CurseForge file response is invalid")
        return transform_file(project_id, item)


    @router.get("/api/curseforge/projects/{project_id}/files", response_model=CurseForgeFilesPayload)
    def curseforge_files(
        project_id: int,
        minecraft_version: str = "",
        loader: Literal["any", "forge", "fabric", "quilt", "neoforge"] = "any",
        page_size: int = Query(default=20, ge=1, le=50),
        index: int = Query(default=0, ge=0),
    ) -> CurseForgeFilesPayload:
        params: dict[str, int | str] = {"pageSize": page_size, "index": index}
        if minecraft_version.strip():
            params["gameVersion"] = minecraft_version.strip()
        mod_loader_type = CURSEFORGE_LOADER_TYPES[loader]
        if mod_loader_type is not None:
            params["modLoaderType"] = mod_loader_type
        data = curseforge_get(f"/v1/mods/{project_id}/files", params)
        raw_items = data.get("data") or []
        items = [transform_file(project_id, item) for item in raw_items if isinstance(item, dict)]
        return CurseForgeFilesPayload(items=items, has_api_key=True)


    @router.get("/api/curseforge/projects/{project_id}/files/{file_id}", response_model=CurseForgeFile)
    def curseforge_file(project_id: int, file_id: int) -> CurseForgeFile:
        return get_curseforge_file(project_id, file_id)


    @router.get("/api/curseforge/projects/{project_id}/files/{file_id}/dependencies", response_model=list[CurseForgeFile])
    def curseforge_dependencies(project_id: int, file_id: int) -> list[CurseForgeFile]:
        file = get_curseforge_file(project_id, file_id)
        dependencies = []
        for dependency in file.dependencies:
            if dependency.required and dependency.relation_type == 3:
                files_payload = curseforge_files(dependency.mod_id, page_size=1)
                dependencies.extend(files_payload.items[:1])
        return dependencies


    def download_curseforge_file(file: CurseForgeFile) -> bytes:
        if not file.download_url:
            raise HTTPException(status_code=409, detail=f"{file.file_name} has restricted download")
        try:
            response = httpx.get(file.download_url, follow_redirects=True, timeout=120)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise HTTPException(status_code=502, detail=f"Failed to download {file.file_name}") from error
        if len(response.content) > 128 * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"{file.file_name} is too large")
        return response.content


    def install_curseforge_jar(server_id: str, file: CurseForgeFile, content: bytes):
        return agent_client.install_mod(
            server_id,
            ModInstallRequest(
                filename=file.file_name,
                content=base64.b64encode(content).decode("ascii"),
                source="curseforge",
                project_id=str(file.mod_id),
                file_id=str(file.id),
            ),
        )


    def install_curseforge_modpack(server_id: str, archive_bytes: bytes) -> tuple[list, list[str]]:
        installed = []
        skipped: list[str] = []
        try:
            archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
        except zipfile.BadZipFile as error:
            raise HTTPException(status_code=400, detail="CurseForge modpack archive is invalid") from error

        names = set(archive.namelist())
        if "manifest.json" in names:
            try:
                manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                raise HTTPException(status_code=400, detail="CurseForge manifest.json is invalid") from error
            for item in manifest.get("files") or []:
                if not isinstance(item, dict) or not item.get("required", True):
                    continue
                project_id = int(item.get("projectID") or item.get("projectId") or 0)
                file_id = int(item.get("fileID") or item.get("fileId") or 0)
                if not project_id or not file_id:
                    continue
                child = get_curseforge_file(project_id, file_id)
                if child.restricted:
                    skipped.append(f"{child.file_name}: restricted download")
                    continue
                try:
                    installed.append(install_curseforge_jar(server_id, child, download_curseforge_file(child)))
                except Exception as error:
                    skipped.append(f"{child.file_name}: {error}")

        for name in sorted(names):
            if not name.startswith("mods/") or not name.endswith(".jar"):
                continue
            jar_name = name.rsplit("/", 1)[-1]
            try:
                installed.append(
                    agent_client.install_mod(
                        server_id,
                        ModInstallRequest(
                            filename=jar_name,
                            content=base64.b64encode(archive.read(name)).decode("ascii"),
                            source="curseforge",
                        ),
                    ),
                )
            except Exception as error:
                skipped.append(f"{jar_name}: {error}")
        for prefix in ("overrides/", "serverfiles/"):
            for name in sorted(names):
                if not name.startswith(prefix) or name.endswith("/"):
                    continue
                relative_path = name.removeprefix(prefix)
                if not relative_path or relative_path.startswith("../") or "/../" in relative_path:
                    continue
                if relative_path.startswith("mods/") and relative_path.endswith(".jar"):
                    continue
                try:
                    agent_client.write_file(
                        server_id,
                        FileWriteRequest(
                            path=relative_path,
                            content=base64.b64encode(archive.read(name)).decode("ascii"),
                            encoding="base64",
                        ),
                    )
                except Exception as error:
                    skipped.append(f"{relative_path}: {error}")
        return installed, skipped


    @router.post("/api/curseforge/install", response_model=CurseForgeInstallResult)
    def install_curseforge_file(payload: CurseForgeInstallRequest) -> CurseForgeInstallResult:
        if not agent_client.configured:
            raise HTTPException(status_code=409, detail="Host agent is required for CurseForge install")
        queue = [get_curseforge_file(payload.project_id, payload.file_id)]
        if payload.include_dependencies:
            queue.extend(curseforge_dependencies(payload.project_id, payload.file_id))
        installed = []
        skipped = []
        for file in queue:
            if file.restricted:
                skipped.append(f"{file.file_name}: restricted download")
                continue
            content = download_curseforge_file(file)
            try:
                if file.file_name.endswith(".zip"):
                    modpack_installed, modpack_skipped = install_curseforge_modpack(payload.server_id, content)
                    installed.extend(modpack_installed)
                    skipped.extend(modpack_skipped)
                else:
                    installed.append(install_curseforge_jar(payload.server_id, file, content))
            except Exception as error:
                skipped.append(f"{file.file_name}: {error}")
        if installed:
            try:
                agent_client.refresh_manifest(payload.server_id)
            except Exception as error:
                skipped.append(f"manifest refresh: {error}")
        append_log(f"{payload.server_id}: CurseForge installed {len(installed)}, skipped {len(skipped)}")
        return CurseForgeInstallResult(ok=bool(installed), message=f"Installed {len(installed)} files", installed=installed, skipped=skipped)


    @router.get("/api/files", response_model=list[FileItem])
    def list_files() -> list[FileItem]:
        return files

    return router
