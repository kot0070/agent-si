# K04 Lane A2 — canonical 11-step model router (selection only, never invokes SDKs).
# Implements spec section 24 order; optimization never overrides hard
# eligibility; quality >= required AND risk <= max come before cost.
"""ModelRouter: hard capability -> provider capability -> provider health ->
model health -> security risk -> routing policy -> resources -> budget ->
quality threshold -> optimization -> fallback chain."""

from __future__ import annotations

import hashlib
import threading
import uuid
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, Tuple

from . import types as T
from .kb_port import KbModelFacts, KbReader
from .telemetry_port import TelemetryEmitter, routing_event
from agent_si.context_keeper.register import DevelopmentBindingScopeError
from agent_si.context_keeper.register import check_development_binding_use

if TYPE_CHECKING:
    from .interface import CandidateView, RoutingDecision

UNKNOWN_PRICE_PENALTY = 1e12
LOCAL_DRAFT_MIN_RATE = 0.50

#: Named refusal when high-risk reasoning is asked of a candidate that
#: is not measured-capable (K04OPEN3 M1, row 1605).
HIGH_RISK_CANDIDATE_NOT_MEASURED_CAPABLE = \
    "HIGH_RISK_CANDIDATE_NOT_MEASURED_CAPABLE"
#: Named refusal when the high-risk endpoint gets a non-high task risk.
HIGH_RISK_TASK_RISK_REQUIRED = "HIGH_RISK_TASK_RISK_REQUIRED"


def _new_id(prefix: str) -> str:
    return "%s-%s" % (prefix, uuid.uuid4().hex[:12])


# --------------------------------------------------------------------------
# Request / deps / outcome

@dataclass(frozen=True)
class RoutingRequest:
    project_id: str
    task_id: str
    run_id: str
    role: str
    task_class: str
    routing_policy: T.RoutingPolicy
    optimization_policy: T.OptimizationPolicy
    candidates: tuple = ()
    required_capabilities: tuple = ("text",)
    required_modalities: tuple = ("text",)
    task_risk: str = "LOW"
    mode: str = "AUTO"
    pinned_provider: object = None
    pinned_model: object = None
    override_provider: object = None
    override_model: object = None
    excluded_models: tuple = ()
    exclude_pairs: tuple = ()
    preferred_route: object = None
    preferred_strategy: object = None
    ranking: str = "optimal"
    turn_cap: object = None
    director_pick_provider: object = None
    director_pick_model: object = None
    subtask_id: object = None
    stage: object = None
    manager_trigger: object = None
    manager_trigger_ref: object = None
    tolerant_parser: bool = False
    retry_policy_ref: object = None
    fallback_policy_ref: object = None
    verification_policy_ref: object = None
    audit_policy_ref: object = None
    override_policy_ref: object = None
    max_tokens: object = None

    def __post_init__(self):
        if self.role not in T.ROLES:
            raise ValueError("invalid role: %r" % (self.role,))
        if self.mode not in ("AUTO", "PINNED", "pool"):
            raise ValueError("invalid mode: %r" % (self.mode,))
        if self.ranking not in ("optimal", "listed"):
            raise ValueError("invalid ranking: %r" % (self.ranking,))
        T.check_enum("task_risk", self.task_risk, T.RISK_LEVELS)


@dataclass(frozen=True)
class RoutingDeps:
    kb: KbReader
    provider_health: Mapping = None
    model_health: Mapping = None
    provider_capabilities: Mapping = None
    resource_state: object = None
    budget_state: object = None
    manager_profile: object = None
    store: object = None
    emitter: object = None


@dataclass(frozen=True)
class RoutingOutcome:
    status: str  # ROUTED | BLOCKED
    decision: T.RoutingDecision
    assignments: tuple
    snapshot: T.RoutingEvidenceSnapshot
    trace: tuple


# --------------------------------------------------------------------------
# Internal candidate evaluation

@dataclass
class _Eval:
    candidate: T.CandidateModel
    facts: Optional[KbModelFacts]
    index: int
    passed: bool = True
    failed_step: str = ""
    fail_detail: str = ""
    missing_caps: Tuple[str, ...] = ()
    branch: str = ""
    capability_state: str = "UNKNOWN"
    required_verification: str = "STANDARD"
    quality: Optional[float] = None
    fit: Optional[float] = None
    cost_per_1k: Optional[float] = None
    cost_known: bool = False
    latency_ms: Optional[float] = None
    local_route: str = ""  # LOCAL | SPLIT_ONLY | CLOUD_ONLY | NO
    score: float = 0.0

    @property
    def provider(self) -> str:
        return self.candidate.provider

    @property
    def model(self) -> str:
        return self.candidate.model


def _effective_caps(provider_caps, facts: Optional[KbModelFacts]):
    if facts is None:
        return None
    return set(provider_caps or ()) & set(facts.modalities or ())


def measured_capable(facts: Optional[KbModelFacts], policy) -> bool:
    """Row 1605 shared predicate: MEASURED evidence meeting policy bars.

    Mirrors the CAPABILITY_EVIDENCE branch condition restricted to
    MEASURED fields_state: the same sample/confidence/freshness bars the
    selection path enforces. Shared by the in-selection high-risk gate
    below and the served high-risk endpoint so the two never drift.
    """
    if facts is None:
        return False
    return (facts.fields_state == "MEASURED"
            and facts.strict_pass_rate is not None
            and facts.sample_count is not None
            and facts.sample_count >= policy.sample_min
            and facts.confidence is not None
            and facts.confidence >= policy.confidence_min
            and _fresh_ok(facts.freshness, policy.freshness_requirement))


#: Optimization Policy view fields (ARCH-528): required quality, risk
#: ceiling and weights, read off the real OptimizationPolicy.
POLICY_VIEW_FIELDS = (
    "required_quality", "max_risk", "weight_quality", "weight_cost",
    "weight_latency", "weight_cloud_tokens",
)


def optimization_policy_view(opt) -> dict:
    """ARCH-528 Optimization Policy view (kit/BUILD_PLAN.md:1594).

    Quote kit/BUILD_PLAN.md:1594 B0B-UNCOVERED_ARCH-528: "The AI
    SETTINGS Optimization Policy view presents required quality and
    risk ceiling and weights and". Presents required quality, risk
    ceiling and weights derived from the real OptimizationPolicy (or
    an equivalent mapping); missing values raise ValueError, never a
    guessed default. Production callers: _finish and blocked_outcome
    below (every decision reason carries this view on the served
    routing entry).
    """
    if opt is None:
        raise ValueError(
            "optimization_policy_view needs an OptimizationPolicy, "
            "got None")
    try:
        if hasattr(opt, "get") and not hasattr(opt, "required_quality"):
            values = {name: opt.get(name) for name in POLICY_VIEW_FIELDS}
            extra = {"policy_id": opt.get("policy_id"),
                     "version": opt.get("version")}
        else:
            values = {name: getattr(opt, name)
                      for name in POLICY_VIEW_FIELDS}
            extra = {"policy_id": getattr(opt, "policy_id", None),
                     "version": getattr(opt, "version", None)}
    except AttributeError as exc:
        raise ValueError(
            "optimization_policy_view: policy shape missing %s" % (exc,)
        ) from None
    missing = sorted(name for name, value in values.items()
                     if value is None)
    if missing:
        raise ValueError(
            "optimization_policy_view: policy missing %s"
            % ", ".join(missing))
    view = dict(extra)
    view.update(values)
    return view


def _policy_view_text(opt) -> str:
    """Evidence-only reason rendering of optimization_policy_view.

    Returns "" on any failure so rendering never breaks selection.
    """
    try:
        view = optimization_policy_view(opt)
    except Exception:
        return ""
    return ("policy_view=required_quality>=%s max_risk<=%s "
            "weight_quality=%s weight_cost=%s weight_latency=%s "
            "weight_cloud_tokens=%s"
            % (view["required_quality"], view["max_risk"],
               view["weight_quality"], view["weight_cost"],
               view["weight_latency"], view["weight_cloud_tokens"]))


