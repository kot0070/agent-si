# FXBOOT: navigate after GUI is up (RED-first).
# Exe stayed on splash `Запуск...`; logs showed
# `window navigation failed (Main window failed to start)` while the server
# answered 200. Cause: window.load_url(url) ran BEFORE _webview.start(...);
# pywebview load_url waits for the shown window, which cannot happen before
# start. Fix: navigate from the func pywebview runs after the GUI is up,
# for BOTH the app URL and the failure HTML. A failed app navigation falls
# back to the browser + the WebView2 note so no still splash remains.
import os
import sys
import types

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from agent_si import sidecar  # noqa: E402


class _RealWindow:
    """Acts like the real pywebview window: load_url fails pre-start."""

    def __init__(self):
        self.loaded = []
        self.width = 1280
        self.height = 800
        self._begun = False

    def load_url(self, url):
        if not self._begun:
            raise RuntimeError("Main window failed to start")
        self.loaded.append(url)


class _RealWebview:
    """Acts like real pywebview: start(func, ...) runs func after GUI up."""

    def __init__(self):
        self.window = _RealWindow()
        self.start_calls = []
        self.func_ran = []

    def create_window(self, title, url=None, html=None, **kwargs):
        return self.window

    def start(self, func=None, *args, **kwargs):
        self.start_calls.append((func, args, kwargs))
        self.window._begun = True
        if callable(func):
            self.func_ran.append(True)
            func()
        return None


class _FakeServer:
    def __init__(self, _config):
        self.should_exit = False

    def run(self):
        return None


def _stub(monkeypatch, tmp_path, started, webview):
    import uvicorn

    data_root = str(tmp_path / "data")
    os.makedirs(data_root, exist_ok=True)
    monkeypatch.setenv("AGENT_SI_DATA_DIR", data_root)
    monkeypatch.setenv("AGENT_SI_LOCALE", "en")

    class _State:
        ui_session_token = "tok-fxboot"

    class _App:
        state = _State()

    monkeypatch.setattr(sidecar, "build_app", lambda: _App())
    monkeypatch.setattr(sidecar, "pick_free_port", lambda: 12799)

    class _Server(_FakeServer):
        pass

    _Server.started = started
    monkeypatch.setattr(uvicorn, "Server", _Server)
    monkeypatch.setitem(sys.modules, "webview", webview)
    monkeypatch.setattr(
        sidecar, "_open_in_browser", lambda url: webview.browser.append(url))
    monkeypatch.setattr(
        sidecar, "_note_webview_missing",
        lambda url: webview.notes.append(url))
    webview.browser = []
    webview.notes = []
    return data_root


def test_app_navigates_inside_start(monkeypatch, tmp_path):
    """Success path: app URL loads via the start func (not before)."""
    import signal

    webview = _RealWebview()
    _stub(monkeypatch, tmp_path, True, webview)
    old_int = signal.getsignal(signal.SIGINT)
    old_term = signal.getsignal(signal.SIGTERM)
    try:
        assert sidecar.main([]) == 0
    finally:
        signal.signal(signal.SIGINT, old_int)
        signal.signal(signal.SIGTERM, old_term)
    assert webview.func_ran, "start must run the navigate func"
    assert webview.window.loaded, "app URL must load into the window"
    assert webview.window.loaded[0].startswith("http://127.0.0.1:")
    assert "token=" in webview.window.loaded[0]
    assert webview.browser == []
    assert webview.notes == []


def test_failure_navigates_inside_start(monkeypatch, tmp_path):
    """Failure path: failure HTML loads via the start func (not before)."""
    webview = _RealWebview()
    _stub(monkeypatch, tmp_path, False, webview)
    assert sidecar.main([]) == 1
    assert webview.func_ran, "start must run the failure func"
    assert webview.window.loaded, "failure page must load into the window"
    assert "did not start" in webview.window.loaded[0]
