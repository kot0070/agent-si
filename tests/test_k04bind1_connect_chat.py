"""K04BIND1: provider connect binds chat (MR-01/02/03).

Through the REAL app (create_app + store dir + secret_store memory +
HTTP TestClient) with a fake ONLY at the provider network transport
(urllib urlopen). No mock providers in product code.
"""
import io
import json
import logging
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

APP_TOKEN = "k04bind1-app-token"
BAIT = "FAKE-K04BIND1-BAIT-0000-zzzz-not-a-real-key"
BAIT2 = "FAKE-K04BIND1-BAIT-1111-yyyy-not-a-real-key"
HEADERS = {"x-actor": "ui-probe", "x-ui-session-token": APP_TOKEN}

CANNED_TEXT = "k04bind1 canned reply"
CANNED_USAGE = {"input_tokens": 3, "output_tokens": 5,
                "cached_tokens": 0, "reasoning_tokens": 0}


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


def _patch_urlopen(monkeypatch, mode):
    def _fake(request, timeout=None):
        if mode["fail"]:
            raise _urlreq.URLError("simulated failure K04BIND1")
        return _FakeResp(_ok_body())
    monkeypatch.setattr(_urlreq, "urlopen", _fake)


def _settings(tmp_path):
    return {"store_dir": str(tmp_path / "appdata"),
            "ui_session_token": APP_TOKEN,
            "secret_store": "memory"}


def _parse_sse(text):
    events = []
    for line in text.splitlines():
        if line.startswith("data:"):
            events.append(json.loads(line[len("data:"):].strip()))
    return events


def _make_client(tmp_path):
    _steplimits._reset_state()
    app = create_app(_settings(tmp_path))
    return fastapi.testclient.TestClient(app, raise_server_exceptions=False), app


