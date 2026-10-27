"""K05 local-AI adapter interface (shapes only, no logic).

Frozen sources (read-only; 0C wins every clash):
RECORDS/day0/0C_ARCHITECTURE.md sec 6 (lifecycle SCAN to
ROUTING_ELIGIBILITY with no skips; local works without a
capability base under NOT_CONFIGURED while routing continues;
UNKNOWN never picked; every local decision records capability
evidence; explicit pin is UNVERIFIED with no measured evidence;
every SPLIT route carries local draft plus cloud verification
before audit) and sec 12 (K05 owns src/agent_si/local/),
RECORDS/day1/K04_INTERFACE.md plus the K04 frozen interface module
(QualityBasis values and the SPLIT atomic local_draft plus
cloud_verify refs are reused read-only, never redefined here).
Other packages code against this module only; lane internals
(names starting with _) are never imported. Every function
body is `...` (no logic): real behavior lives in the owning
lane module named in REALIZATION_MAP. Standard library only.
"""

from __future__ import annotations

import itertools
import os
from dataclasses import dataclass
from enum import Enum


class LifecycleStage(str, Enum):
    """Frozen 0C sec 6 order; stages advance one step at a time, no skips."""

    SCAN = "SCAN"
    DISCOVER = "DISCOVER"
    IDENTIFY = "IDENTIFY"
    REGISTER = "REGISTER"
    PROBE = "PROBE"
    BENCHMARK = "BENCHMARK"
    ROUTING_ELIGIBILITY = "ROUTING_ELIGIBILITY"


class EvidenceTier(str, Enum):
    """Local capability evidence tier; UNKNOWN is never picked."""

    UNKNOWN = "UNKNOWN"
    PROXY = "PROXY"
    MEASURED = "MEASURED"


#: Route recorded when the user explicitly pins a local model.
ROUTE_EXPLICIT_PIN = "EXPLICIT_MODEL_PIN"

#: Split route: a local draft plus a cloud verification, kept together.
ROUTE_SPLIT = "SPLIT"

#: Capability-base-absent status; routing continues normally.
STATUS_NOT_CONFIGURED = "NOT_CONFIGURED"

#: Frozen K05 local error-code names, each with one owning condition:
#: NOT_CONFIGURED (capability base absent; routing continues),
#: GATEWAY_BUSY (passive check refused; a user bench/test run is active),
#: LIFECYCLE_SKIP_REFUSED (an advance skips a lifecycle stage),
#: UNKNOWN_TIER_INELIGIBLE (an UNKNOWN tier was picked).
ERROR_CODES_LOCAL = (
    "NOT_CONFIGURED",
    "GATEWAY_BUSY",
    "LIFECYCLE_SKIP_REFUSED",
    "UNKNOWN_TIER_INELIGIBLE",
    "SESSION_TOKEN_REFUSED",
)


@dataclass(frozen=True)
class CapabilityEvidence:
    evidence_ref: str
    tier: EvidenceTier


@dataclass(frozen=True)
class EligibilityVerdict:
    eligible: bool
    reason: str
    evidence_refs: tuple
    gateway_allowed: bool
    eligibility_source: str


@dataclass(frozen=True)
class LocalDecision:
    decision_id: str
    project_id: str
    task_id: str
    run_id: str
    route: str
    quality_basis: str
    capability_evidence_refs: tuple
    measured_evidence_count: int


@dataclass(frozen=True)
class SplitAssignment:
    local_draft_ref: str
    cloud_verify_ref: str
    draft_hash: str


#: Frozen lifecycle order; positions are indices into this tuple.
_STAGE_ORDER = tuple(LifecycleStage)

#: Per-process run-identity fallbacks (generated, never None; env wins when set).
_FALLBACK_PROJECT_ID = f"local-project-{os.getpid()}"
_FALLBACK_TASK_ID = f"local-task-{os.getpid()}"
_FALLBACK_RUN_ID = f"local-run-{os.getpid()}"

#: Decision ids, unique per call in call order.
_DECISION_SEQ = itertools.count(1)


def _run_identity() -> tuple:
    """Run identity from env config, else per-process generated fallbacks."""
    project_id = os.environ.get("AGENT_SI_PROJECT_ID") or _FALLBACK_PROJECT_ID
    task_id = os.environ.get("AGENT_SI_TASK_ID") or _FALLBACK_TASK_ID
    run_id = os.environ.get("AGENT_SI_RUN_ID") or _FALLBACK_RUN_ID
    return project_id, task_id, run_id


#: Role-config field names are never capability task classes
#: (B0B-UNCOVERED_MVP_ACCEPT-223): a ref naming one of these is refused,
#: never accepted as capability evidence. Grounded in the local settings
#: module (EXPLICIT_CONFIG_FIELDS, LocalAIConfig fields, dotted
#: settings.localAi view keys and their trailing segments). Entries are
#: lowercase: candidates are lowercased before comparison.
_ROLE_CONFIG_FIELDS = frozenset(
    {
        "endpoint_url",
        "model_id",
        "permission_scope",
        "local_only_mode",
        "project_key",
        "capability_evidence",
        "title",
        "purpose",
        "needitnow",
        "settings.localai.title",
        "settings.localai.purpose",
        "settings.localai.needitnow",
    }
)

