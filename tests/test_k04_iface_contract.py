"""K04 STRICT frozen-interface contract: frozen wins (RED until lanes match).

Read-only over every lane (routing, providers/registry,
providers/adapters, model_kb, budget, backend pools_routes+modelkb):
imports plus inspect only. No fakes, no network, no installs, no writes.
Stdlib + pytest only. Fast (<120s): pure signature/shape compares.

Strictness (no subset/substring/structural tolerance):
- every frozen function in interface.py: inspect.signature param names
  EXACTLY, order-sensitive, self/cls excluded, stub-vs-real-target via
  IF.REALIZATION_MAP;
- dataclass/TypedDict field and key sets EXACTLY as ordered lists;
- enum value lists EXACTLY ordered;
- KB_ROW_FIELDS / KB_ROW_KEYS / KB_SOURCED_FIELD_KEYS exact tuples;
- FROZEN_SELECTION_STEPS exact; ERROR_CODES exact;
- HTTP_ROUTES exact set (upper-cased method + path) vs PR.ROUTES;
- frontend component props EXACT sets (sorted compare).
Drift rows D1-D15 (HD_REQUEST_IFACE_CODE): each has a dedicated
test_dNN test that FAILS while RED.
"""
import importlib
import inspect
import os
import re
import sys
from dataclasses import fields as dc_fields

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_HERE, "..", "src")
_SRC = os.path.abspath(_SRC)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
_REPO = os.path.dirname(_HERE)
_FRONT = os.path.join(_REPO, "frontend", "src", "settings", "ProvidersPage")

import pytest

from agent_si.routing import interface as IF
from agent_si.routing import types as RT
from agent_si.providers.registry import provider_api as PAPI
from agent_si.providers.adapters import usage_probe as UPR
from agent_si.model_kb import kb as KB
from agent_si.budget import gate as BG
from agent_si.budget import telemetry as BT
from agent_si.backend import pools_routes as PR


# ---------------------------------------------------------------- helpers

def field_names(cls):
    return [f.name for f in dc_fields(cls)]


def _sig_params(fn):
    names = [p.name for p in inspect.signature(fn).parameters.values()
             if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD,
                           p.KEYWORD_ONLY)]
    if names[:1] in (["self"], ["cls"]):
        names = names[1:]
    return names


def stub_params(name):
    return _sig_params(getattr(IF, name))


def resolve(dotted):
    bits = dotted.split(".")
    for i in range(len(bits), 0, -1):
        try:
            obj = importlib.import_module(".".join(bits[:i]))
            rest = bits[i:]
            break
        except ImportError:
            continue
    for bit in rest:
        obj = getattr(obj, bit)
    return obj


def real_params(frozen_name):
    return _sig_params(resolve(IF.REALIZATION_MAP[frozen_name]))


def _norm_ann(ann):
    if ann is inspect.Parameter.empty:
        return ""
    try:
        text = repr(ann)
    except Exception:
        try:
            text = str(ann)
        except Exception:
            return "<unrepresentable>"
    return re.sub(r"\s+", "", text)


def _norm_default(value):
    if value is inspect.Parameter.empty:
        return "<empty>"
    try:
        return "=" + repr(value)
    except Exception:
        return "=<unrepresentable>"


def _sig_full(fn):
    params = list(inspect.signature(fn).parameters.values())
    if params[:1] and params[0].name in ("self", "cls") and \
            params[0].kind in (inspect.Parameter.POSITIONAL_ONLY,
                               inspect.Parameter.POSITIONAL_OR_KEYWORD):
        params = params[1:]
    return [(p.name, str(p.kind), _norm_default(p.default),
             _norm_ann(p.annotation)) for p in params]


def _sigs_match(stub_fn, real_fn):
    stub = _sig_full(stub_fn)
    real = _sig_full(real_fn)
    return stub == real


def front_text(name):
    with open(os.path.join(_FRONT, name), encoding="utf-8") as fh:
        return fh.read()


def props_block(text, type_name):
    match = re.search(r"type\s+%s\s*=\s*\{(.*?)\};" % re.escape(type_name),
                      text, re.DOTALL)
    assert match, "missing %s in component file" % type_name
    return match.group(1)


def prop_names(block):
    return re.findall(r"(\w+)\??:", block)


# ------------------------------------------------------- stub surface lock

def test_realization_targets_importable_and_callable():
    for frozen, dotted in IF.REALIZATION_MAP.items():
        target = resolve(dotted)
        assert callable(target), "%s -> %s not callable" % (frozen, dotted)


def test_stub_exposes_all_frozen_functions():
    for frozen in IF.REALIZATION_MAP:
        assert callable(getattr(IF, frozen)), "stub missing %s" % frozen


def test_stub_bodies_are_ellipsis_no_raise():
    for frozen in IF.REALIZATION_MAP:
        src = inspect.getsource(getattr(IF, frozen))
        assert "raise NotImplementedError" not in src, frozen
        assert "..." in src, frozen
    assert IF.replay("rd-1") is None
    assert IF.get_state("p1") is None


# ------------------------------------------------------- frozen pins (GREEN)

def test_frozen_enum_values_pinned():
    assert [m.value for m in IF.RoleMode] == ["PINNED", "pool", "AUTO"]
    assert [m.value for m in IF.RiskLevel] == ["LOW", "MEDIUM", "HIGH",
                                               "CRITICAL"]
    assert [m.value for m in IF.PriceBasis] == ["KNOWN", "UNKNOWN"]
    assert [m.value for m in IF.QualityBasis] == [
        "MEASURED", "STATIC_VERIFIED", "UNVERIFIED_PIN", "UNKNOWN"]
    assert [m.value for m in IF.PoolStrategy] == [
        "DIRECTOR_PER_TASK", "AUTO", "FALLBACK_ORDER", "SPLIT_PARALLEL"]
    assert IF.NON_DEFAULT_EXAMPLE == "meta/muse-spark-1.3-contributor"


def test_frozen_selection_steps_and_error_codes_pinned():
    assert list(IF.FROZEN_SELECTION_STEPS) == list(RT.SELECTION_STEPS)
    assert list(IF.ERROR_CODES_K13) == ["CONTEXT_WRONG_CONTRACT_VERSION",
                                        "POLICY_CONFLICT", "CONTEXT_MISSING"]
    assert list(IF.ERROR_CODES_K04) == [
        "NO_PROFILE_BLOCKED", "NO_ELIGIBLE_CANDIDATE", "MODALITY_MISMATCH",
        "PROVIDER_UNEVIDENCED", "PRICE_UNKNOWN_EXPENSIVE",
        "BUDGET_SOFT_WARN", "BUDGET_HARD_BLOCKED", "PENDING_RECONCILIATION",
        "DUPLICATE_SETTLEMENT_REFUSED", "KB_VALIDATION_FAILED",
        "KB_PROPOSAL_NOT_APPROVED", "KEY_SAVE_TIMEOUT",
        "CREDENTIAL_ENTRY_MISSING"]


