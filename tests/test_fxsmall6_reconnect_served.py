"""FXSMALL item 6 served: re-connect after a dropped key value is idempotent.

Through the REAL app (create_app + TestClient + memory secret store), fakes
only at the provider network boundary (urllib urlopen). Scenario from the
H104 log (20:42:21): connect Meta (keys 201, connect 200), drop the key
value behind the registry's back (the card falls back to Connect), save +
connect again. Before the fix the second connect answered 400 "instance
already registered: meta/default"; now it answers 200 with the row updated
and no duplicate instance. A different base URL for the same id stays a
400 carrying PROVIDER_CONFLICT.
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
from agent_si.providers.registry import provider_routes as _routes  # noqa: E402

APP_TOKEN = "fxsmall6-app-token"
BAIT = "FAKE-FXSMALL6-0000-zzzz-not-a-real-key"
HEADERS = {"x-actor": "ui-probe", "x-ui-session-token": APP_TOKEN}
META_MODEL = "meta/muse-spark-1.3-contributor"

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

    monkeypatch.setattr(_urlreq, "urlopen", _fake_urlopen)
    import agent_si.local.bench_runner as _bench
    monkeypatch.setattr(_bench, "passive_gateway_check",
                        lambda ref: type("Probe", (), {
                            "reachable": True,
                            "reason": "fxsmall6 canned reachable"})())


def _make_client(tmp_path):
    _steplimits._reset_state()
    app = create_app({"store_dir": str(tmp_path / "appdata"),
                      "ui_session_token": APP_TOKEN,
                      "secret_store": "memory"})
    return (fastapi.testclient.TestClient(app, raise_server_exceptions=False),
            app)


def _save(client, preset_id="meta", key_value=BAIT):
    saved = client.post("/api/v1/providers/keys",
                        json={"preset_id": preset_id, "key_value": key_value},
                        headers=HEADERS)
    assert saved.status_code == 201, saved.text
    assert BAIT not in saved.text
    return saved.json()["key_ref"]


def _connect(client, key_ref, preset_id="meta", model=META_MODEL):
    return client.post("/api/v1/providers/connect",
                       json={"preset_id": preset_id, "model": model,
                             "key_ref": key_ref},
                       headers=HEADERS)


def _listed(client):
    listed = client.get("/api/v1/providers", headers=HEADERS)
    assert listed.status_code == 200, listed.text
    return {r["provider_id"]: r for r in listed.json()["providers"]}


def test_reconnect_after_dropped_key_value_is_idempotent(tmp_path,
                                                         monkeypatch):
    """Second Connect after a dropped key value: 200, row updated, no dup."""
    calls = []
    _patch_network(monkeypatch, calls)
    client, app = _make_client(tmp_path)
    first = _connect(client, _save(client))
    assert first.status_code == 200, first.text
    # Sibling-window case: the value dies behind the registry's back; the
    # card falls back to Connect while the row stays registered.
    app.state.k04_ctx.credential_store.delete("meta")
    assert "meta" not in _listed(client), "gone value must drop the card"
    second = _connect(client, _save(client))
    assert second.status_code == 200, second.text
    assert BAIT not in second.text
    rows = _listed(client)
    assert set(rows) == {"meta"}, rows
    assert second.json()["provider"]["provider_id"] == "meta", second.text


def test_same_id_different_base_url_keeps_plain_refusal(tmp_path,
                                                        monkeypatch):
    """A real conflict refuses 400 with the PROVIDER_CONFLICT code."""
    calls = []
    _patch_network(monkeypatch, calls)
    client, app = _make_client(tmp_path)
    first = _connect(client, _save(client))
    assert first.status_code == 200, first.text
    real_preset = _routes.get_preset("meta")
    assert real_preset["base_url"].startswith("https://"), real_preset
    monkeypatch.setattr(_routes, "get_preset",
                        lambda key: dict(real_preset,
                                         base_url="http://conflict.invalid"))
    refused = _connect(client, _save(client))
    assert refused.status_code == 400, refused.text
    body = refused.json()
    assert body.get("code") == "PROVIDER_CONFLICT", body
    assert "different base URL" in body.get("message", ""), body
    # The kept row still answers with the registered base URL only.
    rows = _listed(client)
    assert set(rows) == {"meta"}, rows
