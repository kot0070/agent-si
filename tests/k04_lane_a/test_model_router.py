# K04 Lane A2 — model router tests (RED first, then GREEN).
# Self-sufficient: portable sys.path bootstrap, no other coder's files needed.
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import pytest

from dataclasses import dataclass as _dataclass

from agent_si.routing import types as T
from agent_si.routing import router as R
from agent_si.routing import fallback as F
from agent_si.routing import roles as RL
from agent_si.routing import pools as P
from agent_si.routing import kb_port as KB
from agent_si.routing import telemetry_port as TP
from agent_si.routing.store import RoutingStore
from agent_si.backend import pools_routes as PR

DEV_MODEL_ID = "meta/muse-spark-1.3-contributor"


# ---------------------------------------------------------------- fakes

class FakeKb(KB.KbReader):
    # FAKE-OF: KB.KbReader (in-memory facts dict for selection tests)
    def __init__(self, facts):
        self._facts = dict(facts)

    def facts(self, provider, model):
        return self._facts.get((provider, model))

    def models(self, provider=None):
        return [f for (p, _m), f in self._facts.items()
                if provider is None or p == provider]


def make_facts(provider, model, *, fit=0.9, quality=0.9, price_in=0.01,
               price_out=0.03, modalities=("text", "tools", "coding"),
               risk="LOW", state="MEASURED", static=False, sample=50,
               conf=0.9, fresh="CURRENT", latency_ms=400.0):
    return KB.KbModelFacts(
        provider=provider, model=model,
        task_fit={"coding": fit, "text": fit, "general": fit},
        strict_pass_rate=quality, tolerant_pass_rate=quality,
        sample_count=sample, confidence=conf, freshness=fresh,
        input_price=price_in, output_price=price_out,
        modalities=modalities, assessed_risk=risk,
        fields_state=state, verified_static=static,
        source="fake", measured_at="2026-01-01T00:00:00+00:00",
        latency_ms=latency_ms)


def pol(task_class="coding", **kw):
    d = dict(policy_id="rp-1", version=1,
             created_at="2026-01-01T00:00:00+00:00", hash="h",
             task_class=task_class, risk_level="LOW",
             strict_min=1.0, tolerant_min=0.85, confidence_min=0.7,
             sample_min=20, freshness_requirement="CURRENT",
             local_allowed=True, split_allowed=True, cloud_required=False)
    d.update(kw)
    return T.RoutingPolicy(**d)


def opt(**kw):
    d = dict(policy_id="op-1", version=1,
             created_at="2026-01-01T00:00:00+00:00", hash="h",
             required_quality=0.8, max_risk="HIGH",
             weight_quality=1.0, weight_cost=1.0, weight_latency=1.0,
             weight_cloud_tokens=1.0, local_preference=False,
             deadline=None, budget_limit=None)
    d.update(kw)
    return T.OptimizationPolicy(**d)


def up(provider, status="ONLINE"):
    return T.ProviderHealth(provider=provider, status=status)


def mh(provider, model, status="READY"):
    return T.ModelHealth(provider=provider, model=model, status=status)


def cand(provider, model, **kw):
    return T.CandidateModel(provider=provider, model=model, **kw)


def req(candidates, **kw):
    d = dict(project_id="p1", task_id="t1", run_id="r1", role="worker",
             task_class="coding",
             required_capabilities=("text", "tools"),
             required_modalities=("text",),
             task_risk="LOW", routing_policy=pol(), optimization_policy=opt(),
             candidates=tuple(candidates), mode="AUTO")
    d.update(kw)
    return R.RoutingRequest(**d)


def deps(kb, providers, models, caps=None, store=None, emitter=None,
         resource=None, budget=None, manager_profile=None):
    return R.RoutingDeps(
        kb=kb,
        provider_health={p: up(p, s) for p, s in providers.items()},
        model_health={(p, m): mh(p, m, s) for (p, m), s in models.items()},
        provider_capabilities=dict(caps or {}),
        resource_state={"eligible": True, "ref": "rs-1"} if resource is None else resource,
        budget_state={"eligible": True, "ref": "bs-1"} if budget is None else budget,
        store=store, emitter=emitter, manager_profile=manager_profile)


ALPHA_CAPS = {"alpha": ("text", "tools", "coding"),
              "beta": ("text", "tools", "coding"),
              "gamma": ("text", "tools", "coding")}


# ---------------------------------------------------------------- router fit

def test_fit_beats_alphabet():
    kb = FakeKb({
        ("t1", "aardvark-chat"): make_facts("t1", "aardvark-chat", fit=0.30, quality=0.90),
        ("t1", "zeta-coder"): make_facts("t1", "zeta-coder", fit=0.95, quality=0.95),
    })
    out = R._select_impl(
        req([cand("t1", "aardvark-chat"), cand("t1", "zeta-coder")]),
        deps(kb, {"t1": "ONLINE"},
             {("t1", "aardvark-chat"): "READY", ("t1", "zeta-coder"): "READY"},
             {"t1": ("text", "tools", "coding")}))
    assert out.status == "ROUTED"
    assert out.decision.selected_model == "zeta-coder"
    assert "coding" in out.decision.reason


def test_unknown_price_loses_tie():
    kb = FakeKb({
        ("t1", "m-cheap-known"): make_facts("t1", "m-cheap-known", fit=0.9,
                                            quality=0.9, price_in=0.01, price_out=0.03),
        ("t1", "m-cheap-unknown"): make_facts("t1", "m-cheap-unknown", fit=0.9,
                                              quality=0.9, price_in=None, price_out=None),
    })
    out = R._select_impl(
        req([cand("t1", "m-cheap-unknown"), cand("t1", "m-cheap-known")]),
        deps(kb, {"t1": "ONLINE"},
             {("t1", "m-cheap-known"): "READY", ("t1", "m-cheap-unknown"): "READY"},
             {"t1": ("text", "tools", "coding")}))
    assert out.status == "ROUTED"
    assert out.decision.selected_model == "m-cheap-known"
    assert "unknown price" in out.decision.reason


def test_modality_gate_holds():
    kb = FakeKb({
        ("t1", "text-only"): make_facts("t1", "text-only", fit=0.99, quality=0.99,
                                        modalities=("text",)),
        ("t1", "vision-pro"): make_facts("t1", "vision-pro", fit=0.80, quality=0.85,
                                         price_in=0.05, price_out=0.10,
                                         modalities=("text", "vision")),
    })
    out = R._select_impl(
        req([cand("t1", "text-only"), cand("t1", "vision-pro")],
            required_capabilities=("text", "vision"),
            required_modalities=("text", "vision")),
        deps(kb, {"t1": "ONLINE"},
             {("t1", "text-only"): "READY", ("t1", "vision-pro"): "READY"},
             {"t1": ("text", "vision")}))
    assert out.status == "ROUTED"
    assert out.decision.selected_model == "vision-pro"


# ---------------------------------------------------------------- identity

def test_similar_ids_are_distinct_entities():
    kb = FakeKb({
        ("beta", "beta/coder-2"): make_facts("beta", "beta/coder-2", fit=0.9, quality=0.9),
        ("beta", "beta/coder-2-plus"): make_facts("beta", "beta/coder-2-plus",
                                                 fit=0.9, quality=0.91),
    })
    r = req([cand("beta", "beta/coder-2"), cand("beta", "beta/coder-2-plus")])
    d = deps(kb, {"beta": "ONLINE"},
             {("beta", "beta/coder-2"): "READY",
              ("beta", "beta/coder-2-plus"): "READY"},
             {"beta": ("text", "tools", "coding")})
    out = R._select_impl(r, d)
    assert out.status == "ROUTED"
    # same name on one provider, two distinct entities; winner keeps exact id
    assert out.decision.selected_model in ("beta/coder-2", "beta/coder-2-plus")
    names = [c["model"] for c in out.snapshot.candidate_snapshot]
    assert "beta/coder-2" in names and "beta/coder-2-plus" in names


