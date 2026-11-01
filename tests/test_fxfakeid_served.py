"""FXFAKEID served proofs: real-clock reservations, 400 on missing ids.

Served = each test boots the served app (create_app + TestClient, memory
secret store, isolated tmp store_dir) and hits a real HTTP route, then
asserts against the real product store (no fakes in product; no network).

Row -> route -> test:
- FXFAKEID reservation-clock -> POST /api/v1/budget/providers/reserve-tokens
  -> test_fxfakeid_reserve_tokens_uses_real_clock_served
- FXFAKEID 400-no-invented-id -> POST /api/v1/budget/providers/reserve-tokens
  -> test_fxfakeid_reserve_tokens_missing_ids_400_no_row_served
- FXFAKEID 400-no-invented-id -> GET /api/v1/teststage/settings/defaults
  -> test_fxfakeid_settings_defaults_missing_project_400_served
"""
import copy
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import fastapi.testclient  # noqa: E402

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.budget import telemetry as _telemetry  # noqa: E402
from agent_si.budget import routes as _routes  # noqa: E402

APP_TOKEN = "fxfakeid-app-token"
HEADERS = {"x-actor": "fxfakeid-probe", "x-ui-session-token": APP_TOKEN}

OLD_LITERAL = "2026-10-27T00:00:00Z"
RESERVATION_TTL_SECONDS = 86400


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


def _utcnow_z():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@pytest.fixture()
def _isolated_product_state():
    """Snapshot-restore module-global product stores this file touches."""
    before_snapshots = copy.deepcopy(_telemetry._SNAPSHOT_REGISTRY)
    before_usage = copy.deepcopy(_telemetry._USAGE_REGISTRY)
    before_leftover = copy.deepcopy(_routes._K04N4_LEFTOVER)
    try:
        yield
    finally:
        _telemetry._SNAPSHOT_REGISTRY.clear()
        _telemetry._SNAPSHOT_REGISTRY.update(before_snapshots)
        _telemetry._USAGE_REGISTRY.clear()
        _telemetry._USAGE_REGISTRY.update(before_usage)
        _routes._K04N4_LEFTOVER.clear()
        _routes._K04N4_LEFTOVER.update(before_leftover)


# FXFAKEID reservation-clock: a served reservation carries the real clock,
# never the old fixed literal.
def test_fxfakeid_reserve_tokens_uses_real_clock_served(
        tmp_path, _isolated_product_state):
    client, _app = _client(tmp_path)
    before = _utcnow_z()
    resp = client.post(
        "/api/v1/budget/providers/reserve-tokens",
        json={"project_id": "fxfakeid-clock", "task_id": "fxfakeid-t1",
              "run_id": "fxfakeid-r1",
              "reservation_id": "fxfakeid-res-1",
              "estimated_amount": "2.50", "currency": "USD",
              "hard_limit": "10.00"},
        headers=HEADERS)
    after = _utcnow_z()
    assert resp.status_code == 200, resp.text
    from agent_si.budget.gate import BudgetGate
    fresh = BudgetGate(store_dir=_budget_dir(tmp_path))
    res = fresh.get_reservation("fxfakeid-res-1")
    assert res.expires_at != OLD_LITERAL, res.to_dict()
    assert before <= res.reserved_at <= after, res.to_dict()
    reserved = datetime.fromisoformat(res.reserved_at.replace("Z", "+00:00"))
    expires = datetime.fromisoformat(res.expires_at.replace("Z", "+00:00"))
    assert expires - reserved == timedelta(seconds=RESERVATION_TTL_SECONDS), \
        res.to_dict()
    assert res.expires_at > after, res.to_dict()


# FXFAKEID 400-no-invented-id: a POST that needs ids but supplies none
# answers 400 with a coded body and writes no row.
def test_fxfakeid_reserve_tokens_missing_ids_400_no_row_served(
        tmp_path, _isolated_product_state):
    client, _app = _client(tmp_path)
    resp = client.post(
        "/api/v1/budget/providers/reserve-tokens",
        json={"project_id": "fxfakeid-noids", "estimated_amount": "1.00",
              "currency": "USD", "hard_limit": "10.00"},
        headers=HEADERS)
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert isinstance(body.get("code"), str) and body["code"], body
    assert body["code"] == body["code"].upper(), body
    assert "_" in body["code"], body
    from agent_si.budget.gate import BudgetGate
    fresh = BudgetGate(store_dir=_budget_dir(tmp_path))
    try:
        fresh.get_state("fxfakeid-noids")
    except (KeyError, LookupError):
        pass
    else:
        raise AssertionError(
            "refused POST must not configure project state")


# FXFAKEID 400-no-invented-id (query lane): settings/defaults with no
# project_id answers 400 instead of inventing the global default.
def test_fxfakeid_settings_defaults_missing_project_400_served(
        tmp_path, _isolated_product_state):
    client, _app = _client(tmp_path)
    resp = client.get("/api/v1/teststage/settings/defaults")
    assert resp.status_code == 400, resp.text
    detail = resp.json().get("detail") or {}
    assert isinstance(detail.get("code"), str) and detail["code"], resp.text
    assert detail["code"] == detail["code"].upper(), resp.text
    assert "_" in detail["code"], resp.text