# ------------------------------------------------------------------ D1-D15

def test_d01_pool_strategy_values_match_real():
    assert [m.value for m in IF.PoolStrategy] == list(RT.POOL_STRATEGIES)


def test_d02_kb_row_fields_frozen_wins():
    # Frozen stub is the oracle (frozen-wins): stub-vs-real exact compare.
    # (Sec 3.4 prose tokens like "dated price" are not identifiers and are
    # never asserted here.)
    assert list(IF.KB_ROW_FIELDS) == list(KB.ROW_FIELD_NAMES)
    assert tuple(IF.KB_ROW_KEYS) == ("provider_id", "model_id", "fields")
    assert tuple(IF.KB_SOURCED_FIELD_KEYS) == ("value", "source",
                                               "retrieved_at")


def test_d03_select_signature_exact():
    assert _sigs_match(IF.select,
                       resolve(IF.REALIZATION_MAP["select"]))


def test_d04_resolve_role_model_signature_exact():
    assert _sigs_match(IF.resolve_role_model,
                       resolve(IF.REALIZATION_MAP["resolve_role_model"]))


def test_d05_record_fallback_signature_exact():
    assert _sigs_match(IF.record_fallback,
                       resolve(IF.REALIZATION_MAP["record_fallback"]))


def test_d06_replay_tuple_not_dict():
    assert _sigs_match(IF.replay,
                       resolve(IF.REALIZATION_MAP["replay"]))
    stub_ret = inspect.signature(IF.replay).return_annotation
    real_ret = inspect.signature(
        resolve(IF.REALIZATION_MAP["replay"])).return_annotation
    assert stub_ret == real_ret


def test_d07_budget_telemetry_signatures_exact():
    assert _sigs_match(IF.compare_and_reserve,
                       resolve(IF.REALIZATION_MAP["compare_and_reserve"]))
    assert _sigs_match(IF.settle, resolve(IF.REALIZATION_MAP["settle"]))
    assert _sigs_match(IF.reconcile_pending,
                       resolve(IF.REALIZATION_MAP["reconcile_pending"]))
    assert _sigs_match(IF.get_state,
                       resolve(IF.REALIZATION_MAP["get_state"]))
    assert _sigs_match(IF.calculate_cost,
                       resolve(IF.REALIZATION_MAP["calculate_cost"]))


def test_d08_kb_loader_signatures_exact():
    assert _sigs_match(IF.read_kb, resolve(IF.REALIZATION_MAP["read_kb"]))
    assert _sigs_match(IF.resolve_exact_id,
                       resolve(IF.REALIZATION_MAP["resolve_exact_id"]))
    assert _sigs_match(IF.propose_update,
                       resolve(IF.REALIZATION_MAP["propose_update"]))


def test_d09_http_routes_exact_set(tmp_path):
    client = _served_entry("GET", "/api/v1/providers", tmp_path)
    app = client.app
    real = set()
    for route in getattr(app, "routes", []):
        for m in (getattr(route, "methods", None) or set()):
            real.add((m.upper(), getattr(route, "path", "")))
    assert set(IF.HTTP_ROUTES) == real


def test_d10_registry_module_fns_exact():
    for name in ("register_provider", "get_provider", "list_providers",
                 "record_health", "remove_provider"):
        target = resolve(IF.REALIZATION_MAP[name])
        assert "." not in target.__qualname__, \
            "%s: frozen 3.2 wants a module-level function, real is %s" % (
                name, target.__qualname__)
        assert _sigs_match(getattr(IF, name), target), name


def test_d11_probe_usage_signature_exact():
    assert _sigs_match(IF.probe_usage,
                       resolve(IF.REALIZATION_MAP["probe_usage"]))


def test_d12_resolve_model_signature_exact():
    assert _sigs_match(IF.resolve_model,
                       resolve(IF.REALIZATION_MAP["resolve_model"]))


def test_d13_pick_pool_strategy_signature_exact():
    assert _sigs_match(IF.pick_pool_strategy,
                       resolve(IF.REALIZATION_MAP["pick_pool_strategy"]))


def test_d14_backend_handler_signatures_exact():
    assert _sigs_match(IF.get_role_pools,
                       resolve(IF.REALIZATION_MAP["get_role_pools"]))
    assert _sigs_match(IF.set_role_pool,
                       resolve(IF.REALIZATION_MAP["set_role_pool"]))
    assert _sigs_match(IF.get_kb_status,
                       resolve(IF.REALIZATION_MAP["get_kb_status"]))
    assert _sigs_match(IF.get_models,
                       resolve(IF.REALIZATION_MAP["get_models"]))
    assert _sigs_match(IF.apply_proposal,
                       resolve(IF.REALIZATION_MAP["apply_proposal"]))


# K04 D15 (ruling ii, HD_VERDICT_D15_ADD): d.ts-conformance check.
# The stub frontend/src/settings/ProvidersPage/k04-iface.d.ts (types
# ONLY, frozen sha 9594321e) is the oracle: each ruled REQUIRED prop is
# present as required, each ACCEPTED added prop is present (optional-ness
# per d.ts: timeoutMs? refreshKey? loadEntries? optional, rest required),
# and the same sets match the implementation tsx prop types parsed from
# source text (no tsx import). The behaviour leg
# k04-iface.contract.test.tsx covers match/mismatch/token-less/token-ok.

D15_IFACE_SPECS = (
    ("ConnectDialogProps", "ConnectDialog.tsx", "ConnectDialogProps",
     ["preset_id"],
     ["preset", "open", "store", "onClose", "onConnected"],
     ["timeoutMs"]),
    ("DisconnectDialogProps", "DisconnectDialog.tsx",
     "DisconnectDialogProps",
     ["provider_id"],
     ["providerLabel", "secretId", "open", "store", "sessionToken",
      "onClose", "onDisconnected"],
     []),
    ("LeftoverKeyFinderProps", "LeftoverKeyFinder.tsx",
     "LeftoverKeyFinderProps",
     [],
     ["store", "sessionToken", "linkedSecretIds"],
     ["refreshKey", "loadEntries"]),
)

D15_BEHAVIOUR_CASES = ("match:", "mismatch:", "token-less", "token-ok")


