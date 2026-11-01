# K04NEXT3 C1 lane — pools/routing-side seams for R-311, R-332, R-339.
# Every claim goes through agent_si.backend.pools_routes._DISPATCH entries
# (the served HTTP surface); the pools-side authority is the new
# agent_si.pools package. No mocks for the claim, loopback TEST data only.
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend import pools_routes as PR
from agent_si.pools import (
    PoolMember,
    binding_summary,
    make_binding,
    strategy_label,
    suggest_strongest,
)
from agent_si.routing import kb_port as KB
from agent_si.routing import roles as RL
from agent_si.routing import types as T
from agent_si.routing.store import RoutingStore


class _FakeKb(KB.KbReader):
    # FAKE-OF: KB.KbReader (in-memory facts dict for served path tests)
    def __init__(self, facts):
        self._facts = dict(facts)

    def facts(self, provider, model):
        return self._facts.get((provider, model))

    def models(self, provider=None):
        return [f for (p, _m), f in self._facts.items()
                if provider is None or p == provider]


def _facts(provider, model, *, state="MEASURED", quality=0.9,
           price_in=0.01, price_out=0.03):
    return KB.KbModelFacts(
        provider=provider, model=model,
        task_fit={"coding": quality, "text": quality,
                  "general": quality},
        strict_pass_rate=quality, tolerant_pass_rate=quality,
        sample_count=50, confidence=0.9, freshness="CURRENT",
        input_price=price_in, output_price=price_out,
        modalities=("text",), assessed_risk="LOW",
        fields_state=state, verified_static=False,
        source="k04next3-c1", measured_at="2026-10-29T00:00:00+00:00",
        latency_ms=400.0)


def _ctx(tmp_path, kb, models, budget_state=None):
    return PR.RoutingCtx(
        store=RoutingStore(str(tmp_path)),
        role_table=RL.RoleTable(),
        kb=kb,
        provider_health={"pa": T.ProviderHealth(provider="pa",
                                                status="ONLINE"),
                         "pb": T.ProviderHealth(provider="pb",
                                                status="ONLINE")},
        model_health={(m[0], m[1]): T.ModelHealth(
            provider=m[0], model=m[1], status="READY") for m in models},
        provider_capabilities={"pa": ("text",), "pb": ("text",)},
        resource_state={"eligible": True, "ref": "rs-c1"},
        budget_state=(budget_state if budget_state is not None
                      else {"eligible": True, "ref": "bs-c1"}),
        emitter=None,
        session_token="ui-test-c1")


# R-311 pools/routing-side seam: the budget block says "budget" in words,
# and the blocked decision replays the same wording through the why entry.
def test_r311_served_block_replay_states_budget_in_words(tmp_path):
    kb = _FakeKb({("pa", "pa/m1"): _facts("pa", "pa/m1")})
    ctx = _ctx(tmp_path, kb, [("pa", "pa/m1")],
               budget_state={"eligible": False, "ref": "bs-blocked"})
    decide = dict(PR._DISPATCH)[("post", "/api/v1/routing/decide")]
    status, payload = decide(ctx, {}, {
        "project_id": "p1", "task_id": "t1", "run_id": "r1",
        "role": "worker", "task_class": "coding",
        "candidates": [{"provider": "pa", "model": "pa/m1"}]})
    assert status == 200, payload
    assert payload["status"] == "BLOCKED", payload
    assert "budget" in payload["reason"].lower(), payload
    why = dict(PR._DISPATCH)[("get", "/api/v1/routing/why")]
    status, bundle = why(ctx, {"decision_id": payload["decision_id"]}, {})
    assert status == 200, bundle
    assert bundle["decision"]["decision_id"] == payload["decision_id"], bundle
    assert "budget" in json.dumps(bundle).lower(), bundle


# R-332 pools-side seam: a pool/AUTO binding serves the fittest member and
# the roles entry lists the stored mode plus the frozen strategy.
def test_r332_served_pool_auto_routes_fittest(tmp_path):
    kb = _FakeKb({
        ("pa", "pa/m1"): _facts("pa", "pa/m1", quality=0.62),
        ("pb", "pb/b-1"): _facts("pb", "pb/b-1", quality=0.95),
    })
    ctx = _ctx(tmp_path, kb, [("pa", "pa/m1"), ("pb", "pb/b-1")])
    put = dict(PR._DISPATCH)[("put", "/api/v1/roles/pools")]
    status, payload = put(ctx, {}, {
        "project_id": "p1", "role": "worker", "mode": "pool",
        "provider": None, "model": None,
        "pool": [{"provider": "pa", "model": "pa/m1",
                  "use_mode": "primary"},
                 {"provider": "pb", "model": "pb/b-1",
                  "use_mode": "fallback"}],
        "strategy": "AUTO"})
    assert status == 200, payload
    stored = ctx.store.get_pool("p1", "worker")
    summary = binding_summary(stored)
    assert summary["strategy"] == "AUTO", summary
    assert summary["member_count"] == 2, summary
    assert (summary["strategy_label"]
            == strategy_label("AUTO") == T.STRATEGY_LABELS["AUTO"])
    decide = dict(PR._DISPATCH)[("post", "/api/v1/routing/decide")]
    status, payload = decide(ctx, {}, {
        "project_id": "p1", "task_id": "t1", "run_id": "r1",
        "role": "worker", "task_class": "coding"})
    assert status == 200, payload
    assert payload["status"] == "ROUTED", payload
    assert payload["selected_model"] == "pb/b-1", payload
    assert payload["strategy"] == "AUTO", payload
    assert payload["reason"], payload
    roles = dict(PR._DISPATCH)[("get", "/api/v1/roles/pools")]
    status, listed = roles(ctx, {"project_id": "p1"}, {})
    assert status == 200, listed
    worker = [row for row in listed["roles"] if row["role"] == "worker"][0]
    assert worker["mode"] == "pool", worker
    assert worker["strategy"] == "AUTO", worker
    assert len(worker["pool"]) == 2, worker


