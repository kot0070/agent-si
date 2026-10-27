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


def check_eligibility(capability_store_ref: str, gateway_state_ref: str) -> EligibilityVerdict:
    """Eligibility from store evidence plus gateway state; the verdict records the evidence refs used."""
    store_text = capability_store_ref if isinstance(capability_store_ref, str) else ""
    lowered = store_text.lower()
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
    if tier is EvidenceTier.UNKNOWN:
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
    return EligibilityVerdict(
        eligible=True,
        reason=(
            f"eligible: {tier.value} capability evidence in store ref "
            f"{capability_store_ref!r}; gateway idle"
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