def iface_block(text, iface_name):
    match = re.search(r"interface\s+%s\s*\{(.*?)\}" % re.escape(iface_name),
                      text, re.DOTALL)
    assert match, "missing %s in k04-iface.d.ts" % iface_name
    return match.group(1)


def prop_optionality(block):
    return dict(re.findall(r"^\s*(\w+)(\?)?\s*:", block, re.MULTILINE))


def test_d15_frontend_props_exact():
    with open(os.path.join(_FRONT, "k04-iface.d.ts"),
              encoding="utf-8") as fh:
        dts = fh.read()
    leg_path = os.path.join(_FRONT, "k04-iface.contract.test.tsx")
    assert os.path.isfile(leg_path), "missing behaviour leg %s" % leg_path
    with open(leg_path, encoding="utf-8") as fh:
        leg = fh.read()
    for case in D15_BEHAVIOUR_CASES:
        assert case in leg, "behaviour leg missing case %s" % case
    for spec in D15_IFACE_SPECS:
        iface_name, tsx_name, tsx_type, req, added_req, added_opt = spec
        stub_props = prop_optionality(iface_block(dts, iface_name))
        for name in req + added_req:
            assert name in stub_props, (iface_name, name)
            assert not stub_props[name], (iface_name, name)
        for name in added_opt:
            assert stub_props.get(name) == "?", (iface_name, name)
        assert sorted(stub_props) == sorted(req + added_req + added_opt), \
            iface_name
        impl_props = prop_optionality(
            props_block(front_text(tsx_name), tsx_type))
        assert impl_props == stub_props, (iface_name, tsx_name)


# ------------------------------------------------- record shapes (ordered)

RECORD_PAIRS = [
    ("SecretRef", IF.SecretRef, RT.SecretRef),
    ("ProviderContracts", IF.ProviderContracts, PAPI.ProviderContracts),
    ("FallbackRecord", IF.FallbackRecord, RT.FallbackRecord),
    ("RoutingPolicy", IF.RoutingPolicy, RT.RoutingPolicy),
    ("OptimizationPolicy", IF.OptimizationPolicy, RT.OptimizationPolicy),
    ("RoleModelProfile", IF.RoleModelProfile, RT.RoleModelProfile),
    ("DefaultManagerProfile", IF.DefaultManagerProfile,
     RT.DefaultManagerProfile),
    ("RoutingAssignment", IF.RoutingAssignment, RT.RoutingAssignment),
    ("RoutingEvidenceSnapshot", IF.RoutingEvidenceSnapshot,
     RT.RoutingEvidenceSnapshot),
    ("RoutingDecision", IF.RoutingDecision, RT.RoutingDecision),
    ("BudgetState", IF.BudgetState, BG.BudgetState),
    ("BudgetReservation", IF.BudgetReservation, BG.BudgetReservation),
    ("BudgetSettlement", IF.BudgetSettlement, BG.BudgetSettlement),
    ("MetricRecord", IF.MetricRecord, BT.MetricRecord),
    ("PricingSnapshot", IF.PricingSnapshot, BT.PricingSnapshot),
]


@pytest.mark.parametrize("name,stub,real", RECORD_PAIRS,
                         ids=[p[0] for p in RECORD_PAIRS])
def test_record_field_order_matches_real(name, stub, real):
    assert field_names(stub) == field_names(real)


def test_shared_shape_field_order():
    assert field_names(IF.ProviderRef) == ["provider_id", "provider_instance"]
    assert field_names(IF.ModelRef) == ["provider_id", "model"]
    assert field_names(IF.CandidateView) == [
        "provider_id", "provider_instance", "model",
        "effective_capability_ref", "price_basis", "quality_basis",
        "modality_ok", "rejected", "reject_reason"]
    assert field_names(IF.ReasonText) == [
        "task_class", "fit_basis", "price_basis", "quality_basis",
        "rejected"]
    assert field_names(IF.ReservationRequest) == [
        "project_id", "task_id", "run_id", "estimated_amount",
        "provider_request_ref"]
    assert field_names(IF.CostLine) == ["amount", "currency",
                                        "pricing_snapshot_id"]


def test_telemetry_event_keys_match_builder():
    built = BT.build_telemetry_event(
        event_id="e-iface", project_id="p-iface",
        timestamp="2026-01-01T00:00:00+00:00", event_type="run_started")
    assert set(built) == set(IF.TelemetryEvent.__annotations__)


def test_usage_capability_keys_match_real_ordered():
    assert tuple(IF.UsageReportingCapabilities.__annotations__) == \
        tuple(UPR.USAGE_CAPABILITY_FIELDS)


def test_kb_envelope_and_sourced_keys():
    row = KB.make_model_row("p-iface", "m-iface")
    assert set(row) == set(IF.KB_ROW_KEYS)
    assert set(KB.sourced()) == set(IF.KB_SOURCED_FIELD_KEYS)
    assert set(IF.ModelContracts.__annotations__) == set(IF.KB_ROW_KEYS)

# ---------------------------------------------------------------------------
# K04 BEHAVIOR CONTRACTS (CTBEHAV extension; appended 2026-10-26, nothing
# above this marker was modified).
#
# 11-vs-9 rule: sec6 lists 11 K04 DRIFT rows, but only 9 are consumer-visible
# raise conditions -- PRICE_UNKNOWN_EXPENSIVE is a K04-internal treatment flag
# (penalty behavior at routing/router.py:468, never raised) and KEY_SAVE_TIMEOUT
# is a K04-internal frontend concern; PENDING_RECONCILIATION and
# CREDENTIAL_ENTRY_MISSING are already MATCH (pinned GREEN elsewhere).
#
# Section (a) rule: each test_bNN drives the REAL behavior module into the
# frozen error condition and asserts the frozen ERROR_CODES_K04 literal
# surfaces (raised or recorded with that exact string). Real code that
# raises a differently-named error (or BLOCKED-with-reason) fails: RED
# until lane facades map the condition to the literal code.
# ---------------------------------------------------------------------------
from agent_si.routing import roles as _RL
from agent_si.routing import router as _RTR
from agent_si.routing import kb_port as _KBP
from agent_si.model_kb import updater as _KUPD
from agent_si.providers.registry.registry import ProviderRegistry as _ProviderRegistry
from agent_si.providers.registry.contracts import SecretRef as _SecretRef


def _b_policy(**kw):
    d = dict(policy_id="rp-b", version=1,
             created_at="2026-01-01T00:00:00+00:00", hash="h",
             task_class="coding", risk_level="LOW",
             strict_min=1.0, tolerant_min=0.85, confidence_min=0.7,
             sample_min=20, freshness_requirement="CURRENT",
             local_allowed=True, split_allowed=True, cloud_required=False)
    d.update(kw)
    return RT.RoutingPolicy(**d)


