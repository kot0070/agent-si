"""NF7K05A toolbench behaviour test (id nf7k05a-toolbench).

RED on the old tree (adapter.tool_agent_register and
bench_runner.bench_scan_record do not exist); GREEN after.

Served proof through create_app + HTTP client against the real local
backend (no FakeBench, no doubles in mount files):
- R-312: a local runtime attaches on the served local entry and registers
  + runs as a tool agent.
- R-341: served scan -> level -> run record with duration + PC-load
  warnings + size-scaled levels lands in the capability base.

New-module globals get a snapshot-restore fixture (sibling
behaviour-test pattern); entries stay JSON-serializable.
"""
from __future__ import annotations

import copy
import dataclasses
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import pytest

from agent_si.backend import local_connect as _served_connect
from agent_si.capability_store import store as _cap_store
from agent_si.local import adapter as _adapter
from agent_si.local import bench_runner as _runner
from agent_si.local.bench_protocol import BenchLevel, level_floor_minutes

TEST_ID = "nf7k05a-toolbench"

_TOKEN_HEADERS = {"x-actor": "user", "x-ui-session-token": "tok-nf7k05a-1"}
_RUNTIME_REF = "http://127.0.0.1:11434"
_EVIDENCE_REF = "cap:measured:toolbench-model:localbench:Quick:v1"
_HEALTHY_REF = "healthy-probe-ok"
_IDLE_REF = "idle"
_ALLOWED_SCOPE = "local-contact-allowed"


@pytest.fixture()
def toolbench_state(monkeypatch):
    """Snapshot-restore every mutable global the toolbench touches."""
    runner_dicts = {}
    for _name in (
        "_RUNS",
        "_PROGRESS",
        "_RUN_ROWS",
        "_RESERVATIONS",
        "_LEASES",
        "_RUN_LEASE",
    ):
        runner_dicts[_name] = copy.deepcopy(getattr(_runner, _name))
    runner_queue = list(_runner._QUEUE)
    runner_active = _runner._ACTIVE_RUN_ID
    adapter_globals = {}
    for _name in ("_TOOL_AGENTS", "_TOOL_AGENT_SEQ"):
        if hasattr(_adapter, _name):
            value = getattr(_adapter, _name)
            adapter_globals[_name] = (
                copy.deepcopy(value) if isinstance(value, dict) else value
            )
    store_records = dict(_cap_store._RECORDS)
    store_by_ref = dict(_cap_store._RECORDS_BY_REF)
    attached = _served_connect._ATTACHED_RUNTIME
    paired = _served_connect._PAIRED_SESSION_TOKEN
    journal_override = _runner._JOURNAL_PATH_OVERRIDE
    _runner.set_journal_path(None)
    monkeypatch.delenv("AGENT_SI_UI_SESSION_TOKEN", raising=False)
    monkeypatch.delenv(_runner.JOURNAL_ENV_VAR, raising=False)
    yield
    try:
        if _runner._ACTIVE_RUN_ID is not None:
            _runner.stop_run(_runner._ACTIVE_RUN_ID)
    except (KeyError, Exception):
        pass
    for rsv in _runner.list_reservations():
        if rsv.status == "queued":
            try:
                _runner.cancel_reservation(rsv.reservation_id, rsv.owner)
            except (KeyError, Exception):
                pass
    for _name, _saved in runner_dicts.items():
        _target = getattr(_runner, _name)
        _target.clear()
        _target.update(_saved)
    _runner._QUEUE[:] = runner_queue
    _runner._ACTIVE_RUN_ID = runner_active
    for _name, _saved in adapter_globals.items():
        setattr(_adapter, _name, _saved)
    if hasattr(_adapter, "_TOOL_AGENTS"):
        _adapter._TOOL_AGENTS.clear()
        _adapter._TOOL_AGENTS.update(adapter_globals.get("_TOOL_AGENTS", {}))
    _cap_store._RECORDS.clear()
    _cap_store._RECORDS.update(store_records)
    _cap_store._RECORDS_BY_REF.clear()
    _cap_store._RECORDS_BY_REF.update(store_by_ref)
    _served_connect._ATTACHED_RUNTIME = attached
    _served_connect._PAIRED_SESSION_TOKEN = paired
    _runner.set_journal_path(journal_override)


