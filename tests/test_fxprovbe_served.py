"""FXPROVBE: live model lists, enabled routing truth, no-vanish, no-hang.

Through the REAL app (create_app + TestClient + memory secret store) with a
fake ONLY at the network boundary (urllib urlopen). No real keys, no real
providers, no real network. Unit parts hit the new lane module directly.
"""
import json
import os
import sys
import threading
import urllib.request as _urlreq

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import fastapi.testclient  # noqa: E402
import pytest  # noqa: E402

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.backend.orchestration import steplimits as _steplimits  # noqa: E402
from agent_si.providers.registry import provider_model_lists as _lists  # noqa: E402

APP_TOKEN = "fxprovbe-app-token"
WRONG_HEADERS = {"x-actor": "ui-probe", "x-ui-session-token": "fxprovbe-wrong"}
HEADERS = {"x-actor": "ui-probe", "x-ui-session-token": APP_TOKEN}
BAIT = "FAKE-FXPROVBE-0000-zzzz-not-a-real-key"

LIVE_MODELS = {"data": [{"id": "gpt-4o-mini"}, {"id": "gpt-4o"},
                         {"id": "o1-preview"}]}
CANNED_USAGE = {"choices": [{"message": {"content": "fx canned"},
                             "finish_reason": "stop"}],
                "usage": {"input_tokens": 2, "output_tokens": 3}}


class _FakeResp:
    def __init__(self, payload):
        if isinstance(payload, bytes):
            self._raw = payload
        else:
            self._raw = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _patch_network(monkeypatch, calls, live=LIVE_MODELS, fail_models=False,
                   hang_models=False, hang_event=None):
    def _fake_urlopen(request, timeout=None):
        url = getattr(request, "full_url", str(request))
        calls.append(url)
        if url.rstrip("/").endswith("/models"):
            if hang_models:
                assert hang_event is not None
                hang_event.wait(30)
            if fail_models:
                raise _urlreq.HTTPError(url, 401, "denied", {}, None)
            return _FakeResp(live)
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
    key_ref = saved.json()["key_ref"]
    conn = client.post("/api/v1/providers/connect",
                       json={"preset_id": preset_id, "model": model,
                             "key_ref": key_ref},
                       headers=HEADERS)
    assert conn.status_code == 200, conn.text
    return conn


# --- unit: strict parse -----------------------------------------------------

def test_parse_good_body_sorted_stripped():
    body = {"data": [{"id": "  b-2 "}, {"id": "a-1"}, {"id": "a-1"}]}
    assert _lists.parse_live_models(body) == ["a-1", "b-2"]


@pytest.mark.parametrize("bad", [
    None, [], "x", {"nope": []}, {"data": None}, {"data": "x"},
    {"data": []}, {"data": [{"noid": 1}]}, {"data": [{"id": ""}]},
    {"data": [{"id": "  "}]}, {"data": [{"id": 5}]}, {"data": ["x"]},
    {"data": [{"id": "ok"}, {"id": ""}]},
])
def test_parse_bad_shapes_refused(bad):
    with pytest.raises(_lists.LiveModelsError):
        _lists.parse_live_models(bad)


# --- unit: one normalisation place ------------------------------------------

def test_canonical_prefix_forms_are_one_model():
    assert _lists.canonical_model_id("meta", "muse-spark-1.3") == \
        _lists.canonical_model_id("meta", "meta/muse-spark-1.3") == \
        "meta/muse-spark-1.3"


def test_wire_form_is_provider_accepted():
    assert _lists.wire_model_id("meta/muse-spark-1.3") == "muse-spark-1.3"
    assert _lists.wire_model_id("openai/openai/gpt-4o") == "openai/gpt-4o"


def test_dated_snapshot_resolves_by_exact_rule():
    assert _lists.dated_base_id("claude-haiku-4-5-20251001") == \
        "claude-haiku-4-5"
    assert _lists.dated_base_id("gpt-4o") == "gpt-4o"
    assert _lists.dated_base_id("gpt-4o-mini") == "gpt-4o-mini"
    assert _lists.dated_base_id("qwen2.5:7b") == "qwen2.5"


def test_no_fuzzy_match():
    rows = [{"provider_id": "openai", "model_id": "openai/gpt-4o-mini",
             "fields": {}}]
    assert _lists.resolve_kb_row(rows, "openai", "openai/gpt-4o") is None
    hit = _lists.resolve_kb_row(rows, "openai", "gpt-4o-mini")
    assert hit is not None and hit["model_id"] == "openai/gpt-4o-mini"


