# OC-K04 continuation rows: ARCH-528 / ARCH-424 / UID-33 / UID-4 / UID-17.
# Served = the served dispatch tables (pools_routes._DISPATCH), the same
# convention as test_k04_iface_contract.py test_w05. No network, loopback
# TEST data only, memory secret store.
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import pytest

from agent_si.backend import pools_routes as PR
from agent_si.budget import telemetry as BT
from agent_si.context_keeper import register as REG
from agent_si.model_kb import updater
from agent_si.routing import kb_port as KB
from agent_si.routing import roles as RL
from agent_si.routing import router as R
from agent_si.routing import types as T
from agent_si.routing.store import RoutingStore

DEV_PROVIDER = "meta"
DEV_MODEL = "meta/muse-spark-1.3-contributor"


class _FakeKb(KB.KbReader):
    # FAKE-OF: KB.KbReader (in-memory facts dict for continuation tests)
    def __init__(self, facts):
        self._facts = dict(facts)

    def facts(self, provider, model):
        return self._facts.get((provider, model))

    def models(self, provider=None):
        return [f for (p, _m), f in self._facts.items()
                if provider is None or p == provider]


def _facts(provider, model, *, state="MEASURED", quality=0.9):
    return KB.KbModelFacts(
        provider=provider, model=model,
        task_fit={"coding": quality, "text": quality,
                  "general": quality},
        strict_pass_rate=quality, tolerant_pass_rate=quality,
        sample_count=50, confidence=0.9, freshness="CURRENT",
        input_price=0.01, output_price=0.03,
        modalities=("text",), assessed_risk="LOW",
        fields_state=state, verified_static=False,
        source="k04m9-test", measured_at="2026-10-29T00:00:00+00:00",
        latency_ms=400.0)


def _router_deps(kb):
    return R.RoutingDeps(
        kb=kb,
        provider_health={"pa": T.ProviderHealth(provider="pa",
                                                status="ONLINE")},
        model_health={("pa", "pa/m1"): T.ModelHealth(
            provider="pa", model="pa/m1", status="READY")},
        provider_capabilities={"pa": ("text",)},
        resource_state={"eligible": True, "ref": "rs-m9"},
        budget_state={"eligible": True, "ref": "bs-m9"})


def _request(candidates, **kw):
    policy = T.RoutingPolicy(
        policy_id="rp-m9", version=1, created_at="2026-10-29T00:00:00Z",
        hash="h", task_class="coding", risk_level="LOW",
        strict_min=1.0, tolerant_min=0.85, confidence_min=0.7,
        sample_min=20, freshness_requirement="CURRENT",
        local_allowed=True, split_allowed=True, cloud_required=False)
    opt = T.OptimizationPolicy(
        policy_id="op-m9", version=1, created_at="2026-10-29T00:00:00Z",
        hash="h", required_quality=0.8, max_risk="HIGH",
        weight_quality=1.0, weight_cost=1.0, weight_latency=1.0,
        weight_cloud_tokens=1.0, local_preference=False,
        deadline=None, budget_limit=None)
    d = dict(project_id="p1", task_id="t1", run_id="r1", role="worker",
             task_class="coding",
             required_capabilities=("text",), required_modalities=("text",),
             task_risk="LOW", routing_policy=policy,
             optimization_policy=opt, candidates=tuple(candidates),
             mode="AUTO")
    d.update(kw)
    return R.RoutingRequest(**d)