#: Refusal code shared with the capability-store side guard: a role-config
#: field presented where a task class or model ref is required.
_ROLE_CONFIG_AS_TASK_CLASS_REFUSED = "CAPABILITY_ROLE_CONFIG_AS_TASK_CLASS_REFUSED"


def _ref_task_candidate(ref_text: str) -> str:
    """Task-class candidate carried by a store ref: the whole ref, or the
    task segment of a stable ``cap:<model>:<task>:v1`` ref, or the tail of a
    ``head:tail`` ref. Compared lowercased against _ROLE_CONFIG_FIELDS."""
    text = ref_text.strip().lower()
    if text.startswith("cap:"):
        body = text[len("cap:"):]
        if body.endswith(":v1"):
            body = body[: -len(":v1")]
        if ":" in body:
            _model, task = body.split(":", 1)
            return task.strip()
        return body.strip()
    if ":" in text:
        _head, tail = text.split(":", 1)
        return tail.strip()
    return text


def _reject_role_config_ref(value: object, kind: str) -> None:
    """Refuse a role-config field where a task class or model ref is required."""
    text = value if isinstance(value, str) else ""
    candidate = _ref_task_candidate(text)
    if candidate in _ROLE_CONFIG_FIELDS:
        raise Exception(
            f"{_ROLE_CONFIG_AS_TASK_CLASS_REFUSED}: {kind} "
            f"{value!r} names a role-config field, never a capability "
            "task class; role config fields are not capability evidence"
        )


def _carries_routing_eligibility(ref_lowered: str) -> bool:
    """True exactly for routing-eligibility evidence: a structured store
    evidence ref (stable ``cap:`` refs, contract ``store-ref-`` refs) or an
    explicit ROUTING_ELIGIBILITY lifecycle-stage marker. A bare tier label
    (``measured``/``proxy`` alone) is not evidence and never qualifies:
    MEASURED is not ROUTING_ELIGIBLE."""
    text = ref_lowered.strip()
    if text.startswith("cap:") or text.startswith("store-ref"):
        return True
    normalized = text.replace("_", "-")
    return "routing-eligib" in normalized or "routingeligib" in normalized


def _carries_static_capability(ref_lowered: str) -> bool:
    """True exactly for branch-B evidence: a structured store evidence ref
    (stable ``cap:`` refs, contract ``store-ref-`` refs) carrying a
    verified-static-capability signal. A bare static label alone is not
    evidence and never qualifies, mirroring branch A."""
    text = ref_lowered.strip().replace("_", "-")
    if "static-verified" not in text:
        return False
    return text.startswith("cap:") or text.startswith("store-ref")


def check_eligibility(capability_store_ref: str, gateway_state_ref: str) -> EligibilityVerdict:
    """Eligibility from routing-eligibility evidence plus gateway state.

    Branch A is benchmark evidence (a structured store evidence ref
    carrying a MEASURED signal, or an explicit ROUTING_ELIGIBILITY stage
    marker); branch B is verified static capability (a structured store
    evidence ref carrying a static-verified signal, no benchmark needed).
    A bare tier label (``measured``/``proxy``/``static-verified`` alone) is
    not routing eligibility and never yields eligible=True; MEASURED is not
    ROUTING_ELIGIBLE. UNKNOWN is never picked. The verdict records the
    evidence refs used. A non-idle gateway refuses every branch.
    """
    _reject_role_config_ref(capability_store_ref, "capability store ref")
    store_text = capability_store_ref if isinstance(capability_store_ref, str) else ""
    lowered = store_text.lower()
    static_capability = _carries_static_capability(lowered)
    static_signal = "static-verified" in lowered.replace("_", "-")
    if "measured" in lowered:
        tier = EvidenceTier.MEASURED
    elif "proxy" in lowered:
        tier = EvidenceTier.PROXY
    else:
        tier = EvidenceTier.UNKNOWN
    gateway_text = gateway_state_ref if isinstance(gateway_state_ref, str) else ""
    gateway_lowered = gateway_text.lower()
    gateway_allowed = "idle" in gateway_lowered and "running" not in gateway_lowered
    evidence_refs = (capability_store_ref, gateway_state_ref)
    eligibility_source = "capability-store/gateway"
    if tier is EvidenceTier.UNKNOWN and not static_signal:
        return EligibilityVerdict(
            eligible=False,
            reason=(
                "UNKNOWN_TIER_INELIGIBLE: store ref "
                f"{capability_store_ref!r} carries only UNKNOWN evidence; "
                "UNKNOWN is never picked"
            ),
            evidence_refs=evidence_refs,
            gateway_allowed=gateway_allowed,
            eligibility_source=eligibility_source,
        )
    if not gateway_allowed:
        return EligibilityVerdict(
            eligible=False,
            reason=(
                "GATEWAY_BUSY: gateway state ref "
                f"{gateway_state_ref!r} does not report an idle machine; "
                "local contact skipped, never forced"
            ),
            evidence_refs=evidence_refs,
            gateway_allowed=gateway_allowed,
            eligibility_source=eligibility_source,
        )
    if tier is EvidenceTier.PROXY or not (
        _carries_routing_eligibility(lowered) or static_capability
    ):
        return EligibilityVerdict(
            eligible=False,
            reason=(
                f"{tier.value}_NOT_ROUTING_ELIGIBLE: store ref "
                f"{capability_store_ref!r} carries a {tier.value} tier label "
                "but no routing-eligibility evidence; MEASURED is not "
                "ROUTING_ELIGIBLE, eligible only on evidence that reached "
                "the ROUTING_ELIGIBILITY lifecycle stage"
            ),
            evidence_refs=evidence_refs,
            gateway_allowed=gateway_allowed,
            eligibility_source=eligibility_source,
        )
    if static_capability and tier is not EvidenceTier.MEASURED:
        return EligibilityVerdict(
            eligible=True,
            reason=(
                "eligible: branch-B verified static capability in "
                f"store ref {capability_store_ref!r} with an idle gateway; "
                "UNKNOWN is never picked"
            ),
            evidence_refs=evidence_refs,
            gateway_allowed=gateway_allowed,
            eligibility_source=eligibility_source,
        )
    return EligibilityVerdict(
        eligible=True,
        reason=(
            f"eligible: routing-eligibility evidence ({tier.value} tier) in "
            f"store ref {capability_store_ref!r}; gateway idle"
        ),
        evidence_refs=evidence_refs,
        gateway_allowed=gateway_allowed,
        eligibility_source=eligibility_source,
    )