def _pricing_version_id(provider, model, input_price, output_price) -> str:
    """Deterministic version id for one provider/model/price triple."""
    raw = "|".join((str(provider), str(model), str(input_price),
                    str(output_price)))
    return "psnap-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _record_winner_pricing(request, deps, winner) -> str:
    """ARCH-424 winner-price evidence (kit/BUILD_PLAN.md:1643).

    Records the routed winner's known prices as a new immutable
    PricingSnapshot version through the bound BudgetGate registry
    (BudgetGate.publish_pricing_snapshot, guarded by
    pricing_snapshot_immutable in agent_si.budget.gate); versions
    accumulate, old rows are never rewritten. Evidence only: returns
    "" unless the winner has known prices and a versioned registry is
    bound, and never raises into selection.
    """
    try:
        gate = getattr(deps, "budget_state", None)
        publish = getattr(gate, "publish_pricing_snapshot", None)
        if publish is None or winner is None:
            return ""
        if not getattr(winner, "cost_known", False):
            return ""
        facts = getattr(winner, "facts", None)
        if facts is None:
            return ""
        candidate = getattr(winner, "candidate", None)
        provider = getattr(facts, "provider", None) or getattr(
            candidate, "provider", None)
        model = getattr(facts, "model", None) or getattr(
            candidate, "model", None)
        if not provider or not model:
            return ""
        input_price = getattr(facts, "input_price", None)
        output_price = getattr(facts, "output_price", None)
        if input_price is None or output_price is None:
            return ""
        stored = publish({
            "pricing_snapshot_id": _pricing_version_id(
                provider, model, input_price, output_price),
            "provider_id": provider, "model_id": model,
            "currency": None, "effective_at": T.utcnow(),
            "source": "routing-decision",
            "input_token_price": input_price,
            "output_token_price": output_price,
            "cached_token_price": None, "reasoning_token_price": None,
            "request_price": None, "other_rules": [],
            "created_at": T.utcnow(), "hash": "",
        })
        if isinstance(stored, Mapping):
            stored_id = stored.get("pricing_snapshot_id")
        else:
            stored_id = getattr(stored, "pricing_snapshot_id", None)
        if not stored_id:
            return ""
        return "pricing_snapshot=%s" % (stored_id,)
    except Exception:
        return ""


