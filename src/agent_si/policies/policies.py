"""Versioned hash-addressed policy objects (Manifest sections 16, 17, 25A, 26A).

Every policy is an immutable, versioned, hash-addressed record: new content
is a new version with a new hash, never a rewrite. Shared names come ONLY
from iface/frozen_manifest/manifest.py; on any clash the 0C architecture
(section 12 map) wins per the manifest reconciliation table.
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

try:
    from iface.frozen_manifest import manifest
except ImportError:  # alternate layout: the iface/ directory itself on sys.path
    from frozen_manifest import manifest


class PolicyLifecycleEvent(str, Enum):
    """Manifest section 25A PolicyLifecycleEvent (frozen set)."""

    ACTIVATED = "ACTIVATED"
    SUPERSEDED = "SUPERSEDED"
    RETIRED = "RETIRED"


class ReworkCounterType(str, Enum):
    """Manifest section 16 ReworkCounterType (frozen set)."""

    PHASE0_REWORK = "PHASE0_REWORK"
    RUNTIME_REWORK = "RUNTIME_REWORK"
    VERIFICATION_REWORK = "VERIFICATION_REWORK"
    AUDIT_REWORK = "AUDIT_REWORK"


class FallbackCounterScope(str, Enum):
    """Manifest section 16 FallbackCounterScope (frozen set)."""

    RUN = "RUN"
    TASK = "TASK"


class VerificationRequirement(str, Enum):
    """Manifest section 26A VerificationRequirement."""

    STANDARD = "STANDARD"
    ENHANCED = "ENHANCED"


class AuditRequirement(str, Enum):
    """Manifest section 26A AuditRequirement (NONE prohibited)."""

    REQUIRED_L2 = "REQUIRED_L2"
    REQUIRED_L3 = "REQUIRED_L3"
    REQUIRED_L4_MANUAL = "REQUIRED_L4_MANUAL"


def _as_tuple(value: Any) -> Tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    return tuple(value)


def _coerce_enum(value: Any, enum: Any) -> Any:
    if isinstance(value, enum):
        return value
    return enum(str(value))


# ---------------------------------------------------------------------------
# Immutable policy objects (sections 16, 25A, 26A, 28, 18B).
# Common fields: policy_id, version, created_at, hash, supersedes_policy_ref.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RoutingPolicy:
    """Manifest section 28 RoutingPolicy. Immutable, versioned."""

    policy_id: str = ""
    version: int = 1
    created_at: str = ""
    hash: str = ""
    supersedes_policy_ref: Optional[str] = None
    task_class: str = ""
    risk_level: manifest.RiskLevel = manifest.RiskLevel.MEDIUM
    strict_min: float = 0.0
    tolerant_min: float = 0.0
    confidence_min: float = 0.0
    sample_min: int = 0
    freshness_requirement: str = ""
    local_allowed: bool = False
    split_allowed: bool = False
    cloud_required: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "risk_level", _coerce_enum(self.risk_level, manifest.RiskLevel)
        )


@dataclass(frozen=True)
class OptimizationPolicy:
    """Manifest section 28 OptimizationPolicy. Immutable, versioned."""

    policy_id: str = ""
    version: int = 1
    created_at: str = ""
    hash: str = ""
    supersedes_policy_ref: Optional[str] = None
    required_quality: float = 0.0
    max_risk: manifest.RiskLevel = manifest.RiskLevel.MEDIUM
    weight_quality: float = 0.0
    weight_cost: float = 0.0
    weight_latency: float = 0.0
    weight_cloud_tokens: float = 0.0
    local_preference: float = 0.0
    deadline: str = ""
    budget_limit: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "max_risk", _coerce_enum(self.max_risk, manifest.RiskLevel)
        )


@dataclass(frozen=True)
class RetryPolicy:
    """Manifest section 16 RetryPolicy. Immutable, versioned."""

    policy_id: str = ""
    version: int = 1
    created_at: str = ""
    hash: str = ""
    supersedes_policy_ref: Optional[str] = None
    executor_attempt_max: int = 3
    provider_retry_max: int = 2
    format_retry_max: int = 1
    verification_retry_max: int = 1
    verification_correction_max: int = 2
    audit_correction_max: int = 2
    runtime_correction_max: int = 3
    backoff_policy: str = ""


@dataclass(frozen=True)
class FallbackPolicy:
    """Manifest section 16 FallbackPolicy. Immutable, versioned."""

    policy_id: str = ""
    version: int = 1
    created_at: str = ""
    hash: str = ""
    supersedes_policy_ref: Optional[str] = None
    allowed_reasons: Tuple[str, ...] = ()
    fallback_chain: Tuple[str, ...] = ()
    same_run_rules: str = ""
    new_run_rules: str = ""
    max_fallbacks_per_run: int = 1
    max_fallbacks_per_task: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "allowed_reasons", _as_tuple(self.allowed_reasons))
        object.__setattr__(self, "fallback_chain", _as_tuple(self.fallback_chain))


@dataclass(frozen=True)
class VerificationPolicy:
    """Manifest section 26A VerificationPolicy. Immutable, versioned."""

    policy_id: str = ""
    version: int = 1
    created_at: str = ""
    hash: str = ""
    supersedes_policy_ref: Optional[str] = None
    requirement: VerificationRequirement = VerificationRequirement.STANDARD
    required_types: Tuple[str, ...] = ()
    retry_policy_ref: str = ""
    evidence_requirements: Tuple[str, ...] = ()
    failure_disposition_policy_ref: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "requirement",
            _coerce_enum(self.requirement, VerificationRequirement),
        )
        object.__setattr__(self, "required_types", _as_tuple(self.required_types))
        object.__setattr__(
            self, "evidence_requirements", _as_tuple(self.evidence_requirements)
        )


@dataclass(frozen=True)
class AuditPolicy:
    """Manifest section 26A AuditPolicy. Immutable, versioned."""

    policy_id: str = ""
    version: int = 1
    created_at: str = ""
    hash: str = ""
    supersedes_policy_ref: Optional[str] = None
    audit_requirement: AuditRequirement = AuditRequirement.REQUIRED_L2
    minimum_independence_level: str = ""
    required_context_integrity: str = ""
    retry_policy_ref: str = ""
    override_policy_ref: str = ""
    manual_review_rules: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "audit_requirement",
            _coerce_enum(self.audit_requirement, AuditRequirement),
        )
        object.__setattr__(
            self, "manual_review_rules", _as_tuple(self.manual_review_rules)
        )


@dataclass(frozen=True)
class OverridePolicy:
    """Manifest section 18B OverridePolicy. Immutable, versioned, user-only."""

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

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "allowed_source_states", _as_tuple(self.allowed_source_states)
        )
        object.__setattr__(
            self,
            "non_overridable_failure_classes",
            _as_tuple(self.non_overridable_failure_classes),
        )
        object.__setattr__(
            self,
            "non_overridable_ac_types",
            _as_tuple(self.non_overridable_ac_types),
        )
        object.__setattr__(
            self,
            "non_overridable_gate_ids",
            _as_tuple(self.non_overridable_gate_ids),
        )
        object.__setattr__(
            self, "post_override_rules", _as_tuple(self.post_override_rules)
        )
        object.__setattr__(
            self, "evidence_requirements", _as_tuple(self.evidence_requirements)
        )


@dataclass(frozen=True)
class FailureDispositionPolicy:
    """Manifest section 26A FailureDispositionPolicy. Immutable, versioned."""

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

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "failure_class_rules", _as_tuple(self.failure_class_rules)
        )
        object.__setattr__(self, "severity_rules", _as_tuple(self.severity_rules))


POLICY_FIELDS: Dict[str, Tuple[str, ...]] = {
    "RoutingPolicy": (
        "policy_id",
        "version",
        "created_at",
        "supersedes_policy_ref",
        "task_class",
        "risk_level",
        "strict_min",
        "tolerant_min",
        "confidence_min",
        "sample_min",
        "freshness_requirement",
        "local_allowed",
        "split_allowed",
        "cloud_required",
    ),
    "FallbackPolicy": (
        "policy_id",
        "version",
        "created_at",
        "supersedes_policy_ref",
        "allowed_reasons",
        "fallback_chain",
        "same_run_rules",
        "new_run_rules",
        "max_fallbacks_per_run",
        "max_fallbacks_per_task",
    ),
    "RetryPolicy": (
        "policy_id",
        "version",
        "created_at",
        "supersedes_policy_ref",
        "executor_attempt_max",
        "provider_retry_max",
        "format_retry_max",
        "verification_retry_max",
        "verification_correction_max",
        "audit_correction_max",
        "runtime_correction_max",
        "backoff_policy",
    ),
    "VerificationPolicy": (
        "policy_id",
        "version",
        "created_at",
        "supersedes_policy_ref",
        "requirement",
        "required_types",
        "retry_policy_ref",
        "evidence_requirements",
        "failure_disposition_policy_ref",
    ),
    "AuditPolicy": (
        "policy_id",
        "version",
        "created_at",
        "supersedes_policy_ref",
        "audit_requirement",
        "minimum_independence_level",
        "required_context_integrity",
        "retry_policy_ref",
        "override_policy_ref",
        "manual_review_rules",
    ),
    "OverridePolicy": (
        "policy_id",
        "version",
        "created_at",
        "supersedes_policy_ref",
        "accepted_risk_allowed",
        "allowed_source_states",
        "non_overridable_failure_classes",
        "non_overridable_ac_types",
        "non_overridable_gate_ids",
        "required_authority",
        "post_override_rules",
        "evidence_requirements",
    ),
    "FailureDispositionPolicy": (
        "policy_id",
        "version",
        "created_at",
        "supersedes_policy_ref",
        "failure_class_rules",
        "severity_rules",
        "retry_policy_ref",
        "fallback_policy_ref",
        "override_policy_ref",
    ),
    "OptimizationPolicy": (
        "policy_id",
        "version",
        "created_at",
        "supersedes_policy_ref",
        "required_quality",
        "max_risk",
        "weight_quality",
        "weight_cost",
        "weight_latency",
        "weight_cloud_tokens",
        "local_preference",
        "deadline",
        "budget_limit",
    ),
}
"""Canonical hash-addressed field order per policy (hash covers content only)."""


def _canonical(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _canonical(value[key]) for key in sorted(value)}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(
        "policy_hash covers only JSON-canonical field values, got %r" % type(value)
    )


def compute_policy_hash(policy: Any) -> str:
    """sha256 over the canonical field order for the policy type (section 25A).

    The field order is POLICY_FIELDS[type(policy).__name__] minus hash itself.
    Same content always yields the same digest (one content, one hash).
    """
    fields = POLICY_FIELDS[type(policy).__name__]
    payload = {name: _canonical(getattr(policy, name)) for name in fields}
    encoded = json.dumps(
        payload, sort_keys=False, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _bump(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(
            "%s must be supplied explicitly for non-integer versions" % field_name
        )
    return value + 1


def new_policy_version(old: Any, **changes: Any) -> Any:
    """Build a NEW policy version; *old* is never modified (sections 16, 25A).

    version defaults to old+1 (or may be supplied explicitly); hash is always
    recomputed and can never be supplied. Returns the new frozen instance;
    the input keeps its original version and hash.
    """
    if "hash" in changes:
        raise ValueError("hash is recomputed, never supplied")
    version = changes.pop("version", _bump(old.version, "version"))
    new = replace(old, version=version, **changes)
    return replace(new, hash=compute_policy_hash(new))


# ---------------------------------------------------------------------------
# PolicyLifecycleRecord: status derived, never stored (section 25A).
# ---------------------------------------------------------------------------

POLICY_LIFECYCLE_FIELDS = (
    "policy_lifecycle_id",
    "policy_ref",
    "policy_id",
    "policy_version",
    "lifecycle_sequence",
    "event",
    "created_at",
    "reason",
    "supersedes_policy_ref",
)
"""Manifest section 25A PolicyLifecycleRecord field order (no status field)."""


@dataclass(frozen=True)
class PolicyLifecycleRecord:
    """Manifest section 25A PolicyLifecycleRecord. Immutable, status derived."""

    policy_lifecycle_id: str = ""
    policy_ref: str = ""
    policy_id: str = ""
    policy_version: int = 0
    lifecycle_sequence: int = 0
    event: PolicyLifecycleEvent = PolicyLifecycleEvent.ACTIVATED
    created_at: str = ""
    reason: str = ""
    supersedes_policy_ref: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "event",
            _coerce_enum(self.event, PolicyLifecycleEvent),
        )

    @property
    def status(self) -> str:
        """Derived status (ACTIVE | SUPERSEDED | RETIRED); never stored."""
        if self.event == PolicyLifecycleEvent.RETIRED:
            return "RETIRED"
        if self.event == PolicyLifecycleEvent.SUPERSEDED:
            return "SUPERSEDED"
        return "ACTIVE"


def derive_policy_status(records: Iterable[PolicyLifecycleRecord]) -> Optional[str]:
    """Active lifecycle status = status of the highest lifecycle_sequence."""
    best: Optional[PolicyLifecycleRecord] = None
    for record in records:
        if best is None or record.lifecycle_sequence > best.lifecycle_sequence:
            best = record
    return best.status if best is not None else None


# ---------------------------------------------------------------------------
# PolicyIdentity rule (section 25A): nested refs must equal contract refs.
# ---------------------------------------------------------------------------

CONTRACT_REF_NAMES = (
    "routing_policy_ref",
    "optimization_policy_ref",
    "retry_policy_ref",
    "fallback_policy_ref",
    "verification_policy_ref",
    "audit_policy_ref",
    "override_policy_ref",
)
"""The seven TaskContract policy refs: the single sources of truth."""

POLICY_IDENTITY_RULES: Tuple[Tuple[str, str], ...] = (
    ("verification.retry_policy_ref", "retry_policy_ref"),
    ("audit.retry_policy_ref", "retry_policy_ref"),
    ("audit.override_policy_ref", "override_policy_ref"),
    ("failure_disposition.retry_policy_ref", "retry_policy_ref"),
    ("failure_disposition.fallback_policy_ref", "fallback_policy_ref"),
    ("failure_disposition.override_policy_ref", "override_policy_ref"),
)
"""Nested (policy, field) refs that MUST equal the active contract refs."""

VERIFICATION_FDP_BINDING = "verification.failure_disposition_policy_ref"
"""VerificationPolicy binds its FailureDispositionPolicy exactly (section 26A):
no dangling generic refs; an empty binding is a POLICY_CONFLICT."""


def enforce_policy_identity(
    contract_refs: Mapping[str, str],
    nested_refs: Mapping[str, str],
    delegations: Iterable[str] = (),
) -> bool:
    """Check nested policy refs against the active contract refs (section 25A).

    Every POLICY_IDENTITY_RULES entry must equal its contract ref unless the
    nested field is delegated by the contract. Conflict = POLICY_CONFLICT and
    execution is blocked. Returns True when identity holds.
    """
    delegated = set(delegations)
    for nested_name, contract_name in POLICY_IDENTITY_RULES:
        if nested_name in delegated:
            continue
        expected = contract_refs.get(contract_name)
        if nested_name in nested_refs and nested_refs[nested_name] != expected:
            raise manifest.PolicyConflictError(
                "POLICY_CONFLICT: nested ref %r (%r) differs from contract ref "
                "%r (%r); execution blocked (Manifest section 25A)"
                % (nested_name, nested_refs[nested_name], contract_name, expected)
            )
    if VERIFICATION_FDP_BINDING not in delegated and not nested_refs.get(
        VERIFICATION_FDP_BINDING
    ):
        raise manifest.PolicyConflictError(
            "POLICY_CONFLICT: %r is dangling; VerificationPolicy must bind "
            "its FailureDispositionPolicy exactly (Manifest section 26A)"
            % (VERIFICATION_FDP_BINDING,)
        )
    return True


# ---------------------------------------------------------------------------
# Counter records + atomic restart-safe counters (section 16, ports).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RetryRecord:
    """Manifest section 16 retry record. Immutable."""

    retry_id: str = ""
    project_id: str = ""
    task_id: str = ""
    run_id: Optional[str] = None
    reason: str = ""
    attempt: int = 0
    failed_AC: Tuple[str, ...] = ()
    evidence_ref: str = ""
    owner: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "failed_AC", _as_tuple(self.failed_AC))


@dataclass(frozen=True)
class FallbackRecord:
    """Manifest section 17 FallbackRecord. Immutable."""

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
class ReworkCounterRecord:
    """Manifest section 16 ReworkCounterRecord. Atomic updates, restart-safe."""

    counter_id: str = ""
    project_id: str = ""
    scope_type: str = ""
    scope_id: str = ""
    counter_type: ReworkCounterType = ReworkCounterType.RUNTIME_REWORK
    value: int = 0
    limit: int = 0
    updated_at: str = ""
    version: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "counter_type",
            _coerce_enum(self.counter_type, ReworkCounterType),
        )


@dataclass(frozen=True)
class FallbackCounterRecord:
    """Manifest section 16 FallbackCounterRecord. Scope RUN or TASK."""

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

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "scope_type",
            _coerce_enum(self.scope_type, FallbackCounterScope),
        )


class CounterLimitExceededError(Exception):
    """A counter increment was refused: the applicable limit is reached."""


class RestartSafeCounter(manifest.CounterStore):
    """Atomic restart-safe counter backing (Manifest section 16, ports).

    increment(scope, kind, limit) is atomic under a lock; restart recovery
    rebuilds state from committed counter records via rehydrate(), so the
    value never depends on process memory.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._values: Dict[Tuple[str, str], int] = {}

    def increment(self, scope: str, kind: str, limit: int) -> int:
        """Atomically bump (scope, kind); refuse past *limit*."""
        with self._lock:
            value = self._values.get((scope, kind), 0) + 1
            if value > limit:
                raise CounterLimitExceededError(
                    "counter (%r, %r) reached limit %d" % (scope, kind, limit)
                )
            self._values[(scope, kind)] = value
            return value

    @classmethod
    def rehydrate(cls, records: Iterable[Any]) -> "RestartSafeCounter":
        """Rebuild counter state from committed records (restart recovery)."""
        store = cls()
        for record in records:
            kind = getattr(record, "counter_type", None)
            if kind is None:
                kind = "fallback"
            else:
                kind = str(getattr(kind, "value", kind)).lower()
            scope_type = getattr(record, "scope_type", "")
            scope_type = getattr(scope_type, "value", scope_type)
            scope = "%s:%s" % (str(scope_type).lower(), getattr(record, "scope_id", ""))
            key = (scope, kind)
            store._values[key] = max(store._values.get(key, 0), record.value)
        return store


