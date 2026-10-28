"""K05R7 M-PROBE D41: host check fails closed before any external contact.

RED before the k05r7 guard names land (missing names fail on unfixed code);
GREEN after. Real loopback server sockets; socket-call recording proves no
external traffic. Fakes/monkeypatches live in this file only.
"""
from __future__ import annotations

import pathlib
import socket
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from agent_si.local import bench_runner as runner
from agent_si.local import k05r7_probe_envs as penvs


def _listen_loopback():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    return srv


def _closed_loopback_port() -> int:
    srv = _listen_loopback()
    port = srv.getsockname()[1]
    srv.close()
    return port


def _recorder(monkeypatch):
    calls: list = []
    real = socket.create_connection

    def _fake(address, timeout=None, *args, **kwargs):
        calls.append(address)
        host = address[0] if isinstance(address, tuple) else address
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise AssertionError(f"external socket contact attempted: {address!r}")
        return real(address, timeout=timeout, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", _fake)
    return calls


def test_non_loopback_refused_before_any_contact(monkeypatch) -> None:
    calls = _recorder(monkeypatch)
    for endpoint in (
        "http://192.0.2.10:11434",
        "http://example.com:11434",
        "http://10.0.0.5/",
    ):
        try:
            penvs.guard_probe_endpoint(endpoint)
        except penvs.ProbeRefusedError:
            pass
        else:
            raise AssertionError(f"non-loopback endpoint passed: {endpoint!r}")
    assert calls == []


def test_unparsable_refused_before_any_contact(monkeypatch) -> None:
    calls = _recorder(monkeypatch)
    for endpoint in ("", "http://127.0.0.1:badport", "http://[::1"):
        try:
            penvs.guard_probe_endpoint(endpoint)
        except penvs.ProbeRefusedError:
            pass
        else:
            raise AssertionError(f"unparsable endpoint passed: {endpoint!r}")
    assert calls == []


def test_closed_loopback_port_refused_only_loopback_contact(monkeypatch) -> None:
    calls = _recorder(monkeypatch)
    endpoint = f"http://127.0.0.1:{_closed_loopback_port()}"
    try:
        penvs.guard_probe_endpoint(endpoint, timeout_s=0.1)
    except penvs.ProbeRefusedError as exc:
        assert "unreachable" in str(exc).lower()
    else:
        raise AssertionError(f"closed loopback port passed: {endpoint!r}")
    assert calls != []
    assert all(
        (addr[0] if isinstance(addr, tuple) else addr)
        in ("127.0.0.1", "::1", "localhost")
        for addr in calls
    )


def test_live_loopback_server_passes_guard() -> None:
    srv = _listen_loopback()
    try:
        port = srv.getsockname()[1]
        got = penvs.guard_probe_endpoint(f"127.0.0.1:{port}", timeout_s=2.0)
        assert "127.0.0.1" in got and str(port) in got
    finally:
        srv.close()


def test_runner_wiring_refuses_before_contact(monkeypatch) -> None:
    calls = _recorder(monkeypatch)
    assert issubclass(runner.K05R7ProbeRefusedError, runner.BenchRefusedError)
    try:
        runner.k05r7_guard_probe_endpoint("http://203.0.113.7:11434")
    except runner.K05R7ProbeRefusedError:
        pass
    else:
        raise AssertionError("runner wiring passed a non-loopback endpoint")
    assert calls == []
    skip = runner.k05r7_check_probe_endpoint("http://203.0.113.7:11434")
    assert isinstance(skip, runner.K05R7ProbeSkip) and skip.reason != ""


def test_runner_wiring_accepts_live_loopback() -> None:
    srv = _listen_loopback()
    try:
        port = srv.getsockname()[1]
        got = runner.k05r7_guard_probe_endpoint(f"http://127.0.0.1:{port}")
        assert "127.0.0.1" in got
    finally:
        srv.close()


def test_runner_probe_env_ignores_product_infra(monkeypatch, tmp_path) -> None:
    journal = tmp_path / "bench.journal"
    journal.write_text("infra-junk\n", encoding="utf-8")
    monkeypatch.setenv(runner.JOURNAL_ENV_VAR, str(journal))
    monkeypatch.delenv(penvs.PROBE_ENDPOINT_ENV, raising=False)
    env = runner.k05r7_resolve_probe_env()
    assert env.endpoint is None
    assert runner.k05r7_probe_snapshot() == {}
    assert all(k.startswith(penvs.PROBE_ENV_PREFIX) for k in runner.k05r7_probe_snapshot())