def _evaluate(request: RoutingRequest, deps: RoutingDeps,
              candidate: T.CandidateModel, index: int,
              pin: Optional[Tuple[str, str]]) -> Tuple[_Eval, List[T.GateTrace]]:
    ev = _Eval(candidate=candidate,
               facts=deps.kb.facts(candidate.provider, candidate.model),
               index=index)
    traces: List[T.GateTrace] = []

    def fail(step: str, detail: str) -> Tuple[_Eval, List[T.GateTrace]]:
        ev.passed = False
        ev.failed_step = step
        ev.fail_detail = detail
        traces.append(T.GateTrace(step, candidate.provider, candidate.model,
                                  False, detail))
        return ev, traces

    def ok(step: str, detail: str = "") -> None:
        traces.append(T.GateTrace(step, candidate.provider, candidate.model,
                                  True, detail))

    is_pin = pin is not None and (candidate.provider, candidate.model) == pin
    # UID-33 scope gate: the agent_si development binding applies only to
    # the product development process; AUTO selection never adopts it
    # (the refusal names the candidate, other candidates still route).
    # An explicit PINNED choice stays the user's call.
    try:
        check_development_binding_use(
            provider=candidate.provider, model=candidate.model,
            use=("explicit-pinned-choice" if is_pin else "auto-selection"))
    except DevelopmentBindingScopeError as exc:
        return fail("DEV_BINDING_SCOPE", str(exc))
    required = set(request.required_capabilities or ()) | set(request.required_modalities or ())
    provider_caps = tuple((deps.provider_capabilities or {}).get(candidate.provider, ()))
    effective = _effective_caps(provider_caps, ev.facts)

    # Step 1 — hard capability: effective = provider x model (section 34A).
    if effective is None:
        if is_pin:
            ok("HARD_CAPABILITY_FILTER", "pin: no KB row, not known-incompatible")
        else:
            return fail("HARD_CAPABILITY_FILTER",
                        "no capability data (UNKNOWN never capable)")
    elif not required <= set(effective):
        missing = sorted(required - set(effective))
        ev.missing_caps = tuple(missing)
        if is_pin:
            return fail("HARD_CAPABILITY_FILTER",
                        "pin known-incompatible, missing %s" % ",".join(missing))
        return fail("HARD_CAPABILITY_FILTER",
                    "missing capabilities %s" % ",".join(missing))
    else:
        ok("HARD_CAPABILITY_FILTER", "effective covers %d required" % len(required))

    # Step 2 — provider capability.
    if not required <= set(provider_caps):
        if not (is_pin and ev.facts is None):
            missing = sorted(required - set(provider_caps))
            return fail("PROVIDER_CAPABILITY_FILTER",
                        "provider lacks %s" % ",".join(missing))
    ok("PROVIDER_CAPABILITY_FILTER")

    # Step 3 — provider health (fail closed on unknown).
    phealth = (deps.provider_health or {}).get(candidate.provider)
    if phealth is None or phealth.status != "ONLINE":
        seen = phealth.status if phealth is not None else "unknown"
        return fail("PROVIDER_HEALTH_FILTER", "provider status %s" % seen)
    ok("PROVIDER_HEALTH_FILTER", "provider ONLINE")

    # Step 4 — model health (fail closed on unknown).
    mhealth = (deps.model_health or {}).get((candidate.provider, candidate.model))
    if mhealth is None or mhealth.status != "READY":
        seen = mhealth.status if mhealth is not None else "unknown"
        return fail("MODEL_HEALTH_FILTER", "model status %s" % seen)
    ok("MODEL_HEALTH_FILTER", "model READY")

    # Step 5 — security/risk: assessed risk must fit max_risk.
    opt = request.optimization_policy
    if ev.facts is not None:
        if ev.facts.assessed_risk not in T.RISK_LEVELS:
            return fail("SECURITY_RISK_FILTER",
                        "assessed risk %r not a RiskLevel" % (ev.facts.assessed_risk,))
        if not T.risk_at_most(ev.facts.assessed_risk, opt.max_risk):
            return fail("SECURITY_RISK_FILTER",
                        "assessed risk %s exceeds max %s"
                        % (ev.facts.assessed_risk, opt.max_risk))
        ok("SECURITY_RISK_FILTER",
           "risk %s within max %s" % (ev.facts.assessed_risk, opt.max_risk))
    else:
        ok("SECURITY_RISK_FILTER", "pin: no assessed risk on file")

    # Step 6 — routing policy + eligibility branch (A/B/C) + LOCAL bars.
    policy = request.routing_policy
    if policy.cloud_required and candidate.provider_type != "cloud":
        return fail("ROUTING_POLICY_FILTER", "policy requires cloud")
    if not policy.local_allowed and candidate.provider_type == "local":
        return fail("ROUTING_POLICY_FILTER", "policy forbids local")
    if is_pin or (request.override_provider is not None and
                  (candidate.provider, candidate.model) ==
                  (request.override_provider, request.override_model)):
        ev.branch = "EXPLICIT_MODEL_PIN"
        ev.capability_state = "UNVERIFIED"
        ev.required_verification = "ENHANCED"
        ok("ROUTING_POLICY_FILTER", "explicit pin (UNVERIFIED, ENHANCED)")
    elif ev.facts is not None and ev.facts.verified_static:
        ev.branch = "VERIFIED_STATIC_CAPABILITY"
        ev.capability_state = (ev.facts.fields_state
                               if ev.facts.fields_state in ("MEASURED", "PROXY")
                               else "UNVERIFIED")
        ok("ROUTING_POLICY_FILTER", "verified static capability")
    elif (ev.facts is not None and ev.facts.fields_state in ("MEASURED", "PROXY")
          and ev.facts.strict_pass_rate is not None
          and ev.facts.sample_count is not None
          and ev.facts.sample_count >= policy.sample_min
          and ev.facts.confidence is not None
          and ev.facts.confidence >= policy.confidence_min
          and _fresh_ok(ev.facts.freshness, policy.freshness_requirement)):
        ev.branch = "CAPABILITY_EVIDENCE"
        ev.capability_state = ev.facts.fields_state
        ok("ROUTING_POLICY_FILTER",
           "measured evidence branch (sample/conf/freshness hold)")
    else:
        return fail("ROUTING_POLICY_FILTER",
                    "no valid evidence branch (need measured evidence, "
                    "verified static capability, or explicit pin)")

    # ARCH-726 capable gate: high-risk reasoning plus final verification
    # run only on measured capable candidates. An explicit PINNED choice
    # keeps its ENHANCED verification; every other non-measured branch
    # fails here, before quality or cost are even considered.
    if request.task_risk in ("HIGH", "CRITICAL"):
        if ev.branch == "CAPABILITY_EVIDENCE" \
                and ev.capability_state == "MEASURED":
            ev.required_verification = "FINAL_VERIFICATION"
            ok("CAPABLE_GATE",
               "high-risk on a measured capable candidate "
               "(final verification required)")
        elif ev.branch != "EXPLICIT_MODEL_PIN":
            return fail(
                "CAPABLE_GATE",
                "high-risk task needs a measured capable candidate "
                "(got %s/%s)" % (ev.branch, ev.capability_state))

    # Route tag for local candidates (bootstrap 100/85/50 thresholds).
    if candidate.provider_type == "local":
        if ev.branch == "EXPLICIT_MODEL_PIN":
            ev.local_route = "LOCAL"
        elif ev.facts is not None and ev.facts.fields_state == "MEASURED":
            strict = ev.facts.strict_pass_rate or 0.0
            tolerant = ev.facts.tolerant_pass_rate if ev.facts.tolerant_pass_rate is not None else 0.0
            if strict >= policy.strict_min:
                ev.local_route = "LOCAL"
            elif request.tolerant_parser and tolerant >= policy.tolerant_min:
                ev.local_route = "LOCAL"
            elif max(strict, tolerant) >= LOCAL_DRAFT_MIN_RATE:
                ev.local_route = "SPLIT_ONLY"
            else:
                return fail("ROUTING_POLICY_FILTER",
                            "local rate below bootstrap thresholds (need >= %.2f for draft)"
                            % LOCAL_DRAFT_MIN_RATE)
        else:
            return fail("ROUTING_POLICY_FILTER",
                        "local route needs MEASURED evidence")
        ok("ROUTING_POLICY_FILTER", "local route tag %s" % ev.local_route)

    # Steps 7/8 — resource + budget: enforce snapshots when provided,
    # emit refs either way (the gates themselves run later at the gate).
    resource = deps.resource_state
    if isinstance(resource, Mapping) and resource.get("eligible") is False:
        return fail("RESOURCE_SCHEDULER_FILTER", "resource precheck ineligible")
    ok("RESOURCE_SCHEDULER_FILTER")
    budget = deps.budget_state
    billable = candidate.provider_type == "cloud"
    if (isinstance(budget, Mapping) and budget.get("eligible") is False
            and billable):
        return fail("BUDGET_ELIGIBILITY_FILTER", "budget eligibility refused")
    ok("BUDGET_ELIGIBILITY_FILTER")

    # Step 9 — quality threshold (quality >= required before cost).
    # A local draft in the SPLIT band (>= draft floor) stays eligible: the
    # cloud verifier enforces the final bar over the draft output.
    if ev.facts is not None and ev.branch == "CAPABILITY_EVIDENCE":
        strict = ev.facts.strict_pass_rate
        tolerant = ev.facts.tolerant_pass_rate
        ev.quality = strict if strict is not None else tolerant
        if ev.quality is not None and ev.quality < opt.required_quality:
            if (ev.candidate.provider_type == "local"
                    and ev.quality >= LOCAL_DRAFT_MIN_RATE):
                ok("QUALITY_THRESHOLD",
                   "draft-band quality %.2f (cloud verify required)"
                   % ev.quality)
            else:
                return fail("QUALITY_THRESHOLD",
                            "quality %.2f below required %.2f"
                            % (ev.quality, opt.required_quality))
    elif ev.branch == "VERIFIED_STATIC_CAPABILITY":
        ev.quality = (ev.facts.strict_pass_rate if ev.facts is not None else None)
    else:
        ev.quality = None  # pin: quality enforced later by ENHANCED verification
    ok("QUALITY_THRESHOLD")

    # Row 1605 — high-risk reasoning/final-verification gate: a
    # measured-capable candidate (CAPABILITY_EVIDENCE with MEASURED
    # state) routed for a HIGH/CRITICAL-risk task needs ENHANCED (final)
    # verification. Pins, verified-static capability and other branches
    # keep their own level; lower-risk tasks are unaffected.
    if (ev.branch == "CAPABILITY_EVIDENCE"
            and measured_capable(ev.facts, policy)
            and request.task_risk in ("HIGH", "CRITICAL")
            and ev.required_verification != "FINAL_VERIFICATION"):
        ev.required_verification = "ENHANCED"
        ok("HIGH_RISK_VERIFICATION_GATE",
           "HIGH/CRITICAL task risk: measured-capable candidate needs "
           "final (ENHANCED) verification")
    else:
        ok("HIGH_RISK_VERIFICATION_GATE", "no elevation")

    # Shared descriptors for optimization.
    if ev.facts is not None:
        ev.fit = ev.facts.fit_for(request.task_class)
        if ev.facts.has_known_price():
            ev.cost_per_1k = float(ev.facts.input_price) + float(ev.facts.output_price)
            ev.cost_known = True
        ev.latency_ms = ev.facts.latency_ms
    ok("OPTIMIZATION_SCORE", "eligible for optimization")
    return ev, traces


def _fresh_ok(freshness: Optional[str], requirement: str) -> bool:
    order = {"UNKNOWN": 0, "INCOMPATIBLE": 0, None: -1, "STALE": 1, "CURRENT": 2}
    need = order.get(requirement, 2)
    return order.get(freshness, -1) >= need


def _no_survivor_code(request: RoutingRequest, rejected: List[_Eval]) -> str:
    """Literal sec6 code for a no-survivor block, classified honestly.

    MODALITY_MISMATCH only when every rejection died at the hard
    capability filter and every missing item is a required modality;
    anything else (empty data, non-modality gates, mixed missing sets)
    is NO_ELIGIBLE_CANDIDATE.
    """
    modalities = set(request.required_modalities or ())
    if rejected and modalities:
        for ev in rejected:
            missing = set(ev.missing_caps or ())
            if (ev.failed_step != "HARD_CAPABILITY_FILTER" or not missing
                    or not set(missing) <= modalities):
                break
        else:
            return "MODALITY_MISMATCH"
    return "NO_ELIGIBLE_CANDIDATE"


# --------------------------------------------------------------------------
# Reason builder