# FXFAKEID2 served proofs: no invented project/task/run ids on live routes.
#
# Row -> route -> test:
# - FXFAKEID2 get_budget default -> GET /api/v1/budget
#   -> test_fxfakeid2_get_budget_missing_project_400_no_p1_row_served
# - FXFAKEID2 pools query default -> GET /api/v1/routing/roles
#   -> test_fxfakeid2_pools_roles_missing_project_400_served
# - FXFAKEID2 post_decide defaults -> POST /api/v1/routing/decide
#   -> test_fxfakeid2_post_decide_missing_ids_400_no_row_served
# - FXFAKEID2 trial-cap defaults -> POST /api/v1/budget/providers/trial-cap
#   -> test_fxfakeid2_trial_cap_missing_ids_400_no_row_served
# - FXFAKEID2 breach default -> POST /api/v1/budget/providers/breach
#   -> test_fxfakeid2_breach_missing_project_400_no_row_served
# - FXFAKEID2 blocked-terminate default
#   -> POST /api/v1/budget/providers/blocked-terminate
#   -> test_fxfakeid2_blocked_terminate_missing_project_400_no_row_served

# FXFAKEID2 get_budget: a missing project_id answers 400 with the
# BUDGET_PROJECT_ID_REQUIRED code, never the invented "p1" row.
def test_fxfakeid2_get_budget_missing_project_400_no_p1_row_served(
        tmp_path, _isolated_product_state):
    client, _app = _client(tmp_path)
    resp = client.get("/api/v1/budget")
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body.get("code") == "BUDGET_PROJECT_ID_REQUIRED", body
    from agent_si.budget.gate import BudgetGate
    fresh = BudgetGate(store_dir=_budget_dir(tmp_path))
    try:
        fresh.get_state("p1")
    except (KeyError, LookupError):
        pass
    else:
        raise AssertionError(
            "refused GET must not create budget state for 'p1'")


# FXFAKEID2 pools query lane: list_roles with no project_id answers 400
# in the file's existing {"error": ...} style, never the invented "p1".
def test_fxfakeid2_pools_roles_missing_project_400_served(
        tmp_path, _isolated_product_state):
    client, _app = _client(tmp_path)
    resp = client.get("/api/v1/routing/roles")
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert "project_id" in body.get("error", ""), body


# FXFAKEID2 post_decide: a POST that needs ids but supplies none answers
# 400 and persists zero new decision rows.
def test_fxfakeid2_post_decide_missing_ids_400_no_row_served(
        tmp_path, _isolated_product_state):
    client, app = _client(tmp_path)
    store = app.state.k04_ctx.store
    before = len(store._load_table("decisions"))
    resp = client.post(
        "/api/v1/routing/decide",
        json={"role": "worker", "task_class": "coding",
              "candidates": [{"provider": "pa", "model": "pa/a-1"}]},
        headers=HEADERS)
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert "project_id" in body.get("error", ""), body
    assert len(store._load_table("decisions")) == before, (
        "refused POST must not persist a decision row")


# FXFAKEID2 trial-cap: a POST with no ids answers 400 with a named code
# and writes no reservation rows under the old invented ids.
def test_fxfakeid2_trial_cap_missing_ids_400_no_row_served(
        tmp_path, _isolated_product_state):
    client, _app = _client(tmp_path)
    resp = client.post("/api/v1/budget/providers/trial-cap",
                       json={}, headers=HEADERS)
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body.get("code") in ("BUDGET_PROJECT_ID_REQUIRED",
                                "BUDGET_TASK_ID_REQUIRED",
                                "BUDGET_RUN_ID_REQUIRED"), body
    from agent_si.budget.gate import BudgetGate
    fresh = BudgetGate(store_dir=_budget_dir(tmp_path))
    try:
        fresh.get_state("k04n4-p63")
    except (KeyError, LookupError):
        pass
    else:
        raise AssertionError(
            "refused POST must not configure project state")
    for rid in ("k04n4-p63-r1", "k04n4-p63-r2",
                "k04n4-p63-r3", "k04n4-p63-r4"):
        try:
            fresh.get_reservation(rid)
        except (KeyError, LookupError):
            pass
        else:
            raise AssertionError(
                "refused POST must not write reservation %r" % (rid,))


# FXFAKEID2 breach: a POST with task_id+run_id but no project_id answers
# 400 with BUDGET_PROJECT_ID_REQUIRED and writes no invented-id state.
def test_fxfakeid2_breach_missing_project_400_no_row_served(
        tmp_path, _isolated_product_state):
    client, _app = _client(tmp_path)
    resp = client.post("/api/v1/budget/providers/breach",
                       json={"task_id": "fxfakeid2-breach-t1",
                             "run_id": "fxfakeid2-breach-r1"},
                       headers=HEADERS)
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body.get("code") == "BUDGET_PROJECT_ID_REQUIRED", body
    from agent_si.budget.gate import BudgetGate
    fresh = BudgetGate(store_dir=_budget_dir(tmp_path))
    try:
        fresh.get_state("k04f-breach")
    except (KeyError, LookupError):
        pass
    else:
        raise AssertionError(
            "refused POST must not configure project state")


# FXFAKEID2 blocked-terminate: a POST with task_id+run_id but no
# project_id answers 400 with BUDGET_PROJECT_ID_REQUIRED and writes no
# invented-id state or reservation.
def test_fxfakeid2_blocked_terminate_missing_project_400_no_row_served(
        tmp_path, _isolated_product_state):
    client, _app = _client(tmp_path)
    resp = client.post("/api/v1/budget/providers/blocked-terminate",
                       json={"task_id": "fxfakeid2-b34-t1",
                             "run_id": "fxfakeid2-b34-r1"},
                       headers=HEADERS)
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body.get("code") == "BUDGET_PROJECT_ID_REQUIRED", body
    from agent_si.budget.gate import BudgetGate
    fresh = BudgetGate(store_dir=_budget_dir(tmp_path))
    try:
        fresh.get_state("k04f-b34")
    except (KeyError, LookupError):
        pass
    else:
        raise AssertionError(
            "refused POST must not configure project state")
    try:
        fresh.get_reservation("k04f-started-fxfakeid2-b34-r1")
    except (KeyError, LookupError):
        pass
    else:
        raise AssertionError(
            "refused POST must not write a reservation")
