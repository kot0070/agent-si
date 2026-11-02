"""FXR2E-CONNECT: wrong key refused at save, never stored (RED-first).

Save turns around: the pasted key is held in memory and checked with
a live GET of the provider /models through the model-list egress; the
value reaches the store only on success. A fake 401 answers 401 with
the refused plain text and no key_ref; the card stays Connect (no
provider row). A failed replace keeps the old working key untouched.
Network failure saves nothing. State after restart stays clean.
"""
import json
import os
import sys
import urllib.error as _urlerror
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

APP_TOKEN = "fxr2e-connect-token"
ACTOR_HEADERS = {"x-actor": "fxr2e-connect", "x-ui-session-token": APP_TOKEN}
PREFIX = "agent_si/provider/"
BAD = "FXR2E-WRONG-KEY-abc-not-a-real-key"
GOOD = "FXR2E-GOOD-KEY-ok-not-a-real-key"

REFUSED = "The provider refused this key. Paste the full key again."
UNREACHABLE = "Could not reach the provider."


def _settings(tmp_path):
    return {"store_dir": str(tmp_path / "appdata"),
            "ui_session_token": APP_TOKEN,
            "secret_store": "memory"}


def _client(tmp_path):
    _steplimits._reset_state()
    app = create_app(_settings(tmp_path))
    return (fastapi.testclient.TestClient(app, raise_server_exceptions=False),
            app)


def _models_ok(request, timeout=None):
    body = json.dumps({"data": [{"id": "gpt-4o"}]}).encode("utf-8")

    class _Resp:
        def read(self):
            return body

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    return _Resp()


def _http_401(request, timeout=None):
    raise _urlerror.HTTPError(
        "https://api.openai.com/v1/models", 401, "Unauthorized", {}, None)


def _net_down(request, timeout=None):
    raise _urlerror.URLError("simulated outage")


def _save(client, key_value, preset="openai"):
    return client.post(
        "/api/v1/providers/keys",
        json={"preset_id": preset, "key_value": key_value},
        headers=ACTOR_HEADERS)


def _providers(client):
    listed = client.get("/api/v1/providers", headers=ACTOR_HEADERS)
    assert listed.status_code == 200, listed.text
    return listed.json()["providers"]


def _leftovers(client):
    resp = client.get("/api/v1/budget/providers/leftover-keys",
                      params={"app_prefix": PREFIX})
    assert resp.status_code == 200, resp.text
    return resp.json()["entries"]


def test_wrong_key_refused_not_stored(tmp_path, monkeypatch):
    """Fake 401 on /models: 401 refused text, no key_ref, nothing stored."""
    monkeypatch.setattr(_urlreq, "urlopen", _http_401)
    client, app = _client(tmp_path)
    resp = _save(client, BAD)
    assert resp.status_code == 401, resp.text
    body = resp.json()
    assert body.get("code") != "CONTEXT_WRONG_CONTRACT_VERSION", body
    assert body.get("code") == "PROVIDER_KEY_REFUSED", body
    assert body.get("message") == REFUSED, body
    assert "key_ref" not in body, body
    assert BAD not in resp.text
    assert _providers(client) == [], "card must stay Connect"
    assert _leftovers(client) == []
    assert "openai" not in app.state.k04_ctx.credential_store


def test_state_after_restart_stays_clean(tmp_path, monkeypatch):
    """Same store dir, fresh app: the refused key stays gone."""
    monkeypatch.setattr(_urlreq, "urlopen", _http_401)
    client, _app = _client(tmp_path)
    refused = _save(client, BAD)
    assert refused.status_code == 401, refused.text
    client2, _app2 = _client(tmp_path)
    assert _providers(client2) == []
    assert _leftovers(client2) == []


def test_failed_replace_keeps_old_working_key(tmp_path, monkeypatch):
    """Good key saved, bad replace refused: the old key still works."""
    monkeypatch.setattr(_urlreq, "urlopen", _models_ok)
    client, app = _client(tmp_path)
    saved = _save(client, GOOD)
    assert saved.status_code == 201, saved.text
    key_ref = saved.json()["key_ref"]
    monkeypatch.setattr(_urlreq, "urlopen", _http_401)
    refused = _save(client, BAD)
    assert refused.status_code == 401, refused.text
    assert refused.json().get("code") == "PROVIDER_KEY_REFUSED"
    store = app.state.k04_ctx.credential_store
    assert store.get_secret("openai") == GOOD, "old key untouched"


def test_network_failure_saves_nothing(tmp_path, monkeypatch):
    """Unreachable provider: 503 unreachable text, card stays Connect."""
    monkeypatch.setattr(_urlreq, "urlopen", _net_down)
    client, app = _client(tmp_path)
    resp = _save(client, BAD)
    assert resp.status_code == 503, resp.text
    body = resp.json()
    assert body.get("message") == UNREACHABLE, body
    assert body.get("code") == "EVIDENCE_PROBE_NETWORK", body
    assert _providers(client) == []
    assert "openai" not in app.state.k04_ctx.credential_store
