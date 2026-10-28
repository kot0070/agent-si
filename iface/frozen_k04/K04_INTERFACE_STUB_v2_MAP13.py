"""K04 frozen cross-package interface (shapes only, no logic).

Frozen source: RECORDS/day1/K04_INTERFACE.md (read-only; 0C wins clashes).
Other packages code against this module only; lane internals (names
starting with _) are never imported. Every function body is `...`
(no logic): real behavior lives in the owning lane module named
in REALIZATION_MAP. Standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, TypedDict


class RoleMode(str, Enum):
    """Frozen section 2: one row per executable role per project."""

    PINNED = "PINNED"
    pool = "pool"
    AUTO = "AUTO"


class RiskLevel(str, Enum):
    """Frozen section 2 (never substituted for FailureSeverity)."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class PriceBasis(str, Enum):
    """Frozen section 2: UNKNOWN price is expensive, never zero."""

    KNOWN = "KNOWN"
    UNKNOWN = "UNKNOWN"


class QualityBasis(str, Enum):
    """Frozen section 2: capabilities stay UNKNOWN until evidenced."""

    MEASURED = "MEASURED"
    STATIC_VERIFIED = "STATIC_VERIFIED"
    UNVERIFIED_PIN = "UNVERIFIED_PIN"
    UNKNOWN = "UNKNOWN"


class PoolStrategy(str, Enum):
    """Frozen section 2: plain-language picker values only."""

    DIRECTOR_PER_TASK = "DIRECTOR_PER_TASK"
    AUTO = "AUTO"
    FALLBACK_ORDER = "FALLBACK_ORDER"
    SPLIT_PARALLEL = "SPLIT_PARALLEL"


@dataclass(frozen=True)
class ProviderRef:
    provider_id: str
    provider_instance: Optional[str]


@dataclass(frozen=True)
class ModelRef:
    provider_id: str
    model: str


@dataclass(frozen=True)
class CandidateView:
    provider_id: str
    provider_instance: Optional[str]
    model: str
    effective_capability_ref: str
    price_basis: PriceBasis
    quality_basis: QualityBasis
    modality_ok: bool
    rejected: bool
    reject_reason: Optional[str]


@dataclass(frozen=True)
class ReasonText:
    task_class: str
    fit_basis: str
    price_basis: str
    quality_basis: str
    rejected: List[str]


@dataclass(frozen=True)
class ReservationRequest:
    project_id: str
    task_id: str
    run_id: str
    estimated_amount: float
    provider_request_ref: str


@dataclass(frozen=True)
class CostLine:
    amount: Optional[float]
    currency: str
    pricing_snapshot_id: Optional[str]


#: Never a default, never in a fallback chain or role profile unless
#: the user made an explicit PINNED choice (frozen section 2).
NON_DEFAULT_EXAMPLE = "meta/muse-spark-1.3-contributor"


@dataclass(frozen=True)
class SecretRef:
    secret_id: str
    provider_id: str
    type: str
    scope: str
    source: str
    created_at: str
    last_rotated_at: str


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
    deadline: Any
    budget_limit: Any


@dataclass(frozen=True)
class DefaultManagerProfile:
    profile_id: str = "DMP-001"
    version: int = 1
    provider: Any = None
    model: Any = None
    binding: str = "DEFAULT"
    hash: str = ""


@dataclass(frozen=True)
class RoleModelProfile:
    role: str
    project_id: str
    mode: str
    provider: Any = None
    model: Any = None
    binding: str = "DEFAULT"
    version: int = 1
    hash: str = ""


@dataclass(frozen=True)
class RoutingAssignment:
    assignment_id: str
    project_id: str
    task_id: str
    run_id: str
    subtask_id: Any
    role: Any
    stage: Any
    route: str
    provider: str
    provider_instance: Any
    model: str
    capability_evidence_refs: tuple
    resource_state_ref: str
    budget_reservation_ref: Any
    routing_policy_ref: str
    optimization_policy_ref: str
    status: str = "PLANNED"


@dataclass(frozen=True)
class RoutingEvidenceSnapshot:
    routing_snapshot_id: str
    project_id: str
    task_id: str
    run_id: str
    created_at: str
    provider_health_snapshot: Any
    model_health_snapshot: Any
    resource_state_snapshot: Any
    budget_state_snapshot: Any
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
    selected_provider: Any
    selected_model: Any
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
    estimated_cost: Any
    estimated_latency: Any
    optimization_score: Any
    fallback_chain: tuple