def test_same_name_two_providers_are_distinct():
    kb = FakeKb({
        ("pa", "shared/x-1"): make_facts("pa", "shared/x-1", fit=0.9, quality=0.9),
        ("pb", "shared/x-1"): make_facts("pb", "shared/x-1", fit=0.9, quality=0.9,
                                         price_in=0.02, price_out=0.06),
    })
    out = R._select_impl(
        req([cand("pa", "shared/x-1"), cand("pb", "shared/x-1")]),
        deps(kb, {"pa": "ONLINE", "pb": "ONLINE"},
             {("pa", "shared/x-1"): "READY", ("pb", "shared/x-1"): "READY"},
             {"pa": ("text", "tools", "coding"),
              "pb": ("text", "tools", "coding")}))
    assert out.status == "ROUTED"
    assert (out.decision.selected_provider, out.decision.selected_model) == ("pa", "shared/x-1")


def test_effective_capability_is_provider_intersect_model():
    kb = FakeKb({
        ("pa", "shared/x-1"): make_facts("pa", "shared/x-1", fit=0.9, quality=0.9,
                                         modalities=("text", "tools", "coding")),
        ("pb", "shared/x-1"): make_facts("pb", "shared/x-1", fit=0.9, quality=0.9,
                                         modalities=("text", "tools", "coding")),
    })
    out = R._select_impl(
        req([cand("pa", "shared/x-1"), cand("pb", "shared/x-1")]),
        deps(kb, {"pa": "ONLINE", "pb": "ONLINE"},
             {("pa", "shared/x-1"): "READY", ("pb", "shared/x-1"): "READY"},
             {"pa": ("text",),  # provider lacks tools -> effective lacks tools
              "pb": ("text", "tools", "coding")}))
    assert out.status == "ROUTED"
    assert out.decision.selected_provider == "pb"


# ---------------------------------------------------------------- AUTO reason

def test_auto_reason_names_basis_and_rejected():
    kb = FakeKb({
        ("t1", "cheap-fit"): make_facts("t1", "cheap-fit", fit=0.92, quality=0.95,
                                        price_in=0.004, price_out=0.012),
        ("t1", "pricey-fit"): make_facts("t1", "pricey-fit", fit=0.92, quality=0.96,
                                         price_in=0.05, price_out=0.15),
        ("t1", "weak-fit"): make_facts("t1", "weak-fit", fit=0.92, quality=0.50,
                                       price_in=0.001, price_out=0.002),
    })
    out = R._select_impl(
        req([cand("t1", "cheap-fit"), cand("t1", "pricey-fit"), cand("t1", "weak-fit")]),
        deps(kb, {"t1": "ONLINE"},
             {("t1", "cheap-fit"): "READY", ("t1", "pricey-fit"): "READY",
              ("t1", "weak-fit"): "READY"},
             {"t1": ("text", "tools", "coding")}))
    assert out.status == "ROUTED"
    assert out.decision.selected_model == "cheap-fit"
    reason = out.decision.reason
    assert "coding" in reason and "fit" in reason
    assert "price" in reason and "quality" in reason
    assert "weak-fit" in reason  # rejected candidate named
    assert "pricey-fit" in reason


def test_removal_reroutes_naming_removed():
    facts = {
        ("t1", "first-pick"): make_facts("t1", "first-pick", fit=0.92, quality=0.95,
                                         price_in=0.004, price_out=0.012),
        ("t1", "second-pick"): make_facts("t1", "second-pick", fit=0.92, quality=0.94,
                                          price_in=0.006, price_out=0.018),
    }
    kb = FakeKb(facts)
    d = deps(kb, {"t1": "ONLINE"},
             {("t1", "first-pick"): "READY", ("t1", "second-pick"): "READY"},
             {"t1": ("text", "tools", "coding")})
    first = R._select_impl(req([cand("t1", "first-pick"), cand("t1", "second-pick")]), d)
    assert first.decision.selected_model == "first-pick"
    second = R._select_impl(req([cand("t1", "first-pick"), cand("t1", "second-pick")],
                          excluded_models=("first-pick",)), d)
    assert second.status == "ROUTED"
    assert second.decision.selected_model == "second-pick"
    assert "first-pick" in second.decision.reason


def test_director_per_block_manager_per_task_recorded():
    kb = FakeKb({("t1", "m1"): make_facts("t1", "m1")})
    d = deps(kb, {"t1": "ONLINE"}, {("t1", "m1"): "READY"},
             {"t1": ("text", "tools", "coding")})
    out_d = R._select_impl(req([cand("t1", "m1")], role="director"), d)
    out_m = R._select_impl(req([cand("t1", "m1")], role="manager"), d)
    assert out_d.assignments[0].stage == "block"
    assert out_m.assignments[0].stage == "task"
    assert out_d.assignments[0].role == "director"
    assert out_m.assignments[0].role == "manager"


# ---------------------------------------------------------------- fresh install

def test_fresh_install_blocks_with_reason():
    table = RL.RoleTable()
    for role in ("director", "manager", "worker", "auditor", "watcher"):
        res = table.resolve("proj-new", role)
        assert res.status == "BLOCKED"
        assert res.reason != ""
        assert "NO_PROFILE_BLOCKED" in res.reason
        assert "pick PINNED or AUTO" in res.reason


def test_dev_id_in_no_default():
    table = RL.RoleTable()
    assert table.list_profiles("proj-new") == []
    for module in ("types", "router", "roles", "fallback", "pools",
                   "kb_port", "telemetry_port", "store"):
        import importlib
        mod = importlib.import_module("agent_si.routing." + module)
        src = open(mod.__file__, encoding="utf-8").read()
        assert DEV_MODEL_ID not in src, module


# ---------------------------------------------------------------- single provider

def test_single_provider_all_roles_one_model():
    table = RL.RoleTable()
    RL.apply_single_provider(table, "p1", "solo", "solo/only-1")
    kb = FakeKb({("solo", "solo/only-1"): make_facts("solo", "solo/only-1")})
    d = deps(kb, {"solo": "ONLINE"}, {("solo", "solo/only-1"): "READY"},
             {"solo": ("text", "tools", "coding")})
    for role in ("director", "manager", "worker", "auditor", "watcher"):
        res = table.resolve(
            "p1", role,
            provider_health={"solo": up("solo", "ONLINE")},
            model_health={("solo", "solo/only-1"): mh("solo", "solo/only-1", "READY")})
        assert res.status == "READY", (role, res.reason)
        assert (res.provider, res.model) == ("solo", "solo/only-1")
        out = R._select_impl(req([cand("solo", "solo/only-1")], role=role), d)
        assert out.decision.selected_model == "solo/only-1"


# ---------------------------------------------------------------- pinned via fallback only

def test_pinned_replaced_only_via_fallback():
    table = RL.RoleTable()
    table.set_profile(T.RoleModelProfile(
        role="worker", project_id="p1", mode="PINNED",
        provider="pa", model="pa/pinned-1", binding="DEFAULT",
        version=1, hash="h"))
    events = []
    emitter = TP.TelemetryEmitter()
    emitter.add_sink(events.append)
    # unhealthy pin: resolve keeps the pin, never silently swaps
    res = table.resolve("p1", "worker",
                        provider_health={"pa": up("pa", "OFFLINE")},
                        model_health={("pa", "pa/pinned-1"): mh("pa", "pa/pinned-1", "ERROR")})
    assert res.status == "PINNED_UNHEALTHY"
    assert (res.provider, res.model) == ("pa", "pa/pinned-1")
    # the ONLY swap path: replace_pinned with a canonical reason
    rec, new_pin = F.replace_pinned(
        old_provider="pa", old_model="pa/pinned-1",
        new_provider="pb", new_model="pb/spare-1",
        project_id="p1", task_id="t1", source_run_id="r1",
        reason="health_failure", policy_ref="fp-1", evidence_ref="ev-1",
        store=None, emitter=emitter)
    assert rec.reason == "health_failure"
    assert (rec.from_provider, rec.from_model) == ("pa", "pa/pinned-1")
    assert (rec.to_provider, rec.to_model) == ("pb", "pb/spare-1")
    assert (new_pin["provider"], new_pin["model"]) == ("pb", "pb/spare-1")
    assert any(e.get("fallback_reason") == "health_failure" for e in events)