def lifecycle_position(stage: LifecycleStage) -> int:
    """Zero-based position of a stage in the frozen lifecycle order."""
    return _STAGE_ORDER.index(stage)


def advance_lifecycle(current: LifecycleStage, target: LifecycleStage) -> LifecycleStage:
    """One-step advance only; skipping a stage refuses with LIFECYCLE_SKIP_REFUSED."""
    try:
        current_pos = _STAGE_ORDER.index(current)
        target_pos = _STAGE_ORDER.index(target)
    except ValueError:
        raise Exception(
            "LIFECYCLE_SKIP_REFUSED: unknown lifecycle stage in advance from "
            f"{current!r} to {target!r}; single-step advance only"
        ) from None
    if target_pos == current_pos + 1:
        return _STAGE_ORDER[target_pos]
    raise Exception(
        "LIFECYCLE_SKIP_REFUSED: advance from "
        f"{_STAGE_ORDER[current_pos].value} to {_STAGE_ORDER[target_pos].value} "
        "is not a single step; stages advance one at a time, no skips"
    )


def record_explicit_pin(model_ref: str) -> LocalDecision:
    """User pin: route EXPLICIT_MODEL_PIN, UNVERIFIED quality, zero measured evidence."""
    _reject_role_config_ref(model_ref, "pin model ref")
    project_id, task_id, run_id = _run_identity()
    return LocalDecision(
        decision_id=f"local-decision-{next(_DECISION_SEQ):06d}",
        project_id=project_id,
        task_id=task_id,
        run_id=run_id,
        route=ROUTE_EXPLICIT_PIN,
        quality_basis="UNVERIFIED_PIN",
        capability_evidence_refs=(model_ref,),
        measured_evidence_count=0,
    )


def record_split_decision(local_draft_ref: str, cloud_verify_ref: str, draft_hash: str) -> SplitAssignment:
    """SPLIT carries the local draft plus the cloud verify refs atomically, bound by the draft hash; cloud verification runs before audit."""
    for name, value in (
        ("local_draft_ref", local_draft_ref),
        ("cloud_verify_ref", cloud_verify_ref),
        ("draft_hash", draft_hash),
    ):
        if not isinstance(value, str) or not value:
            raise ValueError(f"SPLIT refs must be non-empty strings: {name} is {value!r}")
    return SplitAssignment(
        local_draft_ref=local_draft_ref,
        cloud_verify_ref=cloud_verify_ref,
        draft_hash=draft_hash,
    )


def routing_continues(status: str) -> bool:
    """True exactly when routing continues normally, including under NOT_CONFIGURED."""
    return status == STATUS_NOT_CONFIGURED


#: Frozen function name to owning lane implementation (dotted path).
REALIZATION_MAP = {
    "check_eligibility": "agent_si.local.service.LocalAdapter.check_eligibility",
    "lifecycle_position": "agent_si.local.service.LifecycleService.position",
    "advance_lifecycle": "agent_si.local.service.LifecycleService.advance",
    "record_explicit_pin": "agent_si.local.service.LocalAdapter.record_explicit_pin",
    "record_split_decision": "agent_si.local.service.LocalAdapter.record_split_decision",
    "routing_continues": "agent_si.local.service.LocalAdapter.routing_continues",
}
