"""Deterministic verification records + attempt-execution gate.

Manifest sections 21C VERIFICATION_RECORD, 17C VERIFICATION_FAILURE_PRECEDENCE
and 26A VERIFICATION_AND_AUDIT_POLICY (policy-ref binding background).

All helpers are pure. Scope ids are deterministic over canonicalised inputs
(normalised ids/refs, sorted arrays, deduped: same set = same id). Records
are frozen dataclasses in the style of ``agent_si.domain.contracts``: a
committed instance is never rewritten, corrections are NEW records, and the
latest record per scope is the one with the highest monotonic
``verification_sequence``. Shared names (TaskState, VerificationResult, ...)
come ONLY from ``iface.frozen_manifest.manifest``; 0C wins on any clash.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Iterable, Mapping, Optional, Tuple

try:
    from iface.frozen_manifest import manifest
except ImportError:  # alternate layout: the iface/ directory itself on sys.path
    from frozen_manifest import manifest


# --------------------------------------------------------------------------
# enums local to verification (no clash: manifest.py defines none of these)
# --------------------------------------------------------------------------

class VerificationTargetType(str, Enum):
    """Manifest section 21C verification target types."""

    RUN_OUTPUT = "RUN_OUTPUT"
    ATTEMPT_OUTPUT = "ATTEMPT_OUTPUT"
    MULTI_ATTEMPT_OUTPUT = "MULTI_ATTEMPT_OUTPUT"
    ARTIFACT_SET = "ARTIFACT_SET"
    SUBTASK_OUTPUT = "SUBTASK_OUTPUT"


class CriterionVerificationResult(str, Enum):
    """Manifest section 21C per-criterion outcomes."""

    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class VerificationHandlingDisposition(str, Enum):
    """Manifest section 21C runtime handling (never rewrites the result)."""

    ACCEPT = "ACCEPT"
    RETRY_VERIFIER = "RETRY_VERIFIER"
    RETRY_EXECUTION = "RETRY_EXECUTION"
    FALLBACK = "FALLBACK"
    REWORK = "REWORK"
    BLOCK = "BLOCK"
    ESCALATE = "ESCALATE"
    FAIL = "FAIL"


class VerificationFailureClass(str, Enum):
    """Manifest section 17C failure classes."""

    VERIFICATION_INFRA_FAILURE = "VERIFICATION_INFRA_FAILURE"
    OUTPUT_FORMAT_FAILURE = "OUTPUT_FORMAT_FAILURE"
    PROVIDER_OR_MODEL_CAPABILITY_FAILURE = (
        "PROVIDER_OR_MODEL_CAPABILITY_FAILURE"
    )
    IMPLEMENTATION_AC_DEFECT = "IMPLEMENTATION_AC_DEFECT"
    SECURITY_OR_POLICY_FAILURE = "SECURITY_OR_POLICY_FAILURE"
    UNKNOWN_FAILURE = "UNKNOWN_FAILURE"


class FailureSeverity(str, Enum):
    """Manifest section 17C severities (never selects BLOCKED/ESCALATE alone)."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class GateFailureClass(str, Enum):
    """Manifest section 17C gate-failure disposition classes."""

    BUDGET_BLOCKED = "BUDGET_BLOCKED"
    RESOURCE_FAILURE = "RESOURCE_FAILURE"
    POLICY_BLOCK = "POLICY_BLOCK"
    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
    HEALTH_FAILURE = "HEALTH_FAILURE"


class RetryKind(str, Enum):
    """Manifest section 17C retry classes."""

    VERIFICATION_ONLY_RETRY = "VERIFICATION_ONLY_RETRY"
    EXECUTION_PRODUCING_RETRY = "EXECUTION_PRODUCING_RETRY"


class CorrectionLoopKind(str, Enum):
    """Manifest section 17C correction-loop (budget) kinds."""

    VERIFICATION_LOOP = "VERIFICATION_LOOP"
    AUDIT_LOOP = "AUDIT_LOOP"


# --------------------------------------------------------------------------
# deterministic scope ids (Manifest section 21C)
# --------------------------------------------------------------------------

def _norm_token(value: object) -> str:
    token = str(value).strip()
    if not token:
        raise ValueError("scope id inputs must be non-blank strings")
    return token