def test_fallback_reason_set_enforced():
    F.bind_fallback_ctx({"project_id": "p1", "task_id": "t1",
                         "source_run_id": "r1", "replacement_run_id": "r1",
                         "source_attempt_id": None})
    try:
        with pytest.raises(ValueError):
            F.build_fallback_record(
                "mysterious_vibes", "a", "a/m", "b", "b/m", "fp", "ev")
        for reason in T.FALLBACK_REASONS:
            rec = F.build_fallback_record(
                reason, "a", "a/m", "b", "b/m", "fp", "ev")
            assert rec.reason == reason
    finally:
        F.unbind_fallback_ctx()


# ---------------------------------------------------------------- Manager profile

def test_manager_never_reselected_per_run():
    profile = RL.make_default_manager_profile(provider="meta", model="meta/mgr-9")
    kb = FakeKb({
        ("meta", "meta/mgr-9"): make_facts("meta", "meta/mgr-9", fit=0.9, quality=0.9),
        ("alt", "alt/shiny"): make_facts("alt", "alt/shiny", fit=0.99, quality=0.99,
                                         price_in=0.001, price_out=0.002),
    })
    d = deps(kb, {"meta": "ONLINE", "alt": "ONLINE"},
             {("meta", "meta/mgr-9"): "READY", ("alt", "alt/shiny"): "READY"},
             {"meta": ("text", "tools", "coding"),
              "alt": ("text", "tools", "coding")},
             manager_profile=profile)
    out = R._select_impl(req([cand("meta", "meta/mgr-9"), cand("alt", "alt/shiny")],
                       role="manager"), d)
    assert out.decision.selected_model == "meta/mgr-9"
    with pytest.raises(ValueError):
        RL.resolve_manager(profile, to_provider="alt", to_model="alt/shiny",
                           trigger="vibes", trigger_ref="x")
    rec, profile2 = RL.resolve_manager(
        profile, to_provider="alt", to_model="alt/shiny",
        trigger="fallback", trigger_ref="fb-1",
        project_id="p1", task_id="t1", run_id="r1")
    assert profile2.model == "alt/shiny" and profile2.version == 2
    assert rec.reason in T.FALLBACK_REASONS


# ---------------------------------------------------------------- bootstrap + NO-DATA

def local_req(candidates, **kw):
    d = dict(project_id="p1", task_id="t1", run_id="r1", role="worker",
             task_class="coding",
             required_capabilities=("text",),
             required_modalities=("text",),
             task_risk="LOW", routing_policy=pol(), optimization_policy=opt(),
             candidates=tuple(candidates), mode="AUTO")
    d.update(kw)
    return R.RoutingRequest(**d)


def test_no_data_never_local():
    kb = FakeKb({  # local model has NO facts at all
        ("cloud", "cloud/big"): make_facts("cloud", "cloud/big", fit=0.85, quality=0.9),
    })
    out = R._select_impl(
        local_req([cand("lo", "lo/tiny", provider_type="local"),
                   cand("cloud", "cloud/big")]),
        deps(kb, {"lo": "ONLINE", "cloud": "ONLINE"},
             {("lo", "lo/tiny"): "READY", ("cloud", "cloud/big"): "READY"},
             {"lo": ("text",), "cloud": ("text", "tools", "coding")}))
    assert out.status == "ROUTED"
    assert out.decision.route == "CLOUD"
    assert out.decision.selected_provider == "cloud"


def test_bootstrap_full_measured_safe_class_local():
    kb = FakeKb({("lo", "lo/tiny"): make_facts("lo", "lo/tiny", fit=0.9, quality=1.0,
                                               price_in=0.0, price_out=0.0)})
    out = R._select_impl(
        local_req([cand("lo", "lo/tiny", provider_type="local")]),
        deps(kb, {"lo": "ONLINE"}, {("lo", "lo/tiny"): "READY"},
             {"lo": ("text",)}))
    assert out.decision.route == "LOCAL"


def test_bootstrap_tolerant_parser_local():
    kb = FakeKb({("lo", "lo/tiny"): make_facts("lo", "lo/tiny", fit=0.9, quality=0.9,
                                               price_in=0.0, price_out=0.0)})
    out = R._select_impl(
        local_req([cand("lo", "lo/tiny", provider_type="local")], tolerant_parser=True),
        deps(kb, {"lo": "ONLINE"}, {("lo", "lo/tiny"): "READY"},
             {"lo": ("text",)}))
    assert out.decision.route == "LOCAL"


def test_bootstrap_mid_range_split_atomic():
    kb = FakeKb({
        ("lo", "lo/tiny"): make_facts("lo", "lo/tiny", fit=0.8, quality=0.60,
                                      price_in=0.0, price_out=0.0),
        ("cloud", "cloud/big"): make_facts("cloud", "cloud/big", fit=0.85, quality=0.95),
    })
    out = R._select_impl(
        local_req([cand("lo", "lo/tiny", provider_type="local"),
                   cand("cloud", "cloud/big")],
                  preferred_route="SPLIT",
                  preferred_strategy="LOCAL_DRAFT_CLOUD_FINAL"),
        deps(kb, {"lo": "ONLINE", "cloud": "ONLINE"},
             {("lo", "lo/tiny"): "READY", ("cloud", "cloud/big"): "READY"},
             {"lo": ("text",), "cloud": ("text", "tools", "coding")}))
    assert out.status == "ROUTED"
    assert out.decision.route == "SPLIT"
    stages = sorted(a.stage for a in out.assignments)
    assert stages == ["cloud_verify", "local_draft"]
    by_stage = {a.stage: a for a in out.assignments}
    assert by_stage["local_draft"].provider == "lo"
    assert by_stage["cloud_verify"].provider == "cloud"


def test_bootstrap_low_goes_cloud():
    kb = FakeKb({
        ("lo", "lo/tiny"): make_facts("lo", "lo/tiny", fit=0.5, quality=0.30,
                                      price_in=0.0, price_out=0.0),
        ("cloud", "cloud/big"): make_facts("cloud", "cloud/big", fit=0.85, quality=0.95),
    })
    out = R._select_impl(
        local_req([cand("lo", "lo/tiny", provider_type="local"),
                   cand("cloud", "cloud/big")]),
        deps(kb, {"lo": "ONLINE", "cloud": "ONLINE"},
             {("lo", "lo/tiny"): "READY", ("cloud", "cloud/big"): "READY"},
             {"lo": ("text",), "cloud": ("text", "tools", "coding")}))
    assert out.decision.route == "CLOUD"
    assert out.decision.selected_provider == "cloud"


# ---------------------------------------------------------------- quality/risk before cost

def test_quality_and_risk_before_cost():
    kb = FakeKb({
        ("t1", "cheap-weak"): make_facts("t1", "cheap-weak", fit=0.9, quality=0.50,
                                         price_in=0.001, price_out=0.002),
        ("t1", "cheap-risky"): make_facts("t1", "cheap-risky", fit=0.9, quality=0.95,
                                          price_in=0.001, price_out=0.002,
                                          risk="CRITICAL"),
        ("t1", "dear-sound"): make_facts("t1", "dear-sound", fit=0.9, quality=0.95,
                                         price_in=0.05, price_out=0.15, risk="LOW"),
    })
    out = R._select_impl(
        req([cand("t1", "cheap-weak"), cand("t1", "cheap-risky"), cand("t1", "dear-sound")]),
        deps(kb, {"t1": "ONLINE"},
             {("t1", "cheap-weak"): "READY", ("t1", "cheap-risky"): "READY",
              ("t1", "dear-sound"): "READY"},
             {"t1": ("text", "tools", "coding")}))
    assert out.status == "ROUTED"
    assert out.decision.selected_model == "dear-sound"


