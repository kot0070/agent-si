# FXINST: single instance per data folder (RED-first).
# Lock (port + pid) under the data dir; second launch checks pid alive +
# health, POSTs the loopback focus route (window show + restore + focus),
# exits 0; stale is removed, start proceeds; window closed but backend
# ending: wait up to 5 s, then start; browser fallback only for no-WebView2.
# AGENT_SI_ALLOW_MULTI=1 skips the lock for test copies only.
import json
import os
import socket
import sys
import threading
import time

from http.server import BaseHTTPRequestHandler, HTTPServer

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest  # noqa: E402

from agent_si import sidecar  # noqa: E402


class _ProbeHandler(BaseHTTPRequestHandler):
    """Minimal healthy-instance probe: about 200, focus captured."""

    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/api/v1/sidecar/about":
            body = b'{"status":"ok"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/api/v1/sidecar/focus":
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                self.rfile.read(length)
            self.server.focus_hits.append(dict(self.headers))
            body = b'{"focused":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()


def _free_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((sidecar.HOST, 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def _start_probe():
    server = HTTPServer((sidecar.HOST, 0), _ProbeHandler)
    server.focus_hits = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _dead_pid():
    return 2 ** 30 + 7


def test_fxinst_alive_record_focuses_never_browser(monkeypatch, tmp_path):
    """Live pid + answering health: focus POST, exit-path, no browser."""
    server = _start_probe()
    try:
        port = int(server.server_address[1])
        root = str(tmp_path)
        monkeypatch.setattr(
            sidecar, "_open_in_browser",
            lambda url: (_ for _ in ()).throw(
                AssertionError("loser opened a browser: %r" % url)))
        port_path = sidecar._port_file_path(root)
        sidecar._write_port_file(
            port_path, port, "tok-focus", pid=os.getpid())
        assert sidecar._single_instance_gate(root) == "focused"
        assert len(server.focus_hits) == 1
        assert not os.path.exists(sidecar._lock_file_path(root))
    finally:
        server.shutdown()


def test_fxinst_dead_pid_is_stale_and_proceeds(monkeypatch, tmp_path):
    """Dead pid: record cleared, start proceeds, no focus, no browser."""
    posted = []
    monkeypatch.setattr(
        sidecar, "_post_focus_request",
        lambda port, token, timeout=3.0: posted.append(port) or True)
    monkeypatch.setattr(
        sidecar, "_open_in_browser",
        lambda url: (_ for _ in ()).throw(
            AssertionError("stale path opened a browser")))
    root = str(tmp_path)
    port_path = sidecar._port_file_path(root)
    sidecar._write_port_file(
        port_path, _free_port(), "tok-dead", pid=_dead_pid())
    assert sidecar._single_instance_gate(root) == "proceed"
    assert not os.path.exists(port_path)
    assert posted == []
    sidecar._release_startup_lock(sidecar._lock_file_path(root))


def test_fxinst_malformed_record_is_stale(monkeypatch, tmp_path):
    """Garbage record: treated as absent, start proceeds."""
    root = str(tmp_path)
    port_path = sidecar._port_file_path(root)
    with open(port_path, "w", encoding="utf-8") as handle:
        handle.write("not-a-port\n")
    assert sidecar._single_instance_gate(root) == "proceed"
    assert not os.path.exists(port_path)
    sidecar._release_startup_lock(sidecar._lock_file_path(root))


def test_fxinst_port_busy_by_other_program_is_stale(monkeypatch, tmp_path):
    """Port live but pid dead and no health: another program, proceed."""
    posted = []
    monkeypatch.setattr(
        sidecar, "_post_focus_request",
        lambda port, token, timeout=3.0: posted.append(port) or True)
    monkeypatch.setattr(
        sidecar, "_open_in_browser",
        lambda url: (_ for _ in ()).throw(
            AssertionError("busy-port path opened a browser")))
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((sidecar.HOST, 0))
    sock.listen(1)
    try:
        port = int(sock.getsockname()[1])
        root = str(tmp_path)
        port_path = sidecar._port_file_path(root)
        sidecar._write_port_file(
            port_path, port, "tok-busy", pid=_dead_pid())
        assert sidecar._single_instance_gate(root) == "proceed"
        assert not os.path.exists(port_path)
        assert posted == []
    finally:
        sock.close()
        sidecar._release_startup_lock(
            sidecar._lock_file_path(str(tmp_path)))


def test_fxinst_ending_backend_waits_then_starts(monkeypatch, tmp_path):
    """Pid alive, port dead (window closed, backend ending): 5 s then start."""
    root = str(tmp_path)
    port_path = sidecar._port_file_path(root)
    sidecar._write_port_file(
        port_path, _free_port(), "tok-ending", pid=os.getpid())
    started = time.monotonic()
    assert sidecar._single_instance_gate(
        root, loser_wait=2.0, end_wait=1.0) == "proceed"
    assert time.monotonic() - started >= 1.0
    assert not os.path.exists(port_path)
    sidecar._release_startup_lock(sidecar._lock_file_path(root))


def test_fxinst_focus_route_token_rule(monkeypatch):
    """Served focus route: 401 no actor, 403 bad token, 200 brings front."""
    from fastapi.testclient import TestClient

    seen = []
    monkeypatch.setattr(
        sidecar, "_bring_window_to_front",
        lambda: seen.append(1) or True)
    app = sidecar.build_app()
    client = TestClient(app, raise_server_exceptions=False)
    token = app.state.ui_session_token
    assert client.post("/api/v1/sidecar/focus").status_code == 401
    resp = client.post(
        "/api/v1/sidecar/focus",
        headers={"x-actor": "fxinst", "x-ui-session-token": "bad"})
    assert resp.status_code == 403, resp.text
    resp = client.post(
        "/api/v1/sidecar/focus",
        headers={"x-actor": "fxinst", "x-ui-session-token": token})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"focused": True}
    assert seen == [1]
    monkeypatch.setattr(
        sidecar, "_bring_window_to_front", lambda: False)
    resp = client.post(
        "/api/v1/sidecar/focus",
        headers={"x-actor": "fxinst", "x-ui-session-token": token})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"focused": False}