# ARCH-424: new prices arrive only as new immutable PricingSnapshot
# versions (BUILD_PLAN.md:1643).
def test_k04m9_price_version_must_advance():
    snapshot = {"pricing_snapshot_id": "snap-m9-1", "currency": "USD",
                "effective_at": "2026-10-29T00:00:00Z", "source": "t",
                "input_token_price": "0.001", "output_token_price": "0.002",
                "created_at": "2026-10-29T00:00:00Z"}
    # The same id is a silent-mutation path: refused.
    with pytest.raises(updater.PriceVersionError):
        updater.new_snapshot_version(
            snapshot, pricing_snapshot_id="snap-m9-1",
            created_at="2026-10-29T00:00:01Z")
    with pytest.raises(updater.PriceVersionError):
        updater.new_snapshot_version(
            snapshot, pricing_snapshot_id="",
            created_at="2026-10-29T00:00:01Z")
    # Unknown price fields are refused (no silent schema drift).
    with pytest.raises(updater.PriceVersionError):
        updater.new_snapshot_version(
            snapshot, pricing_snapshot_id="snap-m9-2",
            created_at="2026-10-29T00:00:01Z",
            free_lunch_price="0")
    fixed = updater.new_snapshot_version(
        snapshot, pricing_snapshot_id="snap-m9-2",
        created_at="2026-10-29T00:00:01Z", input_token_price="0.005")
    assert fixed["pricing_snapshot_id"] == "snap-m9-2"
    assert fixed["input_token_price"] == "0.005"
    assert snapshot["pricing_snapshot_id"] == "snap-m9-1"
    assert snapshot["input_token_price"] == "0.001"
    # The derived version prices real cost through the injected port.
    assert updater.compute_cost(
        lambda usage, snap: "0.010", {"in": 1}, fixed) == "0.010"


def test_k04m9_snapshot_registry_rejects_reuse():
    first = BT.make_snapshot(
        pricing_snapshot_id="ps-m9-reuse", provider_id="cloud-a",
        model_id="cloud-a/model-x", currency="USD",
        effective_at="2026-10-29T00:00:00Z", source="provider_pricing_api",
        input_token_price="0.001", output_token_price="0.002",
        created_at="2026-10-29T00:00:00Z")
    # Byte-identical re-registration is idempotent (restart-safe).
    again = BT.make_snapshot(
        pricing_snapshot_id="ps-m9-reuse", provider_id="cloud-a",
        model_id="cloud-a/model-x", currency="USD",
        effective_at="2026-10-29T00:00:00Z", source="provider_pricing_api",
        input_token_price="0.001", output_token_price="0.002",
        created_at="2026-10-29T00:00:00Z")
    assert again is first
    # Same id with new prices would rewrite served history: refused.
    with pytest.raises(BT.SnapshotIdReuseError):
        BT.make_snapshot(
            pricing_snapshot_id="ps-m9-reuse", provider_id="cloud-a",
            model_id="cloud-a/model-x", currency="USD",
            effective_at="2026-10-29T00:00:00Z",
            source="provider_pricing_api",
            input_token_price="0.009", output_token_price="0.002",
            created_at="2026-10-29T00:00:01Z")
    usage = BT.register_usage("use-m9-reuse", input_tokens=1000)
    priced = BT.CostCalculator.calculate("use-m9-reuse", "ps-m9-reuse")
    assert priced.amount == "1.000000", priced
    assert priced.pricing_snapshot_id == "ps-m9-reuse"


# ARCH-528: the AI SETTINGS Optimization Policy view presents required
# quality, the risk ceiling and the weights (BUILD_PLAN.md:1594).
def test_k04m9_optimization_policy_served(tmp_path):
    get_policy = dict(PR._DISPATCH)[(
        "get", "/api/v1/routing/optimization-policy")]
    ctx = PR.RoutingCtx(store=RoutingStore(str(tmp_path)),
                        role_table=RL.RoleTable(), kb=_FakeKb({}))
    status, payload = get_policy(ctx, {}, None)
    assert status == 200, payload
    assert payload["required_quality"] == 0.8, payload
    assert payload["max_risk"] == "HIGH", payload
    weights = payload["weights"]
    assert weights["weight_quality"] == 1.0, weights
    assert weights["weight_cost"] == 1.0, weights
    assert weights["weight_latency"] == 1.0, weights
    assert weights["weight_cloud_tokens"] == 1.0, weights