# ---------------------------------------------------------------- UNKNOWN / MEASURED

def test_unknown_capability_never_capable():
    kb = FakeKb({
        ("t1", "ghost"): make_facts("t1", "ghost", state="UNKNOWN", quality=None,
                                    price_in=0.001, price_out=0.002),
        ("t1", "solid"): make_facts("t1", "solid", fit=0.85, quality=0.9),
    })
    out = R._select_impl(
        req([cand("t1", "ghost"), cand("t1", "solid")]),
        deps(kb, {"t1": "ONLINE"},
             {("t1", "ghost"): "READY", ("t1", "solid"): "READY"},
             {"t1": ("text", "tools", "coding")}))
    assert out.decision.selected_model == "solid"


def test_measured_not_routing_eligible_without_gates():
    kb = FakeKb({
        ("t1", "measured-down"): make_facts("t1", "measured-down", fit=0.95, quality=0.99),
        ("t1", "solid"): make_facts("t1", "solid", fit=0.85, quality=0.9),
    })
    out = R._select_impl(
        req([cand("t1", "measured-down"), cand("t1", "solid")]),
        deps(kb, {"t1": "ONLINE"},
             {("t1", "measured-down"): "ERROR", ("t1", "solid"): "READY"},
             {"t1": ("text", "tools", "coding")}))
    assert out.decision.selected_model == "solid"


# ---------------------------------------------------------------- verbatim ids + mock

def test_ids_verbatim_no_reword():
    kb = FakeKb({
        ("MiXeD", "MiXeD/CaSe-Model_X"): make_facts("MiXeD", "MiXeD/CaSe-Model_X",
                                                   fit=0.9, quality=0.9),
    })
    out = R._select_impl(
        req([cand("MiXeD", "MiXeD/CaSe-Model_X")]),
        deps(kb, {"MiXeD": "ONLINE"},
             {("MiXeD", "MiXeD/CaSe-Model_X"): "READY"},
             {"MiXeD": ("text", "tools", "coding")}))
    assert out.decision.selected_provider == "MiXeD"
    assert out.decision.selected_model == "MiXeD/CaSe-Model_X"
    assert out.assignments[0].model == "MiXeD/CaSe-Model_X"


def test_mock_provider_marks_mock_true():
    kb = FakeKb({
        ("mk", "mk/fake-1"): make_facts("mk", "mk/fake-1", fit=0.9, quality=0.9),
    })
    out = R._select_impl(
        req([cand("mk", "mk/fake-1", is_mock=True)]),
        deps(kb, {"mk": "ONLINE"}, {("mk", "mk/fake-1"): "READY"},
             {"mk": ("text", "tools", "coding")}))
    assert out.status == "ROUTED"
    assert "mock: true" in out.decision.reason
    snaps = out.snapshot.candidate_snapshot
    assert any(c.get("mock") is True for c in snaps)


# ---------------------------------------------------------------- per-run override + turn cap

def test_per_run_override_only_through_routing_params():
    kb = FakeKb({
        ("pa", "pa/std"): make_facts("pa", "pa/std", fit=0.9, quality=0.9),
        ("pb", "pb/other"): make_facts("pb", "pb/other", fit=0.9, quality=0.9,
                                       price_in=0.02, price_out=0.06),
    })
    d = deps(kb, {"pa": "ONLINE", "pb": "ONLINE"},
             {("pa", "pa/std"): "READY", ("pb", "pb/other"): "READY"},
             {"pa": ("text", "tools", "coding"),
              "pb": ("text", "tools", "coding")})
    plain = R._select_impl(req([cand("pa", "pa/std"), cand("pb", "pb/other")]), d)
    assert plain.decision.selected_model == "pa/std"
    over = R._select_impl(req([cand("pa", "pa/std"), cand("pb", "pb/other")],
                        override_provider="pb", override_model="pb/other"), d)
    assert over.decision.selected_model == "pb/other"
    assert over.decision.eligibility_source == "EXPLICIT_MODEL_PIN"
    assert over.decision.capability_state == "UNVERIFIED"
    assert over.decision.required_verification == "ENHANCED"


def test_turn_cap_recorded():
    kb = FakeKb({("t1", "m1"): make_facts("t1", "m1")})
    out = R._select_impl(
        req([cand("t1", "m1")], turn_cap=40),
        deps(kb, {"t1": "ONLINE"}, {("t1", "m1"): "READY"},
             {"t1": ("text", "tools", "coding")}))
    assert "turn_cap=40" in out.decision.reason


def test_all_blocked_reports_reason():
    kb = FakeKb({("t1", "m1"): make_facts("t1", "m1")})
    out = R._select_impl(
        req([cand("t1", "m1")]),
        deps(kb, {"t1": "OFFLINE"}, {("t1", "m1"): "READY"},
             {"t1": ("text", "tools", "coding")}))
    assert out.status == "BLOCKED"
    assert out.decision.selected_model is None
    assert out.decision.reason != ""


# ---------------------------------------------------------------- A2FIX-A owned tests


@_dataclass(frozen=True)
class FakeCandidateView:
    # FAKE-OF: interface.CandidateView (duck-typed view for facade tests)
    provider_id: str
    model: str
    provider_instance: object = None
    effective_capability_ref: str = ""
    price_basis: str = "KNOWN"
    quality_basis: str = "MEASURED"
    modality_ok: bool = True
    rejected: bool = False
    reject_reason: object = None


def test_d1_frozen_strategy_values_pinned():
    assert list(T.POOL_STRATEGIES) == ["DIRECTOR_PER_TASK", "AUTO",
                                       "FALLBACK_ORDER", "SPLIT_PARALLEL"]
    assert set(T.STRATEGY_LABELS) == set(T.POOL_STRATEGIES)
    assert T.STRATEGY_LABELS["DIRECTOR_PER_TASK"] == "Director decides per task"
    assert T.STRATEGY_LABELS["AUTO"] == "Auto"
    assert T.STRATEGY_LABELS["FALLBACK_ORDER"] == "Fallback order"
    assert T.STRATEGY_LABELS["SPLIT_PARALLEL"] == "Split/parallel"
    assert P.default_strategy_for(2) == "DIRECTOR_PER_TASK"
    assert P.default_strategy_for(5) == "DIRECTOR_PER_TASK"
    assert P.default_strategy_for(1) == "AUTO"
    assert P.default_strategy_for(0) == "AUTO"
    two = P.make_binding("worker", "p1", [P.PoolMember("t1", "t1/m1"),
                                          P.PoolMember("t2", "t2/m2")])
    assert two.strategy == "DIRECTOR_PER_TASK"
    one = P.make_binding("worker", "p1", [P.PoolMember("t1", "t1/m1")])
    assert one.strategy == "AUTO"
    with pytest.raises(ValueError):
        P.make_binding("worker", "p1", [P.PoolMember("t1", "t1/m1")],
                       strategy="auto")


def test_d1_legacy_persisted_binding_migrates_on_read(tmp_path):
    store = RoutingStore(str(tmp_path))
    assert store.get_pool("p1", "worker") is None
    legacy = {"role": "worker", "project_id": "p1", "strategy": "auto",
              "version": 1,
              "members": [{"provider": "t1", "model": "t1/m1",
                           "use_mode": "primary", "provider_type": "cloud"}]}
    with pytest.raises(ValueError):
        store.save_pool(legacy)
    with pytest.raises(ValueError):
        store.save_pool(dict(legacy, strategy="director_decides"))
    store._save_table("profiles", {"roles": {}, "manager": None,
                                   "pools": {"p1\x00worker": legacy}})
    row = store.get_pool("p1", "worker")
    assert row["strategy"] == "AUTO"
    view = P.binding_view(row)
    assert view["strategy"] == "AUTO"
    assert view["strategy_label"] == "Auto"
    frozen = P.make_binding("worker", "p1",
                            [P.PoolMember("t1", "t1/m1")])
    assert frozen.strategy == "AUTO"
    store.save_pool(frozen)
    assert store.get_pool("p1", "worker")["strategy"] == "AUTO"


