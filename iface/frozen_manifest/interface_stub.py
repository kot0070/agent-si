"""K13 frozen interface stub (Day 0 DRAFT transcription, no logic).

FROZEN: typed transcription of RECORDS/day0/K13_MANIFEST.md (Day 0 DRAFT,
sha256 f256bab4d31be3cd9e86c22a1bdcef90b08ad62500a8eca2051705cc0a9b0690).
Naming authority is RECORDS/day0/0C_ARCHITECTURE.md: 0C wins every clash.

Every public function below carries an ellipsis body and no logic; every
record below is a schema other packages consume. Field/enum/table names
equal the manifest text. Two Python-identifier mappings apply:
``from`` -> ``from_state`` (TransitionRecord: ``from`` is a keyword) and
``re-execution`` -> ``re_execution`` (TelemetryEvent: hyphen is illegal).
Manifest names ride in each field's metadata under ``manifest_name``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, FrozenSet, Iterable, List, Mapping, Optional, Tuple

try:
    from iface.frozen_manifest import manifest
except ImportError:  # alternate layout: the iface/ directory itself on sys.path
    from frozen_manifest import manifest  # type: ignore[no-redef]

MANIFEST_SHA256 = manifest.MANIFEST_SHA256


def verify_manifest(path: Any) -> bool:
    ...


# ---------------------------------------------------------------------------
# Manifest-owned machines, tables and error names (single source: manifest).
# ---------------------------------------------------------------------------

TaskState = manifest.TaskState
AuditResult = manifest.AuditResult
AuditHandlingDisposition = manifest.AuditHandlingDisposition
CompletionDisposition = manifest.CompletionDisposition
ExecutionRunStatus = manifest.ExecutionRunStatus
ExecutionAttemptStatus = manifest.ExecutionAttemptStatus
RunTerminationReason = manifest.RunTerminationReason
AmendmentStatus = manifest.AmendmentStatus
AmendmentScope = manifest.AmendmentScope
EffectiveFrom = manifest.EffectiveFrom
VerificationResult = manifest.VerificationResult
RiskLevel = manifest.RiskLevel
IncidentSeverity = manifest.IncidentSeverity

TASK_TERMINAL = manifest.TASK_TERMINAL
TASK_ALLOWED = manifest.TASK_ALLOWED
TASK_CONDITIONAL_OVERRIDE_EDGES = manifest.TASK_CONDITIONAL_OVERRIDE_EDGES
TASK_DYNAMIC_RESUME_SOURCES = manifest.TASK_DYNAMIC_RESUME_SOURCES
AUDIT_RESULT_TRANSITION_MAP = manifest.AUDIT_RESULT_TRANSITION_MAP
RUN_TERMINAL = manifest.RUN_TERMINAL
RUN_ALLOWED = manifest.RUN_ALLOWED
ATTEMPT_TERMINAL = manifest.ATTEMPT_TERMINAL
ATTEMPT_ALLOWED = manifest.ATTEMPT_ALLOWED

CONTEXT_WRONG_CONTRACT_VERSION = manifest.CONTEXT_WRONG_CONTRACT_VERSION
POLICY_CONFLICT = manifest.POLICY_CONFLICT
CONTEXT_MISSING = manifest.CONTEXT_MISSING

ContextWrongContractVersionError = manifest.ContextWrongContractVersionError
PolicyConflictError = manifest.PolicyConflictError
ContextMissingError = manifest.ContextMissingError

RepositoryPort = manifest.RepositoryPort
CounterStore = manifest.CounterStore

TASK_CONTRACT_FIELDS = manifest.TASK_CONTRACT_FIELDS
CONTRACT_ACTIVATION_FIELDS = manifest.CONTRACT_ACTIVATION_FIELDS
AMENDMENT_FIELDS = manifest.AMENDMENT_FIELDS
TRANSITION_FIELDS = manifest.TRANSITION_FIELDS

RUN_STATUS_TERMINATION_COMPATIBILITY: Dict[Any, FrozenSet[Any]] = {
    ExecutionRunStatus.SUCCEEDED: frozenset({RunTerminationReason.COMPLETED}),
    ExecutionRunStatus.FAILED: frozenset(
        {
            RunTerminationReason.EXECUTION_FAILED,
            RunTerminationReason.VERIFICATION_FAILED,
            RunTerminationReason.AUDIT_FAIL,
            RunTerminationReason.POLICY_BLOCK,
            RunTerminationReason.RESOURCE_FAILURE,
            RunTerminationReason.ROUTING_NO_ELIGIBLE_CANDIDATE,
            RunTerminationReason.CAPABILITY_UNAVAILABLE,
            RunTerminationReason.BUDGET_BLOCKED,
        }
    ),
    ExecutionRunStatus.CANCELLED: frozenset(
        {
            RunTerminationReason.CANCELLED_BY_USER,
            RunTerminationReason.CANCELLED_BY_AMENDMENT,
        }
    ),
    ExecutionRunStatus.SUPERSEDED: frozenset(
        {
            RunTerminationReason.SUPERSEDED_BY_FALLBACK,
            RunTerminationReason.SUPERSEDED_BY_REWORK,
        }
    ),
    ExecutionRunStatus.CREATED: frozenset({RunTerminationReason.NONE}),
    ExecutionRunStatus.RUNNING: frozenset({RunTerminationReason.NONE}),
    ExecutionRunStatus.VERIFYING: frozenset({RunTerminationReason.NONE}),
    ExecutionRunStatus.AUDITING: frozenset({RunTerminationReason.NONE}),
    ExecutionRunStatus.REWORK_REQUIRED: frozenset({RunTerminationReason.NONE}),
}
"""Manifest section 14A RUN_STATUS_TERMINATION_COMPATIBILITY."""

FINALIZATION_MAPPING: Tuple[Tuple[Any, Any, Any], ...] = (
    (TaskState.COMPLETED, AuditResult.PASS, CompletionDisposition.VERIFIED_PASS),
    (TaskState.COMPLETED, None, CompletionDisposition.ACCEPTED_RISK),
    (TaskState.FAILED, None, CompletionDisposition.FAILED),
    (TaskState.CANCELLED, None, CompletionDisposition.CANCELLED),
)
"""Manifest section 21D FINALIZATION_MAPPING (override row needs OverrideRecord)."""


class RestartReason(str, Enum):
    """Manifest section 12 restart/reroute reason (correction count NOT incremented)."""

    AMENDMENT_RESTART = "AMENDMENT_RESTART"
    FALLBACK_REROUTE = "FALLBACK_REROUTE"


class ExecutionRunCreationReason(str, Enum):
    """Manifest section 14 EXECUTION_RUN creation reason."""

    INITIAL_EXECUTION = "INITIAL_EXECUTION"
    VERIFICATION_REWORK = "VERIFICATION_REWORK"
    AUDIT_REWORK = "AUDIT_REWORK"
    AMENDMENT_RESTART = "AMENDMENT_RESTART"
    FALLBACK_REROUTE = "FALLBACK_REROUTE"


class ACType(str, Enum):
    """Manifest section 13A ACCEPTANCE_CRITERION type."""

    DETERMINISTIC = "DETERMINISTIC"
    SEMANTIC = "SEMANTIC"
    SECURITY = "SECURITY"
    ARCHITECTURE = "ARCHITECTURE"
    MANUAL = "MANUAL"


class AttemptType(str, Enum):
    """Manifest section 14B attempt type."""

    INITIAL = "INITIAL"
    RETRY = "RETRY"
    FORMAT_RETRY = "FORMAT_RETRY"
    PROVIDER_RETRY = "PROVIDER_RETRY"
    VERIFICATION_RETRY = "VERIFICATION_RETRY"
    TOOL_RETRY = "TOOL_RETRY"


class ManagerProfileBinding(str, Enum):
    """Manifest section 3B Manager profile binding."""

    DEFAULT = "DEFAULT"
    HARD_LOCK = "HARD_LOCK"


class RoleMode(str, Enum):
    """Manifest section 8 RoleModelProfile mode (0C spelling; ``pool`` is lowercase)."""

    PINNED = "PINNED"
    pool = "pool"
    AUTO = "AUTO"


class VerificationTargetType(str, Enum):
    """Manifest section 21C verification target type."""

    RUN_OUTPUT = "RUN_OUTPUT"
    ATTEMPT_OUTPUT = "ATTEMPT_OUTPUT"
    MULTI_ATTEMPT_OUTPUT = "MULTI_ATTEMPT_OUTPUT"
    ARTIFACT_SET = "ARTIFACT_SET"
    SUBTASK_OUTPUT = "SUBTASK_OUTPUT"


class VerificationHandlingDisposition(str, Enum):
    """Manifest section 21C verification handling disposition."""

    ACCEPT = "ACCEPT"
    RETRY_VERIFIER = "RETRY_VERIFIER"
    RETRY_EXECUTION = "RETRY_EXECUTION"
    FALLBACK = "FALLBACK"
    REWORK = "REWORK"
    BLOCK = "BLOCK"
    ESCALATE = "ESCALATE"
    FAIL = "FAIL"


class CriterionVerificationResult(str, Enum):
    """Manifest section 21C per-criterion result."""

    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class VerificationFailureClass(str, Enum):
    """Manifest section 17C verification failure class."""

    VERIFICATION_INFRA_FAILURE = "VERIFICATION_INFRA_FAILURE"
    OUTPUT_FORMAT_FAILURE = "OUTPUT_FORMAT_FAILURE"
    PROVIDER_OR_MODEL_CAPABILITY_FAILURE = "PROVIDER_OR_MODEL_CAPABILITY_FAILURE"
    IMPLEMENTATION_AC_DEFECT = "IMPLEMENTATION_AC_DEFECT"
    SECURITY_OR_POLICY_FAILURE = "SECURITY_OR_POLICY_FAILURE"
    UNKNOWN_FAILURE = "UNKNOWN_FAILURE"


class FailureSeverity(str, Enum):
    """Manifest section 17C failure severity (never substitutes for RiskLevel)."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class GateFailureClass(str, Enum):
    """Manifest section 17C gate failure classes (first failure wins)."""

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
    """Manifest section 17C correction loop counters."""

    VERIFICATION_LOOP = "VERIFICATION_LOOP"
    AUDIT_LOOP = "AUDIT_LOOP"