def _canonical_set(values: Iterable[object]) -> Tuple[str, ...]:
    seen = set()
    for value in values:
        token = str(value).strip()
        if token:
            seen.add(token)
    ordered = tuple(sorted(seen))
    if not ordered:
        raise ValueError("scope id sets must contain at least one non-blank entry")
    return ordered


def _digest(canonical: Tuple[str, ...]) -> str:
    return hashlib.sha256("\n".join(canonical).encode("utf-8")).hexdigest()


def run_output_scope_id(task_id: object, run_id: object,
                         contract_hash: object) -> str:
    """RUN_OUTPUT scope: TASK:<task>:RUN:<run>:CONTRACT:<hash>:RUN_OUTPUT."""
    return "TASK:%s:RUN:%s:CONTRACT:%s:RUN_OUTPUT" % (
        _norm_token(task_id),
        _norm_token(run_id),
        _norm_token(contract_hash),
    )


def attempt_output_scope_id(task_id: object, run_id: object,
                             attempt_id: object) -> str:
    """ATTEMPT_OUTPUT scope: one stable id per attempt."""
    return "TASK:%s:RUN:%s:ATTEMPT:%s:ATTEMPT_OUTPUT" % (
        _norm_token(task_id),
        _norm_token(run_id),
        _norm_token(attempt_id),
    )


def multi_attempt_scope_id(attempt_ids: Iterable[object]) -> str:
    """MULTI_ATTEMPT_OUTPUT scope: sha256 over canonical sorted attempt ids."""
    return "MULTI_ATTEMPT_OUTPUT:" + _digest(_canonical_set(attempt_ids))


def artifact_set_scope_id(artifact_refs: Iterable[object]) -> str:
    """ARTIFACT_SET scope: sha256 over canonical sorted artifact refs."""
    return "ARTIFACT_SET:" + _digest(_canonical_set(artifact_refs))


def subtask_output_scope_id(task_id: object, subtask_id: object) -> str:
    """SUBTASK_OUTPUT scope: one stable id per subtask."""
    return "TASK:%s:SUBTASK:%s:SUBTASK_OUTPUT" % (
        _norm_token(task_id),
        _norm_token(subtask_id),
    )


def _coerce_target_type(value: object) -> VerificationTargetType:
    if isinstance(value, VerificationTargetType):
        return value
    return VerificationTargetType(str(value))


def scope_id_for(target_type: object, *,
                 task_id: object = "", run_id: object = "",
                 contract_hash: object = "", attempt_id: object = "",
                 attempt_ids: Iterable[object] = (),
                 artifact_refs: Iterable[object] = (),
                 subtask_id: object = "") -> str:
    """Build the scope id for *target_type* from canonicalised inputs."""
    target = _coerce_target_type(target_type)
    if target == VerificationTargetType.RUN_OUTPUT:
        return run_output_scope_id(task_id, run_id, contract_hash)
    if target == VerificationTargetType.ATTEMPT_OUTPUT:
        return attempt_output_scope_id(task_id, run_id, attempt_id)
    if target == VerificationTargetType.MULTI_ATTEMPT_OUTPUT:
        return multi_attempt_scope_id(attempt_ids)
    if target == VerificationTargetType.ARTIFACT_SET:
        return artifact_set_scope_id(artifact_refs)
    return subtask_output_scope_id(task_id, subtask_id)


# --------------------------------------------------------------------------
# records (Manifest section 21C; frozen style mirrored from domain.contracts)
# --------------------------------------------------------------------------

def _as_tuple(value: object) -> Tuple:
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    return tuple(value)


def _coerce_criterion_result(value: object) -> CriterionVerificationResult:
    if isinstance(value, CriterionVerificationResult):
        return value
    return CriterionVerificationResult(str(value))


def _coerce_severity(value: object) -> FailureSeverity:
    if isinstance(value, FailureSeverity):
        return value
    return FailureSeverity(str(value))


def _coerce_failure_class(value: object) -> Optional[VerificationFailureClass]:
    if value is None:
        return None
    if isinstance(value, VerificationFailureClass):
        return value
    return VerificationFailureClass(str(value))


def _coerce_verification_result(value: object) -> manifest.VerificationResult:
    if isinstance(value, manifest.VerificationResult):
        return value
    return manifest.VerificationResult(str(value))


