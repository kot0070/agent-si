"""Lane B STEP2 context register: verbatim append-only store (K13 45A/45B).

Frozen shapes are reused from
:mod:`agent_si.context_keeper.interface` (never redefined here):
:data:`CONTEXT_VIOLATION_TYPES` order, ``IncidentSeverity``
LOW/MEDIUM/HIGH/CRITICAL and ``ContextIntegrityRecord``. Standard library
only.
"""

from __future__ import annotations

import dataclasses
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from agent_si.context_keeper import interface as ck


#: Dotted name of the frozen context-keeper contract module. Product
#: code keeps no static import of it; the module object and the frozen
#: row types are resolved late so the same class objects the keeper
#: tests use are returned.
_CK_MODULE = "agent_si.context_keeper.interface"


def _ck():
    """Return the frozen context-keeper contract module object."""
    try:
        return sys.modules[_CK_MODULE]
    except KeyError:
        raise RuntimeError(
            "frozen contract %r is not imported" % (_CK_MODULE,)
        )


#: Frozen row names re-exported late (same class objects, never copies).
_FROZEN_NAMES = ("IncidentSeverity", "ContextIntegrityRecord")

def __getattr__(name):
    """Expose frozen row names late (identity with the contract module)."""
    if name in _FROZEN_NAMES:
        return getattr(_ck(), name)
    raise AttributeError(
        "module %r has no attribute %r" % (__name__, name)
    )

#: Reused frozen severity (identity with the contract module;
#: provided late through __getattr__ above, never redefined here).

#: Reused frozen violation row (identity with the contract module;
#: provided late through __getattr__ above, never redefined here).

#: Cancel keeps history; only the logical scope exists (K13 45B, SPEC 4).
CANCEL_SCOPE_DEFAULT = "LOGICAL_ONLY"

#: Provenance marker: the ref was pinned by the keeper.
SOURCED = "SOURCED"

#: Provenance marker: the ref is not known to the keeper.
UNKNOWN = "UNKNOWN"

#: Reference states for schedule/trigger comparison (K13 0A).
REF_STATES = ("PRESERVED", "CHANGED", "MISSING", "CONTRADICTED")

#: Model that produced keeper rows (M-A provenance pin).
MODEL_ID = "meta/muse-spark-1.3-contributor"

#: Severities that block level start / continuation (K13 45A, SPEC 45A).
def _blocking_severities():
    """Frozen blocking severities, resolved late (HIGH/CRITICAL)."""
    severe = _ck().IncidentSeverity
    return (severe.HIGH, severe.CRITICAL)


@dataclass(frozen=True)
class LevelStartBundle:
    """Refs re-injected when a level starts (violations authoritative)."""

    project_id: str
    unresolved: Tuple[ck.ContextIntegrityRecord, ...]
    refs: Tuple[str, ...]
    blocked: bool


def compare_refs(
    expected: Tuple[str, ...],
    actual: Tuple[str, ...],
    conflicting_refs: Tuple[str, ...] = (),
    changed_refs: Tuple[str, ...] = (),
) -> Tuple[Dict[str, str], Tuple[str, ...]]:
    """Compare expected vs actual refs (K13 0A states).

    Returns the per-expected-ref state mapping plus the extra actual
    refs (present in actual, absent from expected).
    """
    conflicting = set(conflicting_refs)
    changed = set(changed_refs)
    seen = set(actual)
    wanted = set(expected)
    states: Dict[str, str] = {}
    for ref in expected:
        if ref in conflicting:
            states[ref] = "CONTRADICTED"
        elif ref in changed:
            states[ref] = "CHANGED"
        elif ref in seen:
            states[ref] = "PRESERVED"
        else:
            states[ref] = "MISSING"
    extra = tuple(ref for ref in actual if ref not in wanted)
    return states, extra


