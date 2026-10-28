"""ExecutionRun lifecycle state machine (Manifest sections 14, 14A).

Covers the section 14 ExecutionRun record (one contract_hash per life,
atomic run_sequence UNIQUE(task, sequence), revision_no for verification /
audit correction loops only), the frozen 15-step creation transaction (no
execution before the step-13 AttemptExecutionGate passes), the section 14A
ALLOWED table + TERMINAL set, the RUN_STATUS_TERMINATION_COMPATIBILITY map,
the pre-run failure disposition per cause, and the audit disposition map
(BLOCKED / ESCALATE are task-level suspensions, never run-terminal).

Shared names come ONLY from iface.frozen_manifest.manifest (M1a-owned);
this module defines no parallel enums. Runs are frozen dataclasses: every
transition returns a NEW instance; committed history is never rewritten.
Atomicity across writers is the repository compare_and_set (the run record
itself carries no version: manifest section 14 defines no state_version
field); the pure transition guards status + edge + compatibility and
validates the caller-supplied version token shape.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, FrozenSet, Iterable, Optional, Tuple

try:
    from iface.frozen_manifest import manifest
except ImportError:  # alternate layout: the iface/ directory itself on sys.path
    from frozen_manifest import manifest


INITIAL_EXECUTION = "INITIAL_EXECUTION"
VERIFICATION_REWORK = "VERIFICATION_REWORK"
AUDIT_REWORK = "AUDIT_REWORK"
AMENDMENT_RESTART = "AMENDMENT_RESTART"
FALLBACK_REROUTE = "FALLBACK_REROUTE"

CREATION_REASONS: FrozenSet[str] = frozenset(
    {
        INITIAL_EXECUTION,
        VERIFICATION_REWORK,
        AUDIT_REWORK,
        AMENDMENT_RESTART,
        FALLBACK_REROUTE,
    }
)
"""Manifest section 14 ExecutionRunCreationReason values (plain strings;
the frozen manifest module carries no enum for them)."""

_CORRECTION_REASONS: FrozenSet[str] = frozenset(
    {VERIFICATION_REWORK, AUDIT_REWORK}
)

TERMINAL = manifest.RUN_TERMINAL
"""Manifest section 14A run TERMINAL (shared name, not redefined)."""

ALLOWED = manifest.RUN_ALLOWED
"""Manifest section 14A run ALLOWED (shared name, not redefined)."""

CREATION_STEPS: Tuple[str, ...] = (
    "RESOLVE_ACTIVE_CONTRACT",
    "ALLOCATE_RUN_SEQUENCE",
    "BUILD_SKELETON",
    "MODEL_ROUTER_CANDIDATES",
    "SCHEDULER_PRECHECK",
    "BUDGET_PRECHECK",
    "PERSIST_ROUTING_EVIDENCE_SNAPSHOT",
    "PERSIST_ROUTING_DECISION",
    "BIND_ROUTING_FIELDS",
    "SCHEDULER_RESERVE",
    "BUDGET_RESERVE",
    "COMPENSATE_ON_LATER_GATE_FAILURE",
    "ATTEMPT_EXECUTION_GATE",
    "START_RUNNING",
    "PRE_RUN_FAILURE_DISPOSITION",
)
"""Frozen section 14 creation order. Step 13 (index 12) is the
AttemptExecutionGate: no execution before it passes. Step 15 routes a
gate failure to the pre-run failure disposition."""

GATE_STEP = "ATTEMPT_EXECUTION_GATE"

RUN_STATUS_TERMINATION_COMPATIBILITY: Dict[
    manifest.ExecutionRunStatus, FrozenSet[manifest.RunTerminationReason]
] = {
    manifest.ExecutionRunStatus.SUCCEEDED: frozenset(
        {manifest.RunTerminationReason.COMPLETED}
    ),
    manifest.ExecutionRunStatus.FAILED: frozenset(
        {
            manifest.RunTerminationReason.EXECUTION_FAILED,
            manifest.RunTerminationReason.VERIFICATION_FAILED,
            manifest.RunTerminationReason.AUDIT_FAIL,
            manifest.RunTerminationReason.POLICY_BLOCK,
            manifest.RunTerminationReason.RESOURCE_FAILURE,
            manifest.RunTerminationReason.ROUTING_NO_ELIGIBLE_CANDIDATE,
            manifest.RunTerminationReason.CAPABILITY_UNAVAILABLE,
            manifest.RunTerminationReason.BUDGET_BLOCKED,
        }
    ),
    manifest.ExecutionRunStatus.CANCELLED: frozenset(
        {
            manifest.RunTerminationReason.CANCELLED_BY_USER,
            manifest.RunTerminationReason.CANCELLED_BY_AMENDMENT,
        }
    ),
    manifest.ExecutionRunStatus.SUPERSEDED: frozenset(
        {
            manifest.RunTerminationReason.SUPERSEDED_BY_FALLBACK,
            manifest.RunTerminationReason.SUPERSEDED_BY_REWORK,
        }
    ),
    manifest.ExecutionRunStatus.CREATED: frozenset(
        {manifest.RunTerminationReason.NONE}
    ),
    manifest.ExecutionRunStatus.RUNNING: frozenset(
        {manifest.RunTerminationReason.NONE}
    ),
    manifest.ExecutionRunStatus.VERIFYING: frozenset(
        {manifest.RunTerminationReason.NONE}
    ),
    manifest.ExecutionRunStatus.AUDITING: frozenset(
        {manifest.RunTerminationReason.NONE}
    ),
    manifest.ExecutionRunStatus.REWORK_REQUIRED: frozenset(
        {manifest.RunTerminationReason.NONE}
    ),
}
"""Manifest section 14A RUN_STATUS_TERMINATION_COMPATIBILITY. Invalid pairs
are prohibited; audit result values are never run statuses."""


class RunMachineError(Exception):
    """Base error for ExecutionRun lifecycle violations (sections 14, 14A)."""


class StaleRunStateError(RunMachineError):
    """CAS failure: current status/version differs from expected (loser re-reads)."""


class IllegalRunTransitionError(RunMachineError):
    """Edge absent from the section 14A ALLOWED table (incl. terminal exits)."""


class IncompatibleTerminationError(RunMachineError):
    """Status/termination-reason pair outside the compatibility map."""


class DuplicateRunSequenceError(RunMachineError):
    """run_sequence already allocated for this task (UNIQUE(task, sequence))."""


class CreationOrderError(RunMachineError):
    """Creation step taken out of the frozen 15-step order."""


class GateNotPassedError(RunMachineError):
    """Step-13 AttemptExecutionGate has not passed; no execution allowed."""


class ExecutionBeforeGateError(GateNotPassedError):
    """Execution noted before the step-13 gate passed."""


class PreRunDispositionError(RunMachineError):
    """Pre-run disposition requested for a non-CREATED run or unknown cause."""


class AuditDispositionError(RunMachineError):
    """Audit disposition requested for a non-AUDITING run or unknown result."""


def _coerce_status(value: object) -> manifest.ExecutionRunStatus:
    if isinstance(value, manifest.ExecutionRunStatus):
        return value
    try:
        return manifest.ExecutionRunStatus(str(value))
    except ValueError:
        raise IllegalRunTransitionError(
            "unknown run status %r (sections 14, 14A)" % (value,)
        ) from None


def _coerce_reason(value: object) -> manifest.RunTerminationReason:
    if isinstance(value, manifest.RunTerminationReason):
        return value
    try:
        return manifest.RunTerminationReason(str(value))
    except ValueError:
        raise IncompatibleTerminationError(
            "unknown termination reason %r (section 14A)" % (value,)
        ) from None


@dataclass(frozen=True)
class ExecutionRun:
    """Manifest section 14 ExecutionRun. Immutable; one contract_hash per life.

    Full section 14 selection-field set: routing/selection fields stay null
    until step 9 binds them (bind_routing_fields / bind_selection_fields).
    No state_version: the manifest defines none; commit-time compare-and-set
    lives in the repository port, not on the record.
    """

    run_id: str = ""
    project_id: str = ""
    task_id: str = ""
    contract_hash: str = ""
    run_sequence: int = 0
    revision_no: int = 0
    creation_reason: str = INITIAL_EXECUTION
    source_run_id: Optional[str] = None
    routing_decision_ref: Optional[str] = None
    routing_decision_refs: Tuple[str, ...] = ()
    route: Optional[str] = None
    split_strategy: Optional[str] = None
    primary_provider: Optional[str] = None
    primary_provider_instance: Optional[str] = None
    primary_model: Optional[str] = None
    implementer_provider_ids: Tuple[str, ...] = ()
    implementer_model_ids: Tuple[str, ...] = ()
    status: manifest.ExecutionRunStatus = manifest.ExecutionRunStatus.CREATED
    termination_reason: manifest.RunTerminationReason = (
        manifest.RunTerminationReason.NONE
    )
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    created_at: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.status, str) and not isinstance(
            self.status, manifest.ExecutionRunStatus
        ):
            object.__setattr__(
                self, "status", manifest.ExecutionRunStatus(self.status)
            )
        if isinstance(self.termination_reason, str) and not isinstance(
            self.termination_reason, manifest.RunTerminationReason
        ):
            object.__setattr__(
                self,
                "termination_reason",
                manifest.RunTerminationReason(self.termination_reason),
            )
        if not isinstance(self.routing_decision_refs, tuple):
            object.__setattr__(
                self,
                "routing_decision_refs",
                tuple(self.routing_decision_refs or ()),
            )
        if not isinstance(self.implementer_provider_ids, tuple):
            object.__setattr__(
                self,
                "implementer_provider_ids",
                tuple(self.implementer_provider_ids or ()),
            )
        if not isinstance(self.implementer_model_ids, tuple):
            object.__setattr__(
                self,
                "implementer_model_ids",
                tuple(self.implementer_model_ids or ()),
            )


@dataclass(frozen=True)
class CreationState:
    """Transient cursor over the frozen 15-step creation transaction (section 14)."""

    steps_completed: Tuple[str, ...] = ()
    gate_passed: bool = False
    execution_noted: bool = False


def is_termination_compatible(status: object, reason: object) -> bool:
    """Return True iff the status/reason pair is compatible (section 14A)."""
    try:
        status_value = _coerce_status(status)
    except IllegalRunTransitionError:
        return False
    try:
        reason_value = _coerce_reason(reason)
    except IncompatibleTerminationError:
        return False
    return reason_value in RUN_STATUS_TERMINATION_COMPATIBILITY.get(
        status_value, frozenset()
    )


def allocate_run_sequence(existing_sequences: Iterable[int]) -> int:
    """Allocate the next run_sequence: max + 1, starting at 1 (atomic per task)."""
    used = list(existing_sequences or ())
    return (max(used) + 1) if used else 1


def derive_revision_no(creation_reason: str, source_revision_no: int = 0) -> int:
    """Derive revision_no (section 14): verification/audit correction loops
    increment; amendment restart / fallback reroute do NOT increment."""
    if creation_reason not in CREATION_REASONS:
        raise ValueError("unknown creation reason %r (section 14)" % (creation_reason,))
    if creation_reason in _CORRECTION_REASONS:
        return source_revision_no + 1
    return source_revision_no


def create_run(
    *,
    run_id: str,
    project_id: str,
    task_id: str,
    contract_hash: str,
    run_sequence: int,
    existing_sequences: Iterable[int] = (),
    creation_reason: str = INITIAL_EXECUTION,
    source_run: Optional[ExecutionRun] = None,
    created_at: str = "",
) -> ExecutionRun:
    """Build the step-3 skeleton: CREATED, NONE, active hash, nulls (section 14).

    Enforces a non-empty active contract_hash, UNIQUE(task, run_sequence),
    and the revision_no rule. Selection/routing fields stay null until
    step 9 binds them (bind_routing_fields / bind_selection_fields).
    """
    if not contract_hash:
        raise ValueError("active contract_hash is required (section 14)")
    if creation_reason not in CREATION_REASONS:
        raise ValueError("unknown creation reason %r (section 14)" % (creation_reason,))
    if run_sequence in set(existing_sequences or ()):
        raise DuplicateRunSequenceError(
            "run_sequence %r already allocated (UNIQUE(task, sequence))"
            % (run_sequence,)
        )
    if creation_reason == INITIAL_EXECUTION:
        if source_run is not None:
            raise ValueError("INITIAL_EXECUTION carries no source run (section 14)")
        revision_no = 0
    else:
        if creation_reason in _CORRECTION_REASONS and source_run is None:
            raise ValueError(
                "%s requires a source run (section 14)" % creation_reason
            )
        revision_no = derive_revision_no(
            creation_reason,
            source_run.revision_no if source_run is not None else 0,
        )
    return ExecutionRun(
        run_id=run_id,
        project_id=project_id,
        task_id=task_id,
        contract_hash=contract_hash,
        run_sequence=run_sequence,
        revision_no=revision_no,
        creation_reason=creation_reason,
        source_run_id=source_run.run_id if source_run is not None else None,
        created_at=created_at,
    )


def bind_routing_fields(
    run: ExecutionRun, *, routing_decision_ref: str, route: str
) -> ExecutionRun:
    """Bind step-9 routing fields onto a CREATED skeleton (section 14)."""
    if run.status != manifest.ExecutionRunStatus.CREATED:
        raise CreationOrderError("routing binds only onto a CREATED skeleton")
    return replace(run, routing_decision_ref=routing_decision_ref, route=route)


def bind_selection_fields(
    run: ExecutionRun,
    *,
    routing_decision_refs: Iterable[str] = (),
    split_strategy: Optional[str] = None,
    primary_provider: Optional[str] = None,
    primary_provider_instance: Optional[str] = None,
    primary_model: Optional[str] = None,
    implementer_provider_ids: Iterable[str] = (),
    implementer_model_ids: Iterable[str] = (),
) -> ExecutionRun:
    """Bind step-9 selection fields onto a CREATED skeleton (section 14)."""
    if run.status != manifest.ExecutionRunStatus.CREATED:
        raise CreationOrderError("selection binds only onto a CREATED skeleton")
    return replace(
        run,
        routing_decision_refs=tuple(routing_decision_refs or ()),
        split_strategy=split_strategy,
        primary_provider=primary_provider,
        primary_provider_instance=primary_provider_instance,
        primary_model=primary_model,
        implementer_provider_ids=tuple(implementer_provider_ids or ()),
        implementer_model_ids=tuple(implementer_model_ids or ()),
    )


def advance_creation(state: CreationState, step: str) -> CreationState:
    """Complete the next frozen creation step, in order (section 14)."""
    if len(state.steps_completed) >= len(CREATION_STEPS):
        raise CreationOrderError("all 15 creation steps are complete")
    expected = CREATION_STEPS[len(state.steps_completed)]
    if step != expected:
        raise CreationOrderError(
            "creation step %r out of order: expected %r (section 14)" % (step, expected)
        )
    return replace(state, steps_completed=state.steps_completed + (step,))


def pass_attempt_gate(state: CreationState) -> CreationState:
    """Record the step-13 AttemptExecutionGate pass (section 14, 17C)."""
    if GATE_STEP not in state.steps_completed:
        raise GateNotPassedError(
            "AttemptExecutionGate step not reached (section 14 step 13)"
        )
    return replace(state, gate_passed=True)


def note_execution(state: CreationState) -> CreationState:
    """Record first execution; prohibited before the step-13 gate passes."""
    if not state.gate_passed:
        raise ExecutionBeforeGateError(
            "no execution before the step-13 AttemptExecutionGate passes"
        )
    return replace(state, execution_noted=True)


def transition_run(
    run: ExecutionRun,
    *,
    expected_status: object,
    expected_version: int,
    to_status: object,
    termination_reason: object,
    at: str = "",
) -> ExecutionRun:
    """Commit a run transition with CAS + ALLOWED + compatibility (14, 14A).

    Commits iff current status == expected_status; the edge must be in
    ALLOWED and the status/reason pair in the compatibility map. Returns
    the NEW run; the input is untouched. Terminal entries stamp ended_at;
    RUNNING entry stamps started_at when unset. expected_version is the
    repository commit token (compare_and_set enforces it atomically there);
    it must be a non-negative int and is otherwise carried, not stored:
    the section 14 record carries no version field.
    """
    expected = _coerce_status(expected_status)
    target = _coerce_status(to_status)
    reason = _coerce_reason(termination_reason)
    if (
        isinstance(expected_version, bool)
        or not isinstance(expected_version, int)
        or expected_version < 0
    ):
        raise StaleRunStateError(
            "bad version token %r: repository compare_and_set takes a "
            "non-negative int (re-read)" % (expected_version,)
        )
    if run.status != expected:
        raise StaleRunStateError(
            "CAS mismatch: current %s != expected %s (re-read, section 12 pattern)"
            % (run.status.value, expected.value)
        )
    if not manifest.is_run_transition_allowed(run.status, target):
        raise IllegalRunTransitionError(
            "edge %s -> %s absent from ALLOWED (section 14A)"
            % (run.status.value, target.value)
        )
    if not is_termination_compatible(target, reason):
        raise IncompatibleTerminationError(
            "pair %s + %s outside compatibility (section 14A)"
            % (target.value, reason.value)
        )
    update: Dict[str, object] = {
        "status": target,
        "termination_reason": reason,
    }
    if target == manifest.ExecutionRunStatus.RUNNING and run.started_at is None:
        update["started_at"] = at or None
    if target in manifest.RUN_TERMINAL:
        update["ended_at"] = at or run.ended_at
    moved = replace(run, **update)  # type: ignore[arg-type]
    assert moved.contract_hash == run.contract_hash, "one contract_hash per life"
    return moved


def start_run(
    run: ExecutionRun,
    state: CreationState,
    *,
    expected_version: int,
    started_at: str = "",
) -> ExecutionRun:
    """Commit step 14 (CREATED -> RUNNING); requires the step-13 gate pass."""
    if not state.gate_passed or GATE_STEP not in state.steps_completed:
        raise GateNotPassedError(
            "no execution before the step-13 AttemptExecutionGate passes"
        )
    return transition_run(
        run,
        expected_status=manifest.ExecutionRunStatus.CREATED,
        expected_version=expected_version,
        to_status=manifest.ExecutionRunStatus.RUNNING,
        termination_reason=manifest.RunTerminationReason.NONE,
        at=started_at,
    )


@dataclass(frozen=True)
class PreRunDisposition:
    """Pre-run failure disposition for a CREATED run that cannot start (14)."""

    run_to_status: manifest.ExecutionRunStatus
    run_to_reason: manifest.RunTerminationReason
    task_to_state: Optional[manifest.TaskState]
    release_reservations: bool = True
    replacement_run_id: Optional[str] = None


_PRE_RUN_CAUSES: FrozenSet[manifest.RunTerminationReason] = frozenset(
    {
        manifest.RunTerminationReason.ROUTING_NO_ELIGIBLE_CANDIDATE,
        manifest.RunTerminationReason.CAPABILITY_UNAVAILABLE,
        manifest.RunTerminationReason.RESOURCE_FAILURE,
        manifest.RunTerminationReason.BUDGET_BLOCKED,
        manifest.RunTerminationReason.POLICY_BLOCK,
    }
)


def apply_pre_run_disposition(
    run: ExecutionRun,
    cause: object,
    *,
    recoverable: bool = False,
    conflict: bool = False,
    terminally_unsatisfiable: bool = False,
    correction_staging: bool = False,
    replacement_run_id: Optional[str] = None,
) -> PreRunDisposition:
    """Map a pre-run gate failure to its disposition (section 14).

    Fallback/replacement is decided BEFORE terminalization: with a
    replacement run the CREATED run goes to SUPERSEDED_BY_FALLBACK (FAILED
    never converts to SUPERSEDED); otherwise it goes FAILED with the
    canonical cause plus the task disposition. correction_staging preserves
    the failure class (run reason always equals the cause). Reservations
    for never-RUNNING runs are always released.
    """
    if run.status != manifest.ExecutionRunStatus.CREATED:
        raise PreRunDispositionError(
            "pre-run disposition applies only to CREATED runs (section 14)"
        )
    reason = _coerce_reason(cause)
    if reason not in _PRE_RUN_CAUSES:
        raise PreRunDispositionError(
            "unknown pre-run cause %r (section 14)" % (cause,)
        )
    if replacement_run_id is not None:
        return PreRunDisposition(
            run_to_status=manifest.ExecutionRunStatus.SUPERSEDED,
            run_to_reason=manifest.RunTerminationReason.SUPERSEDED_BY_FALLBACK,
            task_to_state=None,
            release_reservations=True,
            replacement_run_id=replacement_run_id,
        )
    if reason == manifest.RunTerminationReason.ROUTING_NO_ELIGIBLE_CANDIDATE:
        task_to: Optional[manifest.TaskState] = manifest.TaskState.ESCALATED
    elif reason == manifest.RunTerminationReason.CAPABILITY_UNAVAILABLE:
        task_to = manifest.TaskState.ESCALATED
    elif reason in (
        manifest.RunTerminationReason.RESOURCE_FAILURE,
        manifest.RunTerminationReason.BUDGET_BLOCKED,
    ):
        task_to = (
            manifest.TaskState.BLOCKED if recoverable else manifest.TaskState.ESCALATED
        )
    elif terminally_unsatisfiable:
        task_to = manifest.TaskState.FAILED
    elif conflict:
        task_to = manifest.TaskState.ESCALATED
    else:
        task_to = manifest.TaskState.BLOCKED
    _ = correction_staging  # documented: failure class (run reason) is preserved
    return PreRunDisposition(
        run_to_status=manifest.ExecutionRunStatus.FAILED,
        run_to_reason=reason,
        task_to_state=task_to,
        release_reservations=True,
        replacement_run_id=None,
    )


@dataclass(frozen=True)
class AuditDisposition:
    """Run audit disposition for a run in AUDITING (section 14A)."""

    run_to_status: manifest.ExecutionRunStatus
    run_to_reason: manifest.RunTerminationReason
    task_to_state: manifest.TaskState
    run_mutated: bool
    requires_replacement_run: bool
    supersede_reason_after_replacement: Optional[
        manifest.RunTerminationReason
    ] = None


def _coerce_audit_result(value: object) -> manifest.AuditResult:
    if isinstance(value, manifest.AuditResult):
        return value
    try:
        return manifest.AuditResult(str(value))
    except ValueError:
        raise AuditDispositionError(
            "unknown audit result %r (section 17B)" % (value,)
        ) from None


AUDIT_DISPOSITION: Dict[manifest.AuditResult, AuditDisposition] = {
    manifest.AuditResult.PASS: AuditDisposition(
        run_to_status=manifest.ExecutionRunStatus.SUCCEEDED,
        run_to_reason=manifest.RunTerminationReason.COMPLETED,
        task_to_state=manifest.TaskState.COMPLETED,
        run_mutated=True,
        requires_replacement_run=False,
    ),
    manifest.AuditResult.REWORK: AuditDisposition(
        run_to_status=manifest.ExecutionRunStatus.REWORK_REQUIRED,
        run_to_reason=manifest.RunTerminationReason.NONE,
        task_to_state=manifest.TaskState.REWORK_PENDING,
        run_mutated=True,
        requires_replacement_run=True,
        supersede_reason_after_replacement=(
            manifest.RunTerminationReason.SUPERSEDED_BY_REWORK
        ),
    ),
    manifest.AuditResult.FAIL: AuditDisposition(
        run_to_status=manifest.ExecutionRunStatus.FAILED,
        run_to_reason=manifest.RunTerminationReason.AUDIT_FAIL,
        task_to_state=manifest.TaskState.FAILED,
        run_mutated=True,
        requires_replacement_run=False,
    ),
    manifest.AuditResult.BLOCKED: AuditDisposition(
        run_to_status=manifest.ExecutionRunStatus.AUDITING,
        run_to_reason=manifest.RunTerminationReason.NONE,
        task_to_state=manifest.TaskState.BLOCKED,
        run_mutated=False,
        requires_replacement_run=False,
    ),
    manifest.AuditResult.ESCALATE: AuditDisposition(
        run_to_status=manifest.ExecutionRunStatus.AUDITING,
        run_to_reason=manifest.RunTerminationReason.NONE,
        task_to_state=manifest.TaskState.ESCALATED,
        run_mutated=False,
        requires_replacement_run=False,
    ),
}
"""Section 14A run audit disposition. BLOCKED / ESCALATE are task-level
suspensions: the run holds AUDITING and is never run-terminal."""


def apply_audit_disposition(
    run: ExecutionRun, result: object
) -> AuditDisposition:
    """Return the audit disposition for an AUDITING run (section 14A).

    Task legs equal manifest.AUDIT_RESULT_TRANSITION_MAP. REWORK moves the
    run to REWORK_REQUIRED and requires a replacement run, after which the
    prior run goes to SUPERSEDED_BY_REWORK. BLOCKED / ESCALATE hold the run
    in AUDITING with no run mutation.
    """
    if run.status != manifest.ExecutionRunStatus.AUDITING:
        raise AuditDispositionError(
            "audit disposition applies only to AUDITING runs (section 14A)"
        )
    verdict = _coerce_audit_result(result)
    disposition = AUDIT_DISPOSITION[verdict]
    assert disposition.run_to_status not in manifest.RUN_TERMINAL or (
        disposition.run_mutated
        and verdict in (manifest.AuditResult.PASS, manifest.AuditResult.FAIL)
    ), "BLOCKED/ESCALATE are never run-terminal (section 14A)"
    return disposition


__all__ = [
    "manifest",
    "INITIAL_EXECUTION",
    "VERIFICATION_REWORK",
    "AUDIT_REWORK",
    "AMENDMENT_RESTART",
    "FALLBACK_REROUTE",
    "CREATION_REASONS",
    "TERMINAL",
    "ALLOWED",
    "CREATION_STEPS",
    "GATE_STEP",
    "RUN_STATUS_TERMINATION_COMPATIBILITY",
    "RunMachineError",
    "StaleRunStateError",
    "IllegalRunTransitionError",
    "IncompatibleTerminationError",
    "DuplicateRunSequenceError",
    "CreationOrderError",
    "GateNotPassedError",
    "ExecutionBeforeGateError",
    "PreRunDispositionError",
    "AuditDispositionError",
    "ExecutionRun",
    "CreationState",
    "PreRunDisposition",
    "AuditDisposition",
    "AUDIT_DISPOSITION",
    "is_termination_compatible",
    "allocate_run_sequence",
    "derive_revision_no",
    "create_run",
    "bind_routing_fields",
    "bind_selection_fields",
    "advance_creation",
    "pass_attempt_gate",
    "note_execution",
    "transition_run",
    "start_run",
    "apply_pre_run_disposition",
    "apply_audit_disposition",
]