def bump_rework(record: ReworkCounterRecord, store: manifest.CounterStore) -> ReworkCounterRecord:
    """Return a NEW ReworkCounterRecord bumped atomically via *store*."""
    scope = "%s:%s" % (str(record.scope_type).lower(), record.scope_id)
    kind = str(record.counter_type.value).lower()
    return replace(
        record, value=store.increment(scope, kind, record.limit), version=record.version + 1
    )


def bump_fallback(record: FallbackCounterRecord, store: manifest.CounterStore) -> FallbackCounterRecord:
    """Return a NEW FallbackCounterRecord bumped atomically via *store*."""
    scope = "%s:%s" % (str(record.scope_type.value).lower(), record.scope_id)
    return replace(
        record, value=store.increment(scope, "fallback", record.limit), version=record.version + 1
    )


# ---------------------------------------------------------------------------
# DEFAULTS (section 16) and exhaustion rule (never automatic ESCALATE).
# ---------------------------------------------------------------------------

DEFAULTS: Dict[str, int] = {
    "executor_attempt_max": 3,
    "provider_retry_max": 2,
    "format_retry_max": 1,
    "verification_retry_max": 1,
    "audit_correction_max": 2,
    "verification_correction_max": 2,
    "runtime_correction_max": 3,
}
"""Manifest section 16 DEFAULTS (executor3/provider2/format1/verify1/corrections)."""


