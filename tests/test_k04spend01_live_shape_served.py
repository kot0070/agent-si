"""K04SPEND01: live-shape spend firewall + priced charge via updater route.

Through the REAL app (create_app + store dir + secret_store memory +
HTTP TestClient) with a fake ONLY at urllib urlopen (REAL-shaped
OpenAI-compatible gateway replies). Priced row arrives via the product
updater route (fetch_source + propose_update + apply_proposal +
kb.bind_catalog), then persists to the KB store and rebinds at startup.

Case A (firewall): gateway usage {} -> spend unchanged + cost UNAVAILABLE
(never 0 as if free, never estimated).
Case B (priced): gateway usage {4,6} + bound priced meta row
(0.1/0.2 USD) -> spend +1.6 + cost MEASURED; second app from the same
store dir rebinds the persisted catalog at startup and charges again.
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
from agent_si.model_kb import updater as _updater  # noqa: E402
from agent_si.routing import types as _T  # noqa: E402

APP_TOKEN = "k04spend01-app-token"
BAIT = "FAKE-K04SPEND01-0000-zzzz-not-a-real-key"
HEADERS = {"x-actor": "ui-probe", "x-ui-session-token": APP_TOKEN}

CANNED_TEXT = "k04spend01 canned reply"
USAGE_PRESENT = {"input_tokens": 4, "output_tokens": 6}
USAGE_ABSENT = {}

META_PROVIDER = "meta"
META_MODEL = "muse-spark-1.3-contributor"
META_SOURCE_URL = "https://dev.meta.ai/docs/pricing-rate-limits"
META_RETRIEVED_AT = "2026-10-11"
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


def _patch_urlopen(monkeypatch, usage):
    def _fake(request, timeout=None):
        return _FakeResp({"choices": [{"message": {"content": CANNED_TEXT},
                                       "finish_reason": "stop"}],
                          "usage": dict(usage)})
    monkeypatch.setattr(_urlreq, "urlopen", _fake)


def _settings(store_dir):
    return {"store_dir": str(store_dir),
            "ui_session_token": APP_TOKEN,
            "secret_store": "memory"}


def _make_client(store_dir):
    _steplimits._reset_state()
    app = create_app(_settings(store_dir))
    return fastapi.testclient.TestClient(app, raise_server_exceptions=False), app


def _bind_priced_meta_via_updater(seed):
    kept = [row for row in seed.get("models", [])
            if not (isinstance(row, dict)
                    and row.get("provider_id") == META_PROVIDER
                    and row.get("model_id") == META_MODEL)]
    base = _kb.make_catalog(
        [_kb.make_model_row(META_PROVIDER, META_MODEL)] + kept,
        kb_version=int(seed.get("version", {}).get("kb_version", 1)),
        updated_at=seed.get("version", {}).get("updated_at", _kb.UNKNOWN),
        change_log=list(seed.get("version", {}).get("change_log", [])),
        sources=tuple(seed.get("manifest", {}).get("sources", ())))
    fetched_doc = {"models": [{
        "provider_id": META_PROVIDER,
        "model_id": META_MODEL,
        "fields": {"currency": "USD",
                   "input_token_price": 0.1,
                   "output_token_price": 0.2}}]}
    fetched_text = _updater.fetch_source(
        META_SOURCE_URL, lambda url: json.dumps(fetched_doc))
    proposal = _updater.propose_update(
        base, META_SOURCE_URL, fetched_text, META_RETRIEVED_AT)
    assert _updater.validate_proposal(base, proposal) == []
    assert len(proposal["changes"]) == 3, proposal
    result = _updater.apply_proposal(base, proposal, user_confirmed=True)
    assert result["applied"] is True
    return _kb.bind_catalog(result["catalog"])


def _create_project(client):
    resp = client.post("/api/v1/projects",
                       json={"name": "p-spend01", "folder_ref": "dock-sp01"},
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


def _connect(client, preset_id, model):
    resp = client.post("/api/v1/providers/keys",
                       json={"preset_id": preset_id, "key_value": BAIT},
                       headers=HEADERS)
    assert resp.status_code == 201, resp.text
    key_ref = resp.json()["key_ref"]
    conn = client.post("/api/v1/providers/connect",
                       json={"preset_id": preset_id, "model": model,
                             "key_ref": key_ref},
                       headers=HEADERS)
    assert conn.status_code == 200, conn.text


def _seed_worker(app, pid):
    ctx = app.state.k04_ctx
    profile = _T.RoleModelProfile(
        role="worker", project_id=pid, mode="AUTO",
        provider=None, model=None, binding="DEFAULT", version=1,
        hash="seed-spend01")
    ctx.role_table.set_profile(profile)


def _budget_spent(client, pid):
    resp = client.get("/api/v1/budget", params={"project_id": pid},
                      headers=HEADERS)
    assert resp.status_code == 200, resp.text
    return Decimal(str(resp.json().get("budget", {}).get("spent", "0")))


def _cost_rows(app):
    from agent_si.telemetry import run_store as _store
    stored = _store.load_store(
        store_dir=getattr(app.state, "k02r3_store_dir", None))
    return [r for r in stored.get("metric_records", [])
            if r.get("metric_name") == "cost"]


def _reset_kb_global(seed, prev_gate, prev_dir, prev_persist):
    _kb.bind_catalog(seed)
    try:
        from agent_si.runtime import manager as _mgr
        _mgr.set_budget_gate(prev_gate)
    except Exception:
        pass
    try:
        from agent_si.telemetry import run_store as _store
        _store.bind_store_dir(prev_dir)
    except Exception:
        pass
    try:
        _kb.set_persist_dir(prev_persist)
    except Exception:
        pass


def test_usage_absent_firewall_spend_zero_and_unavailable(tmp_path, monkeypatch):
    from agent_si.runtime import manager as _mgr
    from agent_si.telemetry import run_store as _store
    seed = _kb.bound_catalog()
    prev_gate = getattr(_mgr, "_BUDGET_GATE", None)
    prev_dir = _store.bound_store_dir()
    prev_persist = getattr(_kb, "_PERSIST_DIR", None)
    _bind_priced_meta_via_updater(seed)
    try:
        store_dir = tmp_path / "appdata-absent"
        _patch_urlopen(monkeypatch, USAGE_PRESENT)
        client, app = _make_client(store_dir)
        pid = _create_project(client)
        _seed_worker(app, pid)
        _connect(client, "meta", META_MODEL)
        _patch_urlopen(monkeypatch, USAGE_ABSENT)
        before = _budget_spent(client, pid)
        chat = client.post("/api/v1/chat/stream",
                           json={"project": pid, "message": "hi firewall"},
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
    finally:
        _reset_kb_global(seed, prev_gate, prev_dir, prev_persist)


def test_usage_present_priced_charges_and_persists(tmp_path, monkeypatch):
    _patch_urlopen(monkeypatch, USAGE_PRESENT)
    from agent_si.runtime import manager as _mgr
    from agent_si.telemetry import run_store as _store
    seed = _kb.bound_catalog()
    prev_gate = getattr(_mgr, "_BUDGET_GATE", None)
    prev_dir = _store.bound_store_dir()
    prev_persist = getattr(_kb, "_PERSIST_DIR", None)
    _bind_priced_meta_via_updater(seed)
    try:
        store_dir = tmp_path / "appdata-priced"
        client, app = _make_client(store_dir)
        pid = _create_project(client)
        _seed_worker(app, pid)
        _connect(client, "meta", META_MODEL)
        before = _budget_spent(client, pid)
        chat = client.post("/api/v1/chat/stream",
                           json={"project": pid, "message": "hi priced"},
                           headers=HEADERS)
        assert chat.status_code == 200, chat.text
        assert "NO_PROVIDER_BOUND" not in chat.text, chat.text
        after = _budget_spent(client, pid)
        assert after - before == EXPECTED_DELTA, (before, after)
        costs = _cost_rows(app)
        assert costs, "no cost rows recorded"
        measured = [r for r in costs if r.get("state") == "MEASURED"]
        assert measured, costs
        assert any(float(r.get("value") or 0) > 0 for r in measured), costs
        persisted = _kb.persist_path()
        assert persisted and os.path.isfile(persisted), persisted
        # Startup rebind: drop the in-memory priced catalog, rebuild the
        # app from the same store dir, the priced row must come back.
        _kb.bind_catalog(seed)
        _kb.set_persist_dir(None)
        client2, app2 = _make_client(store_dir)
        rows = [r for r in _kb.bound_catalog().get("models", [])
                if r.get("provider_id") == META_PROVIDER
                and r.get("model_id") == META_MODEL]
        assert len(rows) == 1, "startup did not rebind persisted catalog"
        fields = rows[0]["fields"]
        assert fields["input_token_price"]["value"] == 0.1, fields
        assert fields["output_token_price"]["value"] == 0.2, fields
    finally:
        _reset_kb_global(seed, prev_gate, prev_dir, prev_persist)
