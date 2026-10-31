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


#: --- Additive M-ADMIT admission gate (B0B-BP02-63/68/77/88; new names only).
#: Four hard gates in a fixed order, every one fail-closed: tier (63,
#: UNKNOWN is never admitted and only routing-eligibility evidence
#: admits), health (68, only a healthy signal admits), gateway (77, idle
#: only, never forced), permission (88, only the allowlisted scope
#: admits). A refusal names its gate and records every ref supplied.
#: Pure: no IO, no mutation, standard library only.

#: Permission scopes that admit local contact (88; mirrors the frozen
#: settings allowlist: only this scope is servable).
ADMISSION_ALLOWED_PERMISSION_SCOPES = ("local-contact-allowed",)

#: SPEC 26 ROUTING_POLICY decision thresholds, highest branch first. A
#: score at or above a threshold takes that branch; a missing score or a
#: score below every threshold takes the NO-DATA branch.
ROUTING_POLICY_THRESHOLDS = (100, 85, 50)

#: SPEC 26 ROUTING_POLICY branch names aligned with the thresholds above.
ROUTING_POLICY_BRANCHES = ("A", "B", "C")

#: SPEC 26 branch taken with no usable score.
ROUTING_POLICY_NO_DATA_BRANCH = "NO-DATA"


@dataclass(frozen=True)
class AdmissionVerdict:
    admitted: bool
    reason: str
    admission_refs: tuple
    gate_allowed: bool
    admission_source: str


@dataclass(frozen=True)
class VerifierRecord:
    verifier_ref: str
    draft_ref: str
    draft_hash: str


def _is_healthy_signal(health_ref: object) -> bool:
    """True exactly for a healthy signal: carries ``healthy`` without an
    ``unhealthy`` marker. Anything else is refused, fail-closed."""
    lowered = health_ref.lower() if isinstance(health_ref, str) else ""
    return "healthy" in lowered and "unhealthy" not in lowered


#: Role levels the capability-tier gate serves (B0B-BP02-63): only a
#: named role level admits, and only with capability-tier evidence plus
#: a healthy signal plus an idle gateway. Any other level refuses.
_CAPABILITY_TIER_ROLE_LEVELS = ("quick", "standard", "deep")

#: Canonical role level evaluated by check_admission (B0B-BP02-63): the
#: tier/health/gateway gates are level-independent for valid levels, so
#: the production admission path evaluates them at the deepest level.
_CANONICAL_ADMIT_ROLE_LEVEL = "deep"


