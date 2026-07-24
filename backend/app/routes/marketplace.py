from __future__ import annotations

import base64
import hashlib
import io
import json
import zipfile
from collections.abc import Callable
from datetime import datetime
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
    BuildManifestDiff,
    BuildManifestMod,
    ModUpdatePlan,
    ModUpdatePlanItem,
    ModInstallRequest,
    ModItem,
    SafeUpdateResult,
    GameServer,
    ServerOperationProgress,
    ServerState,
)
from ..operation_state import server_operation_state, update_server_operation_progress
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
    get_server: Callable[[str], GameServer],
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
            manifest_files = [
                item
                for item in manifest.get("files") or []
                if isinstance(item, dict) and item.get("required", True)
            ]
        else:
            manifest_files = []
        embedded_mods = [
            name
            for name in sorted(names)
            if name.startswith("mods/") and name.endswith(".jar")
        ]
        override_files = [
            name
            for prefix in ("overrides/", "serverfiles/")
            for name in sorted(names)
            if name.startswith(prefix) and not name.endswith("/")
        ]
        total_files = len(manifest_files) + len(embedded_mods) + len(override_files)
        done = 0
        update_server_operation_progress(
            server_id,
            current=0,
            total=total_files,
            current_item="manifest.json",
            message=f"0 из {total_files} файлов",
        )

        for item in manifest_files:
                project_id = int(item.get("projectID") or item.get("projectId") or 0)
                file_id = int(item.get("fileID") or item.get("fileId") or 0)
                if not project_id or not file_id:
                    done += 1
                    continue
                child = get_curseforge_file(project_id, file_id)
                update_server_operation_progress(
                    server_id,
                    current=done,
                    total=total_files,
                    current_item=child.file_name,
                    message=f"Скачиваю {done + 1} из {total_files}",
                )
                if child.restricted:
                    skipped.append(f"{child.file_name}: restricted download")
                    done += 1
                    update_server_operation_progress(
                        server_id,
                        current=done,
                        total=total_files,
                        current_item=child.file_name,
                        message=f"{done} из {total_files} файлов",
                    )
                    continue
                try:
                    installed.append(install_curseforge_jar(server_id, child, download_curseforge_file(child)))
                except Exception as error:
                    skipped.append(f"{child.file_name}: {error}")
                done += 1
                update_server_operation_progress(
                    server_id,
                    current=done,
                    total=total_files,
                    current_item=child.file_name,
                    message=f"{done} из {total_files} файлов",
                )

        for name in embedded_mods:
            jar_name = name.rsplit("/", 1)[-1]
            update_server_operation_progress(
                server_id,
                current=done,
                total=total_files,
                current_item=jar_name,
                message=f"Устанавливаю {done + 1} из {total_files}",
            )
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
            done += 1
            update_server_operation_progress(
                server_id,
                current=done,
                total=total_files,
                current_item=jar_name,
                message=f"{done} из {total_files} файлов",
            )
        for name in override_files:
            relative_path = name.removeprefix("overrides/").removeprefix("serverfiles/")
            if not relative_path or relative_path.startswith("../") or "/../" in relative_path:
                done += 1
                continue
            if relative_path.startswith("mods/") and relative_path.endswith(".jar"):
                done += 1
                continue
            update_server_operation_progress(
                server_id,
                current=done,
                total=total_files,
                current_item=relative_path,
                message=f"Копирую {done + 1} из {total_files}",
            )
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
            done += 1
            update_server_operation_progress(
                server_id,
                current=done,
                total=total_files,
                current_item=relative_path,
                message=f"{done} из {total_files} файлов",
            )
        return installed, skipped


    @router.post("/api/curseforge/install", response_model=CurseForgeInstallResult)
    def install_curseforge_file(payload: CurseForgeInstallRequest) -> CurseForgeInstallResult:
        if not agent_client.configured:
            raise HTTPException(status_code=409, detail="Host agent is required for CurseForge install")
        get_server(payload.server_id)
        initial_progress = ServerOperationProgress(label="Установка CurseForge", message="Готовлю список файлов")
        with server_operation_state(payload.server_id, ServerState.installing, initial_progress):
            queue = [get_curseforge_file(payload.project_id, payload.file_id)]
            if payload.include_dependencies:
                queue.extend(curseforge_dependencies(payload.project_id, payload.file_id))
            update_server_operation_progress(
                payload.server_id,
                total=len(queue),
                message=f"0 из {len(queue)} файлов",
            )
            installed = []
            skipped = []
            for index, file in enumerate(queue, start=1):
                update_server_operation_progress(
                    payload.server_id,
                    current=index - 1,
                    total=len(queue),
                    current_item=file.file_name,
                    message=f"Скачиваю {index} из {len(queue)}",
                )
                if file.restricted:
                    skipped.append(f"{file.file_name}: restricted download")
                    update_server_operation_progress(
                        payload.server_id,
                        current=index,
                        total=len(queue),
                        current_item=file.file_name,
                        message=f"{index} из {len(queue)} файлов",
                    )
                    continue
                content = download_curseforge_file(file)
                try:
                    update_server_operation_progress(
                        payload.server_id,
                        current=index - 1,
                        total=len(queue),
                        current_item=file.file_name,
                        message=f"Устанавливаю {index} из {len(queue)}",
                    )
                    if file.file_name.endswith(".zip"):
                        modpack_installed, modpack_skipped = install_curseforge_modpack(payload.server_id, content)
                        installed.extend(modpack_installed)
                        skipped.extend(modpack_skipped)
                    else:
                        installed.append(install_curseforge_jar(payload.server_id, file, content))
                except Exception as error:
                    skipped.append(f"{file.file_name}: {error}")
                update_server_operation_progress(
                    payload.server_id,
                    current=index,
                    total=len(queue),
                    current_item=file.file_name,
                    message=f"{index} из {len(queue)} файлов",
                )
            if installed:
                try:
                    update_server_operation_progress(
                        payload.server_id,
                        current=len(queue),
                        total=len(queue),
                        current_item="",
                        message="Обновляю manifest сервера",
                    )
                    agent_client.refresh_manifest(payload.server_id)
                except Exception as error:
                    skipped.append(f"manifest refresh: {error}")
            append_log(f"{payload.server_id}: CurseForge installed {len(installed)}, skipped {len(skipped)}")
            return CurseForgeInstallResult(ok=bool(installed), message=f"Installed {len(installed)} files", installed=installed, skipped=skipped)


    def loader_for_manifest(value: str) -> Literal["any", "forge", "fabric", "quilt", "neoforge"]:
        if value in {"forge", "fabric", "neoforge"}:
            return value  # type: ignore[return-value]
        return "any"


    def choose_update_candidate(current: BuildManifestMod, minecraft_version: str, loader: str) -> CurseForgeFile | None:
        if current.source != "curseforge" or not current.project_id:
            return None
        project_id = int(current.project_id)
        params: dict[str, int | str] = {"pageSize": 50, "index": 0}
        if minecraft_version:
            params["gameVersion"] = minecraft_version
        mod_loader_type = CURSEFORGE_LOADER_TYPES[loader_for_manifest(loader)]
        if mod_loader_type is not None:
            params["modLoaderType"] = mod_loader_type
        data = curseforge_get(f"/v1/mods/{project_id}/files", params)
        raw_items = data.get("data") or []
        first_candidate: CurseForgeFile | None = None
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            candidate = transform_file(project_id, item)
            if candidate.restricted:
                continue
            if not candidate.file_name.endswith(".jar"):
                continue
            if str(candidate.id) == current.file_id:
                return first_candidate
            if first_candidate is None:
                first_candidate = candidate
        return None


    @router.post("/api/servers/{server_id}/updates/resolve", response_model=SafeUpdateResult)
    def resolve_curseforge_updates(server_id: str) -> SafeUpdateResult:
        if not agent_client.configured:
            raise HTTPException(status_code=409, detail="Host agent is required for safe updates")
        manifest = agent_client.refresh_manifest(server_id)
        plan_items: list[ModUpdatePlanItem] = []
        warnings: list[str] = []
        for current in manifest.mods:
            if current.source != "curseforge":
                continue
            try:
                candidate_file = choose_update_candidate(current, manifest.minecraft_version, manifest.loader)
            except Exception as error:
                warnings.append(f"{current.filename}: {error}")
                continue
            if candidate_file is None:
                continue
            try:
                content = download_curseforge_file(candidate_file)
            except Exception as error:
                warnings.append(f"{current.filename}: {error}")
                continue
            candidate = BuildManifestMod(
                id=current.id,
                name=current.name,
                version=candidate_file.display_name or current.version,
                loader=current.loader,
                side=current.side,
                filename=candidate_file.file_name,
                path=f"mods/{candidate_file.file_name}",
                sha256=hashlib.sha256(content).hexdigest(),
                source="curseforge",
                project_id=str(candidate_file.mod_id),
                file_id=str(candidate_file.id),
                installed_at=datetime.now().isoformat(timespec="seconds"),
                dependencies=current.dependencies,
            )
            plan_items.append(
                ModUpdatePlanItem(
                    current=current,
                    candidate=candidate,
                    action="update",
                    reason=f"CurseForge file {candidate_file.id}",
                    content=base64.b64encode(content).decode("ascii"),
                ),
            )
        added = []
        removed = []
        changed = [{"before": item.current, "after": item.candidate} for item in plan_items]
        plan = ModUpdatePlan(
            server_id=server_id,
            created_at=datetime.now().isoformat(timespec="seconds"),
            items=plan_items,
            diff=BuildManifestDiff(added=added, removed=removed, changed=changed),
            warnings=warnings,
        )
        message = f"Найдено обновлений: {len(plan_items)}"
        return SafeUpdateResult(ok=True, message=message, plan=plan)


    @router.get("/api/files", response_model=list[FileItem])
    def list_files() -> list[FileItem]:
        return files

    return router