def test_d4_resolve_role_model_no_profile_blocked():
    with pytest.raises(ValueError) as exc:
        RL.resolve_role_model("worker", "proj-fresh")
    assert "NO_PROFILE_BLOCKED" in str(exc.value)
    assert "worker" in str(exc.value)


def test_d4_resolve_role_model_pinned_returns_modelref(tmp_path):
    table = RL.RoleTable()
    table.set_profile(T.RoleModelProfile(
        role="worker", project_id="p1", mode="PINNED",
        provider="pa", model="pa/m1", binding="DEFAULT",
        version=1, hash="h"))
    RL.bind_role_table(table)
    try:
        ref = RL.resolve_role_model("worker", "p1")
    finally:
        RL.unbind_role_table()
    assert isinstance(ref, RL.ModelRef)
    assert (ref.provider, ref.model) == ("pa", "pa/m1")
    store = RoutingStore(str(tmp_path))
    store.save_role_profile(T.RoleModelProfile(
        role="auditor", project_id="p9", mode="PINNED",
        provider="pb", model="pb/audit-2", binding="DEFAULT",
        version=1, hash="h"))
    RL.bind_role_table(RL.RoleTable(store=store))
    try:
        ref2 = RL.resolve_role_model("auditor", "p9")
    finally:
        RL.unbind_role_table()
    assert (ref2.provider, ref2.model) == ("pb", "pb/audit-2")


def test_d4_resolve_role_model_non_pinned_names_mode():
    table = RL.RoleTable()
    table.set_profile(T.RoleModelProfile(
        role="worker", project_id="p1", mode="AUTO",
        binding="DEFAULT", version=1, hash="h"))
    RL.bind_role_table(table)
    try:
        with pytest.raises(ValueError) as exc_auto:
            RL.resolve_role_model("worker", "p1")
    finally:
        RL.unbind_role_table()
    assert "NO_PROFILE_BLOCKED" in str(exc_auto.value)
    assert "AUTO" in str(exc_auto.value)
    table.set_profile(T.RoleModelProfile(
        role="manager", project_id="p1", mode="pool",
        binding="DEFAULT", version=1, hash="h"))
    RL.bind_role_table(table)
    try:
        with pytest.raises(ValueError) as exc_pool:
            RL.resolve_role_model("manager", "p1")
    finally:
        RL.unbind_role_table()
    assert "NO_PROFILE_BLOCKED" in str(exc_pool.value)
    assert "pool" in str(exc_pool.value)


def test_d5_record_fallback_facade_ids_from_ctx():
    F.bind_fallback_ctx({"project_id": "p1", "task_id": "t1",
                         "source_run_id": "r1", "replacement_run_id": "r2",
                         "source_attempt_id": "a1",
                         "fallback_id": "fb-fixed"})
    try:
        rec = F.build_fallback_record(
            "health_failure", "pa", "pa/m", "pb", "pb/m", "fp-1", "ev-1")
    finally:
        F.unbind_fallback_ctx()
    assert isinstance(rec, T.FallbackRecord)
    assert rec.fallback_id == "fb-fixed"
    assert rec.project_id == "p1" and rec.task_id == "t1"
    assert rec.source_run_id == "r1"
    assert rec.replacement_run_id == "r2"
    assert rec.source_attempt_id == "a1"
    assert (rec.from_provider, rec.from_model) == ("pa", "pa/m")
    assert (rec.to_provider, rec.to_model) == ("pb", "pb/m")
    assert rec.policy_ref == "fp-1" and rec.evidence_ref == "ev-1"
    F.bind_fallback_ctx({"project_id": "p1", "task_id": "t1",
                         "source_run_id": "r1"})
    try:
        minted = F.build_fallback_record(
            "timeout", "pa", "pa/m", "pb", "pb/m", "fp-1", "ev-1")
    finally:
        F.unbind_fallback_ctx()
    assert minted.fallback_id.startswith("fb-")
    assert minted.replacement_run_id is None
    assert minted.source_attempt_id is None


def test_d5_record_fallback_missing_id_and_bad_reason():
    F.bind_fallback_ctx({"project_id": "p1", "task_id": "t1"})
    try:
        with pytest.raises(ValueError) as exc:
            F.build_fallback_record(
                "health_failure", "pa", "pa/m", "pb", "pb/m", "fp-1", "ev-1")
    finally:
        F.unbind_fallback_ctx()
    assert "source_run_id" in str(exc.value)
    with pytest.raises(ValueError):
        F.build_fallback_record(
            "health_failure", "pa", "pa/m", "pb", "pb/m", "fp-1", "ev-1")
    F.bind_fallback_ctx({"project_id": "p1", "task_id": "t1",
                         "source_run_id": "r1"})
    try:
        with pytest.raises(ValueError):
            F.build_fallback_record(
                "mysterious_vibes", "pa", "pa/m", "pb", "pb/m",
                "fp-1", "ev-1")
    finally:
        F.unbind_fallback_ctx()


def _task(**over):
    base = {"project_id": "p1", "task_id": "t1", "run_id": "r1",
            "role": "worker", "task_class": "coding",
            "required_capabilities": ("text", "tools"),
            "required_modalities": ("text",)}
    base.update(over)
    return base


def _facade_setup(**over):
    kb = FakeKb({("t1", "t1/m1"): make_facts("t1", "t1/m1"),
                 ("t1", "t1/m2"): make_facts("t1", "t1/m2", fit=0.7,
                                             quality=0.85,
                                             price_in=0.05,
                                             price_out=0.15)})
    ctx = dict(
        task_contracts={"task:t1": _task()},
        routing_policies={"pol:rp": pol()},
        optimization_policies={"pol:op": opt()},
        kb=kb,
        provider_health={"t1": up("t1", "ONLINE")},
        model_health={("t1", "t1/m1"): mh("t1", "t1/m1", "READY"),
                      ("t1", "t1/m2"): mh("t1", "t1/m2", "READY")},
        provider_capabilities={"t1": ("text", "tools", "coding")},
        resource_state={"eligible": True, "ref": "rs-1"},
        budget_state={"eligible": True, "ref": "bs-1"})
    ctx.update(over)
    return ctx


def test_d3_select_facade_routed_end_to_end():
    ctx = _facade_setup()
    R.bind_select_scope(ctx)
    try:
        out = R.select("task:t1",
                       [FakeCandidateView("t1", "t1/m1"),
                        FakeCandidateView("t1", "t1/m2")],
                       "pol:rp", "pol:op", "bs:1", "rs:1")
    finally:
        R.unbind_select_scope()
    assert out.status == "ROUTED"
    assert out.decision.selected_model == "t1/m1"
    assert out.decision.routing_policy_ref == "rp-1:v1"
    assert out.assignments[0].resource_state_ref == "rs-1"


def test_d3_select_facade_accepts_mapping_views():
    ctx = _facade_setup()
    R.bind_select_scope(ctx)
    try:
        out = R.select("task:t1",
                       [{"provider_id": "t1", "model": "t1/m1"}],
                       "pol:rp", "pol:op", "bs:1", "rs:1")
    finally:
        R.unbind_select_scope()
    assert out.status == "ROUTED"
    assert out.decision.selected_model == "t1/m1"


