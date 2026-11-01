"""FB2B3: Anthropic connect health probe request shape (served).

Through the REAL app (create_app + store dir + secret_store memory +
HTTP TestClient) with a fake ONLY at the network transport (urllib
urlopen). All bait values are fake placeholders, never real keys.

Proves the connect-time evidence probe for the anthropic leg sends the
Anthropic /v1/messages shape (F1): POST {base}/v1/messages with
x-api-key + anthropic-version headers and a
{model, max_tokens, messages} body, so connect evidences instead of
recording "provider answered HTTP 400".

Plus a real-network case (no urlopen fake): with no external hosts the
probe must fail closed (health ERROR, not evidenced).
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
from agent_si.providers.adapters import legs as _legs  # noqa: E402

APP_TOKEN = "fb2b3-app-token"
HEADERS = {"x-actor": "ui-probe", "x-ui-session-token": APP_TOKEN}

# Fake placeholders only, never real keys.
BAIT = "FAKE-FB2B3-ANTHROPIC-0000-not-a-real-key"
BAIT_NET = "FAKE-FB2B3-ANTHROPIC-1111-not-a-real-key"

MODEL = "claude-fb2b3-probe"
CANNED_TEXT = "fb2b3 anthropic canned reply"

# Pinned Anthropic API version (F1): the served shape carries exactly this.
VERSION = "2023-06-01"

BASE_URL = "https://api.anthropic.com"
MESSAGES_URL = BASE_URL + "/v1/messages"


def _anthropic_ok_body():
    return {
        "id": "msg_fb2b3",
        "type": "message",
        "role": "assistant",
        "model": MODEL,
        "content": [{"type": "text", "text": CANNED_TEXT}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 3, "output_tokens": 5},
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


def _shape_error(request, body):
    """Return '' when the request is the exact F1 shape, else why not."""
    if request.full_url != MESSAGES_URL:
        return f"url {request.full_url!r} != {MESSAGES_URL!r}"
    try:
        method = request.get_method()
    except Exception:
        method = ""
    if method != "POST":
        return f"method {method!r} != POST"
    seen = {}
    try:
        for key, value in request.header_items():
            seen[str(key).lower()] = value
    except Exception:
        return "headers unreadable"
    if seen.get("content-type") != "application/json":
        return f"content-type {seen.get('content-type')!r}"
    if seen.get("x-api-key") != BAIT:
        return "x-api-key missing or wrong"
    if "authorization" in seen:
        return "openai-style Authorization header must be absent"
    if seen.get("anthropic-version") != VERSION:
        return (f"anthropic-version {seen.get('anthropic-version')!r} "
                f"!= {VERSION!r}")
    if seen.get("anthropic-version") != _legs.ANTHROPIC_API_VERSION:
        return "anthropic-version not the pinned legs pin"
    if not isinstance(body, dict):
        return "body is not a JSON object"
    if set(body.keys()) != {"model", "max_tokens", "messages"}:
        return f"body keys {sorted(body.keys())!r}"
    if body.get("model") != MODEL:
        return f"model {body.get('model')!r} != {MODEL!r}"
    if (not isinstance(body.get("max_tokens"), int)
            or isinstance(body.get("max_tokens"), bool)):
        return f"max_tokens {body.get('max_tokens')!r} is not an int"
    if body.get("messages") != [{"role": "user", "content": "ping"}]:
        return f"messages {body.get('messages')!r}"
    return ""


def _settings(tmp_path):
    return {"store_dir": str(tmp_path / "appdata"),
            "ui_session_token": APP_TOKEN,
            "secret_store": "memory"}


def _make_client(tmp_path):
    _steplimits._reset_state()
    app = create_app(_settings(tmp_path))
    return (fastapi.testclient.TestClient(app, raise_server_exceptions=False),
            app)


def _create_project(client):
    resp = client.post("/api/v1/projects",
                       json={"name": "p-fb2b3",
                             "folder_ref": "dock-fb2b3"},
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
    raise AssertionError(f"no project id in {body!r}")


def _save_key(client, bait):
    resp = client.post("/api/v1/providers/keys",
                       json={"preset_id": "anthropic", "key_value": bait},
                       headers=HEADERS)
    assert resp.status_code == 201, resp.text
    assert bait not in resp.text
    return resp.json()["key_ref"]


def _rows(client):
    listed = client.get("/api/v1/providers", headers=HEADERS)
    assert listed.status_code == 200, listed.text
    return {r["provider_id"]: r for r in listed.json()["providers"]}


def _evidence(app):
    return [r for r in app.state.k04_ctx.audit_sink.records
            if isinstance(r, dict) and r.get("event") == "provck2-evidence"
            and r.get("provider_id") == "anthropic"]


def test_anthropic_probe_sends_messages_shape(tmp_path, monkeypatch):
    """Served fake asserting the exact F1 shape; connect evidences."""
    captured = {}

    def _fake(request, timeout=None):
        try:
            raw = request.data
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            body = {}
        captured["body"] = body
        problem = _shape_error(request, body)
        if problem:
            raise _urlerror.HTTPError(
                request.full_url
                if hasattr(request, "full_url") else str(
                    getattr(request, "selector", "")),
                400, "Bad Request: " + problem, {}, io.BytesIO(b"{}"))
        return _FakeResp(_anthropic_ok_body())

    monkeypatch.setattr(_urlreq, "urlopen", _fake)
    client, app = _make_client(tmp_path)
    _create_project(client)
    key_ref = _save_key(client, BAIT)
    conn = client.post("/api/v1/providers/connect",
                       json={"preset_id": "anthropic", "model": MODEL,
                             "key_ref": key_ref},
                       headers=HEADERS)
    assert conn.status_code == 200, conn.text
    assert BAIT not in conn.text
    assert captured, "no provider request was made"
    rows = _rows(client)
    assert "anthropic" in rows, rows
    assert rows["anthropic"]["evidenced"] is True, rows
    assert rows["anthropic"]["health"] != "ERROR", rows
    assert BAIT not in json.dumps(rows)
    proof = _evidence(app)
    assert len(proof) == 1, proof
    assert proof[0]["class"] == "ok", proof
    assert proof[0]["code"] == "EVIDENCE_OK", proof
    assert BAIT not in str(app.state.k04_ctx.audit_sink.records)


def test_anthropic_probe_real_network_fails_closed(tmp_path):
    """No urlopen fake (no external hosts): the probe fails closed."""
    client, _app = _make_client(tmp_path)
    _create_project(client)
    key_ref = _save_key(client, BAIT_NET)
    conn = client.post("/api/v1/providers/connect",
                       json={"preset_id": "anthropic",
                             "model": "claude-fb2b3-net",
                             "key_ref": key_ref},
                       headers=HEADERS)
    assert conn.status_code == 200, conn.text
    assert BAIT_NET not in conn.text
    rows = _rows(client)
    assert "anthropic" in rows, rows
    assert rows["anthropic"]["evidenced"] is False, rows
    assert rows["anthropic"]["health"] == "ERROR", rows
    assert BAIT_NET not in json.dumps(rows)
