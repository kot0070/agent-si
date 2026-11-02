# FXWV: WebView2-runtime diagnosis (RED-first).
# The fallback box said "WebView2 runtime is missing" for EVERY window
# failure (import error, dead window, start error), even on machines
# WITH the runtime installed. Now: missing is said only when the
# EdgeUpdate client key carries no real pv; an installed runtime gets
# a different plain notice; the frozen exe unblocks its own files.
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

_SECRET = "tok-secret-9"
_URL = "http://127.0.0.1:12997/?token=" + _SECRET
_PLAIN = "http://127.0.0.1:12997/"


class _DeadStartWebview:
    """create_window works, start() raises (the juror's path)."""

    def create_window(self, *args, **kwargs):
        return object()

    def start(self, *args, **kwargs):
        raise RuntimeError("boom-start")


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


class _NoWaitEvent(sidecar.threading.Event):
    def wait(self, timeout=None):
        return True


def _run_main(monkeypatch, tmp_path, webview_mod, pvs):
    """Real main() with registry read + webview import faked at the boundary."""
    data_root = str(tmp_path / "data")
    os.makedirs(data_root, exist_ok=True)
    monkeypatch.setenv("AGENT_SI_DATA_DIR", data_root)
    monkeypatch.setattr(sidecar, "_screen_work_area", lambda: (1920, 1080))

    class _State:
        ui_session_token = _SECRET

    class _App:
        state = _State()

    monkeypatch.setattr(sidecar, "build_app", lambda: _App())
    monkeypatch.setattr(sidecar, "pick_free_port", lambda: 12997)
    monkeypatch.setattr(sidecar, "_read_webview2_pvs", lambda: list(pvs))
    monkeypatch.setitem(sys.modules, "webview", webview_mod)
    monkeypatch.setitem(sys.modules, "uvicorn", _FakeUvicorn())
    monkeypatch.setattr(sidecar.threading, "Event", _NoWaitEvent)
    launched = []
    missing_notes = []
    failed_notes = []
    monkeypatch.setattr(
        sidecar, "_open_in_browser",
        lambda url: launched.append(str(url)) or True)
    monkeypatch.setattr(
        sidecar, "_note_webview_missing",
        lambda url: missing_notes.append(str(url)) or False)
    monkeypatch.setattr(
        sidecar, "_note_window_open_failed",
        lambda url, reason, log_file: failed_notes.append(
            (str(url), str(reason), log_file)) or False)
    old_int = signal.getsignal(signal.SIGINT)
    old_term = signal.getsignal(signal.SIGTERM)
    try:
        assert sidecar.main([]) == 0
    finally:
        signal.signal(signal.SIGINT, old_int)
        signal.signal(signal.SIGTERM, old_term)
    return launched, missing_notes, failed_notes


def test_main_missing_note_when_runtime_absent(monkeypatch, tmp_path):
    """No pv anywhere: start error keeps the current missing text."""
    launched, missing, failed = _run_main(
        monkeypatch, tmp_path, _DeadStartWebview(), [])
    assert launched == [_URL], "browser fallback still opens: %r" % (launched,)
    assert failed == [], "installed notice must not fire: %r" % (failed,)
    assert missing == [_URL], "missing notice keeps firing: %r" % (missing,)


def test_main_open_failed_note_when_runtime_present(monkeypatch, tmp_path):
    """Real pv: no word 'missing'; reason + log path travel along."""
    launched, missing, failed = _run_main(
        monkeypatch, tmp_path, _DeadStartWebview(), ["156.0.4314.58"])
    assert launched == [_URL], "browser fallback still opens: %r" % (launched,)
    assert missing == [], "missing notice must stay silent: %r" % (missing,)
    assert len(failed) == 1, "installed notice fires once: %r" % (failed,)
    url, reason, log_file = failed[0]
    assert url == _URL
    assert "RuntimeError" in reason and "boom-start" in reason, (
        "real cause with its type: %r" % (reason,))
    assert log_file and log_file.endswith("agent-si.log"), (
        "log file path travels along: %r" % (log_file,))


