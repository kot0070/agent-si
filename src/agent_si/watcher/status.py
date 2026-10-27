"""Watcher status: stored facts only, never computed (lane A STEP2).

Owns the REALIZATION_MAP entry ``watcher.status.get`` (:func:`get`).
The payload replays stored facts: integrity from the stored verify, the
journal head from the stored rows, plus a fresh generation stamp.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from agent_si.watcher import integrity as integrity_store
from agent_si.watcher import journal as journal_store
from agent_si.watcher.journal import ERROR_CODES, WatcherError

__all__ = (
    "ERROR_CODES",
    "WatcherError",
    "WatcherStatus",
    "get",
    "reset_state",
)


@dataclass(frozen=True)
class WatcherStatus:
    """Status payload: project, stored integrity, stored journal head."""

    project_id: str
    integrity_ok: bool = False
    journal_head: str = ""
    generated_at: str = ""


def _utcnow() -> str:
    """Current UTC time rendered like the frozen timestamps."""
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def reset_state() -> None:
    """Status keeps no per-run state; present for probe isolation."""
    return None


def get(project_id: str) -> WatcherStatus:
    """Serve stored facts: stored verify plus stored journal head."""
    key = str(project_id)
    try:
        integrity_store.verify(key)
        ok = True
    except WatcherError:
        ok = False
    rows = journal_store.list_events(key)
    head = rows[-1].entry_id if rows else ""
    return WatcherStatus(
        project_id=key,
        integrity_ok=ok,
        journal_head=head,
        generated_at=_utcnow(),
    )