def _basis_text(ev: _Eval, opt: T.OptimizationPolicy) -> str:
    if ev.branch == "EXPLICIT_MODEL_PIN":
        fit = "fit %s" % (_fmt(ev.fit) if ev.fit is not None else "unknown")
        return "explicit pin (UNVERIFIED, ENHANCED verification) %s" % fit
    if ev.branch == "VERIFIED_STATIC_CAPABILITY":
        return "verified static capability"
    price = ("known prices in=%s/1k out=%s/1k"
             % (_fmt(ev.facts.input_price), _fmt(ev.facts.output_price))
             if ev.cost_known else "unknown price (treated expensive)")
    if ev.quality is not None and ev.quality < opt.required_quality:
        return ("draft-band quality %s (below required %s, cloud verify "
                "required) %s risk %s<=%s"
                % (_fmt(ev.quality), _fmt(opt.required_quality), price,
                   ev.facts.assessed_risk if ev.facts else "?",
                   opt.max_risk))
    return ("measured quality %s>=%s %s risk %s<=%s"
            % (_fmt(ev.quality), _fmt(opt.required_quality), price,
               ev.facts.assessed_risk if ev.facts else "?",
               opt.max_risk))


def _fmt(value) -> str:
    if value is None:
        return "?"
    if isinstance(value, float):
        return "%.3f" % value if value < 1 else "%.2f" % value
    return str(value)


def _build_reason(route: str, request: RoutingRequest, winner: Optional[_Eval],
                  ranked: List[_Eval], removed: List[str],
                  rejected: List[_Eval], extra: str = "") -> str:
    parts = ["route=%s task=%s" % (route, request.task_class)]
    if (winner is not None and winner.branch == "CAPABILITY_EVIDENCE"
            and winner.required_verification == "ENHANCED"
            and request.task_risk in ("HIGH", "CRITICAL")):
        parts.append("HIGH_RISK: final verification required "
                     "(measured-capable candidate on %s task)"
                     % request.task_risk)
    if winner is not None:
        parts.append("fit=%s" % (_fmt(winner.fit) if winner.fit is not None
                                 else "unknown"))
        parts.append("price+quality basis=" +
                     _basis_text(winner, request.optimization_policy))
        if winner.candidate.is_mock:
            parts.append("mock: true")
    if request.turn_cap is not None:
        parts.append("turn_cap=%s" % (request.turn_cap,))
    if extra:
        parts.append(extra)
    if winner is not None:
        for ev in ranked:
            if ev is winner or not ev.passed:
                continue
            parts.append("outranked: %s (score %s, %s)"
                         % (ev.model, _fmt(ev.score),
                            _basis_text(ev, request.optimization_policy)))
    for ev in rejected:
        parts.append("rejected: %s (%s at %s)"
                     % (ev.model, ev.fail_detail, ev.failed_step))
    for name in removed:
        parts.append("removed: %s" % name)
    return "; ".join(parts)


def _target_flow_evidence(request: RoutingRequest, deps: RoutingDeps) -> str:
    """Row 1673 — explicit TARGET_FLOW resolution evidence for the reason.

    Reports table.resolve for this request's role so the served decide
    flow shows the explicit per-role result (READY, BLOCKED with
    NO_PROFILE_BLOCKED, PINNED_UNHEALTHY); never a default, never a
    swap. Evidence only: any failure yields "" and routing is unchanged.
    """
    try:
        from . import roles as _roles
        store = getattr(deps, "store", None)
        if hasattr(store, "get_role_profile"):
            table = _roles.RoleTable(store=store)
        else:
            table = _roles.RoleTable()
        res = _roles.resolve_target_flow(
            table, request.project_id, request.role,
            provider_health=getattr(deps, "provider_health", None),
            model_health=getattr(deps, "model_health", None),
            exclude_pairs=tuple(getattr(request, "exclude_pairs", None)
                                or ()))
    except Exception:
        return ""
    return "target_flow=%s:%s %s" % (res.role, res.status, res.reason)


# --------------------------------------------------------------------------
# Selection

def _select_impl(request: RoutingRequest, deps: RoutingDeps) -> RoutingOutcome:
    """Run the canonical 11-step selection; pure (no persistence, no emits)."""
    if request.routing_policy.task_class not in ("*", request.task_class):
        return blocked_outcome(
            request, deps, [],
            "routing policy task_class %r does not cover task %r"
            % (request.routing_policy.task_class, request.task_class))

    pin: Optional[Tuple[str, str]] = None
    manager_forced = False
    if request.role == "manager" and deps.manager_profile is not None:
        if request.manager_trigger is None and request.override_provider is None:
            pin = (deps.manager_profile.provider, deps.manager_profile.model)
            manager_forced = True
        elif request.manager_trigger is not None:
            if request.manager_trigger not in T.MANAGER_TRIGGER_SOURCES:
                return blocked_outcome(
                    request, deps, [],
                    "Manager model change needs a recorded trigger "
                    "(fallback, routing_decision, user_override)")
    if request.mode == "PINNED" or request.override_provider is not None:
        provider = request.override_provider or request.pinned_provider
        model = request.override_model or request.pinned_model
        if request.role == "manager" and request.manager_trigger is None:
            return blocked_outcome(
                request, deps, [],
                "Manager model override needs a recorded trigger "
                "(fallback, routing_decision, user_override)")
        if not provider or not model:
            return blocked_outcome(request, deps, [],
                                   "pin requested but no provider/model given")
        pin = (provider, model)

    known_ids = {(c.provider, c.model) for c in request.candidates}
    if pin is not None and pin not in known_ids:
        return blocked_outcome(
            request, deps, [],
            "NO_ELIGIBLE_CANDIDATE: pinned model %s/%s is not a known "
            "candidate (ids are verbatim)" % pin)

    removed: List[str] = []
    pool: List[T.CandidateModel] = []
    for c in request.candidates:
        if c.model in (request.excluded_models or ()):
            removed.append(c.model)
            continue
        if (c.provider, c.model) in (request.exclude_pairs or ()):
            removed.append("%s/%s" % (c.provider, c.model))
            continue
        if pin is not None and (c.provider, c.model) != pin:
            continue
        pool.append(c)
    if not pool:
        detail = "NO_ELIGIBLE_CANDIDATE: no candidates left"
        if removed:
            detail += " (removed: %s)" % ", ".join(removed)
        return blocked_outcome(request, deps, [], detail, removed=removed)

    evals: List[_Eval] = []
    traces: List[T.GateTrace] = []
    for index, candidate in enumerate(pool):
        ev, trace = _evaluate(request, deps, candidate, index, pin)
        evals.append(ev)
        traces.extend(trace)
    survivors = [ev for ev in evals if ev.passed]
    rejected = [ev for ev in evals if not ev.passed]

    preferred = request.preferred_route
    if preferred == "SPLIT":
        return _select_split(request, deps, survivors, rejected, removed,
                             traces, manager_forced)
    if preferred == "PARALLEL":
        return _select_parallel(request, deps, survivors, rejected, removed,
                                traces)
    return _select_single(request, deps, survivors, rejected, removed, traces,
                          manager_forced)


def _optimization_key(ev: _Eval, opt: T.OptimizationPolicy):
    cost = ev.cost_per_1k if ev.cost_known else UNKNOWN_PRICE_PENALTY
    latency = ev.latency_ms if ev.latency_ms is not None else 1000.0
    return (0 if ev.cost_known else 1, cost, latency, ev.index)


def _rank(evals: List[_Eval], request: RoutingRequest) -> List[_Eval]:
    if request.ranking == "listed":
        return list(evals)
    opt = request.optimization_policy
    for ev in evals:
        cost = ev.cost_per_1k if ev.cost_known else UNKNOWN_PRICE_PENALTY
        latency = ev.latency_ms if ev.latency_ms is not None else 1000.0
        cloud = 0.0 if ev.candidate.provider_type == "local" else 1.0
        fit = ev.fit if ev.fit is not None else 0.0
        ev.score = round(opt.weight_cost * cost
                         + opt.weight_latency * latency / 1000.0
                         + opt.weight_cloud_tokens * cloud
                         - opt.weight_quality * fit, 6)
    return sorted(evals, key=lambda ev: (ev.score,) + _optimization_key(ev, opt)[1:])


