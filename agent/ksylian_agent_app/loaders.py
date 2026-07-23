from __future__ import annotations

import json
import shlex
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from .config import (
    AGENT_USER_AGENT,
    FABRIC_META_API_URL,
    FORGE_MAVEN_URL,
    MINECRAFT_USER,
    MINECRAFT_VERSION_MANIFEST_URL,
    MODRINTH_API_URL,
    NEOFORGE_MAVEN_URL,
    PAPER_API_URL,
    PURPUR_API_URL,
    SERVER_ROOT,
    SYSTEMD_DIR,
)
from .hashing import file_digest
from .minecraft import (
    java_binary,
    minecraft_version_key,
    normalize_cpu_limit,
    normalize_ram,
    required_java_major,
    start_command_for_server,
    write_server_scaffold,
)
from .processes import apply_server_permissions, run, run_in
from .schemas import StoredServer
from .security import is_relative_path, server_base_path


def request_json(url: str, timeout: int = 30) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": AGENT_USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise HTTPException(status_code=502, detail=f"Download metadata request failed: HTTP {error.code}") from error
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=502, detail=f"Download metadata request failed: {error}") from error


def request_text(url: str, timeout: int = 30) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": AGENT_USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        raise HTTPException(status_code=502, detail=f"Download metadata request failed: HTTP {error.code}") from error
    except (urllib.error.URLError, TimeoutError, UnicodeDecodeError) as error:
        raise HTTPException(status_code=502, detail=f"Download metadata request failed: {error}") from error