class RunSuspensionState(str, Enum):
    """Manifest section 12 suspension runtime state."""

    NONE = "NONE"
    SUSPENDED_BY_TASK = "SUSPENDED_BY_TASK"


class AttemptResultDisposition(str, Enum):
    """Manifest section 12 late attempt result disposition."""

    NORMAL = "NORMAL"
    LATE_AFTER_SUSPENSION = "LATE_AFTER_SUSPENSION"
    QUARANTINED = "QUARANTINED"
    RECONCILED_ACCEPTED = "RECONCILED_ACCEPTED"
    RECONCILED_REJECTED = "RECONCILED_REJECTED"


class LateResultDecision(str, Enum):
    """Manifest section 12 late-result reconciliation decision."""

    ACCEPT_AS_EVIDENCE = "ACCEPT_AS_EVIDENCE"
    REJECT = "REJECT"
    SUPERSEDED = "SUPERSEDED"


class ActionExecutionStatus(str, Enum):
    """Manifest section 19A external-action execution status."""

    CREATED = "CREATED"
    IN_PROGRESS = "IN_PROGRESS"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    UNKNOWN_EXTERNAL_STATE = "UNKNOWN_EXTERNAL_STATE"


class OverrideRecordStatus(str, Enum):
    """Manifest section 18B override record status."""

    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    CANCELLED = "CANCELLED"


class PolicyLifecycleEvent(str, Enum):
    """Manifest section 25A policy lifecycle event (status derived, never stored)."""

    ACTIVATED = "ACTIVATED"
    SUPERSEDED = "SUPERSEDED"
    RETIRED = "RETIRED"


class ReworkCounterType(str, Enum):
    """Manifest section 16 rework counter type."""

    PHASE0_REWORK = "PHASE0_REWORK"
    RUNTIME_REWORK = "RUNTIME_REWORK"
    VERIFICATION_REWORK = "VERIFICATION_REWORK"
    AUDIT_REWORK = "AUDIT_REWORK"


class FallbackCounterScope(str, Enum):
    """Manifest section 16 fallback counter scope."""

    RUN = "RUN"
    TASK = "TASK"


class VerificationRequirement(str, Enum):
    """Manifest section 26A verification requirement."""

    STANDARD = "STANDARD"
    ENHANCED = "ENHANCED"


class AuditRequirement(str, Enum):
    """Manifest section 26A audit requirement (no silent no-audit success path)."""

    REQUIRED_L2 = "REQUIRED_L2"
    REQUIRED_L3 = "REQUIRED_L3"
    REQUIRED_L4_MANUAL = "REQUIRED_L4_MANUAL"


class ResourceLeaseStatus(str, Enum):
    """Manifest section 38 resource lease status."""

    CREATED = "CREATED"
    ACTIVE = "ACTIVE"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"
    ORPHANED = "ORPHANED"


class ResourceReservationStatus(str, Enum):
    """Manifest section 38 resource reservation status."""

    CREATED = "CREATED"
    ACTIVE = "ACTIVE"
    FULFILLED = "FULFILLED"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"
    ORPHANED = "ORPHANED"


class BudgetReservationStatus(str, Enum):
    """Manifest section 27A budget reservation status."""

    CREATED = "CREATED"
    ACTIVE = "ACTIVE"
    SETTLED = "SETTLED"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


class BudgetSettlementStatus(str, Enum):
    """Manifest section 27A budget settlement status."""

    PENDING_RECONCILIATION = "PENDING_RECONCILIATION"
    SETTLED = "SETTLED"
    FAILED = "FAILED"
    VOIDED = "VOIDED"


class RoutingAssignmentStatus(str, Enum):
    """Manifest section 28 routing assignment status."""

    PLANNED = "PLANNED"
    BOUND = "BOUND"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"


class TaskPackageStatus(str, Enum):
    """Manifest section 21A task package status."""

    ACTIVE = "ACTIVE"
    CONSUMED = "CONSUMED"
    INVALIDATED = "INVALIDATED"


class AgentTaskStatus(str, Enum):
    """Manifest section 21A agent task status."""

    ACTIVE = "ACTIVE"
    CONSUMED = "CONSUMED"
    INVALIDATED = "INVALIDATED"


class TaskPlanStatus(str, Enum):
    """Manifest section 21E task plan status."""

    CREATED = "CREATED"
    ACTIVE = "ACTIVE"
    INVALIDATED = "INVALIDATED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class PlannedSubtaskStatus(str, Enum):
    """Manifest section 21E planned subtask status."""

    PLANNED = "PLANNED"
    READY = "READY"
    RUNNING = "RUNNING"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    INVALIDATED = "INVALIDATED"


class PlanCompatibilityResult(str, Enum):
    """Manifest section 21E plan compatibility result."""

    COMPATIBLE = "COMPATIBLE"
    INCOMPATIBLE = "INCOMPATIBLE"


class MetricState(str, Enum):
    """Manifest section 11 metric state."""

    MEASURED = "MEASURED"
    CALCULATED = "CALCULATED"
    ESTIMATED = "ESTIMATED"
    INFERRED = "INFERRED"
    UNAVAILABLE = "UNAVAILABLE"


CONTEXT_VIOLATION_TYPES: Tuple[str, ...] = (
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
)
"""Manifest section 45A frozen context violation types."""

INCIDENT_TYPES: Tuple[str, ...] = (
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
)
"""Manifest section 46 frozen incident types."""

FALLBACK_REASONS: Tuple[str, ...] = (
    "provider_fail",
    "model_fail",
    "timeout",
    "rate_limit",
    "context_overflow",
    "invalid_output",
    "verification_fail",
    "capability_mismatch",
    "context_missing",
    "context_stale",
    "context_conflict",
    "context_truncated",
    "context_wrong_contract",
    "context_recovery_failed",
    "context_summary_drift",
    "provider_capability_mismatch",
    "resource_unavailable",
    "health_failure",
)
"""Manifest section 17 frozen fallback reasons."""


@dataclass(frozen=True)
class Project:
    """Manifest section 8 project model (mutable config; profile/policy change via DecisionRecord)."""

    project_id: str = ""
    name: str = ""
    description: str = ""
    created_at: str = ""
    updated_at: str = ""
    status: str = ""
    workspace_root: str = ""
    default_director: str = ""
    default_manager_provider: str = ""
    default_manager_model: str = ""
    default_policies: Tuple[str, ...] = ()
    budget_config: str = ""
    local_ai_config_ref: str = ""
    capability_db_ref: str = ""
    core_accounting: str = "ALWAYS_ON"
    diagnostic_telemetry_enabled: bool = False
    sdk_tracing_enabled: bool = False
    archived: bool = False


@dataclass(frozen=True)
class RoleModelProfile:
    """Manifest section 8 role model profile (0C-sourced; one row per executable role)."""

    role: str = ""
    project_id: str = ""
    mode: RoleMode = RoleMode.AUTO
    provider: str = ""
    model: str = ""
    binding: ManagerProfileBinding = ManagerProfileBinding.DEFAULT
    version: int = 0
    hash: str = ""


@dataclass(frozen=True)
class DefaultManagerProfile:
    """Manifest section 3B default Manager profile (DEFAULT is not a hard lock)."""

    profile_id: str = "DMP-001"
    version: int = 0
    provider: str = ""
    model: str = ""
    binding: ManagerProfileBinding = ManagerProfileBinding.DEFAULT
    hash: str = ""


@dataclass(frozen=True)
class TaskContract:
    """Manifest section 13 TaskContract (immutable; change = new version + hash)."""

    schema_version: str = ""
    contract_version: int = 0
    contract_sequence: int = 0
    contract_hash: str = ""
    project_id: str = ""
    task_id: str = ""
    parent_task_id: Optional[str] = None
    supersedes_task_id: Optional[str] = None
    phase_id: Optional[str] = None
    created_at: str = ""
    created_by: str = ""
    priority: str = ""
    risk: RiskLevel = RiskLevel.MEDIUM
    goal: str = ""
    requirements: Tuple[str, ...] = ()
    acceptance_criteria: Tuple[str, ...] = ()
    inputs: Tuple[str, ...] = ()
    outputs: Tuple[str, ...] = ()
    workspace: str = ""
    permissions: str = ""
    tools: Tuple[str, ...] = ()
    verification_policy_ref: str = ""
    audit_policy_ref: str = ""
    routing_policy_ref: str = ""
    retry_policy_ref: str = ""
    fallback_policy_ref: str = ""
    optimization_policy_ref: str = ""
    override_policy_ref: str = ""


@dataclass(frozen=True)
class AcceptanceCriterion:
    """Manifest section 13A acceptance criterion (new contract = new criterion set)."""

    ac_id: str = ""
    statement: str = ""
    source: str = ""
    type: ACType = ACType.DETERMINISTIC
    required: bool = False
    severity: FailureSeverity = FailureSeverity.MEDIUM
    verification_method: str = ""
    verifier_ref: str = ""
    evidence_required: bool = False
    pass_condition: str = ""


@dataclass(frozen=True)
class ContractActivationRecord:
    """Manifest section 15 activation record (authoritative; active = highest sequence)."""

    activation_id: str = ""
    project_id: str = ""
    task_id: str = ""
    activation_sequence: int = 0
    contract_version: int = 0
    contract_sequence: int = 0
    contract_hash: str = ""
    previous_contract_hash: Optional[str] = None
    amendment_id: Optional[str] = None
    effective_from: EffectiveFrom = EffectiveFrom.IMMEDIATE
    activation_reason: str = ""
    activated_at: str = ""
    evidence_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Amendment:
    """Manifest section 15 amendment (contract-affecting vs runtime-metadata)."""

    amendment_id: str = ""
    project_id: str = ""
    amendment_sequence: int = 0
    scope: AmendmentScope = AmendmentScope.TASK
    effective_from: EffectiveFrom = EffectiveFrom.NEXT_TASK
    target: str = ""
    change: str = ""
    reason: str = ""
    created_at: str = ""
    source: str = ""
    status: AmendmentStatus = AmendmentStatus.PENDING