# R-332 pools-side seam: PINNED routes the pinned model and holds no pool
# binding; AUTO refuses a provider/model (frozen profile contract).
def test_r332_served_pinned_mode_routes_pinned_model(tmp_path):
    kb = _FakeKb({
        ("pa", "pa/m1"): _facts("pa", "pa/m1", quality=0.62),
        ("pb", "pb/b-1"): _facts("pb", "pb/b-1", quality=0.95),
    })
    ctx = _ctx(tmp_path, kb, [("pa", "pa/m1"), ("pb", "pb/b-1")])
    put = dict(PR._DISPATCH)[("put", "/api/v1/roles/pools")]
    status, payload = put(ctx, {}, {
        "project_id": "p1", "role": "worker", "mode": "PINNED",
        "provider": "pa", "model": "pa/m1",
        "pool": [], "strategy": "AUTO"})
    assert status == 200, payload
    assert ctx.store.get_pool("p1", "worker") is None, \
        "PINNED holds no pool binding"
    decide = dict(PR._DISPATCH)[("post", "/api/v1/routing/decide")]
    status, payload = decide(ctx, {}, {
        "project_id": "p1", "task_id": "t1", "run_id": "r1",
        "role": "worker", "task_class": "coding",
        "candidates": [{"provider": "pa", "model": "pa/m1"},
                       {"provider": "pb", "model": "pb/b-1"}]})
    assert status == 200, payload
    assert payload["status"] == "ROUTED", payload
    assert payload["selected_model"] == "pa/m1", payload
    status, payload = put(ctx, {}, {
        "project_id": "p1", "role": "worker", "mode": "AUTO",
        "provider": "pa", "model": "pa/m1",
        "pool": [], "strategy": "AUTO"})
    assert status == 400, payload


# R-339 pools/routing-side seam: the picker (model checkboxes) exposes
# opaque keys only (never raw ids), the pick pins the model, and the
# suggest entry names the strongest model with its reason.
def test_r339_served_picker_hides_raw_ids_pick_pins_and_suggests(tmp_path):
    kb = _FakeKb({
        ("pa", "pa/m1"): _facts("pa", "pa/m1", quality=0.9),
        ("pb", "pb/b-1"): _facts("pb", "pb/b-1", quality=0.7),
    })
    ctx = _ctx(tmp_path, kb, [("pa", "pa/m1"), ("pb", "pb/b-1")])
    get_picker = dict(PR._DISPATCH)[("get", "/api/v1/routing/picker")]
    status, payload = get_picker(
        ctx, {"project_id": "p1", "role": "worker",
              "purpose": "coding"}, {})
    assert status == 200, payload
    options = payload["options"]
    assert len(options) == 2, payload
    dumped = json.dumps(options)
    assert "pa/m1" not in dumped and "pb/b-1" not in dumped, dumped
    keys = [opt["key"] for opt in options]
    assert len(set(keys)) == 2 and all(str(k) for k in keys), options
    post_pick = dict(PR._DISPATCH)[("post", "/api/v1/routing/pick")]
    status, payload = post_pick(ctx, {}, {
        "project_id": "p1", "role": "worker", "key": "no-such-key"})
    assert status == 404, payload
    status, payload = post_pick(ctx, {}, {
        "project_id": "p1", "role": "worker", "key": keys[0]})
    assert status == 200, payload
    assert payload["profile"]["mode"] == "PINNED", payload
    picked_model = payload["profile"]["model"]
    decide = dict(PR._DISPATCH)[("post", "/api/v1/routing/decide")]
    status, routed = decide(ctx, {}, {
        "project_id": "p1", "task_id": "t1", "run_id": "r1",
        "role": "worker", "task_class": "coding",
        "candidates": [{"provider": "pa", "model": "pa/m1"},
                       {"provider": "pb", "model": "pb/b-1"}]})
    assert status == 200, routed
    assert routed["status"] == "ROUTED", routed
    assert routed["selected_model"] == picked_model, routed
    get_suggest = dict(PR._DISPATCH)[("get", "/api/v1/routing/suggest")]
    status, payload = get_suggest(
        ctx, {"provider": "pa", "purpose": "coding"}, {})
    assert status == 200, payload
    assert payload["model"] == "pa/m1", payload
    assert payload["reason"], payload
    assert (suggest_strongest(kb, "pa").model
            == payload["model"] == "pa/m1")
    status, payload = get_suggest(
        ctx, {"provider": "nope", "purpose": "coding"}, {})
    assert status == 404, payload


# Pools-side seam: the new pools package builds bindings with the frozen
# default strategy rule (single member AUTO, several Director decides).
def test_pools_package_builds_bindings_with_default_strategy():
    solo = make_binding("worker", "p1",
                        [PoolMember("pa", "pa/m1")])
    assert solo.strategy == "AUTO", solo
    assert strategy_label(solo.strategy) == "Auto", solo
    multi = make_binding("worker", "p1",
                         [PoolMember("pa", "pa/m1"),
                          PoolMember("pb", "pb/b-1")])
    assert multi.strategy == "DIRECTOR_PER_TASK", multi
    assert (strategy_label(multi.strategy)
            == T.STRATEGY_LABELS["DIRECTOR_PER_TASK"])
    summary = binding_summary(multi)
    assert summary["member_count"] == 2, summary
    assert "Director decides per task" in summary["sentence"], summary