class _CountWebview:
    """Fake webview: counts windows; start blocks until released."""

    def __init__(self, gate):
        self._gate = gate
        self.windows_created = 0
        self._lock = threading.Lock()
        self.windows = []

    def create_window(self, title, url, **kwargs):
        with self._lock:
            self.windows_created += 1

        class _Win:
            width = kwargs.get("width", 1280)
            height = kwargs.get("height", 800)

            def show(self):
                pass

            def restore(self):
                pass

            def bring_to_front(self):
                pass

        window = _Win()
        self.windows.append(window)
        return window

    def start(self, private_mode=False, storage_path=None):
        self._gate.wait(120)


def _shim_uvicorn(monkeypatch, counter):
    """Count backend builds by wrapping sidecar._make_config.

    The real uvicorn module stays intact (its loop/policy submodule
    imports keep working); only the config build is counted.
    """
    import uvicorn as _real

    def _counting_config(app, port, host=None, log_config=None):
        counter["builds"] += 1
        return _real.Config(
            app, host=host or sidecar.HOST, port=port,
            log_config=log_config)

    monkeypatch.setattr(sidecar, "_make_config", _counting_config)


def test_fxinst_five_concurrent_starts_one_backend_one_window(
        monkeypatch, tmp_path):
    """5 starts at once on a fresh data folder: 1 backend + 1 window."""
    import uvicorn as _real  # noqa: F401

    data_root = str(tmp_path / "data")
    os.makedirs(data_root, exist_ok=True)
    monkeypatch.setenv("AGENT_SI_DATA_DIR", data_root)
    monkeypatch.delenv("AGENT_SI_ALLOW_MULTI", raising=False)
    gate = threading.Event()
    fake_webview = _CountWebview(gate)
    monkeypatch.setitem(sys.modules, "webview", fake_webview)
    counter = {"builds": 0}
    _shim_uvicorn(monkeypatch, counter)
    # Warm the product app build once: module imports dominate the
    # first build (~10 s); the raced builds must fit main's 20 s
    # server-start wait.
    sidecar.build_app()
    results = [None] * 5

    def _run(index):
        try:
            results[index] = sidecar.main([])
        except Exception as exc:  # noqa: BLE001
            results[index] = "EXC %r" % (exc,)

    threads = [threading.Thread(target=_run, args=(i,), daemon=True)
               for i in range(5)]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        alive = sum(1 for thread in threads if thread.is_alive())
        focused = sum(1 for value in results if value == 0)
        if alive == 1 and focused == 4:
            break
        time.sleep(0.1)
    gate.set()
    for thread in threads:
        thread.join(timeout=60)
    assert results == [0, 0, 0, 0, 0], results
    assert counter["builds"] == 1, counter
    assert fake_webview.windows_created == 1, fake_webview.windows_created