def _b_opt(**kw):
    d = dict(policy_id="op-b", version=1,
             created_at="2026-01-01T00:00:00+00:00", hash="h",
             required_quality=0.8, max_risk="HIGH",
             weight_quality=1.0, weight_cost=1.0, weight_latency=1.0,
             weight_cloud_tokens=1.0, local_preference=False,
             deadline=None, budget_limit=None)
    d.update(kw)
    return RT.OptimizationPolicy(**d)


class _BKb:
    # FAKE-OF: agent_si.routing.kb_port.KbReader (named KB rows for tests).
    # Input plumbing only: every RED assert below inspects REAL router
    # output, so this never stands in for the proof.
    def __init__(self, rows):
        self._rows = dict(rows)

    def facts(self, provider, model):
        return self._rows.get((provider, model))

    def models(self, provider=None):
        return [f for (p, _m), f in self._rows.items()
                if provider is None or p == provider]


def _b_facts(provider, model, **kw):
    d = dict(provider=provider, model=model,
             task_fit={"coding": 0.9, "text": 0.9, "general": 0.9},
             strict_pass_rate=0.9, tolerant_pass_rate=0.9,
             sample_count=50, confidence=0.9, freshness="CURRENT",
             input_price=0.01, output_price=0.03,
             modalities=("text",), assessed_risk="LOW",
             fields_state="MEASURED", verified_static=True,
             source="ctbehav", measured_at="2026-01-01T00:00:00+00:00",
             latency_ms=400.0)
    d.update(kw)
    return _KBP.KbModelFacts(**d)


def _b_select(task_extra=None, views=(), kb_rows=None, **ctx_extra):
    task = {"project_id": "p1", "task_id": "t1", "run_id": "r1",
            "role": "worker", "task_class": "coding"}
    task.update(task_extra or {})
    ctx = {
        "task_contracts": {"tc-b": task},
        "routing_policies": {"rp-b": _b_policy()},
        "optimization_policies": {"op-b": _b_opt()},
        "budget_state": {"eligible": True, "ref": "bs-b"},
        "resource_state": {"eligible": True, "ref": "rs-b"},
        "kb": _BKb(kb_rows or {}),
        "provider_health": {"pa": RT.ProviderHealth(provider="pa",
                                                    status="ONLINE")},
        "model_health": {("pa", "m1"): RT.ModelHealth(provider="pa",
                                                      model="m1",
                                                      status="READY")},
        "provider_capabilities": {"pa": ("text",)},
    }
    ctx.update(ctx_extra)
    # Exact 6-ref facade (no **ctx): bind server scope, mechanical only.
    _RTR.bind_select_scope(ctx)
    try:
        return _RTR.select("tc-b", list(views), "rp-b", "op-b", "bs-b",
                           "rs-b")
    finally:
        _RTR.unbind_select_scope()


class _BStore:
    # Port plumbing: in-memory credential-store double (has/delete only).
    def __init__(self):
        self._entries = {}

    def seed(self, secret_id):
        self._entries[secret_id] = "seed"

    def has(self, secret_id):
        return secret_id in self._entries

    def delete(self, secret_id):
        del self._entries[secret_id]


class _BSink:
    # Port plumbing: in-memory audit sink double.
    def __init__(self):
        self.records = []

    def append(self, record):
        self.records.append(dict(record))


def test_b01_no_profile_blocked_recorded():
    # K04.md row 87 -> src/agent_si/routing/roles.py:79-88.
    table = _RL.RoleTable()
    res = table.resolve("p1", "worker")
    assert res.status == "BLOCKED"
    assert "pick PINNED or AUTO" in res.reason
    assert "NO_PROFILE_BLOCKED" in res.reason, (
        "DRIFT row 87: fresh-install BLOCKED carries a reason string, not "
        "the frozen code; got %r (lane must map BLOCKED-with-reason to "
        "NO_PROFILE_BLOCKED)" % (res.reason,))


def test_b02_no_eligible_candidate_recorded():
    # K04.md row 88 -> src/agent_si/routing/router.py:463-467 (empty pool
    # arm). NOTE 2026-10-26: the lane mapped this arm mid-task (the frozen
    # facade raises ValueError carrying NO_ELIGIBLE_CANDIDATE); this test
    # pins the completed mapping, so it is GREEN.
    with pytest.raises(ValueError) as excinfo:
        _b_select(views=[])
    assert "no candidates left" in str(excinfo.value)
    assert "NO_ELIGIBLE_CANDIDATE" in str(excinfo.value), (
        "DRIFT row 88: empty-pool block says %r without the frozen code "
        "(lane must surface NO_ELIGIBLE_CANDIDATE)"
        % (excinfo.value,))


def test_b03_modality_mismatch_recorded():
    # K04.md row 89: _split_views (router.py:998-1021) never checks the
    # frozen CandidateView.modality_ok flag, so a modality-false view routes.
    outcome = _b_select(
        views=[{"provider_id": "pa", "model": "m1",
                "modality_ok": False, "rejected": False}],
        kb_rows={("pa", "m1"): _b_facts("pa", "m1")})
    assert outcome.status == "ROUTED", (
        "setup broke: modality_ok=False view did not route: %r"
        % (outcome.decision.reason,))
    assert "MODALITY_MISMATCH" in outcome.decision.reason, (
        "DRIFT row 89: modality_ok=False routed with no frozen code in %r "
        "(lane must reject modality-false views with MODALITY_MISMATCH)"
        % (outcome.decision.reason,))


def test_b04_provider_unevidenced_recorded():
    # K04.md row 90 -> src/agent_si/providers/registry/provider_api.py:279-288.
    api = PAPI.ProviderAPI(_ProviderRegistry(), _BStore(), _BSink())
    view = api.register_provider(
        {"provider_id": "openai", "type": "openai",
         "base_url": "http://127.0.0.1:9/v1"},
        _SecretRef(secret_id="s-b04", provider_id="openai"), model="m-b04")
    assert view.evidenced is False
    assert api.is_evidenced("openai") is False
    surfaced = repr(view) + "|evidenced=%s" % (view.evidenced,)
    assert "PROVIDER_UNEVIDENCED" in surfaced, (
        "DRIFT row 90: unevidenced view carries no frozen code: %r "
        "(lane must surface PROVIDER_UNEVIDENCED)" % (surfaced,))


