"""K05BATCH Aster served-evidence tests (test_k05batchk1a_served).

K1A rows: bench-steer group M-P4-129/130/132/133 plus M-D local-AI rows
M-D-D15/D16/D41, proven on the real stack: served HTTP routes (create_app
+ TestClient) where a route fronts the behavior, else the real module
entry points (no fakes, no doubles in mount files, no skip, no xfail).

- M-P4-129: benchmark results steer the cloud-vs-local split to deeper
  levels (adapter.recommend_split steering rule, bench_runner
  split_steer_record written by the queue_run benchmark path, read by
  steered_split).
- M-P4-130: the picker steers only on finalized (stopped) runs' rows;
  rows from a still-active run are not read-only originals yet.
- M-P4-132: levels rank by one shared wall-clock-minutes mapping
  (Quick 5, Standard 15, Deep 30); the steer note cites the winning
  level's minutes.
- M-P4-133: only MEASURED rows steer; PROXY rows never steer; the served
  gateway check refuses cloud endpoints (LOCAL-ONLY zero cloud).
- M-D-D15: only AGENT_SI_PROBE_* feeds probe resolution.
- M-D-D16: versioned backups + owner gate close on matching record.
- M-D-D41: fail-closed host check before any contact, served too.

M-D-D10 and M-D-D22 carry zero in-tree definition (no marker in src,
tests, RECORDS): NOT-DONE waits-for-definition, never faked, so no test
here invents behavior for them.
"""

from __future__ import annotations

import copy
import json
import pathlib
import socket
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import fastapi.testclient  # noqa: E402

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.local import adapter as _adapter  # noqa: E402
from agent_si.local import bench_runner as _runner  # noqa: E402
from agent_si.local import k05r3_backups as _backups  # noqa: E402
from agent_si.local import k05r7_probe_envs as _penvs  # noqa: E402
from agent_si.local import config as _config  # noqa: E402
from agent_si.local.bench_protocol import (  # noqa: E402
    BenchLevel,
    HardwareProfile,
    ResultKind,
    build_result_row,
)
from agent_si.local.bench_runner import (  # noqa: E402
    BenchRefusedError,
    RunHandle,
    RunProgress,
    RunReservation,
)
from agent_si.model_kb import SEED_CATALOG, bind_catalog, bound_catalog  # noqa: E402
from agent_si.model_kb import kb as _kb  # noqa: E402
from agent_si.model_kb import loader as _loader  # noqa: E402
from agent_si.model_kb.kb_reader import CatalogKbReader  # noqa: E402
from agent_si.providers.registry import ProviderRegistry  # noqa: E402
from agent_si.routing.picker import PICKED, pick  # noqa: E402

LOOPBACK = "http://127.0.0.1:9/v1"
APP_TOKEN = "k05batchk1a-app-token"
_OWNER = "k05batchk1a"
_HEADERS = {"x-actor": "k05batchk1a-user", "x-ui-session-token": APP_TOKEN}

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
    assert run_id not in _runner._RUNS, "store polluted: %r" % run_id
    _runner._RUNS[run_id] = RunHandle(
        run_id=run_id, model_id=model_id, level=level)
    _runner._PROGRESS[run_id] = RunProgress(
        run_id=run_id, done_cases=0, total_cases=1, paused=False,
        stopped=stopped)
    _runner._RUN_ROWS[run_id] = []


