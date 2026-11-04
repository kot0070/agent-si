"""K04WIRE1: served stack uses only real stores; no silent memory fallback.

- default settings (os) wire OSCredentialStore + persistent file audit sink;
  audit records survive a restart, never carry the secret value.
- OS build failure: app still starts, k04_config_error carries the verbatim
  reason, keys/connect answer 503, NO memory store is used.
- secret_store memory (or testing True) keeps the memory stack.
- no environment/runner detection anywhere in the wired path.
"""
import os
import sys
import urllib.request as _urlreq

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import fastapi.testclient  # noqa: E402

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.providers.registry import facades as FAC  # noqa: E402
from agent_si.providers.registry.os_credential_store import (  # noqa: E402
    OSCredentialStore,
)

APP_TOKEN = "k04wire1-app-token"
BAIT = "FAKE-K04WIRE1-BAIT-9999-zzzz-not-a-real-key"
SUFFIX = "TESTK04WIRE1"
HEADERS = {"x-actor": "ui-probe", "x-ui-session-token": APP_TOKEN}


def _settings(tmp_path, **extra):
    base = {
        "store_dir": str(tmp_path / "appdata"),
        "ui_session_token": APP_TOKEN,
        "secret_label_suffix": SUFFIX,
    }
    base.update(extra)
    return base


def _stub_models_ok(monkeypatch):
    """Save preflight sees a live /models list (network stays faked)."""

    class _Resp:
        def read(self):
            return b'{"data": [{"id": "gpt-4o"}]}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        _urlreq, "urlopen",
        lambda request, timeout=None: _Resp())


def test_os_served_audit_persists_across_restart(tmp_path, monkeypatch):
    # S4: asserts the real OS default, so it opts out of the
    # conftest memory default for this test only.
    monkeypatch.delenv("AGENT_SI_SECRET_STORE", raising=False)
    _stub_models_ok(monkeypatch)
    settings = _settings(tmp_path)
    app = create_app(settings)
    assert app.state.k04_config_error is None, app.state.k04_config_error
    assert app.state.k04_ctx is not None
    cred = app.state.k04_ctx.credential_store
    assert isinstance(cred, OSCredentialStore), type(cred)
    assert type(cred).__name__ != "_MemoryCredentialStore"
    sink = app.state.k04_ctx.audit_sink
    assert type(sink).__name__ == "_FileAuditSink", type(sink)
    assert str(sink.path).endswith("provider_audit.jsonl"), sink.path
    assert str(tmp_path / "appdata") in str(sink.path), sink.path
    client = fastapi.testclient.TestClient(app)
    try:
        resp = client.post(
            "/api/v1/providers/keys",
            json={"preset_id": "openai", "key_value": BAIT},
            headers=HEADERS)
        assert resp.status_code == 201, resp.text
        assert BAIT not in resp.text
    finally:
        try:
            if cred.has("openai"):
                cred.delete("openai")
        except Exception:
            pass
    assert os.path.isfile(sink.path), sink.path
    with open(sink.path, "r", encoding="utf-8") as fh:
        raw = fh.read()
    assert BAIT not in raw
    assert "key-save" in raw
    assert "openai" in raw
    # restart: same store dir, fresh app object
    app2 = create_app(settings)
    assert app2.state.k04_config_error is None, app2.state.k04_config_error
    sink2 = app2.state.k04_ctx.audit_sink
    assert type(sink2).__name__ == "_FileAuditSink", type(sink2)
    recs = sink2.records
    assert any(
        isinstance(r, dict) and r.get("reason") == "key-save"
        and r.get("entry") == "openai" for r in recs), recs
    assert BAIT not in str(recs)
    # cleanup any leftover TEST-labelled OS entry
    try:
        if app2.state.k04_ctx.credential_store.has("openai"):
            app2.state.k04_ctx.credential_store.delete("openai")
    except Exception:
        pass


def test_os_build_failure_starts_app_and_503_no_memory(monkeypatch, tmp_path):
    # S4: asserts the real OS default, so it opts out of the
    # conftest memory default for this test only.
    monkeypatch.delenv("AGENT_SI_SECRET_STORE", raising=False)
    reason = "simulated-OS-down-K04WIRE1"

    def _boom(**kwargs):
        raise OSError(reason)

    def _no_memory(*a, **k):
        raise AssertionError("silent memory fallback is forbidden")

    monkeypatch.setattr(FAC, "os_stack", _boom)
    monkeypatch.setattr(FAC, "memory_stack", _no_memory)
    settings = _settings(tmp_path)
    app = create_app(settings)  # app still starts
    assert app.state.k04_ctx is None
    err = app.state.k04_config_error
    assert err is not None
    assert "K04 OS credential store unavailable" in err
    assert reason in err  # verbatim reason carried
    client = fastapi.testclient.TestClient(app)
    resp = client.post(
        "/api/v1/providers/keys",
        json={"preset_id": "openai", "key_value": BAIT},
        headers=HEADERS)
    assert resp.status_code == 503, resp.text
    assert reason in resp.text
    assert BAIT not in resp.text
    conn = client.post(
        "/api/v1/providers/connect",
        json={"preset_id": "openai", "model": "m-k04wire1",
              "key_ref": {"secret_id": "openai", "provider_id": "openai"}},
        headers=HEADERS)
    assert conn.status_code == 503, conn.text
    assert reason in conn.text


def test_memory_setting_keeps_memory_stack(tmp_path, monkeypatch):
    _stub_models_ok(monkeypatch)
    settings = _settings(tmp_path, secret_store="memory")
    app = create_app(settings)
    assert app.state.k04_config_error is None
    cred = app.state.k04_ctx.credential_store
    assert type(cred).__name__ == "_MemoryCredentialStore", type(cred)
    assert type(app.state.k04_ctx.audit_sink).__name__ == \
        "_MemoryAuditSink"
    client = fastapi.testclient.TestClient(app)
    resp = client.post(
        "/api/v1/providers/keys",
        json={"preset_id": "openai", "key_value": BAIT},
        headers=HEADERS)
    assert resp.status_code == 201, resp.text
    assert BAIT not in str(app.state.k04_ctx.audit_sink.records)


def test_no_env_or_runner_detection():
    # S4: the single sanctioned product setting (env.example)
    # AGENT_SI_SECRET_STORE may be read in the wired path (settings
    # win, the env decides only when settings stay silent); every
    # other env read and all runner detection stay banned.
    for mod_path in (
        os.path.join(_SRC, "agent_si", "backend", "app.py"),
        os.path.join(_SRC, "agent_si", "providers", "registry",
                     "facades.py"),
    ):
        with open(mod_path, "r", encoding="utf-8") as fh:
            text = fh.read()
        for marker in ("GITHUB_ACTIONS", "PYTEST_CURRENT_TEST",
                       "RUNNER", "CI_"):
            assert marker not in text, (mod_path, marker)
        for i, line in enumerate(text.splitlines(), 1):
            if ("os.environ" in line or "os.getenv" in line
                    or "getenv(" in line or "environ.get" in line):
                assert "AGENT_SI_SECRET_STORE" in line, (
                    mod_path, i, line.strip()[:160])
