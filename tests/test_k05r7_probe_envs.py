"""K05R7 M-PROBE D15: offline probe envs separate from product infra.

RED before src/agent_si/local/k05r7_probe_envs.py lands (missing names fail
on unfixed code); GREEN after. Real loopback server sockets plus real tmp
paths; no canned product values. Fakes/monkeypatches live in this file only.
"""
from __future__ import annotations

import os
import pathlib
import socket
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import pytest

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


def test_resolve_endpoint_only_from_probe_env(monkeypatch) -> None:
    monkeypatch.setenv(penvs.PROBE_ENDPOINT_ENV, "http://127.0.0.1:11434")
    assert penvs.resolve_probe_endpoint() == "http://127.0.0.1:11434"
    assert penvs.resolve_probe_env().endpoint == "http://127.0.0.1:11434"


def test_product_infra_env_never_affects_probe(monkeypatch, tmp_path) -> None:
    journal = tmp_path / "bench.journal"
    journal.write_text("infra-junk\n", encoding="utf-8")
    monkeypatch.setenv("AGENT_SI_BENCH_JOURNAL", str(journal))
    monkeypatch.setenv("AGENT_SI_SOMETHING_ELSE", "infra-junk-value")
    monkeypatch.delenv(penvs.PROBE_ENDPOINT_ENV, raising=False)
    monkeypatch.delenv(penvs.PROBE_TIMEOUT_ENV, raising=False)
    before = penvs.resolve_probe_env()
    snap = penvs.probe_env_snapshot()
    assert "AGENT_SI_BENCH_JOURNAL" not in snap
    assert all(k.startswith(penvs.PROBE_ENV_PREFIX) for k in snap)
    assert before.endpoint is None
    assert before.timeout_s == penvs.DEFAULT_PROBE_TIMEOUT_S
    monkeypatch.setenv(penvs.PROBE_ENDPOINT_ENV, "http://127.0.0.1:1234")
    after = penvs.resolve_probe_env()
    assert after.endpoint == "http://127.0.0.1:1234"
    # Product infra env still present, probe answer unchanged by it.
    assert os.environ.get("AGENT_SI_BENCH_JOURNAL") == str(journal)
    assert penvs.resolve_probe_endpoint() == "http://127.0.0.1:1234"


def test_snapshot_holds_probe_prefix_only(monkeypatch) -> None:
    monkeypatch.setenv(penvs.PROBE_ENDPOINT_ENV, "http://127.0.0.1:11434")
    monkeypatch.setenv(penvs.PROBE_TIMEOUT_ENV, "0.1")
    monkeypatch.setenv("AGENT_SI_BENCH_JOURNAL", "infra-only")
    snap = penvs.probe_env_snapshot()
    assert snap[penvs.PROBE_ENDPOINT_ENV] == "http://127.0.0.1:11434"
    assert snap[penvs.PROBE_TIMEOUT_ENV] == "0.1"
    assert "AGENT_SI_BENCH_JOURNAL" not in snap


def test_targets_loopback_only_default(monkeypatch) -> None:
    monkeypatch.delenv(penvs.PROBE_ENDPOINT_ENV, raising=False)
    for host, _port, _endpoint in penvs.probe_targets():
        assert penvs.probe_host_allowed(host) is True
    assert len(penvs.probe_targets()) >= 1


def test_targets_loopback_only_custom(monkeypatch) -> None:
    monkeypatch.setenv(penvs.PROBE_ENDPOINT_ENV, "http://127.0.0.1:11434")
    targets = penvs.probe_targets()
    assert len(targets) == 1
    host, _port, endpoint = targets[0]
    assert host == "127.0.0.1"
    assert "127.0.0.1" in endpoint


def test_non_loopback_endpoint_yields_no_targets(monkeypatch) -> None:
    monkeypatch.setenv(penvs.PROBE_ENDPOINT_ENV, "http://192.0.2.10:11434")
    assert penvs.probe_targets() == ()


def test_live_loopback_reachable_and_closed_port_not() -> None:
    srv = _listen_loopback()
    try:
        port = srv.getsockname()[1]
        assert penvs.probe_reachable("127.0.0.1", port) is True
    finally:
        srv.close()
    assert penvs.probe_reachable("127.0.0.1", _closed_loopback_port()) is False


def test_probe_reachable_makes_no_contact_off_loopback(monkeypatch) -> None:
    calls: list = []

    def _boom(address, timeout=None):
        calls.append(address)
        raise AssertionError("non-loopback socket contact attempted")

    monkeypatch.setattr(socket, "create_connection", _boom)
    assert penvs.probe_reachable("192.0.2.10", 11434) is False
    assert penvs.probe_reachable("example.com", 80) is False
    assert calls == []


def test_bad_timeout_env_falls_back_to_default(monkeypatch) -> None:
    for bad in ("", "junk", "-1", "0", "inf", "nan"):
        monkeypatch.setenv(penvs.PROBE_TIMEOUT_ENV, bad)
        assert penvs.resolve_probe_timeout_s() == penvs.DEFAULT_PROBE_TIMEOUT_S
    monkeypatch.setenv(penvs.PROBE_TIMEOUT_ENV, "0.05")
    assert penvs.resolve_probe_timeout_s() == pytest.approx(0.05)