@dataclass(frozen=True)
class TransitionRecord:
    """Manifest section 12 transition record (CAS on id + expected version).

    Manifest field ``from`` is exposed as ``from_state`` (``from`` is a
    Python keyword); the manifest name rides in field metadata.
    """

    transition_id: str = ""
    project_id: str = ""
    task_id: str = ""
    run_id: Optional[str] = None
    transition_sequence: int = 0
    expected_from_state: TaskState = TaskState.CREATED
    expected_state_version: int = 0
    new_state_version: int = 0
    actor: str = ""
    from_state: TaskState = field(
        default=TaskState.CREATED, metadata={"manifest_name": "from"}
    )
    to: TaskState = TaskState.CREATED
    reason: str = ""
    timestamp: str = ""
    evidence_ref: str = ""
    suspended_from_state: Optional[TaskState] = None
    resume_target_state: Optional[TaskState] = None


@dataclass(frozen=True)
class ExecutionRun:
    """Manifest section 14 execution run (exactly one contract_hash for life)."""

    run_id: str = ""
    project_id: str = ""
    task_id: str = ""
    contract_hash: str = ""
    run_sequence: int = 0
    revision_no: int = 0
    creation_reason: ExecutionRunCreationReason = ExecutionRunCreationReason.INITIAL_EXECUTION
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
    status: ExecutionRunStatus = ExecutionRunStatus.CREATED
    termination_reason: RunTerminationReason = RunTerminationReason.NONE
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    created_at: str = ""


@dataclass(frozen=True)
class ExecutionAttempt:
    """Manifest section 14B execution attempt (immutable subordinate of one run)."""

    attempt_id: str = ""
    project_id: str = ""
    task_id: str = ""
    run_id: str = ""
    routing_assignment_id: Optional[str] = None
    attempt_no: Optional[int] = None
    run_attempt_sequence: int = 0
    attempt_type: AttemptType = AttemptType.INITIAL
    provider: str = ""
    provider_instance: Optional[str] = None
    model: str = ""
    canonical_provider_id: str = ""
    canonical_model_id: str = ""
    output_artifact_refs: Tuple[str, ...] = ()
    material_contribution: bool = False
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    status: ExecutionAttemptStatus = ExecutionAttemptStatus.CREATED
    error_ref: Optional[str] = None
    usage_ref: Optional[str] = None
    input_ref: Optional[str] = None
    output_ref: Optional[str] = None
    retry_reason: Optional[str] = None
    fallback_reason: Optional[str] = None


@dataclass(frozen=True)
class SuspensionRecord:
    """Manifest section 12 suspension record (authoritative, persistent)."""

    suspension_id: str = ""
    project_id: str = ""
    task_id: str = ""
    run_id: Optional[str] = None
    attempt_id: Optional[str] = None
    source_task_state: Optional[TaskState] = None
    reason: str = ""
    started_at: str = ""
    resolved_at: Optional[str] = None
    run_suspension_state: RunSuspensionState = RunSuspensionState.SUSPENDED_BY_TASK
    late_result_disposition: Optional[AttemptResultDisposition] = None
    evidence_refs: Tuple[str, ...] = ()
    status: str = ""


@dataclass(frozen=True)
class LateResultReconciliationRecord:
    """Manifest section 12 late-result reconciliation (Director/authorized recovery only)."""

    reconciliation_id: str = ""
    project_id: str = ""
    task_id: str = ""
    run_id: str = ""
    attempt_id: str = ""
    suspension_id: str = ""
    late_output_refs: Tuple[str, ...] = ()
    decision: LateResultDecision = LateResultDecision.REJECT
    decided_by: str = ""
    decided_at: str = ""
    reason: str = ""
    verification_ref: Optional[str] = None
    evidence_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class RoutingPolicy:
    """Manifest section 28 routing policy (K13 schema; K04 writer per 0C map)."""

    policy_id: str = ""
    version: int = 1
    created_at: str = ""
    hash: str = ""
    supersedes_policy_ref: Optional[str] = None
    task_class: str = ""
    risk_level: RiskLevel = RiskLevel.MEDIUM
    strict_min: float = 0.0
    tolerant_min: float = 0.0
    confidence_min: float = 0.0
    sample_min: int = 0
    freshness_requirement: str = ""
    local_allowed: bool = False
    split_allowed: bool = False
    cloud_required: bool = False


@dataclass(frozen=True)
class OptimizationPolicy:
    """Manifest section 28 optimization policy (K13 schema; K04 writer per 0C map)."""

    policy_id: str = ""
    version: int = 1
    created_at: str = ""
    hash: str = ""
    supersedes_policy_ref: Optional[str] = None
    required_quality: float = 0.0
    max_risk: RiskLevel = RiskLevel.MEDIUM
    weight_quality: float = 0.0
    weight_cost: float = 0.0
    weight_latency: float = 0.0
    weight_cloud_tokens: float = 0.0
    local_preference: float = 0.0
    deadline: str = ""
    budget_limit: float = 0.0


@dataclass(frozen=True)
class RetryPolicy:
    """Manifest section 16 retry policy (immutable, versioned)."""

    policy_id: str = ""
    version: int = 1
    executor_attempt_max: int = 3
    provider_retry_max: int = 2
    format_retry_max: int = 1
    verification_retry_max: int = 1
    verification_correction_max: int = 2
    audit_correction_max: int = 2
    runtime_correction_max: int = 3
    backoff_policy: str = ""
    created_at: str = ""
    hash: str = ""
    supersedes_policy_ref: Optional[str] = None


@dataclass(frozen=True)
class FallbackPolicy:
    """Manifest section 16 fallback policy (immutable, versioned)."""

    policy_id: str = ""
    version: int = 1
    allowed_reasons: Tuple[str, ...] = ()
    fallback_chain: Tuple[str, ...] = ()
    same_run_rules: str = ""
    new_run_rules: str = ""
    max_fallbacks_per_run: int = 1
    max_fallbacks_per_task: int = 1
    created_at: str = ""
    hash: str = ""
    supersedes_policy_ref: Optional[str] = None


@dataclass(frozen=True)
class VerificationPolicy:
    """Manifest section 26A verification policy (immutable, versioned)."""

    policy_id: str = ""
    version: int = 1
    created_at: str = ""
    hash: str = ""
    requirement: VerificationRequirement = VerificationRequirement.STANDARD
    required_types: Tuple[str, ...] = ()
    retry_policy_ref: str = ""
    evidence_requirements: Tuple[str, ...] = ()
    failure_disposition_policy_ref: str = ""


@dataclass(frozen=True)
class FailureDispositionPolicy:
    """Manifest section 26A failure disposition policy (immutable, versioned)."""

    policy_id: str = ""
    version: int = 1
    created_at: str = ""
    hash: str = ""
    supersedes_policy_ref: Optional[str] = None
    failure_class_rules: Tuple[str, ...] = ()
    severity_rules: Tuple[str, ...] = ()
    retry_policy_ref: str = ""
    fallback_policy_ref: str = ""
    override_policy_ref: str = ""


@dataclass(frozen=True)
class AuditPolicy:
    """Manifest section 26A audit policy (immutable, versioned)."""

    policy_id: str = ""
    version: int = 1
    created_at: str = ""
    hash: str = ""
    audit_requirement: AuditRequirement = AuditRequirement.REQUIRED_L2
    minimum_independence_level: str = ""
    required_context_integrity: str = ""
    retry_policy_ref: str = ""
    override_policy_ref: str = ""
    manual_review_rules: Tuple[str, ...] = ()


@dataclass(frozen=True)
class OverridePolicy:
    """Manifest section 18B override policy (immutable; user-only author/activate/supersede)."""

    policy_id: str = ""
    version: int = 1
    created_at: str = ""
    hash: str = ""
    supersedes_policy_ref: Optional[str] = None
    accepted_risk_allowed: bool = False
    allowed_source_states: Tuple[str, ...] = ()
    non_overridable_failure_classes: Tuple[str, ...] = ()
    non_overridable_ac_types: Tuple[str, ...] = ()
    non_overridable_gate_ids: Tuple[str, ...] = ()
    required_authority: str = ""
    post_override_rules: Tuple[str, ...] = ()
    evidence_requirements: Tuple[str, ...] = ()


@dataclass(frozen=True)
class PolicyLifecycleRecord:
    """Manifest section 25A policy lifecycle record (status derived, never stored)."""

    policy_lifecycle_id: str = ""
    policy_ref: str = ""
    policy_id: str = ""
    policy_version: int = 0
    lifecycle_sequence: int = 0
    event: PolicyLifecycleEvent = PolicyLifecycleEvent.ACTIVATED
    created_at: str = ""
    reason: str = ""
    supersedes_policy_ref: Optional[str] = None


@dataclass(frozen=True)
class ReworkCounterRecord:
    """Manifest section 16 rework counter (authoritative, persistent, atomic)."""

    counter_id: str = ""
    project_id: str = ""
    scope_type: str = ""
    scope_id: str = ""
    counter_type: ReworkCounterType = ReworkCounterType.RUNTIME_REWORK
    value: int = 0
    limit: int = 0
    updated_at: str = ""
    version: int = 0


@dataclass(frozen=True)
class FallbackCounterRecord:
    """Manifest section 16 fallback counter (authoritative, persistent, atomic)."""

    counter_id: str = ""
    project_id: str = ""
    task_id: str = ""
    run_id: Optional[str] = None
    scope_type: FallbackCounterScope = FallbackCounterScope.RUN
    scope_id: str = ""
    value: int = 0
    limit: int = 0
    updated_at: str = ""
    version: int = 0


@dataclass(frozen=True)
class RetryRecord:
    """Manifest section 16 retry record (reason/attempt/failed_AC/evidence/owner + refs)."""

    retry_id: str = ""
    project_id: str = ""
    task_id: str = ""
    run_id: Optional[str] = None
    reason: str = ""
    attempt: int = 0
    failed_AC: Tuple[str, ...] = ()
    evidence_ref: str = ""
    owner: str = ""


