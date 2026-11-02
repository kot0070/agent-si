"""H8: instant window with splash, then app; failure names reason + logs (RED-first).

RC5 boot took 22.5 s in a test window (blocking service probes on the
server loop + frozen unpack). The window must appear at once with a
local splash ("Starting Agent SI... first start can take up to a
minute"), then navigate to the app; a backend that never gets ready
shows the reason plus the log folder. Served-path tests through
sidecar.main with a stubbed native window.
"""
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


def test_splash_names_startup_and_holds_no_secret():
    """The local splash page carries the wait line, never a token."""
    html = sidecar._splash_html()
    assert "Starting Agent SI" in html
    assert "minute" in html
    assert "token" not in html.lower()
    assert "http" not in html


def test_failure_page_names_reason_and_log_folder(tmp_path):
    """The failure page carries the reason plus the log folder path."""
    html = sidecar._failure_html(
        "server did not start", str(tmp_path / "logs"))
    assert "server did not start" in html
    assert str(tmp_path / "logs") in html


class _FakeWindow:
    def __init__(self):
        self.loaded = []
        self.width = 1280
        self.height = 800

    def load_url(self, url):
        self.loaded.append(url)


class _FakeServer:
    started = False

    def __init__(self, config):
        self.config = config
        self.should_exit = False

    def run(self):
        return None


def _stub_webview(monkeypatch):
    window = _FakeWindow()
    stub = types.SimpleNamespace(
        windows=[window],
        created=[],
    )

    def _create_window(title, url=None, html=None, **kwargs):
        stub.created.append({"title": title, "url": url, "html": html})
        return window

    stub.create_window = _create_window
    stub.started = []

    def _start(*args, **kwargs):
        stub.started.append((args, kwargs))
        return None

    stub.start = _start
    monkeypatch.setitem(sys.modules, "webview", stub)
    return window, stub


def _stub_server(monkeypatch, started):
    import uvicorn

    class _Server(_FakeServer):
        pass

    _Server.started = started
    monkeypatch.setattr(uvicorn, "Server", _Server)


def test_backend_never_ready_shows_failure(monkeypatch, tmp_path):
    """A backend that never starts: splash first, then reason + logs."""
    import uvicorn  # noqa: F401

    monkeypatch.setenv("AGENT_SI_DATA_DIR", str(tmp_path / "data"))
    window, stub = _stub_webview(monkeypatch)
    _stub_server(monkeypatch, started=False)
    code = sidecar.main([])
    assert code == 1
    assert stub.created, "the window must appear at once, before the backend"
    assert "Starting Agent SI" in (stub.created[0]["html"] or "")
    assert window.loaded, "the failure page must load into the window"
    assert "server did not start" in window.loaded[0]
    assert "logs" in window.loaded[0]


def test_backend_ready_navigates_to_app(monkeypatch, tmp_path):
    """A backend that starts: splash first, then the app URL with token."""
    import uvicorn  # noqa: F401

    monkeypatch.setenv("AGENT_SI_DATA_DIR", str(tmp_path / "data"))
    window, stub = _stub_webview(monkeypatch)
    _stub_server(monkeypatch, started=True)
    code = sidecar.main([])
    assert code == 0
    assert stub.created, "the window must appear at once, before the backend"
    assert "Starting Agent SI" in (stub.created[0]["html"] or "")
    assert window.loaded, "the app URL must load into the window"
    assert window.loaded[0].startswith("http://127.0.0.1:")
    assert "token=" in window.loaded[0]
