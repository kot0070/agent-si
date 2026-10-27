# K04 Lane A2 — frozen routing record types (K13 manifest names, exact fields).
# Stdlib only. No machine paths, no vendor/model defaults, no raw secrets.
"""Shared frozen dataclasses for the model router.

Field names implement the K13 frozen interface manifest exactly:
RoutingDecision, RoutingAssignment, RoutingEvidenceSnapshot, RoutingPolicy,
OptimizationPolicy (manifest section 28), FallbackRecord (section 17),
DefaultManagerProfile (section 3B), RoleModelProfile (section 8).
Never rename a field here: persistence, replay and WHY_THIS_MODEL depend
on the exact names.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

# --------------------------------------------------------------------------
# Frozen vocabularies (manifest sections 17, 17C reference, 25A, 28, 35, 36)

FALLBACK_REASONS = (
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

ROUTING_ASSIGNMENT_STATUSES = (
    "PLANNED",
    "BOUND",
    "RUNNING",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
    "SUPERSEDED",
)

RISK_LEVELS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
RISK_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}

ROLES = ("director", "manager", "worker", "auditor", "watcher")

ROLE_MODES = ("PINNED", "pool", "AUTO")

PROFILE_BINDINGS = ("DEFAULT", "HARD_LOCK")

ROUTES = ("CLOUD", "LOCAL", "SPLIT", "PARALLEL", "HYBRID", "BLOCKED")

SELECTION_STEPS = (
    "HARD_CAPABILITY_FILTER",
    "PROVIDER_CAPABILITY_FILTER",
    "PROVIDER_HEALTH_FILTER",
    "MODEL_HEALTH_FILTER",
    "SECURITY_RISK_FILTER",
    "ROUTING_POLICY_FILTER",
    "RESOURCE_SCHEDULER_FILTER",
    "BUDGET_ELIGIBILITY_FILTER",
    "QUALITY_THRESHOLD",
    "OPTIMIZATION_SCORE",
    "FALLBACK_CHAIN",
)

ELIGIBILITY_BRANCHES = (
    "CAPABILITY_EVIDENCE",
    "VERIFIED_STATIC_CAPABILITY",
    "EXPLICIT_MODEL_PIN",
)

CAPABILITY_STATES = ("MEASURED", "PROXY", "UNVERIFIED", "UNKNOWN")

VERIFICATION_LEVELS = ("STANDARD", "ENHANCED")

PROVIDER_STATUSES = ("ONLINE", "DEGRADED", "OFFLINE", "UNKNOWN")

MODEL_HEALTH_STATUSES = ("READY", "LOADING", "DEGRADED", "ERROR", "OFFLINE", "UNKNOWN")

POOL_USE_MODES = ("primary", "fallback", "draft", "verify", "parallel")

POOL_STRATEGIES = ("DIRECTOR_PER_TASK", "AUTO", "FALLBACK_ORDER",
                   "SPLIT_PARALLEL")

STRATEGY_LABELS = {
    "DIRECTOR_PER_TASK": "Director decides per task",
    "AUTO": "Auto",
    "FALLBACK_ORDER": "Fallback order",
    "SPLIT_PARALLEL": "Split/parallel",
}

#: Persisted bindings written before the frozen vocabulary use these legacy
#: values. RoutingStore.get_pool migrates them to POOL_STRATEGIES on READ;
#: save_pool and PoolBinding reject them (frozen values only on WRITE).
LEGACY_POOL_STRATEGIES = {
    "director_decides": "DIRECTOR_PER_TASK",
    "auto": "AUTO",
    "fallback_order": "FALLBACK_ORDER",
    "split_parallel": "SPLIT_PARALLEL",
}


def migrate_pool_strategy(value):
    """Map a legacy persisted pool strategy to the frozen vocabulary.

    Frozen values pass through unchanged; legacy values map via
    LEGACY_POOL_STRATEGIES; anything else is returned as-is so the caller
    (check_enum or the member-count rule) decides its fate.
    """
    return LEGACY_POOL_STRATEGIES.get(value, value)

MANAGER_TRIGGER_SOURCES = ("fallback", "routing_decision", "user_override")


# --------------------------------------------------------------------------
# Helpers

def utcnow() -> str:
    """Current UTC time as an ISO-8601 string (portable, no machine facts)."""
    return datetime.now(timezone.utc).isoformat()


def stable_hash(payload) -> str:
    """sha256 over canonical JSON (sorted keys, compact separators)."""
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                     default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def risk_at_most(risk: str, cap: str) -> bool:
    """True when RiskLevel `risk` is within ceiling `cap` (section 25A order)."""
    return RISK_ORDER[risk] <= RISK_ORDER[cap]


def check_enum(name: str, value, allowed) -> None:
    if value not in allowed:
        raise ValueError("invalid %s: %r (allowed: %s)"
                         % (name, value, ", ".join(allowed)))


# --------------------------------------------------------------------------
# Secret reference (manifest section 20A: refs travel, raw secrets never do)

@dataclass(frozen=True)
class SecretRef:
    secret_id: str
    provider_id: str
    type: str
    scope: str
    source: str
    created_at: str
    last_rotated_at: str


# --------------------------------------------------------------------------
# Policies (manifest section 28; immutable, versioned, hash-addressed)

@dataclass(frozen=True)
class RoutingPolicy:
    policy_id: str
    version: int
    created_at: str
    hash: str
    task_class: str
    risk_level: str
    strict_min: float
    tolerant_min: float
    confidence_min: float
    sample_min: int
    freshness_requirement: str
    local_allowed: bool
    split_allowed: bool
    cloud_required: bool

    def __post_init__(self):
        check_enum("risk_level", self.risk_level, RISK_LEVELS)


@dataclass(frozen=True)
class OptimizationPolicy:
    policy_id: str
    version: int
    created_at: str
    hash: str
    required_quality: float
    max_risk: str
    weight_quality: float
    weight_cost: float
    weight_latency: float
    weight_cloud_tokens: float
    local_preference: bool
    deadline: object
    budget_limit: object
    token_overhead: int = 0

    def __post_init__(self):
        check_enum("max_risk", self.max_risk, RISK_LEVELS)


# --------------------------------------------------------------------------
# Profiles (manifest sections 3B and 8)

@dataclass(frozen=True)
class DefaultManagerProfile:
    profile_id: str = "DMP-001"
    version: int = 1
    provider: object = None
    model: object = None
    binding: str = "DEFAULT"
    hash: str = ""

    def __post_init__(self):
        check_enum("binding", self.binding, PROFILE_BINDINGS)
        if not self.provider or not self.model:
            raise ValueError("DefaultManagerProfile needs an explicit "
                             "provider and model (project config, never a "
                             "code default)")


@dataclass(frozen=True)
class RoleModelProfile:
    role: str
    project_id: str
    mode: str
    provider: object = None
    model: object = None
    binding: str = "DEFAULT"
    version: int = 1
    hash: str = ""

    def __post_init__(self):
        if self.role not in ROLES:
            raise ValueError("invalid role: %r" % (self.role,))
        check_enum("mode", self.mode, ROLE_MODES)
        check_enum("binding", self.binding, PROFILE_BINDINGS)
        if self.mode == "PINNED" and (not self.provider or not self.model):
            raise ValueError("PINNED profile needs provider and model")
        if self.mode == "AUTO" and (self.provider or self.model):
            raise ValueError("AUTO profile holds no provider/model")


# --------------------------------------------------------------------------
# Routing records (manifest section 28)

@dataclass(frozen=True)
class RoutingAssignment:
    assignment_id: str
    project_id: str
    task_id: str
    run_id: str
    subtask_id: object
    role: object
    stage: object
    route: str
    provider: str
    provider_instance: object
    model: str
    capability_evidence_refs: tuple
    resource_state_ref: str
    budget_reservation_ref: object
    routing_policy_ref: str
    optimization_policy_ref: str
    status: str = "PLANNED"

    def __post_init__(self):
        check_enum("status", self.status, ROUTING_ASSIGNMENT_STATUSES)


@dataclass(frozen=True)
class RoutingEvidenceSnapshot:
    routing_snapshot_id: str
    project_id: str
    task_id: str
    run_id: str
    created_at: str
    provider_health_snapshot: object
    model_health_snapshot: object
    resource_state_snapshot: object
    budget_state_snapshot: object
    candidate_snapshot: tuple
    policy_versions: tuple
    capability_evidence_refs: tuple
    hash: str


@dataclass(frozen=True)
class RoutingDecision:
    decision_id: str
    project_id: str
    task_id: str
    run_id: str
    routing_snapshot_id: str
    routing_policy_ref: str
    optimization_policy_ref: str
    retry_policy_ref: str
    fallback_policy_ref: str
    verification_policy_ref: str
    audit_policy_ref: str
    override_policy_ref: str
    candidate_models: tuple
    candidate_providers: tuple
    selected_provider: object
    selected_model: object
    routing_assignment_ids: tuple
    route: str
    strategy: str
    reason: str
    eligibility_source: str
    capability_state: str
    required_verification: str
    eligibility_branch_evidence_refs: tuple
    capability_evidence_refs: tuple
    provider_health_ref: str
    model_health_ref: str
    resource_state_ref: str
    risk_override: bool
    estimated_cost: object
    estimated_latency: object
    optimization_score: object
    fallback_chain: tuple
    estimated_tokens: object = None


# --------------------------------------------------------------------------
# Fallback record (manifest section 17)

@dataclass(frozen=True)
class FallbackRecord:
    fallback_id: str
    project_id: str
    task_id: str
    source_run_id: str
    replacement_run_id: object
    source_attempt_id: object
    reason: str
    from_provider: str
    from_model: str
    to_provider: str
    to_model: str
    policy_ref: str
    evidence_ref: str

    def __post_init__(self):
        check_enum("reason", self.reason, FALLBACK_REASONS)


# --------------------------------------------------------------------------
# Router inputs (selection only; registries stay lookup+health per section 44)

@dataclass(frozen=True)
class CandidateModel:
    provider: str
    model: str
    provider_instance: object = None
    provider_type: str = "cloud"
    is_mock: bool = False

    def __post_init__(self):
        if self.provider_type not in ("cloud", "local"):
            raise ValueError("invalid provider_type: %r"
                             % (self.provider_type,))


@dataclass(frozen=True)
class ProviderHealth:
    provider: str
    status: str
    last_check: object = None
    latency_ms: object = None
    error: object = None
    capacity_state: object = None

    def __post_init__(self):
        check_enum("status", self.status, PROVIDER_STATUSES)


@dataclass(frozen=True)
class ModelHealth:
    provider: str
    model: str
    status: str
    loaded_state: object = None
    latency_ms: object = None
    memory_state: object = None
    last_check: object = None
    error: object = None

    def __post_init__(self):
        check_enum("status", self.status, MODEL_HEALTH_STATUSES)


def empty_tuple(value) -> tuple:
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    return tuple(value)


@dataclass(frozen=True)
class GateTrace:
    """One candidate's verdict at one selection step (diagnostics, not stored)."""
    step: str
    provider: str
    model: str
    passed: bool
    detail: str = ""