def capability_tier_admit(
    role_level: str,
    capability_store_ref: str,
    health_ref: str,
    gateway_state_ref: str,
) -> AdmissionVerdict:
    """Tier-plus-health-plus-gateway admission for one role level.

    Row B0B-BP02-63: a local candidate is admitted per role level only
    with capability-tier evidence plus a healthy signal plus an idle
    gateway. UNKNOWN is never admitted and a bare tier label never
    admits, mirroring check_eligibility so this gate is never weaker;
    only routing-eligibility evidence (or verified static capability)
    admits. The verdict records every ref supplied. check_admission
    calls this gate on the production admission path, then applies
    the permission gate.
    """
    _reject_role_config_ref(capability_store_ref, "capability store ref")
    level_text = role_level.lower() if isinstance(role_level, str) else ""
    admission_refs = (
        role_level,
        capability_store_ref,
        health_ref,
        gateway_state_ref,
    )
    admission_source = "capability-store/health/gateway"
    if level_text not in _CAPABILITY_TIER_ROLE_LEVELS:
        return AdmissionVerdict(
            admitted=False,
            reason=(
                "UNKNOWN_ROLE_LEVEL_REFUSED: role level "
                f"{role_level!r} names no servable role level; admission "
                "needs one of 'quick', 'standard' or 'deep'"
            ),
            admission_refs=admission_refs,
            gate_allowed=False,
            admission_source=admission_source,
        )
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
    if tier is EvidenceTier.UNKNOWN and not static_signal:
        return AdmissionVerdict(
            admitted=False,
            reason=(
                "UNKNOWN_TIER_INELIGIBLE: store ref "
                f"{capability_store_ref!r} carries only UNKNOWN evidence; "
                "UNKNOWN is never admitted"
            ),
            admission_refs=admission_refs,
            gate_allowed=gateway_allowed,
            admission_source=admission_source,
        )
    if tier is EvidenceTier.PROXY or not (
        _carries_routing_eligibility(lowered) or static_capability
    ):
        return AdmissionVerdict(
            admitted=False,
            reason=(
                f"{tier.value}_NOT_ROUTING_ELIGIBLE: store ref "
                f"{capability_store_ref!r} carries a {tier.value} tier label "
                "but no routing-eligibility evidence; MEASURED is not "
                "ROUTING_ELIGIBLE, admission only on evidence that reached "
                "the ROUTING_ELIGIBILITY lifecycle stage"
            ),
            admission_refs=admission_refs,
            gate_allowed=gateway_allowed,
            admission_source=admission_source,
        )
    if not _is_healthy_signal(health_ref):
        return AdmissionVerdict(
            admitted=False,
            reason=(
                "ADMISSION_HEALTH_REFUSED: health ref "
                f"{health_ref!r} does not report a healthy model; "
                "admission needs a healthy signal"
            ),
            admission_refs=admission_refs,
            gate_allowed=gateway_allowed,
            admission_source=admission_source,
        )
    if not gateway_allowed:
        return AdmissionVerdict(
            admitted=False,
            reason=(
                "GATEWAY_BUSY: gateway state ref "
                f"{gateway_state_ref!r} does not report an idle machine; "
                "local contact skipped, never forced"
            ),
            admission_refs=admission_refs,
            gate_allowed=gateway_allowed,
            admission_source=admission_source,
        )
    if static_capability and tier is not EvidenceTier.MEASURED:
        return AdmissionVerdict(
            admitted=True,
            reason=(
                "admitted: branch-B verified static capability with healthy "
                "signal and idle gateway; UNKNOWN is never admitted"
            ),
            admission_refs=admission_refs,
            gate_allowed=gateway_allowed,
            admission_source=admission_source,
        )
    return AdmissionVerdict(
        admitted=True,
        reason=(
            f"admitted: routing-eligibility evidence ({tier.value} tier) "
            "with healthy signal and idle gateway"
        ),
        admission_refs=admission_refs,
        gate_allowed=gateway_allowed,
        admission_source=admission_source,
    )