def test_resolved_row_keeps_callable_id():
    rows = [{"provider_id": "meta",
             "model_id": "meta/muse-spark-1.3-contributor", "fields": {}}]
    hit = _lists.resolve_kb_row(rows, "meta", "muse-spark-1.3-contributor")
    assert hit is not None
    assert _lists.wire_model_id(hit["model_id"]) == \
        "muse-spark-1.3-contributor"


# --- unit: merge --------------------------------------------------------------

def test_merge_marks_listed_and_unknown():
    live = ["b-live", "a-kb"]
    kb = [{"provider_id": "p", "model_id": "p/a-kb",
           "fields": {"input_token_price": {"value": 1.0},
                      "output_token_price": {"value": 2.0}}},
          {"provider_id": "p", "model_id": "p/old-kb", "fields": {}}]
    rows = _lists.merge_model_rows("p", live, kb)
    by_id = {r["id"]: r for r in rows}
    assert [r["id"] for r in rows] == sorted(by_id)
    assert by_id["p/a-kb"]["listed"] is True
    assert by_id["p/a-kb"]["kb_known"] is True
    assert by_id["p/a-kb"]["price"] == pytest.approx(3.0)
    assert by_id["p/old-kb"]["listed"] is False
    assert by_id["b-live" if "b-live" in by_id else "p/b-live"][
        "kb_known"] is False


# --- unit: timeout + join ------------------------------------------------------

def test_refresh_timeout_is_10s():
    assert _lists.MODELS_TIMEOUT_S == 10


def test_refresh_failure_is_generic_and_keyless():
    def _boom(url, headers, timeout):
        raise TimeoutError("hung")
    with pytest.raises(_lists.LiveModelsError) as exc:
        _lists.fetch_live_models("https://api.example/v1", BAIT,
                                 provider_id="openai", http_get=_boom)
    assert BAIT not in str(exc.value)
    assert "api.example" not in str(exc.value)


def test_second_refresh_joins_inflight():
    seen = []
    release = threading.Event()

    def _slow(url, headers, timeout):
        seen.append(url)
        release.wait(10)
        return {"data": [{"id": "m-1"}]}

    results = _lists._INFLIGHT
    out = {}

    def _run(key):
        out[key] = _lists.refresh_with_join(
            "openai", "https://api.example/v1", BAIT,
            [{"provider_id": "openai", "model_id": "openai/m-1",
              "fields": {}}],
            http_get=_slow, store_dir=None)

    first = threading.Thread(target=_run, args=("a",))
    first.start()
    import time as _t
    _t.sleep(0.2)
    second = threading.Thread(target=_run, args=("b",))
    second.start()
    _t.sleep(0.2)
    release.set()
    first.join(10)
    second.join(10)
    assert out["a"] is out["b"]
    assert len(seen) == 1
    results.clear()


# --- served: refresh after connect ---------------------------------------------

def test_connect_runs_refresh_and_get_shape(tmp_path, monkeypatch):
    calls = []
    _patch_network(monkeypatch, calls)
    client = _make_client(tmp_path)
    _connect(client, "openai", "openai/gpt-4o-mini")
    models = client.get("/api/v1/providers/openai/models", headers=HEADERS)
    assert models.status_code == 200, models.text
    payload = models.json()
    assert payload["source"] == "provider", payload
    assert payload["enabled"] == ["openai/gpt-4o-mini"], payload
    ids = [m["id"] for m in payload["models"]]
    assert ids == sorted(ids)
    assert "openai/gpt-4o-mini" in ids and "openai/gpt-4o" in ids
    row = {m["id"]: m for m in payload["models"]}["openai/gpt-4o-mini"]
    assert set(row) >= {"id", "name", "price", "kb_known"}
    assert BAIT not in models.text


