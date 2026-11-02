# FXPORTABLE served tests (P1/P3/P5-guard): portable-exe defaults.
#
# Served = the real product app (agent_si.backend.app.create_app,
# untouched) plus the real sidecar helpers and the real CODE executor.
# P1: frozen bundle with no AGENT_SI_DATA_DIR defaults to <exe>/data
# (created on demand), read-only exe folder falls back to
# %LOCALAPPDATA%/AgentSI/data; env still wins; the key-save route
# answers 201 through the default dir. P3: a forced webview import
# failure opens the same URL in the browser and names the WebView2
# download link; a live port record reattaches instead of starting a
# second server. P5-guard: no python on PATH answers BLOCKED naming
# the fix, never a bare 500. P2 (FirstRunGate) is a UI rule: proved by
# tsc plus frontend/src/app/__tests__/fxkitui.test.tsx (9/10; the one
# old-contract fixture is reported, not edited here). P4/P5-exe and P6
# are RC3 pre-check notes (built exe, clean env), not unit tests.
import os
import shutil
import socket
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest  # noqa: E402

from agent_si import k10_start, sidecar  # noqa: E402
from agent_si.test_runners import code_executor  # noqa: E402

FAKE_EXE_DIRNAME = "bundle"


def _freeze(monkeypatch, exe_path):
    """Fake a frozen bundle: sys.frozen True, sys.executable the exe."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_path), raising=False)


def _unfrozen(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)


def _fake_exe(tmp_path):
    exe_dir = tmp_path / FAKE_EXE_DIRNAME
    exe_dir.mkdir()
    return str(exe_dir / "AgentSI.exe")


# --- P1: frozen data-dir default -------------------------------------------


def test_fxportable_p1_frozen_defaults_to_exe_data(tmp_path, monkeypatch):
    """Frozen + no env: data dir is <exe>/data, created on demand."""
    monkeypatch.delenv("AGENT_SI_DATA_DIR", raising=False)
    _freeze(monkeypatch, _fake_exe(tmp_path))
    resolved = k10_start.resolve_env_data_dir()
    assert resolved == os.path.abspath(
        os.path.join(str(tmp_path), FAKE_EXE_DIRNAME, "data"))
    assert os.path.isdir(resolved)


def test_fxportable_p1_env_still_wins(tmp_path, monkeypatch):
    """Frozen + env set: the env dir wins, exe data is not created."""
    from agent_si.backend.app import get_data_dir

    wanted = tmp_path / "custom-data"
    monkeypatch.setenv("AGENT_SI_DATA_DIR", str(wanted))
    _freeze(monkeypatch, _fake_exe(tmp_path))
    resolved = k10_start.resolve_env_data_dir()
    assert resolved == os.path.abspath(str(wanted))
    assert os.path.isdir(str(wanted))
    assert not os.path.exists(
        os.path.join(str(tmp_path), FAKE_EXE_DIRNAME, "data"))
    assert get_data_dir() == os.path.abspath(str(wanted))


def test_fxportable_p1_readonly_exe_falls_back_to_localappdata(
        tmp_path, monkeypatch):
    """Frozen + unwritable exe folder: %LOCALAPPDATA%/AgentSI/data."""
    monkeypatch.delenv("AGENT_SI_DATA_DIR", raising=False)
    exe = _fake_exe(tmp_path)
    _freeze(monkeypatch, exe)
    local_app = tmp_path / "localappdata"
    local_app.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(local_app))
    real_makedirs = os.makedirs

    def _guarded(path, *args, **kwargs):
        if os.path.abspath(str(path)).startswith(
                os.path.abspath(str(tmp_path / FAKE_EXE_DIRNAME))):
            raise PermissionError("read-only install dir")
        return real_makedirs(path, *args, **kwargs)

    monkeypatch.setattr(os, "makedirs", _guarded)
    monkeypatch.setattr(k10_start.os, "makedirs", _guarded)
    resolved = k10_start.resolve_env_data_dir()
    assert resolved == os.path.abspath(
        os.path.join(str(local_app), "AgentSI", "data"))
    assert os.path.isdir(resolved)


def test_fxportable_p1_unfrozen_stays_none(tmp_path, monkeypatch):
    """Unfrozen + no env: no default (legacy no-dir path untouched)."""
    monkeypatch.delenv("AGENT_SI_DATA_DIR", raising=False)
    _unfrozen(monkeypatch)
    assert k10_start.resolve_env_data_dir() is None


def test_fxportable_p1_key_save_201_with_default_dir(tmp_path, monkeypatch):
    """Frozen + no env: K04 configured off the default dir, key save 201."""
    from fastapi.testclient import TestClient

    from agent_si.backend.app import create_app

    monkeypatch.delenv("AGENT_SI_DATA_DIR", raising=False)
    _freeze(monkeypatch, _fake_exe(tmp_path))
    app = create_app({"secret_store": "memory", "testing": True})
    assert app.state.data_dir == os.path.abspath(
        os.path.join(str(tmp_path), FAKE_EXE_DIRNAME, "data"))
    client = TestClient(app)
    token = app.state.ui_session_token
    resp = client.post(
        "/api/v1/providers/keys",
        json={"preset_id": "openai", "key_value": "FAKE-fxportable-p1"},
        headers={"x-actor": "fxportable", "x-ui-session-token": token},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["key_ref"]["secret_id"] == "openai"
    assert "FAKE-fxportable-p1" not in resp.text


def test_fxportable_p1_audit_path_under_data_dir(tmp_path, monkeypatch):
    """Frozen: audit path lives under the data dir, not beside the exe."""
    from agent_si.providers.registry import facades

    monkeypatch.delenv("AGENT_SI_DATA_DIR", raising=False)
    _freeze(monkeypatch, _fake_exe(tmp_path))
    path = facades.default_audit_path()
    assert os.path.abspath(path).startswith(
        os.path.abspath(
            os.path.join(str(tmp_path), FAKE_EXE_DIRNAME, "data")) + os.sep)
    assert path.endswith("provider_audit.jsonl")


# --- P3: webview-absent fallback + single instance -------------------------


def test_fxportable_p3_browser_fallback_on_webview_failure(monkeypatch):
    """Forced webview import failure: browser opens, link is named."""
    opened = []
    monkeypatch.setitem(sys.modules, "webview", None)
    import webbrowser

    monkeypatch.setattr(
        webbrowser, "open", lambda url: opened.append(url) or True)
    monkeypatch.setattr(sidecar.os, "name", "posix")
    url = "http://127.0.0.1:9/?token=t"
    assert sidecar._open_in_browser(url) is True
    assert opened == [url]
    assert sidecar._note_webview_missing(url) is False
    assert sidecar._WEBVIEW2_DOWNLOAD_URL.startswith("https://")


def test_fxportable_p3_single_instance_reattaches(monkeypatch, tmp_path):
    """Live port record: same URL opened, no second server started."""
    opened = []
    monkeypatch.setattr(
        sidecar, "_open_in_browser", lambda url: opened.append(url) or True)
    monkeypatch.setattr(
        sidecar, "_sidecar_data_dir", lambda: str(tmp_path))
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((sidecar.HOST, 0))
    sock.listen(1)
    port = int(sock.getsockname()[1])
    try:
        path = sidecar._port_file_path(str(tmp_path))
        sidecar._write_port_file(path, port, "tok-1")
        assert sidecar._reattach_running() is True
        assert opened == ["http://" + sidecar.HOST + ":"
                          + str(port) + "/?token=tok-1"]
    finally:
        sock.close()
    assert sidecar._reattach_running() is False
    assert not os.path.exists(path)


def test_fxportable_p3_no_record_means_first_start(monkeypatch, tmp_path):
    """No port record: first start proceeds (no reattach)."""
    monkeypatch.setattr(
        sidecar, "_sidecar_data_dir", lambda: str(tmp_path))
    assert sidecar._reattach_running() is False


# --- P5-guard: honest BLOCKED without python -------------------------------


def _freeze_without_python(monkeypatch, tmp_path):
    monkeypatch.delenv("AGENT_SI_DATA_DIR", raising=False)
    monkeypatch.delenv("AGENT_SI_PYTHON", raising=False)
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    _freeze(monkeypatch, _fake_exe(tmp_path))


def test_fxportable_p5_no_python_blocked_not_500(tmp_path, monkeypatch):
    """Frozen + no python: resolver refuses naming the fix, not raise."""
    _freeze_without_python(monkeypatch, tmp_path)
    project = tmp_path / "proj"
    project.mkdir()
    (project / "test_probe.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8")
    argv, reason = code_executor.resolve_code_command(
        project_dir=str(project), test_id="probe")
    assert argv is None
    assert reason is not None and "AGENT_SI_PYTHON" in reason
    with pytest.raises(code_executor.ExecutorBlocked):
        code_executor.execute_code_test(
            data_root=str(tmp_path / "data"), project_id="p1",
            test_id="probe")


def test_fxportable_p5_catalog_reports_blocked(tmp_path, monkeypatch):
    """Frozen + no python: catalog CODE test is BLOCKED, never 500."""
    _freeze_without_python(monkeypatch, tmp_path)
    project = tmp_path / "proj"
    project.mkdir()
    (project / "test_probe.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8")
    outcome = code_executor.execute_catalog_test(
        test_id="probe", kind="CODE", intent="", project_id="p1",
        data_root=str(tmp_path / "data"), project_dir=str(project))
    assert outcome["status"] == "BLOCKED"
    assert "python" in str(outcome["reason"]).lower()
