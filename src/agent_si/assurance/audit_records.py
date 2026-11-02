"""Audit records, verdicts, failure classes.

Frozen sources: RECORDS/day0/K13_MANIFEST.md §17B (AuditResult and
AuditHandlingDisposition, immutable result, handling separate),
§17C (VerificationFailureClass, FailureSeverity), §21C
(VerificationRecord shape mirrored here; missing evidence ref fails the
criterion), §26A (AuditRequirement, minimum independence level),
§45A (context-integrity result gates PASS), §14 (ExecutionRunCreationReason
AUDIT_REWORK / VERIFICATION_REWORK correction runs), §16
(ReworkCounterRecord, AUDIT_REWORK counter kind); SPEC 18
(AUDIT_INDEPENDENCE: execution record carries the auditor's actual runtime
binding); SPEC 20B (contributor sets derived from work records);
the requirement-verdict spec (requirement verdicts
PRESERVED / CHANGED / MISSING / CONTRADICTED; non-PRESERVED blocks PASS).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Protocol, Tuple


class AuditResult(str, Enum):
    """Canonical audit verdicts; immutable evidence (K13 §17B)."""

    PASS = "PASS"
    REWORK = "REWORK"
    BLOCKED = "BLOCKED"
    ESCALATE = "ESCALATE"
    FAIL = "FAIL"


class AuditHandlingDisposition(str, Enum):
    """Separate runtime decision; never rewrites the result (K13 §17B)."""

    COMPLETE = "COMPLETE"
    REWORK = "REWORK"
    BLOCK = "BLOCK"
    ESCALATE = "ESCALATE"
    FAIL = "FAIL"


class RequirementVerdict(str, Enum):
    """Per-requirement verdict; anything not PRESERVED blocks PASS (SPEC 0A)."""

    PRESERVED = "PRESERVED"
    CHANGED = "CHANGED"
    MISSING = "MISSING"
    CONTRADICTED = "CONTRADICTED"


class VerificationFailureClass(str, Enum):
    """One deterministic path per failure class (K13 §17C)."""

    VERIFICATION_INFRA_FAILURE = "VERIFICATION_INFRA_FAILURE"
    OUTPUT_FORMAT_FAILURE = "OUTPUT_FORMAT_FAILURE"
    PROVIDER_OR_MODEL_CAPABILITY_FAILURE = (
        "PROVIDER_OR_MODEL_CAPABILITY_FAILURE"
    )
    IMPLEMENTATION_AC_DEFECT = "IMPLEMENTATION_AC_DEFECT"
    SECURITY_OR_POLICY_FAILURE = "SECURITY_OR_POLICY_FAILURE"
    UNKNOWN_FAILURE = "UNKNOWN_FAILURE"


class FailureSeverity(str, Enum):
    """Shared severity scale (K13 §17C, §45A)."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class CriterionVerificationResult(str, Enum):
    """Per-criterion outcome; missing evidence ref fails it (K13 §21C)."""

    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class IndependenceLevel(str, Enum):
    """Auditor independence levels; L0 is prohibited (SPEC 18, K13 §26A)."""

    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"


class AuditRequirement(str, Enum):
    """Required audit level; NONE is prohibited (K13 §26A)."""

    REQUIRED_L2 = "REQUIRED_L2"
    REQUIRED_L3 = "REQUIRED_L3"
    REQUIRED_L4_MANUAL = "REQUIRED_L4_MANUAL"


#: Context-integrity value that alone permits PASS (K13 §45A).
CONTEXT_INTEGRITY_PASS = "PASS"

#: Exhausted audit budget preserves REWORK and escalates handling (K13 §17B).
REWORK_BUDGET_EXHAUSTED = "REWORK_BUDGET_EXHAUSTED"

#: Context-integrity values; anything else is rejected, never stored (R13).
CONTEXT_INTEGRITY_VALUES = ("PASS", "REWORK", "BLOCKED")

#: Status spellings that count a plain context record as resolved.
_RESOLVED_STATUS_VALUES = frozenset(
    {"resolved", "closed", "fixed", "done", "complete", "completed"}
)

#: Status spellings that never count as resolved.
_UNRESOLVED_STATUS_VALUES = frozenset(
    {"open", "unresolved", "pending", "false", "no", "0", ""}
)


def _as_record_tuple(context_records):
    """Normalize a plain record list; a bare record becomes one item."""
    if context_records is None:
        return ()
    if isinstance(context_records, dict):
        return (context_records,)
    if isinstance(context_records, (list, tuple)):
        return tuple(context_records)
    return (context_records,)


