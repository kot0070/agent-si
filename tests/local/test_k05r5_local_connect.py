"""K05R5 M-LOCAL behaviour tests: local_connect via the real discovery path.

Proves the two leaks stay fixed through the real entry points:
`get_status()` reports NOT_CONFIGURED only when truly unconfigured
(detached / unreachable / unconfigured ref); `list_models()` returns rows
for the attached runtime and () only when none is attached/discoverable.
The only boundary stood up by these tests is a bare loopback TCP acceptor
(proving the real stdlib socket probe path); no product logic is faked.
"""
from __future__ import annotations

import pathlib
import socket
import sys
import threading

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))

import pytest

from agent_si.backend import local_connect
from agent_si.local import bench_runner as runner

_TOKEN = "k05r5-local-token"


@pytest.fixture(autouse=True)
def _isolate_lane_state():
    """Snapshot process-global lane state, start clean, restore afterwards.

    local_connect._PAIRED_SESSION_TOKEN binds process-wide on the first
    well-formed write and gateway/bench_runner hold serial-slot globals,
    so each test starts detached/unpaired with a free probe path.
    """
    saved_paired = local_connect._PAIRED_SESSION_TOKEN
    saved_attached = local_connect._ATTACHED_RUNTIME
    saved_active = runner._ACTIVE_RUN_ID
    local_connect._PAIRED_SESSION_TOKEN = None
    local_connect._ATTACHED_RUNTIME = None
    runner._ACTIVE_RUN_ID = None
    yield
    local_connect._PAIRED_SESSION_TOKEN = saved_paired
    local_connect._ATTACHED_RUNTIME = saved_attached
    runner._ACTIVE_RUN_ID = saved_active


class _LoopbackListener:
    """Bare TCP acceptor on 127.0.0.1:0; network-boundary only, no product fakery."""

    def __init__(self) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.port = self.sock.getsockname()[1]
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def _serve(self) -> None:
        self.sock.settimeout(0.05)
        while not self._stop.is_set():
            try:
                conn, _ = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                conn.close()
            except OSError:
                pass

    def __enter__(self) -> "_LoopbackListener":
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self._thread.join(timeout=5)
        self.sock.close()


def _closed_loopback_port() -> int:
    """A loopback port with provably nothing listening (bound then released)."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


def test_detached_status_is_not_configured() -> None:
    status = local_connect.get_status()
    assert status.status == "NOT_CONFIGURED"
    assert status.reason != ""


def test_detached_models_empty() -> None:
    assert local_connect.list_models() == ()


def test_unconfigured_ref_stays_not_configured_and_empty() -> None:
    local_connect.connect("runtime-ref-1", session_token=_TOKEN)
    status = local_connect.get_status()
    assert status.status == "NOT_CONFIGURED"
    assert status.reason != ""
    assert local_connect.list_models() == ()


def test_attached_unreachable_is_not_configured_and_empty() -> None:
    ref = "http://127.0.0.1:%d" % _closed_loopback_port()
    local_connect.connect(ref, session_token=_TOKEN)
    status = local_connect.get_status()
    assert status.status == "NOT_CONFIGURED"
    assert status.reason != ""
    assert local_connect.list_models() == ()


def test_attached_reachable_reports_live_status_and_row() -> None:
    with _LoopbackListener() as listener:
        ref = "http://127.0.0.1:%d" % listener.port
        local_connect.connect(ref, session_token=_TOKEN)
        status = local_connect.get_status()
        assert status.status != "NOT_CONFIGURED"
        assert status.reason != ""
        rows = local_connect.list_models()
        assert isinstance(rows, tuple)
        assert len(rows) == 1
        assert isinstance(rows[0], local_connect.LocalModelRow)
        assert rows[0].model == ref
        assert rows[0].evidence_tier == "PROXY"
        assert rows[0].status != ""


def test_disconnect_returns_to_not_configured_and_empty() -> None:
    with _LoopbackListener() as listener:
        ref = "http://127.0.0.1:%d" % listener.port
        local_connect.connect(ref, session_token=_TOKEN)
        assert local_connect.get_status().status != "NOT_CONFIGURED"
        assert len(local_connect.list_models()) == 1
    local_connect.disconnect(session_token=_TOKEN)
    assert local_connect.get_status().status == "NOT_CONFIGURED"
    assert local_connect.list_models() == ()


def test_refused_writes_change_nothing() -> None:
    with _LoopbackListener() as listener:
        ref = "http://127.0.0.1:%d" % listener.port
        local_connect.connect(ref, session_token=_TOKEN)
        before = (local_connect.get_status(), local_connect.list_models())
        with pytest.raises(Exception) as excinfo:
            local_connect.connect(ref, session_token="wrong-token-1")
        assert "SESSION_TOKEN_REFUSED" in str(excinfo.value)
        with pytest.raises(Exception) as excinfo:
            local_connect.disconnect(session_token="wrong-token-1")
        assert "SESSION_TOKEN_REFUSED" in str(excinfo.value)
        assert (local_connect.get_status(), local_connect.list_models()) == before
