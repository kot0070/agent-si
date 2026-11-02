"""FXLEFTOVER2 served rows: leftover-keys reads the real credential store.

Live HTTP through create_app + TestClient on an isolated store dir
(secret store memory only): a key saved through POST /api/v1/providers/keys
(fake value) lists on GET leftover-keys, deletes on POST leftover-delete,
and a key bound to a connected provider refuses delete with 409. No fakes
outside this file, no mocks of product code, loopback TestClient only.
"""
import os
import sys
import urllib.request as _urlreq

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import fastapi.testclient  # noqa: E402

from agent_si.backend import stop_all as _stop  # noqa: E402
from agent_si.backend.app import create_app  # noqa: E402
from agent_si.watcher import journal as _journal  # noqa: E402

TOKEN = "fxleftover2-served-token"
FAKE_VALUE = "fxleftover2-fake-key-value"


class _FakeResp:
    def __init__(self, payload):
        self._raw = payload

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _stub_live(monkeypatch, usage_body):
    """Save preflight sees a models list; the evidence probe sees usage."""

    def _fake(request, timeout=None):
        from urllib.parse import urlparse as _parse

        try:
            path = _parse(getattr(request, "full_url", "")).path
        except Exception:
            path = ""
        if path.rstrip("/").endswith("/models"):
            return _FakeResp(b'{"data": [{"id": "m-fxleftover2"}]}')
        return _FakeResp(usage_body)

    monkeypatch.setattr(_urlreq, "urlopen", _fake)


def _headers():
    return {"x-actor": "ui-fxleftover2", "x-ui-session-token": TOKEN}


def _client(tmp_path):
    _journal.reset_state()
    _stop.reset_state()
    app = create_app(
        {"store_dir": str(tmp_path / "appdata"),
         "secret_store": "memory",
         "ui_session_token": TOKEN})
    return fastapi.testclient.TestClient(app)


def _save_key(client, preset_id):
    resp = client.post(
        "/api/v1/providers/keys",
        json={"preset_id": preset_id, "key_value": FAKE_VALUE},
        headers=_headers())
    assert resp.status_code == 201, resp.text
    key_ref = resp.json()["key_ref"]
    assert key_ref["secret_id"] == preset_id, resp.text
    return key_ref


def _listed_names(client, app_prefix):
    listed = client.get("/api/v1/budget/providers/leftover-keys",
                        params={"app_prefix": app_prefix})
    assert listed.status_code == 200, listed.text
    return listed, [row["name"] for row in listed.json()["entries"]]


def test_fxleftover2_saved_key_listed_then_deleted_over_http(
        tmp_path, monkeypatch):
    """Row 1: a key saved through the keys route lists on leftover-keys
    (names plus dates only, never the value) then deletes."""
    monkeypatch.setenv("AGENT_SI_SECRET_STORE", "memory")
    _stub_live(monkeypatch, b'{"usage": {}}')
    client = _client(tmp_path)
    _save_key(client, "openai")
    listed, names = _listed_names(client, "openai")
    assert "openai" in names, listed.text
    assert FAKE_VALUE not in listed.text
    assert "value" not in listed.text
    for row in listed.json()["entries"]:
        assert set(row.keys()) == {"name", "last_used_at"}, row
    removed = client.post(
        "/api/v1/budget/providers/leftover-delete",
        json={"app_prefix": "openai", "name": "openai",
              "confirmed": True, "session_token": TOKEN},
        headers=_headers())
    assert removed.status_code == 200, removed.text
    assert removed.json().get("removed") is True, removed.text
    _, names = _listed_names(client, "openai")
    assert names == [], names


def test_fxleftover2_connected_key_delete_refused_over_http(
        tmp_path, monkeypatch):
    """Row 2: deleting a key bound to a connected provider refuses
    with 409 LIVE_LINKED and the entry stays listed."""
    monkeypatch.setenv("AGENT_SI_SECRET_STORE", "memory")
    _stub_live(monkeypatch, b'{"choices": [{"message": {"content": "ok"}}],'
                            b'"usage": {"input_tokens": 1, '
                            b'"output_tokens": 1}}')
    client = _client(tmp_path)
    key_ref = _save_key(client, "ollama")
    connected = client.post(
        "/api/v1/providers/connect",
        json={"preset_id": "ollama",
              "model": "fxleftover2-test-model",
              "key_ref": key_ref},
        headers=_headers())
    assert connected.status_code == 200, connected.text
    _, names = _listed_names(client, "ollama")
    assert "ollama" in names, names
    refused = client.post(
        "/api/v1/budget/providers/leftover-delete",
        json={"app_prefix": "ollama", "name": "ollama",
              "confirmed": True, "session_token": TOKEN},
        headers=_headers())
    assert refused.status_code == 409, refused.text
    assert refused.json().get("reason") == "LIVE_LINKED", refused.text
    _, names = _listed_names(client, "ollama")
    assert "ollama" in names, names