def _plain_field(item, names):
    """Read one field from a plain record (mapping or attribute object)."""
    if isinstance(item, dict):
        for name in names:
            if name in item:
                return item[name]
        return None
    for name in names:
        if hasattr(item, name):
            return getattr(item, name)
    getter = getattr(item, "get", None)
    if callable(getter):
        for name in names:
            try:
                value = getter(name)
            except Exception:
                continue
            if value is not None:
                return value
    return None


def _violation_severity(item) -> str:
    """Severity spelling of a plain record, upper-cased ("" when absent)."""
    value = _plain_field(item, ("severity",))
    if value is None:
        return ""
    return str(value).strip().upper()


def _violation_resolved(item) -> bool:
    """True only when the plain record is positively resolved.

    A record with neither a ``resolved`` marker nor a ``status`` counts as
    unresolved (fail-closed): only a positive resolution clears the block.
    """
    marker = _plain_field(item, ("resolved",))
    if marker is not None:
        if isinstance(marker, bool):
            return marker
        text = str(marker).strip().lower()
        if text in _UNRESOLVED_STATUS_VALUES:
            return False
        return True
    status = _plain_field(item, ("status",))
    if status is None:
        return False
    if isinstance(status, bool):
        return status
    return str(status).strip().lower() in _RESOLVED_STATUS_VALUES


def _violation_scope(item):
    """Scope of a plain record, or None when it carries no scope."""
    value = _plain_field(item, ("scope_id", "audit_scope_id", "scope"))
    if value is None:
        return None
    return str(value)


def _violation_in_scope(item, scope_id) -> bool:
    """True when the record belongs to the audited scope.

    Records without scope information count as in scope (fail-closed).
    """
    if scope_id is None:
        return True
    scope = _violation_scope(item)
    return scope is None or scope == scope_id


def decide_context_integrity(context_records=(), scope_id=None) -> str:
    """Map plain context records to their context-integrity value.

    CRITICAL unresolved in scope gives BLOCKED; HIGH unresolved (and no
    CRITICAL unresolved) gives REWORK; all resolved or empty gives PASS
    (K13 §45A mapping).
    """
    blocking_high = False
    for item in _as_record_tuple(context_records):
        if not _violation_in_scope(item, scope_id):
            continue
        if _violation_resolved(item):
            continue
        severity = _violation_severity(item)
        if severity == "CRITICAL":
            return "BLOCKED"
        if severity == "HIGH":
            blocking_high = True
    if blocking_high:
        return "REWORK"
    return CONTEXT_INTEGRITY_PASS


def decide_audit_result(
    context_records=(),
    context_integrity=CONTEXT_INTEGRITY_PASS,
    scope_id=None,
):
    """Decide the audit result for plain context records.

    Rejects a context_integrity outside PASS/REWORK/BLOCKED (R13); an
    unresolved HIGH/CRITICAL in scope means the result is NOT PASS (R10);
    PASS is returned only while context_integrity reads PASS (R14).
    """
    if context_integrity not in CONTEXT_INTEGRITY_VALUES:
        raise ValueError(
            "context_integrity %r is not one of %s"
            % (context_integrity, "/".join(CONTEXT_INTEGRITY_VALUES))
        )
    integrity = decide_context_integrity(context_records, scope_id)
    if integrity == "BLOCKED":
        return AuditResult.BLOCKED
    if integrity == "REWORK":
        return AuditResult.REWORK
    if context_integrity != CONTEXT_INTEGRITY_PASS:
        return AuditResult(context_integrity)
    return AuditResult.PASS


def validate_audit_result(
    result, context_integrity, context_records=(), scope_id=None
):
    """Reject an audit result the integrity rules forbid (else return it).

    R13 rejects a context_integrity outside PASS/REWORK/BLOCKED; R14
    forbids PASS unless context_integrity reads PASS; R10 forbids PASS
    while an unresolved HIGH/CRITICAL violation sits in the audited scope.
    """
    if context_integrity not in CONTEXT_INTEGRITY_VALUES:
        raise ValueError(
            "context_integrity %r is not one of %s"
            % (context_integrity, "/".join(CONTEXT_INTEGRITY_VALUES))
        )
    if result == AuditResult.PASS:
        if context_integrity != CONTEXT_INTEGRITY_PASS:
            raise ValueError(
                "PASS is forbidden unless context_integrity reads PASS"
            )
        integrity = decide_context_integrity(context_records, scope_id)
        if integrity != CONTEXT_INTEGRITY_PASS:
            raise ValueError(
                "PASS is forbidden with an unresolved HIGH/CRITICAL "
                "violation in scope"
            )
    return result


@dataclass(frozen=True)
class RequirementVerdictRow:
    """One requirement's audit verdict with its evidence (SPEC 0A)."""

    requirement_id: str
    verdict: RequirementVerdict
    evidence_refs: Tuple[str, ...] = ()
    note: Optional[str] = None