def _coerce_handling(value: object) -> VerificationHandlingDisposition:
    if isinstance(value, VerificationHandlingDisposition):
        return value
    return VerificationHandlingDisposition(str(value))


@dataclass(frozen=True)
class CriterionResult:
    """Manifest section 21C criterion result. Immutable."""

    criterion_result_id: str = ""
    ac_id: str = ""
    result: CriterionVerificationResult = CriterionVerificationResult.FAIL
    severity: FailureSeverity = FailureSeverity.MEDIUM
    verification_method: str = ""
    evidence_refs: Tuple[str, ...] = ()
    failure_class: Optional[VerificationFailureClass] = None
    notes: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "result", _coerce_criterion_result(self.result)
        )
        object.__setattr__(self, "severity", _coerce_severity(self.severity))
        object.__setattr__(
            self, "failure_class", _coerce_failure_class(self.failure_class)
        )
        object.__setattr__(self, "evidence_refs", _as_tuple(self.evidence_refs))


@dataclass(frozen=True)
class VerificationRecord:
    """Manifest section 21C VerificationRecord. Immutable, authoritative."""

    verification_id: str = ""
    verification_sequence: int = 0
    supersedes_verification_id: Optional[str] = None
    project_id: str = ""
    task_id: str = ""
    subtask_id: Optional[str] = None
    run_id: str = ""
    verification_scope_id: str = ""
    verification_target_type: VerificationTargetType = (
        VerificationTargetType.RUN_OUTPUT
    )
    attempt_id: Optional[str] = None
    attempt_ids: Tuple[str, ...] = ()
    artifact_refs: Tuple[str, ...] = ()
    contract_hash: str = ""
    criterion_results: Tuple[CriterionResult, ...] = ()
    result: manifest.VerificationResult = manifest.VerificationResult.FAIL
    handling_disposition: VerificationHandlingDisposition = (
        VerificationHandlingDisposition.FAIL
    )
    failure_class: Optional[VerificationFailureClass] = None
    created_at: str = ""
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    evidence_refs: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "verification_target_type",
            _coerce_target_type(self.verification_target_type),
        )
        object.__setattr__(
            self, "result", _coerce_verification_result(self.result)
        )
        object.__setattr__(
            self, "handling_disposition", _coerce_handling(
                self.handling_disposition)
        )
        object.__setattr__(
            self, "failure_class", _coerce_failure_class(self.failure_class)
        )
        object.__setattr__(self, "attempt_ids", _as_tuple(self.attempt_ids))
        object.__setattr__(
            self, "artifact_refs", _as_tuple(self.artifact_refs)
        )
        object.__setattr__(
            self, "criterion_results", _as_tuple(self.criterion_results)
        )
        object.__setattr__(
            self, "evidence_refs", _as_tuple(self.evidence_refs)
        )


def criterion_effective_result(
    criterion: CriterionResult,
) -> CriterionVerificationResult:
    """Missing evidence ref fails the criterion; never a silent PASS (21C).

    Fail-closed unconditionally: the evidence requirement lives at AC level
    (S13A AcceptanceCriterion.evidence_required), so no per-criterion flag
    duplicates it here; 0C wins on any clash.
    """
    if (
        criterion.result == CriterionVerificationResult.PASS
        and not criterion.evidence_refs
    ):
        return CriterionVerificationResult.FAIL
    return criterion.result


def resolve_latest(
    records: Iterable[VerificationRecord],
) -> Dict[str, VerificationRecord]:
    """Latest record per scope: highest verification_sequence wins (21C)."""
    latest: Dict[str, VerificationRecord] = {}
    for record in records:
        current = latest.get(record.verification_scope_id)
        if current is None or (
            record.verification_sequence > current.verification_sequence
        ):
            latest[record.verification_scope_id] = record
    return latest


def latest_for_scope(
    records: Iterable[VerificationRecord], scope_id: str
) -> Optional[VerificationRecord]:
    """Latest record for one scope, or None when the scope has no record."""
    return resolve_latest(records).get(scope_id)


# --------------------------------------------------------------------------
# canonical disposition (Manifest section 21C)
# --------------------------------------------------------------------------

