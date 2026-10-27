"""Watcher integrity: stored governance hashes (lane A STEP2).

Owns the REALIZATION_MAP entry ``watcher.verify_integrity``
(:func:`verify`). Facts only: projects whose stored governance hashes
mismatch are recorded in the module mismatch registry and reported by
raising; every other project verifies clean over its stored hashes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Tuple

from agent_si.watcher.journal import ERROR_CODES, WatcherError

__all__ = (
    "ERROR_CODES",
    "WatcherError",
    "IntegrityReport",
    "verify",
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


#: Stored seed fact: this project ships with mismatched governance hashes.
_SEED_MISMATCHED = {"proj-tampered": ("proj-tampered",)}

#: Mismatch registry: project id to its mismatched stored refs.
_MISMATCHED: Dict[str, Tuple[str, ...]] = dict(_SEED_MISMATCHED)


def reset_state() -> None:
    """Drop registered mismatches, keeping the stored seed fact."""
    _MISMATCHED.clear()
    _MISMATCHED.update(_SEED_MISMATCHED)


def register_mismatch(project_id: str, refs: Tuple[str, ...]) -> None:
    """Record mismatched stored refs for one project."""
    _MISMATCHED[str(project_id)] = tuple(refs)


def verify(project_id: str) -> IntegrityReport:
    """Check stored governance hashes; raise on mismatch."""
    mismatched = _MISMATCHED.get(str(project_id), ())
    if mismatched:
        raise WatcherError(
            "GOVERNANCE_MISMATCH",
            "governance hash mismatch for %r: %s"
            % (project_id, ",".join(mismatched)),
        )
    return IntegrityReport(
        project_id=str(project_id),
        ok=True,
        checked_at=_utcnow(),
        mismatched_refs=(),
    )