def test_main_import_failure_keeps_real_cause(monkeypatch, tmp_path):
    """webview import error + installed runtime: cause is the ImportError."""
    launched, missing, failed = _run_main(
        monkeypatch, tmp_path, None, ["156.0.4314.58"])
    assert launched == [_URL]
    assert missing == []
    assert len(failed) == 1
    _url, reason, _log = failed[0]
    assert "ImportError" in reason or "ModuleNotFoundError" in reason, (
        "import cause (ImportError family) kept: %r" % (reason,))


def test_fallback_log_carries_exception_type(monkeypatch, tmp_path):
    """The data-dir log line names the exception type, not just text."""
    logged = []
    monkeypatch.setattr(
        sidecar, "_log", lambda message: logged.append(str(message)))
    _run_main(monkeypatch, tmp_path, _DeadStartWebview(), ["1.2.3.4"])
    line = " ".join(logged)
    assert "RuntimeError" in line and "boom-start" in line, (
        "type + text in the log: %r" % (logged,))


def test_missing_notice_text_unchanged(monkeypatch):
    """Not installed: the current text (missing + download link, no token)."""
    logged = []
    monkeypatch.setattr(sidecar.os, "name", "posix")
    monkeypatch.setattr(
        sidecar, "_log", lambda message: logged.append(str(message)))
    assert sidecar._note_webview_missing(_URL) is False
    text = " ".join(logged)
    assert "missing" in text.lower(), "current wording kept: %r" % (text,)
    assert _SECRET not in text and "token=" not in text
    assert _PLAIN in text


def test_open_failed_notice_text(monkeypatch, tmp_path):
    """Installed: plain words, no 'missing', no token, reason + log path."""
    logged = []
    monkeypatch.setattr(sidecar.os, "name", "posix")
    monkeypatch.setattr(
        sidecar, "_log", lambda message: logged.append(str(message)))
    log_file = str(tmp_path / "agent-si.log")
    assert sidecar._note_window_open_failed(
        _URL, "RuntimeError: boom-start", log_file) is False
    text = " ".join(logged)
    assert "missing" not in text.lower(), "never says missing: %r" % (text,)
    assert _SECRET not in text and "token=" not in text, (
        "no token in the box: %r" % (text,))
    assert _PLAIN in text, "plain address kept: %r" % (text,)
    assert "boom-start" in text, "one-line reason kept: %r" % (text,)
    assert log_file in text, "log file path named: %r" % (text,)


def _mark(path):
    with open(path + ":Zone.Identifier", "w") as handle:
        handle.write("[ZoneTransfer]\r\nZoneId=3\r\n")


def test_unblock_removes_mark_keeps_content(tmp_path):
    """Marked temp folder: streams gone after unblock, bytes untouched."""
    root = str(tmp_path / "app")
    os.makedirs(os.path.join(root, "sub"), exist_ok=True)
    files = [os.path.join(root, "a.dll"), os.path.join(root, "sub", "b.pyd")]
    for path in files:
        with open(path, "w") as handle:
            handle.write("PAYLOAD-" + os.path.basename(path))
        _mark(path)
    assert sidecar._unblock_zone_identifiers(root) == 2
    for path in files:
        assert not os.path.exists(path + ":Zone.Identifier")
        with open(path) as handle:
            assert handle.read() == "PAYLOAD-" + os.path.basename(path)


def test_unblock_default_root_is_frozen_only(monkeypatch):
    """Source checkout (not frozen): the exe folder is never walked."""
    monkeypatch.delattr(sys, "frozen", raising=False)

    def _boom(*args, **kwargs):
        raise AssertionError("must not walk outside the frozen exe")

    monkeypatch.setattr(sidecar.os, "walk", _boom)
    assert sidecar._unblock_zone_identifiers() == 0
