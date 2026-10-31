"""PROVCK2: connect-time preflight + allowlisted failure classes.

Through the REAL app (create_app + store dir + secret_store memory +
HTTP TestClient) with fakes ONLY at the network transport (urllib
urlopen) and at the credential-store read edge (flaky wrapper). All
bait values are fake placeholders, never real keys.

Proves, per class (store-read vs network vs HTTP vs unknown):
- classification is correct (provck2-evidence audit record class/code),
- no bait bytes leak into any surface (connect payload, provider list,
  audit records, persisted provider_connections.json).
Plus: a transient store-read failure is retried once (provck2-store-retry
record) and a recovered read evidences normally.
"""
import json
import os
import sys
import urllib.error as _urlerror
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

APP_TOKEN = "provck2-app-token"
HEADERS = {"x-actor": "ui-probe", "x-ui-session-token": APP_TOKEN}

# Fake placeholders only, never real keys. Each test uses its own bait
# so a leak is attributable to the exact class under test.
BAIT_RETRY = "PROVCK2-FAKE-BAIT-1001-not-a-real-key"
BAIT_STORE = "PROVCK2-FAKE-BAIT-2002-not-a-real-key"
BAIT_NET = "PROVCK2-FAKE-BAIT-3003-not-a-real-key"
BAIT_HTTP = "PROVCK2-FAKE-BAIT-4004-not-a-real-key"
BAIT_UNKNOWN = "PROVCK2-FAKE-BAIT-5005-not-a-real-key"
BAIT_TRUNC = "PROVCK2-FAKE-BAIT-6006-not-a-real-key"

CANNED_USAGE = {"input_tokens": 3, "output_tokens": 5,
                "cached_tokens": 0, "reasoning_tokens": 0}


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
    return {"choices": [{"message": {"content": "provck2 canned"},
                         "finish_reason": "stop"}],
            "usage": dict(CANNED_USAGE)}


def _settings(tmp_path):
    return {"store_dir": str(tmp_path / "appdata"),
            "ui_session_token": APP_TOKEN,
            "secret_store": "memory"}


def _make_client(tmp_path):
    _steplimits._reset_state()
    app = create_app(_settings(tmp_path))
    return (fastapi.testclient.TestClient(app, raise_server_exceptions=False),
            app)