@dataclass(frozen=True)
class FallbackRecord:
    fallback_id: str
    project_id: str
    task_id: str
    source_run_id: str
    replacement_run_id: Any
    source_attempt_id: Any
    reason: str
    from_provider: str
    from_model: str
    to_provider: str
    to_model: str
    policy_ref: str
    evidence_ref: str


@dataclass(frozen=True)
class ProviderContracts:
    provider_id: str
    type: str
    base_url: str
    secret_ref: SecretRef
    instance_id: str = "default"
    evidenced: bool = False
    health: str = "UNKNOWN"
    mock: bool = False


class ModelContracts(TypedDict):
    """KB row shape served at choice points (frozen section 4/5 name)."""

    provider_id: str
    model_id: str
    fields: Dict[str, Any]


@dataclass
class BudgetState:
    project_id: str
    currency: str
    budget_limit: str
    soft_limit: str
    hard_limit: str
    spent: str = "0"
    reserved: str = "0"
    updated_at: str = ""
    provider_spend_caps: Dict[str, str] = dc_field(default_factory=dict)


@dataclass
class BudgetReservation:
    reservation_id: str
    project_id: str
    task_id: str
    run_id: str
    estimated_amount: str
    reserved_at: str
    expires_at: str
    status: str = "ACTIVE"
    provider_request_ref: str = ""
    provider_id: str = ""


@dataclass
class BudgetSettlement:
    settlement_id: str
    reservation_id: str
    provider_usage_evidence_ref: Optional[str]
    provider_request_ref: str
    dedupe_key: str
    actual_amount: Optional[str]
    difference: Optional[str]
    status: str
    settled_at: Optional[str]
    source: str


@dataclass
class MetricRecord:
    metric_id: str
    project_id: str
    task_id: str
    run_id: str
    metric_name: str
    value: Any
    unit: str
    state: str
    source: str
    recorded_at: str


@dataclass
class PricingSnapshot:
    pricing_snapshot_id: str
    provider_id: str
    model_id: str
    currency: str
    effective_at: str
    source: str
    input_token_price: Optional[str] = None
    output_token_price: Optional[str] = None
    cached_token_price: Optional[str] = None
    reasoning_token_price: Optional[str] = None
    request_price: Optional[str] = None
    other_rules: list = dc_field(default_factory=list)
    created_at: str = ""
    hash: str = ""


TelemetryEvent = TypedDict("TelemetryEvent", {
    "event_id": str,
    "project_id": str,
    "timestamp": str,
    "task_id": Any,
    "run_id": Any,
    "attempt_id": Any,
    "subtask_id": Any,
    "parent_id": Any,
    "role": Any,
    "task_class": Any,
    "risk": Any,
    "state": Any,
    "route": Any,
    "split_strategy": Any,
    "provider": Any,
    "model": Any,
    "provider_instance": Any,
    "event_type": str,
    "retry": Any,
    "verification_ref": Any,
    "audit_ref": Any,
    "re-execution": Any,
    "error_ref": Any,
    "fallback_reason": Any,
    "capability_rule": Any,
    "capability_evidence_ref": Any,
    "routing_decision_ref": Any,
    "routing_snapshot_id": Any,
    "resource_state_ref": Any,
    "metric_refs": Any,
    "final_status": Any,
})


class UsageReportingCapabilities(TypedDict):
    provider_id: str
    instance_id: str
    state: str
    input_tokens: Any
    output_tokens: Any
    cached_tokens: Any
    reasoning_tokens: Any
    raw_usage: Any
    stream_usage: Any
    cost_fields: Any
    request_level_usage: Any
    verified_at: str
    evidence_ref: Any


#: Every served KB row holds these fields or UNKNOWN, each with source
#: and date (frozen section 3.4).
KB_ROW_FIELDS = (
    "purpose",
    "strengths",
    "weaknesses",
    "context_window",
    "max_output",
    "modalities",
    "tool_calling",
    "reasoning",
    "knowledge_cutoff",
    "currency",
    "price_effective_at",
    "input_token_price",
    "output_token_price",
    "cached_token_price",
    "reasoning_token_price",
    "request_price",
    "best_for",
    "avoid_for",
    "cost_tier",
    "role_notes",
    "source_links",
)

#: KB row envelope keys plus sourced-field keys.
KB_ROW_KEYS = ("provider_id", "model_id", "fields")
KB_SOURCED_FIELD_KEYS = ("value", "source", "retrieved_at")

