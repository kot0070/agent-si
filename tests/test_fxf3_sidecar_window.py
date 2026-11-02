# F3: sidecar native window size (RED-first).
# create_window opened 800x600 (pywebview default), hiding nav behind
# the condensed bar. The window now opens 1280x800, capped to the
# screen work area (floor 1024x700, cap wins on tiny screens); the
# close size is saved in the DATA DIR (never localStorage: the UI
# origin port changes every launch) and restored + capped next start.
import json
import os
import signal
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from agent_si import sidecar  # noqa: E402


def test_default_kept_on_normal_screen(monkeypatch):
    """Normal screen: default 1280x800 is kept (no record)."""
    monkeypatch.setattr(sidecar, "_screen_work_area", lambda: (1920, 1080))
    assert sidecar.resolve_window_size(None) == (1280, 800)


def test_cap_applies_on_small_screen(monkeypatch):
    """Small screen: default is capped to the work area."""
    monkeypatch.setattr(sidecar, "_screen_work_area", lambda: (1100, 700))
    assert sidecar.resolve_window_size(None) == (1100, 700)


def test_minimum_floor_applies(monkeypatch, tmp_path):
    """A tiny saved record is floored to 1024x700 on a big screen."""
    monkeypatch.setattr(sidecar, "_screen_work_area", lambda: (1920, 1080))
    root = str(tmp_path / "data")
    os.makedirs(root, exist_ok=True)
    sidecar._write_window_size(
        sidecar._window_size_file_path(root), 100, 100)
    assert sidecar.resolve_window_size(root) == (1024, 700)


def test_malformed_record_falls_back_to_default(monkeypatch, tmp_path):
    """Garbage in the size file: default (capped) is used, no crash."""
    monkeypatch.setattr(sidecar, "_screen_work_area", lambda: (1920, 1080))
    root = str(tmp_path / "data")
    os.makedirs(root, exist_ok=True)
    with open(sidecar._window_size_file_path(root), "w",
              encoding="utf-8") as handle:
        handle.write("not-json{")
    assert sidecar.resolve_window_size(root) == (1280, 800)


def test_save_restore_roundtrip_and_capped_restore(monkeypatch, tmp_path):
    """Close size persists in the DATA DIR file; restore caps it."""
    root = str(tmp_path / "data")
    os.makedirs(root, exist_ok=True)
    path = sidecar._window_size_file_path(root)
    assert os.path.dirname(path) == os.path.abspath(root)
    sidecar._write_window_size(path, 1400, 900)
    monkeypatch.setattr(sidecar, "_screen_work_area", lambda: (1920, 1080))
    assert sidecar.resolve_window_size(root) == (1400, 900)
    monkeypatch.setattr(sidecar, "_screen_work_area", lambda: (1100, 700))
    assert sidecar.resolve_window_size(root) == (1100, 700)


class _FakeWindow:
    def __init__(self, width, height):
        self.width = width
        self.height = height


class _FakeWebview:
    instances = ()

    def __init__(self):
        self.seen = {}
        self.started = {}
        # FXHYGIENE: recorders for the stubbed fallbacks (no test may
        # open a native dialog or a browser: _run_main_with_screen
        # replaces sidecar._open_in_browser/_note_webview_missing).
        self.browser_urls = []
        self.missing_notes = []

    def create_window(self, title, url, width=None, height=None, **kwargs):
        self.seen = {"title": title, "url": url,
                     "width": width, "height": height, **kwargs}
        self.window = _FakeWindow(width, height)
        return self.window

    def start(self, private_mode=False, storage_path=None):
        self.started = {"private_mode": private_mode,
                        "storage_path": storage_path}


class _FakeServer:
    def __init__(self, _config):
        self.started = True
        self.should_exit = False

    def run(self):
        return None


class _FakeUvicorn:
    Server = _FakeServer

    @staticmethod
    def Config(app, host=None, port=None, log_config=None):
        return object()


def _run_main_with_screen(monkeypatch, tmp_path, work):
    """Run sidecar.main() with fake uvicorn/webview; return webview fake."""
    data_root = str(tmp_path / "data")
    os.makedirs(data_root, exist_ok=True)
    monkeypatch.setenv("AGENT_SI_DATA_DIR", data_root)
    monkeypatch.setattr(sidecar, "_screen_work_area", lambda: work)

    class _State:
        ui_session_token = "tok-for-size"

    class _App:
        state = _State()

    monkeypatch.setattr(sidecar, "build_app", lambda: _App())
    monkeypatch.setattr(sidecar, "pick_free_port", lambda: 12799)
    fake_webview = _FakeWebview()
    # FXHYGIENE: stub BOTH real fallbacks (browser + native message
    # box): any exception in main()'s try would otherwise open a real
    # browser tab and a real MessageBoxW carrying the test token URL.
    monkeypatch.setattr(
        sidecar, "_open_in_browser",
        lambda url: fake_webview.browser_urls.append(url) or False)
    monkeypatch.setattr(
        sidecar, "_note_webview_missing",
        lambda url: fake_webview.missing_notes.append(url) or False)
    monkeypatch.setitem(sys.modules, "webview", fake_webview)
    monkeypatch.setitem(sys.modules, "uvicorn", _FakeUvicorn())
    old_int = signal.getsignal(signal.SIGINT)
    old_term = signal.getsignal(signal.SIGTERM)
    try:
        assert sidecar.main([]) == 0
    finally:
        signal.signal(signal.SIGINT, old_int)
        signal.signal(signal.SIGTERM, old_term)
    return data_root, fake_webview


def test_main_passes_default_size_and_saves_it(monkeypatch, tmp_path):
    """LIVE main(): create_window gets 1280x800; close size lands in DATA DIR."""
    data_root, fake = _run_main_with_screen(
        monkeypatch, tmp_path, (1920, 1080))
    assert fake.seen["width"] == 1280
    assert fake.seen["height"] == 800
    assert fake.browser_urls == []
    assert fake.missing_notes == []
    assert fake.seen.get("text_select") is True
    with open(sidecar._window_size_file_path(data_root),
              encoding="utf-8") as handle:
        saved = json.load(handle)
    assert (int(saved["width"]), int(saved["height"])) == (1280, 800)


def test_main_caps_size_on_small_screen(monkeypatch, tmp_path):
    """LIVE main(): small work area caps the created window."""
    _, fake = _run_main_with_screen(monkeypatch, tmp_path, (1100, 700))
    assert fake.seen["width"] == 1100
    assert fake.seen["height"] == 700
    assert fake.browser_urls == []
    assert fake.missing_notes == []
    assert fake.seen.get("text_select") is True
