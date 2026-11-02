"""FXRESP latency pins: coalesced telemetry reads + off-loop watch passes.

RED-first: before the fix the analytics route parsed the telemetry file
five times per poll (one per aggregate helper) and the watch-loop pass
ran inline on the server event loop (a ~10 s pass stalled one in-flight
GET every ~30 s). After the fix one poll parses once and the pass runs
off-loop, so p95 stays far under the 300 ms budget while a run works.
"""
import asyncio
import os
import statistics
import sys
import time

import pytest
from fastapi.testclient import TestClient

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.telemetry import run_store as _store  # noqa: E402
from agent_si.watcher import watch_loop as _loop  # noqa: E402

TOKEN = "fxresp-latency-token"
ACTOR = "fxresp-latency"
PID = "fxresp-latency-proj"


def _settings(store_dir):
    return {"testing": True, "ui_session_token": TOKEN,
            "store_dir": str(store_dir)}


def _seed(store_dir, count=500):
    for i in range(count):
        _store.record_provider_usage(
            project_id=PID, task_id="t-seed", run_id="seed-%d" % i,
            provider="mock", model="mock-slow",
            usage={"input_tokens": 10, "output_tokens": 5},
            store_dir=str(store_dir))


def test_analytics_poll_parses_store_once(tmp_path, monkeypatch):
    """One project analytics poll parses the store file exactly once."""
    _seed(tmp_path)
    parses = []
    real_read = _store._read_store

    def _counting(path):
        parses.append(path)
        return real_read(path)

    monkeypatch.setattr(_store, "_read_store", _counting)
    app = create_app(_settings(tmp_path))
    client = TestClient(app)
    try:
        resp = client.get("/api/v1/analytics/telemetry",
                          params={"project_id": PID})
    finally:
        client.close()
    assert resp.status_code == 200
    assert len(parses) == 1, "poll parsed store %d times" % len(parses)


def test_analytics_latency_budget(tmp_path):
    """20 sequential analytics polls: p95 under the 300 ms budget."""
    _seed(tmp_path)
    app = create_app(_settings(tmp_path))
    client = TestClient(app)
    try:
        lat = []
        for _ in range(20):
            start = time.perf_counter()
            resp = client.get("/api/v1/analytics/telemetry",
                              params={"project_id": PID})
            lat.append((time.perf_counter() - start) * 1000.0)
            assert resp.status_code == 200
    finally:
        client.close()
    p95 = statistics.quantiles(lat, n=100)[94]
    assert p95 < 300.0, "analytics p95 %.1f ms over budget" % p95


def test_watch_pass_runs_off_event_loop(monkeypatch):
    """A blocking pass never stalls the loop: sleep fires on time."""
    blocked = []

    def _slow_tick(app=None):
        blocked.append(True)
        time.sleep(2.0)
        return {"services_checked": 0, "watched": []}

    monkeypatch.setattr(_loop, "tick_once", _slow_tick)

    async def _main():
        start = time.perf_counter()
        _loop.start(app=None, interval_s=0.05)
        try:
            await asyncio.sleep(0.6)
        finally:
            await _loop.stop()
        return (time.perf_counter() - start) * 1000.0

    elapsed_ms = asyncio.run(_main())
    assert blocked, "the loop pass never ran"
    assert elapsed_ms < 1500.0, \
        "loop blocked the event loop for %.0f ms" % elapsed_ms
