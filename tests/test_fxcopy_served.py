# FXCOPY: copy affordance + single terminal summary (RED-first).
# 1. The native window must allow text selection (text_select=True).
# 2. Each assistant message carries a quiet Copy action (Ctrl+C untouched).
# 3. A terminal part failure emits ONE summary line, not FAILED + Needs-you
#    + run-failed repeats of the same reason.
import json
import os
import signal
import sys
import threading

import pytest
from fastapi.testclient import TestClient

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from agent_si import sidecar  # noqa: E402

from test_fxdevrun_served import (  # noqa: E402
    _audit_pass,
    _FakeFactory,
    _one_part_plan,
    _parse_sse,
    _plan_text,
    _post_chat,
    _project_dir,
    _served_app,
    _types,
    _worker_always_red,
)

_COPY_TESTID = "chat-copy"
_DIALOG_SECRET = "tok-secret-4"
_DIALOG_URL = "http://127.0.0.1:12999/?token=" + _DIALOG_SECRET


class _CopyFakeWindow:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.loaded = []

    def load_url(self, url):
        self.loaded.append(url)


class _CopyFakeWebview:
    def __init__(self):
        self.seen_kwargs = {}

    def create_window(self, title, url, **kwargs):
        self.seen_kwargs = dict(kwargs)
        width = kwargs.get("width")
        height = kwargs.get("height")
        self.window = _CopyFakeWindow(width, height)
        return self.window

    def start(self, func=None, private_mode=False, storage_path=None):
        if callable(func):
            func()
        return None


class _CopyFakeServer:
    def __init__(self, _config):
        self.started = True
        self.should_exit = False

    def run(self):
        return None


class _CopyFakeUvicorn:
    Server = _CopyFakeServer

    @staticmethod
    def Config(app, host=None, port=None, log_config=None):
        return object()


def test_copy_window_allows_text_select(monkeypatch, tmp_path):
    """create_window passes text_select=True (pywebview defaults False)."""
    data_root = str(tmp_path / "data")
    os.makedirs(data_root, exist_ok=True)
    monkeypatch.setenv("AGENT_SI_DATA_DIR", data_root)
    monkeypatch.setattr(sidecar, "_screen_work_area", lambda: (1920, 1080))

    class _State:
        ui_session_token = "tok-fxcopy"

    class _App:
        state = _State()

    monkeypatch.setattr(sidecar, "build_app", lambda: _App())
    monkeypatch.setattr(sidecar, "pick_free_port", lambda: 12798)
    fake_webview = _CopyFakeWebview()
    monkeypatch.setitem(sys.modules, "webview", fake_webview)
    monkeypatch.setitem(sys.modules, "uvicorn", _CopyFakeUvicorn())
    old_int = signal.getsignal(signal.SIGINT)
    old_term = signal.getsignal(signal.SIGTERM)
    try:
        assert sidecar.main([]) == 0
    finally:
        signal.signal(signal.SIGINT, old_int)
        signal.signal(signal.SIGTERM, old_term)
    assert fake_webview.seen_kwargs.get("text_select") is True, (
        "create_window kwargs: %r" % (fake_webview.seen_kwargs,))


def test_copy_affordance_per_assistant_message():
    """The chat component renders a quiet Copy action per assistant text."""
    path = os.path.join(
        _ROOT, "frontend", "src", "chat", "index.tsx")
    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    assert _COPY_TESTID in source, (
        "no per-assistant Copy affordance in frontend/src/chat/index.tsx")


