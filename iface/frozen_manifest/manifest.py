"""K13 frozen manifest interface.

FROZEN: read-only transcription of RECORDS/day0/K13_MANIFEST.md (Day 0 DRAFT).
Naming authority is RECORDS/day0/0C_ARCHITECTURE.md: 0C wins every clash
(manifest reconciliation table; otherwise "none").

Verify at start: call verify_manifest() against the manifest file before
trusting these values. Changes only as a named delta (K13-DELTA-n) with a
supersedes ref; anything that cannot be expressed as a delta is escalated via
HD_REQUEST. Never silently edit this module.
"""

from __future__ import annotations

import hashlib
from enum import Enum
from pathlib import Path
from typing import Any, Dict, FrozenSet, Optional, Protocol, Union

MANIFEST_SHA256 = "f256bab4d31be3cd9e86c22a1bdcef90b08ad62500a8eca2051705cc0a9b0690"


def verify_manifest(path: Union[str, Path]) -> bool:
    """Return True iff the file at *path* matches MANIFEST_SHA256."""
    try:
        digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return False
    return digest == MANIFEST_SHA256


class TaskState(str, Enum):
    """Manifest section 12 TASK_STATE_MACHINE."""

    CREATED = "CREATED"
    PACKAGED = "PACKAGED"
    ASSIGNED = "ASSIGNED"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    AUDITING = "AUDITING"
    REWORK_PENDING = "REWORK_PENDING"
    BLOCKED = "BLOCKED"
    ESCALATED = "ESCALATED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


class AuditResult(str, Enum):
    """Manifest section 17B CANONICAL_AUDIT_RESULT (canonical verdicts)."""

    PASS = "PASS"
    REWORK = "REWORK"
    BLOCKED = "BLOCKED"
    ESCALATE = "ESCALATE"
    FAIL = "FAIL"


class AuditHandlingDisposition(str, Enum):
    """Manifest section 17B (runtime decision; never rewrites the result)."""

    COMPLETE = "COMPLETE"
    REWORK = "REWORK"
    BLOCK = "BLOCK"
    ESCALATE = "ESCALATE"
    FAIL = "FAIL"


class CompletionDisposition(str, Enum):
    """Manifest section 18B COMPLETION_DISPOSITION."""

    VERIFIED_PASS = "VERIFIED_PASS"
    ACCEPTED_RISK = "ACCEPTED_RISK"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ExecutionRunStatus(str, Enum):
    """Manifest section 14A EXECUTION_LIFECYCLE_ENUMS."""

    CREATED = "CREATED"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    AUDITING = "AUDITING"
    REWORK_REQUIRED = "REWORK_REQUIRED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"


class ExecutionAttemptStatus(str, Enum):
    """Manifest section 14A (linear lifecycle, section 14B)."""

    CREATED = "CREATED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class RunTerminationReason(str, Enum):
    """Manifest section 14A RUN_STATUS_TERMINATION_COMPATIBILITY."""

    NONE = "NONE"
    COMPLETED = "COMPLETED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    AUDIT_FAIL = "AUDIT_FAIL"
    CANCELLED_BY_USER = "CANCELLED_BY_USER"
    CANCELLED_BY_AMENDMENT = "CANCELLED_BY_AMENDMENT"
    SUPERSEDED_BY_FALLBACK = "SUPERSEDED_BY_FALLBACK"
    SUPERSEDED_BY_REWORK = "SUPERSEDED_BY_REWORK"
    POLICY_BLOCK = "POLICY_BLOCK"
    RESOURCE_FAILURE = "RESOURCE_FAILURE"
    ROUTING_NO_ELIGIBLE_CANDIDATE = "ROUTING_NO_ELIGIBLE_CANDIDATE"
    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
    BUDGET_BLOCKED = "BUDGET_BLOCKED"


class AmendmentStatus(str, Enum):
    """Manifest section 15 AMENDMENTS."""

    PENDING = "PENDING"
    APPLIED = "APPLIED"
    SUPERSEDED = "SUPERSEDED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class AmendmentScope(str, Enum):
    """Manifest section 15 (precedence GLOBAL then PHASE then TASK)."""

    GLOBAL = "GLOBAL"
    PHASE = "PHASE"
    TASK = "TASK"