def download_file(
    url: str,
    destination: Path,
    *,
    md5: str = "",
    sha1: str = "",
    sha256: str = "",
    sha512: str = "",
    minimum_size: int = 1024,
) -> None:
    if not is_relative_path(destination, SERVER_ROOT):
        raise HTTPException(status_code=400, detail="Download destination is outside allowed directory")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(f"{destination.suffix}.tmp")
    last_error: Exception | None = None

    for attempt in range(3):
        request = urllib.request.Request(url, headers={"User-Agent": AGENT_USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=180) as response, temporary.open("wb") as file:
                shutil.copyfileobj(response, file)
            if temporary.stat().st_size < minimum_size:
                raise OSError("downloaded file is unexpectedly small")
            if md5 and file_digest(temporary, "md5").lower() != md5.lower():
                raise OSError("downloaded file md5 checksum mismatch")
            if sha1 and file_digest(temporary, "sha1").lower() != sha1.lower():
                raise OSError("downloaded file sha1 checksum mismatch")
            if sha256 and file_digest(temporary, "sha256").lower() != sha256.lower():
                raise OSError("downloaded file sha256 checksum mismatch")
            if sha512 and file_digest(temporary, "sha512").lower() != sha512.lower():
                raise OSError("downloaded file sha512 checksum mismatch")
            temporary.replace(destination)
            return
        except urllib.error.HTTPError as error:
            temporary.unlink(missing_ok=True)
            last_error = error
            if error.code < 500:
                break
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            temporary.unlink(missing_ok=True)
            last_error = error
        if attempt < 2:
            time.sleep(1 + attempt)

    if isinstance(last_error, urllib.error.HTTPError):
        raise HTTPException(status_code=502, detail=f"Server jar download failed: HTTP {last_error.code}") from last_error
    raise HTTPException(status_code=502, detail=f"Server jar download failed: {last_error}") from last_error


def download_vanilla_server_jar(version: str, destination: Path) -> None:
    manifest = request_json(MINECRAFT_VERSION_MANIFEST_URL)
    versions = manifest.get("versions")
    if not isinstance(versions, list):
        raise HTTPException(status_code=502, detail="Minecraft version manifest is invalid")

    version_url = ""
    for item in versions:
        if isinstance(item, dict) and item.get("id") == version:
            version_url = str(item.get("url") or "")
            break
    if not version_url:
        raise HTTPException(status_code=404, detail=f"Minecraft version {version} was not found")

    metadata = request_json(version_url)
    server_download = metadata.get("downloads", {}).get("server", {})
    server_url = str(server_download.get("url") or "")
    server_sha1 = str(server_download.get("sha1") or "")
    if not server_url:
        raise HTTPException(status_code=404, detail=f"Server jar for Minecraft {version} was not found")

    download_file(server_url, destination, sha1=server_sha1)


def download_paper_server_jar(version: str, destination: Path) -> None:
    builds = request_json(f"{PAPER_API_URL}/versions/{version}/builds")
    if not isinstance(builds, list) or not builds:
        raise HTTPException(status_code=404, detail=f"Paper build for Minecraft {version} was not found")

    selected = next((item for item in builds if isinstance(item, dict) and item.get("channel") == "STABLE"), None)
    if selected is None:
        selected = next((item for item in builds if isinstance(item, dict)), None)
    if selected is None:
        raise HTTPException(status_code=404, detail=f"Paper build for Minecraft {version} was not found")

    download = selected.get("downloads", {}).get("server:default", {})
    download_url = str(download.get("url") or "")
    checksum = str(download.get("checksums", {}).get("sha256") or "")
    if not download_url:
        raise HTTPException(status_code=404, detail=f"Paper server jar for Minecraft {version} was not found")

    download_file(download_url, destination, sha256=checksum)


def download_purpur_server_jar(version: str, destination: Path) -> None:
    metadata = request_json(f"{PURPUR_API_URL}/{version}")
    builds = metadata.get("builds") if isinstance(metadata, dict) else None
    latest = str(builds.get("latest") or "") if isinstance(builds, dict) else ""
    if not latest:
        raise HTTPException(status_code=404, detail=f"Purpur build for Minecraft {version} was not found")

    build_metadata = request_json(f"{PURPUR_API_URL}/{version}/{latest}")
    checksum = str(build_metadata.get("md5") or "") if isinstance(build_metadata, dict) else ""
    download_file(f"{PURPUR_API_URL}/{version}/{latest}/download", destination, md5=checksum)


def latest_fabric_component(path: str, label: str) -> str:
    items = request_json(f"{FABRIC_META_API_URL}{path}")
    if not isinstance(items, list):
        raise HTTPException(status_code=502, detail=f"Fabric {label} metadata is invalid")
    for item in items:
        if isinstance(item, dict) and item.get("stable") is True and item.get("version"):
            return str(item["version"])
    for item in items:
        if isinstance(item, dict) and item.get("version"):
            return str(item["version"])
    raise HTTPException(status_code=404, detail=f"Fabric {label} version was not found")


def fabric_loader_versions(minecraft_version: str = "") -> list[str]:
    path = f"/versions/loader/{minecraft_version}" if minecraft_version else "/versions/loader"
    items = request_json(f"{FABRIC_META_API_URL}{path}")
    if not isinstance(items, list):
        raise HTTPException(status_code=502, detail="Fabric loader metadata is invalid")
    versions: list[str] = []
    for item in items:
        loader = item.get("loader") if isinstance(item, dict) and minecraft_version else item
        if isinstance(loader, dict) and loader.get("version"):
            versions.append(str(loader["version"]))
    return list(dict.fromkeys(versions))


def fabric_installer_versions() -> list[str]:
    items = request_json(f"{FABRIC_META_API_URL}/versions/installer")
    if not isinstance(items, list):
        raise HTTPException(status_code=502, detail="Fabric installer metadata is invalid")
    return [str(item["version"]) for item in items if isinstance(item, dict) and item.get("version")]


def download_fabric_server_jar(
    version: str,
    destination: Path,
    loader_version: str = "",
    installer_version: str = "",
) -> None:
    loaders = request_json(f"{FABRIC_META_API_URL}/versions/loader/{version}")
    if not isinstance(loaders, list) or not loaders:
        raise HTTPException(status_code=404, detail=f"Fabric loader for Minecraft {version} was not found")

    selected_loader_version = loader_version.strip()
    if selected_loader_version and selected_loader_version not in fabric_loader_versions(version):
        raise HTTPException(status_code=404, detail=f"Fabric loader {selected_loader_version} for Minecraft {version} was not found")
    loader_version = selected_loader_version
    for item in loaders:
        loader = item.get("loader") if isinstance(item, dict) else None
        if not loader_version and isinstance(loader, dict) and loader.get("stable") is True and loader.get("version"):
            loader_version = str(loader["version"])
            break
    if not loader_version:
        loader = loaders[0].get("loader") if isinstance(loaders[0], dict) else None
        loader_version = str(loader.get("version") or "") if isinstance(loader, dict) else ""
    if not loader_version:
        raise HTTPException(status_code=404, detail=f"Fabric loader for Minecraft {version} was not found")

    installer_versions = fabric_installer_versions()
    selected_installer_version = installer_version.strip()
    if selected_installer_version and selected_installer_version not in installer_versions:
        raise HTTPException(status_code=404, detail=f"Fabric installer {selected_installer_version} was not found")
    installer_version = selected_installer_version or latest_fabric_component("/versions/installer", "installer")
    download_file(
        f"{FABRIC_META_API_URL}/versions/loader/{version}/{loader_version}/{installer_version}/server/jar",
        destination,
    )


def install_fabric_api(server: StoredServer) -> None:
    mods_dir = server_base_path(server) / "mods"
    mods_dir.mkdir(parents=True, exist_ok=True)
    query = urllib.parse.urlencode({"loaders": '["fabric"]', "game_versions": json.dumps([server.version])})
    versions = request_json(f"{MODRINTH_API_URL}/project/fabric-api/version?{query}")
    if not isinstance(versions, list) or not versions:
        raise HTTPException(status_code=404, detail=f"Fabric API for Minecraft {server.version} was not found")
    selected = next((item for item in versions if isinstance(item, dict) and item.get("version_type") == "release"), None)
    selected = selected or next((item for item in versions if isinstance(item, dict)), None)
    files = selected.get("files") if isinstance(selected, dict) else None
    primary = next((item for item in files if isinstance(item, dict) and item.get("primary")), None) if isinstance(files, list) else None
    file_item = primary or (files[0] if isinstance(files, list) and files else None)
    if not isinstance(file_item, dict):
        raise HTTPException(status_code=404, detail="Fabric API download was not found")
    filename = Path(str(file_item.get("filename") or "fabric-api.jar")).name
    url = str(file_item.get("url") or "")
    sha512 = str(file_item.get("hashes", {}).get("sha512") or "")
    if not url:
        raise HTTPException(status_code=404, detail="Fabric API download URL was not found")
    download_file(url, mods_dir / filename, sha512=sha512)


def forge_versions() -> list[str]:
    metadata = request_text(f"{FORGE_MAVEN_URL}/maven-metadata.xml")
    try:
        root = ET.fromstring(metadata)
    except ET.ParseError as error:
        raise HTTPException(status_code=502, detail="Forge metadata is invalid") from error
    return [item.text.strip() for item in root.findall(".//version") if item.text and item.text.strip()]


def latest_forge_version(minecraft_version: str, selected_version: str = "") -> str:
    if selected_version.strip():
        versions = forge_versions()
        if selected_version.strip() not in versions:
            raise HTTPException(status_code=404, detail=f"Forge build {selected_version} was not found")
        return selected_version.strip()
    prefix = f"{minecraft_version}-"
    matches = [version for version in forge_versions() if version.startswith(prefix)]
    if not matches:
        raise HTTPException(status_code=404, detail=f"Forge build for Minecraft {minecraft_version} was not found")
    return matches[-1]


def neoforge_versions() -> list[str]:
    metadata = request_text(f"{NEOFORGE_MAVEN_URL}/maven-metadata.xml")
    try:
        root = ET.fromstring(metadata)
    except ET.ParseError as error:
        raise HTTPException(status_code=502, detail="NeoForge metadata is invalid") from error
    return [item.text.strip() for item in root.findall(".//version") if item.text and item.text.strip()]


def latest_neoforge_version(minecraft_version: str, selected_version: str = "") -> str:
    versions = neoforge_versions()
    if selected_version.strip():
        if selected_version.strip() not in versions:
            raise HTTPException(status_code=404, detail=f"NeoForge build {selected_version} was not found")
        return selected_version.strip()
    # NeoForge 1.20.2+ versions are commonly published as 20.2.x, 20.4.x, etc.
    version = minecraft_version_key(minecraft_version)
    prefix = f"{version[1]}.{version[2]}." if version[0] == 1 and version[1] >= 20 else minecraft_version
    matches = [item for item in versions if item.startswith(prefix)]
    if not matches:
        matches = [item for item in versions if minecraft_version in item]
    if not matches:
        raise HTTPException(status_code=404, detail=f"NeoForge build for Minecraft {minecraft_version} was not found")
    return matches[-1]


def install_forge_server(server: StoredServer) -> list[str]:
    server_path = server_base_path(server)
    forge_version = latest_forge_version(server.version, server.loader_version)
    installer = server_path / f"forge-{forge_version}-installer.jar"
    download_file(f"{FORGE_MAVEN_URL}/{forge_version}/forge-{forge_version}-installer.jar", installer)

    java = java_binary(server.version, server.java_runtime)
    min_ram = normalize_ram(server.min_ram, "1G")
    max_ram = normalize_ram(server.max_ram, "2G")
    result = run_in([java, "-jar", str(installer), "--installServer"], cwd=server_path, timeout=600)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "Forge installer failed"
        raise HTTPException(status_code=502, detail=detail)

    unix_args = server_path / "libraries" / "net" / "minecraftforge" / "forge" / forge_version / "unix_args.txt"
    if unix_args.exists():
        return [
            java,
            f"-Xms{min_ram}",
            f"-Xmx{max_ram}",
            *server.jvm_args,
            "@libraries/net/minecraftforge/forge/{forge_version}/unix_args.txt".format(forge_version=forge_version),
            "nogui",
        ]

    forge_jar = next(server_path.glob(f"forge-{forge_version}*.jar"), None)
    if forge_jar:
        return [java, f"-Xms{min_ram}", f"-Xmx{max_ram}", *server.jvm_args, "-jar", forge_jar.name, "nogui"]

    raise HTTPException(status_code=502, detail="Forge installer did not produce a runnable server")


def install_neoforge_server(server: StoredServer) -> list[str]:
    server_path = server_base_path(server)
    neoforge_version = latest_neoforge_version(server.version, server.loader_version)
    installer = server_path / f"neoforge-{neoforge_version}-installer.jar"
    download_file(f"{NEOFORGE_MAVEN_URL}/{neoforge_version}/neoforge-{neoforge_version}-installer.jar", installer)

    java = java_binary(server.version, server.java_runtime)
    min_ram = normalize_ram(server.min_ram, "1G")
    max_ram = normalize_ram(server.max_ram, "2G")
    result = run_in([java, "-jar", str(installer), "--installServer"], cwd=server_path, timeout=600)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "NeoForge installer failed"
        raise HTTPException(status_code=502, detail=detail)

    unix_args = server_path / "libraries" / "net" / "neoforged" / "neoforge" / neoforge_version / "unix_args.txt"
    if unix_args.exists():
        return [
            java,
            f"-Xms{min_ram}",
            f"-Xmx{max_ram}",
            *server.jvm_args,
            f"@libraries/net/neoforged/neoforge/{neoforge_version}/unix_args.txt",
            "nogui",
        ]

    neoforge_jar = next(server_path.glob(f"neoforge-{neoforge_version}*.jar"), None)
    if neoforge_jar:
        return [java, f"-Xms{min_ram}", f"-Xmx{max_ram}", *server.jvm_args, "-jar", neoforge_jar.name, "nogui"]

    raise HTTPException(status_code=502, detail="NeoForge installer did not produce a runnable server")


class ServerLoader:
    loader_type = "vanilla"

    def versions(self) -> list[str]:
        return []

    def install(self, server: StoredServer) -> StoredServer:
        return server

    def update(self, server: StoredServer) -> StoredServer:
        return self.install(server)

    def required_java(self, server: StoredServer) -> int:
        return required_java_major(server.version)

    def command(self, server: StoredServer) -> list[str]:
        return server.start_command

    def installed_version(self, server: StoredServer) -> str:
        return server.version


class JarServerLoader(ServerLoader):
    def __init__(self, loader_type: str, downloader: Any):
        self.loader_type = loader_type
        self.downloader = downloader

    def install(self, server: StoredServer) -> StoredServer:
        java = java_binary(server.version, server.java_runtime)
        destination = server_base_path(server) / "server.jar"
        if not destination.exists():
            self.downloader(server.version, destination)
        server.start_command = start_command_for_server(server, java)
        return server


class FabricLoader(JarServerLoader):
    def __init__(self):
        super().__init__("fabric", download_fabric_server_jar)

    def command(self, server: StoredServer) -> list[str]:
        return start_command_for_server(server, java_binary(server.version, server.java_runtime))

    def install(self, server: StoredServer) -> StoredServer:
        destination = server_base_path(server) / "server.jar"
        if not destination.exists():
            download_fabric_server_jar(server.version, destination, server.loader_version, server.installer_version)
        if server.install_fabric_api:
            install_fabric_api(server)
        server.start_command = start_command_for_server(server, java_binary(server.version, server.java_runtime))
        return server


class ForgeLoader(ServerLoader):
    loader_type = "forge"

    def versions(self) -> list[str]:
        return forge_versions()

    def install(self, server: StoredServer) -> StoredServer:
        if not server.start_command:
            server.start_command = install_forge_server(server)
        return server


class NeoForgeLoader(ServerLoader):
    loader_type = "neoforge"

    def versions(self) -> list[str]:
        return neoforge_versions()

    def install(self, server: StoredServer) -> StoredServer:
        if not server.start_command:
            server.start_command = install_neoforge_server(server)
        return server


SERVER_LOADERS: dict[str, ServerLoader] = {
    "vanilla": JarServerLoader("vanilla", download_vanilla_server_jar),
    "paper": JarServerLoader("paper", download_paper_server_jar),
    "purpur": JarServerLoader("purpur", download_purpur_server_jar),
    "fabric": FabricLoader(),
    "forge": ForgeLoader(),
    "neoforge": NeoForgeLoader(),
}


def provision_server_files(server: StoredServer) -> StoredServer:
    loader = SERVER_LOADERS.get(server.type)
    if loader:
        return loader.install(server)
    raise HTTPException(status_code=400, detail=f"Server type {server.type} cannot be provisioned")


def update_server_files(server: StoredServer) -> StoredServer:
    if not server.managed:
        raise HTTPException(status_code=409, detail="Legacy servers cannot be updated by Ksylian")
    server_path = server_base_path(server)
    if server.type in {"vanilla", "paper", "purpur", "fabric"}:
        (server_path / "server.jar").unlink(missing_ok=True)
    if server.type == "forge":
        server.start_command = []
    if server.type == "neoforge":
        server.start_command = []
    return ensure_server_provisioned(server)


def write_systemd_unit(server: StoredServer) -> None:
    unit_path = SYSTEMD_DIR / server.service
    start_command = server.start_command or start_command_for_server(server, java_binary(server.version, server.java_runtime))
    server_path = server_base_path(server)
    max_ram = normalize_ram(server.max_ram, "2G")
    cpu_quota = f"{normalize_cpu_limit(server.cpu_limit)}%"
    content = "\n".join(
        [
            "[Unit]",
            f"Description=Ksylian Minecraft Server {server.name}",
            "After=network.target",
            "",
            "[Service]",
            "Type=simple",
            f"User={MINECRAFT_USER}",
            f"Group={MINECRAFT_USER}",
            f"WorkingDirectory={server_path}",
            f"ExecStart={shlex.join(start_command)}",
            "Restart=on-failure",
            "RestartSec=10",
            "SuccessExitStatus=0 143",
            f"MemoryMax={max_ram}",
            f"CPUQuota={cpu_quota}",
            "NoNewPrivileges=true",
            "PrivateTmp=true",
            "ProtectSystem=full",
            "ProtectHome=true",
            f"ReadWritePaths={server_path}",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "",
        ]
    )
    unit_path.write_text(content)

    daemon_reload = run(["systemctl", "daemon-reload"], timeout=30)
    if daemon_reload.returncode != 0:
        raise HTTPException(status_code=500, detail=daemon_reload.stderr.strip() or "systemctl daemon-reload failed")

    enable = run(["systemctl", "enable", server.service], timeout=30)
    if enable.returncode != 0:
        raise HTTPException(status_code=500, detail=enable.stderr.strip() or "systemctl enable failed")


def ensure_server_provisioned(server: StoredServer) -> StoredServer:
    if not server.managed:
        return server

    write_server_scaffold(server)
    server = provision_server_files(server)
    apply_server_permissions(server)

    write_systemd_unit(server)
    return server
