"""K04BIND2: OpenAI-compatible evidence probe live shape (MR-05).

Through the REAL app (create_app + store dir + secret_store memory +
HTTP TestClient) with a fake ONLY at urllib urlopen. No mock providers
in product code. No network. No key values in assertions.
"""
import io
import json
import os
import sys
import urllib.error as _urlerror
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

APP_TOKEN = "k04bind2-app-token"
BAIT = "FAKE-K04BIND2-BAIT-0000-zzzz-not-a-real-key"
BAIT2 = "FAKE-K04BIND2-BAIT-1111-yyyy-not-a-real-key"
HEADERS = {"x-actor": "ui-probe", "x-ui-session-token": APP_TOKEN}

CANNED_TEXT = "k04bind2 canned reply"
# Recorded OpenAI-shaped usage (wire names, not METRIC_KEYS).
OPENAI_USAGE = {
    "prompt_tokens": 11,
    "completion_tokens": 7,
    "total_tokens": 18,
    "prompt_tokens_details": {"cached_tokens": 3},
}


class _FakeResp:
    def __init__(self, payload):
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _openai_body():
    # Director-protocol answer shape: one provider call answers the turn.
    return {
        "choices": [{"message": {"content": json.dumps(
            {"answer": CANNED_TEXT})},
                     "finish_reason": "stop"}],
        "usage": dict(OPENAI_USAGE),
    }


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
                       json={"name": "p-bind2", "folder_ref": "dock-bind2"},
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


def test_openai_usage_evidenced_and_chat_answers(tmp_path, monkeypatch):
    captured = []

    def _fake(request, timeout=None):
        try:
            raw = request.data
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            body = {}
        captured.append(body)
        return _FakeResp(_openai_body())

    monkeypatch.setattr(_urlreq, "urlopen", _fake)
    client, app = _make_client(tmp_path)
    pid = _create_project(client)
    resp = client.post("/api/v1/providers/keys",
                       json={"preset_id": "openai", "key_value": BAIT},
                       headers=HEADERS)
    assert resp.status_code == 201, resp.text
    assert BAIT not in resp.text
    key_ref = resp.json()["key_ref"]
    model = "gpt-4o-mini-bind2"
    conn = client.post("/api/v1/providers/connect",
                       json={"preset_id": "openai", "model": model,
                             "key_ref": key_ref},
                       headers=HEADERS)
    assert conn.status_code == 200, conn.text
    assert BAIT not in conn.text
    listed = client.get("/api/v1/providers", headers=HEADERS)
    assert listed.status_code == 200, listed.text
    rows = {r["provider_id"]: r for r in listed.json()["providers"]}
    assert "openai" in rows, rows
    assert rows["openai"]["evidenced"] is True, rows
    assert BAIT not in listed.text
    # Probe request body carries the connected model and one message.
    assert captured, "no provider request was made"
    probe_hits = [b for b in captured
                  if b.get("model") == model
                  and isinstance(b.get("messages"), list)
                  and len(b.get("messages")) == 1]
    assert probe_hits, captured
    first_msg = probe_hits[0]["messages"][0]
    assert first_msg.get("role") == "user", probe_hits[0]
    assert isinstance(first_msg.get("content"), str) and first_msg.get(
        "content"), probe_hits[0]
    chat = client.post("/api/v1/chat/stream",
                       json={"project": pid, "message": "hi bind2"},
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


def test_http400_health_error_keeps_status(tmp_path, monkeypatch):
    captured = []

    def _fake(request, timeout=None):
        try:
            raw = request.data
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            body = {}
        captured.append(body)
        raise _urlerror.HTTPError(
            request.full_url if hasattr(request, "full_url") else str(
                getattr(request, "selector", "")),
            400, "Bad Request", {}, io.BytesIO(b"{}"))

    monkeypatch.setattr(_urlreq, "urlopen", _fake)
    client, app = _make_client(tmp_path)
    _create_project(client)
    resp = client.post("/api/v1/providers/keys",
                       json={"preset_id": "openai", "key_value": BAIT2},
                       headers=HEADERS)
    assert resp.status_code == 201, resp.text
    key_ref = resp.json()["key_ref"]
    model = "gpt-4o-mini-400"
    conn = client.post("/api/v1/providers/connect",
                       json={"preset_id": "openai", "model": model,
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
    assert "400" in str(rows["openai"].get("error", "")), rows
    assert BAIT2 not in listed.text
    assert captured, "no provider request was made"
    probe_hits = [b for b in captured
                  if b.get("model") == model
                  and isinstance(b.get("messages"), list)
                  and len(b.get("messages")) == 1]
    assert probe_hits, captured