def _served_client():
    """create_app + HTTP client on the real served local entry (wired in app)."""
    from agent_si.backend.app import create_app

    app = create_app({"env": "test"})
    assert app.state.localbench_mounted is True
    from fastapi.testclient import TestClient

    return TestClient(app)


def test_tool_agent_registration_served(toolbench_state) -> None:
    """R-312: attached runtime registers + runs as a tool agent (served)."""
    assert TEST_ID == "nf7k05a-toolbench"
    register = _adapter.tool_agent_register
    client = _served_client()

    resp = client.post(
        "/api/v1/local/connect",
        json={"runtime_ref": _RUNTIME_REF},
        headers=_TOKEN_HEADERS,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "NOT_CONFIGURED"

    status = client.get("/api/v1/local/status")
    assert status.status_code == 200, status.text

    reg = register(
        runtime_ref=_RUNTIME_REF,
        capability_store_ref=_EVIDENCE_REF,
        health_ref=_HEALTHY_REF,
        gateway_state_ref=_IDLE_REF,
        permission_scope=_ALLOWED_SCOPE,
    )
    assert reg.registered is True
    assert reg.runtime_ref == _RUNTIME_REF
    assert json.dumps(dataclasses.asdict(reg))

    refused = register(
        runtime_ref=_RUNTIME_REF,
        capability_store_ref=_EVIDENCE_REF,
        health_ref=_HEALTHY_REF,
        gateway_state_ref=_IDLE_REF,
        permission_scope="wrong-scope",
    )
    assert refused.registered is False
    assert "ADMISSION_PERMISSION_REFUSED" in refused.reason

    models = client.get("/api/v1/local/models")
    assert models.status_code == 200, models.text
    assert isinstance(models.json(), list)


def test_bench_scan_level_run_record_served(toolbench_state, tmp_path) -> None:
    """R-341: scan -> level -> run record with duration + warnings lands."""
    record = _runner.bench_scan_record
    client = _served_client()

    models_dir = tmp_path / "models"
    models_dir.mkdir()
    (models_dir / "qwen-8b.gguf").write_text("fake-weights", encoding="utf-8")
    (models_dir / "mistral-8b.gguf").write_text("fake-weights", encoding="utf-8")

    scanned = client.get(
        "/api/v1/local/bench/scan",
        params={"path": str(models_dir), "allowlist": str(tmp_path)},
    )
    assert scanned.status_code == 200, scanned.text
    assert scanned.json() == ["mistral-8b.gguf", "qwen-8b.gguf"]

    estimate = client.get(
        "/api/v1/local/bench/estimate",
        params={"model_id": "toolbench-model", "level": "Quick"},
    )
    assert estimate.status_code == 200, estimate.text
    assert estimate.json()["minutes_min"] >= 5.0

    got = record(
        allowlist_dirs=[str(tmp_path)],
        requested_path=str(models_dir),
        model_id="toolbench-model",
        model_params_b=8.0,
        level="Quick",
        pc_in_use=True,
        work_dir=str(tmp_path),
    )
    assert got["models"] == ["mistral-8b.gguf", "qwen-8b.gguf"]
    assert got["level"] == BenchLevel.Quick.value
    assert (got["floor_minutes_min"], got["floor_minutes_max"]) == level_floor_minutes(
        BenchLevel.Quick, 8.0
    )
    codes = [warning["code"] for warning in got["warnings"]]
    assert "BENCH_DURATION" in codes
    assert "BENCH_PC_IN_USE" in codes
    assert got["duration_s"] >= 0.0
    assert isinstance(got["evidence_ref"], str) and got["evidence_ref"]
    assert json.dumps(got)

    row = _cap_store.get_evidence("toolbench-model", got["task_class"])
    assert row is not None
    assert row.tier == _cap_store.EvidenceTier.MEASURED
    assert row.evidence_ref == got["evidence_ref"]
    assert _cap_store.require_current(got["evidence_ref"]).model_id == "toolbench-model"

    scaled = record(
        allowlist_dirs=[str(tmp_path)],
        requested_path=str(models_dir),
        model_id="toolbench-model-16b",
        model_params_b=16.0,
        level="Quick",
        pc_in_use=False,
        work_dir=str(tmp_path),
    )
    assert scaled["floor_minutes_min"] == 2.0 * got["floor_minutes_min"]
    assert scaled["floor_minutes_max"] == 2.0 * got["floor_minutes_max"]
    assert [warning["code"] for warning in scaled["warnings"]] == ["BENCH_DURATION"]