def test_d3_select_facade_persists_and_emits(tmp_path):
    ctx = _facade_setup()
    store = RoutingStore(str(tmp_path))
    events = []
    emitter = TP.TelemetryEmitter()
    emitter.add_sink(events.append)
    ctx.update(store=store, emitter=emitter)
    R.bind_select_scope(ctx)
    try:
        out = R.select("task:t1",
                       [FakeCandidateView("t1", "t1/m1"),
                        FakeCandidateView("t1", "t1/m2")],
                       "pol:rp", "pol:op", "bs:1", "rs:1")
    finally:
        R.unbind_select_scope()
    assert out.status == "ROUTED"
    assert store.get_decision(
        out.decision.decision_id)["selected_model"] == "t1/m1"
    assert events
    assert events[0].get("routing_decision_ref") == out.decision.decision_id
    assert events[0].get("reason") == out.decision.reason


def test_d3_select_facade_blocked_on_unknown_ref():
    ctx = _facade_setup()
    R.bind_select_scope(ctx)
    try:
        with pytest.raises(ValueError, match="pol:missing"):
            R.select("task:t1", [FakeCandidateView("t1", "t1/m1")],
                     "pol:missing", "pol:op", "bs:1", "rs:1")
        with pytest.raises(ValueError, match="task:missing"):
            R.select("task:missing", [FakeCandidateView("t1", "t1/m1")],
                     "pol:rp", "pol:op", "bs:1", "rs:1")
    finally:
        R.unbind_select_scope()
    R.bind_select_scope(_facade_setup(budget_state=None))
    try:
        with pytest.raises(ValueError, match="budget_state_ref"):
            R.select("task:t1", [FakeCandidateView("t1", "t1/m1")],
                     "pol:rp", "pol:op", "bs:1", "rs:1")
    finally:
        R.unbind_select_scope()


def test_d3_select_facade_rejected_views_excluded():
    ctx = _facade_setup()
    R.bind_select_scope(ctx)
    try:
        with pytest.raises(ValueError) as exc:
            R.select("task:t1",
                     [FakeCandidateView("t1", "t1/m1", rejected=True,
                                        reject_reason="auditor must differ")],
                     "pol:rp", "pol:op", "bs:1", "rs:1")
    finally:
        R.unbind_select_scope()
    assert "t1/m1" in str(exc.value)
    assert "NO_ELIGIBLE_CANDIDATE" in str(exc.value)


def test_d3_select_facade_raises_literal_code_on_block():
    ctx = _facade_setup()
    ctx["task_contracts"] = {
        "task:t1": _task(required_modalities=("text", "vision"))}
    R.bind_select_scope(ctx)
    try:
        with pytest.raises(ValueError, match="MODALITY_MISMATCH"):
            R.select("task:t1", [FakeCandidateView("t1", "t1/m1")],
                     "pol:rp", "pol:op", "bs:1", "rs:1")
    finally:
        R.unbind_select_scope()


def test_block_codes_modality_vs_eligibility():
    kb = FakeKb({("t1", "text-only"): make_facts("t1", "text-only",
                                                modalities=("text",))})
    out = R._select_impl(
        req([cand("t1", "text-only")],
            required_capabilities=("text",),
            required_modalities=("text", "vision")),
        deps(kb, {"t1": "ONLINE"}, {("t1", "text-only"): "READY"},
             {"t1": ("text",)}))
    assert out.status == "BLOCKED"
    assert "MODALITY_MISMATCH" in out.decision.reason
    out2 = R._select_impl(
        req([cand("t1", "text-only")],
            required_capabilities=("text", "tools"),
            required_modalities=("text",)),
        deps(kb, {"t1": "ONLINE"}, {("t1", "text-only"): "READY"},
             {"t1": ("text",)}))
    assert out2.status == "BLOCKED"
    assert "NO_ELIGIBLE_CANDIDATE" in out2.decision.reason
    assert "MODALITY_MISMATCH" not in out2.decision.reason


def test_d3_select_facade_modality_false_winner_flagged_routed():
    # Entry level: a modality_ok=False view still ROUTES (internal gate
    # unchanged) but the ROUTED reason carries the MODALITY_MISMATCH
    # treatment flag for the winner's own source view.
    ctx = _facade_setup()
    R.bind_select_scope(ctx)
    try:
        out = R.select("task:t1",
                       [{"provider_id": "t1", "model": "t1/m1",
                         "modality_ok": False}],
                       "pol:rp", "pol:op", "bs:1", "rs:1")
    finally:
        R.unbind_select_scope()
    assert out.status == "ROUTED"
    assert out.decision.selected_model == "t1/m1"
    assert "MODALITY_MISMATCH" in out.decision.reason


def test_d3_select_facade_modality_true_winner_unflagged():
    # Control: a modality_ok=True winner carries no flag; the internal
    # gate path is untouched (all _select_impl tests stay green).
    ctx = _facade_setup()
    R.bind_select_scope(ctx)
    try:
        out = R.select("task:t1",
                       [{"provider_id": "t1", "model": "t1/m1",
                         "modality_ok": True}],
                       "pol:rp", "pol:op", "bs:1", "rs:1")
    finally:
        R.unbind_select_scope()
    assert out.status == "ROUTED"
    assert out.decision.selected_model == "t1/m1"
    assert "MODALITY_MISMATCH" not in out.decision.reason


def test_d6_why_replay_returns_record_triple(tmp_path):
    kb = FakeKb({("t1", "m1"): make_facts("t1", "m1")})
    out = R._select_impl(
        req([cand("t1", "m1")], turn_cap=40),
        deps(kb, {"t1": "ONLINE"}, {("t1", "m1"): "READY"},
             {"t1": ("text", "tools", "coding")}))
    store = RoutingStore(str(tmp_path))
    did = store.save_decision(out.decision, out.assignments, out.snapshot,
                              turn_cap=40)
    triple = store.why_replay(did)
    assert isinstance(triple, tuple) and len(triple) == 3
    decision, assignments, snapshot = triple
    assert isinstance(decision, T.RoutingDecision)
    assert isinstance(assignments, list)
    assert all(isinstance(a, T.RoutingAssignment) for a in assignments)
    assert isinstance(snapshot, T.RoutingEvidenceSnapshot)
    assert decision.decision_id == did
    assert decision.selected_model == "m1"
    assert decision.reason == out.decision.reason
    assert len(assignments) == len(out.assignments)
    assert (snapshot.routing_snapshot_id
            == out.decision.routing_snapshot_id)
    assert snapshot.hash == out.snapshot.hash
    assert store.why_replay("rd-no-such-decision") is None
    meta = store.get_meta(did)
    assert meta is not None and meta.get("turn_cap") == 40


def test_d13_pick_pool_strategy_no_binding_is_auto():
    assert P.pick_pool_strategy("worker", "p1") == "AUTO"


def test_d13_pick_pool_strategy_store_and_explicit_binding(tmp_path):
    store = RoutingStore(str(tmp_path))
    store.save_pool(P.make_binding(
        "worker", "p1", [P.PoolMember("t1", "t1/m1"),
                         P.PoolMember("t2", "t2/m2")]))
    P.bind_pool_store(store)
    try:
        assert (P.pick_pool_strategy("worker", "p1")
                == "DIRECTOR_PER_TASK")
        store.save_pool(P.make_binding(
            "auditor", "p1", [P.PoolMember("t1", "t1/m1")]))
        assert P.pick_pool_strategy("auditor", "p1") == "AUTO"
        explicit = P.make_binding(
            "manager", "p1", [P.PoolMember("t1", "t1/m1")],
            strategy="SPLIT_PARALLEL")
        store.save_pool(explicit)
        assert (P.pick_pool_strategy("manager", "p1")
                == "SPLIT_PARALLEL")
    finally:
        P.unbind_pool_store()
    # a store holding only auditor+worker rows: the worker row resolves,
    # a role with no stored row reports AUTO
    store_b = RoutingStore(str(tmp_path / "b"))
    store_b.save_pool(P.make_binding(
        "auditor", "p1", [P.PoolMember("t1", "t1/m1")], strategy="AUTO"))
    store_b.save_pool(P.make_binding(
        "worker", "p1", [P.PoolMember("t1", "t1/m1")],
        strategy="FALLBACK_ORDER"))
    P.bind_pool_store(store_b)
    try:
        assert P.pick_pool_strategy("worker", "p1") == "FALLBACK_ORDER"
        assert P.pick_pool_strategy("manager", "p1") == "AUTO"
    finally:
        P.unbind_pool_store()