def _route_for(ev: _Eval) -> str:
    if ev.candidate.provider_type == "local":
        return "LOCAL"
    return "CLOUD"


def _estimated_tokens(request: RoutingRequest):
    """Real estimated_tokens derivation (ARCH-412).

    Token-denominated hard budget is max_tokens-based when price is
    UNAVAILABLE: the estimate is the request max_tokens plus the policy
    overhead. Negative inputs are rejected, never silently summed.
    """
    max_tokens = request.max_tokens
    overhead = request.optimization_policy.token_overhead
    if max_tokens is not None and max_tokens < 0:
        raise ValueError("estimated_tokens: negative max_tokens %r"
                         % (max_tokens,))
    if overhead is not None and overhead < 0:
        raise ValueError("estimated_tokens: negative token_overhead %r"
                         % (overhead,))
    return (max_tokens or 0) + (overhead or 0)


def _select_single(request, deps, survivors, rejected, removed, traces,
                   manager_forced: bool) -> RoutingOutcome:
    eligible = [ev for ev in survivors
                if not (ev.candidate.provider_type == "local"
                        and ev.local_route != "LOCAL")]
    if not eligible:
        if survivors:
            detail = ("NO_ELIGIBLE_CANDIDATE: no eligible candidate "
                      "survived all hard gates "
                      "(local draft-only without a SPLIT request)")
        else:
            detail = ("%s: no eligible candidate survived all hard gates"
                      % _no_survivor_code(request, rejected))
        # The blocked record keeps every evaluated candidate (eligible
        # drafts plus rejected rows with their failed step), so the
        # WHY_THIS_MODEL replay names the refusing gate.
        return blocked_outcome(request, deps, traces, detail, removed=removed,
                               evals=list(survivors) + list(rejected))
    ranked = _rank(eligible, request)
    winner = ranked[0]
    runners = ranked[1:]
    route = _route_for(winner)
    source = "MANAGER_PROFILE" if manager_forced else winner.branch
    reason = _build_reason(route, request, winner, ranked, removed, rejected)
    return _finish(request, deps, traces, ranked, winner, runners, route,
                   request.preferred_strategy or ("MANAGER_PROFILE" if manager_forced
                                                  else winner.branch
                                                  if request.mode == "pool"
                                                  else "auto"),
                   reason, source, winner, None)


def _select_split(request, deps, survivors, rejected, removed, traces,
                _manager_forced: bool = False) -> RoutingOutcome:
    policy = request.routing_policy
    if not policy.split_allowed:
        return blocked_outcome(request, deps, traces,
                               "SPLIT requested but policy forbids split",
                               removed=removed, evals=survivors)
    drafts = [ev for ev in survivors
              if ev.candidate.provider_type == "local"
              and ev.local_route in ("LOCAL", "SPLIT_ONLY")]
    verifiers = [ev for ev in survivors
                 if ev.candidate.provider_type == "cloud"]
    if not drafts:
        return blocked_outcome(
            request, deps, traces,
            "NO_ELIGIBLE_CANDIDATE: SPLIT requested but no eligible "
            "local draft", removed=removed, evals=survivors)
    if not verifiers:
        return blocked_outcome(
            request, deps, traces,
            "NO_ELIGIBLE_CANDIDATE: SPLIT requested but no eligible "
            "cloud verifier", removed=removed, evals=survivors)
    draft = _rank(drafts, request)[0]
    verifier = _rank(verifiers, request)[0]
    ranked = [draft, verifier]
    reason = _build_reason(
        "SPLIT", request, draft, ranked, removed, rejected,
        extra="strategy=%s draft=%s verify=%s"
        % (request.preferred_strategy or "LOCAL_DRAFT_CLOUD_FINAL",
           draft.model, verifier.model))
    return _finish(request, deps, traces, ranked, draft,
                   [verifier] + [ev for ev in _rank(verifiers, request)[1:]],
                   "SPLIT",
                   request.preferred_strategy or "LOCAL_DRAFT_CLOUD_FINAL",
                   reason, draft.branch, draft, verifier)


def _select_parallel(request, deps, survivors, rejected, removed, traces) -> RoutingOutcome:
    ranked = _rank(list(survivors), request)
    if len(ranked) < 2:
        return blocked_outcome(
            request, deps, traces,
            "NO_ELIGIBLE_CANDIDATE: PARALLEL requested but fewer than 2 "
            "survivors", removed=removed, evals=survivors)
    first, second = ranked[0], ranked[1]
    reason = _build_reason(
        "PARALLEL", request, first, ranked, removed, rejected,
        extra="strategy=%s lanes=%s,%s"
        % (request.preferred_strategy or "PARALLEL_COMPARE",
           first.model, second.model))
    return _finish(request, deps, traces, ranked, first, ranked[1:],
                   "PARALLEL",
                   request.preferred_strategy or "PARALLEL_COMPARE",
                   reason, first.branch, first, second)


