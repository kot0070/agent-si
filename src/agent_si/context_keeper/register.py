"""Lane B STEP2 context register: verbatim append-only store (K13 45A/45B).

K08 SPEC 0A user-requirement register (verbatim text per requirement id
plus the PRESERVED audit gate) lives in
:mod:`agent_si.context_keeper.requirements` and is re-exported here.

Frozen shapes are reused from
:mod:`agent_si.context_keeper.interface` (never redefined here):
:data:`CONTEXT_VIOLATION_TYPES` order, ``IncidentSeverity``
LOW/MEDIUM/HIGH/CRITICAL and ``ContextIntegrityRecord``. Standard library
only.
"""

from __future__ import annotations

import dataclasses
import importlib
import json
import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

from agent_si.context_keeper.requirements import (
    RequirementAudit,
    RequirementRegister,
    RequirementRow,
    audit_requirements,
)

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

#: K08 SPEC 0A user-requirement register names (same class objects as
#: agent_si.context_keeper.requirements, never copies).

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

#: Scope the agent_si development model binding applies to
#: (B0B-UNCOVERED_UI_DELTA-33): the product development process only.
#: It is provenance metadata (which model produced a row), never a
#: production default, fallback member or auto-selected model.
DEVELOPMENT_BINDING_SCOPE = "product-development-process"

#: Explicit human choice: the only production use that may name the
#: development binding (a PINNED profile the user picked on purpose).
EXPLICIT_PINNED_USE = "explicit-pinned-choice"

DEV_BINDING_SCOPE_VIOLATION = "DEV_BINDING_SCOPE_VIOLATION"


class DevelopmentBindingScopeError(ValueError):
    """The development binding is used outside its scope."""

    code = DEV_BINDING_SCOPE_VIOLATION


def development_binding():
    """Return the (provider, model) development binding pair.

    Parsed from MODEL_ID so the literal lives in exactly one module.
    """
    provider, _, model = MODEL_ID.partition("/")
    return provider, MODEL_ID


def is_development_binding(provider, model) -> bool:
    """Return True when (provider, model) is the development binding."""
    dev_provider, dev_model = development_binding()
    return str(provider) == dev_provider and str(model) == dev_model


def check_development_binding_use(*, provider, model, use: str):
    """Enforce the development-binding scope (UI_DELTA-33).

    The development binding applies only to the product development
    process (provenance) or an explicit PINNED choice; silent production
    adoption (auto-selection, role defaults, fallback chains,
    production runs) raises DevelopmentBindingScopeError. Ordinary
    models pass every use.
    """
    if not is_development_binding(provider, model):
        return None
    if use in (DEVELOPMENT_BINDING_SCOPE, EXPLICIT_PINNED_USE):
        return None
    raise DevelopmentBindingScopeError(
        "development binding %s/%s applies only to %r "
        "(or an explicit PINNED choice); got use %r "
        "[DEV_BINDING_SCOPE_VIOLATION]"
        % (provider, model, DEVELOPMENT_BINDING_SCOPE, use))

#: Severities that block level start / continuation (K13 45A, SPEC 45A).
def _blocking_severities():
    """Frozen blocking severities, resolved late (HIGH/CRITICAL)."""
    severe = _ck().IncidentSeverity
    return (severe.HIGH, severe.CRITICAL)


#: Register rows file name inside a file-backed store dir.
_REGISTER_ROWS_FILE = "register_rows.json"


def _contract():
    """Return the frozen contract module, importing it late when needed."""
    try:
        return sys.modules[_CK_MODULE]
    except KeyError:
        return importlib.import_module(_CK_MODULE)


def _record_to_dict(record) -> dict:
    """Serialize a frozen integrity row to JSON-safe primitives."""
    return {
        "context_event_id": record.context_event_id,
        "incident_ref": record.incident_ref,
        "project_id": record.project_id,
        "task_id": record.task_id,
        "run_id": record.run_id,
        "actor": record.actor,
        "detected_by": record.detected_by,
        "type": record.type,
        "severity": getattr(record.severity, "value", record.severity),
        "expected_context_refs": list(record.expected_context_refs),
        "actual_context_refs": list(record.actual_context_refs),
        "missing_refs": list(record.missing_refs),
        "conflicting_refs": list(record.conflicting_refs),
        "contract_hash": record.contract_hash,
        "detected_at": record.detected_at,
        "impact": record.impact,
        "resolution": record.resolution,
        "resolved_at": record.resolved_at,
        "evidence_refs": list(record.evidence_refs),
    }


def _record_from_dict(payload):
    """Rebuild the frozen integrity row (same class object, never a copy)."""
    contract = _contract()
    return contract.ContextIntegrityRecord(
        context_event_id=payload["context_event_id"],
        incident_ref=payload["incident_ref"],
        project_id=payload["project_id"],
        task_id=payload["task_id"],
        run_id=payload["run_id"],
        actor=payload["actor"],
        detected_by=payload["detected_by"],
        type=payload["type"],
        severity=contract.IncidentSeverity(payload["severity"]),
        expected_context_refs=tuple(payload["expected_context_refs"]),
        actual_context_refs=tuple(payload["actual_context_refs"]),
        missing_refs=tuple(payload["missing_refs"]),
        conflicting_refs=tuple(payload["conflicting_refs"]),
        contract_hash=payload["contract_hash"],
        detected_at=payload["detected_at"],
        impact=payload["impact"],
        resolution=payload["resolution"],
        resolved_at=payload["resolved_at"],
        evidence_refs=tuple(payload["evidence_refs"]),
    )


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

    def __init__(self, store_dir=None) -> None:
        self._by_id: Dict[str, ck.ContextIntegrityRecord] = {}
        self._order: List[str] = []
        self._store_dir = store_dir
        if store_dir is not None:
            os.makedirs(store_dir, exist_ok=True)
            self._load()

    def _path(self, name):
        return os.path.join(str(self._store_dir), name)

    def _write_json(self, name, payload):
        if self._store_dir is None:
            return
        tmp = self._path(name + ".tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, self._path(name))

    def _load(self):
        try:
            with open(
                self._path(_REGISTER_ROWS_FILE), encoding="utf-8"
            ) as fh:
                rows = json.load(fh)
        except FileNotFoundError:
            return
        for payload in rows:
            record = _record_from_dict(payload)
            event_id = record.context_event_id
            if event_id not in self._by_id:
                self._by_id[event_id] = record
                self._order.append(event_id)

    def _sync(self):
        if self._store_dir is not None:
            self._load()

    def _persist(self):
        self._write_json(
            _REGISTER_ROWS_FILE,
            [
                _record_to_dict(self._by_id[event_id])
                for event_id in self._order
            ],
        )

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
        self._persist()
        return record

    def read(self, context_event_id: str) -> Optional[ck.ContextIntegrityRecord]:
        """Return the stored row for context_event_id, else None."""
        row = self._by_id.get(context_event_id)
        if row is None and self._store_dir is not None:
            self._sync()
            row = self._by_id.get(context_event_id)
        return row

    def list_unresolved(self, project_id: str) -> List[ck.ContextIntegrityRecord]:
        """Return rows of project_id whose resolved_at is None."""
        self._sync()
        return [
            self._by_id[event_id]
            for event_id in self._order
            if self._by_id[event_id].project_id == project_id
            and self._by_id[event_id].resolved_at is None
        ]

    def list_all(self, project_id: str) -> List[ck.ContextIntegrityRecord]:
        """Return every row of project_id (resolved rows stay in history)."""
        self._sync()
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
        self._persist()
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