def test_refresh_route_and_failed_refresh_keeps_last(tmp_path, monkeypatch):
    calls = []
    _patch_network(monkeypatch, calls)
    client = _make_client(tmp_path)
    _connect(client, "openai", "openai/gpt-4o-mini")
    client.get("/api/v1/providers/openai/models",
               headers=HEADERS).json()
    fail_live = {"data": [{"id": "gpt-zzz-new"}]}
    _patch_network(monkeypatch, calls, live=fail_live)
    ok = client.post("/api/v1/providers/openai/models/refresh", headers=HEADERS)
    assert ok.status_code == 200, ok.text
    assert "openai/gpt-zzz-new" in [m["id"] for m in ok.json()["models"]]
    _patch_network(monkeypatch, calls, fail_models=True)
    bad = client.post("/api/v1/providers/openai/models/refresh",
                      headers=HEADERS)
    assert bad.status_code in (502, 503, 504), bad.text
    assert "keeping the last list" in bad.json()["error"].lower()
    assert BAIT not in bad.text
    kept = client.get("/api/v1/providers/openai/models", headers=HEADERS)
    assert kept.status_code == 200
    assert [m["id"] for m in kept.json()["models"]] == \
        [m["id"] for m in ok.json()["models"]]
    listed = client.get("/api/v1/providers", headers=HEADERS).json()
    assert "openai" in {r["provider_id"] for r in listed["providers"]}


def test_refresh_token_guarded(tmp_path, monkeypatch):
    calls = []
    _patch_network(monkeypatch, calls)
    client = _make_client(tmp_path)
    _connect(client, "openai", "openai/gpt-4o-mini")
    denied = client.post("/api/v1/providers/openai/models/refresh",
                         headers=WRONG_HEADERS)
    assert denied.status_code in (401, 403), denied.text


# --- served: enabled is the routing truth ---------------------------------------

def test_put_enabled_gates_chat_models(tmp_path, monkeypatch):
    calls = []
    _patch_network(monkeypatch, calls)
    client = _make_client(tmp_path)
    _connect(client, "openai", "openai/gpt-4o-mini")
    put = client.put("/api/v1/providers/openai/models",
                     json={"ids": ["openai/gpt-4o"]}, headers=HEADERS)
    assert put.status_code == 200, put.text
    assert put.json()["enabled"] == ["openai/gpt-4o"]
    chat = client.get("/api/v1/chat/models?project_id=p1", headers=HEADERS)
    assert chat.status_code == 200, chat.text
    got = [m["model"] for m in chat.json()["models"]
           if m["provider_id"] == "openai"]
    canon = ["openai/" + m if "/" not in m else m for m in got]
    assert "openai/gpt-4o" in canon, got
    assert "openai/gpt-4o-mini" not in canon, got
    put2 = client.put("/api/v1/providers/openai/models",
                      json={"ids": ["openai/gpt-4o", "openai/gpt-4o-mini"]},
                      headers=HEADERS)
    assert put2.status_code == 200, put2.text
    chat2 = client.get("/api/v1/chat/models?project_id=p1",
                       headers=HEADERS).json()
    got2 = [m["model"] for m in chat2["models"]
            if m["provider_id"] == "openai"]
    canon2 = ["openai/" + m if "/" not in m else m for m in got2]
    assert "openai/gpt-4o-mini" in canon2, got2


def test_put_rejects_unknown_ids_and_needs_token(tmp_path, monkeypatch):
    calls = []
    _patch_network(monkeypatch, calls)
    client = _make_client(tmp_path)
    _connect(client, "openai", "openai/gpt-4o-mini")
    bad = client.put("/api/v1/providers/openai/models",
                     json={"ids": ["openai/no-such-model"]}, headers=HEADERS)
    assert bad.status_code == 400, bad.text
    denied = client.put("/api/v1/providers/openai/models",
                        json={"ids": ["openai/gpt-4o"]},
                        headers=WRONG_HEADERS)
    assert denied.status_code in (401, 403), denied.text
    wrong_shape = client.put("/api/v1/providers/openai/models",
                             json={"ids": "openai/gpt-4o"}, headers=HEADERS)
    assert wrong_shape.status_code == 400, wrong_shape.text


# --- served: nothing vanishes -----------------------------------------------------