def _finish(request: RoutingRequest, deps: RoutingDeps,
            traces: List[T.GateTrace], ranked: List[_Eval], winner: _Eval,
            runners: List[_Eval], route: str, strategy: str, reason: str,
            source: str, primary: _Eval,
            secondary: Optional[_Eval]) -> RoutingOutcome:
    decision_id = _new_id("rd")
    snapshot_id = _new_id("rs")
    stage_default = {"director": "block"}.get(request.role, "task")
    stage = request.stage or stage_default

    resource_ref = _ref(deps.resource_state, "resource:not-provided")
    budget_ref = _ref(deps.budget_state, "budget:not-provided")
    opt = request.optimization_policy
    policy = request.routing_policy

    assignments: List[T.RoutingAssignment] = []
    if route in ("SPLIT", "PARALLEL") and secondary is not None:
        stages = (("local_draft", "cloud_verify") if route == "SPLIT"
                  else ("parallel_a", "parallel_b"))
        first, second = ((primary, secondary) if route == "SPLIT"
                         or primary.score <= secondary.score
                         else (secondary, primary))
        if route == "SPLIT":
            ordered = sorted([primary, secondary],
                             key=lambda ev: 0 if ev.candidate.provider_type == "local" else 1)
            first, second = ordered[0], ordered[1]
        for ev, lane in zip((first, second), stages):
            assignments.append(T.RoutingAssignment(
                assignment_id=_new_id("ra"),
                project_id=request.project_id, task_id=request.task_id,
                run_id=request.run_id, subtask_id=request.subtask_id,
                role=request.role, stage=lane, route=route,
                provider=ev.candidate.provider,
                provider_instance=ev.candidate.provider_instance,
                model=ev.candidate.model,
                capability_evidence_refs=_evidence_refs(ev),
                resource_state_ref=resource_ref,
                budget_reservation_ref=(None if ev.candidate.provider_type == "local"
                                        else budget_ref),
                routing_policy_ref=_policy_ref(policy),
                optimization_policy_ref=_policy_ref(opt),
                status="PLANNED"))
    else:
        assignments.append(T.RoutingAssignment(
            assignment_id=_new_id("ra"),
            project_id=request.project_id, task_id=request.task_id,
            run_id=request.run_id, subtask_id=request.subtask_id,
            role=request.role, stage=stage, route=route,
            provider=winner.candidate.provider,
            provider_instance=winner.candidate.provider_instance,
            model=winner.candidate.model,
            capability_evidence_refs=_evidence_refs(winner),
            resource_state_ref=resource_ref,
            budget_reservation_ref=(None if winner.candidate.provider_type == "local"
                                    else budget_ref),
            routing_policy_ref=_policy_ref(policy),
            optimization_policy_ref=_policy_ref(opt),
            status="PLANNED"))

    flow_evidence = _target_flow_evidence(request, deps)
    if flow_evidence:
        reason = "%s; %s" % (reason, flow_evidence)
    policy_view = _policy_view_text(opt)
    if policy_view:
        reason = "%s; %s" % (reason, policy_view)
    pricing_evidence = _record_winner_pricing(request, deps, winner)
    if pricing_evidence:
        reason = "%s; %s" % (reason, pricing_evidence)

    candidate_snapshot = tuple(
        {"provider": ev.candidate.provider, "model": ev.candidate.model,
         "provider_type": ev.candidate.provider_type,
         "mock": bool(ev.candidate.is_mock), "branch": ev.branch,
         "capability_state": ev.capability_state, "quality": ev.quality,
         "fit": ev.fit, "cost_known": ev.cost_known,
         "cost_per_1k": ev.cost_per_1k, "passed": ev.passed,
         "failed_step": ev.failed_step, "fail_detail": ev.fail_detail,
         "local_route": ev.local_route, "score": ev.score}
        for ev in ranked)

    snapshot = T.RoutingEvidenceSnapshot(
        routing_snapshot_id=snapshot_id,
        project_id=request.project_id, task_id=request.task_id,
        run_id=request.run_id, created_at=T.utcnow(),
        provider_health_snapshot={p: h.status for p, h in
                                  (deps.provider_health or {}).items()},
        model_health_snapshot={"%s/%s" % k: h.status for k, h in
                               (deps.model_health or {}).items()},
        resource_state_snapshot=(dict(deps.resource_state)
                                 if isinstance(deps.resource_state, Mapping)
                                 else deps.resource_state),
        budget_state_snapshot=(dict(deps.budget_state)
                               if isinstance(deps.budget_state, Mapping)
                               else deps.budget_state),
        candidate_snapshot=candidate_snapshot,
        policy_versions=(_policy_ref(policy), _policy_ref(opt)),
        capability_evidence_refs=tuple(
            "kb:%s/%s" % (ev.candidate.provider, ev.candidate.model)
            for ev in ranked if ev.facts is not None),
        hash="")

    decision = T.RoutingDecision(
        decision_id=decision_id,
        project_id=request.project_id, task_id=request.task_id,
        run_id=request.run_id, routing_snapshot_id=snapshot_id,
        routing_policy_ref=_policy_ref(policy),
        optimization_policy_ref=_policy_ref(opt),
        retry_policy_ref=request.retry_policy_ref,
        fallback_policy_ref=request.fallback_policy_ref,
        verification_policy_ref=request.verification_policy_ref,
        audit_policy_ref=request.audit_policy_ref,
        override_policy_ref=request.override_policy_ref,
        candidate_models=tuple(c.model for c in request.candidates
                               if c.model not in (request.excluded_models or ())),
        candidate_providers=tuple(dict.fromkeys(
            c.provider for c in request.candidates)),
        selected_provider=winner.candidate.provider,
        selected_model=winner.candidate.model,
        routing_assignment_ids=tuple(a.assignment_id for a in assignments),
        route=route, strategy=strategy, reason=reason,
        eligibility_source=source,
        capability_state=winner.capability_state,
        required_verification=winner.required_verification,
        eligibility_branch_evidence_refs=tuple(_evidence_refs(winner)),
        capability_evidence_refs=tuple(_evidence_refs(winner)),
        provider_health_ref="ph:%s" % decision_id,
        model_health_ref="mh:%s" % decision_id,
        resource_state_ref=resource_ref,
        risk_override=False,
        estimated_cost=(winner.cost_per_1k if winner.cost_known else None),
        estimated_latency=winner.latency_ms,
        optimization_score=winner.score,
        fallback_chain=tuple({"provider": ev.candidate.provider,
                               "model": ev.candidate.model}
                              for ev in runners),
        estimated_tokens=_estimated_tokens(request))
    snapshot = replace(snapshot, hash=T.stable_hash({
        "providers": snapshot.provider_health_snapshot,
        "models": snapshot.model_health_snapshot,
        "candidates": [dict(c) for c in candidate_snapshot],
        "policies": list(snapshot.policy_versions)}))
    return RoutingOutcome("ROUTED", decision, tuple(assignments), snapshot,
                          tuple(traces))


def blocked_outcome(request: RoutingRequest, deps: RoutingDeps,
                    traces, reason: str, removed=None,
                    evals=None) -> RoutingOutcome:
    decision_id = _new_id("rd")
    snapshot_id = _new_id("rs")
    policy = request.routing_policy
    opt = request.optimization_policy
    full_reason = "route=BLOCKED task=%s; blocked: %s" % (request.task_class, reason)
    if request.turn_cap is not None:
        full_reason += "; turn_cap=%s" % (request.turn_cap,)
    for name in (removed or []):
        full_reason += "; removed: %s" % name
    for ev in (evals or []):
        if not ev.passed:
            full_reason += ("; rejected: %s (%s at %s)"
                            % (ev.model, ev.fail_detail, ev.failed_step))
    flow_evidence = _target_flow_evidence(request, deps)
    if flow_evidence:
        full_reason += "; %s" % flow_evidence
    policy_view = _policy_view_text(opt)
    if policy_view:
        full_reason += "; %s" % policy_view
    decision = T.RoutingDecision(
        decision_id=decision_id,
        project_id=request.project_id, task_id=request.task_id,
        run_id=request.run_id, routing_snapshot_id=snapshot_id,
        routing_policy_ref=_policy_ref(policy),
        optimization_policy_ref=_policy_ref(opt),
        retry_policy_ref=request.retry_policy_ref,
        fallback_policy_ref=request.fallback_policy_ref,
        verification_policy_ref=request.verification_policy_ref,
        audit_policy_ref=request.audit_policy_ref,
        override_policy_ref=request.override_policy_ref,
        candidate_models=tuple(c.model for c in request.candidates),
        candidate_providers=tuple(dict.fromkeys(
            c.provider for c in request.candidates)),
        selected_provider=None, selected_model=None,
        routing_assignment_ids=(),
        route="BLOCKED", strategy=request.preferred_strategy or "none",
        reason=full_reason, eligibility_source="NONE",
        capability_state="UNKNOWN", required_verification="ENHANCED",
        eligibility_branch_evidence_refs=(),
        capability_evidence_refs=(),
        provider_health_ref="ph:%s" % decision_id,
        model_health_ref="mh:%s" % decision_id,
        resource_state_ref=_ref(deps.resource_state, "resource:not-provided"),
        risk_override=False, estimated_cost=None, estimated_latency=None,
        optimization_score=None, fallback_chain=(),
        estimated_tokens=_estimated_tokens(request))
    snapshot = T.RoutingEvidenceSnapshot(
        routing_snapshot_id=snapshot_id,
        project_id=request.project_id, task_id=request.task_id,
        run_id=request.run_id, created_at=T.utcnow(),
        provider_health_snapshot={p: h.status for p, h in
                                  (deps.provider_health or {}).items()},
        model_health_snapshot={"%s/%s" % k: h.status for k, h in
                               (deps.model_health or {}).items()},
        resource_state_snapshot=(dict(deps.resource_state)
                                 if isinstance(deps.resource_state, Mapping)
                                 else deps.resource_state),
        budget_state_snapshot=(dict(deps.budget_state)
                               if isinstance(deps.budget_state, Mapping)
                               else deps.budget_state),
        candidate_snapshot=tuple(
            {"provider": ev.candidate.provider, "model": ev.candidate.model,
             "provider_type": ev.candidate.provider_type,
             "mock": bool(ev.candidate.is_mock), "branch": ev.branch,
             "capability_state": ev.capability_state, "quality": ev.quality,
             "fit": ev.fit, "cost_known": ev.cost_known,
             "cost_per_1k": ev.cost_per_1k, "passed": ev.passed,
             "failed_step": ev.failed_step, "fail_detail": ev.fail_detail,
             "local_route": ev.local_route, "score": ev.score}
            for ev in (evals or [])),
        policy_versions=(_policy_ref(policy), _policy_ref(opt)),
        capability_evidence_refs=(),
        hash="")
    snapshot = replace(snapshot, hash=T.stable_hash({
        "providers": snapshot.provider_health_snapshot,
        "models": snapshot.model_health_snapshot,
        "candidates": [dict(c) for c in snapshot.candidate_snapshot],
        "policies": list(snapshot.policy_versions)}))
    return RoutingOutcome("BLOCKED", decision, (), snapshot, tuple(traces))