def check_admission(
    capability_store_ref: str,
    health_ref: str,
    gateway_state_ref: str,
    permission_scope: str,
) -> AdmissionVerdict:
    """Admission from tier plus health plus gateway plus permission.

    Tier (63) admits only routing-eligibility evidence, mirroring
    check_eligibility so this gate is never weaker: UNKNOWN is never
    admitted and a bare tier label never admits. Health (68) admits
    only a healthy signal. Gateway (77) admits only an idle machine,
    never forced. Permission (88) admits only the allowlisted scope.
    The verdict records every ref supplied. The tier/health/gateway
    gates evaluate through capability_tier_admit on the production
    admission path, so this gate is never weaker than the tier gate.
    """
    _reject_role_config_ref(capability_store_ref, "capability store ref")
    _reject_role_config_ref(permission_scope, "permission scope")
    admission_refs = (
        capability_store_ref,
        health_ref,
        gateway_state_ref,
        permission_scope,
    )
    admission_source = "capability-store/health/gateway/permission"
    gate = capability_tier_admit(
        _CANONICAL_ADMIT_ROLE_LEVEL,
        capability_store_ref,
        health_ref,
        gateway_state_ref,
    )
    if not gate.admitted:
        return AdmissionVerdict(
            admitted=False,
            reason=gate.reason,
            admission_refs=admission_refs,
            gate_allowed=gate.gate_allowed,
            admission_source=admission_source,
        )
    if not isinstance(permission_scope, str) or (
        permission_scope not in ADMISSION_ALLOWED_PERMISSION_SCOPES
    ):
        return AdmissionVerdict(
            admitted=False,
            reason=(
                "ADMISSION_PERMISSION_REFUSED: permission scope "
                f"{permission_scope!r} is not allowlisted for local "
                "contact; admission needs the servable scope"
            ),
            admission_refs=admission_refs,
            gate_allowed=gate.gate_allowed,
            admission_source=admission_source,
        )
    store_text = capability_store_ref if isinstance(capability_store_ref, str) else ""
    lowered = store_text.lower()
    if "measured" in lowered:
        tier = EvidenceTier.MEASURED
    elif "proxy" in lowered:
        tier = EvidenceTier.PROXY
    else:
        tier = EvidenceTier.UNKNOWN
    if _carries_static_capability(lowered) and tier is not EvidenceTier.MEASURED:
        return AdmissionVerdict(
            admitted=True,
            reason=(
                "admitted: branch-B verified static capability with healthy "
                "signal, idle gateway and allowlisted permission; "
                "UNKNOWN is never admitted"
            ),
            admission_refs=admission_refs,
            gate_allowed=gate.gate_allowed,
            admission_source=admission_source,
        )
    return AdmissionVerdict(
        admitted=True,
        reason=(
            f"admitted: routing-eligibility evidence ({tier.value} tier) "
            "with healthy signal, idle gateway and allowlisted permission"
        ),
        admission_refs=admission_refs,
        gate_allowed=gate.gate_allowed,
        admission_source=admission_source,
    )


#: --- Additive tool-agent registration (R-312; new names only). ---
#: Local runtimes attach on the served local entry and register as tool
#: agents only through the production admission path: check_admission
#: must admit the runtime's evidence, else the runtime stays
#: unregistered (a wrong permission scope refuses with
#: ADMISSION_PERMISSION_REFUSED and registers nothing). Registrations
#: are read-only history; entries are JSON-serializable.
_TOOL_AGENTS: dict = {}

_TOOL_AGENT_SEQ = itertools.count(1)


@dataclass(frozen=True)
class ToolAgentRegistration:
    registered: bool
    runtime_ref: str
    reason: str


def tool_agent_register(
    runtime_ref: str,
    capability_store_ref: str,
    health_ref: str,
    gateway_state_ref: str,
    permission_scope: str,
) -> ToolAgentRegistration:
    """Register a local runtime as a tool agent (R-312).

    The runtime registers and runs as a tool agent only when the
    production admission path (check_admission) admits its capability
    evidence with a healthy signal, an idle gateway and the allowlisted
    permission scope; any refusal registers nothing and names its gate.
    Every field must be a non-empty string where a ref belongs, and
    role-config fields are refused where task-class or model refs belong.
    """
    if not isinstance(runtime_ref, str) or not runtime_ref:
        raise ValueError(f"runtime_ref must be a non-empty string, got {runtime_ref!r}")
    _reject_role_config_ref(capability_store_ref, "capability store ref")
    _reject_role_config_ref(permission_scope, "permission scope")
    verdict = check_admission(
        capability_store_ref, health_ref, gateway_state_ref, permission_scope
    )
    if not verdict.admitted:
        return ToolAgentRegistration(
            registered=False,
            runtime_ref=runtime_ref,
            reason=verdict.reason,
        )
    agent_id = f"tool-agent-{next(_TOOL_AGENT_SEQ):04d}"
    registration = ToolAgentRegistration(
        registered=True,
        runtime_ref=runtime_ref,
        reason=(
            f"registered: local runtime {runtime_ref!r} admitted as tool "
            f"agent ({agent_id}) on evidence {verdict.admission_refs!r}; "
            "UNKNOWN is never admitted"
        ),
    )
    _TOOL_AGENTS[agent_id] = registration
    return registration