def test_disconnect_removes_only_self_reconnect_single_row(
        tmp_path, monkeypatch):
    calls = []
    _patch_network(monkeypatch, calls)
    client = _make_client(tmp_path)
    _connect(client, "openai", "openai/gpt-4o-mini")
    _connect(client, "meta", "meta/muse-spark-1.3-contributor")
    client.put("/api/v1/providers/meta/models",
               json={"ids": ["meta/muse-spark-1.3-contributor"]},
               headers=HEADERS)
    disc = client.post("/api/v1/providers/openai/disconnect", json={},
                       headers=HEADERS)
    assert disc.status_code == 200, disc.text
    listed = client.get("/api/v1/providers", headers=HEADERS).json()
    ids = [r["provider_id"] for r in listed["providers"]]
    assert ids.count("meta") == 1 and "openai" not in ids
    meta_models = client.get("/api/v1/providers/meta/models",
                             headers=HEADERS)
    assert meta_models.status_code == 200
    assert meta_models.json()["enabled"] == \
        ["meta/muse-spark-1.3-contributor"]
    _connect(client, "openai", "openai/gpt-4o-mini")
    relisted = client.get("/api/v1/providers", headers=HEADERS).json()
    assert [r["provider_id"] for r in relisted["providers"]].count(
        "openai") == 1


def test_kb_rebind_keeps_connected_and_enabled(tmp_path, monkeypatch):
    calls = []
    _patch_network(monkeypatch, calls)
    client = _make_client(tmp_path)
    _connect(client, "openai", "openai/gpt-4o-mini")
    client.put("/api/v1/providers/openai/models",
               json={"ids": ["openai/gpt-4o"]}, headers=HEADERS)
    import copy as _copy

    from agent_si.model_kb import kb as _kb
    catalog = _kb.bound_catalog()
    empty = _copy.deepcopy(catalog)
    empty["models"] = []
    _kb.bind_catalog(empty)
    try:
        listed = client.get("/api/v1/providers", headers=HEADERS).json()
        assert "openai" in {r["provider_id"]
                            for r in listed["providers"]}
        kept = client.get("/api/v1/providers/openai/models",
                          headers=HEADERS)
        assert kept.status_code == 200
        assert kept.json()["enabled"] == ["openai/gpt-4o"]
    finally:
        _kb.bind_catalog(catalog)


def test_local_models_keep_list_without_network(tmp_path, monkeypatch):
    calls = []
    _patch_network(monkeypatch, calls)
    client = _make_client(tmp_path)
    conn = client.post("/api/v1/local/connect",
                       json={"runtime_ref": "http://localhost:11434"},
                       headers=HEADERS)
    assert conn.status_code == 200, conn.text
    models = client.get("/api/v1/providers/ollama/models", headers=HEADERS)
    assert models.status_code in (200, 404), models.text
    # FXROLEPICK R2 (intended): a local provider answers off the attached
    # runtime's real names via one loopback read. Never a cloud/non-loopback
    # fetch and never a gateway (key) call.
    reads = [u for u in calls if u.rstrip("/").endswith("/models")]
    assert all(u.startswith("http://localhost:11434/") for u in reads), reads
    assert not [u for u in calls if u.startswith("gateway:")], calls


# --- routing: auto compares every connected provider -------------------------------

def test_auto_compares_both_connected_providers():
    from agent_si.backend import routing_auto as _auto
    catalog = {"models": [
        {"provider_id": "openai", "model_id": "openai/gpt-4o-mini",
         "fields": {"input_token_price": {"value": 1.0},
                    "output_token_price": {"value": 2.0}}},
        {"provider_id": "meta",
         "model_id": "meta/muse-spark-1.3-contributor",
         "fields": {"input_token_price": {"value": 5.0},
                    "output_token_price": {"value": 5.0}}},
    ]}
    pick = _auto.pick_auto(catalog, ["openai", "meta"], "coding")
    compared = {(c["provider"], c["model"]) for c in pick["why"]["compared"]}
    assert ("openai", "openai/gpt-4o-mini") in compared
    assert ("meta", "meta/muse-spark-1.3-contributor") in compared


def test_auto_honours_enabled_and_dated_ids():
    from agent_si.backend import routing_auto as _auto
    catalog = {"models": [
        {"provider_id": "anthropic",
         "model_id": "anthropic/claude-haiku-4-5", "fields": {}},
    ]}
    enabled = {"anthropic": ["anthropic/claude-haiku-4-5-20251001"]}
    pick = _auto.pick_auto(catalog, ["anthropic"], "coding",
                           enabled=enabled)
    assert pick["model"] == "anthropic/claude-haiku-4-5", pick
    assert pick["manager"] == "anthropic", pick
    blocked = {"anthropic": ["anthropic/some-other-model"]}
    with pytest.raises(_auto.AutoBlocked):
        _auto.pick_auto(catalog, ["anthropic"], "coding",
                        enabled=blocked)