class EffectiveFrom(str, Enum):
    """Manifest section 15 (amendment timing)."""

    IMMEDIATE = "IMMEDIATE"
    NEXT_RETRY = "NEXT_RETRY"
    NEXT_TASK = "NEXT_TASK"
    NEXT_PHASE = "NEXT_PHASE"
    FUTURE_ONLY = "FUTURE_ONLY"


class VerificationResult(str, Enum):
    """Manifest section 21C VERIFICATION_RECORD."""

    PASS = "PASS"
    RETRY = "RETRY"
    FALLBACK = "FALLBACK"
    REWORK = "REWORK"
    BLOCKED = "BLOCKED"
    ESCALATE = "ESCALATE"
    FAIL = "FAIL"


class RiskLevel(str, Enum):
    """Manifest section 25A RISK_LEVEL (ordered LOW < MEDIUM < HIGH < CRITICAL)."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class IncidentSeverity(str, Enum):
    """Manifest section 46 INCIDENTS (shared severity)."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


TASK_TERMINAL: FrozenSet[TaskState] = frozenset(
    {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED}
)
"""Manifest section 12 TERMINAL. ESCALATED is NON_TERMINAL_SUSPENDED."""

TASK_ALLOWED: Dict[TaskState, FrozenSet[TaskState]] = {
    TaskState.CREATED: frozenset({TaskState.PACKAGED, TaskState.CANCELLED, TaskState.FAILED}),
    TaskState.PACKAGED: frozenset({TaskState.ASSIGNED, TaskState.BLOCKED, TaskState.CANCELLED}),
    TaskState.ASSIGNED: frozenset(
        {TaskState.PLANNING, TaskState.BLOCKED, TaskState.FAILED, TaskState.CANCELLED}
    ),
    TaskState.PLANNING: frozenset(
        {TaskState.EXECUTING, TaskState.BLOCKED, TaskState.ESCALATED, TaskState.CANCELLED}
    ),
    TaskState.EXECUTING: frozenset(
        {
            TaskState.VERIFYING,
            TaskState.REWORK_PENDING,
            TaskState.BLOCKED,
            TaskState.FAILED,
            TaskState.ESCALATED,
            TaskState.CANCELLED,
        }
    ),
    TaskState.VERIFYING: frozenset(
        {
            TaskState.AUDITING,
            TaskState.REWORK_PENDING,
            TaskState.BLOCKED,
            TaskState.FAILED,
            TaskState.ESCALATED,
            TaskState.CANCELLED,
        }
    ),
    TaskState.AUDITING: frozenset(
        {
            TaskState.COMPLETED,
            TaskState.REWORK_PENDING,
            TaskState.BLOCKED,
            TaskState.ESCALATED,
            TaskState.FAILED,
            TaskState.CANCELLED,
        }
    ),
    TaskState.REWORK_PENDING: frozenset(
        {TaskState.EXECUTING, TaskState.ESCALATED, TaskState.CANCELLED}
    ),
    TaskState.BLOCKED: frozenset({TaskState.ESCALATED, TaskState.CANCELLED}),
    TaskState.ESCALATED: frozenset({TaskState.FAILED, TaskState.CANCELLED}),
    TaskState.COMPLETED: frozenset(),
    TaskState.FAILED: frozenset(),
    TaskState.CANCELLED: frozenset(),
}
"""Manifest section 12 ALLOWED (from -> to set).

BLOCKED/ESCALATED resume edges (previous_resumable_state / resume_target_state)
are record-dynamic, not static edges, and are intentionally absent here: they
are validated against the recorded resume_target_state at commit time, never
by this table. Terminal states have no outgoing edges.
"""

TASK_CONDITIONAL_OVERRIDE_EDGES: FrozenSet[tuple] = frozenset(
    {
        (TaskState.REWORK_PENDING, TaskState.COMPLETED),
        (TaskState.BLOCKED, TaskState.COMPLETED),
        (TaskState.ESCALATED, TaskState.COMPLETED),
    }
)
"""Manifest section 12 CONDITIONAL_USER_OVERRIDE_EDGES.

Only canonical exceptions, each ONLY with explicit user authorization +
CompletionDisposition ACCEPTED_RISK + required OverrideRecord, AuditResult
unchanged; FAIL never converts (recovery is a new superseding Task).
Enabled in is_task_transition_allowed() only when override=True.
"""

