"""K05OPEN3 bench-next picker lane (M-P4-130, M-P4-132, M-P4-133): RED->GREEN.

One behaviour test per row, each through create_app plus HTTP client:

- M-P4-130 (owner benchmark originals read-only; suite may grow): the
  picker steers only on finalized (stopped) runs' rows. Rows from a still
  active (growing, writable) run are not read-only originals yet, so they
  never steer. Served history/results prove the evidence comes from the
  real bench store.
- M-P4-132 (level durations 5-15-30 min; equal wall-clock meaning): levels
  rank by one shared wall-clock-minutes mapping (Quick 5, Standard 15,
  Deep 30) and the steer note cites the winning level's minutes. Served
  estimates prove the duration floors served-side.
- M-P4-133 (real local-model runs only via gateway; fakes in tests;
  LOCAL-ONLY zero cloud): only MEASURED rows steer; PROXY rows (test-only
  non-measured evidence) never steer. The served gateway check proves
  cloud endpoints are refused and nothing is forced.

Bench input discipline: the REAL bench_runner store is used (real
RunHandle / RunProgress / BenchResultRow types; the picker reads via the
public list_run_ids + run_result_rows + run_progress and never writes).
This fixture seeds the real in-memory store directly (test-only loopback
models) and the picker never writes it. Keys are distinctive and removed
in teardown, so no state leaks to other test files.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import copy

import fastapi.testclient
import pytest

from agent_si.backend.app import create_app
from agent_si.local import bench_runner as _bench_runner
from agent_si.local.bench_protocol import (
    BenchLevel,
    HardwareProfile,
    ResultKind,
    build_result_row,
)
from agent_si.local.bench_runner import RunHandle, RunProgress
from agent_si.model_kb import SEED_CATALOG, bind_catalog, bound_catalog
from agent_si.model_kb import kb as _kb
from agent_si.model_kb import loader as _loader
from agent_si.model_kb.kb_reader import CatalogKbReader
from agent_si.providers.registry import ProviderRegistry
from agent_si.routing.picker import PICKED, pick

LOOPBACK = "http://127.0.0.1:9/v1"
APP_TOKEN = "k05open3-app-token"

_HW = HardwareProfile(gpu_vendor="CPU-only", gpu_model=None, vram_mb=None,
                      ram_mb=8192, cpu_only=True)


@pytest.fixture()
def reader():
    """Real CatalogKbReader over the real shipped seed catalog."""
    saved = copy.deepcopy(_kb.bound_catalog())
    bind_catalog(SEED_CATALOG)
    try:
        yield CatalogKbReader()
    finally:
        bind_catalog(saved)


def _real_row(provider_id, model_id):
    """One real bound-catalog row; rules are built from these rows."""
    row = _loader.find_row(bound_catalog(), provider_id, model_id)
    assert row is not None, "real seed row missing: %s/%s" % (
        provider_id, model_id)
    return row


def _registry(local_model, cloud_model):
    """Real registry with one routing-eligible local plus one cloud."""
    reg = ProviderRegistry()
    reg.register_instance({
        "provider": "openai",
        "model": local_model,
        "instance_id": "local-1",
        "provider_type": "local",
        "base_url": LOOPBACK,
        "credential_ref": {"secret_id": "ref-local-1",
                           "provider_id": "openai"},
    })
    reg.register_instance({
        "provider": "openai",
        "model": cloud_model,
        "instance_id": "default",
        "provider_type": "cloud",
        "base_url": LOOPBACK,
        "credential_ref": {"secret_id": "ref-cloud-1",
                           "provider_id": "openai"},
    })
    reg.record_credential_evidence("openai", "local-1", "fake-probe-local")
    reg.record_credential_evidence("openai", "default", "fake-probe-cloud")
    reg.record_health("openai", "local-1", "ONLINE")
    reg.record_health("openai", "default", "ONLINE")
    return reg


def _seed_run(run_id, model_id, level, stopped):
    """Seed one run into the REAL bench store (fixture setup, test data)."""
    assert run_id not in _bench_runner._RUNS, "store polluted: %r" % run_id
    _bench_runner._RUNS[run_id] = RunHandle(
        run_id=run_id, model_id=model_id, level=level)
    _bench_runner._PROGRESS[run_id] = RunProgress(
        run_id=run_id, done_cases=0, total_cases=1, paused=False,
        stopped=stopped)
    _bench_runner._RUN_ROWS[run_id] = []


def _seed_row(run_id, case_id, model_id, kind=ResultKind.MEASURED):
    """Append one real result row to a seeded run (fixture setup)."""
    assert run_id in _bench_runner._RUN_ROWS, "unknown seed run: %r" % run_id
    _bench_runner._RUN_ROWS[run_id].append(
        build_result_row(case_id, kind, model_id, _HW))


@pytest.fixture()
def bench_store():
    """Seeded bench runs; teardown removes exactly the keys this file added."""
    added = []

    def _add(run_id, model_id, level, stopped):
        _seed_run(run_id, model_id, level, stopped)
        added.append(run_id)
        return run_id

    try:
        yield _add
    finally:
        for run_id in added:
            _bench_runner._RUNS.pop(run_id, None)
            _bench_runner._PROGRESS.pop(run_id, None)
            _bench_runner._RUN_ROWS.pop(run_id, None)


def _client():
    """Served app over HTTP (reads need no token; writes stay refused)."""
    app = create_app({"ui_session_token": APP_TOKEN})
    return fastapi.testclient.TestClient(app)


def _cloud_first_rule(rule_id, local_model, cloud_model):
    """Cloud candidate listed first: legacy first-eligible order picks cloud."""
    return {"rule_id": rule_id, "candidates": [
        {"script": "cloud-summarize", "parameters": {"depth": 1},
         "requires": {"provider_type": "cloud", "model": cloud_model}},
        {"script": "local-summarize", "parameters": {"depth": 1},
         "requires": {"provider_type": "local", "model": local_model}}]}


def test_originals_read_only_active_run_rows_do_not_steer(
        reader, bench_store):
    """M-P4-130: rows from a still-active (growing) run never steer.

    The served history/results prove the active run's row is real bench
    evidence; the picker still keeps the legacy order because an active
    run's rows are not read-only originals yet.
    """
    local = _real_row("openai", "gpt-4o")
    cloud = _real_row("openai", "gpt-4o-mini")
    reg = _registry(local["model_id"], cloud["model_id"])
    run_id = bench_store("k05open3-active-orig", local["model_id"],
                         BenchLevel.Quick, False)
    _seed_row(run_id, "k05open3-case-orig", local["model_id"])
    client = _client()
    hist = client.get("/api/v1/local/bench/history")
    assert hist.status_code == 200, hist.text
    assert run_id in hist.json()
    served = client.get("/api/v1/local/bench/results",
                        params={"run_id": run_id})
    assert served.status_code == 200, served.text
    rows = served.json()
    assert len(rows) == 1
    assert rows[0]["case_id"] == "k05open3-case-orig"
    res = pick(_cloud_first_rule("k05open3-case-orig", local["model_id"],
                                 cloud["model_id"]), reg, reader)
    assert res.status == PICKED
    assert res.script == "cloud-summarize"
    assert "bench" not in res.reason


def test_level_durations_carry_equal_wall_clock_meaning(
        reader, bench_store):
    """M-P4-132: the steer note cites the winning level's wall-clock minutes.

    The served estimates prove the 5-15-30 floors served-side; the picker
    ranks levels by one shared wall-clock-minutes mapping, so a Standard
    steer carries its minutes in the reason.
    """
    local = _real_row("openai", "gpt-4o")
    cloud = _real_row("openai", "gpt-4o-mini")
    reg = _registry(local["model_id"], cloud["model_id"])
    run_id = bench_store("k05open3-dur-std", local["model_id"],
                         BenchLevel.Standard, True)
    _seed_row(run_id, "k05open3-case-dur", local["model_id"])
    client = _client()
    for level, floor in (("Quick", 5.0), ("Standard", 15.0),
                         ("Deep", 30.0)):
        est = client.get("/api/v1/local/bench/estimate",
                         params={"model_id": "k05open3-estimate-model",
                                 "level": level})
        assert est.status_code == 200, est.text
        body = est.json()
        assert body["minutes_min"] >= floor
        assert body["minutes_max"] >= body["minutes_min"]
    res = pick(_cloud_first_rule("k05open3-case-dur", local["model_id"],
                                 cloud["model_id"]), reg, reader)
    assert res.status == PICKED
    assert res.script == "local-summarize"
    assert res.model == local["model_id"]
    assert "15 min" in res.reason


def test_only_measured_rows_steer_proxy_never_moves_routing(
        reader, bench_store):
    """M-P4-133: PROXY rows never steer; only real MEASURED runs count.

    Two Deep PROXY rows for cloud would outrank one Quick MEASURED row
    for local by depth alone; the picker ignores non-measured evidence.
    The served gateway check proves cloud endpoints are refused and no
    contact is forced (LOCAL-ONLY zero cloud).
    """
    local = _real_row("openai", "gpt-4o")
    cloud = _real_row("openai", "gpt-4o-mini")
    reg = _registry(local["model_id"], cloud["model_id"])
    proxy_run = bench_store("k05open3-proxy-deep", cloud["model_id"],
                            BenchLevel.Deep, True)
    _seed_row(proxy_run, "k05open3-case-gw", cloud["model_id"],
              ResultKind.PROXY)
    _seed_row(proxy_run, "k05open3-case-gw", cloud["model_id"],
              ResultKind.PROXY)
    real_run = bench_store("k05open3-real-quick", local["model_id"],
                           BenchLevel.Quick, True)
    _seed_row(real_run, "k05open3-case-gw", local["model_id"],
              ResultKind.MEASURED)
    client = _client()
    refused = client.get("/api/v1/local/bench/check",
                         params={"endpoint": "https://api.openai.com"})
    assert refused.status_code == 200, refused.text
    assert refused.json()["reachable"] is False
    idle = client.get("/api/v1/local/bench/check",
                      params={"endpoint": "http://127.0.0.1:9"})
    assert idle.status_code == 200, idle.text
    assert idle.json()["reachable"] is False
    served = client.get("/api/v1/local/bench/results",
                        params={"run_id": proxy_run})
    assert served.status_code == 200, served.text
    assert [row["kind"] for row in served.json()] == ["PROXY", "PROXY"]
    res = pick(_cloud_first_rule("k05open3-case-gw", local["model_id"],
                                 cloud["model_id"]), reg, reader)
    assert res.status == PICKED
    assert res.script == "local-summarize"
    assert res.model == local["model_id"]