#: Canonical selection order, hard eligibility before optimization
#: (frozen section 3.1).
FROZEN_SELECTION_STEPS = (
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

#: Frozen error-code names (sections 6: K13 never redefined, then K04).
ERROR_CODES_K13 = (
    "CONTEXT_WRONG_CONTRACT_VERSION",
    "POLICY_CONFLICT",
    "CONTEXT_MISSING",
)
ERROR_CODES_K04 = (
    "NO_PROFILE_BLOCKED",
    "NO_ELIGIBLE_CANDIDATE",
    "MODALITY_MISMATCH",
    "PROVIDER_UNEVIDENCED",
    "PRICE_UNKNOWN_EXPENSIVE",
    "BUDGET_SOFT_WARN",
    "BUDGET_HARD_BLOCKED",
    "PENDING_RECONCILIATION",
    "DUPLICATE_SETTLEMENT_REFUSED",
    "KB_VALIDATION_FAILED",
    "KB_PROPOSAL_NOT_APPROVED",
    "KEY_SAVE_TIMEOUT",
    "CREDENTIAL_ENTRY_MISSING",
)


def _stub() -> None:
    """Frozen interface marker: real behavior lives in REALIZATION_MAP."""
    ...


def select(task_contract_ref: str, candidates: List[CandidateView],
           routing_policy_ref: str, optimization_policy_ref: str,
           budget_state_ref: str,
           resource_state_ref: str) -> RoutingDecision:
    """Frozen 3.1: selection only, never provider SDK calls."""
    ...


def replay(decision_id: str) -> Tuple[RoutingDecision,
                                      List[RoutingAssignment],
                                      RoutingEvidenceSnapshot]:
    """Frozen 3.1: decision + assignments + snapshot; history never live."""
    ...


def record_fallback(reason: str, from_provider: str, from_model: str,
                    to_provider: str, to_model: str, policy_ref: str,
                    evidence_ref: str) -> FallbackRecord:
    """Frozen 3.1: pinned swaps only through this recorded path."""
    ...


def resolve_role_model(role: str, project_id: str) -> ModelRef:
    """Frozen 3.1: NO_PROFILE_BLOCKED with a reason when no profile."""
    ...


def pick_pool_strategy(role: str, project_id: str) -> PoolStrategy:
    """Frozen 3.1: plain-language strategy, never raw pool ids."""
    ...


def register_provider(descriptor: ProviderContracts,
                      secret_ref: SecretRef) -> ProviderContracts:
    """Frozen 3.2: key-only connect; preset fills id, type and base URL."""
    ...


def get_provider(provider_id: str) -> Optional[ProviderContracts]:
    """Frozen 3.2."""
    ...


def list_providers(only_evidenced: bool) -> List[ProviderContracts]:
    """Frozen 3.2: matrix rows record only evidenced credentials."""
    ...


def record_health(provider_id: str, provider_instance: Optional[str],
                  health: str) -> ProviderContracts:
    """Frozen 3.2: per-instance health; latest check wins."""
    ...


def remove_provider(provider_id: str) -> None:
    """Frozen 3.2: clean removal incl. the store entry."""
    ...


def probe_usage(adapter_id: str, provider_id: str,
                streaming: bool) -> UsageReportingCapabilities:
    """Frozen 3.3: every adapter probed; streaming verified separately."""
    ...


def resolve_model(provider_id: str, model: str) -> ModelContracts:
    """Frozen 3.3: exact id, never reworded or case-folded."""
    ...


def read_kb(provider_ids: List[str]) -> List[ModelContracts]:
    """Frozen 3.4: AUTO reads only connected providers."""
    ...


def resolve_exact_id(model: str) -> Tuple[ModelContracts, str]:
    """Frozen 3.4: contract plus dated snapshot ref."""
    ...


def propose_update(draft: dict, updated_by_model: str) -> dict:
    """Frozen 3.4: schema-validated proposal, applied only by the user."""
    ...


def compare_and_reserve(request: ReservationRequest) -> BudgetReservation:
    """Frozen 3.5: atomic compare-and-reserve before any billable call."""
    ...


def settle(settlement: BudgetSettlement) -> BudgetSettlement:
    """Frozen 3.5: deterministic dedupe; duplicates refused."""
    ...


def reconcile_pending(project_id: str) -> List[BudgetSettlement]:
    """Frozen 3.5: restart reconciliation; expired releases idempotent."""
    ...


def get_state(project_id: str) -> BudgetState:
    """Frozen 3.5: remaining derived, never stored truth."""
    ...


def calculate_cost(usage_ref: str, pricing_snapshot_id: str) -> CostLine:
    """Frozen 3.5: cost only over a pricing snapshot; never zero."""
    ...


def get_role_pools(project_id: str) -> List[RoleModelProfile]:
    """Frozen 3.6: stored bindings with declared use mode per member."""
    ...


def set_role_pool(project_id: str, role: str, mode: RoleMode,
                  provider: Optional[str], model: Optional[str],
                  pool: List[ModelRef],
                  strategy: PoolStrategy) -> RoleModelProfile:
    """Frozen 3.6: persists; reflected in subsequent run behavior."""
    ...


def get_kb_status() -> Dict[str, Any]:
    """Frozen 3.7: last-update date overall plus per provider."""
    ...


def get_models(provider_ids: List[str],
               query: Optional[str]) -> List[Dict[str, Any]]:
    """Frozen 3.7: model rows with checkbox state plus search."""
    ...


def apply_proposal(proposal_id: str,
                   approved_by_user: bool) -> Dict[str, Any]:
    """Frozen 3.7: applies only on explicit user approval."""
    ...


class ProvidersPageProps(TypedDict):
    project_id: str


class ConnectDialogProps(TypedDict):
    preset_id: str


class DisconnectDialogProps(TypedDict):
    provider_id: str


class RolePoolPickerProps(TypedDict):
    role: str
    project_id: str


class ChatModelSelectorProps(TypedDict):
    project_id: str


class LeftoverKeyFinderProps(TypedDict):
    pass


#: Frozen section 4 HTTP surface: (method, path) pairs.
HTTP_ROUTES = (
    ("GET", "/api/v1/providers"),
    ("POST", "/api/v1/providers/connect"),
    ("POST", "/api/v1/providers/{id}/disconnect"),
    ("GET", "/api/v1/providers/{id}/models"),
    ("GET", "/api/v1/chat/models"),
    ("GET", "/api/v1/roles/pools"),
    ("PUT", "/api/v1/roles/pools"),
    ("GET", "/api/v1/routing/decision/{id}/why"),
    ("GET", "/api/v1/budget"),
    ("GET", "/api/v1/kb/status"),
    ("POST", "/api/v1/kb/proposals/apply"),
)

#: Frozen function name to owning lane implementation (dotted path).
#: Parameter shapes may be adapted per lane; the contract test pins the
#: exact mapping.
REALIZATION_MAP = {
    "select": "agent_si.routing.router.select",
    "replay": "agent_si.routing.store.RoutingStore.why_replay",
    "record_fallback": "agent_si.routing.fallback.build_fallback_record",
    "resolve_role_model": "agent_si.routing.roles.resolve_role_model",
    "pick_pool_strategy": "agent_si.routing.pools.pick_pool_strategy",
    "register_provider":
        "agent_si.providers.registry.facades.register_provider",
    "get_provider":
        "agent_si.providers.registry.facades.get_provider",
    "list_providers":
        "agent_si.providers.registry.facades.list_providers",
    "record_health":
        "agent_si.providers.registry.facades.record_health",
    "remove_provider":
        "agent_si.providers.registry.facades.remove_provider",
    "probe_usage": "agent_si.providers.adapters.facades.probe_usage",
    "resolve_model": "agent_si.providers.adapters.facades.resolve_model",
    "read_kb": "agent_si.model_kb.loader.read_kb",
    "resolve_exact_id": "agent_si.model_kb.loader.resolve_exact_id",
    "propose_update": "agent_si.model_kb.loader.propose_update",
    "compare_and_reserve": "agent_si.budget.gate.BudgetGate.compare_and_reserve",
    "settle": "agent_si.budget.gate.BudgetGate.settle",
    "reconcile_pending": "agent_si.budget.gate.BudgetGate.reconcile_on_restart",
    "get_state": "agent_si.budget.gate.BudgetGate.get_state",
    "calculate_cost": "agent_si.budget.telemetry.CostCalculator.calculate",
    "get_role_pools": "agent_si.backend.pools_routes.get_role_pools",
    "set_role_pool": "agent_si.backend.pools_routes.set_role_pool",
    "get_kb_status": "agent_si.backend.modelkb.get_kb_status",
    "get_models": "agent_si.backend.modelkb.get_models",
    "apply_proposal": "agent_si.backend.modelkb.apply_proposal",
}