@dataclass(frozen=True)
class AuditRecord:
    """Immutable authoritative audit record (mirrors K13 §21C record shape).

    context_session_ref is unique and differs from every producer session
    of the scope (SPEC 18); audit_scope_id is deterministic
    (canonicalized, same inputs give the same id); audit_sequence is
    monotonic per scope with UNIQUE(scope, sequence); latest wins.
    context_integrity carries the register result and PASS is forbidden
    unless it reads PASS (K13 §45A).
    """

    audit_id: str
    project_id: str
    task_id: str
    run_id: str
    audit_scope_id: str
    audit_sequence: int
    supersedes_audit_id: Optional[str]
    context_session_ref: str
    producer_session_refs: Tuple[str, ...]
    implementer_model_ids: Tuple[str, ...]
    contract_hash: str
    audit_policy_ref: str
    artifact_refs: Tuple[str, ...]
    evidence_refs: Tuple[str, ...]
    requirement_verdicts: Tuple[RequirementVerdictRow, ...]
    context_integrity: str
    result: AuditResult
    handling_disposition: AuditHandlingDisposition
    failure_class: Optional[VerificationFailureClass]
    created_at: str
    decided_at: Optional[str] = None


@dataclass(frozen=True)
class AuditExecutionRecord:
    """The audit execution with the auditor's actual runtime binding (SPEC 18)."""

    audit_execution_id: str
    audit_id: str
    project_id: str
    task_id: str
    run_id: Optional[str]
    auditor_provider_id: str
    auditor_model: str
    auditor_session_ref: str
    implementer_model_ids: Tuple[str, ...]
    independence_level: IndependenceLevel
    manual_reviewer_ref: Optional[str]
    created_at: str


#: Live audit-log state (module-level; thin subclasses carry no state).
_AUDIT_RECORDS: Dict[str, AuditRecord] = {}
_INSERT_ORDER: Dict[str, int] = {}
_INSERT_SERIAL: int = 0


def _store_record(
    record: AuditRecord, context_records=()
) -> AuditRecord:
    """Persist one record; latest write wins, first-seen order is kept.

    The ctx-integrity PASS block runs on this persisted path: a
    context_integrity outside PASS/REWORK/BLOCKED, a PASS without a PASS
    integrity, and a PASS refused by the audited scope mapping all raise
    and store nothing.
    """
    validate_audit_result(
        record.result,
        record.context_integrity,
        context_records,
        scope_id=record.audit_scope_id,
    )
    global _INSERT_SERIAL
    if record.audit_id not in _INSERT_ORDER:
        _INSERT_ORDER[record.audit_id] = _INSERT_SERIAL
        _INSERT_SERIAL += 1
    _AUDIT_RECORDS[record.audit_id] = record
    return record


def _fetch_record(audit_id: str) -> Optional[AuditRecord]:
    """Return one stored record by id, or None when absent."""
    return _AUDIT_RECORDS.get(audit_id)


def _records_for_run(run_id: str) -> Tuple[AuditRecord, ...]:
    """Stored records for one run, in insertion order."""
    matching = [r for r in _AUDIT_RECORDS.values() if r.run_id == run_id]
    matching.sort(key=lambda r: _INSERT_ORDER[r.audit_id])
    return tuple(matching)


class AuditLog(Protocol):
    """Append-only audit log; every close leaves a queryable row (M-P1-41)."""

    def append(
        self, record: AuditRecord, context_records=()
    ) -> AuditRecord:
        """Persist one immutable audit record; duplicates return stored.

        The optional plain record list (severity plus resolved/status plus
        scope fields) carries the audited scope; a PASS the mapping refuses
        raises and is never stored.
        """
        return _store_record(record, context_records)

    def load(self, audit_id: str) -> AuditRecord | None:
        """Return one audit record by id, if present."""
        return _fetch_record(audit_id)

    def latest_for_scope(self, audit_scope_id: str) -> AuditRecord | None:
        """Return the highest-sequence record for a scope (latest wins)."""
        matching = [
            r for r in _AUDIT_RECORDS.values() if r.audit_scope_id == audit_scope_id
        ]
        if not matching:
            return None
        return max(
            matching,
            key=lambda r: (r.audit_sequence, _INSERT_ORDER[r.audit_id]),
        )

    def list_by_task(self, task_id: str) -> Tuple[AuditRecord, ...]:
        """Return a task's audit records in replay-friendly order."""
        matching = [r for r in _AUDIT_RECORDS.values() if r.task_id == task_id]
        matching.sort(key=lambda r: (r.audit_sequence, _INSERT_ORDER[r.audit_id]))
        return tuple(matching)