def default_retry_policy(
    policy_id: str = "retry-default", created_at: str = ""
) -> RetryPolicy:
    """The section 16 DEFAULTS as an immutable versioned RetryPolicy."""
    bare = RetryPolicy(
        policy_id=policy_id,
        version=1,
        created_at=created_at,
        executor_attempt_max=DEFAULTS["executor_attempt_max"],
        provider_retry_max=DEFAULTS["provider_retry_max"],
        format_retry_max=DEFAULTS["format_retry_max"],
        verification_retry_max=DEFAULTS["verification_retry_max"],
        verification_correction_max=DEFAULTS["verification_correction_max"],
        audit_correction_max=DEFAULTS["audit_correction_max"],
        runtime_correction_max=DEFAULTS["runtime_correction_max"],
    )
    return replace(bare, hash=compute_policy_hash(bare))


def is_exhausted(record: RetryRecord, policy: RetryPolicy) -> bool:
    """True when the retry attempt budget (executor_attempt_max) is spent."""
    return record.attempt >= policy.executor_attempt_max


def resolve_exhaustion(exhausted_class: str) -> manifest.AuditHandlingDisposition:
    """Exhaustion disposition (section 16): never automatic ESCALATE.

    retry_exhausted / fallback_exhausted follow the failure precedence to
    FAIL; ESCALATE only when the canonical disposition selects it, which this
    path never does on its own.
    """
    if exhausted_class not in ("retry_exhausted", "fallback_exhausted"):
        raise ValueError("unknown exhaustion class %r" % exhausted_class)
    return manifest.AuditHandlingDisposition.FAIL