STATIC_DISPOSITION_MAP: Dict[
    manifest.VerificationResult, VerificationHandlingDisposition
] = {
    manifest.VerificationResult.PASS: VerificationHandlingDisposition.ACCEPT,
    manifest.VerificationResult.FALLBACK: (
        VerificationHandlingDisposition.FALLBACK
    ),
    manifest.VerificationResult.BLOCKED: VerificationHandlingDisposition.BLOCK,
    manifest.VerificationResult.ESCALATE: (
        VerificationHandlingDisposition.ESCALATE
    ),
    manifest.VerificationResult.FAIL: VerificationHandlingDisposition.FAIL,
}
"""Results with a single handling; RETRY/REWORK need the caller's context."""


def canonical_handling(
    result: object,
    *,
    execution_producing: bool = False,
    correction_budget_exhausted: bool = False,
) -> VerificationHandlingDisposition:
    """Map one VerificationResult to exactly one handling path (21C).

    PASS -> ACCEPT; RETRY -> RETRY_VERIFIER, or RETRY_EXECUTION for the
    explicit return-to-execution lifecycle; FALLBACK -> FALLBACK;
    REWORK -> REWORK with budget, else ESCALATE (the result itself is
    preserved by handling_for_record); BLOCKED -> BLOCK;
    ESCALATE -> ESCALATE; FAIL -> FAIL.
    """
    outcome = _coerce_verification_result(result)
    if outcome == manifest.VerificationResult.RETRY:
        if execution_producing:
            return VerificationHandlingDisposition.RETRY_EXECUTION
        return VerificationHandlingDisposition.RETRY_VERIFIER
    if outcome == manifest.VerificationResult.REWORK:
        if correction_budget_exhausted:
            return VerificationHandlingDisposition.ESCALATE
        return VerificationHandlingDisposition.REWORK
    return STATIC_DISPOSITION_MAP[outcome]


def handling_for_record(
    record: VerificationRecord,
    *,
    execution_producing: bool = False,
    correction_budget_exhausted: bool = False,
) -> VerificationHandlingDisposition:
    """Handling for a stored record without rewriting its result (21C).

    REWORK-exhausted keeps result REWORK while handling escalates; the
    caller persists a NEW record, never mutates this one.
    """
    return canonical_handling(
        record.result,
        execution_producing=execution_producing,
        correction_budget_exhausted=correction_budget_exhausted,
    )


# --------------------------------------------------------------------------
# deterministic failure-class paths (Manifest section 17C)
# --------------------------------------------------------------------------

def _coerce_failure_severity(value: object) -> FailureSeverity:
    if isinstance(value, FailureSeverity):
        return value
    return FailureSeverity(str(value))


def failure_class_path(
    failure_class: object,
    severity: object,
    *,
    retry_budget: bool = False,
    correction_budget: bool = False,
    fallback_available: bool = False,
    recoverable: bool = False,
    authority_conflict: bool = False,
    terminal_violation: bool = False,
) -> str:
    """One event -> exactly one path (17C DETERMINISTIC_DISPOSITION).

    INFRA -> VERIFICATION_RETRY if budget else ESCALATE; FORMAT ->
    FORMAT_RETRY / FALLBACK / correction loop for LOW/MEDIUM/HIGH and
    ESCALATE for CRITICAL; CAPABILITY -> FALLBACK / adaptation correction /
    ESCALATE; AC_DEFECT -> correction loop; SECURITY/POLICY -> BLOCKED when
    recoverable, ESCALATE on conflict/authority, FAIL on confirmed terminal
    violation; UNKNOWN -> BLOCKED plus classification. Severity alone never
    selects BLOCKED/ESCALATE.
    """
    klass = _coerce_failure_class(failure_class)
    level = _coerce_failure_severity(severity)
    if klass is None:
        raise ValueError("failure_class is required")
    if klass == VerificationFailureClass.VERIFICATION_INFRA_FAILURE:
        return "VERIFICATION_RETRY" if retry_budget else "ESCALATE"
    if klass == VerificationFailureClass.OUTPUT_FORMAT_FAILURE:
        if level == FailureSeverity.CRITICAL:
            return "ESCALATE"
        if retry_budget:
            return "FORMAT_RETRY"
        if fallback_available:
            return "FALLBACK"
        if correction_budget:
            return "CORRECTION_LOOP"
        return "ESCALATE"
    if klass == VerificationFailureClass.PROVIDER_OR_MODEL_CAPABILITY_FAILURE:
        if fallback_available:
            return "FALLBACK"
        if correction_budget:
            return "CORRECTION_LOOP"
        return "ESCALATE"
    if klass == VerificationFailureClass.IMPLEMENTATION_AC_DEFECT:
        return "CORRECTION_LOOP" if correction_budget else "ESCALATE"
    if klass == VerificationFailureClass.SECURITY_OR_POLICY_FAILURE:
        if terminal_violation:
            return "FAIL"
        if authority_conflict:
            return "ESCALATE"
        if recoverable:
            return "BLOCKED"
        return "ESCALATE"
    return "BLOCKED"