def _seed_row(run_id, case_id, model_id, kind=ResultKind.MEASURED):
    """Append one real result row to a seeded run (fixture setup)."""
    assert run_id in _runner._RUN_ROWS, "unknown seed run: %r" % run_id
    _runner._RUN_ROWS[run_id].append(
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
            _runner._RUNS.pop(run_id, None)
            _runner._PROGRESS.pop(run_id, None)
            _runner._RUN_ROWS.pop(run_id, None)


@pytest.fixture()
def steer_state():
    """Clean scheduler slot plus pristine steer record; restore both after."""
    _drain_scheduler()
    prior_steer = dict(getattr(_runner, "_SPLIT_STEER", {}) or {})
    initial = getattr(_runner, "_SPLIT_STEER_INITIAL", None)
    if isinstance(initial, dict) and isinstance(
        getattr(_runner, "_SPLIT_STEER", None), dict
    ):
        _runner._SPLIT_STEER.clear()
        _runner._SPLIT_STEER.update(initial)
    yield
    _drain_scheduler()
    if prior_steer and isinstance(getattr(_runner, "_SPLIT_STEER", None), dict):
        _runner._SPLIT_STEER.clear()
        _runner._SPLIT_STEER.update(prior_steer)


@pytest.fixture()
def _clean_config_store():
    """config._STORE snapshot-restore; tests use their own project key."""
    before = dict(_config._STORE)
    yield
    _config._STORE.clear()
    _config._STORE.update(before)


def _drain_scheduler() -> None:
    """Stop the active run and cancel this lane's queued reservations."""
    try:
        active = _runner._ACTIVE_RUN_ID
    except AttributeError:
        active = None
    if active is not None:
        try:
            _runner.stop_run(active)
        except KeyError:
            pass
    try:
        reservations = _runner.list_reservations()
    except AttributeError:
        return
    for rsv in reservations:
        if rsv.status == "queued" and rsv.owner == _OWNER:
            try:
                _runner.cancel_reservation(rsv.reservation_id, rsv.owner)
            except (KeyError, BenchRefusedError):
                pass


def _client():
    """Served app over HTTP (reads need no token; writes stay refused)."""
    app = create_app({"env": "test", "ui_session_token": APP_TOKEN})
    assert app.state.localbench_mounted is True
    return fastapi.testclient.TestClient(app)


def _cloud_first_rule(rule_id, local_model, cloud_model):
    """Cloud candidate listed first: legacy first-eligible order picks cloud."""
    return {"rule_id": rule_id, "candidates": [
        {"script": "cloud-summarize", "parameters": {"depth": 1},
         "requires": {"provider_type": "cloud", "model": cloud_model}},
        {"script": "local-summarize", "parameters": {"depth": 1},
         "requires": {"provider_type": "local", "model": local_model}}]}


def test_k1a_steer_rule_deeper_levels_go_local(steer_state) -> None:
    """M-P4-129: benchmark results steer the split to deeper levels."""
    deep_summary = {
        "level": "Deep",
        "measured_score": 0.9,
        "proxy_score": 0.5,
        "tier": "MEASURED",
    }
    assert _adapter.recommend_split(deep_summary)["split"] == "local"
    assert _adapter.recommend_split({
        "level": "Quick", "measured_score": 0.9,
        "proxy_score": 0.5, "tier": "MEASURED",
    })["split"] == "cloud"
    assert _adapter.recommend_split(
        {"level": "Deep", "tier": "UNKNOWN"})["split"] == "cloud"

    record = _runner.split_steer_record()
    assert record["benchmarked"] is False
    assert _runner.steered_split(deep_summary)["split"] == "cloud"

    outcome = _runner.queue_run(
        "k05batchk1a-model", BenchLevel.Deep, True, owner=_OWNER
    )
    assert isinstance(outcome, (RunHandle, RunReservation))
    record = _runner.split_steer_record()
    assert record["benchmarked"] is True
    assert record["level"] == "Deep"
    assert record["depth"] == 2

    assert _runner.steered_split(deep_summary)["split"] == "local"
    assert _runner.steered_split({
        "level": "Quick", "measured_score": 0.9,
        "proxy_score": 0.5, "tier": "MEASURED",
    })["split"] == "cloud"
    assert _runner.steered_split(
        {"level": "Deep", "tier": "UNKNOWN"})["split"] == "cloud"


def test_k1a_originals_read_only_active_run_rows_do_not_steer(
        reader, bench_store):
    """M-P4-130: rows from a still-active run never steer."""
    local = _real_row("openai", "gpt-4o")
    cloud = _real_row("openai", "gpt-4o-mini")
    reg = _registry(local["model_id"], cloud["model_id"])
    run_id = bench_store("k05batchk1a-active-orig", local["model_id"],
                         BenchLevel.Quick, False)
    _seed_row(run_id, "k05batchk1a-case-orig", local["model_id"])
    client = _client()
    hist = client.get("/api/v1/local/bench/history")
    assert hist.status_code == 200, hist.text
    assert run_id in hist.json()
    served = client.get("/api/v1/local/bench/results",
                        params={"run_id": run_id})
    assert served.status_code == 200, served.text
    rows = served.json()
    assert len(rows) == 1
    assert rows[0]["case_id"] == "k05batchk1a-case-orig"
    res = pick(_cloud_first_rule("k05batchk1a-case-orig", local["model_id"],
                                 cloud["model_id"]), reg, reader)
    assert res.status == PICKED
    assert res.script == "cloud-summarize"
    assert "bench" not in res.reason


def test_k1a_level_durations_carry_equal_wall_clock_meaning(
        reader, bench_store):
    """M-P4-132: the steer note cites the winning level's minutes."""
    local = _real_row("openai", "gpt-4o")
    cloud = _real_row("openai", "gpt-4o-mini")
    reg = _registry(local["model_id"], cloud["model_id"])
    run_id = bench_store("k05batchk1a-dur-std", local["model_id"],
                         BenchLevel.Standard, True)
    _seed_row(run_id, "k05batchk1a-case-dur", local["model_id"])
    client = _client()
    for level, floor in (("Quick", 5.0), ("Standard", 15.0),
                         ("Deep", 30.0)):
        est = client.get("/api/v1/local/bench/estimate",
                         params={"model_id": "k05batchk1a-estimate-model",
                                 "level": level})
        assert est.status_code == 200, est.text
        body = est.json()
        assert body["minutes_min"] >= floor
        assert body["minutes_max"] >= body["minutes_min"]
    res = pick(_cloud_first_rule("k05batchk1a-case-dur", local["model_id"],
                                 cloud["model_id"]), reg, reader)
    assert res.status == PICKED
    assert res.script == "local-summarize"
    assert res.model == local["model_id"]
    assert "15 min" in res.reason


def test_k1a_only_measured_rows_steer(reader, bench_store):
    """M-P4-133: PROXY rows never steer; only MEASURED runs count."""
    local = _real_row("openai", "gpt-4o")
    cloud = _real_row("openai", "gpt-4o-mini")
    reg = _registry(local["model_id"], cloud["model_id"])
    proxy_run = bench_store("k05batchk1a-proxy-deep", cloud["model_id"],
                            BenchLevel.Deep, True)
    _seed_row(proxy_run, "k05batchk1a-case-gw", cloud["model_id"],
              ResultKind.PROXY)
    _seed_row(proxy_run, "k05batchk1a-case-gw", cloud["model_id"],
              ResultKind.PROXY)
    real_run = bench_store("k05batchk1a-real-quick", local["model_id"],
                           BenchLevel.Quick, True)
    _seed_row(real_run, "k05batchk1a-case-gw", local["model_id"],
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
    res = pick(_cloud_first_rule("k05batchk1a-case-gw", local["model_id"],
                                 cloud["model_id"]), reg, reader)
    assert res.status == PICKED
    assert res.script == "local-summarize"
    assert res.model == local["model_id"]


def test_k1a_probe_env_prefix_isolation() -> None:
    """M-D-D15: only AGENT_SI_PROBE_* feeds probe resolution."""
    env = {
        "AGENT_SI_PROBE_ENDPOINT": "http://127.0.0.1:11434",
        "AGENT_SI_PROBE_TIMEOUT_S": "0.2",
        "AGENT_SI_BENCH_JOURNAL": "/tmp/infra-journal",
        "AGENT_SI_OTHER_INFRA": "infra",
    }
    snap = _penvs.probe_env_snapshot(env)
    assert snap == {
        "AGENT_SI_PROBE_ENDPOINT": "http://127.0.0.1:11434",
        "AGENT_SI_PROBE_TIMEOUT_S": "0.2",
    }
    resolved = _penvs.resolve_probe_env(env)
    assert resolved.endpoint == "http://127.0.0.1:11434"
    assert resolved.timeout_s == 0.2


def test_k1a_backups_owner_gate(_clean_config_store) -> None:
    """M-D-D16: versioned backups + owner gate close on matching record."""
    store = _backups.VersionedBackupStore()
    first = store.keep("kb-k1a", "copy-one")
    second = store.keep("kb-k1a", "copy-two")
    assert store.serve_current(second) == "copy-two"
    with pytest.raises(_backups.BackupError) as excinfo:
        store.serve_current(first)
    assert excinfo.value.code == _backups.K05R3_BACKUP_STALE_AS_CURRENT_REFUSED
    assert store.serve_backup(first) == "copy-one"
    book = _backups.OwnerGateBook()
    gate = book.open_gate("gate-k1a", "proj-k1a", "gate-k1a: proceed?")
    assert gate.state == _backups.GATE_OPEN
    decision = _config.record_decision(
        "proj-k1a", "gate-k1a: proceed? yes", "owner reason", "owner"
    )
    assert json.dumps({"decision_id": decision.decision_id,
                       "project_id": decision.project_id})
    closed = book.close_gate("gate-k1a", decision)
    assert closed.state == _backups.GATE_CLOSED
    assert closed.decided_by == decision.decision_id
    foreign = _config.record_decision(
        "proj-other", "gate-k1a: proceed? yes", "owner reason", "owner"
    )
    with pytest.raises(_backups.OwnerGateError) as excinfo2:
        book.close_gate("gate-k1a", foreign)
    assert excinfo2.value.code in (
        _backups.K05R3_OWNER_GATE_STATE_REFUSED,
        _backups.K05R3_OWNER_GATE_DECISION_REFUSED,
    )


def test_k1a_probe_guard_served(monkeypatch) -> None:
    """M-D-D41: fail-closed host check before any contact, served too."""
    calls: list = []
    real = socket.create_connection

    def _recorder(address, timeout=None, *args, **kwargs):
        calls.append(address)
        host = address[0] if isinstance(address, tuple) else address
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise AssertionError("external contact attempted: %r" % (address,))
        return real(address, timeout=timeout, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", _recorder)
    for endpoint in ("https://api.openai.com", "http://10.0.0.5/", "http://[::1"):
        with pytest.raises(_penvs.ProbeRefusedError):
            _penvs.guard_probe_endpoint(endpoint)
    assert calls == []
    client = _client()
    refused = client.get(
        "/api/v1/local/bench/check", params={"endpoint": "https://api.openai.com"}
    )
    assert refused.status_code == 200, refused.text
    assert refused.json()["reachable"] is False
    assert calls == []
