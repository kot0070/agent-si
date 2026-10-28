"""Watcher integrity: hash-pinned stored journal rows.

Owns the REALIZATION_MAP entry ``watcher.verify_integrity``
(:func:`verify`). Pins are sha256 digests over the project's stored
journal rows, sealed per project with :func:`seal`; ``verify`` recomputes
the digest over the sealed prefix and raises GOVERNANCE_MISMATCH naming
the mismatched refs on divergence. Rows appended after the seal keep
verifying clean, since the log is append-only. ``register_mismatch``
stays as a compat shim that forces one project to mismatch until reset.
No entries are pre-seeded; reset_state clears every pin and force.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from agent_si.watcher import journal as journal_store
from agent_si.watcher.journal import ERROR_CODES, WatcherError

__all__ = (
    "ERROR_CODES",
    "WatcherError",
    "IntegrityReport",
    "verify",
    "seal",
    "register_mismatch",
    "reset_state",
)


@dataclass(frozen=True)
class IntegrityReport:
    """Verify outcome over stored hashes."""

    project_id: str
    ok: bool
    checked_at: str = ""
    mismatched_refs: Tuple[str, ...] = ()


def _utcnow() -> str:
    """Current UTC time rendered like the frozen timestamps."""
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


#: Sealed pins per project: row count, aggregate digest, sealed rows.
_PINNED: Dict[str, dict] = {}

#: Forced mismatches per project (compat shim only).
_FORCED: Dict[str, Tuple[str, ...]] = {}


def _canon_row(row) -> str:
    """Canonical pinned form of one stored row."""
    return "|".join((
        str(row.kind),
        str(row.source),
        str(row.summary),
        ",".join(str(ref) for ref in row.refs),
        str(row.entry_id),
        str(row.timestamp),
        str(row.digest),
    ))


def _digest_rows(canon_rows: List[str]) -> str:
    """sha256 pin over canonical stored rows."""
    return hashlib.sha256("\n".join(canon_rows).encode("utf-8")).hexdigest()


def reset_state() -> None:
    """Drop every pin and every forced mismatch."""
    _PINNED.clear()
    _FORCED.clear()


def register_mismatch(project_id: str, refs: Tuple[str, ...]) -> None:
    """Compat shim: force one project to mismatch until reset."""
    _FORCED[str(project_id)] = tuple(refs)


def seal(project_id: str) -> IntegrityReport:
    """Pin the project's current stored rows; return the clean report."""
    key = str(project_id)
    rows = journal_store.stored_rows(key)
    canon = [_canon_row(row) for row in rows]
    _FORCED.pop(key, None)
    _PINNED[key] = {
        "count": len(canon),
        "digest": _digest_rows(canon),
        "rows": tuple(
            (text, tuple(row.refs)) for text, row in zip(canon, rows)
        ),
    }
    return IntegrityReport(
        project_id=key,
        ok=True,
        checked_at=_utcnow(),
        mismatched_refs=(),
    )


def verify(project_id: str) -> IntegrityReport:
    """Check stored rows against the pin; raise on divergence."""
    key = str(project_id)
    forced = _FORCED.get(key, ())
    if forced:
        raise WatcherError(
            "GOVERNANCE_MISMATCH",
            "governance hash mismatch for %r: %s"
            % (key, ",".join(forced)),
        )
    pin = _PINNED.get(key)
    if pin is None:
        return IntegrityReport(
            project_id=key,
            ok=True,
            checked_at=_utcnow(),
            mismatched_refs=(),
        )
    rows = journal_store.stored_rows(key)
    canon = [_canon_row(row) for row in rows]
    sealed = pin["rows"]
    if len(canon) < len(sealed) or _digest_rows(canon[:len(sealed)]) != pin["digest"]:
        mismatched: List[str] = []
        for index, (want, refs) in enumerate(sealed):
            if index >= len(canon) or canon[index] != want:
                mismatched.extend(str(ref) for ref in refs)
        detail = ",".join(dict.fromkeys(mismatched)) or "sealed rows changed"
        raise WatcherError(
            "GOVERNANCE_MISMATCH",
            "governance hash mismatch for %r: %s" % (key, detail),
        )
    return IntegrityReport(
        project_id=key,
        ok=True,
        checked_at=_utcnow(),
        mismatched_refs=(),
    )