@dataclass(frozen=True)
class FallbackRecord:
    """Manifest section 17 fallback record (no blind retry where fallback fits)."""

    fallback_id: str = ""
    project_id: str = ""
    task_id: str = ""
    source_run_id: str = ""
    replacement_run_id: Optional[str] = None
    source_attempt_id: Optional[str] = None
    reason: str = ""
    from_provider: str = ""
    from_model: str = ""
    to_provider: str = ""
    to_model: str = ""
    policy_ref: str = ""
    evidence_ref: str = ""


@dataclass(frozen=True)
class DecisionRecord:
    """Manifest section 21B decision record (nullable task/run for pre-run + Phase-0)."""

    decision_id: str = ""
    project_id: str = ""
    task_id: Optional[str] = None
    run_id: Optional[str] = None
    phase_id: Optional[str] = None
    gate_id: Optional[str] = None
    scope: str = ""
    type: str = ""
    statement: str = ""
    reason: str = ""
    authority: str = ""
    created_at: str = ""
    evidence_refs: Tuple[str, ...] = ()
    supersedes_decision_id: Optional[str] = None
    status: str = ""


@dataclass(frozen=True)
class AuthorizationRecord:
    """Manifest section 19A authorization record (R0 auto; R2 Director; R3 user)."""

    authorization_id: str = ""
    project_id: str = ""
    task_id: str = ""
    run_id: Optional[str] = None
    risk_level: RiskLevel = RiskLevel.LOW
    action: str = ""
    scope: str = ""
    granted_by: str = ""
    granted_at: str = ""
    expires_at: Optional[str] = None
    evidence_ref: str = ""


@dataclass(frozen=True)
class OverrideRecord:
    """Manifest section 18B override record (never rewrites history)."""

    override_id: str = ""
    project_id: str = ""
    task_id: str = ""
    run_id: Optional[str] = None
    created_at: str = ""
    authorized_by: str = ""
    authorization_ref: str = ""
    original_result: Optional[AuditResult] = None
    override_source_state: Optional[TaskState] = None
    override_reason: str = ""
    override_action: str = ""
    accepted_risks: Tuple[str, ...] = ()
    evidence_refs: Tuple[str, ...] = ()
    scope: str = ""
    status: OverrideRecordStatus = OverrideRecordStatus.ACTIVE


@dataclass(frozen=True)
class CriterionResult:
    """Manifest section 21C per-criterion verification result."""

    criterion_result_id: str = ""
    ac_id: str = ""
    result: CriterionVerificationResult = CriterionVerificationResult.FAIL
    severity: FailureSeverity = FailureSeverity.MEDIUM
    verification_method: str = ""
    evidence_refs: Tuple[str, ...] = ()
    failure_class: Optional[VerificationFailureClass] = None
    notes: Optional[str] = None


@dataclass(frozen=True)
class VerificationRecord:
    """Manifest section 21C verification record (immutable, authoritative, persistent)."""

    verification_id: str = ""
    verification_sequence: int = 0
    supersedes_verification_id: Optional[str] = None
    project_id: str = ""
    task_id: str = ""
    subtask_id: Optional[str] = None
    run_id: str = ""
    verification_scope_id: str = ""
    verification_target_type: VerificationTargetType = VerificationTargetType.RUN_OUTPUT
    attempt_id: Optional[str] = None
    attempt_ids: Tuple[str, ...] = ()
    artifact_refs: Tuple[str, ...] = ()
    contract_hash: str = ""
    criterion_results: Tuple[Any, ...] = ()
    result: VerificationResult = VerificationResult.FAIL
    handling_disposition: VerificationHandlingDisposition = (
        VerificationHandlingDisposition.FAIL
    )
    failure_class: Optional[VerificationFailureClass] = None
    created_at: str = ""
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    evidence_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class FinalizationRecord:
    """Manifest section 21D finalization record (assembled from authoritative records only)."""

    finalization_id: str = ""
    project_id: str = ""
    task_id: str = ""
    run_id: Optional[str] = None
    task_state: TaskState = TaskState.CANCELLED
    audit_ref: Any = None
    audit_result: Optional[AuditResult] = None
    completion_disposition: CompletionDisposition = CompletionDisposition.CANCELLED
    override_ref: Optional[OverrideRecord] = None
    verification_ref: Optional[str] = None
    output_refs: Tuple[str, ...] = ()
    metric_refs: Tuple[str, ...] = ()
    completed_at: str = ""
    limitations: Tuple[str, ...] = ()


@dataclass(frozen=True)
class TaskPackage:
    """Manifest section 21A bounded Director->Manager context (seven policy refs gated)."""

    package_id: str = ""
    project_id: str = ""
    task_id: str = ""
    contract_hash: str = ""
    goal: str = ""
    context_refs: Tuple[str, ...] = ()
    input_refs: Tuple[str, ...] = ()
    requirements_ref: str = ""
    acceptance_criteria_refs: Tuple[str, ...] = ()
    workspace: str = ""
    permissions_ref: str = ""
    tools_ref: str = ""
    routing_policy_ref: str = ""
    retry_policy_ref: str = ""
    fallback_policy_ref: str = ""
    optimization_policy_ref: str = ""
    verification_policy_ref: str = ""
    audit_policy_ref: str = ""
    override_policy_ref: str = ""
    created_at: str = ""
    status: TaskPackageStatus = TaskPackageStatus.ACTIVE
    invalidated_at: Optional[str] = None
    invalidation_reason: Optional[str] = None
    superseded_by_ref: Optional[str] = None
    hash: str = ""


@dataclass(frozen=True)
class AgentTask:
    """Manifest section 21A bounded Manager->Agent context."""

    agent_task_id: str = ""
    project_id: str = ""
    task_id: str = ""
    subtask_id: Optional[str] = None
    run_id: str = ""
    agent_id: str = ""
    contract_hash: str = ""
    goal: str = ""
    context_refs: Tuple[str, ...] = ()
    input_refs: Tuple[str, ...] = ()
    acceptance_criteria_refs: Tuple[str, ...] = ()
    workspace: str = ""
    permissions_ref: str = ""
    tools_ref: str = ""
    expected_outputs: Tuple[str, ...] = ()
    created_at: str = ""
    status: AgentTaskStatus = AgentTaskStatus.ACTIVE
    invalidated_at: Optional[str] = None
    invalidation_reason: Optional[str] = None
    superseded_by_ref: Optional[str] = None
    hash: str = ""


@dataclass(frozen=True)
class TaskPlan:
    """Manifest section 21E task plan (authoritative, persistent)."""

    task_plan_id: str = ""
    project_id: str = ""
    task_id: str = ""
    contract_hash: str = ""
    created_at: str = ""
    created_by: str = ""
    status: TaskPlanStatus = TaskPlanStatus.CREATED
    subtask_ids: Tuple[str, ...] = ()
    dependency_edges: Tuple[str, ...] = ()
    evidence_refs: Tuple[str, ...] = ()
    version: int = 0
    hash: str = ""


@dataclass(frozen=True)
class PlannedSubtask:
    """Manifest section 21E planned subtask."""

    subtask_id: str = ""
    task_plan_id: str = ""
    project_id: str = ""
    task_id: str = ""
    parent_subtask_id: Optional[str] = None
    goal: str = ""
    task_class: str = ""
    risk: RiskLevel = RiskLevel.LOW
    required_capabilities: Tuple[str, ...] = ()
    knowledge_needs: Tuple[str, ...] = ()
    tool_needs: Tuple[str, ...] = ()
    acceptance_criteria_refs: Tuple[str, ...] = ()
    dependency_ids: Tuple[str, ...] = ()
    status: PlannedSubtaskStatus = PlannedSubtaskStatus.PLANNED


@dataclass(frozen=True)
class PlanCompatibilityRecord:
    """Manifest section 21E plan compatibility (contract-affecting = INCOMPATIBLE unless proven)."""

    plan_compatibility_id: str = ""
    project_id: str = ""
    task_id: str = ""
    old_contract_hash: str = ""
    new_contract_hash: str = ""
    task_plan_id: str = ""
    result: PlanCompatibilityResult = PlanCompatibilityResult.INCOMPATIBLE
    checked_fields: Tuple[str, ...] = ()
    evidence_refs: Tuple[str, ...] = ()
    created_at: str = ""


@dataclass(frozen=True)
class AuditRecord:
    """Manifest sections 17B/41 audit record (canonical AuditResult verdicts; K03 assurance writer)."""

    ...


@dataclass(frozen=True)
class AuditExecutionRecord:
    """Manifest section 41 audit execution record (K03 assurance writer)."""

    ...


@dataclass(frozen=True)
class ManagerReturn:
    """Manifest section 3A manager return (K02-owned record; referenced here by name only)."""

    ...


@dataclass(frozen=True)
class TelemetryEvent:
    """Manifest section 55 telemetry envelope (NOT a multi-metric record).

    Manifest field ``re-execution`` is exposed as ``re_execution`` (a hyphen
    is illegal in Python); the manifest name rides in field metadata.
    """

    event_id: str = ""
    project_id: str = ""
    timestamp: str = ""
    task_id: Optional[str] = None
    run_id: Optional[str] = None
    attempt_id: Optional[str] = None
    subtask_id: Optional[str] = None
    parent_id: Optional[str] = None
    role: Optional[str] = None
    task_class: Optional[str] = None
    risk: Optional[RiskLevel] = None
    state: Optional[str] = None
    route: Optional[str] = None
    split_strategy: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    provider_instance: Optional[str] = None
    event_type: str = ""
    retry: Optional[str] = None
    verification_ref: Optional[str] = None
    audit_ref: Optional[str] = None
    re_execution: Optional[str] = field(
        default=None, metadata={"manifest_name": "re-execution"}
    )
    error_ref: Optional[str] = None
    fallback_reason: Optional[str] = None
    capability_rule: Optional[str] = None
    capability_evidence_ref: Optional[str] = None
    routing_decision_ref: Optional[str] = None
    routing_snapshot_id: Optional[str] = None
    resource_state_ref: Optional[str] = None
    metric_refs: Tuple[str, ...] = ()
    final_status: Optional[str] = None