def disposition_after_exhaustion(record: RetryRecord) -> str:
    """Handling name after retry exhaustion; never ESCALATE automatically."""
    return resolve_exhaustion("retry_exhausted").value


__all__ = [
    "PolicyLifecycleEvent",
    "ReworkCounterType",
    "FallbackCounterScope",
    "VerificationRequirement",
    "AuditRequirement",
    "RoutingPolicy",
    "OptimizationPolicy",
    "RetryPolicy",
    "FallbackPolicy",
    "VerificationPolicy",
    "AuditPolicy",
    "OverridePolicy",
    "FailureDispositionPolicy",
    "POLICY_FIELDS",
    "compute_policy_hash",
    "new_policy_version",
    "POLICY_LIFECYCLE_FIELDS",
    "PolicyLifecycleRecord",
    "derive_policy_status",
    "CONTRACT_REF_NAMES",
    "POLICY_IDENTITY_RULES",
    "VERIFICATION_FDP_BINDING",
    "enforce_policy_identity",
    "RetryRecord",
    "FallbackRecord",
    "ReworkCounterRecord",
    "FallbackCounterRecord",
    "CounterLimitExceededError",
    "RestartSafeCounter",
    "bump_rework",
    "bump_fallback",
    "DEFAULTS",
    "default_retry_policy",
    "is_exhausted",
    "resolve_exhaustion",
    "disposition_after_exhaustion",
]
