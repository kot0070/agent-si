"""Watcher journal: stored event rows plus append receipts (lane A STEP2).

Owns REALIZATION_MAP entries ``journal.append_event`` (:func:`append_event`)
and ``journal.list_events`` (:func:`list_events`). Rows are stored facts:
append validates the kind, assigns a unique entry id, stamps real UTC time,
digests the row with sha256, then stores the row. Reads serve stored rows
only, never computed values. The lane error (:class:`WatcherError`) plus
the error-code table are defined once here and reused by sibling import.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Tuple

__all__ = (
    "WatcherError",
    "ERROR_CODES",
    "KINDS",
    "JournalEntry",
    "append_event",
    "list_events",
    "reset_state",
)


class WatcherError(Exception):
    """Lane error: code names one entry of ERROR_CODES."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


#: Lane error-code names; each is raised in its own condition.
ERROR_CODES = (
    "RULE_NOT_FOUND",
    "GOVERNANCE_MISMATCH",
    "JOURNAL_KIND_UNKNOWN",
    "STOP_REASON_MISSING",
    "PRESET_NOT_FOUND",
    "SESSION_TOKEN_MISSING",
    "SESSION_TOKEN_INVALID",
)

#: Stored journal event kinds carried on append.
KINDS = (
    "WATCH_DECISION",
    "TAMPER_ATTEMPT",
    "GUARD_BLOCK",
    "STOP_ALL",
    "SERVICE_STATE",
    "AUTOMATION_RUN",
    "CONTEXT_CHECKPOINT",
    "CONTEXT_RECOVERY",
    "OUTAGE_SIGNAL",
)


@dataclass(frozen=True)
class JournalEntry:
    """Append receipt: unique id, UTC stamp, row digest."""

    entry_id: str
    timestamp: str
    hash: str = ""


def _utcnow() -> str:
    """Current UTC time rendered like the frozen timestamps."""
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


#: Stored rows per project: each row keeps kind, receipt, source,
#: summary and refs. Receipts are served from these rows only.
_ROWS: Dict[str, List[dict]] = {}

#: Entry-id sequence; restarted by reset_state for probe isolation.
_SEQ = 0

#: Digest nonce; never reset so digests stay unique across resets.
_NONCE = 0


def reset_state() -> None:
    """Clear stored rows and restart entry ids."""
    global _SEQ
    _ROWS.clear()
    _SEQ = 0


def append_event(project_id: str, source: str, kind: str,
                 summary: str, refs: Tuple[str, ...]) -> JournalEntry:
    """Validate the kind, store the row, return the receipt."""
    if kind not in KINDS:
        raise WatcherError(
            "JOURNAL_KIND_UNKNOWN", "unknown journal kind %r" % (kind,)
        )
    global _SEQ, _NONCE
    _SEQ += 1
    _NONCE += 1
    stamped = _utcnow()
    entry_id = "evt-%04d" % _SEQ
    digest = hashlib.sha256(
        "|".join((
            str(project_id),
            str(source),
            str(kind),
            str(summary),
            ",".join(str(ref) for ref in refs),
            entry_id,
            stamped,
            str(_NONCE),
        )).encode("utf-8")
    ).hexdigest()
    entry = JournalEntry(entry_id=entry_id, timestamp=stamped, hash=digest)
    _ROWS.setdefault(str(project_id), []).append(
        {
            "kind": kind,
            "entry": entry,
            "source": source,
            "summary": summary,
            "refs": tuple(refs),
        }
    )
    return entry


def list_events(project_id: str, kind: str = "") -> Tuple[JournalEntry, ...]:
    """Serve stored rows only; empty kind reads all kinds."""
    rows = _ROWS.get(str(project_id), [])
    if kind:
        if kind not in KINDS:
            raise WatcherError(
                "JOURNAL_KIND_UNKNOWN", "unknown journal kind %r" % (kind,)
            )
        return tuple(row["entry"] for row in rows if row["kind"] == kind)
    return tuple(row["entry"] for row in rows)