@dataclass(frozen=True)
class MetricRecord:
    """Manifest section 11 metric record (value+unit+state+source required at write)."""

    metric_id: str = ""
    project_id: str = ""
    task_id: Optional[str] = None
    run_id: Optional[str] = None
    metric_name: str = ""
    value: float = 0.0
    unit: str = ""
    state: MetricState = MetricState.UNAVAILABLE
    source: str = ""
    recorded_at: str = ""


@dataclass(frozen=True)
class PricingSnapshot:
    """Manifest section 11 pricing snapshot (authoritative when used for cost)."""

    pricing_snapshot_id: str = ""
    provider_id: str = ""
    model_id: str = ""
    currency: str = ""
    effective_at: str = ""
    source: str = ""
    input_token_price: Optional[float] = None
    output_token_price: Optional[float] = None
    cached_token_price: Optional[float] = None
    reasoning_token_price: Optional[float] = None
    request_price: Optional[float] = None
    other_rules: Tuple[str, ...] = ()
    created_at: str = ""
    hash: str = ""


@dataclass(frozen=True)
class SecretRef:
    """Manifest section 20A secret reference (handles travel; raw values never do)."""

    secret_id: str = ""
    provider_id: str = ""
    type: str = ""
    scope: str = ""
    source: str = ""
    created_at: str = ""
    last_rotated_at: str = ""


@dataclass(frozen=True)
class ActionExecution:
    """Manifest section 19A action execution (no blind duplicate of mutations)."""

    action_id: str = ""
    project_id: str = ""
    task_id: str = ""
    run_id: str = ""
    idempotency_key: str = ""
    authorization_ref: str = ""
    attempt: int = 1
    status: ActionExecutionStatus = ActionExecutionStatus.CREATED
    external_ref: Optional[str] = None
    created_at: str = ""
    completed_at: str = ""


@dataclass(frozen=True)
class IncidentRecord:
    """Manifest section 46 incident record (indexes context violations only)."""

    incident_id: str = ""
    project_id: str = ""
    timestamp: str = ""
    task_id: str = ""
    run_id: Optional[str] = None
    actor: str = ""
    detected_by: str = ""
    severity: IncidentSeverity = IncidentSeverity.MEDIUM
    type: str = ""
    description: str = ""
    root_cause: str = ""
    impact: str = ""
    action: str = ""
    regression_test: str = ""
    status: str = ""


@dataclass(frozen=True)
class ContextIntegrityRecord:
    """Manifest section 45A context integrity record (authoritative; mandatory)."""

    context_event_id: str = ""
    incident_ref: Optional[str] = None
    project_id: str = ""
    task_id: str = ""
    run_id: Optional[str] = None
    actor: str = ""
    detected_by: str = ""
    type: str = ""
    severity: IncidentSeverity = IncidentSeverity.MEDIUM
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


@dataclass(frozen=True)
class RoutingAssignment:
    """Manifest section 28 routing assignment (K13 schema; K04 writer per 0C map)."""

    assignment_id: str = ""
    project_id: str = ""
    task_id: str = ""
    run_id: str = ""
    subtask_id: Optional[str] = None
    role: Optional[str] = None
    stage: Optional[str] = None
    route: str = ""
    provider: str = ""
    provider_instance: Optional[str] = None
    model: str = ""
    capability_evidence_refs: Tuple[str, ...] = ()
    resource_state_ref: str = ""
    budget_reservation_ref: Optional[str] = None
    routing_policy_ref: str = ""
    optimization_policy_ref: str = ""
    status: RoutingAssignmentStatus = RoutingAssignmentStatus.PLANNED


@dataclass(frozen=True)
class RoutingEvidenceSnapshot:
    """Manifest section 28 routing evidence snapshot (K13 schema; K04 writer)."""

    routing_snapshot_id: str = ""
    project_id: str = ""
    task_id: str = ""
    run_id: str = ""
    created_at: str = ""
    provider_health_snapshot: str = ""
    model_health_snapshot: str = ""
    resource_state_snapshot: str = ""
    budget_state_snapshot: str = ""
    candidate_snapshot: Tuple[str, ...] = ()
    policy_versions: Tuple[str, ...] = ()
    capability_evidence_refs: Tuple[str, ...] = ()
    hash: str = ""


@dataclass(frozen=True)
class RoutingDecision:
    """Manifest section 28 routing decision (K13 schema, K04 writer; UI reads WHY_THIS_MODEL)."""

    decision_id: str = ""
    project_id: str = ""
    task_id: str = ""
    run_id: str = ""
    routing_snapshot_id: str = ""
    routing_policy_ref: str = ""
    optimization_policy_ref: str = ""
    retry_policy_ref: str = ""
    fallback_policy_ref: str = ""
    verification_policy_ref: str = ""
    audit_policy_ref: str = ""
    override_policy_ref: str = ""
    candidate_models: Tuple[str, ...] = ()
    candidate_providers: Tuple[str, ...] = ()
    selected_provider: Optional[str] = None
    selected_model: Optional[str] = None
    routing_assignment_ids: Tuple[str, ...] = ()
    route: str = ""
    strategy: str = ""
    reason: str = ""
    eligibility_source: str = ""
    capability_state: str = ""
    required_verification: str = ""
    eligibility_branch_evidence_refs: Tuple[str, ...] = ()
    capability_evidence_refs: Tuple[str, ...] = ()
    provider_health_ref: str = ""
    model_health_ref: str = ""
    resource_state_ref: str = ""
    risk_override: str = ""
    estimated_cost: float = 0.0
    estimated_latency: float = 0.0
    optimization_score: float = 0.0
    fallback_chain: Tuple[str, ...] = ()


@dataclass(frozen=True)
class BudgetState:
    """Manifest section 27A budget state (remaining_derived recomputed, never truth)."""

    project_id: str = ""
    currency: str = ""
    budget_limit: float = 0.0
    soft_limit: float = 0.0
    hard_limit: float = 0.0
    spent: float = 0.0
    reserved: float = 0.0
    remaining_derived: float = 0.0
    updated_at: str = ""


@dataclass(frozen=True)
class BudgetReservation:
    """Manifest section 27A budget reservation (K13 schema; K04 code per 0C map)."""

    reservation_id: str = ""
    project_id: str = ""
    task_id: str = ""
    run_id: str = ""
    estimated_amount: float = 0.0
    reserved_at: str = ""
    expires_at: str = ""
    status: BudgetReservationStatus = BudgetReservationStatus.CREATED


@dataclass(frozen=True)
class BudgetSettlement:
    """Manifest section 27A budget settlement (K13 schema; K04 code per 0C map)."""

    settlement_id: str = ""
    reservation_id: str = ""
    provider_usage_evidence_ref: Optional[str] = None
    provider_request_ref: str = ""
    dedupe_key: str = ""
    actual_amount: Optional[float] = None
    difference: Optional[float] = None
    status: BudgetSettlementStatus = BudgetSettlementStatus.PENDING_RECONCILIATION
    settled_at: Optional[str] = None
    source: str = ""


@dataclass(frozen=True)
class ResourceLease:
    """Manifest section 38 resource lease (authoritative, persistent)."""

    lease_id: str = ""
    project_id: str = ""
    task_id: str = ""
    run_id: str = ""
    resource_type: str = ""
    resource_id: str = ""
    owner_run_id: str = ""
    acquired_at: float = 0.0
    expires_at: float = 0.0
    released_at: Optional[float] = None
    status: ResourceLeaseStatus = ResourceLeaseStatus.CREATED
    capacity_claim: int = 0
    evidence_ref: str = ""


@dataclass(frozen=True)
class ResourceReservation:
    """Manifest section 38 resource reservation (authoritative, persistent)."""

    reservation_id: str = ""
    project_id: str = ""
    task_id: str = ""
    run_id: str = ""
    resource_type: str = ""
    resource_id: Optional[str] = None
    owner_run_id: str = ""
    requested_capacity: int = 0
    created_at: float = 0.0
    expires_at: float = 0.0
    fulfilled_at: Optional[float] = None
    released_at: Optional[float] = None
    status: ResourceReservationStatus = ResourceReservationStatus.CREATED
    evidence_ref: str = ""


@dataclass(frozen=True)
class ResourceStateSnapshot:
    """Manifest section 38 resource state snapshot (precheck output; replay history)."""

    resource_state_snapshot_id: str = ""
    project_id: str = ""
    task_id: str = ""
    run_id: str = ""
    created_at: float = 0.0
    available_gpu_slots: int = 0
    available_cpu_slots: int = 0
    memory_available: int = 0
    gpu_memory_available: int = 0
    queue_depth: int = 0
    provider_capacity_refs: Tuple[str, ...] = ()
    hash: str = ""


@dataclass(frozen=True)
class SchedulerConfig:
    """Manifest section 38 scheduler config (max_*_global/per-provider/per-model + pools + policies)."""

    max_parallel_global: int = 0
    max_parallel_per_provider: int = 0
    max_parallel_per_model: int = 0
    local_gpu_slots: int = 0
    local_cpu_slots: int = 0
    memory_budget: int = 0
    gpu_memory_budget: int = 0
    queue_policy: str = ""
    priority_policy: str = ""


@dataclass(frozen=True)
class ArtifactRef:
    """Manifest section 40 artifact reference (beats repeated inline content)."""

    artifact_id: str = ""
    path: str = ""
    version: int = 0
    hash: str = ""
    hash_algorithm: str = ""
    media_type: str = ""
    size: int = 0
    created_at: str = ""
    source: str = ""
    owner: str = ""
    read_scope: str = ""
    range: str = ""
    trust_level: str = ""
    provenance_ref: str = ""


