"""K04F budget seam: 8 uncovered rows proved served (REAL app + TestClient).

Served = each test boots the served app (create_app + TestClient, memory
secret store) and hits a real HTTP route, then asserts the row behavior
against the real product module (no fakes in product; no network; no keys).

Row -> route -> test:
- B0B-UNCOVERED_BP04-8 -> POST /api/v1/budget/k04f/breach ->
  test_k04f_bp04_8_breach_persistent_incident_served
- B0B-UNCOVERED_BP04-34 -> POST /api/v1/budget/k04f/blocked-terminate ->
  test_k04f_bp04_34_blocked_terminates_run_served
- B0B-UNCOVERED_ARCH-412 -> GET /api/v1/budget/k04f/estimate ->
  test_k04f_arch_412_estimated_tokens_served
- B0B-UNCOVERED_ARCH-416 -> POST /api/v1/budget/k04f/reserve-tokens ->
  test_k04f_arch_416_reserve_tokens_served
- B0B-UNCOVERED_ARCH-427 -> POST /api/v1/budget/k04f/route-block ->
  test_k04f_arch_427_routable_block_served
- B0B-UNCOVERED_BP04-5 -> POST /api/v1/budget/k04f/attach ->
  test_k04f_bp04_5_recollect_attaches_served
- B0B-UNCOVERED_BP04-14 -> POST /api/v1/budget/k04f/snapshot-proof ->
  test_k04f_bp04_14_snapshot_immutable_served
- B0B-UNCOVERED_UI_DELTA-32 -> PUT /api/v1/roles/pools (+ reads) ->
  test_k04f_ui_delta_32_settings_roles_served
"""
import glob
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import fastapi.testclient  # noqa: E402

from agent_si.backend.app import create_app  # noqa: E402

APP_TOKEN = "k04f-app-token"
HEADERS = {"x-actor": "ui-probe", "x-ui-session-token": APP_TOKEN}


def _settings(tmp_path):
    return {"store_dir": str(tmp_path / "appdata"),
            "ui_session_token": APP_TOKEN,
            "secret_store": "memory"}


def _client(tmp_path):
    os.environ["AGENT_SI_SECRET_STORE"] = "memory"
    app = create_app(_settings(tmp_path))
    return fastapi.testclient.TestClient(
        app, raise_server_exceptions=False), app


def _budget_dir(tmp_path):
    return str(tmp_path / "appdata" / "budget")


# [BP04-8]-part: every budget breach is a persistent incident record.
def test_k04f_bp04_8_breach_persistent_incident_served(tmp_path):
    client, _app = _client(tmp_path)
    resp = client.get("/api/v1/budget", params={"project_id": "k04f-b8"})
    assert resp.status_code == 404, resp.text
    resp = client.post(
        "/api/v1/budget/k04f/breach",
        json={"project_id": "k04f-b8", "currency": "USD",
              "hard_limit": "1.00", "fill_amount": "1.00",
              "over_amount": "0.01", "task_id": "t1", "run_id": "r1"},
        headers=HEADERS)
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["code"] == "BUDGET_HARD_BLOCKED", body
    assert body["incident_id"].startswith("inc-k04f-b8-"), body
    persisted = glob.glob(
        os.path.join(_budget_dir(tmp_path), "incident-*.json"))
    assert persisted, "breach incident must persist to the ledger store"
    from agent_si.budget.gate import BudgetGate
    fresh = BudgetGate(store_dir=_budget_dir(tmp_path))
    incidents = fresh.list_incidents("k04f-b8")
    assert [i.incident_id for i in incidents] == [body["incident_id"]], \
        [i.incident_id for i in incidents]
    assert "budget" in incidents[0].description.lower(), \
        incidents[0].description


# [BP04-34]-part: pre-run BUDGET_BLOCKED with started billable work
# terminalizes the run as FAILED/BUDGET_BLOCKED and releases the reserve.
def test_k04f_bp04_34_blocked_terminates_run_served(tmp_path):
    client, _app = _client(tmp_path)
    resp = client.post(
        "/api/v1/budget/k04f/blocked-terminate",
        json={"project_id": "k04f-b34", "task_id": "t1", "run_id": "r1",
              "contract_hash": "k04f-ch-1", "start_amount": "1.00"},
        headers=HEADERS)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["run_to_status"] == "FAILED", body
    assert body["run_to_reason"] == "BUDGET_BLOCKED", body
    assert body["release_reservations"] is True, body
    assert body["reservation_status"] == "RELEASED", body
    from agent_si.budget.gate import BudgetGate
    fresh = BudgetGate(store_dir=_budget_dir(tmp_path))
    res = fresh.get_reservation(body["reservation_id"])
    assert res.status == "RELEASED", res.to_dict()


