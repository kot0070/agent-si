"""K04BIND3: two evidenced providers plus budget charging (MR-08/09/07).

Through the REAL app (create_app + store dir + secret_store memory +
HTTP TestClient) with a fake ONLY at urllib urlopen. No mock providers
in product code.
"""
import json
import os
import sys
import urllib.request as _urlreq

_HERE = os.path.dirname(os.path.abspath(__file__))
_WS = os.path.dirname(_HERE)
_SRC = os.path.join(_WS, "src")
for _p in (_WS, _SRC):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import fastapi.testclient  # noqa: E402

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.backend.orchestration import steplimits as _steplimits  # noqa: E402
from agent_si.routing import types as _T  # noqa: E402

APP_TOKEN = "k04bind3-app-token"
BAIT_O = "FAKE-K04BIND3-O-0000-zzzz-not-a-real-key"
BAIT_M = "FAKE-K04BIND3-M-1111-yyyy-not-a-real-key"
HEADERS = {"x-actor": "ui-probe", "x-ui-session-token": APP_TOKEN}

CANNED_TEXT = "k04bind3 canned reply"
# Per-1M scale (see bud1): 4000/6000 at 0.001/0.002 -> 0.000016 exact.
CANNED_USAGE = {"input_tokens": 4000, "output_tokens": 6000}

