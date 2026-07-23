from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException

from .activity import append_action_log
from .backups import create_backup_archive, latest_restore_candidate, restore_backup
from .manifest import build_manifest, clone_server_for_test, diff_manifests, save_manifest
from .processes import run, service_state
from .runtime import server_runtime_states
from .schemas import AgentServer, BackupRequest, ModUpdatePlan, RestoreRequest, SafeUpdateRequest, SafeUpdateResult, StoredServer


def create_update_plan(server: StoredServer) -> ModUpdatePlan:
    current = build_manifest(server)
    saved = save_manifest(server, current)
    return ModUpdatePlan(
        server_id=server.id,
        created_at=datetime.now().isoformat(timespec="seconds"),
        items=[],
        diff=diff_manifests(saved, current),
        warnings=[
            "Автоматический поиск новых файлов зависит от marketplace source metadata",
            "План без candidate-файлов оставляет моды без изменений",
        ],
    )


def analyze_test_logs(test_root) -> list[str]:
    findings: list[str] = []
    for path in (test_root / "logs").glob("*.log") if (test_root / "logs").exists() else []:
        try:
            content = path.read_text(errors="replace")
        except OSError:
            continue
        for marker in ("ERROR", "FATAL", "Missing", "requires", "depends on", "Incompatible"):
            if marker in content:
                findings.append(f"{path.name}: найдено {marker}")
    if (test_root / "crash-reports").exists():
        reports = sorted((test_root / "crash-reports").glob("*.txt"))
        if reports:
            findings.append(f"crash-report: {reports[-1].name}")
    return findings[:20]


def harden_test_properties(test_root: Path) -> None:
    properties = test_root / "server.properties"
    lines = []
    existing: dict[str, str] = {}
    if properties.exists():
        for line in properties.read_text(errors="replace").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key, value = line.split("=", 1)
                existing[key.strip()] = value.strip()
    existing.update(
        {
            "server-port": "0",
            "enable-query": "false",
            "enable-rcon": "false",
            "online-mode": "false",
            "motd": "Ksylian safe update test",
        },
    )
    for key, value in existing.items():
        lines.append(f"{key}={value}")
    properties.write_text("\n".join(lines) + "\n")
    (test_root / "eula.txt").write_text("eula=true\n")


def test_start_command(server: StoredServer, test_root: Path) -> list[str]:
    if server.start_command:
        return list(server.start_command)
    for script in ("run.sh", "start.sh"):
        if (test_root / script).exists():
            return ["bash", script]
    for name in ("server.jar", "fabric-server-launch.jar"):
        if (test_root / name).exists():
            return ["java", f"-Xms{server.min_ram}", f"-Xmx{server.max_ram}", "-jar", name, "nogui"]
    jars = sorted(test_root.glob("*.jar"), key=lambda item: item.name.lower())
    if jars:
        return ["java", f"-Xms{server.min_ram}", f"-Xmx{server.max_ram}", "-jar", jars[0].name, "nogui"]
    raise HTTPException(status_code=409, detail="Test instance has no runnable server jar")


def run_test_instance(server: StoredServer, test_root: Path, timeout_seconds: int) -> list[str]:
    harden_test_properties(test_root)
    command = test_start_command(server, test_root)
    findings: list[str] = []
    process = subprocess.Popen(
        command,
        cwd=test_root,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    wait_seconds = max(15, min(timeout_seconds, 600))
    try:
        output_text, _ = process.communicate(timeout=wait_seconds)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            output_text, _ = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            output_text, _ = process.communicate(timeout=10)
    loaded = False
    for line in output_text.splitlines():
        upper = line.upper()
        if "ERROR" in upper or "FATAL" in upper:
            findings.append(line.strip()[:220])
        if "MISSING" in upper or "REQUIRES" in upper or "DEPENDS ON" in upper:
            findings.append(line.strip()[:220])
        if "DONE" in upper and "HELP" in upper:
            loaded = True
    if process.returncode not in {None, 0, 143, -15} and not loaded:
        findings.append(f"Тестовый сервер завершился с кодом {process.returncode}")
    findings.extend(analyze_test_logs(test_root))
    if not loaded and not findings:
        findings.append("Тестовый запуск не подтвердил полную загрузку до timeout")
    return findings[:30]


def safe_update_modpack(
    server: StoredServer,
    request: SafeUpdateRequest,
    server_snapshot: Callable[[str], AgentServer],
) -> SafeUpdateResult:
    plan = request.plan or create_update_plan(server)
    test_root = clone_server_for_test(server)
    backup_id = ""
    server_runtime_states[server.id] = "updating"
    try:
        findings = run_test_instance(server, test_root, request.timeout_seconds)
        if findings:
            return SafeUpdateResult(
                ok=False,
                message="Тестовый инстанс обнаружил ошибки",
                plan=plan,
                test_instance_path=str(test_root),
                log_findings=findings,
            )
        if not request.apply:
            append_action_log("server_safe_update_test", server.id, "dry-run ok")
            return SafeUpdateResult(
                ok=True,
                message="Тестовый инстанс подготовлен, критичных ошибок не найдено",
                plan=plan,
                test_instance_path=str(test_root),
            )

        backup = create_backup_archive(
            server,
            BackupRequest(mode="stopped", parts=["world", "mods", "config", "root"], description="Before safe modpack update"),
            reason="pre-update",
        )
        backup_id = backup.id
        was_running = service_state(server.service) == "running"
        if was_running:
            result = run(["systemctl", "stop", server.service], timeout=90)
            if result.returncode != 0:
                raise HTTPException(status_code=500, detail=result.stderr.strip() or "Failed to stop server")
        start_result = run(["systemctl", "start", server.service], timeout=max(30, min(request.timeout_seconds, 600)))
        if start_result.returncode != 0:
            restore_backup(server, RestoreRequest(backup_id=latest_restore_candidate(server), target="all", insurance_backup=False), server_snapshot)
            raise HTTPException(status_code=500, detail=start_result.stderr.strip() or "Server failed after safe update")
        save_manifest(server)
        append_action_log("server_safe_update_apply", server.id, backup_id)
        return SafeUpdateResult(ok=True, message="Обновление применено", plan=plan, backup_id=backup_id, test_instance_path=str(test_root))
    finally:
        shutil.rmtree(test_root, ignore_errors=True)
        server_runtime_states.pop(server.id, None)