TASK_DYNAMIC_RESUME_SOURCES: FrozenSet[TaskState] = frozenset(
    {TaskState.BLOCKED, TaskState.ESCALATED}
)
"""States whose resume edge is instance-dynamic (Manifest section 12
RESUME_INVARIANT): the target is the recorded resume_target_state, decided at
commit time, not by TASK_ALLOWED."""

AUDIT_RESULT_TRANSITION_MAP: Dict[AuditResult, TaskState] = {
    AuditResult.PASS: TaskState.COMPLETED,
    AuditResult.REWORK: TaskState.REWORK_PENDING,
    AuditResult.BLOCKED: TaskState.BLOCKED,
    AuditResult.ESCALATE: TaskState.ESCALATED,
    AuditResult.FAIL: TaskState.FAILED,
}
"""Manifest section 12 AUDIT_RESULT_TRANSITION_MAP (AUDITING ->)."""

RUN_TERMINAL: FrozenSet[ExecutionRunStatus] = frozenset(
    {
        ExecutionRunStatus.SUCCEEDED,
        ExecutionRunStatus.FAILED,
        ExecutionRunStatus.CANCELLED,
        ExecutionRunStatus.SUPERSEDED,
    }
)
"""Manifest section 14A run TERMINAL."""

RUN_ALLOWED: Dict[ExecutionRunStatus, FrozenSet[ExecutionRunStatus]] = {
    ExecutionRunStatus.CREATED: frozenset(
        {
            ExecutionRunStatus.RUNNING,
            ExecutionRunStatus.FAILED,
            ExecutionRunStatus.CANCELLED,
            ExecutionRunStatus.SUPERSEDED,
        }
    ),
    ExecutionRunStatus.RUNNING: frozenset(
        {
            ExecutionRunStatus.VERIFYING,
            ExecutionRunStatus.FAILED,
            ExecutionRunStatus.CANCELLED,
            ExecutionRunStatus.SUPERSEDED,
        }
    ),
    ExecutionRunStatus.VERIFYING: frozenset(
        {
            ExecutionRunStatus.RUNNING,
            ExecutionRunStatus.AUDITING,
            ExecutionRunStatus.REWORK_REQUIRED,
            ExecutionRunStatus.FAILED,
            ExecutionRunStatus.CANCELLED,
            ExecutionRunStatus.SUPERSEDED,
        }
    ),
    ExecutionRunStatus.AUDITING: frozenset(
        {
            ExecutionRunStatus.SUCCEEDED,
            ExecutionRunStatus.REWORK_REQUIRED,
            ExecutionRunStatus.FAILED,
            ExecutionRunStatus.CANCELLED,
            ExecutionRunStatus.SUPERSEDED,
        }
    ),
    ExecutionRunStatus.REWORK_REQUIRED: frozenset(
        {ExecutionRunStatus.SUPERSEDED, ExecutionRunStatus.CANCELLED}
    ),
    ExecutionRunStatus.SUCCEEDED: frozenset(),
    ExecutionRunStatus.FAILED: frozenset(),
    ExecutionRunStatus.CANCELLED: frozenset(),
    ExecutionRunStatus.SUPERSEDED: frozenset(),
}
"""Manifest section 14A run ALLOWED. REWORK_REQUIRED never returns to RUNNING
in-run (correction is a new run)."""

ATTEMPT_TERMINAL: FrozenSet[ExecutionAttemptStatus] = frozenset(
    {
        ExecutionAttemptStatus.SUCCEEDED,
        ExecutionAttemptStatus.FAILED,
        ExecutionAttemptStatus.CANCELLED,
    }
)