def _create_project(client):
    resp = client.post("/api/v1/projects",
                       json={"name": "p-provck2",
                             "folder_ref": "dock-provck2"},
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


def _save_key(client, bait):
    resp = client.post("/api/v1/providers/keys",
                       json={"preset_id": "openai", "key_value": bait},
                       headers=HEADERS)
    assert resp.status_code == 201, resp.text
    assert bait not in resp.text
    return resp.json()["key_ref"]


def _connect(client, key_ref, model):
    return client.post("/api/v1/providers/connect",
                       json={"preset_id": "openai", "model": model,
                             "key_ref": key_ref},
                       headers=HEADERS)


def _rows(client):
    listed = client.get("/api/v1/providers", headers=HEADERS)
    assert listed.status_code == 200, listed.text
    return {r["provider_id"]: r for r in listed.json()["providers"]}


def _connections_text(tmp_path):
    path = os.path.join(str(tmp_path / "appdata"),
                        "provider_connections.json")
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _evidence(app, event="provck2-evidence"):
    return [r for r in app.state.k04_ctx.audit_sink.records
            if isinstance(r, dict) and r.get("event") == event
            and r.get("provider_id") == "openai"]


def _assert_no_leak(bait, *texts):
    for text in texts:
        assert bait not in text, text


def test_store_read_transient_retry_recovers(tmp_path, monkeypatch):
    """A store read failing transiently is retried once, then evidences."""
    monkeypatch.setattr(_urlreq, "urlopen",
                        lambda request, timeout=None: _FakeResp(_ok_body()))
    client, app = _make_client(tmp_path)
    _create_project(client)
    key_ref = _save_key(client, BAIT_RETRY)
    store = app.state.k04_ctx.credential_store
    orig = store.get_secret
    calls = {"n": 0}

    def _flaky(secret_id, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] <= 6:
            raise RuntimeError("PROVCK2 simulated transient store outage")
        return orig(secret_id, *args, **kwargs)

    monkeypatch.setattr(store, "get_secret", _flaky)
    conn = _connect(client, key_ref, "m-retry")
    assert conn.status_code == 200, conn.text
    _assert_no_leak(BAIT_RETRY, conn.text)
    rows = _rows(client)
    assert rows["openai"]["evidenced"] is True, rows
    assert rows["openai"]["health"] != "ERROR", rows
    retries = _evidence(app, "provck2-store-retry")
    assert [r["attempt"] for r in retries] == [1, 2], retries
    assert [r["outcome"] for r in retries] == ["retrying",
                                              "recovered"], retries
    proof = _evidence(app)
    assert len(proof) == 1, proof
    assert proof[0]["class"] == "ok", proof
    assert proof[0]["code"] == "EVIDENCE_OK", proof
    assert proof[0]["store_attempts"] == 2, proof
    audit_text = str(app.state.k04_ctx.audit_sink.records)
    _assert_no_leak(BAIT_RETRY, audit_text, _connections_text(tmp_path),
                    json.dumps(rows))


def test_store_read_failure_class_and_no_leak(tmp_path, monkeypatch):
    """Missing store entry: preflight fails (no urlopen), store-read code."""
    def _must_not_fire(request, timeout=None):
        raise AssertionError("urlopen must not fire before preflight passes")

    monkeypatch.setattr(_urlreq, "urlopen", _must_not_fire)
    client, app = _make_client(tmp_path)
    _create_project(client)
    key_ref = _save_key(client, BAIT_STORE)
    app.state.k04_ctx.credential_store.delete(key_ref["secret_id"])
    conn = _connect(client, key_ref, "m-nostore")
    assert conn.status_code == 200, conn.text
    _assert_no_leak(BAIT_STORE, conn.text)
    rows = _rows(client)
    assert rows["openai"]["health"] == "ERROR", rows
    assert rows["openai"].get("error") == "credential store unavailable", rows
    proof = _evidence(app)
    assert len(proof) == 1, proof
    assert proof[0]["class"] == "store-read", proof
    assert proof[0]["code"] == "CREDENTIAL_STORE_UNAVAILABLE", proof
    assert proof[0]["store_attempts"] == 2, proof
    retries = _evidence(app, "provck2-store-retry")
    assert [r["outcome"] for r in retries] == ["retrying",
                                              "exhausted"], retries
    audit_text = str(app.state.k04_ctx.audit_sink.records)
    _assert_no_leak(BAIT_STORE, audit_text, _connections_text(tmp_path),
                    json.dumps(rows))


def test_network_failure_class_and_no_leak(tmp_path, monkeypatch):
    """Status-less transport failure: generic reason, network class."""
    def _fail(request, timeout=None):
        raise _urlreq.URLError(
            "simulated outage carrying %s inside" % BAIT_NET)

    monkeypatch.setattr(_urlreq, "urlopen", _fail)
    client, app = _make_client(tmp_path)
    _create_project(client)
    key_ref = _save_key(client, BAIT_NET)
    conn = _connect(client, key_ref, "m-net")
    assert conn.status_code == 200, conn.text
    _assert_no_leak(BAIT_NET, conn.text,
                    "simulated outage carrying")
    rows = _rows(client)
    assert rows["openai"]["health"] == "ERROR", rows
    assert rows["openai"].get("error") == "provider check failed", rows
    proof = _evidence(app)
    assert len(proof) == 1, proof
    assert proof[0]["class"] == "network", proof
    assert proof[0]["code"] == "EVIDENCE_PROBE_NETWORK", proof
    assert proof[0]["store_attempts"] == 1, proof
    audit_text = str(app.state.k04_ctx.audit_sink.records)
    _assert_no_leak(BAIT_NET, audit_text, _connections_text(tmp_path),
                    json.dumps(rows), "simulated outage carrying")


def test_http_failure_class_and_no_leak(tmp_path, monkeypatch):
    """HTTP status failure: status-only reason, http class + int status."""
    def _fail(request, timeout=None):
        raise _urlerror.HTTPError(
            "https://api.openai.com/v1/chat/completions", 401,
            "Unauthorized carrying %s inside" % BAIT_HTTP, {}, None)

    monkeypatch.setattr(_urlreq, "urlopen", _fail)
    client, app = _make_client(tmp_path)
    _create_project(client)
    key_ref = _save_key(client, BAIT_HTTP)
    conn = _connect(client, key_ref, "m-http")
    assert conn.status_code == 200, conn.text
    _assert_no_leak(BAIT_HTTP, conn.text, "Unauthorized carrying")
    rows = _rows(client)
    assert rows["openai"]["health"] == "ERROR", rows
    assert rows["openai"].get("error") == "provider answered HTTP 401", rows
    proof = _evidence(app)
    assert len(proof) == 1, proof
    assert proof[0]["class"] == "http", proof
    assert proof[0]["code"] == "PROVIDER_ANSWERED_HTTP", proof
    assert proof[0]["status"] == 401, proof
    assert isinstance(proof[0]["status"], int), proof
    audit_text = str(app.state.k04_ctx.audit_sink.records)
    _assert_no_leak(BAIT_HTTP, audit_text, _connections_text(tmp_path),
                    json.dumps(rows), "Unauthorized carrying")


def test_unknown_statusless_class_and_no_leak(tmp_path, monkeypatch):
    """Non-network status-less failure: generic reason, unknown class."""
    def _fail(request, timeout=None):
        raise RuntimeError("weird local failure %s" % BAIT_UNKNOWN)

    monkeypatch.setattr(_urlreq, "urlopen", _fail)
    client, app = _make_client(tmp_path)
    _create_project(client)
    key_ref = _save_key(client, BAIT_UNKNOWN)
    conn = _connect(client, key_ref, "m-unknown")
    assert conn.status_code == 200, conn.text
    _assert_no_leak(BAIT_UNKNOWN, conn.text, "weird local failure")
    rows = _rows(client)
    assert rows["openai"]["health"] == "ERROR", rows
    assert rows["openai"].get("error") == "provider check failed", rows
    proof = _evidence(app)
    assert len(proof) == 1, proof
    assert proof[0]["class"] == "unknown", proof
    assert proof[0]["code"] == "PROVIDER_CHECK_FAILED", proof
    audit_text = str(app.state.k04_ctx.audit_sink.records)
    _assert_no_leak(BAIT_UNKNOWN, audit_text, _connections_text(tmp_path),
                    json.dumps(rows), "weird local failure")


def test_truncated_body_maps_to_network_class_and_no_leak(
        tmp_path, monkeypatch):
    """Garbled/truncated gateway body: transport failure, network class.

    http.client read errors and undecodable bytes are plain Exceptions
    (not OSError); the transport must map them to the network class with
    the generic reason, never surfacing body bytes.
    """
    import http.client as _httpclient

    class _TruncatedResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            raise _httpclient.IncompleteRead(
                partial=b"\xff\xfe-garbled-%s" % BAIT_TRUNC.encode(),
                expected=128)

    monkeypatch.setattr(_urlreq, "urlopen",
                        lambda request, timeout=None: _TruncatedResp())
    client, app = _make_client(tmp_path)
    _create_project(client)
    key_ref = _save_key(client, BAIT_TRUNC)
    conn = _connect(client, key_ref, "m-trunc")
    assert conn.status_code == 200, conn.text
    _assert_no_leak(BAIT_TRUNC, conn.text, "garbled", "unreadable")
    rows = _rows(client)
    assert rows["openai"]["health"] == "ERROR", rows
    assert rows["openai"].get("error") == "provider check failed", rows
    proof = _evidence(app)
    assert len(proof) == 1, proof
    assert proof[0]["class"] == "network", proof
    assert proof[0]["code"] == "EVIDENCE_PROBE_NETWORK", proof
    assert proof[0]["store_attempts"] == 1, proof
    audit_text = str(app.state.k04_ctx.audit_sink.records)
    _assert_no_leak(BAIT_TRUNC, audit_text, _connections_text(tmp_path),
                    json.dumps(rows), "garbled")

    class _BadBytesResp(_TruncatedResp):
        def read(self):
            return b"\xff\xfe-not-utf8-%s" % BAIT_TRUNC.encode()

    monkeypatch.setattr(_urlreq, "urlopen",
                        lambda request, timeout=None: _BadBytesResp())
    part2 = tmp_path / "part2"
    part2.mkdir(exist_ok=True)
    client2, app2 = _make_client(part2)
    _create_project(client2)
    key_ref2 = _save_key(client2, BAIT_TRUNC)
    conn2 = _connect(client2, key_ref2, "m-badbytes")
    assert conn2.status_code == 200, conn2.text
    rows2 = _rows(client2)
    assert rows2["openai"].get("error") == "provider check failed", rows2
    proof2 = [r for r in app2.state.k04_ctx.audit_sink.records
              if isinstance(r, dict) and r.get("event") == "provck2-evidence"
              and r.get("provider_id") == "openai"]
    assert len(proof2) == 1, proof2
    assert proof2[0]["class"] == "network", proof2
    assert proof2[0]["code"] == "EVIDENCE_PROBE_NETWORK", proof2
    _assert_no_leak(BAIT_TRUNC, str(app2.state.k04_ctx.audit_sink.records),
                    json.dumps(rows2))