def _ref(state, default: str) -> str:
    if isinstance(state, Mapping) and state.get("ref"):
        return str(state["ref"])
    return default


def _policy_ref(policy) -> str:
    return "%s:v%d" % (policy.policy_id, policy.version)


def _evidence_refs(ev: _Eval) -> tuple:
    refs = []
    if ev.facts is not None:
        refs.append("kb:%s/%s" % (ev.candidate.provider, ev.candidate.model))
    if ev.branch == "EXPLICIT_MODEL_PIN":
        refs.append("pin:explicit")
    if ev.branch == "VERIFIED_STATIC_CAPABILITY":
        refs.append("static:verified")
    return tuple(refs)


# --------------------------------------------------------------------------
# Frozen facade (section 3.1): 6 frozen ref params, no server-side context.
#
# This exact frozen signature carries no server-side context (no **ctx),
# so the resolution maps (task contracts, policies, KB, health, states,
# store, emitter) are absent: every ref is unresolvable and the call
# raises ValueError carrying the genuine BLOCKED reason via the
# missing-ref arm below (never a BLOCKED return).
# Candidates accept the frozen CandidateView attribute shape OR the
# mapping shape ({provider_id, model, provider_instance, rejected, ...});
# views marked rejected=True are excluded and named in the outcome.
# provider_type defaults to "cloud" (the frozen view carries no locality).
# Selection semantics live in _select_impl (unchanged).
# Production caller: backend post_decide (worker B) wires through this
# facade; record path mirrors decide_and_record.

_select_scope = threading.local()


def bind_select_scope(mapping):
    """Bind the server-side resolution scope for the frozen select facade.

    Accepts the request-scoped registry mapping (task_contracts,
    routing_policies, optimization_policies, kb, health views, states,
    store, emitter, manager_profile) and returns it unchanged. select
    reads this binding; an unbound call keeps today's missing-ref
    ValueError behavior.
    """
    _select_scope.mapping = mapping
    return mapping


def unbind_select_scope():
    """Clear the bound select scope (call in finally after select)."""
    _select_scope.mapping = None


def select(task_contract_ref: str, candidates: List[CandidateView],
           routing_policy_ref: str, optimization_policy_ref: str,
           budget_state_ref: str,
           resource_state_ref: str) -> RoutingDecision:
    """Frozen 6-param selection facade (frozen refs only, no **ctx).

    Never returns a BLOCKED outcome: with no server-side context every
    ref is unresolvable, so the call raises ValueError carrying the
    genuine missing-ref reason. Selection semantics themselves are
    unchanged in _select_impl.
    """
    ctx = getattr(_select_scope, "mapping", None) or {}
    task_contracts = ctx.get("task_contracts") or {}
    routing_policies = ctx.get("routing_policies") or {}
    optimization_policies = ctx.get("optimization_policies") or {}

    task = (task_contracts.get(task_contract_ref)
            if isinstance(task_contracts, Mapping) else None)
    routing_policy = (routing_policies.get(routing_policy_ref)
                      if isinstance(routing_policies, Mapping) else None)
    optimization_policy = (optimization_policies.get(optimization_policy_ref)
                           if isinstance(optimization_policies, Mapping)
                           else None)
    budget_state = ctx.get("budget_state")
    resource_state = ctx.get("resource_state")
    kb = ctx.get("kb")

    missing = []
    if task is None:
        missing.append("task_contract_ref=%r" % (task_contract_ref,))
    if routing_policy is None:
        missing.append("routing_policy_ref=%r" % (routing_policy_ref,))
    if optimization_policy is None:
        missing.append("optimization_policy_ref=%r" % (optimization_policy_ref,))
    if budget_state is None:
        missing.append("budget_state_ref=%r" % (budget_state_ref,))
    if resource_state is None:
        missing.append("resource_state_ref=%r" % (resource_state_ref,))
    if kb is None:
        missing.append("kb (server-side ctx holds no KbReader)")

    views = list(candidates or [])
    modality_ok_by_pair: Dict[Tuple[str, str], bool] = {}
    for _view in views:
        _provider = _view_field(_view, "provider_id")
        _model = _view_field(_view, "model")
        if _provider and _model:
            if _view_field(_view, "modality_ok", True) is False:
                modality_ok_by_pair[(_provider, _model)] = False
            else:
                modality_ok_by_pair.setdefault((_provider, _model), True)
    kept, rejected = _split_views(views)

    if missing:
        outcome = blocked_outcome(
            _vehicle_request(task, kept, rejected, routing_policy,
                             optimization_policy),
            _vehicle_deps(kb, ctx), (),
            "unresolvable ref: %s" % ", ".join(missing),
            removed=["%s/%s" % pair for pair in rejected])
        raise ValueError(outcome.decision.reason)

    project_id = _contract_field(task, "project_id")
    task_id = _contract_field(task, "task_id")
    run_id = _contract_field(task, "run_id")
    if not project_id or not task_id or not run_id:
        outcome = blocked_outcome(
            _vehicle_request(task, kept, rejected, routing_policy,
                             optimization_policy),
            _vehicle_deps(kb, ctx), (),
            "unresolvable ref: task_contract_ref=%r has no "
            "project/task/run ids" % (task_contract_ref,),
            removed=["%s/%s" % pair for pair in rejected])
        raise ValueError(outcome.decision.reason)

    request = RoutingRequest(
        project_id=project_id, task_id=task_id, run_id=run_id,
        role=_contract_field(task, "role", "worker") or "worker",
        task_class=_contract_field(task, "task_class", "general") or "general",
        routing_policy=routing_policy,
        optimization_policy=optimization_policy,
        candidates=tuple(kept),
        required_capabilities=tuple(
            _contract_field(task, "required_capabilities", ("text",)) or ()),
        required_modalities=tuple(
            _contract_field(task, "required_modalities", ("text",)) or ()),
        task_risk=_contract_field(task, "task_risk", "LOW") or "LOW",
        exclude_pairs=tuple(rejected),
        max_tokens=_contract_field(task, "max_tokens", None))
    deps = RoutingDeps(
        kb=kb,
        provider_health=ctx.get("provider_health"),
        model_health=ctx.get("model_health"),
        provider_capabilities=ctx.get("provider_capabilities"),
        resource_state=resource_state,
        budget_state=budget_state,
        manager_profile=ctx.get("manager_profile"),
        store=ctx.get("store"),
        emitter=None)
    if not kept and rejected:
        outcome = blocked_outcome(
            request, deps, (),
            "NO_ELIGIBLE_CANDIDATE: no candidates left (all %d candidate "
            "view(s) rejected by the caller)" % len(rejected),
            removed=["%s/%s" % pair for pair in rejected])
        raise ValueError(outcome.decision.reason)
    outcome = _select_impl(request, deps)
    if outcome.status == "BLOCKED":
        refusals = "; ".join(
            "refused: %s at %s (%s)"
            % (row.get("model"), row.get("failed_step"),
               row.get("fail_detail"))
            for row in outcome.snapshot.candidate_snapshot
            if not row.get("passed") and row.get("failed_step"))
        reason = outcome.decision.reason
        if refusals:
            reason = "%s; %s" % (reason, refusals)
        raise ValueError(reason)
    _winner = (outcome.decision.selected_provider,
               outcome.decision.selected_model)
    if modality_ok_by_pair.get(_winner, True) is False:
        # Treatment flag (same family as the PRICE_UNKNOWN_EXPENSIVE
        # convention): the winner's own source view carried
        # modality_ok=False, yet selection still routed from KB facts.
        # The internal modality gate (_select_impl) is unchanged.
        outcome = replace(outcome, decision=replace(
            outcome.decision,
            reason="%s; MODALITY_MISMATCH: winner %s/%s routed from a "
            "modality_ok=False view (treatment flag; KB-derived "
            "selection unchanged)" % (
                outcome.decision.reason, _winner[0], _winner[1])))
    if deps.store is not None:
        deps.store.save_decision(outcome.decision, outcome.assignments,
                                 outcome.snapshot)
    emitter = ctx.get("emitter")
    if emitter is not None:
        decision = outcome.decision
        emitter.emit(routing_event(
            project_id=request.project_id, task_id=request.task_id,
            run_id=request.run_id, role=request.role, route=decision.route,
            provider=decision.selected_provider, model=decision.selected_model,
            reason=decision.reason,
            routing_decision_ref=decision.decision_id,
            routing_snapshot_id=decision.routing_snapshot_id,
            mock=("mock: true" in decision.reason),
            capability_rule=decision.eligibility_source))
    return outcome  # type: ignore[return-value]