def _create_project(client):
    resp = client.post("/api/v1/projects",
                       json={"name": "p-bind1", "folder_ref": "dock-bind1"},
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


def test_connect_evidences_and_chat_answers(tmp_path, monkeypatch, caplog):
    mode = {"fail": False}
    _patch_urlopen(monkeypatch, mode)
    client, app = _make_client(tmp_path)
    pid = _create_project(client)
    with caplog.at_level(logging.INFO):
        resp = client.post("/api/v1/providers/keys",
                           json={"preset_id": "openai", "key_value": BAIT},
                           headers=HEADERS)
    assert resp.status_code == 201, resp.text
    assert BAIT not in resp.text
    key_ref = resp.json()["key_ref"]
    conn = client.post("/api/v1/providers/connect",
                       json={"preset_id": "openai", "model": "m-bind1",
                             "key_ref": key_ref},
                       headers=HEADERS)
    assert conn.status_code == 200, conn.text
    assert BAIT not in conn.text
    assert BAIT not in caplog.text
    listed = client.get("/api/v1/providers", headers=HEADERS)
    assert listed.status_code == 200, listed.text
    rows = {r["provider_id"]: r for r in listed.json()["providers"]}
    assert "openai" in rows, rows
    assert rows["openai"]["evidenced"] is True, rows
    assert BAIT not in listed.text
    chat = client.post("/api/v1/chat/stream",
                       json={"project": pid, "message": "hi bind1"},
                       headers=HEADERS)
    assert chat.status_code == 200, chat.text
    assert BAIT not in chat.text
    events = _parse_sse(chat.text)
    kinds = [e.get("type") for e in events]
    assert "NO_PROVIDER_BOUND" not in chat.text, events
    assert kinds[0] == "start", kinds
    assert kinds[-1] == "done", kinds
    deltas = [e.get("text", "") for e in events if e.get("type") == "delta"]
    assert any(CANNED_TEXT in str(t) for t in deltas), events
    assert BAIT not in json.dumps(events)
    assert BAIT not in str(app.state.k04_ctx.audit_sink.records)


def test_transport_failure_error_and_no_provider(tmp_path, monkeypatch):
    mode = {"fail": False}
    _patch_urlopen(monkeypatch, mode)
    client, app = _make_client(tmp_path)
    pid = _create_project(client)
    resp = client.post("/api/v1/providers/keys",
                       json={"preset_id": "openai", "key_value": BAIT2},
                       headers=HEADERS)
    assert resp.status_code == 201, resp.text
    key_ref = resp.json()["key_ref"]
    mode["fail"] = True
    conn = client.post("/api/v1/providers/connect",
                       json={"preset_id": "openai", "model": "m-bindfail",
                             "key_ref": key_ref},
                       headers=HEADERS)
    assert conn.status_code == 200, conn.text
    assert BAIT2 not in conn.text
    listed = client.get("/api/v1/providers", headers=HEADERS)
    assert listed.status_code == 200, listed.text
    rows = {r["provider_id"]: r for r in listed.json()["providers"]}
    assert "openai" in rows, rows
    assert rows["openai"]["evidenced"] is False, rows
    assert rows["openai"]["health"] == "ERROR", rows
    # KEYECHO1: failure reasons are codes/refs only, never the transport
    # exception text (it may carry key bytes): the simulated message
    # must not surface anywhere.
    assert rows["openai"].get("error") == "provider check failed", rows
    assert "simulated failure K04BIND1" not in listed.text
    assert BAIT2 not in listed.text
    chat = client.post("/api/v1/chat/stream",
                       json={"project": pid, "message": "hi fail"},
                       headers=HEADERS)
    assert chat.status_code == 200, chat.text
    assert "NO_PROVIDER_BOUND" in chat.text, chat.text
    assert "provider check failed" in chat.text, chat.text
    assert "simulated failure K04BIND1" not in chat.text
    assert BAIT2 not in chat.text


def test_restart_persists_and_disconnect_clears(tmp_path, monkeypatch):
    mode = {"fail": False}
    _patch_urlopen(monkeypatch, mode)
    client, app = _make_client(tmp_path)
    pid = _create_project(client)
    resp = client.post("/api/v1/providers/keys",
                       json={"preset_id": "openai", "key_value": BAIT},
                       headers=HEADERS)
    assert resp.status_code == 201, resp.text
    key_ref = resp.json()["key_ref"]
    conn = client.post("/api/v1/providers/connect",
                       json={"preset_id": "openai", "model": "m-persist",
                             "key_ref": key_ref},
                       headers=HEADERS)
    assert conn.status_code == 200, conn.text
    # restart on the same store dir
    _steplimits._reset_state()
    app2 = create_app(_settings(tmp_path))
    client2 = fastapi.testclient.TestClient(app2,
                                            raise_server_exceptions=False)
    listed = client2.get("/api/v1/providers", headers=HEADERS)
    assert listed.status_code == 200, listed.text
    rows = {r["provider_id"]: r for r in listed.json()["providers"]}
    assert "openai" in rows, rows
    assert rows["openai"]["evidenced"] is True, rows
    assert BAIT not in listed.text
    # memory store loses the key on restart; re-save restores it
    # (OS store keeps it, no re-save needed there).
    resave = client2.post("/api/v1/providers/keys",
                          json={"preset_id": "openai", "key_value": BAIT},
                          headers=HEADERS)
    assert resave.status_code == 201, resave.text
    chat = client2.post("/api/v1/chat/stream",
                        json={"project": pid, "message": "hi again"},
                        headers=HEADERS)
    assert chat.status_code == 200, chat.text
    assert "NO_PROVIDER_BOUND" not in chat.text, chat.text
    assert CANNED_TEXT in chat.text, chat.text
    assert BAIT not in chat.text
    disc = client2.post("/api/v1/providers/openai/disconnect", json={},
                        headers=HEADERS)
    assert disc.status_code == 200, disc.text
    chat2 = client2.post("/api/v1/chat/stream",
                         json={"project": pid, "message": "hi after"},
                         headers=HEADERS)
    assert chat2.status_code == 200, chat2.text
    assert "NO_PROVIDER_BOUND" in chat2.text, chat2.text
    assert BAIT not in chat2.text