# --------------------------------------------------------------------------
# AttemptExecutionGate (Manifest section 17C)
# --------------------------------------------------------------------------

GATE_CHECK_ORDER: Tuple[str, ...] = (
    "provider_health",
    "model_health",
    "capability_compatibility",
    "security_risk_policy",
    "contract_policy_refs",
    "resource_ownership_capacity",
    "budget_coverage",
    "cancellation_suspension",
    "authorization",
    "routing_fallback_eligibility",
)
"""Frozen check order: the first failing check decides, in this order."""

_CHECK_TO_FAILURE_CLASS: Dict[str, GateFailureClass] = {
    "provider_health": GateFailureClass.HEALTH_FAILURE,
    "model_health": GateFailureClass.HEALTH_FAILURE,
    "capability_compatibility": GateFailureClass.CAPABILITY_UNAVAILABLE,
    "security_risk_policy": GateFailureClass.POLICY_BLOCK,
    "contract_policy_refs": GateFailureClass.POLICY_BLOCK,
    "resource_ownership_capacity": GateFailureClass.RESOURCE_FAILURE,
    "budget_coverage": GateFailureClass.BUDGET_BLOCKED,
    "cancellation_suspension": GateFailureClass.POLICY_BLOCK,
    "authorization": GateFailureClass.POLICY_BLOCK,
    "routing_fallback_eligibility": GateFailureClass.CAPABILITY_UNAVAILABLE,
}

PRE_RUN_FAILURE_DISPOSITION = "PRE_RUN_FAILURE_DISPOSITION"
ATTEMPT_GATE_FAILURE_DISPOSITION = "ATTEMPT_GATE_FAILURE_DISPOSITION"


@dataclass(frozen=True)
class GateDecision:
    """One gate outcome; a failed gate allows no side effect (17C)."""

    allowed: bool
    failed_check: Optional[str] = None
    failure_class: Optional[GateFailureClass] = None
    phase: str = "PROCEED"
    disposition: str = "PROCEED"
    task_effect: str = "NONE"
    run_effect: Optional[str] = None
    side_effects_allowed: bool = True
    detail: str = ""


def _coerce_run_status(value: object) -> manifest.ExecutionRunStatus:
    if isinstance(value, manifest.ExecutionRunStatus):
        return value
    return manifest.ExecutionRunStatus(str(value))


def _class_effect(
    failure_class: GateFailureClass,
    *,
    recoverable: bool,
    fallback_available: bool,
    authority_conflict: bool,
    terminally_unsatisfiable: bool,
    same_run_rereserve: bool,
    pre_run: bool,
) -> Tuple[str, Optional[str], str]:
    """Return (task_effect, run_effect, detail) for one gate failure class."""
    if failure_class == GateFailureClass.BUDGET_BLOCKED:
        if fallback_available:
            return ("FALLBACK", None, "compliant non-billable fallback first")
        if recoverable:
            return ("BLOCKED", None, "recoverable top-up: Task BLOCKED")
        if pre_run:
            return ("ESCALATED", "FAILED/BUDGET_BLOCKED",
                    "no compliant recovery before start")
        return ("FAILED", "FAILED/BUDGET_BLOCKED",
                "RUNNING with no compliant recovery")
    if failure_class == GateFailureClass.RESOURCE_FAILURE:
        if same_run_rereserve:
            return ("SAME_RUN_RETRY", None,
                    "re-reserve only: policy and route unchanged")
        if fallback_available:
            return ("FALLBACK", None, "fallback before terminalization")
        if recoverable:
            return ("BLOCKED", None, "recoverable: Task BLOCKED")
        return ("ESCALATED", "FAILED/RESOURCE_FAILURE",
                "no recovery: run FAILED, Task ESCALATED")
    if failure_class == GateFailureClass.POLICY_BLOCK:
        if terminally_unsatisfiable:
            return ("FAILED", "FAILED/POLICY_BLOCK",
                    "terminally unsatisfiable policy")
        if authority_conflict:
            return ("ESCALATED", None, "authority conflict: Task ESCALATED")
        if recoverable:
            return ("BLOCKED", None, "recoverable auth/dependency: BLOCKED")
        return ("ESCALATED", None, "unresolved policy block: ESCALATED")
    if failure_class == GateFailureClass.CAPABILITY_UNAVAILABLE:
        if fallback_available:
            return ("FALLBACK", None, "fallback first; same-run only when "
                    "the route contract stays valid, else a replacement run")
        return ("ESCALATED", "FAILED/CAPABILITY_UNAVAILABLE",
                "no fallback: run FAILED, Task ESCALATED")
    if fallback_available:
        return ("FALLBACK", None, "health fallback per policy")
    if recoverable:
        return ("BLOCKED", None, "recoverable: Task BLOCKED")
    return ("ESCALATED", None, "no fallback: Task ESCALATED per recoverability")


