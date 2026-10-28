"""Incident and context-integrity records (Manifest sections 45A, 46).

IncidentRecord rows index context violations only: the authoritative truth
stays in ContextIntegrityRecord, and an index row carries the incident id
without duplicating the integrity record. Severity is the manifest-shared
IncidentSeverity; incident and violation type names are the frozen sets
below. Committed records are frozen dataclasses; this module mutates
nothing and invents no severity, type, or status names.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, FrozenSet, Optional, Tuple

try:
    from iface.frozen_manifest import manifest
except ImportError:  # alternate layout: the iface/ directory itself on sys.path
    from frozen_manifest import manifest

IncidentSeverity = manifest.IncidentSeverity
"""Shared severity (Manifest section 46; also used by section 45A records)."""

INCIDENT_TYPES: FrozenSet[str] = frozenset(
    {
        "workspace_violation",
        "provider_failure",
        "model_failure",
        "scheduler_failure",
        "test_failure",
        "audit_failure",
        "scope_deviation",
        "security_issue",
        "retry_exhausted",
        "fallback_exhausted",
        "unsafe_action",
        "data_corruption_risk",
        "capability_mismatch",
    }
)
"""Frozen incident types (Manifest section 46)."""

CONTEXT_VIOLATION_TYPES: FrozenSet[str] = frozenset(
    {
        "CONTEXT_MISSING",
        "CONTEXT_STALE",
        "CONTEXT_CONFLICT",
        "CONTEXT_TRUNCATED",
        "CONTEXT_UNAUTHORIZED_EXPANSION",
        "CONTEXT_WRONG_TASK",
        "CONTEXT_WRONG_CONTRACT_VERSION",
        "CONTEXT_ARTIFACT_UNAVAILABLE",
        "CONTEXT_RECOVERY_FAILED",
        "CONTEXT_SUMMARY_DRIFT",
    }
)
"""Frozen context-violation types (Manifest section 45A)."""


class UnknownIncidentTypeError(ValueError):
    """IncidentRecord.type is not one of the frozen section 46 types."""


class UnknownContextViolationTypeError(ValueError):
    """ContextIntegrityRecord.type is not one of the frozen section 45A types."""


class IncidentLinkError(ValueError):
    """Broken or rewritten incident/index linkage (section 45A index rule)."""


def _as_tuple(value: Any) -> Tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    return tuple(value)


def _coerce_severity(value: Any) -> manifest.IncidentSeverity:
    if isinstance(value, manifest.IncidentSeverity):
        return value
    return manifest.IncidentSeverity(str(value))


@dataclass(frozen=True)
class IncidentRecord:
    """Index-only incident row (Manifest section 46).

    Field order follows the manifest: incident_id, project_id, timestamp,
    task_id, run_id, actor, detected_by, severity, type, description,
    root_cause, impact, action, regression_test, status. The row indexes a
    context violation; the truth lives in ContextIntegrityRecord.
    """

    incident_id: str = ""
    project_id: str = ""
    timestamp: str = ""
    task_id: str = ""
    run_id: Optional[str] = None
    actor: str = ""
    detected_by: str = ""
    severity: manifest.IncidentSeverity = manifest.IncidentSeverity.MEDIUM
    type: str = ""
    description: str = ""
    root_cause: str = ""
    impact: str = ""
    action: str = ""
    regression_test: str = ""
    status: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "severity", _coerce_severity(self.severity))
        if self.type not in INCIDENT_TYPES:
            raise UnknownIncidentTypeError(
                "unknown incident type %r; frozen types: %s"
                % (self.type, sorted(INCIDENT_TYPES))
            )


@dataclass(frozen=True)
class ContextIntegrityRecord:
    """Authoritative context-violation truth (Manifest section 45A).

    Incident rows index this record only (via incident_ref); refs, evidence,
    and resolution live here and are never duplicated into the index row.
    """

    context_event_id: str = ""
    incident_ref: Optional[str] = None
    project_id: str = ""
    task_id: str = ""
    run_id: Optional[str] = None
    actor: str = ""
    detected_by: str = ""
    type: str = ""
    severity: manifest.IncidentSeverity = manifest.IncidentSeverity.MEDIUM
    expected_context_refs: Tuple[str, ...] = ()
    actual_context_refs: Tuple[str, ...] = ()
    missing_refs: Tuple[str, ...] = ()
    conflicting_refs: Tuple[str, ...] = ()
    contract_hash: str = ""
    detected_at: str = ""
    impact: str = ""
    resolution: str = ""
    resolved_at: Optional[str] = None
    evidence_refs: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "severity", _coerce_severity(self.severity))
        object.__setattr__(
            self, "expected_context_refs", _as_tuple(self.expected_context_refs)
        )
        object.__setattr__(
            self, "actual_context_refs", _as_tuple(self.actual_context_refs)
        )
        object.__setattr__(self, "missing_refs", _as_tuple(self.missing_refs))
        object.__setattr__(
            self, "conflicting_refs", _as_tuple(self.conflicting_refs)
        )
        object.__setattr__(self, "evidence_refs", _as_tuple(self.evidence_refs))
        if self.type not in CONTEXT_VIOLATION_TYPES:
            raise UnknownContextViolationTypeError(
                "unknown context-violation type %r; frozen types: %s"
                % (self.type, sorted(CONTEXT_VIOLATION_TYPES))
            )


def index_context_violation(
    truth: ContextIntegrityRecord,
    *,
    incident_id: str,
    type: str,
    timestamp: str = "",
    description: str = "",
    root_cause: str = "",
    impact: str = "",
    action: str = "",
    regression_test: str = "",
    status: str = "",
) -> IncidentRecord:
    """Build the index-only IncidentRecord for a context violation.

    The index row carries the incident id plus routing fields (project, task,
    run, actor, severity); refs, evidence, and resolution stay exclusively
    in *truth* and are never copied over.
    """
    if not incident_id:
        raise IncidentLinkError("index row requires a non-empty incident_id")
    return IncidentRecord(
        incident_id=incident_id,
        project_id=truth.project_id,
        timestamp=timestamp,
        task_id=truth.task_id,
        run_id=truth.run_id,
        actor=truth.actor,
        detected_by=truth.detected_by,
        severity=truth.severity,
        type=type,
        description=description,
        root_cause=root_cause,
        impact=impact,
        action=action,
        regression_test=regression_test,
        status=status,
    )


def link_incident(
    truth: ContextIntegrityRecord, incident_id: str
) -> ContextIntegrityRecord:
    """Return a NEW record carrying *incident_id* as its incident_ref.

    The original is untouched; an already-linked record is never re-linked
    to a different incident id.
    """
    if not incident_id:
        raise IncidentLinkError("incident_ref requires a non-empty incident_id")
    if truth.incident_ref is not None and truth.incident_ref != incident_id:
        raise IncidentLinkError(
            "ContextIntegrityRecord %r already indexed by %r"
            % (truth.context_event_id, truth.incident_ref)
        )
    if truth.incident_ref == incident_id:
        return truth
    return replace(truth, incident_ref=incident_id)


def check_index_linkage(index: IncidentRecord, truth: ContextIntegrityRecord) -> bool:
    """Return True iff *index* is the index row for *truth*.

    Raises IncidentLinkError when the linkage is missing or mismatched:
    mirrored rows carry the incident id, and the truth record holds it in
    incident_ref.
    """
    if not index.incident_id or truth.incident_ref != index.incident_id:
        raise IncidentLinkError(
            "index row %r does not index ContextIntegrityRecord %r"
            % (index.incident_id, truth.context_event_id)
        )
    return True


__all__ = [
    "IncidentSeverity",
    "INCIDENT_TYPES",
    "CONTEXT_VIOLATION_TYPES",
    "UnknownIncidentTypeError",
    "UnknownContextViolationTypeError",
    "IncidentLinkError",
    "IncidentRecord",
    "ContextIntegrityRecord",
    "index_context_violation",
    "link_incident",
    "check_index_linkage",
]