def test_b05_budget_soft_warn_recorded():
    # K04.md row 92 -> src/agent_si/budget/gate.py:496-500.
    gate = BG.BudgetGate()
    gate.configure_project(project_id="p1", currency="USD",
                            budget_limit="10.00", soft_limit="7.00",
                            hard_limit="10.00")
    res = gate.compare_and_reserve(
        {"project_id": "p1", "task_id": "t1", "run_id": "r1",
         "reservation_id": "res-b05", "estimated_amount": "8.00",
         "reserved_at": "2026-10-26T00:00:00Z",
         "expires_at": "2026-10-27T00:00:00Z"})
    assert res.ok is True
    assert res.warning and "soft budget limit reached" in res.warning
    assert "BUDGET_SOFT_WARN" in res.warning, (
        "DRIFT row 92: soft warning says %r without the frozen code "
        "(lane must record BUDGET_SOFT_WARN)" % (res.warning,))


def test_b06_budget_hard_blocked_raised():
    # K04.md row 93 -> src/agent_si/budget/gate.py:547-556.
    gate = BG.BudgetGate()
    gate.configure_project(project_id="p1", currency="USD",
                            budget_limit="10.00", soft_limit="7.00",
                            hard_limit="10.00")
    gate.compare_and_reserve(
        {"project_id": "p1", "task_id": "t1", "run_id": "r1",
         "reservation_id": "res-b06a", "estimated_amount": "8.00",
         "reserved_at": "2026-10-26T00:00:00Z",
         "expires_at": "2026-10-27T00:00:00Z"})
    with pytest.raises(BG.BudgetBlockedError) as excinfo:
        gate.compare_and_reserve(
            {"project_id": "p1", "task_id": "t1", "run_id": "r1",
             "reservation_id": "res-b06b", "estimated_amount": "8.00",
             "reserved_at": "2026-10-26T00:00:00Z",
             "expires_at": "2026-10-27T00:00:00Z"})
    assert "hard budget limit blocks" in str(excinfo.value)
    assert "BUDGET_HARD_BLOCKED" in str(excinfo.value), (
        "DRIFT row 93: hard block raises %r without the frozen code "
        "(lane must raise BUDGET_HARD_BLOCKED)" % (excinfo.value,))


def test_b07_duplicate_settlement_refused_raised():
    # K04.md row 95 -> src/agent_si/budget/gate.py:642-647.
    gate = BG.BudgetGate()
    gate.configure_project(project_id="p1", currency="USD",
                            budget_limit="10.00", soft_limit="7.00",
                            hard_limit="10.00")
    gate.compare_and_reserve(
        {"project_id": "p1", "task_id": "t1", "run_id": "r1",
         "reservation_id": "res-b07", "estimated_amount": "4.00",
         "reserved_at": "2026-10-26T00:00:00Z",
         "expires_at": "2026-10-27T00:00:00Z"})
    first = gate.settle(
        {"reservation_id": "res-b07", "actual_amount": "1.50",
         "provider_usage_evidence_ref": "usage-b07",
         "provider_request_ref": "req-b07", "source": "provider_usage_api",
         "settled_at": "2026-10-26T01:00:00Z"})
    assert first.status == "SETTLED"
    with pytest.raises(BG.DuplicateSettlementError) as excinfo:
        gate.settle(
            {"reservation_id": "res-b07", "actual_amount": "1.50",
             "provider_usage_evidence_ref": "usage-b07",
             "provider_request_ref": "req-b07", "source": "provider_usage_api",
             "settled_at": "2026-10-26T01:00:00Z"})
    assert "duplicate settlement refused" in str(excinfo.value)
    assert "DUPLICATE_SETTLEMENT_REFUSED" in str(excinfo.value), (
        "DRIFT row 95: duplicate settle raises %r without the frozen code "
        "(lane must raise DUPLICATE_SETTLEMENT_REFUSED)" % (excinfo.value,))


def test_b08_kb_validation_failed_raised():
    # K04.md row 96 -> src/agent_si/model_kb/updater.py:266 (raises the
    # KB_VALIDATION_FAILED subclass, but the message lacks the literal).
    catalog = KB.make_catalog([KB.make_model_row("p8", "m8")])
    bad = {"source_url": "https://platform.openai.com/docs/b08",
           "retrieved_at": "2026-10-26",
           "changes": [{"provider_id": "p8", "model_id": "m8",
                        "field": "no_such_field", "new": "x",
                        "source": "https://platform.openai.com/docs/b08",
                        "retrieved_at": "2026-10-26"}]}
    with pytest.raises(_KUPD.ProposalRejectedError) as excinfo:
        _KUPD.apply_proposal(catalog, bad, user_confirmed=True)
    assert "unknown field" in str(excinfo.value)
    assert "KB_VALIDATION_FAILED" in str(excinfo.value), (
        "DRIFT row 96: invalid proposal raises %r without the frozen code "
        "(lane must raise KB_VALIDATION_FAILED)" % (excinfo.value,))


def test_b09_kb_proposal_not_approved_raised():
    # K04.md row 97 -> src/agent_si/model_kb/updater.py:262 (raises the
    # KB_PROPOSAL_NOT_APPROVED subclass, but the message lacks the literal).
    catalog = KB.make_catalog([KB.make_model_row("p9", "m9")])
    with pytest.raises(_KUPD.ConfirmationRequiredError) as excinfo:
        _KUPD.apply_proposal(catalog, {"changes": []}, user_confirmed=False)
    assert "explicit user confirmation" in str(excinfo.value)
    assert "KB_PROPOSAL_NOT_APPROVED" in str(excinfo.value), (
        "DRIFT row 97: unapproved apply raises %r without the frozen code "
        "(lane must raise KB_PROPOSAL_NOT_APPROVED)" % (excinfo.value,))


# ---------------------------------------------------------------------------
# Section (b): sec4 route entry points (1:1 to the 12 K04.md sec4 DRIFT rows
# 64-75). Each test looks the frozen (method, path) up in the SERVED entry
# point (pools_routes.ROUTES / _DISPATCH / serve) -- never a lane module
# function directly -- and invokes the dispatched handler, asserting it
# reaches a REAL implementation with a genuine payload. Missing or
# differently-guarded entries fail: RED until lanes mount the frozen routes.
# ---------------------------------------------------------------------------
from agent_si.routing.store import RoutingStore as _RoutingStore
from agent_si.backend import modelkb as _MKB


