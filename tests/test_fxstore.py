"""FXSTORE: secret store isolation (HD2 lane).

Through the REAL app (create_app + store dir + HTTP TestClient), fakes
only at the provider network transport (urllib urlopen) and at the OS
stack spy. Proves:
- AGENT_SI_SECRET_STORE=memory selects the memory stack (os_stack never
  runs, even when it would raise);
- explicit settings beat the env switch; env beats the default;
- a saved key dies with the app object (memory): recreate -> key gone,
  providers list empty, chat names the missing key;
- env unset keeps the OS default (os_stack called).
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
from agent_si.providers.registry import facades as _facades  # noqa: E402

APP_TOKEN = "fxstore-app-token"
BAIT = "FAKE-FXSTORE-BAIT-0000-zzzz-not-a-real-key"
HEADERS = {"x-actor": "ui-probe", "x-ui-session-token": APP_TOKEN}

CANNED_TEXT = "fxstore canned reply"


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
    return {"choices": [{"message": {"content": json.dumps(
        {"answer": CANNED_TEXT})},
                         "finish_reason": "stop"}],
            "usage": {"input_tokens": 1, "output_tokens": 2,
                      "cached_tokens": 0, "reasoning_tokens": 0}}


def _patch_urlopen(monkeypatch):
    def _fake(request, timeout=None):
        return _FakeResp(_ok_body())
    monkeypatch.setattr(_urlreq, "urlopen", _fake)


def _settings(tmp_path):
    return {"store_dir": str(tmp_path / "appdata"),
            "ui_session_token": APP_TOKEN}


def _make_client(settings):
    _steplimits._reset_state()
    app = create_app(settings)
    return fastapi.testclient.TestClient(app, raise_server_exceptions=False), app


def _create_project(client):
    resp = client.post("/api/v1/projects",
                       json={"name": "p-fxstore", "folder_ref": "dock-fxstore"},
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


def _save_and_connect(client, bait=BAIT, model="m-fxstore"):
    resp = client.post("/api/v1/providers/keys",
                       json={"preset_id": "meta", "key_value": bait},
                       headers=HEADERS)
    assert resp.status_code == 201, resp.text
    key_ref = resp.json()["key_ref"]
    conn = client.post("/api/v1/providers/connect",
                       json={"preset_id": "meta", "model": model,
                             "key_ref": key_ref},
                       headers=HEADERS)
    assert conn.status_code == 200, conn.text
    return key_ref


def _parse_sse(text):
    events = []
    for line in text.splitlines():
        if line.startswith("data:"):
            events.append(json.loads(line[len("data:"):].strip()))
    return events


def test_env_memory_selects_memory_stack_even_when_os_stack_raises(
        tmp_path, monkeypatch):
    """AGENT_SI_SECRET_STORE=memory isolates the window (RED first)."""
    def _boom(**kwargs):
        raise OSError("os stack must not run under memory isolation")
    monkeypatch.setattr(_facades, "os_stack", _boom)
    monkeypatch.setenv("AGENT_SI_SECRET_STORE", "memory")
    _patch_urlopen(monkeypatch)
    client, app = _make_client(_settings(tmp_path))
    store = app.state.k04_ctx.credential_store
    assert type(store).__name__ != "OSCredentialStore", type(store)
    _save_and_connect(client)
    assert store.has("meta") is True
    listed = client.get("/api/v1/providers", headers=HEADERS)
    assert listed.status_code == 200, listed.text
    rows = {r["provider_id"]: r for r in listed.json()["providers"]}
    assert "meta" in rows, rows
    assert BAIT not in listed.text
    assert "AGENT_SI_SECRET_STORE" not in listed.text


def test_env_memory_case_insensitive_and_trimmed(tmp_path, monkeypatch):
    def _boom(**kwargs):
        raise OSError("os stack must not run under memory isolation")
    monkeypatch.setattr(_facades, "os_stack", _boom)
    monkeypatch.setenv("AGENT_SI_SECRET_STORE", " Memory ")
    client, app = _make_client(_settings(tmp_path))
    assert type(app.state.k04_ctx.credential_store).__name__ != \
        "OSCredentialStore"
    assert client.get("/api/v1/providers",
                      headers=HEADERS).status_code == 200


def test_explicit_settings_win_over_env(tmp_path, monkeypatch):
    """secret_store=os in settings beats AGENT_SI_SECRET_STORE=memory."""
    calls = []
    real_os_stack = _facades.os_stack

    def _spy(**kwargs):
        calls.append(kwargs)
        return real_os_stack(**kwargs)
    monkeypatch.setattr(_facades, "os_stack", _spy)
    monkeypatch.setenv("AGENT_SI_SECRET_STORE", "memory")
    settings = _settings(tmp_path)
    settings["secret_store"] = "os"
    _make_client(settings)
    assert calls, "explicit secret_store=os must still call os_stack"


def test_env_unset_keeps_os_default(tmp_path, monkeypatch):
    """No env switch: the OS stack stays the default (RED guard)."""
    calls = []
    real_os_stack = _facades.os_stack

    def _spy(**kwargs):
        calls.append(kwargs)
        return real_os_stack(**kwargs)
    monkeypatch.setattr(_facades, "os_stack", _spy)
    monkeypatch.delenv("AGENT_SI_SECRET_STORE", raising=False)
    _make_client(_settings(tmp_path))
    assert calls, "unset env must keep the OS default stack"


def test_save_recreate_app_key_gone_list_empty_chat_names_key(
        tmp_path, monkeypatch):
    """Memory isolation: keys die with the window (RED first)."""
    def _boom(**kwargs):
        raise OSError("os stack must not run under memory isolation")
    monkeypatch.setattr(_facades, "os_stack", _boom)
    monkeypatch.setenv("AGENT_SI_SECRET_STORE", "memory")
    _patch_urlopen(monkeypatch)
    client, app = _make_client(_settings(tmp_path))
    pid = _create_project(client)
    _save_and_connect(client)
    # recreate the app on the same store dir: the key is gone
    client2, app2 = _make_client(_settings(tmp_path))
    assert app2.state.k04_ctx.credential_store.has("meta") is False
    listed = client2.get("/api/v1/providers", headers=HEADERS)
    assert listed.status_code == 200, listed.text
    rows = {r["provider_id"]: r for r in listed.json()["providers"]}
    assert "meta" not in rows, rows
    chat = client2.post("/api/v1/chat/stream",
                        json={"project": pid, "message": "hi after restart"},
                        headers=HEADERS)
    assert chat.status_code == 200, chat.text
    assert "SECRET_VALUE_MISSING" in chat.text, chat.text
    assert "secret value unavailable" not in chat.text, chat.text
    assert BAIT not in chat.text


def test_missing_key_says_plain_line_not_engine_text(
        tmp_path, monkeypatch):
    """Disconnect-then-send: chat names the key, never engine jargon."""
    def _boom(**kwargs):
        raise OSError("os stack must not run under memory isolation")
    monkeypatch.setattr(_facades, "os_stack", _boom)
    monkeypatch.setenv("AGENT_SI_SECRET_STORE", "memory")
    _patch_urlopen(monkeypatch)
    client, app = _make_client(_settings(tmp_path))
    pid = _create_project(client)
    _save_and_connect(client)
    # drop the value behind the registry's back (sibling-window case)
    app.state.k04_ctx.credential_store.delete("meta")
    listed = client.get("/api/v1/providers", headers=HEADERS)
    assert listed.status_code == 200, listed.text
    rows = {r["provider_id"]: r for r in listed.json()["providers"]}
    assert "meta" not in rows, rows
    chat = client.post("/api/v1/chat/stream",
                       json={"project": pid, "message": "hi missing"},
                       headers=HEADERS)
    assert chat.status_code == 200, chat.text
    events = _parse_sse(chat.text)
    errors = [e for e in events if e.get("type") == "error"]
    assert errors, events
    assert errors[0].get("code") == "SECRET_VALUE_MISSING", events
    assert "AdapterConfigError" not in chat.text, chat.text
    assert "bind the credential store value port" not in chat.text, \
        chat.text
    assert BAIT not in chat.text
