"""FXMODELID served: real ids connect; Anthropic probe body carries bare id.

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

APP_TOKEN = "fxmodelid-app-token"
WRONG_TOKEN = "fxmodelid-wrong-token"
BAIT = "FAKE-FXMODELID-0000-zzzz-not-a-real-key"
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
        try:
            raw = request.data
        except Exception:
            raw = None
        try:
            body = raw.decode("utf-8") if isinstance(raw, bytes) else ""
        except Exception:
            body = ""
        calls.append({"url": getattr(request, "full_url", str(request)),
                      "body": body})
        return _FakeResp(CANNED_USAGE)

    def _fake_gateway(ref):
        calls.append({"url": "gateway:" + str(ref), "body": ""})
        return type("Probe", (), {"reachable": True,
                                  "reason": "fx canned reachable"}())

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


def _connect(calls, client, preset_id, model):
    saved = client.post("/api/v1/providers/keys",
                        json={"preset_id": preset_id, "key_value": BAIT},
                        headers=HEADERS)
    assert saved.status_code == 201, saved.text
    assert BAIT not in saved.text
    key_ref = saved.json()["key_ref"]
    before = len(calls)
    conn = client.post("/api/v1/providers/connect",
                       json={"preset_id": preset_id, "model": model,
                             "key_ref": key_ref},
                       headers=HEADERS)
    assert conn.status_code == 200, conn.text
    assert conn.status_code != 404, conn.text
    assert BAIT not in conn.text
    return calls[before:]


def _probe_bodies(calls, path_suffix):
    out = []
    for call in calls:
        if not isinstance(call, dict):
            continue
        if call["url"].endswith(path_suffix) and call["body"]:
            out.append(json.loads(call["body"]))
    return out


def test_real_ids_connect_and_anthropic_probe_carries_bare_id(
        tmp_path, monkeypatch):
    calls = []
    _patch_network(monkeypatch, calls)
    client = _make_client(tmp_path)
    anth_calls = _connect(calls, client, "anthropic",
                         "anthropic/claude-haiku-4-5")
    probe_bodies = _probe_bodies(anth_calls, "/v1/messages")
    assert probe_bodies, anth_calls
    for body in probe_bodies:
        assert body["model"] == "claude-haiku-4-5", body
        assert body["model"] != "anthropic/claude-haiku-4-5", body
        assert "/" not in body["model"], body


def test_claude_leg_probe_carries_bare_id(tmp_path, monkeypatch):
    calls = []
    _patch_network(monkeypatch, calls)
    client = _make_client(tmp_path)
    claude_calls = _connect(calls, client, "claude",
                           "claude/claude-haiku-4-5")
    probe_bodies = _probe_bodies(claude_calls, "/v1/messages")
    assert probe_bodies, claude_calls
    for body in probe_bodies:
        assert body["model"] == "claude-haiku-4-5", body
        assert "/" not in body["model"], body


def test_cloud_real_ids_connect_roundtrip(tmp_path, monkeypatch):
    calls = []
    _patch_network(monkeypatch, calls)
    client = _make_client(tmp_path)
    for preset_id, model in (
            ("openai", "openai/gpt-4o-mini"),
            ("meta", "meta/muse-spark-1.3-contributor")):
        _connect(calls, client, preset_id, model)
    listed = client.get("/api/v1/providers", headers=HEADERS)
    assert listed.status_code == 200, listed.text
    rows = {r["provider_id"]: r for r in listed.json()["providers"]}
    assert "openai" in rows, rows
    assert "meta" in rows, rows
    for pid in ("openai", "meta"):
        models = client.get("/api/v1/providers/%s/models" % pid,
                            headers=HEADERS)
        assert models.status_code == 200, models.text
        assert BAIT not in models.text


def test_wrong_token_refused_no_key_leak(tmp_path, monkeypatch):
    calls = []
    _patch_network(monkeypatch, calls)
    client = _make_client(tmp_path)
    saved = client.post("/api/v1/providers/keys",
                        json={"preset_id": "anthropic", "key_value": BAIT},
                        headers=WRONG_HEADERS)
    assert saved.status_code in (401, 403), saved.text
    assert BAIT not in saved.text
    conn = client.post("/api/v1/providers/connect",
                       json={"preset_id": "anthropic",
                             "model": "anthropic/claude-haiku-4-5",
                             "key_ref": {"secret_id": "anthropic",
                                         "provider_id": "anthropic"}},
                       headers=WRONG_HEADERS)
    assert conn.status_code in (401, 403), conn.text
    assert BAIT not in conn.text