# [ARCH-412]-part: estimated_tokens = max_tokens + policy overhead.
def test_k04f_arch_412_estimated_tokens_served(tmp_path):
    client, _app = _client(tmp_path)
    resp = client.get("/api/v1/budget/k04f/estimate",
                      params={"max_tokens": "1000", "token_overhead": "64"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["estimated_tokens"] == 1064, resp.text
    resp = client.get("/api/v1/budget/k04f/estimate",
                      params={"token_overhead": "64"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["estimated_tokens"] == 64, resp.text
    resp = client.get("/api/v1/budget/k04f/estimate",
                      params={"max_tokens": "-5", "token_overhead": "0"})
    assert resp.status_code == 400, resp.text


# [ARCH-416]-part: reserve only through reserveTokens with explicit
# currency; invented denominations and amounts are refused.
def test_k04f_arch_416_reserve_tokens_served(tmp_path):
    client, _app = _client(tmp_path)
    base = {"project_id": "k04f-b416", "task_id": "t1", "run_id": "r1",
            "reservation_id": "k04f-res-1", "estimated_amount": "2.50",
            "currency": "USD", "hard_limit": "10.00"}
    resp = client.post("/api/v1/budget/k04f/reserve-tokens", json=dict(base),
                       headers=HEADERS)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["currency"] == "USD", body
    assert body["estimated_amount"] == "2.50", body
    assert body["status"] == "ACTIVE", body
    bad = dict(base, reservation_id="k04f-res-2", currency="EUR")
    resp = client.post("/api/v1/budget/k04f/reserve-tokens", json=bad,
                       headers=HEADERS)
    assert resp.status_code == 409, resp.text
    assert resp.json()["code"] == "CURRENCY_MISMATCH", resp.text
    no_amount = dict(base, reservation_id="k04f-res-3")
    del no_amount["estimated_amount"]
    resp = client.post("/api/v1/budget/k04f/reserve-tokens", json=no_amount,
                       headers=HEADERS)
    assert resp.status_code == 400, resp.text
    resp = client.get("/api/v1/budget", params={"project_id": "k04f-b416"},
                      headers=HEADERS)
    assert resp.status_code == 200, resp.text
    assert resp.json()["budget"]["reserved"] == "2.50", resp.text


# [ARCH-427]-part: recoverable budget blocks route to BLOCKED (top-up
# restores) and to ESCALATED otherwise.
def test_k04f_arch_427_routable_block_served(tmp_path):
    client, _app = _client(tmp_path)
    resp = client.post("/api/v1/budget/k04f/route-block",
                       json={"recoverable": True}, headers=HEADERS)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["failure_class"] == "BUDGET_BLOCKED", body
    assert body["task_effect"] == "BLOCKED", body
    assert body["run_effect"] is None, body
    resp = client.post("/api/v1/budget/k04f/route-block",
                       json={"recoverable": False}, headers=HEADERS)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["task_effect"] == "ESCALATED", body
    assert body["run_effect"] == "FAILED/BUDGET_BLOCKED", body


# [BP04-5]-part: re-collection with an identical usage reference
# attaches to the existing record without duplicating.
def test_k04f_bp04_5_recollect_attaches_served(tmp_path):
    client, _app = _client(tmp_path)
    resp = client.post(
        "/api/v1/budget/k04f/attach",
        json={"usage_ref": "k04f-uref-1",
              "metric": {"metric_id": "k04f-m-1", "project_id": "k04f-b5",
                         "task_id": "t1", "run_id": "r1",
                         "metric_name": "input_tokens", "value": 10,
                         "unit": "tokens", "state": "MEASURED",
                         "source": "provider_usage_api",
                         "recorded_at": "2026-10-26T00:00:00Z"}},
        headers=HEADERS)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["created_first"] is True, body
    assert body["created_second"] is False, body
    assert body["same_row"] is True, body
    assert body["kept_metric_id"] == "k04f-m-1", body
    assert body["store_size"] == 1, body


# [BP04-14]-part: a referenced PricingSnapshot is immutable; a
# same-id re-register with new prices is refused, corrections mint
# a new version while the original row is unchanged.
def test_k04f_bp04_14_snapshot_immutable_served(tmp_path):
    client, _app = _client(tmp_path)
    resp = client.post(
        "/api/v1/budget/k04f/snapshot-proof",
        json={"pricing_snapshot_id": "k04f-ps-1",
              "provider_id": "cloud-a", "model_id": "cloud-a/m1",
              "currency": "USD", "input_token_price": "0.001",
              "output_token_price": "0.002",
              "new_input_token_price": "0.0015"},
        headers=HEADERS)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["cost"] == "2.000000", body
    assert body["refused_code"] == "SNAPSHOT_ID_REUSE", body
    assert body["new_snapshot_id"] == "k04f-ps-1-v2", body
    assert body["new_cost"] == "2.500000", body
    assert body["original_input_price"] == "0.001", body


# [UI_DELTA-32]-part: AI SETTINGS edits are reflected in the stored
# role profiles, and subsequent run behavior (resolution + routing)
# carries the edited pick, never a silent swap.
def test_k04f_ui_delta_32_settings_roles_served(tmp_path):
    client, _app = _client(tmp_path)
    put = {"project_id": "k04f-ui", "role": "worker", "mode": "PINNED",
           "provider": "pa", "model": "pa/m1", "pool": [],
           "strategy": "AUTO"}
    resp = client.put("/api/v1/roles/pools", json=put, headers=HEADERS)
    assert resp.status_code == 200, resp.text
    resp = client.get("/api/v1/routing/role",
                      params={"project_id": "k04f-ui", "role": "worker"})
    assert resp.status_code == 200, resp.text
    profile = resp.json()["profile"]
    assert (profile["provider"], profile["model"],
            profile["mode"]) == ("pa", "pa/m1", "PINNED"), profile
    put["model"] = "pa/m2"
    resp = client.put("/api/v1/roles/pools", json=put, headers=HEADERS)
    assert resp.status_code == 200, resp.text
    resp = client.get("/api/v1/routing/roles",
                      params={"project_id": "k04f-ui"})
    assert resp.status_code == 200, resp.text
    worker = [r for r in resp.json()["roles"]
              if r["role"] == "worker"][0]
    assert (worker["provider"], worker["model"]) == ("pa", "pa/m2"), worker
    assert "pa/m2" in worker["reason"], worker
    assert worker["status"] == "PINNED_UNHEALTHY", worker