@dataclass(frozen=True)
class GovernanceArtifact:
    """Manifest section 21 governance artifact (hash-pinned record refs)."""

    artifact_id: str = ""
    version: int = 0
    phase0_work_id: Optional[str] = None
    hash: str = ""
    hash_algorithm: str = ""
    created_at: str = ""
    approved_by: str = ""
    source: str = ""


@dataclass(frozen=True)
class SdkTracingPolicy:
    """Manifest section 42A SDK tracing privacy policy (default DISABLED per 0C)."""

    enabled: bool = False
    destination: str = "local-processor"
    data_classification: str = "private"
    redaction_required: bool = True
    allow_model_input: bool = False
    allow_model_output: bool = False
    allow_tool_arguments: bool = False
    allow_tool_results: bool = False
    allow_file_content: bool = False
    retention_policy: str = "local-only"
    external_export_allowed: bool = False
    project_scope: str = ""


@dataclass(frozen=True)
class TurnRequest:
    """Manifest section 43 orchestration turn request (single engine entry)."""

    project_id: str = ""
    task_id: str = ""
    run_id: str = ""
    contract_hash: str = ""
    input_ref: str = ""
    tool_results: Tuple[Any, ...] = ()
    secret_refs: Tuple[Any, ...] = ()
    run_config: Any = None


@dataclass(frozen=True)
class TurnResult:
    """Manifest section 43 orchestration turn result."""

    run_id: str = ""
    output_ref: str = ""
    executed: bool = False
    approval_requested: bool = False
    treated_as_data: bool = False
    authorization_ref: Any = None
    reason: str = ""


@dataclass(frozen=True)
class SdkRunResult:
    """Manifest section 43 SDK run result (carries output_ref; runner retries only from RunConfig)."""

    run_id: str = ""
    output_ref: str = ""
    provider: str = ""
    model: str = ""
    status: ExecutionAttemptStatus = ExecutionAttemptStatus.SUCCEEDED
    error_ref: str = ""


@dataclass(frozen=True)
class RoutingDecisionBinding:
    """Manifest section 28 routing decision fields this adapter consumes."""

    decision_id: str = ""
    project_id: str = ""
    task_id: str = ""
    run_id: str = ""
    routing_snapshot_id: str = ""
    selected_provider: str = ""
    selected_model: str = ""
    route: str = ""
    strategy: str = ""
    reason: str = ""


@dataclass(frozen=True)
class RunConfig:
    """Manifest section 14B runner configuration bound to exactly one RoutingDecision."""

    decision_id: str = ""
    project_id: str = ""
    task_id: str = ""
    run_id: str = ""
    selected_provider: str = ""
    selected_model: str = ""
    route: str = ""
    strategy: str = ""
    max_runner_retries: int = 0


@dataclass(frozen=True)
class Phase0WorkRecord:
    """Manifest sections 41/45 phase-0 work record (recovery input; authoritatively stored)."""

    ...


@dataclass(frozen=True)
class CapabilityEvidence:
    """Manifest section 41 capability evidence (base is optional evidence, never the only path)."""

    ...


@dataclass(frozen=True)
class ProviderContract:
    """Manifest section 41 provider contract (authoritative domain record)."""

    ...


@dataclass(frozen=True)
class ModelContract:
    """Manifest section 41 model contract (authoritative domain record)."""

    ...


@dataclass(frozen=True)
class UsageReportingCapability:
    """Manifest sections 41/51 provider usage-reporting capability (authoritative record)."""

    ...


@dataclass(frozen=True)
class CancellableAttempt:
    """Manifest section 45B cancellable attempt (active attempts go to CANCELLED)."""

    attempt_id: str = ""
    run_id: str = ""
    status: ExecutionAttemptStatus = ExecutionAttemptStatus.RUNNING


@dataclass(frozen=True)
class FinalizedPartialUsage:
    """Manifest section 45B finalized partial usage (measurable stays authoritative)."""

    run_id: str = ""
    measured: Tuple[Tuple[str, float], ...] = ()
    unmeasurable: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ReleaseDirective:
    """Manifest section 45B release directive (leases/reservations released deterministically)."""

    kind: str = ""
    ref: str = ""
    action: str = "release"


@dataclass(frozen=True)
class RunCancellation:
    """Manifest section 45B run cancellation (history kept; reason from RunTerminationReason only)."""

    run_id: str = ""
    reason: RunTerminationReason = RunTerminationReason.CANCELLED_BY_USER
    from_status: ExecutionRunStatus = ExecutionRunStatus.RUNNING
    to_status: ExecutionRunStatus = ExecutionRunStatus.CANCELLED
    attempts: Tuple[CancellableAttempt, ...] = ()
    usage: Optional[FinalizedPartialUsage] = None
    releases: Tuple[ReleaseDirective, ...] = ()
    audit_refs: Tuple[str, ...] = ()
    verification_refs: Tuple[str, ...] = ()
    history_kept: bool = True


REPORT_DATASET_KEYS: Tuple[str, ...] = (
    "PROJECT",
    "GOAL",
    "SCOPE",
    "ARCH",
    "PHASES",
    "TASKS",
    "RUNS",
    "MANAGERS",
    "AGENTS",
    "MODELS",
    "PROVIDERS",
    "ROUTES",
    "SPLIT_STRATEGIES",
    "ROUTING_DECISIONS",
    "FALLBACKS",
    "TIME",
    "TOKENS",
    "COST",
    "LOCAL_CALLS",
    "CLOUD_CALLS",
    "RETRIES",
    "REWORKS",
    "FAILURES",
    "INCIDENTS",
    "DEVIATIONS",
    "AMENDMENTS",
    "SECURITY",
    "TESTS",
    "AUDITS",
    "LIMITATIONS",
    "RISKS",
    "CONTEXT_INTEGRITY",
    "CONTEXT_VIOLATIONS",
    "BUDGET",
    "SDK_TRACING_POLICY",
    "USAGE_REPORTING_CAPABILITY",
    "FINAL_STATUS",
)
"""Manifest section 59 frozen report dataset key set, in manifest order."""


# ---------------------------------------------------------------------------
# Typed public signatures (ellipsis bodies, no logic).
# ---------------------------------------------------------------------------

def is_task_transition_allowed(
    from_state: Any, to_state: Any, override: bool = False
) -> bool:
    ...


def is_run_transition_allowed(from_status: Any, to_status: Any) -> bool:
    ...


def is_attempt_transition_allowed(from_status: Any, to_status: Any) -> bool:
    ...


def compute_contract_hash(contract: Any) -> str:
    ...


def activate(
    contract: TaskContract,
    activation_id: str,
    activation_sequence: int,
    activation_reason: str,
    effective_from: Any = ...,
    amendment_id: Optional[str] = ...,
    previous_contract_hash: Optional[str] = ...,
    activated_at: str = ...,
    evidence_refs: Iterable[str] = ...,
) -> ContractActivationRecord:
    ...


def resolve_active(
    activations: Iterable[ContractActivationRecord],
) -> Optional[ContractActivationRecord]:
    ...


def replace_with_new_version(old: TaskContract, **changes: Any) -> TaskContract:
    ...


def order_amendments(amendments: Iterable[Amendment]) -> List[Amendment]:
    ...


def classify(change: Any, contract_fields: Iterable[str] = ...) -> str:
    ...


def apply_terminal_task_rule(task_state: Any, effective_from: Any) -> str:
    ...


def apply_immediate_effect(
    amendment: Amendment,
    task_state: Any,
    active_run_id: Optional[str] = ...,
    active_run_status: Any = ...,
) -> List[Any]:
    ...


def increments_correction_count(reason: Any) -> bool:
    ...


def create_run(
    run_id: str,
    project_id: str,
    task_id: str,
    contract_hash: str,
    run_sequence: int,
    existing_sequences: Iterable[int] = ...,
    creation_reason: str = ...,
    source_run: Optional[ExecutionRun] = ...,
    created_at: str = ...,
) -> ExecutionRun:
    ...


def bind_routing_fields(
    run: ExecutionRun, *, routing_decision_ref: str, route: str
) -> ExecutionRun:
    ...


def transition_run(
    run: ExecutionRun,
    expected_status: Any,
    expected_version: int,
    to_status: Any,
    termination_reason: Any,
    at: str = ...,
) -> ExecutionRun:
    ...


def start_run(
    run: ExecutionRun, state: Any, expected_version: int, started_at: str = ...
) -> ExecutionRun:
    ...


def is_termination_compatible(status: Any, reason: Any) -> bool:
    ...


def allocate_run_sequence(existing_sequences: Iterable[int]) -> int:
    ...


def apply_pre_run_disposition(
    run: ExecutionRun,
    cause: Any,
    recoverable: bool = ...,
    conflict: bool = ...,
    terminally_unsatisfiable: bool = ...,
    correction_staging: bool = ...,
    replacement_run_id: Optional[str] = ...,
) -> Any:
    ...


def apply_audit_disposition(run: ExecutionRun, result: Any) -> Any:
    ...


def is_transition_allowed(fr: Any, to: Any) -> bool:
    ...


def transition_attempt(attempt: ExecutionAttempt, to_status: Any) -> ExecutionAttempt:
    ...


def check_compatible(attempt: ExecutionAttempt) -> None:
    ...


def commit_decision(
    records: Iterable[DecisionRecord],
    expected_version: int,
    record: DecisionRecord,
) -> DecisionRecord:
    ...


def order_decisions(records: Iterable[DecisionRecord]) -> List[DecisionRecord]:
    ...


def resolve_latest(records: Iterable[Any]) -> Optional[Any]:
    ...


def replace_decision(old: DecisionRecord, **changes: Any) -> DecisionRecord:
    ...


def tier_of(record: AuthorizationRecord) -> str:
    ...


def request_high_risk_approval(
    store: Any,
    *,
    authorization_id: str,
    project_id: str,
    task_id: str,
    action: str,
    scope: str,
    granted_by: str,
) -> AuthorizationRecord:
    ...


def compute_policy_hash(policy: Any) -> str:
    ...


def new_policy_version(old: Any, **changes: Any) -> Any:
    ...


def derive_policy_status(records: Iterable[PolicyLifecycleRecord]) -> Optional[str]:
    ...


