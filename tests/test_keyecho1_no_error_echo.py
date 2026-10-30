"""KEYECHO1: connect error paths never echo credential-shaped material.

D-RUN2-01: POST /api/v1/providers/connect `error` carried credential-shaped
material. Root cause: the evidence probe interpolates transport exception
text into the stored failure reason, and urllib's "Invalid header value"
error formats the rejected Authorization header value (i.e. the key) into
that text; the old substring scrub could not match the repr-escaped form.
Fix: failure reasons are codes/refs only, zero credential bytes; a stale
free-text reason restored from disk is dropped, never re-surfaced.

Through the REAL app (create_app + store dir + secret_store memory +
HTTP TestClient) with a fake ONLY at the network transport (urlopen).
All bait values are fake placeholders, never real keys.
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

APP_TOKEN = "keyecho1-app-token"
HEADERS = {"x-actor": "ui-probe", "x-ui-session-token": APP_TOKEN}

# Fake placeholders only. BAIT_NL carries an embedded newline (illegal in
# an HTTP header value) to trigger the exact "Invalid header value" path.
BAIT_NL = "FAKE-KEYECHO1-BAIT-1001-not-a-real-key\nFAKE-KEYECHO1-TAIL"
CORE_NL = "FAKE-KEYECHO1-BAIT-1001-not-a-real-key"
BAIT_MSG = "FAKE-KEYECHO1-BAIT-2002-not-a-real-key"
BAIT_STALE = "FAKE-KEYECHO1-BAIT-3003-not-a-real-key"


def _settings(tmp_path):
    return {"store_dir": str(tmp_path / "appdata"),
            "ui_session_token": APP_TOKEN,
            "secret_store": "memory"}


def _no_network(request, timeout=None):
    raise AssertionError("urlopen must not fire for an illegal header")


def _make_client(tmp_path):
    _steplimits._reset_state()
    app = create_app(_settings(tmp_path))
    return (fastapi.testclient.TestClient(app, raise_server_exceptions=False),
            app)


def _create_project(client):
    resp = client.post("/api/v1/projects",
                       json={"name": "p-keyecho1",
                             "folder_ref": "dock-keyecho1"},
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


def _connections_text(tmp_path):
    path = os.path.join(str(tmp_path / "appdata"),
                        "provider_connections.json")
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def test_invalid_header_bait_never_echoed(tmp_path, monkeypatch):
    monkeypatch.setattr(_urlreq, "urlopen", _no_network)
    client, app = _make_client(tmp_path)
    pid = _create_project(client)
    resp = client.post("/api/v1/providers/keys",
                       json={"preset_id": "openai", "key_value": BAIT_NL},
                       headers=HEADERS)
    assert resp.status_code == 201, resp.text
    assert CORE_NL not in resp.text
    key_ref = resp.json()["key_ref"]
    conn = client.post("/api/v1/providers/connect",
                       json={"preset_id": "openai", "model": "m-echo1",
                             "key_ref": key_ref},
                       headers=HEADERS)
    assert conn.status_code == 200, conn.text
    assert CORE_NL not in conn.text
    prov = (conn.json() or {}).get("provider", {})
    assert prov.get("provider_id") == "openai", conn.text
    listed = client.get("/api/v1/providers", headers=HEADERS)
    assert listed.status_code == 200, listed.text
    rows = {r["provider_id"]: r for r in listed.json()["providers"]}
    assert "openai" in rows, rows
    assert rows["openai"]["health"] == "ERROR", rows
    assert rows["openai"].get("error") == "provider check failed", rows
    assert CORE_NL not in listed.text
    chat = client.post("/api/v1/chat/stream",
                       json={"project": pid, "message": "hi echo1"},
                       headers=HEADERS)
    assert chat.status_code == 200, chat.text
    assert "NO_PROVIDER_BOUND" in chat.text, chat.text
    assert CORE_NL not in chat.text
    assert CORE_NL not in _connections_text(tmp_path)
    assert CORE_NL not in str(app.state.k04_ctx.audit_sink.records)


def test_transport_exception_text_never_echoed(tmp_path, monkeypatch):
    def _fail(request, timeout=None):
        raise _urlreq.URLError(
            "simulated outage carrying %s inside" % BAIT_MSG)
    monkeypatch.setattr(_urlreq, "urlopen", _fail)
    client, app = _make_client(tmp_path)
    pid = _create_project(client)
    resp = client.post("/api/v1/providers/keys",
                       json={"preset_id": "openai", "key_value": BAIT_MSG},
                       headers=HEADERS)
    assert resp.status_code == 201, resp.text
    key_ref = resp.json()["key_ref"]
    conn = client.post("/api/v1/providers/connect",
                       json={"preset_id": "openai", "model": "m-echo2",
                             "key_ref": key_ref},
                       headers=HEADERS)
    assert conn.status_code == 200, conn.text
    assert BAIT_MSG not in conn.text
    assert (conn.json().get("error") == "provider check failed"
            or "error" not in conn.json()), conn.text
    listed = client.get("/api/v1/providers", headers=HEADERS)
    assert listed.status_code == 200, listed.text
    rows = {r["provider_id"]: r for r in listed.json()["providers"]}
    assert rows["openai"].get("error") == "provider check failed", rows
    assert BAIT_MSG not in listed.text
    assert "simulated outage" not in listed.text
    chat = client.post("/api/v1/chat/stream",
                       json={"project": pid, "message": "hi echo2"},
                       headers=HEADERS)
    assert chat.status_code == 200, chat.text
    assert BAIT_MSG not in chat.text
    assert "simulated outage" not in chat.text
    assert BAIT_MSG not in _connections_text(tmp_path)
    assert BAIT_MSG not in str(app.state.k04_ctx.audit_sink.records)


def test_stale_free_text_error_not_restored(tmp_path):
    store_dir = str(tmp_path / "appdata")
    os.makedirs(store_dir, exist_ok=True)
    stale = ("Invalid header value b'Bearer %s'" % BAIT_STALE)
    with open(os.path.join(store_dir, "provider_connections.json"),
              "w", encoding="utf-8") as fh:
        json.dump([{
            "provider_id": "openai",
            "model": "m-stale",
            "instance_id": "default",
            "type": "openai_compatible",
            "base_url": "http://127.0.0.1:9",
            "key_ref": {"secret_id": "openai",
                        "provider_id": "openai"},
            "evidence_ref": None,
            "health": "ERROR",
            "error": stale,
            "mock": False,
        }], fh)
    client, _app = _make_client(tmp_path)
    listed = client.get("/api/v1/providers", headers=HEADERS)
    assert listed.status_code == 200, listed.text
    assert BAIT_STALE not in listed.text
    assert stale not in listed.text