def _served_entry(method, path, tmp_path=None):
    try:
        from agent_si.backend.app import create_app
    except ImportError:
        pytest.fail("create_app missing")
    import fastapi.testclient
    store_dir = str(tmp_path) if tmp_path is not None else "tmp/test-seam"
    app = create_app({"store_dir": store_dir},
                     auth_hook=None, rate_hook=None, model_factory=None)
    client = fastapi.testclient.TestClient(app)
    return client


def _b_ctx(tmp_path):
    return PR.RoutingCtx(store=_RoutingStore(str(tmp_path)),
                         role_table=_RL.RoleTable(), kb=None)


def test_c01_providers_list_entry(tmp_path):
    # K04.md row 64 -> frozen GET /api/v1/providers via the served app.
    client = _served_entry("GET", "/api/v1/providers", tmp_path)
    resp = client.get("/api/v1/providers")
    assert resp.status_code != 404, resp.text


def test_c02_connect_entry(tmp_path):
    # K04.md row 65 -> frozen POST /api/v1/providers/connect via the
    # served app.
    client = _served_entry("POST", "/api/v1/providers/connect", tmp_path)
    resp = client.post("/api/v1/providers/connect", json={})
    assert resp.status_code != 404, resp.text


def test_c03_disconnect_entry(tmp_path):
    # K04.md row 66 -> frozen POST /api/v1/providers/{id}/disconnect
    # via the served app.
    client = _served_entry(
        "POST", "/api/v1/providers/{id}/disconnect", tmp_path)
    resp = client.post("/api/v1/providers/p1/disconnect", json={})
    assert resp.status_code != 404, resp.text


def test_c04_models_entry(tmp_path):
    # K04.md row 67 -> frozen GET /api/v1/providers/{id}/models?query
    # via the served app.
    client = _served_entry(
        "GET", "/api/v1/providers/{id}/models", tmp_path)
    resp = client.get("/api/v1/providers/p1/models")
    assert resp.status_code != 404, resp.text


def test_c05_chatmodels_entry(tmp_path):
    # K04.md row 68 -> frozen GET /api/v1/chat/models via the served app.
    client = _served_entry("GET", "/api/v1/chat/models", tmp_path)
    resp = client.get("/api/v1/chat/models")
    assert resp.status_code != 404, resp.text


def test_c06_roles_pools_get_entry(tmp_path):
    # K04.md row 69 -> frozen GET /api/v1/roles/pools via the served app
    # (reads are open: no auth headers; already mounted by lane A2,
    # pinned here).
    client = _served_entry("GET", "/api/v1/roles/pools", tmp_path)
    resp = client.get("/api/v1/roles/pools", params={"project_id": "p1"})
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert isinstance(payload.get("roles"), list) and payload["roles"], payload
    assert {"role", "mode", "provider", "model", "pool", "strategy"} <= set(
        payload["roles"][0]), payload


def test_c07_roles_pools_put_entry(tmp_path):
    # K04.md row 70 -> frozen PUT /api/v1/roles/pools via the served app
    # (already mounted by lane A2, pinned here).
    # HD V2 ruling 5: USER writes guard the session token first (401/403
    # when token-less); the token rides the x-actor + x-ui-session-token
    # headers, so valid headers are passed here and success is observed.
    client = _served_entry("PUT", "/api/v1/roles/pools", tmp_path)
    body = {"project_id": "p1", "role": "worker", "mode": "AUTO",
            "provider": None, "model": None, "pool": [], "strategy": "AUTO"}
    resp = client.put("/api/v1/roles/pools", json=body,
                      headers={"x-actor": "ui-test-c07",
                               "x-ui-session-token": "ui-test-c07"})
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["profile"]["role"] == "worker", payload
    assert payload["profile"]["mode"] == "AUTO", payload


def test_c08_routing_why_concrete_id_dispatch(tmp_path):
    # K04.md row 71 -> frozen GET /api/v1/routing/decision/{id}/why via
    # the served app. The template is registered, but a concrete decision
    # id must route to it (template/concrete routing unwired =
    # HD-request candidate).
    client = _served_entry(
        "GET", "/api/v1/routing/decision/{id}/why", tmp_path)
    routes = {(m.upper(), getattr(route, "path", ""))
              for route in getattr(client.app, "routes", [])
              for m in (getattr(route, "methods", None) or set())}
    assert ("GET", "/api/v1/routing/decision/{id}/why") in routes
    concrete = "/api/v1/routing/decision/rd-1/why"
    resp = client.get(concrete)
    assert resp.status_code != 404, (
        "HD-request candidate: frozen why route is template-registered but "
        "the served app cannot route concrete ids like %r "
        "(template/concrete routing unwired): %s" % (concrete, resp.text))


def test_c09_budget_entry(tmp_path):
    # K04.md row 72 -> frozen GET /api/v1/budget via the served app
    # (reads are open). NOTE 2026-10-26: lane B2 mounted it
    # (budget/routes.py merged into PR.ROUTES via budget/__init__);
    # this test pins the completed wiring, so it is GREEN.
    client = _served_entry("GET", "/api/v1/budget", tmp_path)
    resp = client.get("/api/v1/budget")
    assert resp.status_code != 404, resp.text


def test_c10_kb_status_entry(tmp_path):
    # K04.md row 73 -> frozen GET /api/v1/kb/status via the served app.
    client = _served_entry("GET", "/api/v1/kb/status", tmp_path)
    resp = client.get("/api/v1/kb/status")
    assert resp.status_code != 404, resp.text


def test_c11_kb_apply_entry(tmp_path):
    # K04.md row 74 -> frozen POST /api/v1/kb/proposals/apply via the
    # served app.
    client = _served_entry(
        "POST", "/api/v1/kb/proposals/apply", tmp_path)
    resp = client.post("/api/v1/kb/proposals/apply", json={})
    assert resp.status_code != 404, resp.text


def test_c12_user_write_guard_entry(tmp_path):
    # K04.md row 75 -> frozen guard via the served app: USER writes check
    # the session token first (reads need none). A token-less USER write
    # (no x-actor + x-ui-session-token headers) must be refused.
    client = _served_entry("PUT", "/api/v1/roles/pools", tmp_path)
    body = {"project_id": "p1", "role": "worker", "mode": "AUTO",
            "provider": None, "model": None, "pool": [], "strategy": "AUTO"}
    resp = client.put("/api/v1/roles/pools", json=body)
    assert resp.status_code in (401, 403), (
        "DRIFT row 75: token-less USER write returns %s (%r); no "
        "actor/session-token guard on USER writes (HD-request candidate)"
        % (resp.status_code, resp.text))