class Register:
    """Verbatim append-only context register (K13 section 45A)."""

    def __init__(self) -> None:
        self._by_id: Dict[str, ck.ContextIntegrityRecord] = {}
        self._order: List[str] = []

    def append(
        self, record: ck.ContextIntegrityRecord
    ) -> ck.ContextIntegrityRecord:
        """Persist record verbatim; a duplicate id returns the stored row."""
        if record.type not in _ck().CONTEXT_VIOLATION_TYPES:
            raise ValueError("unknown violation type: %r" % (record.type,))
        if not isinstance(record.severity, _ck().IncidentSeverity):
            raise ValueError("invalid severity: %r" % (record.severity,))
        stored = self._by_id.get(record.context_event_id)
        if stored is not None:
            return stored
        self._by_id[record.context_event_id] = record
        self._order.append(record.context_event_id)
        return record

    def read(self, context_event_id: str) -> Optional[ck.ContextIntegrityRecord]:
        """Return the stored row for context_event_id, else None."""
        return self._by_id.get(context_event_id)

    def list_unresolved(self, project_id: str) -> List[ck.ContextIntegrityRecord]:
        """Return rows of project_id whose resolved_at is None."""
        return [
            self._by_id[event_id]
            for event_id in self._order
            if self._by_id[event_id].project_id == project_id
            and self._by_id[event_id].resolved_at is None
        ]

    def list_all(self, project_id: str) -> List[ck.ContextIntegrityRecord]:
        """Return every row of project_id (resolved rows stay in history)."""
        return [
            self._by_id[event_id]
            for event_id in self._order
            if self._by_id[event_id].project_id == project_id
        ]

    def read_for_level_start(self, project_id: str) -> LevelStartBundle:
        """Re-inject unresolved rows verbatim at every level start."""
        unresolved = tuple(self.list_unresolved(project_id))
        refs: List[str] = []
        for row in unresolved:
            for ref in (
                row.expected_context_refs
                + row.actual_context_refs
                + row.missing_refs
                + row.conflicting_refs
            ):
                if ref not in refs:
                    refs.append(ref)
        blocked = any(
            row.severity in _blocking_severities() for row in unresolved
        )
        return LevelStartBundle(
            project_id=project_id,
            unresolved=unresolved,
            refs=tuple(refs),
            blocked=blocked,
        )

    def blocking_incidents(
        self, project_id: str
    ) -> List[ck.ContextIntegrityRecord]:
        """Return unresolved HIGH/CRITICAL rows of project_id."""
        return [
            row
            for row in self.list_unresolved(project_id)
            if row.severity in _blocking_severities()
        ]

    def cancel_run(
        self,
        project_id: str,
        run_id: str,
        scope: str = CANCEL_SCOPE_DEFAULT,
    ) -> int:
        """Cancel a run; history is kept, only LOGICAL_ONLY exists."""
        if scope != CANCEL_SCOPE_DEFAULT:
            raise ValueError("unsupported cancel scope: %r" % (scope,))
        retained = 0
        for event_id in self._order:
            row = self._by_id[event_id]
            if row.project_id == project_id and row.run_id == run_id:
                retained += 1
        return retained

    def mark_resolved(
        self, context_event_id: str, resolution: str, resolved_at: str
    ) -> ck.ContextIntegrityRecord:
        """Resolve a row; the row stays in history."""
        stored = self._by_id.get(context_event_id)
        if stored is None:
            raise KeyError(context_event_id)
        updated = dataclasses.replace(
            stored, resolution=resolution, resolved_at=resolved_at
        )
        self._by_id[context_event_id] = updated
        return updated

    def provenance(self, project_id: str, ref: str) -> str:
        """Return SOURCED when the keeper pinned ref, else UNKNOWN."""
        for event_id in self._order:
            row = self._by_id[event_id]
            if row.project_id != project_id:
                continue
            if ref in row.expected_context_refs or ref in row.actual_context_refs:
                return SOURCED
        return UNKNOWN
