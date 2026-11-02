"""FXR2E-1: stable sidecar port in the data dir (RED-first).

Restarting the sidecar must keep the loopback port so the webview
origin (and its localStorage) survives: the chosen port persists in
the data dir, is tried first on the next start, and a taken port
falls back to a free one with a log line. The UI token stays per
launch. The second-instance reattach path (sidecar.port record) is
unchanged.
"""
import os
import socket
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from agent_si import sidecar  # noqa: E402


def _hold_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((sidecar.HOST, 0))
    sock.listen(1)
    return sock


def test_saved_free_port_is_reused(monkeypatch, tmp_path, capsys):
    """A saved, free port is picked again on the next start."""
    monkeypatch.setattr(
        sidecar, "_sidecar_data_dir", lambda: str(tmp_path))
    first = sidecar.resolve_start_port(str(tmp_path))
    assert 1 <= first <= 65535
    second = sidecar.resolve_start_port(str(tmp_path))
    assert second == first, "restart must reuse the saved port"


def test_taken_saved_port_falls_back_and_logs(monkeypatch, tmp_path, capsys):
    """A saved port held by someone else falls back with a log line."""
    monkeypatch.setattr(
        sidecar, "_sidecar_data_dir", lambda: str(tmp_path))
    sidecar.resolve_start_port(str(tmp_path))
    occupying = _hold_port()
    taken = int(occupying.getsockname()[1])
    try:
        with open(sidecar._last_port_file_path(str(tmp_path)), "w",
                   encoding="utf-8") as handle:
            handle.write("%d\n" % taken)
        chosen = sidecar.resolve_start_port(str(tmp_path))
        assert chosen != taken
    finally:
        occupying.close()
    logged = capsys.readouterr().err
    assert str(taken) in logged and str(chosen) in logged


def test_malformed_record_picks_free_port(monkeypatch, tmp_path):
    """A corrupt last-port record never breaks start."""
    monkeypatch.setattr(
        sidecar, "_sidecar_data_dir", lambda: str(tmp_path))
    with open(sidecar._last_port_file_path(str(tmp_path)), "w",
               encoding="utf-8") as handle:
        handle.write("not-a-port\n")
    chosen = sidecar.resolve_start_port(str(tmp_path))
    assert 1 <= chosen <= 65535


def test_ui_token_stays_per_launch():
    """Two apps mint different UI tokens even on the same port."""
    from agent_si.backend.app import create_app

    first = create_app({"testing": True})
    second = create_app({"testing": True})
    assert (first.state.ui_session_token
            != second.state.ui_session_token)


def test_reattach_still_uses_live_port_record(monkeypatch, tmp_path):
    """Only the live sidecar.port record reattaches; lastport alone never."""
    monkeypatch.setattr(
        sidecar, "_sidecar_data_dir", lambda: str(tmp_path))
    with open(sidecar._last_port_file_path(str(tmp_path)), "w",
               encoding="utf-8") as handle:
        handle.write("54321\n")
    assert sidecar._reattach_running() is False
