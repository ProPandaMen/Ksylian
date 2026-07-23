# Архитектура Ksylian

Обновлено: 2026-07-23

## Agent

`agent/ksylian_agent.py` остаётся совместимой точкой входа для systemd:

```python
from ksylian_agent_app.main import app
```

Основная реализация живёт в пакете `agent/ksylian_agent_app/`. Часть доменов уже физически вынесена из бывшего монолита, остальные имеют стабильные import-точки для следующего среза:

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

Следующий безопасный шаг — физически перенести `files.py`, затем `mods.py`, затем `backups.py`, оставляя routes и публичные JSON-схемы без изменений.

## Backend

Backend пока сохраняет совместимый `backend/app/main.py`, но низкоуровневый HTTP-доступ к agent вынесен в `backend/app/agent_client.py`.

Следующие границы для декомпозиции:

- `schemas.py` для Pydantic-моделей.
- `auth.py` и `db.py` для пользователей, invite и SQLite.
- `settings.py` для настроек и секретов.
- `routes/` для групп API.

## Frontend

Frontend начал выделение небольших модулей:

- `dashboardLabels.ts` хранит display labels для состояний и типов серверов.
- `serverDetailTabs.ts` хранит тип и список вкладок страницы сервера.

Следующий безопасный шаг — вынести вкладки `ServerDetailPage.vue` в компоненты по одной: logs, files, mods, backups, diagnostics, settings.

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
