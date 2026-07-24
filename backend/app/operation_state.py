from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from .schemas import GameServer, ServerOperationProgress, ServerState


server_operation_states: dict[str, ServerState] = {}
server_operation_progress: dict[str, ServerOperationProgress] = {}


@contextmanager
def server_operation_state(
    server_id: str,
    state: ServerState,
    progress: ServerOperationProgress | None = None,
) -> Iterator[None]:
    server_operation_states[server_id] = state
    if progress is not None:
        server_operation_progress[server_id] = progress
    try:
        yield
    finally:
        if server_operation_states.get(server_id) == state:
            server_operation_states.pop(server_id, None)
        server_operation_progress.pop(server_id, None)


def update_server_operation_progress(server_id: str, **updates: object) -> None:
    progress = server_operation_progress.get(server_id)
    if progress is None:
        return
    data = progress.model_dump()
    data.update(updates)
    current = int(data.get("current") or 0)
    total = int(data.get("total") or 0)
    data["percent"] = round((current / total) * 100) if total > 0 else 0
    server_operation_progress[server_id] = ServerOperationProgress(**data)


def apply_server_operation_states(servers: list[GameServer]) -> list[GameServer]:
    if not server_operation_states and not server_operation_progress:
        return servers

    updated: list[GameServer] = []
    for server in servers:
        state = server_operation_states.get(server.id)
        progress = server_operation_progress.get(server.id)
        if state is None and progress is None:
            updated.append(server)
        else:
            update = {}
            if state is not None:
                update["state"] = state
            if progress is not None:
                update["operation"] = progress
            updated.append(server.model_copy(update=update))
    return updated