ATTEMPT_ALLOWED: Dict[ExecutionAttemptStatus, FrozenSet[ExecutionAttemptStatus]] = {
    ExecutionAttemptStatus.CREATED: frozenset({ExecutionAttemptStatus.RUNNING}),
    ExecutionAttemptStatus.RUNNING: frozenset(
        {
            ExecutionAttemptStatus.SUCCEEDED,
            ExecutionAttemptStatus.FAILED,
            ExecutionAttemptStatus.CANCELLED,
        }
    ),
    ExecutionAttemptStatus.SUCCEEDED: frozenset(),
    ExecutionAttemptStatus.FAILED: frozenset(),
    ExecutionAttemptStatus.CANCELLED: frozenset(),
}
"""Manifest section 14B linear lifecycle: a finished attempt never reopens."""


def _coerce_task_state(value: Union[str, TaskState]) -> Optional[TaskState]:
    if isinstance(value, TaskState):
        return value
    try:
        return TaskState(str(value))
    except ValueError:
        return None


def _coerce_run_status(value: Union[str, ExecutionRunStatus]) -> Optional[ExecutionRunStatus]:
    if isinstance(value, ExecutionRunStatus):
        return value
    try:
        return ExecutionRunStatus(str(value))
    except ValueError:
        return None


def _coerce_attempt_status(
    value: Union[str, ExecutionAttemptStatus],
) -> Optional[ExecutionAttemptStatus]:
    if isinstance(value, ExecutionAttemptStatus):
        return value
    try:
        return ExecutionAttemptStatus(str(value))
    except ValueError:
        return None


def is_task_transition_allowed(
    from_state: Union[str, TaskState],
    to_state: Union[str, TaskState],
    override: bool = False,
) -> bool:
    """Return True iff the task edge from_state -> to_state is statically legal.

    Manifest section 12. Conditional accepted-risk edges to COMPLETED are
    allowed only with override=True. Dynamic resume edges out of
    BLOCKED/ESCALATED are NOT decided here (always False); they are validated
    against the recorded resume_target_state at commit time. Unknown states
    are never allowed.
    """
    src = _coerce_task_state(from_state)
    dst = _coerce_task_state(to_state)
    if src is None or dst is None:
        return False
    if dst in TASK_ALLOWED.get(src, frozenset()):
        return True
    if override and (src, dst) in TASK_CONDITIONAL_OVERRIDE_EDGES:
        return True
    return False


def is_run_transition_allowed(
    from_status: Union[str, ExecutionRunStatus],
    to_status: Union[str, ExecutionRunStatus],
) -> bool:
    """Return True iff the run edge from_status -> to_status is legal.

    Manifest section 14A run ALLOWED. Unknown statuses are never allowed.
    """
    src = _coerce_run_status(from_status)
    dst = _coerce_run_status(to_status)
    if src is None or dst is None:
        return False
    return dst in RUN_ALLOWED.get(src, frozenset())


def is_attempt_transition_allowed(
    from_status: Union[str, ExecutionAttemptStatus],
    to_status: Union[str, ExecutionAttemptStatus],
) -> bool:
    """Return True iff the attempt edge from_status -> to_status is legal.

    Manifest section 14B linear lifecycle. Unknown statuses are never allowed.
    """
    src = _coerce_attempt_status(from_status)
    dst = _coerce_attempt_status(to_status)
    if src is None or dst is None:
        return False
    return dst in ATTEMPT_ALLOWED.get(src, frozenset())


CONTEXT_WRONG_CONTRACT_VERSION = "CONTEXT_WRONG_CONTRACT_VERSION"
POLICY_CONFLICT = "POLICY_CONFLICT"
CONTEXT_MISSING = "CONTEXT_MISSING"


class ContextWrongContractVersionError(Exception):
    """Stale handoff executed under a superseded contract (Manifest 21A gate)."""

    code = CONTEXT_WRONG_CONTRACT_VERSION


class PolicyConflictError(Exception):
    """Handoff policy refs differ from the active TaskContract refs (21A gate)."""

    code = POLICY_CONFLICT


class ContextMissingError(Exception):
    """Required handoff context absent; no execution (Manifest 21A gate)."""

    code = CONTEXT_MISSING