# UI_DELTA-33: the agent_si development model binding applies only to the
# product development process (BUILD_PLAN.md:1658).
def test_k04m9_dev_binding_scope_rule():
    assert REG.development_binding() == (DEV_PROVIDER, DEV_MODEL)
    assert REG.is_development_binding(DEV_PROVIDER, DEV_MODEL) is True
    assert REG.is_development_binding("pa", "pa/m1") is False
    # The dev-process use and an explicit PINNED choice pass.
    REG.check_development_binding_use(
        provider=DEV_PROVIDER, model=DEV_MODEL,
        use="product-development-process")
    REG.check_development_binding_use(
        provider=DEV_PROVIDER, model=DEV_MODEL,
        use="explicit-pinned-choice")
    # Silent production adoption paths are refused.
    for use in ("auto-selection", "role_default", "fallback",
                "production"):
        with pytest.raises(REG.DevelopmentBindingScopeError):
            REG.check_development_binding_use(
                provider=DEV_PROVIDER, model=DEV_MODEL, use=use)
    # Ordinary models pass every use.
    for use in ("auto-selection", "role_default", "fallback",
                "production", "product-development-process",
                "explicit-pinned-choice"):
        REG.check_development_binding_use(
            provider="pa", model="pa/m1", use=use)


def test_k04m9_dev_binding_never_auto_selected():
    kb = _FakeKb({
        ("pa", "pa/m1"): _facts("pa", "pa/m1", quality=0.85),
        (DEV_PROVIDER, DEV_MODEL): _facts(
            DEV_PROVIDER, DEV_MODEL, quality=0.99),
    })
    deps = R.RoutingDeps(
        kb=kb,
        provider_health={"pa": T.ProviderHealth(provider="pa",
                                                status="ONLINE"),
                         DEV_PROVIDER: T.ProviderHealth(
                             provider=DEV_PROVIDER, status="ONLINE")},
        model_health={("pa", "pa/m1"): T.ModelHealth(
            provider="pa", model="pa/m1", status="READY"),
            (DEV_PROVIDER, DEV_MODEL): T.ModelHealth(
                provider=DEV_PROVIDER, model=DEV_MODEL, status="READY")},
        provider_capabilities={"pa": ("text",), DEV_PROVIDER: ("text",)},
        resource_state={"eligible": True, "ref": "rs-m9"},
        budget_state={"eligible": True, "ref": "bs-m9"})
    out = R._select_impl(
        _request([T.CandidateModel(provider="pa", model="pa/m1"),
                  T.CandidateModel(provider=DEV_PROVIDER,
                                   model=DEV_MODEL)]),
        deps)
    assert out.status == "ROUTED", out.decision.reason
    assert out.decision.selected_model == "pa/m1", out.decision.reason
    assert "development binding" in out.decision.reason
    # An explicit PINNED choice of the dev model stays the user's call.
    pinned = R._select_impl(
        _request([T.CandidateModel(provider=DEV_PROVIDER,
                                   model=DEV_MODEL)],
                 mode="PINNED", pinned_provider=DEV_PROVIDER,
                 pinned_model=DEV_MODEL),
        deps)
    assert pinned.status == "ROUTED", pinned.decision.reason
    assert pinned.decision.selected_model == DEV_MODEL


# UI_DELTA-4: a Manager role model change needs a recorded canonical
# reason; an unjustified change is rejected (BUILD_PLAN.md:1657).
def test_k04m9_manager_change_needs_canonical_reason():
    profile = RL.make_default_manager_profile(provider="meta",
                                              model="meta/mgr-9")
    with pytest.raises(ValueError):
        RL.resolve_manager(
            profile, to_provider="alt", to_model="alt/shiny",
            trigger="fallback", trigger_ref="fb-m9",
            reason="mysterious_vibes",
            project_id="p1", task_id="t1", run_id="r1")
    with pytest.raises(ValueError):
        RL.resolve_manager(
            profile, to_provider="alt", to_model="alt/shiny",
            trigger="vibes", trigger_ref="fb-m9", reason="model_fail",
            project_id="p1", task_id="t1", run_id="r1")
    rec, profile2 = RL.resolve_manager(
        profile, to_provider="alt", to_model="alt/shiny",
        trigger="user_override", trigger_ref="uo-m9",
        reason="verification_fail",
        project_id="p1", task_id="t1", run_id="r1")
    assert profile2.version == 2
    assert (profile2.provider, profile2.model) == ("alt", "alt/shiny")
    assert rec.reason == "verification_fail"
    assert rec.reason in T.FALLBACK_REASONS


