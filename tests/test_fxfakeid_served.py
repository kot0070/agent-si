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