# ---------------------------------------------------------------------------
# Section (c): sec7 wiring (one test per surface). For each cross-package
# surface (sec3 functions, sec4 routes, sec2 shapes) a PRODUCTION caller on
# the user path is invoked and the effect observed -- signature-only asserts
# never pass. Surfaces with no production caller yet FAIL and name the
# HD-request candidate; they never pass vacuously.
# ---------------------------------------------------------------------------
import copy
import json
from unittest import mock as _mock

from agent_si.model_kb import loader as _KLDR
from agent_si.providers.adapters import facades as _FAC


def test_w01_kb_apply_chain_reaches_updater():
    # sec3.4/sec3.7 surface: backend/modelkb.py forwards into
    # loader/updater; the bound catalog version bump is the observed effect.
    catalog = KB.make_catalog([KB.make_model_row("pw", "mw")])
    before = copy.deepcopy(KB.bound_catalog())
    KB.bind_catalog(catalog)
    try:
        fetched = json.dumps({"models": [
            {"provider_id": "pw", "model_id": "mw",
             "fields": {"purpose": "serves chat"}}]})
        proposal = _MKB.trigger_update(
            KB.bound_catalog(), "https://platform.openai.com/docs/w01",
            lambda _url: fetched, "2026-10-26T00:00:00Z")
        assert proposal["changes"], (
            "production trigger_update produced no change: %r" % (proposal,))
        pid = _MKB.stage_proposal(proposal)
        status, payload = _MKB.kb_proposal_apply(
            None, {}, {"proposal_id": pid, "approved_by_user": True})
        assert status == 200, payload
        assert payload["applied"] is True, payload
        live = KB.bound_catalog()
        assert live["version"]["kb_version"] == before["version"].get(
            "kb_version", 0) + 1, live["version"]
        row = _KLDR.find_row(live, "pw", "mw")
        assert row["fields"]["purpose"]["value"] == "serves chat", row
    finally:
        KB.bind_catalog(before)


def test_w02_pools_handler_reads_role_table_and_store(tmp_path):
    # sec3.6 surface: the served set_role handler persists through the real
    # role table and the real store; both effects are observed.
    store = _RoutingStore(str(tmp_path))
    table = _RL.RoleTable()
    ctx = PR.RoutingCtx(store=store, role_table=table, kb=None)
    fn = dict(PR._DISPATCH)[("post", "/api/v1/routing/role")]
    body = {"project_id": "p1", "role": "worker", "mode": "pool",
            "pool": [{"provider": "pa", "model": "m1"}],
            "strategy": "FALLBACK_ORDER"}
    status, payload = fn(ctx, {"session_token": "ui-test-w02"}, body)
    assert status == 200, payload
    assert table.get_profile("p1", "worker").mode == "pool"
    binding = store.get_pool("p1", "worker")
    assert binding is not None and binding["role"] == "worker", binding
    assert any(m.get("provider") == "pa" and m.get("model") == "m1"
               for m in binding["members"]), binding


def test_w03_registry_backs_connect_disconnect():
    # sec3.2 surface: provider_api backs key-only connect plus clean
    # disconnect (credential-store entry deleted too).
    store = _BStore()
    sink = _BSink()
    api = PAPI.ProviderAPI(_ProviderRegistry(), store, sink)
    view = api.connect_via_preset(
        "openai", _SecretRef(secret_id="s-w03", provider_id="openai"),
        model="m-w03")
    assert api.get_provider("openai") is not None
    assert view.provider_id == "openai"
    store.seed("s-w03")
    assert api.remove_provider("openai") is None
    assert api.get_provider("openai") is None


def test_w04_probe_usage_has_no_user_path_caller_HD_REQUEST():
    # sec3.3 surface: the REAL user-path caller check_provider_health
    # (resolve_model -> probe_usage) wires the usage probe (HD V2
    # ruling 7: a real caller on the user path now exists, never a fake
    # caller -- the fake here is only the injected transport, the caller
    # path resolve_model->probe_usage is real).
    def _fake_chat(_request):
        return {"usage": {"input_tokens": 10, "output_tokens": 5,
                          "cached_tokens": 0, "reasoning_tokens": 0}}

    _FAC.bind_provider(
        "openai", {"secret_id": "s-w04", "provider_id": "openai"},
        _fake_chat, "http://127.0.0.1:9/v1")
    try:
        result = _FAC.check_provider_health("openai", "m-w04")
    finally:
        _FAC.clear_provider_bindings()
        _FAC.clear_adapter_transports()
    assert result["provider_id"] == "openai"
    assert result["model_id"] == "m-w04"
    assert result["usage"]["state"] == "VERIFIED"


def test_w05_served_decide_calls_frozen_select(tmp_path):
    # sec7 call-surface (K04.md row 102): the served generic decide path
    # calls the frozen select facade (pools_routes.py:760). NOTE 2026-10-26:
    # worker B wired this mid-task; the unittest.mock spy observes the
    # production call (no behavior faked) and the routed outcome is the
    # observed effect. GREEN pin.
    kb = _BKb({("pa", "m1"): _b_facts("pa", "m1")})
    ctx = PR.RoutingCtx(
        store=_RoutingStore(str(tmp_path)), role_table=_RL.RoleTable(),
        kb=kb,
        provider_health={"pa": RT.ProviderHealth(provider="pa",
                                                  status="ONLINE")},
        model_health={("pa", "m1"): RT.ModelHealth(provider="pa",
                                                    model="m1",
                                                    status="READY")},
        provider_capabilities={"pa": ("text",)},
        resource_state={"eligible": True, "ref": "rs-w05"},
        budget_state={"eligible": True, "ref": "bs-w05"})
    decide = dict(PR._DISPATCH)[("post", "/api/v1/routing/decide")]
    calls = []
    real_select = _RTR.select

    def _spy(*args, **kwargs):
        calls.append((args, kwargs))
        return real_select(*args, **kwargs)

    body = {"project_id": "p1", "task_id": "t1", "run_id": "r1",
            "role": "worker", "task_class": "coding",
            "candidates": [{"provider": "pa", "model": "m1"}]}
    with _mock.patch.object(_RTR, "select", _spy):
        status, payload = decide(ctx, {"session_token": "ui-test-w05"},
                                 body)
    assert status == 200, payload
    assert calls, (
        "sec7 call-surface: served POST /api/v1/routing/decide did not "
        "call frozen select(...) (frozen §3 entry unwired on the user path)")
    assert payload["status"] == "ROUTED", payload


