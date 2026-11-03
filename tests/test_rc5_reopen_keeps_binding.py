"""RC5 reopen: Connected + key + binding survive restarts (RED-first).

Owner laptop: a chat worked, then after reopen NO_PROVIDER_BOUND with
the key gone. Served path with the real store shape (OS credential
store + store-dir connections file): connect, send, rebuild the app
twice (and once with the provider unreachable at boot). The provider
must stay Connected, the key must stay, the chat binding must stay
bound, and sending must work with no reconnect.
"""
import json
import os
import sys
import urllib.request as _urlreq

_HERE = os.path.dirname(os.path.abspath(__file__))
_WS = os.path.dirname(_HERE)
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import fastapi.testclient  # noqa: E402

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.backend.orchestration import steplimits as _steplimits  # noqa: E402

APP_TOKEN = "rc5-reopen-token"
SUFFIX = "TESTR C5REOPEN"
HEADERS = {"x-actor": "ui-rc5", "x-ui-session-token": APP_TOKEN}
BAIT = "FAKE-RC5-REOPEN-0001-not-a-real-key"

USAGE = {"choices": [{"message": {"content": "reopen reply"},
                      "finish_reason": "stop"}],
         "usage": {"input_tokens": 3, "output_tokens": 5}}


class _Resp:
    def __init__(self, payload):
        self._raw = payload

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _online(monkeypatch):
    def _fake(request, timeout=None):
        url = getattr(request, "full_url", "")
        if url.rstrip("/").endswith("/models"):
            return _Resp(json.dumps(
                {"data": [{"id": "gpt-4o"}]}).encode("utf-8"))
        return _Resp(json.dumps(USAGE).encode("utf-8"))

    monkeypatch.setattr(_urlreq, "urlopen", _fake)


def _settings(tmp_path):
    return {"store_dir": str(tmp_path),
            "ui_session_token": APP_TOKEN,
            "secret_label_suffix": SUFFIX}


def _make_client(tmp_path):
    _steplimits._reset_state()
    app = create_app(_settings(tmp_path))
    try:
        from agent_si.providers.registry.os_credential_store import (
            OSCredentialStore)
        assert isinstance(
            app.state.k04_ctx.credential_store, OSCredentialStore)
    except ImportError:
        pass
    return (fastapi.testclient.TestClient(app, raise_server_exceptions=False),
            app)


def _connect(client):
    saved = client.post(
        "/api/v1/providers/keys",
        json={"preset_id": "openai", "key_value": BAIT},
        headers=HEADERS)
    assert saved.status_code == 201, saved.text
    key_ref = saved.json()["key_ref"]
    conn = client.post(
        "/api/v1/providers/connect",
        json={"preset_id": "openai", "model": "gpt-4o",
              "key_ref": key_ref},
        headers=HEADERS)
    assert conn.status_code == 200, conn.text
    return key_ref


def _providers(client):
    resp = client.get("/api/v1/providers", headers=HEADERS)
    assert resp.status_code == 200, resp.text
    return {r["provider_id"]: r for r in resp.json()["providers"]}


def _create_project(client):
    project = client.post(
        "/api/v1/projects",
        json={"name": "rc5-reopen", "folder_ref": "dock-rc5"},
        headers=HEADERS)
    assert project.status_code == 200, project.text
    body = project.json()
    proj = body.get("project") if isinstance(body, dict) else None
    if isinstance(proj, dict):
        pid = str(proj.get("project_id") or proj.get("id") or "")
    else:
        pid = ""
    assert pid, body
    return pid


def _send_to(client, project_id):
    from agent_si.backend.orchestration import steplimits as _limits

    outcome = _limits.apply_steplimit_config_change({
        "project_id": project_id,
        "authority": "rc5-reopen-test",
        "reason": "configure test project limits for reopen chat",
        "task_max_steps": 10,
        "chat_max_steps": 10,
    })
    assert outcome.applied, outcome.reason
    resp = client.post(
        "/api/v1/chat/stream",
        json={"project": project_id, "message": "hi again"},
        headers=HEADERS)
    assert resp.status_code == 200, resp.text
    return resp.text


def _cleanup(client):
    try:
        store = client.app.state.k04_ctx.credential_store
        for sid in ("openai",):
            try:
                if store.has(sid):
                    store.delete(sid)
            except Exception:
                pass
    except Exception:
        pass


def test_reopen_keeps_connected_key_and_binding(tmp_path, monkeypatch):
    """Connect, send, rebuild twice: still Connected, send works."""
    # S4: asserts the real OS default, so it opts out of the
    # conftest memory default for this test only.
    monkeypatch.delenv("AGENT_SI_SECRET_STORE", raising=False)
    _online(monkeypatch)
    store_dir = str(tmp_path / "appdata")
    client, _app = _make_client(store_dir)
    try:
        key_ref = _connect(client)
        assert _providers(client)["openai"]["evidenced"] is True
        project_id = _create_project(client)
        first = _send_to(client, project_id)
        assert "NO_PROVIDER_BOUND" not in first, first
        assert '"type": "done"' in first or '"done"' in first, first
        for _round in range(2):
            # Reopen: rebuild the app on the SAME appdata dir and talk
            # to the EXISTING project (the persisted folder guard
            # PROJECT_FOLDER_IN_USE correctly refuses a re-create).
            client2, _app2 = _make_client(store_dir)
            rows = _providers(client2)
            assert "openai" in rows, rows
            assert rows["openai"]["evidenced"] is True, rows
            again = _send_to(client2, project_id)
            assert "NO_PROVIDER_BOUND" not in again, again
            assert '"type": "done"' in again or '"done"' in again, again
        import glob as _glob

        logged = ""
        for _path in _glob.glob(os.path.join(
                store_dir, "logs", "agent-si*.log")):
            with open(_path, encoding="utf-8") as _fh:
                logged += _fh.read()
        assert "providers=openai" in logged, logged[-2000:]
        gone = client.post("/api/v1/providers/openai/disconnect", json={},
                           headers=HEADERS)
        assert gone.status_code == 200, gone.text
        assert "openai" not in _providers(client)
        listed = client.get(
            "/api/v1/budget/providers/leftover-keys",
            params={"app_prefix": "agent_si/provider/"})
        assert listed.status_code == 200, listed.text
    finally:
        _cleanup(client)


def test_offline_boot_keeps_binding(tmp_path, monkeypatch):
    """Provider unreachable at boot: binding kept, no reconnect needed."""
    # S4: asserts the real OS default, so it opts out of the
    # conftest memory default for this test only.
    monkeypatch.delenv("AGENT_SI_SECRET_STORE", raising=False)
    _online(monkeypatch)
    store_dir = str(tmp_path / "appdata-off")
    client, _app = _make_client(store_dir)
    try:
        _connect(client)
        assert "openai" in _providers(client)

        def _down(request, timeout=None):
            raise _urlreq.URLError("simulated offline boot")

        monkeypatch.setattr(_urlreq, "urlopen", _down)
        cold, _cold_app = _make_client(store_dir)
        try:
            rows = _providers(cold)
            assert "openai" in rows, rows
        finally:
            _cleanup(cold)
    finally:
        _cleanup(client)