def enforce_policy_identity(
    contract_refs: Mapping[str, str],
    nested_refs: Mapping[str, str],
    delegations: Iterable[str] = ...,
) -> None:
    ...


def default_retry_policy() -> RetryPolicy:
    ...


def bump_rework(record: ReworkCounterRecord, store: Any) -> ReworkCounterRecord:
    ...


def bump_fallback(
    record: FallbackCounterRecord, store: Any
) -> FallbackCounterRecord:
    ...


def is_exhausted(record: Any, policy: RetryPolicy) -> bool:
    ...


def resolve_exhaustion(exhausted_class: str) -> AuditHandlingDisposition:
    ...


def disposition_after_exhaustion(record: Any) -> str:
    ...


def run_output_scope_id(task_id: Any, run_id: Any, contract_hash: Any) -> str:
    ...


def attempt_output_scope_id(task_id: Any, run_id: Any, attempt_id: Any) -> str:
    ...


def multi_attempt_scope_id(attempt_ids: Iterable[Any]) -> str:
    ...


def artifact_set_scope_id(artifact_refs: Iterable[Any]) -> str:
    ...


def subtask_output_scope_id(task_id: Any, subtask_id: Any) -> str:
    ...


def scope_id_for(target_type: Any) -> str:
    ...


def criterion_effective_result(criterion: CriterionResult) -> Any:
    ...


def latest_for_scope(records: Iterable[VerificationRecord], scope_id: str) -> Any:
    ...


def canonical_handling(
    result: Any,
    execution_producing: bool = ...,
    correction_budget_exhausted: bool = ...,
) -> VerificationHandlingDisposition:
    ...


def handling_for_record(
    record: VerificationRecord,
    execution_producing: bool = ...,
    correction_budget_exhausted: bool = ...,
) -> Any:
    ...


def failure_class_path(
    failure_class: Any,
    severity: Any,
    retry_budget: bool = ...,
    correction_budget: bool = ...,
    fallback_available: bool = ...,
    recoverable: bool = ...,
    authority_conflict: bool = ...,
    terminal_violation: bool = ...,
) -> Any:
    ...


def correction_allowed(
    kind: Any,
    verification_remaining: int,
    audit_remaining: int,
    runtime_remaining: int,
) -> bool:
    ...


def correction_disposition(
    kind: Any,
    verification_remaining: int,
    audit_remaining: int,
    runtime_remaining: int,
) -> Any:
    ...


def apply_correction_charge(
    kind: Any, verification_count: int, audit_count: int, runtime_count: int
) -> Any:
    ...


def classify_retry(execution_producing: bool) -> RetryKind:
    ...


def completion_disposition_for(
    task_state: Any,
    audit_result: Any = ...,
    override: Optional[OverrideRecord] = ...,
) -> CompletionDisposition:
    ...


def contains_raw_secret(value: Any, secrets: Iterable[str]) -> bool:
    ...


def redact(value: Any, secrets: Iterable[str]) -> Any:
    ...


def filter_export_dataset(dataset: Mapping[str, Any]) -> Dict[str, Any]:
    ...


def export_event(event: TelemetryEvent, secrets: Iterable[str] = ...) -> Dict[str, Any]:
    ...


def active_wall_time(intervals: Iterable[Tuple[float, float]]) -> float:
    ...


def derive_idempotency_key(
    project_id: str,
    task_id: str,
    action: str,
    payload_hash: str,
    contract_hash: str = ...,
) -> str:
    ...


def index_context_violation(
    truth: ContextIntegrityRecord,
    incident_id: str,
    type: str,
    timestamp: str = ...,
    description: str = ...,
    root_cause: str = ...,
    impact: str = ...,
    action: str = ...,
    regression_test: str = ...,
    status: str = ...,
) -> IncidentRecord:
    ...


def link_incident(
    truth: ContextIntegrityRecord, incident_id: str
) -> IncidentRecord:
    ...


def check_index_linkage(index: IncidentRecord, truth: ContextIntegrityRecord) -> bool:
    ...


def is_cancellation_reason(reason: Any) -> bool:
    ...


def validate_cancellation_reason(reason: Any) -> RunTerminationReason:
    ...


def cancel_attempt(attempt: Any, reason: Any) -> Any:
    ...


def cancel_attempts(
    attempts: Iterable[Any], run_id: str, reason: Any
) -> Any:
    ...


def finalize_partial_usage(
    run_id: str,
    measured: Optional[Mapping[str, Any]] = ...,
    unmeasurable: Iterable[str] = ...,
) -> Any:
    ...


def release_all(
    reservation_ids: Iterable[str] = ..., lease_ids: Iterable[str] = ...
) -> Any:
    ...


def finalize_cancellation(
    run_id: str,
    reason: Any,
    from_status: Any = ...,
    attempts: Iterable[Any] = ...,
    measured_usage: Optional[Mapping[str, Any]] = ...,
    unmeasurable_usage: Iterable[str] = ...,
    reservation_ids: Iterable[str] = ...,
    lease_ids: Iterable[str] = ...,
    audit_refs: Iterable[str] = ...,
    verification_refs: Iterable[str] = ...,
) -> Any:
    ...


def run_scope(run_id: str) -> str:
    ...


def task_scope(task_id: str) -> str:
    ...


def budget_blocked(
    spent: float,
    reserved: float,
    hard_limit: float,
    requested: float,
    override_ref: Optional[str] = ...,
) -> Any:
    ...


def transport_for_provider(provider: str) -> str:
    ...


def revalidate_agent_builder_workflow(workflow: Any, *, expected_hash: str) -> Any:
    ...


def is_hosted_export_permitted(
    policy: SdkTracingPolicy,
    authorization_ref: Any = ...,
    export_key_ref: Any = ...,
    run_has_secrets: bool = ...,
    secrets_export_authorized: bool = ...,
) -> bool:
    ...


def app_telemetry_requires_tracing() -> bool:
    ...


def context_recovery_check(
    expected_contract_hash: str,
    recovered_contract_hash: str,
    required_refs_available: bool,
    unresolved_context_incidents_loaded: bool,
    latest_amendments_loaded: bool,
    active_run_consistent: bool,
) -> bool:
    ...


class GateDecision:
    """Manifest section 17C gate decision (fail-closed; first failure wins)."""

    allowed: bool
    failed_check: Optional[str]
    failure_class: Optional[GateFailureClass]
    phase: str
    disposition: str
    task_effect: str
    run_effect: Optional[str]
    side_effects_allowed: bool
    detail: str

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        ...


class AttemptExecutionGate:
    """Manifest section 17C execution gate (frozen check order; fail-closed)."""

    @staticmethod
    def check(
        check_results: Mapping[str, Any],
        *,
        run_status: Any,
        recoverable: bool = ...,
        fallback_available: bool = ...,
        authority_conflict: bool = ...,
        terminally_unsatisfiable: bool = ...,
        same_run_rereserve: bool = ...,
    ) -> GateDecision:
        ...


class VerificationOnlyEffect:
    """Manifest section 17C verifier/check only effect (stays VERIFYING)."""

    task_transition: str
    new_attempt: bool
    increments_correction_count: bool

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        ...


class ExecutionProducingPlan:
    """Manifest section 17C explicit return-to-execution plan."""

    task_from: TaskState
    task_to: TaskState
    task_reason: str
    run_from: ExecutionRunStatus
    run_to: ExecutionRunStatus
    new_attempt: bool
    increments_correction_count: bool
    resume_task_to: TaskState

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        ...


def verification_only_effect() -> VerificationOnlyEffect:
    ...


def execution_producing_plan() -> ExecutionProducingPlan:
    ...


class QuarantineStore:
    """Manifest section 12 suspension/quarantine store (authoritative, persistent)."""

    def open_suspension(
        self,
        *,
        suspension_id: str,
        project_id: str,
        task_id: str,
        run_id: Optional[str] = ...,
        attempt_id: Optional[str] = ...,
        source_task_state: Any = ...,
        reason: str = ...,
        started_at: str = ...,
        evidence_refs: Tuple[str, ...] = ...,
    ) -> SuspensionRecord:
        ...

    def active_suspension_for(self, task_id: str) -> Optional[SuspensionRecord]:
        ...

    def is_halted(self, task_id: str) -> bool:
        ...

    def report_late_result(
        self,
        *,
        project_id: str,
        task_id: str,
        run_id: str,
        attempt_id: str,
        output_refs: Tuple[str, ...] = ...,
        contract_hash: str = ...,
        quarantined_at: str = ...,
        suspension_id: Optional[str] = ...,
    ) -> Any:
        ...

    def note_committed_output(self, ref: str) -> None:
        ...

    @property
    def committed_outputs(self) -> Tuple[str, ...]:
        ...


class AuthorizationStore:
    """Manifest section 19A authorization store (R2/R3 records persist before use)."""

    def append(self, record: AuthorizationRecord) -> AuthorizationRecord:
        ...

    def list_by(self, authorization_id: str) -> List[AuthorizationRecord]:
        ...


class Finalizer:
    """Manifest section 21D finalizer (assembles outcome from authoritative records only)."""

    @staticmethod
    def finalize(
        *,
        finalization_id: str = ...,
        project_id: str,
        task_id: str,
        run_id: Optional[str] = ...,
        task_state: Any,
        audit_result: Any = ...,
        audit_ref: Any = ...,
        verification_ref: Optional[str] = ...,
        override: Optional[OverrideRecord] = ...,
        output_refs: Tuple[str, ...] = ...,
        metric_refs: Tuple[str, ...] = ...,
        accounting_complete: bool = ...,
        budget_settled: bool = ...,
        resources_released: bool = ...,
        limitations: Tuple[str, ...] = ...,
        completed_at: str = ...,
    ) -> FinalizationRecord:
        ...


class TelemetryEventLog:
    """Manifest section 55 append-only envelope store (duplicate id returns stored)."""

    def append(
        self, event: TelemetryEvent, known_secrets: Iterable[str] = ...
    ) -> TelemetryEvent:
        ...

    def load(self, event_id: str) -> Optional[TelemetryEvent]:
        ...

    def list_by_project(self, project_id: str) -> List[TelemetryEvent]:
        ...


