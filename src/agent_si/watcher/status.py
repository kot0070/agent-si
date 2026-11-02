"""Watcher status: stored facts only, never computed (lane A STEP2).

Owns the REALIZATION_MAP entry ``watcher.status.get`` (:func:`get`).
The payload replays stored facts: integrity from the stored verify, the
journal head from the stored rows, plus the stored generation stamp.
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
    """Status payload: project, stored integrity, stored journal head.

    Plus the watcher model truth: the exact model name that answered
    the latest abnormal WATCH_DECISION row (a stored fact), or
    "Rules only" when no model answered yet.
    """

    project_id: str
    integrity_ok: bool = False
    journal_head: str = ""
    generated_at: str = ""
    watcher_model: str = "Rules only"


def _utcnow() -> str:
    """Current UTC time rendered like the frozen timestamps."""
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _watcher_model(project_id: str) -> str:
    """Exact model that answered the latest abnormal decision, else Rules.

    Reads stored WATCH_DECISION rows only: the newest row carrying both
    a ``model=`` and an ``action=`` marker names the model that
    answered; default-action and OFF-marker rows name no model.
    """
    try:
        rows = journal_store.stored_rows(str(project_id), "WATCH_DECISION")
    except Exception:
        return "Rules only"
    for row in reversed(list(rows)):
        try:
            summary = str(row.summary)
        except Exception:
            continue
        if "model=" not in summary or "action=" not in summary:
            continue
        try:
            name = summary.split("model=", 1)[1].split()[0].strip()
        except (IndexError, AttributeError):
            continue
        if name:
            return name
    return "Rules only"


def get(project_id: str) -> WatcherStatus:
    """Serve stored facts: stored verify plus stored journal head."""
    key = str(project_id)
    try:
        integrity_store.verify(key)
        ok = True
    except WatcherError:
        ok = False
    rows = journal_store.list_events(key)
    # K08F2: generated_at is the time of the stored facts served (the
    # stored head stamp; "" when nothing is stored), so two reads with
    # no state change serve equal payloads.
    if rows:
        head = rows[-1].entry_id
        generated_at = rows[-1].timestamp
    else:
        head = ""
        generated_at = ""
    return WatcherStatus(
        project_id=key,
        integrity_ok=ok,
        journal_head=head,
        generated_at=generated_at,
        watcher_model=_watcher_model(key),
    )


def reset_state() -> None:
    """Status keeps no per-run state; present for probe isolation."""
    return None
