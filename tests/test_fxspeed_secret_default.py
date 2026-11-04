"""FXSPEED S4: the secret-store default is memory; explicit settings win.

conftest.py defaults AGENT_SI_SECRET_STORE to memory at import, so no
test run touches the real OS key store unless a test opts out with
monkeypatch.delenv (the OS-default tests in test_k04wire1_real_stack
and test_rc5_reopen_keeps_binding do exactly that).
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_WS = os.path.dirname(_HERE)
_SRC = os.path.join(_WS, "src")
for _p in (_SRC, _WS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.providers.registry import facades as FAC  # noqa: E402


def _settings(tmp_path, **extra):
    base = {"store_dir": str(tmp_path / "appdata"),
            "ui_session_token": "fxspeed-s4-token"}
    base.update(extra)
    return base


def test_conftest_defaults_env_to_memory():
    assert os.environ.get("AGENT_SI_SECRET_STORE") == "memory"


def test_default_settings_use_memory_store(tmp_path):
    app = create_app(_settings(tmp_path))
    assert app.state.k04_config_error is None, app.state.k04_config_error
    cred = app.state.k04_ctx.credential_store
    assert type(cred).__name__ == "_MemoryCredentialStore", type(cred)


def test_explicit_memory_setting_wins_over_os_env(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SI_SECRET_STORE", "os")
    app = create_app(_settings(tmp_path, secret_store="memory"))
    assert app.state.k04_config_error is None, app.state.k04_config_error
    cred = app.state.k04_ctx.credential_store
    assert type(cred).__name__ == "_MemoryCredentialStore", type(cred)


def _fake_os_stack(monkeypatch, calls):
    def _fake(**kwargs):
        calls["n"] = calls.get("n", 0) + 1
        return FAC.memory_stack()

    monkeypatch.setattr(FAC, "os_stack", _fake)


def test_explicit_os_setting_wins_over_env(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENT_SI_SECRET_STORE", raising=False)
    calls: dict = {}
    _fake_os_stack(monkeypatch, calls)
    app = create_app(_settings(tmp_path, secret_store="os"))
    assert app.state.k04_config_error is None, app.state.k04_config_error
    assert calls.get("n") == 1, calls


def test_os_env_routes_to_os_stack(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SI_SECRET_STORE", "os")
    calls: dict = {}
    _fake_os_stack(monkeypatch, calls)
    app = create_app(_settings(tmp_path))
    assert app.state.k04_config_error is None, app.state.k04_config_error
    assert calls.get("n") == 1, calls