META_MODEL_FULL = "meta/muse-spark-1.3-contributor"
META_MODEL_BARE = "muse-spark-1.3-contributor"
OPENAI_MODEL = "gpt-4o-mini"


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
    # Director-protocol answer shape: the dev engine answers plain chat
    # with one provider call (no parts, no repair); the canned text rides
    # the answer so delta assertions keep reading the same fact.
    return {"choices": [{"message": {"content": json.dumps(
        {"answer": CANNED_TEXT})},
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
                       json={"name": "p-bind3", "folder_ref": "dock-bind3"},
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


def _parse_sse(text):
    events = []
    for line in text.splitlines():
        if line.startswith("data:"):
            events.append(json.loads(line[len("data:"):].strip()))
    return events


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
        hash="seed-bind3")
    ctx.role_table.set_profile(profile)


def _save_chat_model(client, pid, model_id):
    resp = client.put("/api/v1/roles/chat-model",
                      json={"project_id": pid, "model_id": model_id},
                      headers=HEADERS)
    assert resp.status_code == 200, resp.text
    return resp


def test_two_evidenced_saved_model_routes(tmp_path, monkeypatch):
    _patch_urlopen(monkeypatch)
    client, app = _make_client(tmp_path)
    pid = _create_project(client)
    _seed_worker(app, pid)
    _connect(client, "openai", OPENAI_MODEL, BAIT_O)
    _connect(client, "meta", META_MODEL_FULL, BAIT_M)
    listed = client.get("/api/v1/providers", headers=HEADERS)
    rows = {r["provider_id"]: r for r in listed.json()["providers"]}
    assert rows["openai"]["evidenced"] is True, rows
    assert rows["meta"]["evidenced"] is True, rows
    _save_chat_model(client, pid, META_MODEL_FULL)
    chat = client.post("/api/v1/chat/stream",
                       json={"project": pid, "message": "hi saved"},
                       headers=HEADERS)
    assert chat.status_code == 200, chat.text
    assert "NO_PROVIDER_BOUND" not in chat.text, chat.text
    events = _parse_sse(chat.text)
    kinds = [e.get("type") for e in events]
    assert kinds[0] == "start", kinds
    assert kinds[-1] == "done", kinds
    assert any(CANNED_TEXT in str(e.get("text", "")) for e in events
               if e.get("type") == "delta"), events
    decision = getattr(app.state, "chat_routing_decision", None)
    assert isinstance(decision, dict), decision
    assert decision.get("provider_id") == "meta", decision
    assert "saved chat model" in str(decision.get("reason", "")), decision
    assert BAIT_O not in chat.text
    assert BAIT_M not in chat.text


def test_no_saved_model_deterministic_choice(tmp_path, monkeypatch):
    _patch_urlopen(monkeypatch)
    client, app = _make_client(tmp_path)
    pid = _create_project(client)
    _seed_worker(app, pid)
    _connect(client, "openai", OPENAI_MODEL, BAIT_O)
    _connect(client, "meta", META_MODEL_FULL, BAIT_M)
    chat = client.post("/api/v1/chat/stream",
                       json={"project": pid, "message": "hi routed"},
                       headers=HEADERS)
    assert chat.status_code == 200, chat.text
    assert "NO_PROVIDER_BOUND" not in chat.text, chat.text
    decision = getattr(app.state, "chat_routing_decision", None)
    assert isinstance(decision, dict), decision
    reason = str(decision.get("reason", ""))
    assert "routing prefers task fit over alphabet" in reason, decision
    assert "unknown price loses" in reason, decision
    # first-connected (openai) wins over alphabetical (meta first)
    assert decision.get("provider_id") == "openai", decision


def test_chat_models_include_meta(tmp_path, monkeypatch):
    _patch_urlopen(monkeypatch)
    client, app = _make_client(tmp_path)
    _create_project(client)
    _connect(client, "openai", OPENAI_MODEL, BAIT_O)
    _connect(client, "meta", META_MODEL_FULL, BAIT_M)
    resp = client.get("/api/v1/chat/models", headers=HEADERS)
    assert resp.status_code == 200, resp.text
    models = resp.json().get("models", [])
    pairs = [(m.get("provider_id"), m.get("model")) for m in models]
    assert any(p == "meta" and "muse-spark-1.3-contributor" in str(m)
               for p, m in pairs), models
    assert any(p == "openai" for p, m in pairs), models


def _budget_spent(client, pid):
    resp = client.get("/api/v1/budget", params={"project_id": pid},
                      headers=HEADERS)
    assert resp.status_code == 200, resp.text
    budget = resp.json().get("budget", {})
    from decimal import Decimal
    return Decimal(str(budget.get("spent", "0")))


def test_budget_unknown_price_records_unavailable(tmp_path, monkeypatch):
    _patch_urlopen(monkeypatch)
    client, app = _make_client(tmp_path)
    pid = _create_project(client)
    _seed_worker(app, pid)
    _connect(client, "openai", OPENAI_MODEL, BAIT_O)
    before = _budget_spent(client, pid)
    chat = client.post("/api/v1/chat/stream",
                       json={"project": pid, "message": "hi budget unknown"},
                       headers=HEADERS)
    assert chat.status_code == 200, chat.text
    assert "NO_PROVIDER_BOUND" not in chat.text, chat.text
    after = _budget_spent(client, pid)
    assert after == before, (before, after)
    from agent_si.telemetry import run_store as _store
    stored = _store.load_store(
        store_dir=getattr(app.state, "k02r3_store_dir", None))
    costs = [r for r in stored.get("metric_records", [])
             if r.get("metric_name") == "cost"]
    assert costs, stored
    assert any(r.get("state") == "UNAVAILABLE" for r in costs), costs


def test_budget_known_price_charges_spent(tmp_path, monkeypatch):
    _patch_urlopen(monkeypatch)
    from agent_si.model_kb import kb as _kb
    seed = _kb.bound_catalog()
    price_model = "priced-model-bind3"
    row = _kb.make_model_row("openai", price_model, fields={
        "input_token_price": {"value": "0.001", "source": "bind3-test",
                              "retrieved_at": "2026-10-28"},
        "output_token_price": {"value": "0.002", "source": "bind3-test",
                               "retrieved_at": "2026-10-28"},
    })
    catalog = _kb.make_catalog([row] + list(seed.get("models", [])),
                               kb_version=99,
                               updated_at="2026-10-28",
                               change_log=[],
                               sources=[])
    _kb.bind_catalog(catalog)
    try:
        client, app = _make_client(tmp_path)
        pid = _create_project(client)
        _seed_worker(app, pid)
        _connect(client, "openai", price_model, BAIT_O)
        before = _budget_spent(client, pid)
        chat = client.post("/api/v1/chat/stream",
                           json={"project": pid, "message": "hi priced"},
                           headers=HEADERS)
        assert chat.status_code == 200, chat.text
        assert "NO_PROVIDER_BOUND" not in chat.text, chat.text
        after = _budget_spent(client, pid)
        assert after > before, (before, after)
        # 4000 in plus 6000 out at 0.001/0.002 per 1M = 0.000016
        from decimal import Decimal
        assert after - before == Decimal("0.000016"), (before, after)
    finally:
        _kb.bind_catalog(seed)