# UI_DELTA-17: TARGET_FLOW resolves every role model from configuration
# with no hard-coded role default (BUILD_PLAN.md:1673).
def test_k04m9_target_flow_from_configuration():
    config = {role: {"provider": "pa", "model": "pa/%s-1" % role}
              for role in T.ROLES}
    for role in T.ROLES:
        ref = RL.resolve_target_flow(config, role, project_id="p1")
        assert (ref.provider, ref.model) == ("pa", "pa/%s-1" % role)
    # A role without a configured entry never falls back to a literal.
    with pytest.raises(RL.TargetFlowMissingError):
        RL.resolve_target_flow({}, "worker", project_id="p1")
    partial = dict(config)
    del partial["auditor"]
    table = RL.RoleTable()
    with pytest.raises(RL.TargetFlowMissingError):
        RL.load_target_flow(table, partial, project_id="p1")
    loaded = RL.load_target_flow(table, config, project_id="p1")
    assert sorted(loaded) == sorted(T.ROLES)
    health = {"pa": T.ProviderHealth(provider="pa", status="ONLINE")}
    mhealth = {("pa", "pa/%s-1" % role): T.ModelHealth(
        provider="pa", model="pa/%s-1" % role, status="READY")
        for role in T.ROLES}
    for role in T.ROLES:
        res = table.resolve("p1", role, provider_health=health,
                            model_health=mhealth)
        assert res.status == "READY", (role, res.reason)
        assert (res.provider, res.model) == ("pa", "pa/%s-1" % role)
    # Unknown role keys and incomplete entries are refused, never ignored.
    with pytest.raises(RL.TargetFlowMissingError):
        RL.resolve_target_flow({"nope": ("pa", "pa/x")}, "nope",
                               project_id="p1")
    with pytest.raises(RL.TargetFlowMissingError):
        RL.resolve_target_flow({"worker": {"provider": "pa"}},
                               "worker", project_id="p1")


def test_k04m9_target_flow_served(tmp_path):
    post_flow = dict(PR._DISPATCH)[("post", "/api/v1/roles/target-flow")]
    ctx = PR.RoutingCtx(store=RoutingStore(str(tmp_path)),
                        role_table=RL.RoleTable(), kb=_FakeKb({}),
                        session_token="ui-test-m9")
    config = {role: {"provider": "pa", "model": "pa/%s-1" % role}
              for role in T.ROLES}
    status, payload = post_flow(
        ctx, {}, {"project_id": "p1", "target_flow": config})
    assert status == 200, payload
    assert sorted(payload["loaded"]) == sorted(T.ROLES), payload
    get_pools = dict(PR._DISPATCH)[("get", "/api/v1/roles/pools")]
    status2, payload2 = get_pools(ctx, {"project_id": "p1"}, None)
    assert status2 == 200, payload2
    by_role = {row["role"]: row for row in payload2["roles"]}
    assert by_role["worker"]["provider"] == "pa", by_role
    # Partial configuration is refused before anything is stored.
    ctx2 = PR.RoutingCtx(store=RoutingStore(str(tmp_path)),
                         role_table=RL.RoleTable(), kb=_FakeKb({}),
                         session_token="ui-test-m9")
    status3, payload3 = post_flow(
        ctx2, {}, {"project_id": "p1", "target_flow": {"worker": config["worker"]}})
    assert status3 == 400, payload3
    assert payload3["code"] == "NO_TARGET_FLOW_DEFAULT", payload3