# ---------------------------------------------------------------------------
# Section (d): token-refusal on USER writes (K02 guard contract).
# Pre-K02 these are RED ("create_app missing" from the _served_entry seam).
# Post-K02 each refused write must return 401/403 and leave served state
# untouched. Wrappers bind impls at import, so served-state invariance
# (readable-state snapshot identical before/after) is the seam-true
# observable for real-implementation-NOT-called. Same seam as c01-c12
# (_served_entry + TestClient, tmp_path store_dir). No-token means no auth
# headers at all.


def test_c13_connect_no_token_refused(tmp_path):
    # Token-less POST /api/v1/providers/connect must be refused (401/403)
    # with no state change. Wrappers bind impls at import, so served-state
    # invariance is the seam-true observable for NOT-called.
    client = _served_entry("POST", "/api/v1/providers/connect", tmp_path)
    before = client.get("/api/v1/providers").text
    body = {"preset_id": "openai", "model": "m-t13",
            "key_ref": {"secret_id": "s-t13", "provider_id": "openai"}}
    resp = client.post("/api/v1/providers/connect", json=body)
    assert resp.status_code in (401, 403), (
        "token-less USER write returns %s (%r); expected 401/403"
        % (resp.status_code, resp.text))
    after = client.get("/api/v1/providers").text
    assert after == before, (
        "refused connect changed served providers state")


def test_c14_connect_wrong_token_refused(tmp_path):
    # Wrong-token POST /api/v1/providers/connect must be refused (401/403)
    # with no state change. Wrappers bind impls at import, so served-state
    # invariance is the seam-true observable for NOT-called.
    client = _served_entry("POST", "/api/v1/providers/connect", tmp_path)
    before = client.get("/api/v1/providers").text
    body = {"preset_id": "openai", "model": "m-t13",
            "key_ref": {"secret_id": "s-t13", "provider_id": "openai"}}
    headers = {"x-actor": "ui-test-t14",
               "x-ui-session-token": "WRONG-token-t14"}
    resp = client.post("/api/v1/providers/connect", json=body,
                       headers=headers)
    assert resp.status_code in (401, 403), (
        "wrong-token USER write returns %s (%r); expected 401/403"
        % (resp.status_code, resp.text))
    after = client.get("/api/v1/providers").text
    assert after == before, (
        "refused connect changed served providers state")


def test_c15_disconnect_no_token_refused(tmp_path):
    # Token-less POST /api/v1/providers/p1/disconnect must be refused
    # (401/403) with no state change. Wrappers bind impls at import, so
    # served-state invariance is the seam-true observable for NOT-called.
    client = _served_entry(
        "POST", "/api/v1/providers/{id}/disconnect", tmp_path)
    before = client.get("/api/v1/providers").text
    resp = client.post("/api/v1/providers/p1/disconnect", json={})
    assert resp.status_code in (401, 403), (
        "token-less USER write returns %s (%r); expected 401/403"
        % (resp.status_code, resp.text))
    after = client.get("/api/v1/providers").text
    assert after == before, (
        "refused disconnect changed served providers state")


def test_c16_disconnect_wrong_token_refused(tmp_path):
    # Wrong-token POST /api/v1/providers/p1/disconnect must be refused
    # (401/403) with no state change. Wrappers bind impls at import, so
    # served-state invariance is the seam-true observable for NOT-called.
    client = _served_entry(
        "POST", "/api/v1/providers/{id}/disconnect", tmp_path)
    before = client.get("/api/v1/providers").text
    headers = {"x-actor": "ui-test-t16",
               "x-ui-session-token": "WRONG-token-t16"}
    resp = client.post("/api/v1/providers/p1/disconnect", json={},
                       headers=headers)
    assert resp.status_code in (401, 403), (
        "wrong-token USER write returns %s (%r); expected 401/403"
        % (resp.status_code, resp.text))
    after = client.get("/api/v1/providers").text
    assert after == before, (
        "refused disconnect changed served providers state")


def test_c17_kb_apply_no_token_refused(tmp_path):
    # Token-less POST /api/v1/kb/proposals/apply must be refused (401/403)
    # with no state change. Wrappers bind impls at import, so served-state
    # invariance is the seam-true observable for NOT-called.
    client = _served_entry(
        "POST", "/api/v1/kb/proposals/apply", tmp_path)
    before = client.get("/api/v1/kb/status").text
    body = {"proposal_id": "kb-prop-t17", "approved_by_user": True}
    resp = client.post("/api/v1/kb/proposals/apply", json=body)
    assert resp.status_code in (401, 403), (
        "token-less USER write returns %s (%r); expected 401/403"
        % (resp.status_code, resp.text))
    after = client.get("/api/v1/kb/status").text
    assert after == before, (
        "refused kb apply changed served kb state")


def test_c18_kb_apply_wrong_token_refused(tmp_path):
    # Wrong-token POST /api/v1/kb/proposals/apply must be refused (401/403)
    # with no state change. Wrappers bind impls at import, so served-state
    # invariance is the seam-true observable for NOT-called.
    client = _served_entry(
        "POST", "/api/v1/kb/proposals/apply", tmp_path)
    before = client.get("/api/v1/kb/status").text
    body = {"proposal_id": "kb-prop-t17", "approved_by_user": True}
    headers = {"x-actor": "ui-test-t18",
               "x-ui-session-token": "WRONG-token-t18"}
    resp = client.post("/api/v1/kb/proposals/apply", json=body,
                       headers=headers)
    assert resp.status_code in (401, 403), (
        "wrong-token USER write returns %s (%r); expected 401/403"
        % (resp.status_code, resp.text))
    after = client.get("/api/v1/kb/status").text
    assert after == before, (
        "refused kb apply changed served kb state")


def test_c19_roles_pools_put_wrong_token_refused(tmp_path):
    # Wrong-token PUT /api/v1/roles/pools must be refused (401/403) with
    # no state change. Wrappers bind impls at import, so served-state
    # invariance is the seam-true observable for NOT-called.
    client = _served_entry("PUT", "/api/v1/roles/pools", tmp_path)
    before = client.get("/api/v1/roles/pools",
                        params={"project_id": "p1"}).text
    body = {"project_id": "p1", "role": "worker", "mode": "AUTO",
            "provider": None, "model": None, "pool": [], "strategy": "AUTO"}
    headers = {"x-actor": "ui-test-t19",
               "x-ui-session-token": "WRONG-token-t19"}
    resp = client.put("/api/v1/roles/pools", json=body, headers=headers)
    assert resp.status_code in (401, 403), (
        "wrong-token USER write returns %s (%r); expected 401/403"
        % (resp.status_code, resp.text))
    after = client.get("/api/v1/roles/pools",
                       params={"project_id": "p1"}).text
    assert after == before, (
        "refused roles-pools PUT changed served roles state")