def record_verifier_decision(
    verifier_ref: str, draft_ref: str, draft_hash: str
) -> VerifierRecord:
    """Verifier record (B0B-UNCOVERED_MVP_ACCEPT-19): binds the verifier
    ref to the draft ref through the draft hash. Every field must be a
    non-empty string; role-config fields are refused where refs belong."""
    for name, value in (
        ("verifier_ref", verifier_ref),
        ("draft_ref", draft_ref),
        ("draft_hash", draft_hash),
    ):
        if not isinstance(value, str) or not value:
            raise ValueError(
                f"verifier refs must be non-empty strings: {name} is {value!r}"
            )
    _reject_role_config_ref(verifier_ref, "verifier ref")
    _reject_role_config_ref(draft_ref, "verifier draft ref")
    return VerifierRecord(
        verifier_ref=verifier_ref,
        draft_ref=draft_ref,
        draft_hash=draft_hash,
    )


def reexamine_verifier_content(
    record: VerifierRecord, content_text: str, content_hash: str
) -> bool:
    """Re-examine content (B0B-UNCOVERED_MVP_ACCEPT-57): True exactly
    when the supplied content is non-empty and its hash still equals the
    recorded draft hash. A mismatch or empty content is False, never an
    admission; misuse of the record shape raises ValueError."""
    if not isinstance(record, VerifierRecord):
        raise ValueError(f"record must be a VerifierRecord, got {record!r}")
    if not isinstance(content_text, str) or not content_text:
        return False
    if not isinstance(content_hash, str) or not content_hash:
        return False
    if not (record.verifier_ref and record.draft_ref and record.draft_hash):
        return False
    return content_hash == record.draft_hash


def confirm_verifier_link(record: VerifierRecord, draft_ref: str) -> bool:
    """Confirm link (B0B-UNCOVERED_MVP_ACCEPT-57): True exactly when the
    record carries complete refs and its draft ref equals the supplied
    draft ref. Anything else is False; misuse of the record shape raises
    ValueError."""
    if not isinstance(record, VerifierRecord):
        raise ValueError(f"record must be a VerifierRecord, got {record!r}")
    if not isinstance(draft_ref, str) or not draft_ref:
        return False
    if not (record.verifier_ref and record.draft_ref and record.draft_hash):
        return False
    return record.draft_ref == draft_ref


def route_by_policy(score: object) -> str:
    """SPEC 26 ROUTING_POLICY branch for a score: at or above 100 takes
    A, at or above 85 takes B, at or above 50 takes C; a missing score
    (None), a non-numeric score marker such as NaN, or a score below
    every threshold takes the NO-DATA branch. Booleans and other
    non-numeric types raise ValueError."""
    if score is None:
        return ROUTING_POLICY_NO_DATA_BRANCH
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise ValueError(f"score must be a number or None, got {score!r}")
    if score != score:
        return ROUTING_POLICY_NO_DATA_BRANCH
    for threshold, branch in zip(ROUTING_POLICY_THRESHOLDS, ROUTING_POLICY_BRANCHES):
        if score >= threshold:
            return branch
    return ROUTING_POLICY_NO_DATA_BRANCH