class RepositoryPort(Protocol):
    """Frozen repository port shape (Manifest ports section).

    One port per aggregate in src/agent_si/storage/; adapters live in
    src/agent_si/adapters/sqlite/ and core never imports adapters.
    load(id) -> record | None; append(record) -> record (immutable logs;
    duplicate idempotent key returns the stored record);
    compare_and_set(id, expected_version, record) -> record (mutable
    aggregates; loser re-reads); list_by(query) -> records in
    replay/audit-friendly order. CAS + UNIQUE rules per record section.
    """

    def load(self, record_id: str) -> Optional[Any]: ...

    def append(self, record: Any) -> Any: ...

    def compare_and_set(
        self, record_id: str, expected_version: Any, record: Any
    ) -> Any: ...

    def list_by(self, query: Any) -> list: ...


class CounterStore(Protocol):
    """Frozen counter port shape (Manifest section 16, ports section).

    increment(scope, kind, limit) -> value: atomic, restart-safe counter bump
    (ReworkCounterRecord / FallbackCounterRecord backing).
    """

    def increment(self, scope: str, kind: str, limit: int) -> int: ...


TASK_CONTRACT_FIELDS = (
    "schema_version",
    "contract_version",
    "contract_sequence",
    "contract_hash",
    "project_id",
    "task_id",
    "parent_task_id",
    "supersedes_task_id",
    "phase_id",
    "created_at",
    "created_by",
    "priority",
    "risk",
    "goal",
    "requirements",
    "acceptance_criteria",
    "inputs",
    "outputs",
    "workspace",
    "permissions",
    "tools",
    "verification_policy_ref",
    "audit_policy_ref",
    "routing_policy_ref",
    "retry_policy_ref",
    "fallback_policy_ref",
    "optimization_policy_ref",
    "override_policy_ref",
)
"""Manifest section 13 TaskContract field order (seven policy refs)."""

CONTRACT_ACTIVATION_FIELDS = (
    "activation_id",
    "project_id",
    "task_id",
    "activation_sequence",
    "contract_version",
    "contract_sequence",
    "contract_hash",
    "previous_contract_hash",
    "amendment_id",
    "effective_from",
    "activation_reason",
    "activated_at",
    "evidence_refs",
)
"""Manifest section 15 ContractActivationRecord field order."""

AMENDMENT_FIELDS = (
    "amendment_id",
    "project_id",
    "amendment_sequence",
    "scope",
    "effective_from",
    "target",
    "change",
    "reason",
    "created_at",
    "source",
    "status",
)
"""Manifest section 15 Amendment field order."""

TRANSITION_FIELDS = (
    "transition_id",
    "project_id",
    "task_id",
    "run_id",
    "transition_sequence",
    "expected_from_state",
    "expected_state_version",
    "new_state_version",
    "actor",
    "from",
    "to",
    "reason",
    "timestamp",
    "evidence_ref",
    "suspended_from_state",
    "resume_target_state",
)
"""Manifest section 12 transition record field order."""


__all__ = [
    "MANIFEST_SHA256",
    "verify_manifest",
    "TaskState",
    "AuditResult",
    "AuditHandlingDisposition",
    "CompletionDisposition",
    "ExecutionRunStatus",
    "ExecutionAttemptStatus",
    "RunTerminationReason",
    "AmendmentStatus",
    "AmendmentScope",
    "EffectiveFrom",
    "VerificationResult",
    "RiskLevel",
    "IncidentSeverity",
    "TASK_TERMINAL",
    "TASK_ALLOWED",
    "TASK_CONDITIONAL_OVERRIDE_EDGES",
    "TASK_DYNAMIC_RESUME_SOURCES",
    "AUDIT_RESULT_TRANSITION_MAP",
    "RUN_TERMINAL",
    "RUN_ALLOWED",
    "ATTEMPT_TERMINAL",
    "ATTEMPT_ALLOWED",
    "is_task_transition_allowed",
    "is_run_transition_allowed",
    "is_attempt_transition_allowed",
    "CONTEXT_WRONG_CONTRACT_VERSION",
    "POLICY_CONFLICT",
    "CONTEXT_MISSING",
    "ContextWrongContractVersionError",
    "PolicyConflictError",
    "ContextMissingError",
    "RepositoryPort",
    "CounterStore",
    "TASK_CONTRACT_FIELDS",
    "CONTRACT_ACTIVATION_FIELDS",
    "AMENDMENT_FIELDS",
    "TRANSITION_FIELDS",
]
