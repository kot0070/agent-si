"""DRF3K04A policy view + immutable PricingSnapshot (testid drf3k04a-policy).

RED-first: fails on the old tree (no Optimization Policy view on the
served routing path, prices have no immutable-version guard) and passes
after. One behaviour test through create_app + HTTP client covering:
- kit/BUILD_PLAN.md:1594 B0B-UNCOVERED_ARCH-528: the served settings
  path presents the Optimization Policy view (required quality, risk
  ceiling, weights) derived from the real OptimizationPolicy on the
  production routing path (every decision reason carries it; the
  persisted decision is read back over a served GET).
- kit/BUILD_PLAN.md:1643 B0B-UNCOVERED_ARCH-424: new prices land only
  as new immutable PricingSnapshot versions (old version never
  mutated, in-place correction refused, versions accumulate).
Real routing backend only: the app's own CatalogKbReader KB, its own
real RoutingStore and its own real BudgetGate; health views use the
real frozen product types (provider transport stand-ins, no FakeRouter,
no doubles in mount files). Loopback TEST data only, memory secret
store, no keys, no network.
"""
import copy
import sys
from dataclasses import replace
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fastapi.testclient import TestClient  # noqa: E402

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.budget.gate import BudgetGate  # noqa: E402
from agent_si.routing import router as R  # noqa: E402
from agent_si.routing import types as T  # noqa: E402
from agent_si.routing.interface import PricingSnapshot  # noqa: E402

APP_TOKEN = "drf3k04a-app-token"
DAY = "2026-10-26T00:00:00Z"
DAY2 = "2026-10-27T00:00:00Z"
HEADERS = {"x-actor": "drf3k04a-probe", "x-ui-session-token": APP_TOKEN}


def _opt():
    return T.OptimizationPolicy(
        policy_id="op-drf3k04a", version=1, created_at=DAY,
        hash="h-drf3k04a", required_quality=0.85,
        max_risk="MEDIUM", weight_quality=1.0,
        weight_cost=0.5, weight_latency=0.25,
        weight_cloud_tokens=0.1, local_preference=False,
        deadline=None, budget_limit=None)


def _pol():
    return T.RoutingPolicy(
        policy_id="rp-drf3k04a", version=1, created_at=DAY,
        hash="h-drf3k04a", task_class="coding", risk_level="LOW",
        strict_min=1.0, tolerant_min=0.85, confidence_min=0.7,
        sample_min=20, freshness_requirement="CURRENT",
        local_allowed=True, split_allowed=True, cloud_required=False)


