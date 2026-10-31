"""K04G CODER-1 Heron served proofs: one behaviour test per owned row.

Each test boots the real seam app (create_app + TestClient, memory
secret store) and drives one live routing route through the create_app
dispatch into the owned routing files (router.py / types.py). Loopback
TEST data only; server-side health/capability views are seeded with the
real frozen product types. No fakes in product code; no shared tests
across rows.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.routing import types as T

TOKEN = "k04g-coder1-token"
HEADERS = {"x-actor": TOKEN, "x-ui-session-token": TOKEN}


def _client(tmp_path):
    """Boot the real seam app on an isolated store dir (served leg)."""
    os.environ["AGENT_SI_SECRET_STORE"] = "memory"
    from agent_si.backend.app import create_app
    import fastapi.testclient as _ftc

    app = create_app({"store_dir": str(tmp_path / "appdata"),
                      "secret_store": "memory",
                      "ui_session_token": TOKEN},
                     auth_hook=None, rate_hook=None, model_factory=None)
    assert app.state.k04_config_error is None, app.state.k04_config_error
    assert app.state.k04_ctx is not None
    return _ftc.TestClient(app), app


def _seed_online(ctx):
    """Seed server-side health/capability views with real frozen types."""
    ctx.provider_health["pa"] = T.ProviderHealth(
        provider="pa", status="ONLINE")
    ctx.model_health[("pa", "pa/m1")] = T.ModelHealth(
        provider="pa", model="pa/m1", status="READY")
    ctx.provider_capabilities["pa"] = ("text",)
    ctx.resource_state = {"eligible": True, "ref": "rs-k04g-coder1"}
    ctx.budget_state = {"eligible": True, "ref": "bs-k04g-coder1"}


def _pin_worker(client):
    resp = client.put("/api/v1/roles/pools", json={
        "project_id": "p1", "role": "worker", "mode": "PINNED",
        "provider": "pa", "model": "pa/m1", "pool": [], "strategy": "AUTO"},
        headers=HEADERS)
    assert resp.status_code == 200, resp.text
    assert resp.json().get("ok") is True, resp.text


def test_k04g_b0b_sdk_79_auto_decide_reaches_selection_gate(tmp_path):
    """B0B-SDK-79: served AUTO decide dispatches into router.select.

    Route: POST /api/v1/routing/decide -> router.select
    (src/agent_si/routing/router.py:1182). The served AUTO path runs
    the frozen 6-ref facade; with no KB row the 11-step selection
    fail-closes at HARD_CAPABILITY_FILTER and the BLOCKED reason still
    carries the Optimization Policy view.
    """
    client, app = _client(tmp_path)
    _seed_online(app.state.k04_ctx)
    resp = client.post("/api/v1/routing/decide", json={
        "project_id": "p1", "task_id": "t1", "run_id": "r1",
        "role": "worker", "task_class": "coding",
        "candidates": [{"provider": "pa", "model": "pa/m1"}]},
        headers=HEADERS)
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["status"] == "BLOCKED", payload
    assert payload["route"] == "BLOCKED", payload
    assert payload["decision_id"], payload
    reason = payload["reason"]
    assert "HARD_CAPABILITY_FILTER" in reason, reason
    assert "policy_view=required_quality>=" in reason, reason


def test_k04g_b0b_sdk_17_pinned_decide_routes_cloud(tmp_path):
    """B0B-SDK-17: served PINNED decide routes CLOUD via decide_and_record.

    Route: POST /api/v1/routing/decide -> router.decide_and_record
    (src/agent_si/routing/router.py:1465). A stored PINNED profile
    takes the EXPLICIT_MODEL_PIN branch to a CLOUD route with the
    Optimization Policy view in the reason.
    """
    client, app = _client(tmp_path)
    _seed_online(app.state.k04_ctx)
    _pin_worker(client)
    resp = client.post("/api/v1/routing/decide", json={
        "project_id": "p1", "task_id": "t1", "run_id": "r1",
        "role": "worker", "task_class": "coding", "mode": "PINNED",
        "candidates": [{"provider": "pa", "model": "pa/m1"}]},
        headers=HEADERS)
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["status"] == "ROUTED", payload
    assert payload["route"] == "CLOUD", payload
    assert payload["selected_provider"] == "pa", payload
    assert payload["selected_model"] == "pa/m1", payload
    assert payload["eligibility_source"] == "EXPLICIT_MODEL_PIN", payload
    assert "policy_view=required_quality>=" in payload["reason"], payload
    assert len(payload["assignments"]) == 1, payload
    assert payload["assignments"][0]["stage"] == "task", payload


def test_k04g_b0b_bp02_8_optimization_policy_view_served(tmp_path):
    """B0B-BP02-8: served Optimization Policy view over create_app.

    Route: GET /api/v1/routing/optimization-policy serves the
    OptimizationPolicy record (src/agent_si/routing/types.py:193):
    required quality, risk ceiling and weights, no token needed.
    """
    client, _app = _client(tmp_path)
    resp = client.get("/api/v1/routing/optimization-policy")
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["required_quality"] == 0.8, payload
    assert payload["max_risk"] == "HIGH", payload
    assert set(payload["weights"]) == {"weight_quality", "weight_cost",
                                       "weight_latency",
                                       "weight_cloud_tokens"}, payload
    assert payload["local_preference"] is False, payload


def test_k04g_b0b_sdk_111_decision_why_replays_routed_triple(tmp_path):
    """B0B-SDK-111: served why replay returns the routed decision triple.

    Route: GET /api/v1/routing/decision/{id}/why replays the served
    PINNED decision as RoutingDecision + assignments + snapshot
    (src/agent_si/routing/types.py:300) with matching snapshot ids.
    """
    client, app = _client(tmp_path)
    _seed_online(app.state.k04_ctx)
    _pin_worker(client)
    resp = client.post("/api/v1/routing/decide", json={
        "project_id": "p1", "task_id": "t1", "run_id": "r1",
        "role": "worker", "task_class": "coding", "mode": "PINNED",
        "candidates": [{"provider": "pa", "model": "pa/m1"}]},
        headers=HEADERS)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ROUTED", resp.text
    decision_id = resp.json()["decision_id"]
    why = client.get("/api/v1/routing/decision/%s/why" % decision_id)
    assert why.status_code == 200, why.text
    body = why.json()
    assert set(("decision", "assignments", "snapshot")) <= set(body), body
    decision = body["decision"]
    assert decision["decision_id"] == decision_id, body
    assert decision["route"] == "CLOUD", body
    assert decision["selected_model"] == "pa/m1", body
    assert (decision["eligibility_source"]
            == "EXPLICIT_MODEL_PIN"), body
    assert "policy_view=required_quality>=" in decision["reason"], body
    assert len(body["assignments"]) == 1, body
    assert body["assignments"][0]["status"] == "PLANNED", body
    assert (body["snapshot"]["routing_snapshot_id"]
            == decision["routing_snapshot_id"]), body
    assert any(row.get("model") == "pa/m1"
               for row in body["snapshot"]["candidate_snapshot"]), body
