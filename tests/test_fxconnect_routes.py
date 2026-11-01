"""FXCONNECT: the exact UI connect JSON reaches the real handlers.

Through the REAL app (create_app + TestClient + memory secret store) with a
fake ONLY at the network boundary (urllib urlopen for the provider evidence
probe, passive gateway check for local discovery). No real keys, no real
providers, no real network.
"""
import json
import os
import sys
import urllib.request as _urlreq

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import fastapi.testclient  # noqa: E402

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.backend.orchestration import steplimits as _steplimits  # noqa: E402

APP_TOKEN = "fxconnect-app-token"
WRONG_TOKEN = "fxconnect-wrong-token"
BAIT = "FAKE-FXCONNECT-0000-zzzz-not-a-real-key"
HEADERS = {"x-actor": "ui-probe", "x-ui-session-token": APP_TOKEN}
WRONG_HEADERS = {"x-actor": "ui-probe", "x-ui-session-token": WRONG_TOKEN}

CANNED_USAGE = {"choices": [{"message": {"content": "fx canned"},
                             "finish_reason": "stop"}],
                "usage": {"input_tokens": 2, "output_tokens": 3}}


class _FakeResp:
    def __init__(self, payload):
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _patch_network(monkeypatch, calls):
    def _fake_urlopen(request, timeout=None):
        calls.append(getattr(request, "full_url", str(request)))
        return _FakeResp(CANNED_USAGE)

    def _fake_gateway(ref):
        calls.append("gateway:" + str(ref))
        return type("Probe", (), {"reachable": True,
                                  "reason": "fx canned reachable"})()

    monkeypatch.setattr(_urlreq, "urlopen", _fake_urlopen)
    import agent_si.local.bench_runner as _bench
    monkeypatch.setattr(_bench, "passive_gateway_check", _fake_gateway)


def _settings(tmp_path):
    return {"store_dir": str(tmp_path / "appdata"),
            "ui_session_token": APP_TOKEN,
            "secret_store": "memory"}


def _make_client(tmp_path):
    _steplimits._reset_state()
    app = create_app(_settings(tmp_path))
    return fastapi.testclient.TestClient(app, raise_server_exceptions=False)


def test_cloud_keys_connect_list_models_disconnect_roundtrip(tmp_path,
                                                             monkeypatch):
    calls = []
    _patch_network(monkeypatch, calls)
    client = _make_client(tmp_path)
    # Exact UI JSON for the key save: preset id plus key value only.
    saved = client.post("/api/v1/providers/keys",
                        json={"preset_id": "openai", "key_value": BAIT},
                        headers=HEADERS)
    assert saved.status_code == 201, saved.text
    assert BAIT not in saved.text
    key_ref = saved.json()["key_ref"]
    # Exact UI JSON for the connect route, as the handler reads it
    # (provider_routes.connect_provider: preset_id, model, key_ref).
    ui_connect = {"preset_id": "openai", "model": "openai/gpt-4o-mini",
                  "key_ref": key_ref}
    conn = client.post("/api/v1/providers/connect", json=ui_connect,
                       headers=HEADERS)
    assert conn.status_code == 200, conn.text
    assert conn.status_code != 404, conn.text
    assert BAIT not in conn.text
    listed = client.get("/api/v1/providers", headers=HEADERS)
    assert listed.status_code == 200, listed.text
    rows = {r["provider_id"]: r for r in listed.json()["providers"]}
    assert "openai" in rows, rows
    models = client.get("/api/v1/providers/openai/models",
                        headers=HEADERS)
    assert models.status_code == 200, models.text
    assert models.json()["provider_id"] == "openai", models.text
    assert BAIT not in models.text
    disc = client.post("/api/v1/providers/openai/disconnect", json={},
                       headers=HEADERS)
    assert disc.status_code == 200, disc.text
    assert disc.json() == {"removed": True, "provider_id": "openai"}
    assert BAIT not in disc.text


def test_wrong_token_refused_no_key_leak(tmp_path, monkeypatch):
    calls = []
    _patch_network(monkeypatch, calls)
    client = _make_client(tmp_path)
    saved = client.post("/api/v1/providers/keys",
                        json={"preset_id": "openai", "key_value": BAIT},
                        headers=WRONG_HEADERS)
    assert saved.status_code in (401, 403), saved.text
    assert BAIT not in saved.text
    conn = client.post("/api/v1/providers/connect",
                       json={"preset_id": "openai", "model": "openai/gpt-4o-mini",
                             "key_ref": {"secret_id": "openai",
                                         "provider_id": "openai"}},
                       headers=WRONG_HEADERS)
    assert conn.status_code in (401, 403), conn.text
    assert BAIT not in conn.text
    disc = client.post("/api/v1/providers/openai/disconnect", json={},
                       headers=WRONG_HEADERS)
    assert disc.status_code in (401, 403), disc.text


def test_local_connect_models_disconnect_roundtrip(tmp_path, monkeypatch):
    calls = []
    _patch_network(monkeypatch, calls)
    client = _make_client(tmp_path)
    # Exact UI JSON for the local connect route, as the handler reads it
    # (local_connect.connect: runtime_ref; token travels in the header).
    conn = client.post("/api/v1/local/connect",
                       json={"runtime_ref": "http://localhost:11434"},
                       headers=HEADERS)
    assert conn.status_code == 200, conn.text
    assert conn.status_code != 404, conn.text
    models = client.get("/api/v1/local/models", headers=HEADERS)
    assert models.status_code == 200, models.text
    disc = client.post("/api/v1/local/disconnect", json={},
                       headers=HEADERS)
    assert disc.status_code == 200, disc.text
    bad = client.post("/api/v1/local/connect",
                      json={"runtime_ref": "http://localhost:11434"},
                      headers=WRONG_HEADERS)
    assert bad.status_code in (401, 403), bad.text
