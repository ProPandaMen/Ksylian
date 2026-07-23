from __future__ import annotations

import re
import shutil
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException

from .activity import append_action_log
from .loaders import write_systemd_unit
from .manifest import save_manifest
from .minecraft import allocate_port, host_primary_ip, normalize_cpu_limit, normalize_jvm_args, normalize_ram, server_type_label
from .mods import scan_installed_mods
from .processes import apply_server_permissions, run, service_state
from .schemas import AgentActionResult, AgentServer, ImportServerPreview, ImportServerRequest, StoredServer
from .security import managed_server_path, server_base_path
from .storage import load_server_store, save_server_store, slugify


def read_properties(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def detect_version(root: Path, properties: dict[str, str]) -> str:
    for key in ("minecraft-version", "version"):
        if properties.get(key):
            return properties[key]
    candidates = " ".join(path.name for path in root.glob("*.jar"))
    match = re.search(r"(?<!\d)(1\.\d+(?:\.\d+)?)(?!\d)", candidates)
    return match.group(1) if match else ""


def detect_loader(root: Path) -> tuple[str, str]:
    jar_names = " ".join(path.name.lower() for path in root.glob("*.jar"))
    if (root / "fabric-server-launch.jar").exists() or "fabric" in jar_names:
        return "fabric", ""
    if "neoforge" in jar_names or (root / "libraries/net/neoforged").exists():
        match = re.search(r"neoforge[-_. ]([0-9][0-9A-Za-z_.-]+)", jar_names)
        return "neoforge", match.group(1) if match else ""
    if "forge" in jar_names or (root / "libraries/net/minecraftforge").exists():
        match = re.search(r"forge[-_. ]([0-9][0-9A-Za-z_.-]+)", jar_names)
        return "forge", match.group(1) if match else ""
    if "purpur" in jar_names:
        return "purpur", ""
    if "paper" in jar_names:
        return "paper", ""
    return "vanilla", ""


def detect_start_command(root: Path, java_runtime: str, min_ram: str, max_ram: str, jvm_args: list[str]) -> list[str]:
    for script in ("run.sh", "start.sh"):
        path = root / script
        if path.exists():
            return ["bash", script]
    preferred = ["server.jar", "fabric-server-launch.jar"]
    for name in preferred:
        if (root / name).exists():
            return ["java", f"-Xms{min_ram}", f"-Xmx{max_ram}", *jvm_args, "-jar", name, "nogui"]
    jars = sorted(root.glob("*.jar"), key=lambda item: item.name.lower())
    if jars:
        return ["java", f"-Xms{min_ram}", f"-Xmx{max_ram}", *jvm_args, "-jar", jars[0].name, "nogui"]
    return ["java", f"-Xms{min_ram}", f"-Xmx{max_ram}", *jvm_args, "-jar", "server.jar", "nogui"]


def preview_existing_server(path: str, name: str = "") -> ImportServerPreview:
    root = Path(path).expanduser().resolve()
    warnings: list[str] = []
    if not root.exists() or not root.is_dir():
        raise HTTPException(status_code=404, detail="Server directory was not found")
    properties = read_properties(root / "server.properties")
    loader, loader_version = detect_loader(root)
    version = detect_version(root, properties)
    port = int(properties.get("server-port") or 25565)
    if not (root / "eula.txt").exists():
        warnings.append("eula.txt не найден")
    if not properties:
        warnings.append("server.properties не найден или пуст")
    if not list(root.glob("*.jar")) and not (root / "run.sh").exists():
        warnings.append("Не найден server jar или run.sh")
    if not version:
        warnings.append("Версия Minecraft не определена автоматически")
    temporary = StoredServer(
        id="preview",
        name=name.strip() or root.name,
        type=loader,  # type: ignore[arg-type]
        pack=server_type_label(loader),
        version=version,
        port=port,
        service="preview.service",
        path=str(root),
        backup_path=str(root / "world"),
        address=f"{host_primary_ip()}:{port}",
        created_at=datetime.now().isoformat(timespec="seconds"),
        managed=False,
    )
    mod_count = len(scan_installed_mods(temporary))
    return ImportServerPreview(
        ok=not warnings,
        name=name.strip() or root.name,
        path=str(root),
        type=loader,  # type: ignore[arg-type]
        version=version,
        loader_version=loader_version,
        java_runtime="auto",
        port=port,
        has_server_properties=bool(properties),
        mod_count=mod_count,
        warnings=warnings,
    )


def import_existing_server(
    request: ImportServerRequest,
    *,
    server_snapshot: Callable[[str], AgentServer],
) -> AgentActionResult:
    preview = preview_existing_server(request.path, request.name)
    source_root = Path(request.path).expanduser().resolve()
    store = load_server_store()
    base_id = slugify(request.name or source_root.name)
    server_id = base_id
    counter = 2
    while server_id in store:
        server_id = f"{base_id}-{counter}"
        counter += 1

    if request.keep_current_path:
        target_root = source_root
        managed = False
    else:
        target_root = managed_server_path(server_id)
        if target_root.exists():
            raise HTTPException(status_code=409, detail="Managed target directory already exists")
        shutil.copytree(source_root, target_root)
        managed = True

    properties = read_properties(target_root / "server.properties")
    port = int(properties.get("server-port") or preview.port or allocate_port(store))
    service = f"ksylian-{server_id}.service"
    min_ram = normalize_ram(request.min_ram, "1G")
    max_ram = normalize_ram(request.max_ram, "2G")
    jvm_args = normalize_jvm_args(request.jvm_args)
    server = StoredServer(
        id=server_id,
        name=request.name.strip() or source_root.name,
        type=preview.type,
        pack=server_type_label(preview.type),
        version=preview.version or "unknown",
        port=port,
        service=service,
        path=str(target_root),
        backup_path=str(target_root / "world"),
        address=f"{host_primary_ip()}:{port}",
        created_at=datetime.now().isoformat(timespec="seconds"),
        managed=managed,
        start_command=detect_start_command(target_root, request.java_runtime, min_ram, max_ram, jvm_args),
        min_ram=min_ram,
        max_ram=max_ram,
        java_runtime=request.java_runtime if request.java_runtime in {"auto", "8", "17", "21"} else "auto",
        jvm_args=jvm_args,
        cpu_limit=normalize_cpu_limit(request.cpu_limit),
        loader_version=request.loader_version.strip() or preview.loader_version,
    )
    store[server.id] = server
    save_server_store(store)
    apply_server_permissions(server)
    write_systemd_unit(server)
    save_manifest(server)

    start_result = run(["systemctl", "start", service], timeout=90)
    if start_result.returncode != 0:
        append_action_log("server_import_start_failed", server.id, start_result.stderr.strip())
    append_action_log("server_import", server.id, str(server_base_path(server)))
    message = f"{server.name}: imported"
    if service_state(service) != "running":
        message += ", unit created but startup needs review"
    return AgentActionResult(ok=True, message=message, server=server_snapshot(server.id))
