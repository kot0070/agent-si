"""FXWALK1 served gate: W12 connect seeds chat models, W19 apps card,
W20 facades default audit path (frozen-safe).

Through the REAL app (create_app + TestClient + memory secret store) with
a fake ONLY at the network boundary (urllib urlopen for the provider
evidence probe, passive gateway check for local discovery). No real keys,
no real providers, no real network.
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
from agent_si.providers.registry import facades as _facades  # noqa: E402

APP_TOKEN = "fxwalk1-app-token"
HEADERS = {"x-actor": "ui-probe", "x-ui-session-token": APP_TOKEN}
BAIT = "FAKE-FXWALK1-0000-zzzz-not-a-real-key"

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


def _connect_openai(client):
    saved = client.post("/api/v1/providers/keys",
                        json={"preset_id": "openai", "key_value": BAIT},
                        headers=HEADERS)
    assert saved.status_code == 201, saved.text
    key_ref = saved.json()["key_ref"]
    conn = client.post("/api/v1/providers/connect",
                       json={"preset_id": "openai", "model": "openai/model-1",
                             "key_ref": key_ref},
                       headers=HEADERS)
    assert conn.status_code == 200, conn.text
    assert BAIT not in conn.text
    return conn


def test_w12_connect_seeds_enabled_chat_models(tmp_path, monkeypatch):
    """W12: after connect the chat models endpoint is non-empty."""
    calls = []
    _patch_network(monkeypatch, calls)
    client = _make_client(tmp_path)
    before = client.get("/api/v1/chat/models?project_id=p1", headers=HEADERS)
    assert before.status_code == 200, before.text
    assert before.json()["models"] == [], before.text
    _connect_openai(client)
    after = client.get("/api/v1/chat/models?project_id=p1", headers=HEADERS)
    assert after.status_code == 200, after.text
    models = after.json()["models"]
    assert len(models) > 0, after.text
    assert any(m["provider_id"] == "openai"
               and "model-1" in m["model"] for m in models), after.text
    assert BAIT not in after.text


def test_w19_apps_card_route_200_with_no_provider(tmp_path, monkeypatch):
    """W19: GET /api/v1/apps/card answers 200 with no provider connected."""
    calls = []
    _patch_network(monkeypatch, calls)
    client = _make_client(tmp_path)
    card = client.get("/api/v1/apps/card?project_id=p1", headers=HEADERS)
    assert card.status_code == 200, card.text
    body = card.json()
    assert body["project_id"] == "p1", card.text
    assert isinstance(body["service_ids"], list), card.text


def test_w20_facades_default_audit_path_frozen_safe(tmp_path, monkeypatch):
    """W20 (FROZENSCAN R11): faked sys.frozen still defaults off the CWD."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable",
                        os.path.join("C:" + os.sep, "bundle", "AgentSI.exe"),
                        raising=False)
    monkeypatch.chdir(tmp_path)
    helper = getattr(_facades, "default_audit_path", None)
    assert callable(helper), "facades.default_audit_path missing (R11)"
    path = helper()
    assert isinstance(path, str) and path, repr(path)
    assert os.path.abspath(path) != os.path.join(os.getcwd(),
                                                 "provider_audit.jsonl")
    assert not os.path.abspath(path).startswith(os.getcwd() + os.sep), path
    stack = _facades.memory_stack()
    assert stack is not None