def _view_field(view, name, default=None):
    if isinstance(view, Mapping):
        return view.get(name, default)
    return getattr(view, name, default)


def _contract_field(task, name, default=None):
    if task is None:
        return default
    if isinstance(task, Mapping):
        return task.get(name, default)
    return getattr(task, name, default)


def _split_views(views):
    """Translate CandidateViews to CandidateModels; rejected views excluded.

    Accepts the frozen CandidateView attribute shape or the mapping shape.
    Views marked rejected=True never reach selection: their
    (provider, model) pairs are returned for exclude_pairs so the raised
    reason names them. provider_type defaults to "cloud" (the frozen view
    carries no locality); price/quality/effective-capability view fields
    are caller-side hints, the router re-derives everything from KB facts.
    """
    kept: List[T.CandidateModel] = []
    rejected: List[Tuple[str, str]] = []
    for view in views:
        provider = _view_field(view, "provider_id")
        model = _view_field(view, "model")
        if not provider or not model:
            continue
        if _view_field(view, "rejected", False):
            rejected.append((provider, model))
            continue
        kept.append(T.CandidateModel(
            provider=provider, model=model,
            provider_instance=_view_field(view, "provider_instance")))
    return kept, rejected


def _unresolved_routing_policy(ref: str) -> T.RoutingPolicy:
    return T.RoutingPolicy(
        policy_id="unresolved:%s" % (ref,), version=0,
        created_at=T.utcnow(), hash="unresolved", task_class="*",
        risk_level="LOW", strict_min=0.0, tolerant_min=0.0,
        confidence_min=0.0, sample_min=0, freshness_requirement="UNKNOWN",
        local_allowed=True, split_allowed=False, cloud_required=False)


def _unresolved_optimization_policy(ref: str) -> T.OptimizationPolicy:
    return T.OptimizationPolicy(
        policy_id="unresolved:%s" % (ref,), version=0,
        created_at=T.utcnow(), hash="unresolved", required_quality=0.0,
        max_risk="CRITICAL", weight_quality=0.0, weight_cost=0.0,
        weight_latency=0.0, weight_cloud_tokens=0.0, local_preference=False,
        deadline=None, budget_limit=None)


def _vehicle_request(task, kept, rejected, routing_policy,
                     optimization_policy) -> RoutingRequest:
    """Minimal vehicle request so an unresolvable ref still yields a real BLOCKED outcome."""
    return RoutingRequest(
        project_id=_contract_field(task, "project_id", "unknown"),
        task_id=_contract_field(task, "task_id", "unknown"),
        run_id=_contract_field(task, "run_id", "unknown") or "unknown",
        role=_contract_field(task, "role", "worker") or "worker",
        task_class=_contract_field(task, "task_class", "general") or "general",
        routing_policy=(routing_policy or _unresolved_routing_policy("missing")),
        optimization_policy=(optimization_policy
                             or _unresolved_optimization_policy("missing")),
        candidates=tuple(kept),
        exclude_pairs=tuple(rejected))


def _vehicle_deps(kb, ctx) -> RoutingDeps:
    return RoutingDeps(
        kb=kb,
        provider_health=ctx.get("provider_health"),
        model_health=ctx.get("model_health"),
        provider_capabilities=ctx.get("provider_capabilities"),
        resource_state=ctx.get("resource_state"),
        budget_state=ctx.get("budget_state"),
        manager_profile=ctx.get("manager_profile"),
        store=None,
        emitter=None)


# --------------------------------------------------------------------------
# Record (persist + emit); selection itself stays pure above.

def _pool_binding_for(request: RoutingRequest, deps: RoutingDeps):
    """Stored pool binding for (project_id, role) for pool-mode requests.

    Returns None for PINNED/AUTO requests (pin and generic paths stay
    unchanged) and when the store holds no binding for the role: only a
    pool-mode request with a stored binding routes through that
    binding's strategy via resolve_pool.
    """
    if request.mode != "pool":
        return None
    store = getattr(deps, "store", None)
    get_pool = getattr(store, "get_pool", None)
    if get_pool is None:
        return None
    try:
        return get_pool(request.project_id, request.role)
    except Exception:
        return None


def _stored_pool_strategy(request: RoutingRequest, deps: RoutingDeps) -> str:
    """Stored pool strategy for this level select via the frozen facade.

    pick_pool_strategy(role, project_id) reads the stored binding written
    by set_role_pool / PUT /api/v1/roles/pools, AUTO when no binding
    exists. The deps store serves as the facade's module store for the
    call so the same binding the pool branch routes through stays
    visible; a previously bound store is restored afterwards.
    """
    from . import pools as _pools
    store = getattr(deps, "store", None)
    if store is None or getattr(store, "get_pool", None) is None:
        return _pools.pick_pool_strategy(request.role, request.project_id)
    prev = _pools._bound_pool_store
    _pools.bind_pool_store(store)
    try:
        return _pools.pick_pool_strategy(request.role, request.project_id)
    finally:
        if prev is None:
            _pools.unbind_pool_store()
        else:
            _pools.bind_pool_store(prev)


def decide_and_record(request: RoutingRequest, deps: RoutingDeps) -> RoutingOutcome:
    """Select, persist the decision bundle, and emit a telemetry event.

    Every level select consults the frozen pick_pool_strategy facade
    (stored-binding read, AUTO when no binding exists). A pool-mode
    request with a stored binding routes through the returned strategy
    (resolve_pool, surfaced via _retag); every other request keeps the
    direct selection path.
    """
    strategy = _stored_pool_strategy(request, deps)
    binding = _pool_binding_for(request, deps)
    if binding is not None:
        from . import pools as _pools
        outcome = _pools.resolve_pool(binding, request, deps,
                                      strategy=strategy)
    else:
        outcome = _select_impl(request, deps)
    store = getattr(deps, "store", None)
    if store is not None:
        store.save_decision(outcome.decision, outcome.assignments,
                            outcome.snapshot, turn_cap=request.turn_cap)
    emitter = getattr(deps, "emitter", None)
    if emitter is not None:
        decision = outcome.decision
        mock = ("mock: true" in decision.reason)
        emitter.emit(routing_event(
            project_id=request.project_id, task_id=request.task_id,
            run_id=request.run_id, role=request.role, route=decision.route,
            provider=decision.selected_provider, model=decision.selected_model,
            reason=decision.reason,
            routing_decision_ref=decision.decision_id,
            routing_snapshot_id=decision.routing_snapshot_id,
            mock=mock, capability_rule=decision.eligibility_source))
    return outcome