class AttemptExecutionGate:
    """Frozen gate: EVERY execution-producing attempt passes it first (17C).

    VERIFICATION_ONLY work stays VERIFYING and never reaches this gate
    unless the verifier itself executes billable/external work. A failure
    on CREATED uses PRE_RUN_FAILURE_DISPOSITION; on RUNNING-or-later uses
    ATTEMPT_GATE_FAILURE_DISPOSITION; no side effect follows a failure.
    """

    @staticmethod
    def check(
        check_results: Mapping[str, object],
        *,
        run_status: object,
        recoverable: bool = False,
        fallback_available: bool = False,
        authority_conflict: bool = False,
        terminally_unsatisfiable: bool = False,
        same_run_rereserve: bool = False,
    ) -> GateDecision:
        """Evaluate the frozen checks in frozen order; first failure wins.

        Missing or falsy check results are fail-closed: an unevidenced
        check does not pass. Returns a GateDecision; never raises for a
        failed check.
        """
        status = _coerce_run_status(run_status)
        failed: Optional[str] = None
        for check_id in GATE_CHECK_ORDER:
            if not check_results.get(check_id, False):
                failed = check_id
                break
        if failed is None:
            return GateDecision(allowed=True)
        failure_class = _CHECK_TO_FAILURE_CLASS[failed]
        pre_run = status == manifest.ExecutionRunStatus.CREATED
        task_effect, run_effect, detail = _class_effect(
            failure_class,
            recoverable=recoverable,
            fallback_available=fallback_available,
            authority_conflict=authority_conflict,
            terminally_unsatisfiable=terminally_unsatisfiable,
            same_run_rereserve=same_run_rereserve,
            pre_run=pre_run,
        )
        return GateDecision(
            allowed=False,
            failed_check=failed,
            failure_class=failure_class,
            phase="PRE_RUN" if pre_run else "ATTEMPT",
            disposition=(PRE_RUN_FAILURE_DISPOSITION if pre_run
                         else ATTEMPT_GATE_FAILURE_DISPOSITION),
            task_effect=task_effect,
            run_effect=run_effect,
            side_effects_allowed=False,
            detail=detail,
        )


# --------------------------------------------------------------------------
# retry classes + correction budgets (Manifest section 17C)
# --------------------------------------------------------------------------

def classify_retry(execution_producing: bool) -> RetryKind:
    """VERIFICATION_ONLY vs EXECUTION_PRODUCING retry (17C)."""
    if execution_producing:
        return RetryKind.EXECUTION_PRODUCING_RETRY
    return RetryKind.VERIFICATION_ONLY_RETRY


@dataclass(frozen=True)
class VerificationOnlyEffect:
    """VERIFICATION_ONLY_RETRY: Task+Run stay VERIFYING, no new attempt."""

    task_transition: str = "STAY_VERIFYING"
    new_attempt: bool = False
    increments_correction_count: bool = False