def test_drf3k04a_policy_view_and_immutable_snapshot(tmp_path):
    """drf3k04a-policy: served policy view + immutable price versions."""
    app = create_app({
        "store_dir": str(tmp_path / "appdata"),
        "secret_store": "memory",
        "ui_session_token": APP_TOKEN,
    })
    assert app.state.k04_config_error is None, app.state.k04_config_error
    ctx = app.state.k04_ctx
    assert ctx is not None
    gate = ctx.budget_state
    assert isinstance(gate, BudgetGate), type(gate)
    client = TestClient(app)

    # ARCH-528: decide on the production routing entry with the app's
    # own real store/KB/gate; the decision reason carries the
    # Optimization Policy view (required quality, risk ceiling,
    # weights) rendered from the real OptimizationPolicy.
    request = R.RoutingRequest(
        project_id="drf3k04a-p1", task_id="t1", run_id="r1",
        role="worker", task_class="coding",
        routing_policy=_pol(), optimization_policy=_opt(),
        candidates=(T.CandidateModel(
            provider="test-drf3k04a",
            model="test-drf3k04a/m-1"),),
        required_capabilities=("text",),
        required_modalities=("text",),
        task_risk="LOW", mode="PINNED",
        pinned_provider="test-drf3k04a",
        pinned_model="test-drf3k04a/m-1")
    deps = R.RoutingDeps(
        kb=ctx.kb,
        provider_health={"test-drf3k04a": T.ProviderHealth(
            provider="test-drf3k04a", status="ONLINE")},
        model_health={("test-drf3k04a", "test-drf3k04a/m-1"):
                      T.ModelHealth(provider="test-drf3k04a",
                                    model="test-drf3k04a/m-1",
                                    status="READY")},
        provider_capabilities={"test-drf3k04a": ("text",)},
        resource_state={"eligible": True, "ref": "rs-drf3k04a"},
        budget_state={"eligible": True, "ref": "bs-drf3k04a"},
        store=ctx.store, emitter=None)
    outcome = R.decide_and_record(request, deps)
    assert outcome.status == "ROUTED", outcome.decision.reason
    reason = outcome.decision.reason
    assert "policy_view" in reason, reason
    assert "0.85" in reason, reason
    assert "MEDIUM" in reason, reason
    assert "weight_quality=1.0" in reason, reason
    assert "weight_cost=0.5" in reason, reason
    assert "weight_latency=0.25" in reason, reason
    assert "weight_cloud_tokens=0.1" in reason, reason

    # The served view matches the product symbol on the real policy.
    view = R.optimization_policy_view(_opt())
    assert view["required_quality"] == 0.85, view
    assert view["max_risk"] == "MEDIUM", view
    assert view["weight_quality"] == 1.0, view
    assert view["weight_cost"] == 0.5, view
    assert view["weight_latency"] == 0.25, view
    assert view["weight_cloud_tokens"] == 0.1, view
    for value in ("0.85", "MEDIUM", "1.0", "0.5", "0.25", "0.1"):
        assert value in reason, (value, reason)

    # The same view comes back over a served GET on the persisted
    # decision (served settings path through create_app + HTTP).
    why = client.get("/api/v1/routing/decision/%s/why"
                     % outcome.decision.decision_id)
    assert why.status_code == 200, why.text
    served_reason = why.json()["decision"]["reason"]
    assert "policy_view" in served_reason, served_reason
    assert "0.85" in served_reason, served_reason
    assert "MEDIUM" in served_reason, served_reason

    # ARCH-424 on the served routing entry: a routed winner with
    # known prices records a new immutable PricingSnapshot version
    # through the bound BudgetGate registry (real KbModelFacts data,
    # real gate, no store write); the reason carries the evidence.
    from agent_si.routing import kb_port as KB
    priced = KB.KbModelFacts(
        provider="test-drf3k04a", model="test-drf3k04a/m-1",
        task_fit={"coding": 0.9}, strict_pass_rate=0.9,
        tolerant_pass_rate=0.9, sample_count=50, confidence=0.9,
        freshness="CURRENT", input_price=0.010, output_price=0.030,
        modalities=("text",), assessed_risk="LOW",
        fields_state="MEASURED", verified_static=False,
        source="TEST-loopback", measured_at=DAY, latency_ms=400.0)
    winner = R._Eval(
        candidate=T.CandidateModel(
            provider="test-drf3k04a", model="test-drf3k04a/m-1"),
        facts=priced, index=0, passed=True,
        branch="CAPABILITY_EVIDENCE", capability_state="MEASURED",
        quality=0.9, fit=0.9, cost_per_1k=0.040, cost_known=True,
        latency_ms=400.0, score=1.0)
    priced_request = R.RoutingRequest(
        project_id="drf3k04a-p1", task_id="t1", run_id="r2",
        role="worker", task_class="coding",
        routing_policy=_pol(), optimization_policy=_opt(),
        candidates=(winner.candidate,))
    priced_deps = R.RoutingDeps(
        kb=ctx.kb,
        provider_health={"test-drf3k04a": T.ProviderHealth(
            provider="test-drf3k04a", status="ONLINE")},
        model_health={("test-drf3k04a", "test-drf3k04a/m-1"):
                      T.ModelHealth(provider="test-drf3k04a",
                                    model="test-drf3k04a/m-1",
                                    status="READY")},
        provider_capabilities={"test-drf3k04a": ("text",)},
        resource_state={"eligible": True, "ref": "rs-drf3k04a"},
        budget_state=gate, store=None, emitter=None)
    priced_outcome = R._finish(
        priced_request, priced_deps, [], [winner], winner, [], "CLOUD",
        "auto", "price+quality basis", "CAPABILITY_EVIDENCE", winner,
        None)
    assert priced_outcome.status == "ROUTED", \
        priced_outcome.decision.reason
    priced_reason = priced_outcome.decision.reason
    assert "policy_view" in priced_reason, priced_reason
    assert "pricing_snapshot=psnap-" in priced_reason, priced_reason
    minted = gate.pricing_history(provider_id="test-drf3k04a")
    assert len(minted) == 1, minted
    snap_id = minted[0]["pricing_snapshot_id"] \
        if isinstance(minted[0], dict) \
        else minted[0].pricing_snapshot_id
    assert snap_id in priced_reason, (snap_id, priced_reason)
    assert ("psnap-" in snap_id) and snap_id.startswith("psnap-")
    kept = gate.get_pricing_snapshot(snap_id)
    kept_price = kept["input_token_price"] \
        if isinstance(kept, dict) else kept.input_token_price
    assert kept_price == 0.010, kept

    # ARCH-424: new prices land only as new immutable versions.
    old = PricingSnapshot(
        pricing_snapshot_id="drf3k04a-snap-1",
        provider_id="test-drf3k04a", model_id="test-drf3k04a/m-1",
        currency="USD", effective_at=DAY, source="TEST-loopback",
        input_token_price="0.010", output_token_price="0.030",
        created_at=DAY, hash="h1")
    frozen = copy.deepcopy(old)
    gate.publish_pricing_snapshot(old)
    assert old == frozen
    # Same id with a changed price is refused (never rewritten in
    # place): a correction must mint a new version id.
    with pytest.raises(ValueError):
        gate.publish_pricing_snapshot(
            replace(old, input_token_price="0.020"))
    assert gate.get_pricing_snapshot(
        "drf3k04a-snap-1").input_token_price == "0.010"
    # Correcting the price mints a new version; the old row is kept.
    new = gate.correct_pricing_snapshot(
        "drf3k04a-snap-1",
        pricing_snapshot_id="drf3k04a-snap-2", created_at=DAY2,
        input_token_price="0.020")
    assert new.pricing_snapshot_id == "drf3k04a-snap-2", new
    assert new.input_token_price == "0.020", new
    assert new.output_token_price == "0.030", new
    assert old == frozen
    assert old.input_token_price == "0.010", old
    assert [(s["pricing_snapshot_id"]
             if isinstance(s, dict) else s.pricing_snapshot_id)
            for s in gate.pricing_history()] == [
                snap_id, "drf3k04a-snap-1", "drf3k04a-snap-2"]
    assert gate.get_pricing_snapshot(
        "drf3k04a-snap-1").input_token_price == "0.010"
    assert gate.get_pricing_snapshot(
        "drf3k04a-snap-2").input_token_price == "0.020"
    # Republishing identical content is idempotent (no new version).
    gate.publish_pricing_snapshot(copy.deepcopy(new))
    assert len(gate.pricing_history()) == 3, gate.pricing_history()
    # Retrieved rows are copies: mutating one never touches the store.
    peek = gate.get_pricing_snapshot("drf3k04a-snap-1")
    peek.input_token_price = "9.999"
    assert gate.get_pricing_snapshot(
        "drf3k04a-snap-1").input_token_price == "0.010"
    # The module guard mints without touching its base either.
    from agent_si.budget import gate as G
    base = copy.deepcopy(
        gate.get_pricing_snapshot("drf3k04a-snap-1"))
    third = G.pricing_snapshot_immutable(
        base, pricing_snapshot_id="drf3k04a-snap-3",
        created_at=DAY2, output_token_price="0.040")
    assert third.pricing_snapshot_id == "drf3k04a-snap-3", third
    assert third.output_token_price == "0.040", third
    assert third.input_token_price == "0.010", third
    assert base == gate.get_pricing_snapshot("drf3k04a-snap-1"), base

    # Served confirmation over HTTP on the same real gate.
    gate.configure_project("drf3k04a-p1", "USD", "100", "80", "100",
                           updated_at=DAY)
    live = client.get("/api/v1/budget",
                      params={"project_id": "drf3k04a-p1"})
    assert live.status_code == 200, live.text
    assert live.json()["budget"]["hard_limit"] == "100", live.text
