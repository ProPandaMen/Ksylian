# Архитектура Ksylian

Обновлено: 2026-07-23

## Agent

`agent/ksylian_agent.py` остаётся совместимой точкой входа для systemd:

```python
from ksylian_agent_app.main import app
```

Основная реализация живёт в пакете `agent/ksylian_agent_app/`. Домены первого agent-среза физически вынесены из бывшего монолита:

- `config.py` — env-конфиг, константы и пути.
- `schemas.py` — Pydantic-модели agent API.
- `security.py` — token/rate-limit/path-safety helpers.
- `storage.py` — store серверов, disabled server ids и slugify.
- `processes.py` — subprocess, Minecraft-user, права и systemd-message helpers.
- `monitoring.py` — метрики хоста, форматирование размеров, процессы, диски и usage сервисов.
- `updates.py` — self-update flow.
- `minecraft.py` — RCON, Java, ping и JVM/resource normalization.
- `loaders.py` — Vanilla/Paper/Purpur/Fabric/Forge/NeoForge loaders.
- `backups.py` — backup, restore, rollback, retention.
- `files.py` — файловый менеджер.
- `mods.py` — scanner и операции с модами.
- `activity.py`, `hashing.py`, `runtime.py` — action log, checksum helpers и transient runtime state.

Следующий безопасный шаг — сгруппировать FastAPI handlers в `routes/` по тем же доменам, оставляя публичные URL и JSON-схемы без изменений.

## Backend

Backend пока сохраняет совместимый `backend/app/main.py`, но ключевые домены уже отделены:

- `schemas.py` — Pydantic-модели и enum-ы публичного API.
- `settings.py` — env-конфиг, константы и JSON settings helpers.
- `auth.py` — пользователи, invite, SQLite init/migration и token auth helpers.
- `agent_client.py` — единая typed-точка для всех запросов к host agent.
- `routes/auth.py` — auth/users handlers без изменения публичных URL.
- `routes/dashboard.py` — dashboard, monitoring, Minecraft versions и agent status/restart handlers.
- `routes/marketplace.py` — marketplace/demo handlers: `/api/mods`, CurseForge search и `/api/files`.
- `routes/servers.py` — server lifecycle, logs, config, RCON, backups, files, mods и loaders handlers.
- `routes/settings.py` — settings/update handlers без изменения публичных URL.

Следующий безопасный шаг — уменьшить dependency fan-out между route factories и helper-функциями, выделив backend service modules для logs, CurseForge/GitHub и demo fallback data.

## Frontend

Frontend начал выделение небольших модулей:

- `dashboardLabels.ts` хранит display labels для состояний и типов серверов.
- `serverDetailTabs.ts` хранит тип и список вкладок страницы сервера.
- `types/` хранит доменные типы, а `types.ts` остаётся barrel export для совместимости старых импортов.
- `pages/server-detail/` содержит вынесенные вкладки страницы сервера: overview, logs, diagnostics, files, mods, backups и settings.

Следующий безопасный шаг — вынести state/actions из `useDashboardStore.ts` в доменные composables, оставив store совместимым facade для текущих страниц.

## Проверки

После каждого архитектурного шага:

```bash
python3 -m py_compile agent/ksylian_agent.py agent/ksylian_agent_app/main.py backend/app/main.py
cd agent && ../backend/.venv/bin/python -m unittest discover -s tests
cd agent && ../backend/.venv/bin/python -c "import ksylian_agent; print(ksylian_agent.app.title)"
cd backend && .venv/bin/python -c "import app.main; print(app.main.app.title)"
cd frontend && npm run build
git diff --check
```
