"""FXPROV served: the exact UI JSON reaches the real provider routes.

Through the REAL app (create_app + TestClient + memory secret store) with a
fake ONLY at the network boundary (urllib urlopen for the provider evidence
probe, passive gateway check for local discovery). No real keys, no real
providers, no real network.

Covers the P2 root: the served registry is the truth the page, first-run
and chat read. Proves the connect->list->models->disconnect roundtrip, the
empty registry of a fresh process (restart), and that the served route
accepts the preset ids the settings page posts.
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

APP_TOKEN = "fxprov-app-token"
WRONG_TOKEN = "fxprov-wrong-token"
BAIT = "FAKE-FXPROV-0000-zzzz-not-a-real-key"
HEADERS = {"x-actor": "ui-probe", "x-ui-session-token": APP_TOKEN}

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


def _connect(client, preset_id, model):
    saved = client.post("/api/v1/providers/keys",
                        json={"preset_id": preset_id, "key_value": BAIT},
                        headers=HEADERS)
    assert saved.status_code == 201, saved.text
    assert BAIT not in saved.text
    key_ref = saved.json()["key_ref"]
    return client.post("/api/v1/providers/connect",
                       json={"preset_id": preset_id, "model": model,
                             "key_ref": key_ref},
                       headers=HEADERS)


def test_cloud_roundtrip_serves_truth_for_page_remount(tmp_path, monkeypatch):
    """Page remount reads the same registry: connect, list, models, drop."""
    calls = []
    _patch_network(monkeypatch, calls)
    client = _make_client(tmp_path)
    conn = _connect(client, "openai", "openai/gpt-4o-mini")
    assert conn.status_code == 200, conn.text
    assert BAIT not in conn.text
    # A remount (leave Settings, return) reads GET /providers: openai stays.
    for _ in range(2):
        listed = client.get("/api/v1/providers", headers=HEADERS)
        assert listed.status_code == 200, listed.text
        rows = {r["provider_id"]: r for r in listed.json()["providers"]}
        assert "openai" in rows, rows
    models = client.get("/api/v1/providers/openai/models", headers=HEADERS)
    assert models.status_code == 200, models.text
    assert models.json()["provider_id"] == "openai", models.text
    # Served spellings are the bare KB ids (never qualified, never invented).
    served_ids = [r["model"] for r in models.json()["models"]]
    assert set(served_ids) == {"gpt-4o", "gpt-4o-mini"}, models.text
    assert BAIT not in models.text
    disc = client.post("/api/v1/providers/openai/disconnect", json={},
                       headers=HEADERS)
    assert disc.status_code == 200, disc.text
    listed = client.get("/api/v1/providers", headers=HEADERS)
    rows = {r["provider_id"]: r for r in listed.json()["providers"]}
    assert "openai" not in rows, rows


def test_restart_keeps_connected_brand_new_dir_lists_nothing(tmp_path,
                                                            monkeypatch):
    """Restart truth (FXSTORE): the registry persists, but a memory-store
    key dies with the window. After a restart without a re-save the
    served list drops the provider (the page shows Connect, never a
    stale Disconnect); a re-save brings it back. A fresh dir is empty."""
    calls = []
    _patch_network(monkeypatch, calls)
    first = _make_client(tmp_path)
    conn = _connect(first, "openai", "openai/gpt-4o-mini")
    assert conn.status_code == 200, conn.text
    restarted = _make_client(tmp_path)
    listed = restarted.get("/api/v1/providers", headers=HEADERS)
    assert listed.status_code == 200, listed.text
    rows = {r["provider_id"] for r in listed.json()["providers"]}
    assert rows == set(), listed.text
    resaved = restarted.post(
        "/api/v1/providers/keys",
        json={"preset_id": "openai", "key_value": BAIT},
        headers=HEADERS)
    assert resaved.status_code == 201, resaved.text
    # The registry entry survives the restart (no re-connect needed):
    # the re-saved value alone brings the row back.
    listed = restarted.get("/api/v1/providers", headers=HEADERS)
    assert listed.status_code == 200, listed.text
    rows = {r["provider_id"] for r in listed.json()["providers"]}
    assert "openai" in rows, listed.text
    fresh = _make_client(tmp_path / "fresh")
    listed = fresh.get("/api/v1/providers", headers=HEADERS)
    assert listed.status_code == 200, listed.text
    assert listed.json()["providers"] == [], listed.text


def test_served_route_accepts_page_preset_ids(tmp_path, monkeypatch):
    """Every cloud preset id the page posts connects on the real route."""
    calls = []
    _patch_network(monkeypatch, calls)
    client = _make_client(tmp_path)
    page_ids = {
        "meta": "meta/muse-spark-1.3-contributor",
        "openai": "openai/gpt-4o-mini",
        "anthropic": "anthropic/claude-haiku-4-5",
        "claude": "claude/claude-haiku-4-5",
        "gemini": "gemini/gemini-3.8-flash",
        "mistral": "mistral/mistral-large-4",
        "groq": "groq/llama-3.3-70b-versatile",
        "openrouter": "openrouter/openrouter-meta-muse-spark-1.3",
        "deepseek": "deepseek/deepseek-v4-pro",
        "xai": "xai/grok-4.7",
        "lm-studio": "lm-studio/chat",
    }
    for preset_id, model in page_ids.items():
        conn = _connect(client, preset_id, model)
        assert conn.status_code == 200, (preset_id, conn.text)
    listed = client.get("/api/v1/providers", headers=HEADERS)
    rows = {r["provider_id"] for r in listed.json()["providers"]}
    assert set(page_ids) <= rows, rows


def test_unknown_preset_rejected(tmp_path, monkeypatch):
    """The old page ids (openai-compatible, lmstudio) never connected."""
    calls = []
    _patch_network(monkeypatch, calls)
    client = _make_client(tmp_path)
    saved = client.post("/api/v1/providers/keys",
                        json={"preset_id": "openai", "key_value": BAIT},
                        headers=HEADERS)
    assert saved.status_code == 201, saved.text
    key_ref = saved.json()["key_ref"]
    for stale in ("openai-compatible", "lmstudio"):
        refused_keys = client.post(
            "/api/v1/providers/keys",
            json={"preset_id": stale, "key_value": BAIT}, headers=HEADERS)
        assert refused_keys.status_code == 400, (stale, refused_keys.text)
        refused = client.post(
            "/api/v1/providers/connect",
            json={"preset_id": stale, "model": "m/x",
                  "key_ref": key_ref},
            headers=HEADERS)
        assert refused.status_code == 400, (stale, refused.text)
        assert "unknown preset" in refused.text, refused.text


def test_local_runtime_roundtrip_through_real_routes(tmp_path, monkeypatch):
    """Local presets attach a runtime the page maps back by base URL."""
    calls = []
    _patch_network(monkeypatch, calls)
    client = _make_client(tmp_path)
    conn = client.post("/api/v1/local/connect",
                       json={"runtime_ref": "http://localhost:11434"},
                       headers=HEADERS)
    assert conn.status_code == 200, conn.text
    models = client.get("/api/v1/local/models", headers=HEADERS)
    assert models.status_code == 200, models.text
    assert "http://localhost:11434" in models.text, models.text
    disc = client.post("/api/v1/local/disconnect", json={},
                       headers=HEADERS)
    assert disc.status_code == 200, disc.text