def test_d13_pick_pool_strategy_legacy_string_migrates(tmp_path):
    # Legacy / unknown rows bypass the frozen-value write guard via a raw
    # row write (save_pool rejects them); the read path migrates or
    # defaults them, resolved through the bound store with exact params.
    store = RoutingStore(str(tmp_path))

    def _read_as(row):
        store._save_table("profiles", {"roles": {}, "manager": None,
                                       "pools": {"p1\x00worker": row}})
        P.bind_pool_store(store)
        try:
            return P.pick_pool_strategy("worker", "p1")
        finally:
            P.unbind_pool_store()

    legacy = {"role": "worker", "project_id": "p1",
              "strategy": "fallback_order", "version": 1,
              "members": [{"provider": "t1", "model": "t1/m1",
                           "use_mode": "primary",
                           "provider_type": "cloud"}]}
    assert _read_as(legacy) == "FALLBACK_ORDER"
    assert _read_as(dict(legacy, strategy="split_parallel")) == "SPLIT_PARALLEL"
    two_unknown = {"role": "worker", "project_id": "p1",
                   "strategy": None, "version": 1,
                   "members": [{"provider": "t1", "model": "t1/m1"},
                               {"provider": "t2", "model": "t2/m2"}]}
    assert _read_as(two_unknown) == "DIRECTOR_PER_TASK"
    one_unknown = dict(two_unknown, strategy="bogus",
                       members=[{"provider": "t1", "model": "t1/m1"}])
    assert _read_as(one_unknown) == "AUTO"


# ---------------------------------------------------------------- K04R1 STEP2-1: pool strategy behaviour through the real entry
# Entry points only (served decide handler, real router entry): no direct
# unit calls of internals below. One test per strategy plus no-binding.

def _pool_entry_kb():
    return FakeKb({
        ("pa", "pa/a-1"): make_facts("pa", "pa/a-1", fit=0.90, quality=0.92,
                                     price_in=0.010, price_out=0.030),
        ("pb", "pb/b-1"): make_facts("pb", "pb/b-1", fit=0.90, quality=0.91,
                                     price_in=0.005, price_out=0.015),
        ("pc", "pc/c-1"): make_facts("pc", "pc/c-1", fit=0.90, quality=0.93,
                                     price_in=0.020, price_out=0.060),
        ("lo", "lo/tiny"): make_facts("lo", "lo/tiny", fit=0.80, quality=0.60,
                                      price_in=0.0, price_out=0.0),
    })


_POOL_ENTRY_CAPS = {"pa": ("text", "tools", "coding"),
                    "pb": ("text", "tools", "coding"),
                    "pc": ("text", "tools", "coding"),
                    "lo": ("text", "tools", "coding")}


def _pool_entry_ctx(tmp_path, emitter=None):
    store = RoutingStore(str(tmp_path / "data"))
    table = RL.RoleTable()
    return PR.RoutingCtx(
        store=store, role_table=table, kb=_pool_entry_kb(),
        provider_health={p: T.ProviderHealth(provider=p, status="ONLINE")
                         for p in ("pa", "pb", "pc", "lo")},
        model_health={k: T.ModelHealth(provider=k[0], model=k[1],
                                       status="READY")
                      for k in [("pa", "pa/a-1"), ("pb", "pb/b-1"),
                                ("pc", "pc/c-1"), ("lo", "lo/tiny")]},
        provider_capabilities=dict(_POOL_ENTRY_CAPS),
        resource_state={"eligible": True, "ref": "rs-1"},
        budget_state={"eligible": True, "ref": "bs-1"},
        emitter=emitter)


def _bind_pool_profile(ctx, role, members, strategy):
    old = PR._DEFAULT_POOLS_CTX
    PR.bind_pools_ctx(ctx)
    try:
        return PR.set_role_pool("p1", role, "pool", None, None,
                                members, strategy)
    finally:
        PR._DEFAULT_POOLS_CTX = old


def _decide_body(role, **over):
    body = {"project_id": "p1", "task_id": "t1", "run_id": "r1",
            "role": role, "task_class": "coding"}
    body.update(over)
    return body


def test_pick_director_decides_per_task_through_decide(tmp_path):
    events = []
    emitter = TP.TelemetryEmitter()
    emitter.add_sink(events.append)
    ctx = _pool_entry_ctx(tmp_path, emitter=emitter)
    _bind_pool_profile(ctx, "director", [
        {"provider": "pa", "model": "pa/a-1", "use_mode": "primary"},
        {"provider": "pb", "model": "pb/b-1", "use_mode": "fallback"}],
        "DIRECTOR_PER_TASK")
    P.bind_pool_store(ctx.store)
    try:
        assert (P.pick_pool_strategy("director", "p1")
                == "DIRECTOR_PER_TASK")
        status, payload = PR.post_decide(ctx, {}, _decide_body("director"))
        assert status == 200, payload
        assert payload["status"] == "BLOCKED"
        assert T.STRATEGY_LABELS["DIRECTOR_PER_TASK"] in payload["reason"]
        status, payload = PR.post_decide(
            ctx, {}, _decide_body("director", director_pick_provider="pa",
                                  director_pick_model="pa/a-1"))
        assert status == 200, payload
        assert payload["status"] == "ROUTED"
        assert payload["selected_model"] == "pa/a-1"
        assert payload["strategy"] == "DIRECTOR_PER_TASK"
        assert T.STRATEGY_LABELS["DIRECTOR_PER_TASK"] in payload["reason"]
        assert events and all(e.get("reason") for e in events)
        assert (T.STRATEGY_LABELS["DIRECTOR_PER_TASK"]
                in events[-1]["reason"])
    finally:
        P.unbind_pool_store()


def test_pick_auto_uses_auto_rule_through_decide(tmp_path):
    events = []
    emitter = TP.TelemetryEmitter()
    emitter.add_sink(events.append)
    ctx = _pool_entry_ctx(tmp_path, emitter=emitter)
    _bind_pool_profile(ctx, "worker", [
        {"provider": "pa", "model": "pa/a-1", "use_mode": "primary"},
        {"provider": "pb", "model": "pb/b-1", "use_mode": "fallback"},
        {"provider": "pc", "model": "pc/c-1", "use_mode": "fallback"}],
        "AUTO")
    P.bind_pool_store(ctx.store)
    try:
        assert P.pick_pool_strategy("worker", "p1") == "AUTO"
        status, payload = PR.post_decide(ctx, {}, _decide_body("worker"))
        assert status == 200, payload
        assert payload["status"] == "ROUTED"
        assert payload["selected_model"] == "pb/b-1"
        assert payload["strategy"] == "AUTO"
        assert T.STRATEGY_LABELS["AUTO"] in payload["reason"]
        assert len(events) == 1
        assert T.STRATEGY_LABELS["AUTO"] in events[0]["reason"]
    finally:
        P.unbind_pool_store()