@dataclass(frozen=True)
class ExecutionProducingPlan:
    """EXECUTION_PRODUCING_RETRY lifecycle (17C).

    Task VERIFYING -> REWORK_PENDING (reason EXECUTION_RETRY); run
    VERIFYING -> RUNNING for the policy-allowed same-run retry/fallback;
    a new attempt runs; Task returns to EXECUTING, then Task EXECUTING ->
    VERIFYING with run RUNNING -> VERIFYING on completion. Never
    increments correction_count; a material route/strategy change instead
    uses FALLBACK_REROUTE with a new run.
    """

    task_from: manifest.TaskState = manifest.TaskState.VERIFYING
    task_to: manifest.TaskState = manifest.TaskState.REWORK_PENDING
    task_reason: str = "EXECUTION_RETRY"
    run_from: manifest.ExecutionRunStatus = (
        manifest.ExecutionRunStatus.VERIFYING
    )
    run_to: manifest.ExecutionRunStatus = manifest.ExecutionRunStatus.RUNNING
    new_attempt: bool = True
    increments_correction_count: bool = False
    resume_task_to: manifest.TaskState = manifest.TaskState.EXECUTING


def verification_only_effect() -> VerificationOnlyEffect:
    """Describe the VERIFICATION_ONLY retry effect; mutates nothing."""
    return VerificationOnlyEffect()


def execution_producing_plan() -> ExecutionProducingPlan:
    """Describe the EXECUTION_PRODUCING retry lifecycle; mutates nothing."""
    return ExecutionProducingPlan()


def _coerce_loop_kind(value: object) -> CorrectionLoopKind:
    if isinstance(value, CorrectionLoopKind):
        return value
    return CorrectionLoopKind(str(value))


def correction_allowed(
    kind: object,
    *,
    verification_remaining: int,
    audit_remaining: int,
    runtime_remaining: int,
) -> bool:
    """A verification loop needs verification AND runtime budget; an audit
    loop needs audit AND runtime budget (17C)."""
    loop = _coerce_loop_kind(kind)
    if runtime_remaining <= 0:
        return False
    if loop == CorrectionLoopKind.VERIFICATION_LOOP:
        return verification_remaining > 0
    return audit_remaining > 0


def correction_disposition(
    kind: object,
    *,
    verification_remaining: int,
    audit_remaining: int,
    runtime_remaining: int,
) -> str:
    """PROCEED while the loop's budgets hold, else ESCALATE (17C)."""
    if correction_allowed(
        kind,
        verification_remaining=verification_remaining,
        audit_remaining=audit_remaining,
        runtime_remaining=runtime_remaining,
    ):
        return "PROCEED"
    return "ESCALATE"


def apply_correction_charge(
    kind: object,
    *,
    verification_count: int,
    audit_count: int,
    runtime_count: int,
) -> Tuple[int, int, int]:
    """Charge one correction run: the loop counter plus, always, the
    runtime counter (17C). Returns the new counts; mutates nothing."""
    loop = _coerce_loop_kind(kind)
    if loop == CorrectionLoopKind.VERIFICATION_LOOP:
        return (verification_count + 1, audit_count, runtime_count + 1)
    return (verification_count, audit_count + 1, runtime_count + 1)


__all__ = [
    "VerificationTargetType",
    "CriterionVerificationResult",
    "VerificationHandlingDisposition",
    "VerificationFailureClass",
    "FailureSeverity",
    "GateFailureClass",
    "RetryKind",
    "CorrectionLoopKind",
    "run_output_scope_id",
    "attempt_output_scope_id",
    "multi_attempt_scope_id",
    "artifact_set_scope_id",
    "subtask_output_scope_id",
    "scope_id_for",
    "CriterionResult",
    "VerificationRecord",
    "criterion_effective_result",
    "resolve_latest",
    "latest_for_scope",
    "STATIC_DISPOSITION_MAP",
    "canonical_handling",
    "handling_for_record",
    "failure_class_path",
    "GATE_CHECK_ORDER",
    "PRE_RUN_FAILURE_DISPOSITION",
    "ATTEMPT_GATE_FAILURE_DISPOSITION",
    "GateDecision",
    "AttemptExecutionGate",
    "classify_retry",
    "VerificationOnlyEffect",
    "ExecutionProducingPlan",
    "verification_only_effect",
    "execution_producing_plan",
    "correction_allowed",
    "correction_disposition",
    "apply_correction_charge",
]