def test_fxinst_second_run_focuses_first(monkeypatch, tmp_path):
    """One real dev-sidecar run twice: second focuses, no second window."""
    import uvicorn as _real  # noqa: F401

    data_root = str(tmp_path / "data")
    os.makedirs(data_root, exist_ok=True)
    monkeypatch.setenv("AGENT_SI_DATA_DIR", data_root)
    monkeypatch.delenv("AGENT_SI_ALLOW_MULTI", raising=False)
    gate = threading.Event()
    fake_webview = _CountWebview(gate)
    monkeypatch.setitem(sys.modules, "webview", fake_webview)
    counter = {"builds": 0}
    _shim_uvicorn(monkeypatch, counter)
    # Warm the product app build once so the background first run
    # reaches healthy fast.
    sidecar.build_app()
    first = threading.Thread(
        target=lambda: sidecar.main([]), daemon=True)
    first.start()
    try:
        deadline = time.monotonic() + 60
        healthy = False
        while time.monotonic() < deadline:
            record = sidecar._read_port_file(
                sidecar._port_file_path(data_root))
            if record is not None and sidecar._health_answers(record[0]):
                healthy = True
                break
            time.sleep(0.1)
        assert healthy, "first run never became healthy"
        assert sidecar.main([]) == 0
        assert counter["builds"] == 1, counter
        assert fake_webview.windows_created == 1, (
            fake_webview.windows_created)
    finally:
        gate.set()
        first.join(timeout=60)


def test_fxinst_allow_multi_skips_lock(monkeypatch, tmp_path):
    """AGENT_SI_ALLOW_MULTI=1: no lock and no port record for test copies."""
    import signal

    data_root = str(tmp_path / "data")
    os.makedirs(data_root, exist_ok=True)
    monkeypatch.setenv("AGENT_SI_DATA_DIR", data_root)
    monkeypatch.setenv("AGENT_SI_ALLOW_MULTI", "1")
    monkeypatch.setattr(sidecar, "_screen_work_area", lambda: (1920, 1080))

    class _State:
        ui_session_token = "tok-multi"

    class _App:
        state = _State()

    monkeypatch.setattr(sidecar, "build_app", lambda: _App())
    monkeypatch.setattr(sidecar, "pick_free_port", lambda: 12798)

    class _FakeWindow:
        width = 1280
        height = 800

    class _FakeWebview:
        def create_window(self, *args, **kwargs):
            return _FakeWindow()

        def start(self, *args, **kwargs):
            return None

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

    monkeypatch.setitem(sys.modules, "webview", _FakeWebview())
    monkeypatch.setitem(sys.modules, "uvicorn", _FakeUvicorn())
    old_int = signal.getsignal(signal.SIGINT)
    old_term = signal.getsignal(signal.SIGTERM)
    try:
        assert sidecar.main([]) == 0
    finally:
        signal.signal(signal.SIGINT, old_int)
        signal.signal(signal.SIGTERM, old_term)
    assert not os.path.exists(sidecar._lock_file_path(data_root))
    assert not os.path.exists(sidecar._port_file_path(data_root))
