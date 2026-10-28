"""K06 M-D-D51 behaviour: channel evaluation persisted before socket use.

Every assertion routes through the real entry point
``channel_socket.open_channel`` (real evaluation plus real loopback
socket), so missing product modules FAIL (RED) until STEP 2 adds them.

Row: channel evaluation persisted before socket use; fail-closed,
no deadlock. Fail-closed means any error or unknown denies and no
socket is opened; persisted means an allow evaluation is durable in
the record store before the socket is touched.
"""

import importlib.util
import json
import pathlib
import socket
import socketserver
import tempfile
import threading
import time

SERVICES_DIR = (
    pathlib.Path(__file__).resolve().parent.parent
    / "src"
    / "agent_si"
    / "services"
)
EVAL_FILE = SERVICES_DIR / "channel_eval.py"
SOCKET_FILE = SERVICES_DIR / "channel_socket.py"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tmp_store():
    fd, path = tempfile.mkstemp(prefix="d51-chan-", suffix=".jsonl")
    import os

    os.close(fd)
    pathlib.Path(path).unlink()
    return path


class _Handler(socketserver.BaseRequestHandler):
    accepted = 0
    lock = threading.Lock()

    def handle(self):
        with _Handler.lock:
            _Handler.accepted += 1
        try:
            self.request.settimeout(5.0)
            self.request.recv(1)
        except OSError:
            pass


def _run_server():
    _Handler.accepted = 0
    server = socketserver.TCPServer(("127.0.0.1", 0), _Handler)
    server.timeout = 5.0
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05})
    thread.daemon = True
    thread.start()
    return server


def _closed_loopback_port():
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


def _records(store):
    lines = pathlib.Path(store).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def test_product_files_exist():
    assert EVAL_FILE.is_file()
    assert SOCKET_FILE.is_file()


def test_modules_import_and_entry_points_wired():
    channel_socket = _load("d51_socket", SOCKET_FILE)
    channel_eval = _load("d51_eval", EVAL_FILE)
    assert callable(channel_socket.open_channel)
    assert callable(channel_eval.evaluate_channel)
    assert callable(channel_eval.load_records)


def test_allow_loopback_persists_evaluation():
    channel_socket = _load("d51_socket_allow", SOCKET_FILE)
    server = _run_server()
    try:
        port = server.server_address[1]
        store = _tmp_store()
        result = channel_socket.open_channel(
            {"host": "127.0.0.1", "port": port},
            store_path=store,
            timeout=5.0,
        )
        assert result["decision"] == "allow"
        assert isinstance(result["reason"], str) and result["reason"]
        assert isinstance(result["evidence_ref"], str) and result["evidence_ref"]
        rows = _records(store)
        assert len(rows) == 1
        row = rows[0]
        assert row["decision"] == "allow"
        assert row["host"] == "127.0.0.1"
        assert row["port"] == port
        assert row["pinned_ip"] == "127.0.0.1"
        assert row["channel_id"]
        assert row["created_at"]
        assert result["evidence_ref"] == "channel:allow:%s" % row["channel_id"]
    finally:
        server.shutdown()
        server.server_close()


def test_evaluation_persisted_before_failed_socket_use():
    channel_socket = _load("d51_socket_refused", SOCKET_FILE)
    store = _tmp_store()
    port = _closed_loopback_port()
    result = channel_socket.open_channel(
        {"host": "127.0.0.1", "port": port},
        store_path=store,
        timeout=2.0,
    )
    assert result["decision"] == "deny"
    rows = _records(store)
    assert len(rows) == 1
    assert rows[0]["decision"] == "allow"
    assert rows[0]["pinned_ip"] == "127.0.0.1"
    assert rows[0]["port"] == port


def test_unresolved_host_denies_without_record_gap():
    channel_socket = _load("d51_socket_unresolved", SOCKET_FILE)
    store = _tmp_store()
    started = time.monotonic()
    result = channel_socket.open_channel(
        {"host": "nonexistent.invalid", "port": 80},
        store_path=store,
        timeout=5.0,
    )
    elapsed = time.monotonic() - started
    assert result["decision"] == "deny"
    assert elapsed < 30.0
    rows = _records(store)
    assert len(rows) == 1
    assert rows[0]["decision"] == "deny"


def test_bad_target_denies():
    channel_socket = _load("d51_socket_bad", SOCKET_FILE)
    store = _tmp_store()
    for target in (
        {"host": "", "port": 80},
        {"host": "127.0.0.1", "port": 0},
        {"host": "127.0.0.1", "port": 70000},
        {"host": "127.0.0.1"},
        "127.0.0.1:80",
        None,
    ):
        result = channel_socket.open_channel(
            target, store_path=store, timeout=2.0
        )
        assert result["decision"] == "deny", target


def test_unknown_policy_key_denies():
    channel_socket = _load("d51_socket_policy", SOCKET_FILE)
    store = _tmp_store()
    result = channel_socket.open_channel(
        {"host": "127.0.0.1", "port": 80},
        policy={"unknown_key": True},
        store_path=store,
        timeout=2.0,
    )
    assert result["decision"] == "deny"


def test_deny_listed_host_opens_no_socket():
    channel_socket = _load("d51_socket_denylist", SOCKET_FILE)
    server = _run_server()
    try:
        port = server.server_address[1]
        store = _tmp_store()
        result = channel_socket.open_channel(
            {"host": "127.0.0.1", "port": port},
            policy={"deny_hosts": ["127.0.0.1"]},
            store_path=store,
            timeout=5.0,
        )
        assert result["decision"] == "deny"
        time.sleep(0.3)
        with _Handler.lock:
            seen = _Handler.accepted
        assert seen == 0
        rows = _records(store)
        assert len(rows) == 1
        assert rows[0]["decision"] == "deny"
    finally:
        server.shutdown()
        server.server_close()


def test_store_failure_denies_before_socket():
    channel_socket = _load("d51_socket_store", SOCKET_FILE)
    server = _run_server()
    try:
        port = server.server_address[1]
        result = channel_socket.open_channel(
            {"host": "127.0.0.1", "port": port},
            store_path=str(pathlib.Path(tempfile.gettempdir())),
            timeout=5.0,
        )
        assert result["decision"] == "deny"
        time.sleep(0.3)
        with _Handler.lock:
            seen = _Handler.accepted
        assert seen == 0
    finally:
        server.shutdown()
        server.server_close()


def test_evaluate_module_shape_and_reader():
    channel_eval = _load("d51_eval_shape", EVAL_FILE)
    store = _tmp_store()
    verdict = channel_eval.evaluate_channel(
        {"host": "127.0.0.1", "port": 80}, store_path=store
    )
    assert verdict["decision"] == "allow"
    assert verdict["record"]["pinned_ip"] == "127.0.0.1"
    assert verdict["evidence_ref"].startswith("channel-eval:allow:")
    rows = channel_eval.load_records(store)
    assert len(rows) == 1
    assert rows[0]["channel_id"] == verdict["record"]["channel_id"]
    denied = channel_eval.evaluate_channel(
        {"host": "", "port": 80}, store_path=store
    )
    assert denied["decision"] == "deny"
    assert denied["evidence_ref"].startswith("channel-eval:deny:")