class MetricRecordLog:
    """Manifest section 11 append-only metric store."""

    def append(self, record: MetricRecord) -> MetricRecord:
        ...

    def load(self, metric_id: str) -> Optional[MetricRecord]:
        ...

    def list_by_project(self, project_id: str) -> List[MetricRecord]:
        ...


class CostCalculator:
    """Manifest section 11 cost calculator (cost only via PricingSnapshot)."""

    @staticmethod
    def calculate(
        usage: Any,
        snapshot: Optional[PricingSnapshot],
        *,
        metric_id: str,
        project_id: str,
        task_id: Optional[str] = ...,
        run_id: Optional[str] = ...,
        recorded_at: str = ...,
        source: str = ...,
    ) -> MetricRecord:
        ...


class ActionLog:
    """Manifest section 19A action log (persist + verify prior external state)."""

    def register(self, execution: ActionExecution) -> ActionExecution:
        ...

    def lookup(self, idempotency_key: str) -> Optional[ActionExecution]:
        ...

    def begin(self, idempotency_key: str) -> ActionExecution:
        ...


class LeaseRequest:
    """Manifest section 38 lease request (reserve inputs)."""

    project_id: str
    task_id: str
    run_id: str
    resource_type: str
    requested_capacity: int
    resource_id: Optional[str]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        ...


class PrecheckOutcome:
    """Manifest section 38 precheck outcome (read-only; never reserves)."""

    eligible: bool
    snapshot: ResourceStateSnapshot
    queue_position: Optional[int]
    available_capacity: int

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        ...


class ReserveOutcome:
    """Manifest section 38 reserve outcome (lease/reservation or queued)."""

    kind: str
    lease: Optional[ResourceLease]
    reservation: Optional[ResourceReservation]
    queue_position: Optional[int]
    estimated_start: Optional[float]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        ...


class LeaseStore:
    """Manifest section 38 lease registry (precheck -> reserve; reconcile on restart)."""

    def precheck(self, request: LeaseRequest, now: float) -> PrecheckOutcome:
        ...

    def reserve(self, request: LeaseRequest, now: float) -> ReserveOutcome:
        ...

    def promote(self, now: float) -> List[ReserveOutcome]:
        ...

    def release(self, lease_id: str, now: float) -> ResourceLease:
        ...

    def fulfill(
        self, reservation_id: str, now: float
    ) -> ResourceReservation:
        ...

    def expire_due(self, now: float) -> Tuple[str, ...]:
        ...

    def get_lease(self, lease_id: str) -> ResourceLease:
        ...

    def get_reservation(self, reservation_id: str) -> ResourceReservation:
        ...


class SchedulingRequest:
    """Manifest section 38 scheduling request (precheck inputs + budget coverage)."""

    project_id: str
    task_id: str
    run_id: str
    resource_type: str
    requested_capacity: int
    spent: float
    reserved: float
    hard_limit: float
    requested_amount: float
    override_ref: Optional[str]
    now: float

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        ...


class SchedulingResult:
    """Manifest section 38 scheduling result (phases + lease/reservation refs)."""

    run_id: str
    status: str
    phases: Tuple[str, ...]
    lease_id: Optional[str]
    lease: Optional[ResourceLease]
    reservation: Optional[ResourceReservation]
    budget_reservation_ref: Optional[str]
    queue_position: Optional[int]
    estimated_start: Optional[float]
    run_status: Any
    attempt_status: Any
    compensated: bool
    blocked_reason: Optional[str]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        ...


class ResourceScheduler:
    """Manifest section 38 execution gating (precheck -> RoutingDecision -> reserve -> gate)."""

    def submit(self, request: SchedulingRequest) -> SchedulingResult:
        ...

    def compensate(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def recover(self, *args: Any, **kwargs: Any) -> Any:
        ...


class OrchestrationInterface:
    """Manifest section 43 orchestration interface (single engine entry run_turn)."""

    def run_turn(self, request: TurnRequest) -> TurnResult:
        ...


class OpenAIAgentsSDKAdapter:
    """Manifest section 43 SDK adapter (SDK calls only; client max_retries=0)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        ...

    def build_run_config(
        self, decision: RoutingDecisionBinding, *, executor_attempt_max: int
    ) -> RunConfig:
        ...

    def run(
        self,
        *,
        run_config: RunConfig,
        input_ref: str,
        secret_refs: Tuple[SecretRef, ...] = ...,
    ) -> SdkRunResult:
        ...

    def execute_builder_workflow(
        self,
        workflow: Any,
        *,
        run_config: RunConfig,
        input_ref: str,
        secret_refs: Tuple[SecretRef, ...] = ...,
    ) -> SdkRunResult:
        ...


class BudgetGate:
    """Manifest section 27A budget gate (K13 schemas; K04 code per 0C map)."""

    def compare_and_reserve(
        self, reservation: BudgetReservation
    ) -> BudgetReservation:
        ...

    def settle(self, settlement: BudgetSettlement) -> BudgetSettlement:
        ...


class ModelRouter:
    """Manifest section 28 model router (K13 schemas; K04 code per 0C map)."""

    def select(self, request: Any) -> RoutingDecision:
        ...


class GuardedToolDispatcher:
    """Manifest ports section dispatcher (K06 code; bound by the K13 SDK adapter)."""

    def dispatch(self, action: ActionExecution) -> ActionExecution:
        ...


def create_app(
    settings: Any, auth_hook: Any, rate_hook: Any, model_factory: Any
) -> Any:
    ...


class CapabilityRepositoryInterface:
    """Manifest section 37 capability port (K13-owned; implemented outside K13)."""

    def read(self, capability_id: str) -> Optional[Any]:
        ...


class ProviderRegistry:
    """Manifest section 44 provider registry (lookup + health views only)."""

    def lookup(self, name: str) -> Optional[Any]:
        ...


class ModelRegistry:
    """Manifest section 44 model registry (lookup + health views only)."""

    def lookup(self, name: str) -> Optional[Any]:
        ...


class CapabilityRegistry:
    """Manifest section 44 capability registry (lookup + health views only)."""

    def lookup(self, name: str) -> Optional[Any]:
        ...


class ToolRegistry:
    """Manifest section 44 tool registry (lookup + health views only)."""

    def lookup(self, name: str) -> Optional[Any]:
        ...


class KnowledgeSourceRegistry:
    """Manifest section 44 knowledge source registry (lookup + health views only)."""

    def lookup(self, name: str) -> Optional[Any]:
        ...


class VerifierRegistry:
    """Manifest section 44 verifier registry (lookup + health views only)."""

    def lookup(self, name: str) -> Optional[Any]:
        ...


class AuditorRegistry:
    """Manifest section 44 auditor registry (lookup + health views only)."""

    def lookup(self, name: str) -> Optional[Any]:
        ...


class ProjectRepository(RepositoryPort):
    """Manifest ports section (one port per aggregate in src/agent_si/storage/)."""

    ...


class TaskContractRepository(RepositoryPort):
    """Manifest section 13 contract history port."""

    ...


class ContractActivationLog(RepositoryPort):
    """Manifest section 15 activation history port."""

    ...


class TaskTransitionLog(RepositoryPort):
    """Manifest section 12 transition history port."""

    ...


class ExecutionRunRepository(RepositoryPort):
    """Manifest section 14 run history port."""

    ...


class ExecutionAttemptLog(RepositoryPort):
    """Manifest section 14B attempt history port."""

    ...


class AmendmentRepository(RepositoryPort):
    """Manifest section 15 amendment port."""

    ...


class PolicyRepository(RepositoryPort):
    """Manifest sections 16/25A/26A/28 policy port (one per policy type)."""

    ...


class PolicyLifecycleLog(RepositoryPort):
    """Manifest section 25A policy lifecycle port."""

    ...


class RetryFallbackCounterStore(CounterStore):
    """Manifest section 16 + ports section atomic counter port."""

    ...


class VerificationLog(RepositoryPort):
    """Manifest section 21C verification history port."""

    ...


class SuspensionLog(RepositoryPort):
    """Manifest section 12 suspension history port."""

    ...


class RoutingDecisionLog(RepositoryPort):
    """Manifest section 28 routing decision port (K13 schema; K04 writer)."""

    ...


class RoutingEvidenceSnapshotLog(RepositoryPort):
    """Manifest section 28 routing evidence snapshot port (K13 schema; K04 writer)."""

    ...


class ResourceLeaseRegistry(RepositoryPort):
    """Manifest section 38 lease registry port."""

    ...


class ResourceReservationRegistry(RepositoryPort):
    """Manifest section 38 reservation registry port."""

    ...


class BudgetLedger(RepositoryPort):
    """Manifest section 27A budget ledger port (reservations + settlements)."""

    def settle_key(self, record: Mapping[str, Any]) -> str:
        ...


class GovernanceArtifactLog(RepositoryPort):
    """Manifest section 21 governance artifact port."""

    ...


class DecisionLog(RepositoryPort):
    """Manifest section 21B decision port."""

    ...


class FinalizationLog(RepositoryPort):
    """Manifest section 21D finalization port."""

    ...


class ContextIntegrityLog(RepositoryPort):
    """Manifest section 45A context integrity port."""

    ...


class IncidentIndex(RepositoryPort):
    """Manifest section 46 incident index port (indexes only, never duplicates truth)."""

    ...


class ReportDatasetBuilder:
    """Manifest section 59 report dataset builder (metrics from records only)."""

    def build(self, sections: Mapping[str, Any]) -> Dict[str, Any]:
        ...


class UnitOfWork:
    """Manifest coverage row M-D-D33: repositories compose under one unit of work."""

    def stage_append(self, repo: Any, record: Mapping[str, Any]) -> None:
        ...

    def stage_compare_and_set(
        self, repo: Any, record_id: str, expected_version: Any, record: Any
    ) -> None:
        ...

    def commit(self) -> None:
        ...

    def rollback(self) -> None:
        ...


