"""FXCAPS (FIXBATCH1 L2): per-provider spend caps enforced, served.

Through the REAL app (create_app + store dir + secret_store memory +
HTTP TestClient). No mocks in product code; no fake providers.
POST /api/v1/budget/limits persists caps; over-cap reserve AND charge
refuse with PROVIDER_SPEND_CAP_BLOCKED; GET /api/v1/budget shows
per-provider spent vs cap; without caps everything stays allowed.
"""
import os
import sys

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_WS, "src")
for _p in (_WS, _SRC):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import fastapi.testclient  # noqa: E402

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.backend.orchestration import steplimits as _steplimits  # noqa: E402

APP_TOKEN = "fxcaps-app-token"
HEADERS = {"x-actor": "ui-probe", "x-ui-session-token": APP_TOKEN}

STAMP = "2026-11-01T00:00:00Z"
EXPIRY = "2026-11-02T00:00:00Z"


def _client(tmp_path):
    _steplimits._reset_state()
    app = create_app({"store_dir": str(tmp_path / "appdata"),
                      "ui_session_token": APP_TOKEN,
                      "secret_store": "memory"})
    return (fastapi.testclient.TestClient(app, raise_server_exceptions=False),
            app)


def _limits(client, pid, caps, **amounts):
    body = {"project_id": pid,
            "budget_limit": amounts.get("budget_limit", "100.00"),
            "soft_limit": amounts.get("soft_limit", "80.00"),
            "hard_limit": amounts.get("hard_limit", "100.00"),
            "provider_spend_caps": caps}
    resp = client.post("/api/v1/budget/limits", json=body,
                       headers=HEADERS)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_limits_persist_served(tmp_path):
    client, _app = _client(tmp_path)
    out = _limits(client, "fxcaps-persist", {"acme": "5.00"})
    assert out["provider_spend_caps"] == {"acme": "5.00"}, out
    resp = client.get("/api/v1/budget", params={"project_id": "fxcaps-persist"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["budget"]["provider_spend_caps"] == {"acme": "5.00"}
    # fresh app over the same store dir: caps survive the restart.
    client2, _app2 = _client(tmp_path)
    again = client2.get("/api/v1/budget",
                        params={"project_id": "fxcaps-persist"})
    assert again.status_code == 200, again.text
    assert again.json()["budget"]["provider_spend_caps"] == {"acme": "5.00"}


def test_limits_need_token_served(tmp_path):
    client, _app = _client(tmp_path)
    resp = client.post("/api/v1/budget/limits",
                       json={"project_id": "fxcaps-notok",
                             "provider_spend_caps": {"acme": "1.00"}})
    assert resp.status_code == 401, resp.text


def test_over_cap_reserve_refused_served(tmp_path):
    client, app = _client(tmp_path)
    _limits(client, "fxcaps-res", {"acme": "5.00"})
    ok = client.post("/api/v1/budget/providers/reserve-tokens",
                     json={"project_id": "fxcaps-res", "task_id": "t1",
                           "run_id": "r1", "reservation_id": "fxcaps-r1",
                           "estimated_amount": "4.00", "currency": "USD",
                           "provider_id": "acme"},
                     headers=HEADERS)
    assert ok.status_code == 200, ok.text
    over = client.post("/api/v1/budget/providers/reserve-tokens",
                       json={"project_id": "fxcaps-res", "task_id": "t1",
                             "run_id": "r1", "reservation_id": "fxcaps-r2",
                             "estimated_amount": "2.00", "currency": "USD",
                             "provider_id": "acme"},
                       headers=HEADERS)
    assert over.status_code == 409, over.text
    assert over.json()["code"] == "PROVIDER_SPEND_CAP_BLOCKED", over.text
    gate = app.state.k04_ctx.budget_state
    incidents = gate.list_incidents("fxcaps-res")
    assert incidents, "cap refusal must record a persistent incident"


def test_over_cap_charge_refused_served(tmp_path):
    client, app = _client(tmp_path)
    _limits(client, "fxcaps-chg", {"acme": "5.00"})
    gate = app.state.k04_ctx.budget_state
    res = gate.compare_and_reserve(
        {"project_id": "fxcaps-chg", "task_id": "t1", "run_id": "r1",
         "reservation_id": "fxcaps-c1", "estimated_amount": "4.00",
         "reserved_at": STAMP, "expires_at": EXPIRY,
         "provider_request_ref": "fxcaps-req-1", "provider_id": "acme"})
    assert res.ok, res
    from agent_si.budget.gate import BudgetBlockedError
    try:
        gate.settle({"reservation_id": "fxcaps-c1",
                     "provider_request_ref": "fxcaps-req-1",
                     "source": "fxcaps-charge", "settled_at": STAMP,
                     "actual_amount": "6.00",
                     "provider_usage_evidence_ref": "usage:fxcaps-chg/t1"})
    except BudgetBlockedError as exc:
        assert "PROVIDER_SPEND_CAP_BLOCKED" in str(exc), str(exc)
    else:
        raise AssertionError("over-cap charge was not refused")
    kept = gate.get_reservation("fxcaps-c1")
    assert kept.status == "ACTIVE", kept.to_dict()
    assert gate.get_state("fxcaps-chg").spent == "0", \
        gate.get_state("fxcaps-chg").to_dict()


def test_get_shows_spent_vs_cap_served(tmp_path):
    client, app = _client(tmp_path)
    _limits(client, "fxcaps-get", {"acme": "5.00"})
    gate = app.state.k04_ctx.budget_state
    gate.compare_and_reserve(
        {"project_id": "fxcaps-get", "task_id": "t1", "run_id": "r1",
         "reservation_id": "fxcaps-g1", "estimated_amount": "2.00",
         "reserved_at": STAMP, "expires_at": EXPIRY,
         "provider_request_ref": "fxcaps-req-g1", "provider_id": "acme"})
    gate.settle({"reservation_id": "fxcaps-g1",
                 "provider_request_ref": "fxcaps-req-g1",
                 "source": "fxcaps-spend", "settled_at": STAMP,
                 "actual_amount": "2.00",
                 "provider_usage_evidence_ref": "usage:fxcaps-get/t1"})
    resp = client.get("/api/v1/budget", params={"project_id": "fxcaps-get"})
    assert resp.status_code == 200, resp.text
    spending = resp.json()["budget"]["provider_spending"]
    assert spending["acme"] == {"spent": "2.00", "reserved": "0",
                                "cap": "5.00"}, spending


def test_no_caps_no_refusal_served(tmp_path):
    client, app = _client(tmp_path)
    _limits(client, "fxcaps-free", {})
    gate = app.state.k04_ctx.budget_state
    res = gate.compare_and_reserve(
        {"project_id": "fxcaps-free", "task_id": "t1", "run_id": "r1",
         "reservation_id": "fxcaps-n1", "estimated_amount": "100.00",
         "reserved_at": STAMP, "expires_at": EXPIRY,
         "provider_request_ref": "fxcaps-req-n1", "provider_id": "acme"})
    assert res.ok, res
    stl = gate.settle({"reservation_id": "fxcaps-n1",
                       "provider_request_ref": "fxcaps-req-n1",
                       "source": "fxcaps-free", "settled_at": STAMP,
                       "actual_amount": "100.00",
                       "provider_usage_evidence_ref": "usage:fxcaps-free/t1"})
    assert stl.status == "SETTLED", stl.to_dict()