def test_pick_fallback_order_first_healthy_through_put_and_decide(tmp_path):
    events = []
    emitter = TP.TelemetryEmitter()
    emitter.add_sink(events.append)
    ctx = _pool_entry_ctx(tmp_path, emitter=emitter)
    ctx.model_health[("pa", "pa/a-1")] = T.ModelHealth(
        provider="pa", model="pa/a-1", status="ERROR")
    status, payload = PR.put_role_pools(ctx, {}, {
        "project_id": "p1", "role": "manager", "mode": "pool",
        "provider": None, "model": None,
        "pool": [{"provider": "pa", "model": "pa/a-1",
                  "use_mode": "primary"},
                 {"provider": "pb", "model": "pb/b-1",
                  "use_mode": "fallback"},
                 {"provider": "pc", "model": "pc/c-1",
                  "use_mode": "fallback"}],
        "strategy": "FALLBACK_ORDER"})
    assert status == 200, payload
    assert payload["binding"]["strategy"] == "FALLBACK_ORDER"
    P.bind_pool_store(ctx.store)
    try:
        assert P.pick_pool_strategy("manager", "p1") == "FALLBACK_ORDER"
        status, payload = PR.post_decide(ctx, {}, _decide_body("manager"))
        assert status == 200, payload
        assert payload["status"] == "ROUTED"
        assert payload["selected_model"] == "pb/b-1"
        assert payload["strategy"] == "FALLBACK_ORDER"
        assert "pa/a-1" in payload["reason"]
        assert T.STRATEGY_LABELS["FALLBACK_ORDER"] in payload["reason"]
        assert [c["model"] for c in payload["fallback_chain"]] == ["pc/c-1"]
        assert len(events) == 1
        assert T.STRATEGY_LABELS["FALLBACK_ORDER"] in events[0]["reason"]
    finally:
        P.unbind_pool_store()


def test_pick_split_parallel_spreads_through_decide(tmp_path):
    events = []
    emitter = TP.TelemetryEmitter()
    emitter.add_sink(events.append)
    ctx = _pool_entry_ctx(tmp_path, emitter=emitter)
    _bind_pool_profile(ctx, "worker", [
        {"provider": "lo", "model": "lo/tiny", "use_mode": "draft",
         "provider_type": "local"},
        {"provider": "pa", "model": "pa/a-1", "use_mode": "verify"}],
        "SPLIT_PARALLEL")
    P.bind_pool_store(ctx.store)
    try:
        assert P.pick_pool_strategy("worker", "p1") == "SPLIT_PARALLEL"
        status, payload = PR.post_decide(ctx, {}, _decide_body("worker"))
        assert status == 200, payload
        assert payload["status"] == "ROUTED"
        assert payload["route"] == "SPLIT"
        assert payload["strategy"] == "SPLIT_PARALLEL"
        assert (sorted(a["stage"] for a in payload["assignments"])
                == ["cloud_verify", "local_draft"])
        assert (sorted((a["provider"], a["model"])
                       for a in payload["assignments"])
                == [("lo", "lo/tiny"), ("pa", "pa/a-1")])
        assert T.STRATEGY_LABELS["SPLIT_PARALLEL"] in payload["reason"]
        assert len(events) == 1
        assert T.STRATEGY_LABELS["SPLIT_PARALLEL"] in events[0]["reason"]
    finally:
        P.unbind_pool_store()


def test_pick_no_binding_defaults_auto_through_decide(tmp_path):
    events = []
    emitter = TP.TelemetryEmitter()
    emitter.add_sink(events.append)
    ctx = _pool_entry_ctx(tmp_path, emitter=emitter)
    assert P.pick_pool_strategy("worker", "p1") == "AUTO"
    status, payload = PR.post_decide(ctx, {}, dict(
        _decide_body("worker"),
        candidates=[{"provider": "pa", "model": "pa/a-1"},
                    {"provider": "pc", "model": "pc/c-1"}]))
    assert status == 200, payload
    assert payload["status"] == "ROUTED"
    assert payload["selected_model"] == "pa/a-1"
    assert len(events) == 1
    assert events[0].get("reason")


def test_pick_router_consults_facade_for_every_role(tmp_path, monkeypatch):
    kb = FakeKb({
        ("pa", "pa/a-1"): make_facts("pa", "pa/a-1", fit=0.90, quality=0.92,
                                     price_in=0.010, price_out=0.030),
        ("pb", "pb/b-1"): make_facts("pb", "pb/b-1", fit=0.90, quality=0.91,
                                     price_in=0.005, price_out=0.015),
    })
    store = RoutingStore(str(tmp_path / "data"))
    wanted = {"director": "DIRECTOR_PER_TASK", "manager": "FALLBACK_ORDER",
              "worker": "AUTO", "auditor": "FALLBACK_ORDER",
              "watcher": "AUTO"}
    for role, strategy in wanted.items():
        store.save_pool(P.make_binding(
            role, "p1", [P.PoolMember("pa", "pa/a-1"),
                         P.PoolMember("pb", "pb/b-1")], strategy=strategy))
    calls = []
    real_pick = P.pick_pool_strategy

    def spy(role, project_id):
        calls.append((role, project_id))
        return real_pick(role, project_id)

    monkeypatch.setattr(P, "pick_pool_strategy", spy)
    events = []
    emitter = TP.TelemetryEmitter()
    emitter.add_sink(events.append)
    d = deps(kb, {"pa": "ONLINE", "pb": "ONLINE"},
             {("pa", "pa/a-1"): "READY", ("pb", "pb/b-1"): "READY"},
             {"pa": ("text", "tools", "coding"),
              "pb": ("text", "tools", "coding")},
             store=store, emitter=emitter)
    for role in ("director", "manager", "worker", "auditor", "watcher"):
        extra = {}
        if role == "director":
            extra = {"director_pick_provider": "pa",
                     "director_pick_model": "pa/a-1"}
        out = R.decide_and_record(
            req([], role=role, mode="pool", **extra), d)
        assert out.status == "ROUTED", (role, out.decision.reason)
        assert out.decision.strategy == wanted[role], role
        assert T.STRATEGY_LABELS[wanted[role]] in out.decision.reason, role
    assert len(calls) == len(wanted)
    assert sorted(role for role, _pid in calls) == sorted(wanted)
    assert {pid for _, pid in calls} == {"p1"}
    by_role = {}
    for e in events:
        by_role.setdefault(e.get("role"), []).append(e)
    assert sorted(by_role) == sorted(wanted)
    for role, strategy in wanted.items():
        assert by_role[role]
        assert all(e.get("reason") for e in by_role[role])
        assert any(T.STRATEGY_LABELS[strategy] in e["reason"]
                   for e in by_role[role]), role


def test_pick_unresolvable_stored_strategy_routes_by_member_count(tmp_path):
    store = RoutingStore(str(tmp_path / "data"))
    store._save_table("profiles", {"roles": {}, "manager": None,
                                   "pools": {"p1\x00worker": {
                                       "role": "worker",
                                       "project_id": "p1",
                                       "strategy": None, "version": 1,
                                       "members": [
                                           {"provider": "pa",
                                            "model": "pa/a-1"},
                                           {"provider": "pb",
                                            "model": "pb/b-1"}]}}})
    kb = FakeKb({
        ("pa", "pa/a-1"): make_facts("pa", "pa/a-1"),
        ("pb", "pb/b-1"): make_facts("pb", "pb/b-1"),
    })
    d = deps(kb, {"pa": "ONLINE", "pb": "ONLINE"},
             {("pa", "pa/a-1"): "READY", ("pb", "pb/b-1"): "READY"},
             {"pa": ("text", "tools", "coding"),
              "pb": ("text", "tools", "coding")},
             store=store)
    P.bind_pool_store(store)
    try:
        assert P.pick_pool_strategy("worker", "p1") == "DIRECTOR_PER_TASK"
    finally:
        P.unbind_pool_store()
    out = R.decide_and_record(req([], role="worker", mode="pool"), d)
    assert out.status == "BLOCKED"
    assert "unknown pool strategy" not in out.decision.reason
    assert T.STRATEGY_LABELS["DIRECTOR_PER_TASK"] in out.decision.reason
    P.bind_pool_store(store)
    try:
        out2 = R.decide_and_record(req([], role="worker", mode="pool",
                                       director_pick_provider="pa",
                                       director_pick_model="pa/a-1"), d)
    finally:
        P.unbind_pool_store()
    assert out2.status == "ROUTED"
    assert out2.decision.selected_model == "pa/a-1"
    assert out2.decision.strategy == "DIRECTOR_PER_TASK"
