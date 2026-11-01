"""K04BUD1: served budget charging through the real app (MR-07b point fix).

Through the REAL app (create_app + store dir + secret_store memory +
HTTP TestClient) with a fake ONLY at urllib urlopen. No mock providers
in product code. Known KB price -> spent grows by tokens x price and
telemetry cost is MEASURED; unknown price -> spent unchanged and cost
stays UNAVAILABLE (never 0.0 as if free).
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
import pytest  # noqa: E402

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.backend.orchestration import steplimits as _steplimits  # noqa: E402
from agent_si.routing import types as _T  # noqa: E402

APP_TOKEN = "k04bud1-app-token"
BAIT = "FAKE-K04BUD1-0000-zzzz-not-a-real-key"
HEADERS = {"x-actor": "ui-probe", "x-ui-session-token": APP_TOKEN}

CANNED_TEXT = "k04bud1 canned reply"
# Per-1M scale: (4000*0.001 + 6000*0.002)/1e6 = 16/1e6 = 0.000016,
# so the 6dp gate delta survives quantization (tiny 4/6 usage would
# quantize to 0.000000 and prove nothing).
CANNED_USAGE = {"input_tokens": 4000, "output_tokens": 6000}

PRICED_MODEL = "k04bud1-priced-model"
UNKNOWN_MODEL = "gpt-4o-mini"


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
                       json={"name": "p-bud1", "folder_ref": "dock-bud1"},
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
        hash="seed-bud1")
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


def test_known_price_charges_spent_and_measured_cost(tmp_path, monkeypatch):
    _patch_urlopen(monkeypatch)
    from agent_si.model_kb import kb as _kb
    from agent_si.runtime import manager as _mgr
    from agent_si.telemetry import run_store as _store

    seed = _kb.bound_catalog()
    prev_gate = getattr(_mgr, "_BUDGET_GATE", None)
    prev_dir = _store.bound_store_dir()
    row = _kb.make_model_row("openai", PRICED_MODEL, fields={
        "input_token_price": {"value": "0.001", "source": "bind3-test",
                              "retrieved_at": "2026-10-28"},
        "output_token_price": {"value": "0.002", "source": "bind3-test",
                               "retrieved_at": "2026-10-28"},
    })
    catalog = _kb.make_catalog([row] + list(seed.get("models", [])),
                               kb_version=99, updated_at="2026-10-28",
                               change_log=[], sources=[])
    _kb.bind_catalog(catalog)
    try:
        client, app = _make_client(tmp_path)
        pid = _create_project(client)
        _seed_worker(app, pid)
        _connect(client, "openai", PRICED_MODEL, BAIT)
        before = _budget_spent(client, pid)
        chat = client.post("/api/v1/chat/stream",
                           json={"project": pid, "message": "hi priced"},
                           headers=HEADERS)
        assert chat.status_code == 200, chat.text
        assert "NO_PROVIDER_BOUND" not in chat.text, chat.text
        after = _budget_spent(client, pid)
        assert after > before, (before, after)
        # (4000*0.001 + 6000*0.002)/1e6 = 16/1e6 = 0.000016, per-1M prices.
        assert after - before == Decimal("0.000016"), (before, after)
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


def test_unknown_price_leaves_spent_and_unavailable_cost(tmp_path, monkeypatch):
    _patch_urlopen(monkeypatch)
    from agent_si.runtime import manager as _mgr
    from agent_si.telemetry import run_store as _store

    prev_gate = getattr(_mgr, "_BUDGET_GATE", None)
    prev_dir = _store.bound_store_dir()
    try:
        client, app = _make_client(tmp_path)
        pid = _create_project(client)
        _seed_worker(app, pid)
        _connect(client, "openai", UNKNOWN_MODEL, BAIT)
        before = _budget_spent(client, pid)
        chat = client.post("/api/v1/chat/stream",
                           json={"project": pid, "message": "hi unknown"},
                           headers=HEADERS)
        assert chat.status_code == 200, chat.text
        assert "NO_PROVIDER_BOUND" not in chat.text, chat.text
        after = _budget_spent(client, pid)
        assert after == before, (before, after)
        costs = _cost_rows(app)
        assert costs, "no cost rows recorded"
        assert any(r.get("state") == "UNAVAILABLE" for r in costs), costs
        for row in costs:
            if row.get("state") == "UNAVAILABLE":
                assert row.get("value") is None, row
                assert row.get("value") != 0.0, row
    finally:
        try:
            _mgr.set_budget_gate(prev_gate)
        except Exception:
            pass
        try:
            _store.bind_store_dir(prev_dir)
        except Exception:
            pass


# Row proofs BP04-67 / 168 / 219 (adapters-owned fail-closed usage
# ports; injected transports only, no network). Each probes through the
# frozen facade entry it names; unbind/rebind must fail closed, never
# answer from a stale port.
from agent_si.providers.adapters import facades as _facades


# FAKE-OF: agent_si.providers.adapters usage-probe port (injected bound
# chat transport playing back a usage-carrying reply, no network)
class _ProbeChat:
    def __init__(self):
        self.requests = []

    def __call__(self, request):
        self.requests.append(dict(request))
        return {"usage": {"input_tokens": 10, "output_tokens": 5,
                          "cached_tokens": 2, "reasoning_tokens": 1},
                "raw": {"input_tokens": 10}, "raw_safe": True}


def _bind_default_openai(transport):
    _facades.clear_adapter_transports()
    _facades.clear_provider_bindings()
    _facades.bind_provider(
        "openai", {"secret_id": "s-bp04", "provider_id": "openai"},
        transport, "https://api.example/v1")


def _clear_facades():
    _facades.clear_adapter_transports()
    _facades.clear_provider_bindings()


def test_bp04_67_unbind_drops_default_probe_port():
    """Row BP04-67 via facades.probe_usage: unbound provider fails closed."""
    chat = _ProbeChat()
    _bind_default_openai(chat)
    try:
        cap = _facades.probe_usage("openai/default", "openai", False)
        assert cap["state"] == "VERIFIED", cap
        assert cap["input_tokens"] == 10, cap
        _facades.clear_provider_bindings()
        with pytest.raises(ValueError):
            _facades.probe_usage("openai/default", "openai", False)
    finally:
        _clear_facades()


def test_bp04_168_unbind_drops_bare_probe_port():
    """Row 168 via facades.probe_usage: bare id fails closed after unbind."""
    chat = _ProbeChat()
    _bind_default_openai(chat)
    try:
        bare = _facades.probe_usage("openai", "openai", False)
        assert bare["state"] == "VERIFIED", bare
        assert bare["input_tokens"] == 10, bare
        _facades.clear_provider_bindings()
        with pytest.raises(ValueError):
            _facades.probe_usage("openai", "openai", False)
    finally:
        _clear_facades()


def test_bp04_219_rebind_keeps_manual_probe_port():
    """Row 219 via facades.probe_usage: rebind never drops a manual port."""
    chat = _ProbeChat()
    _bind_default_openai(chat)
    _facades.clear_adapter_transports()
    manual = _ProbeChat()
    _facades.register_adapter_transports("openai", manual)
    _facades.bind_provider(
        "openai", {"secret_id": "s-bp04", "provider_id": "openai"},
        None, "https://api.example/v1")
    try:
        cap = _facades.probe_usage("openai", "openai", False)
        assert cap["state"] == "VERIFIED", cap
        assert cap["input_tokens"] == 10, cap
        assert len(manual.requests) == 1, manual.requests
        assert chat.requests == [], chat.requests
    finally:
        _clear_facades()


# D-SPEND-02: live-scale per-1M charge a hard limit refuses fails loud.
LIVE_SCALE_USAGE = {"input_tokens": 20000000, "output_tokens": 20000000}
# Per-1M arithmetic at owner 0.1/0.2 prices:
# (20000000*0.1 + 20000000*0.2)/1e6 = 6000000/1e6 = 6.000000,
# which exceeds the 5.00 hard limit, so the gate refuses the reserve.


def _ok_live_scale_body():
    return {"choices": [{"message": {"content": CANNED_TEXT},
                         "finish_reason": "stop"}],
            "usage": dict(LIVE_SCALE_USAGE)}


def _patch_urlopen_live_scale(monkeypatch):
    def _fake(request, timeout=None):
        return _FakeResp(_ok_live_scale_body())
    monkeypatch.setattr(_urlreq, "urlopen", _fake)


def test_live_scale_refused_reserve_fails_loud_and_unavailable(
        tmp_path, monkeypatch, caplog):
    """D-SPEND-02: live-scale cost above the hard limit fails loud.

    Per-1M arithmetic at owner 0.1/0.2 prices:
    (20000000*0.1 + 20000000*0.2)/1e6 = 6.000000 > 5.00 hard limit, so
    compare_and_reserve refuses; the served turn keeps spent unchanged,
    logs the spend UNRECORDED reserve-refused warning (never a silent
    0), and the charge marker stays UNAVAILABLE.
    """
    import logging as _logging

    _patch_urlopen_live_scale(monkeypatch)
    from agent_si.model_kb import kb as _kb
    from agent_si.runtime import manager as _mgr
    from agent_si.telemetry import run_store as _store

    seed = _kb.bound_catalog()
    prev_gate = getattr(_mgr, "_BUDGET_GATE", None)
    prev_dir = _store.bound_store_dir()
    row = _kb.make_model_row("openai", PRICED_MODEL, fields={
        "input_token_price": {"value": "0.1", "source": "bind3-test",
                              "retrieved_at": "2026-10-28"},
        "output_token_price": {"value": "0.2", "source": "bind3-test",
                               "retrieved_at": "2026-10-28"},
    })
    catalog = _kb.make_catalog([row] + list(seed.get("models", [])),
                               kb_version=99, updated_at="2026-10-28",
                               change_log=[], sources=[])
    _kb.bind_catalog(catalog)
    try:
        client, app = _make_client(tmp_path)
        pid = _create_project(client)
        _seed_worker(app, pid)
        _connect(client, "openai", PRICED_MODEL, BAIT)
        before = _budget_spent(client, pid)
        caplog.set_level(_logging.WARNING)
        chat = client.post("/api/v1/chat/stream",
                           json={"project": pid,
                                 "message": "hi live scale"},
                           headers=HEADERS)
        assert chat.status_code == 200, chat.text
        assert "NO_PROVIDER_BOUND" not in chat.text, chat.text
        after = _budget_spent(client, pid)
        assert after == before, (before, after)
        refused = [rec for rec in caplog.records
                   if "UNRECORDED" in rec.getMessage()
                   and "reserve refused" in rec.getMessage()]
        assert refused, [rec.getMessage() for rec in caplog.records]
        marker = _mgr._charge_budget_gate(
            pid, "openai", PRICED_MODEL, dict(LIVE_SCALE_USAGE),
            "probe-live-scale")
        assert marker == "UNAVAILABLE", marker
        costs = _cost_rows(app)
        assert costs, "no cost rows recorded"
        for cost_row in costs:
            assert cost_row.get("value") != 0, cost_row
            assert cost_row.get("value") != 0.0, cost_row
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
