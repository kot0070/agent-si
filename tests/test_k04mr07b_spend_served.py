"""K04MR07B: served spend for the priced meta contributor row.

Through the REAL app (create_app + store dir + secret_store memory +
HTTP TestClient) with a fake ONLY at urllib urlopen. The priced row
comes from the product seed/bind path
(agent_si.model_kb.meta_prices.priced_catalog + kb.bind_catalog):
provider meta / model muse-spark-1.3-contributor, 0.1/0.2 USD sourced at
https://dev.meta.ai/docs/pricing-rate-limits (retrieved 2026-10-11).
Usage {input_tokens:4, output_tokens:6} must charge exactly
4*0.1 + 6*0.2 = 1.6 and leave a MEASURED cost row.
"""
import json
import os
import sys
import urllib.request as _urlreq
from decimal import Decimal

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_WS, "src")
for _p in (_WS, _SRC):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import fastapi.testclient  # noqa: E402

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.backend.orchestration import steplimits as _steplimits  # noqa: E402
from agent_si.model_kb import kb as _kb  # noqa: E402
from agent_si.model_kb import meta_prices as _meta  # noqa: E402
from agent_si.routing import types as _T  # noqa: E402

APP_TOKEN = "k04mr07b-app-token"
BAIT = "FAKE-K04MR07B-0000-zzzz-not-a-real-key"
HEADERS = {"x-actor": "ui-probe", "x-ui-session-token": APP_TOKEN}

CANNED_TEXT = "k04mr07b canned reply"
CANNED_USAGE = {"input_tokens": 4, "output_tokens": 6}

META_MODEL = "muse-spark-1.3-contributor"
EXPECTED_DELTA = Decimal("1.600000")


class _FakeResp:
    def __init__(self, payload):
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _ok_body():
    return {"choices": [{"message": {"content": CANNED_TEXT},
                         "finish_reason": "stop"}],
            "usage": dict(CANNED_USAGE)}


def _patch_urlopen(monkeypatch):
    def _fake(request, timeout=None):
        return _FakeResp(_ok_body())
    monkeypatch.setattr(_urlreq, "urlopen", _fake)


def _settings(tmp_path):
    return {"store_dir": str(tmp_path / "appdata"),
            "ui_session_token": APP_TOKEN,
            "secret_store": "memory"}


def _make_client(tmp_path):
    _steplimits._reset_state()
    app = create_app(_settings(tmp_path))
    return fastapi.testclient.TestClient(app, raise_server_exceptions=False), app


def _create_project(client):
    resp = client.post("/api/v1/projects",
                       json={"name": "p-mr07b", "folder_ref": "dock-mr07b"},
                       headers=HEADERS)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    proj = body.get("project") if isinstance(body, dict) else None
    if isinstance(proj, dict):
        for key in ("project_id", "id", "record_id"):
            if proj.get(key):
                return str(proj.get(key))
    for key in ("project_id", "id"):
        if body.get(key):
            return str(body.get(key))
    raise AssertionError("no project id in %r" % (body,))


def _connect(client, preset_id, model, bait):
    resp = client.post("/api/v1/providers/keys",
                       json={"preset_id": preset_id, "key_value": bait},
                       headers=HEADERS)
    assert resp.status_code == 201, resp.text
    key_ref = resp.json()["key_ref"]
    conn = client.post("/api/v1/providers/connect",
                       json={"preset_id": preset_id, "model": model,
                             "key_ref": key_ref},
                       headers=HEADERS)
    assert conn.status_code == 200, conn.text
    return conn


def _seed_worker(app, pid):
    ctx = app.state.k04_ctx
    profile = _T.RoleModelProfile(
        role="worker", project_id=pid, mode="AUTO",
        provider=None, model=None, binding="DEFAULT", version=1,
        hash="seed-mr07b")
    ctx.role_table.set_profile(profile)


def _budget_spent(client, pid):
    resp = client.get("/api/v1/budget", params={"project_id": pid},
                      headers=HEADERS)
    assert resp.status_code == 200, resp.text
    budget = resp.json().get("budget", {})
    return Decimal(str(budget.get("spent", "0")))


def _cost_rows(app):
    from agent_si.telemetry import run_store as _store

    stored = _store.load_store(
        store_dir=getattr(app.state, "k02r3_store_dir", None))
    return [r for r in stored.get("metric_records", [])
            if r.get("metric_name") == "cost"]


def test_meta_priced_row_charges_spent_and_measured_cost(tmp_path, monkeypatch):
    _patch_urlopen(monkeypatch)
    from agent_si.runtime import manager as _mgr
    from agent_si.telemetry import run_store as _store

    seed = _kb.bound_catalog()
    prev_gate = getattr(_mgr, "_BUDGET_GATE", None)
    prev_dir = _store.bound_store_dir()
    catalog = _meta.priced_catalog(seed)
    rows = [r for r in catalog.get("models", [])
            if r.get("provider_id") == "meta"
            and r.get("model_id") == META_MODEL]
    assert len(rows) == 1, catalog.get("models", [])
    fields = rows[0]["fields"]
    assert fields["input_token_price"]["value"] == 0.1, fields
    assert fields["output_token_price"]["value"] == 0.2, fields
    assert fields["input_token_price"]["source"] == _meta.META_SOURCE_URL
    assert fields["input_token_price"]["retrieved_at"] == "2026-10-11"
    assert fields["currency"]["value"] == "USD"
    _kb.bind_catalog(catalog)
    try:
        client, app = _make_client(tmp_path)
        pid = _create_project(client)
        _seed_worker(app, pid)
        _connect(client, "meta", META_MODEL, BAIT)
        before = _budget_spent(client, pid)
        chat = client.post("/api/v1/chat/stream",
                           json={"project": pid, "message": "hi priced meta"},
                           headers=HEADERS)
        assert chat.status_code == 200, chat.text
        assert "NO_PROVIDER_BOUND" not in chat.text, chat.text
        after = _budget_spent(client, pid)
        assert after > before, (before, after)
        assert after - before == EXPECTED_DELTA, (before, after)
        costs = _cost_rows(app)
        assert costs, "no cost rows recorded"
        measured = [r for r in costs if r.get("state") == "MEASURED"]
        assert measured, costs
        assert any(float(r.get("value") or 0) > 0 for r in measured), costs
    finally:
        _kb.bind_catalog(seed)
        try:
            _mgr.set_budget_gate(prev_gate)
        except Exception:
            pass
        try:
            _store.bind_store_dir(prev_dir)
        except Exception:
            pass