@pytest.mark.timeout(280)
def test_terminal_failure_emits_single_summary(tmp_path):
    """Terminal FAIL: one summary line, no FAILED/Needs-you double."""
    project = "fxcopy-sum"
    folder = _project_dir(tmp_path, project)
    factory = _FakeFactory({
        "director": [_plan_text(_one_part_plan())],
        "manager": [json.dumps({"order": ["p1"]})],
        "worker": [_worker_always_red],
        "auditor": [_audit_pass],
    })
    app = _served_app(tmp_path, project, factory)
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(client, project, folder)
    assert resp.status_code == 200, resp.text
    events = _parse_sse(resp.text)
    assert _types(events)[-1] == "done", events[-2:]
    deltas = [str(event.get("text", ""))
              for event in events if event.get("type") == "delta"]
    needs_you = [text for text in deltas
                 if text.startswith("Needs you:")]
    failed = [text for text in deltas if "FAILED (" in text]
    assert needs_you == [], (
        "terminal reason repeated as a separate Needs-you line: %r"
        % (needs_you,))
    assert len(failed) == 1, (
        "expected exactly one terminal FAILED summary, got %d: %r"
        % (len(failed), failed))
    assert "needs you" in failed[0].lower(), (
        "single summary keeps the user-action signal: %r" % (failed[0],))


class _RaiseWebview:
    def create_window(self, *args, **kwargs):
        raise RuntimeError("no native window in this probe")

    def start(self, *args, **kwargs):
        raise AssertionError("fallback never starts a window")


class _NoWaitEvent(threading.Event):
    def wait(self, timeout=None):
        return True


def test_missing_window_dialog_hides_token_but_launch_keeps_it(monkeypatch):
    """Fallback dialog shows the plain address; the browser URL keeps it."""
    logged = []
    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setattr(
        sidecar, "_log", lambda message: logged.append(str(message)))
    assert sidecar._note_webview_missing(_DIALOG_URL) is False
    assert logged, "fallback dialog text reaches the stderr log"
    assert _DIALOG_SECRET not in " ".join(logged), (
        "dialog text leaks the session token: %r" % (logged,))
    assert "token=" not in " ".join(logged), (
        "dialog text carries a token query: %r" % (logged,))
    assert "http://127.0.0.1:12999/" in " ".join(logged), (
        "dialog text keeps the plain address: %r" % (logged,))


def test_missing_window_launch_url_keeps_token(monkeypatch, tmp_path):
    """Headless fallback: the opened browser URL still carries the token."""
    data_root = str(tmp_path / "data")
    os.makedirs(data_root, exist_ok=True)
    monkeypatch.setenv("AGENT_SI_DATA_DIR", data_root)
    monkeypatch.setattr(sidecar, "_screen_work_area", lambda: (1920, 1080))

    class _State:
        ui_session_token = _DIALOG_SECRET

    class _App:
        state = _State()

    monkeypatch.setattr(sidecar, "build_app", lambda: _App())
    monkeypatch.setattr(sidecar, "pick_free_port", lambda: 12998)
    # FXWV: pin the missing branch (a machine WITH the runtime would
    # otherwise take the installed notice and pop a real dialog here).
    monkeypatch.setattr(sidecar, "_read_webview2_pvs", lambda: [])
    monkeypatch.setitem(sys.modules, "webview", _RaiseWebview())
    monkeypatch.setitem(sys.modules, "uvicorn", _CopyFakeUvicorn())
    monkeypatch.setattr(sidecar.threading, "Event", _NoWaitEvent)
    launched = []
    noted = []
    monkeypatch.setattr(
        sidecar, "_open_in_browser",
        lambda url: launched.append(str(url)) or True)
    monkeypatch.setattr(
        sidecar, "_note_webview_missing",
        lambda url: noted.append(str(url)) or False)
    old_int = signal.getsignal(signal.SIGINT)
    old_term = signal.getsignal(signal.SIGTERM)
    try:
        assert sidecar.main([]) == 0
    finally:
        signal.signal(signal.SIGINT, old_int)
        signal.signal(signal.SIGTERM, old_term)
    assert launched == ["http://127.0.0.1:12998/?token=" + _DIALOG_SECRET], (
        "browser fallback launch keeps the token: %r" % (launched,))
    assert noted == launched, (
        "dialog input is the full URL (stripped inside): %r" % (noted,))