def recommend_split(summary: dict) -> dict:
    """Benchmark-steered cloud-vs-local split (M-P4-129).

    Pure: the verdict derives only from the passed summary dict; no IO,
    no network, no shared mutable state. UNKNOWN evidence never steers
    local: anything without usable measured evidence fails closed to
    "cloud". Standard or Deep levels steer local when measured evidence
    beats proxy.
    """
    if not isinstance(summary, dict):
        raise TypeError(
            "summary must be a dict, got %s" % type(summary).__name__
        )

    def _number(value: object) -> float | None:
        """Usable numeric score, else None (bools and NaN count as missing)."""
        if isinstance(value, bool):
            return None
        if not isinstance(value, (int, float)):
            return None
        as_float = float(value)
        if as_float != as_float:
            return None
        return as_float

    raw_level: object = None
    for _key in ("level", "bench_level", "depth"):
        if _key in summary:
            raw_level = summary[_key]
            break
    unwraps = 0
    while isinstance(raw_level, dict) and unwraps < 4:
        raw_level = raw_level.get("level")
        unwraps += 1
    if not isinstance(raw_level, str):
        enum_value = getattr(raw_level, "value", None)
        if isinstance(enum_value, str):
            raw_level = enum_value
    level_text = raw_level.strip().lower() if isinstance(raw_level, str) else ""
    order = ("quick", "standard", "deep")
    depth = order.index(level_text) if level_text in order else 0
    level_name = ("Quick", "Standard", "Deep")[depth]
    measured: float | None = None
    for _key in ("measured_score", "measured_share", "score", "measured"):
        if _key in summary:
            candidate = _number(summary[_key])
            if candidate is not None:
                measured = candidate
                break
    tier_raw: object = None
    for _key in ("tier", "evidence_tier", "evidence"):
        if _key in summary:
            tier_raw = summary[_key]
            break
    if isinstance(tier_raw, str):
        tier = tier_raw.strip().upper()
        if tier not in ("MEASURED", "PROXY", "UNKNOWN"):
            tier = "UNKNOWN"
    else:
        tier = None
    proxy: float | None = None
    for _key in ("proxy_score", "proxy_share", "proxy", "baseline_score"):
        if _key in summary:
            candidate = _number(summary[_key])
            if candidate is not None:
                proxy = candidate
                break
    baseline = proxy if proxy is not None else 0.0
    if tier == "UNKNOWN" or (measured is None and tier != "MEASURED"):
        return {
            "split": "cloud",
            "reason": (
                "CLOUD: no measured evidence (tier %s, no usable "
                "measured score); fail-closed to cloud"
                % (tier if tier is not None else "missing",)
            ),
        }
    if measured is not None and measured >= baseline and depth >= 1:
        return {
            "split": "local",
            "reason": (
                "LOCAL: %s level with measured %.6g >= proxy %.6g; "
                "benchmark evidence steers local"
                % (level_name, measured, baseline)
            ),
        }
    if measured is None:
        return {
            "split": "cloud",
            "reason": (
                "CLOUD: tier MEASURED without a numeric measured score "
                "at %s level; nothing measured to steer local"
                % (level_name,)
            ),
        }
    if depth < 1:
        return {
            "split": "cloud",
            "reason": (
                "CLOUD: %s level is shallower than Standard despite "
                "measured %.6g vs proxy %.6g; shallow level stays cloud"
                % (level_name, measured, baseline)
            ),
        }
    return {
        "split": "cloud",
        "reason": (
            "CLOUD: proxy %.6g beats measured %.6g at %s level; "
            "cloud wins" % (baseline, measured, level_name)
        ),
    }


#: Frozen function name to owning lane implementation (dotted path).
REALIZATION_MAP = {
    "check_eligibility": "agent_si.local.service.LocalAdapter.check_eligibility",
    "lifecycle_position": "agent_si.local.service.LifecycleService.position",
    "advance_lifecycle": "agent_si.local.service.LifecycleService.advance",
    "record_explicit_pin": "agent_si.local.service.LocalAdapter.record_explicit_pin",
    "record_split_decision": "agent_si.local.service.LocalAdapter.record_split_decision",
    "routing_continues": "agent_si.local.service.LocalAdapter.routing_continues",
    "check_admission": "agent_si.local.service.LocalAdapter.check_admission",
    "record_verifier_decision": "agent_si.local.service.LocalAdapter.record_verifier_decision",
    "reexamine_verifier_content": "agent_si.local.service.LocalAdapter.reexamine_verifier_content",
    "confirm_verifier_link": "agent_si.local.service.LocalAdapter.confirm_verifier_link",
    "route_by_policy": "agent_si.local.service.LocalAdapter.route_by_policy",
}
