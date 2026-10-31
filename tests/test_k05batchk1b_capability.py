"""K05BATCH K1B capability proofs (ids k05batchk1b-*).

KB rows with wiring in coder-2 local files, proven on the real stack:
served HTTP routes (create_app + TestClient) where a route fronts the
behavior, else the real module entry points (no fakes, no doubles, no
skips, no xfails). Rows whose implementation lives in the sibling
coder's adapter file are proven by their frozen lane tests (drf3, nf7,
k05r7_admit) and cited in RETURN, not re-driven here.

Row map:
- R-360: served bench run while busy skips with BUSY_SKIP + evidence.
- R-371: served runs carry hardware profile + PROXY vs MEASURED rows.
- R-341: scan -> level -> run record with duration + PC-load warnings.
- ARCH-189/767: scheduler queue caps + owner/expiry leases.
- 111 + BP05-70: decision record required + project scope guard.
- 181: endpoint/model/permission validators + explicit patch only.
- BP05-29: DISCOVER-stage permission gate + scan rule.
- BP03-47: helper behind the idle gateway; busy refuses, release lands.
- BP06-44/48: used-level local_ai_allowed gate + activation no-mutation.

Globals touched get a snapshot-restore fixture; entries stay
JSON-serializable.
"""

from __future__ import annotations

import copy
import dataclasses
import importlib
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from agent_si.capability_store import store as _cap_store  # noqa: E402
from agent_si.local import bench_runner as _runner  # noqa: E402
from agent_si.local import config as _config  # noqa: E402
from agent_si.local import gateway as _gateway  # noqa: E402
from agent_si.local import k05r3_discover as _discover  # noqa: E402
from agent_si.local import k05r3_helper as _helper  # noqa: E402
from agent_si.local.bench_protocol import BenchLevel  # noqa: E402
from agent_si.local.bench_protocol import level_floor_minutes  # noqa: E402

TEST_IDS = (
    "k05batchk1b-busy-skip",
    "k05batchk1b-run-profile",
    "k05batchk1b-scan-record",
    "k05batchk1b-sched-caps",
    "k05batchk1b-config-gates",
    "k05batchk1b-discover-helper",
    "k05batchk1b-localonly",
)

_TOKEN = "tok-k05batchk1b-1"
_ACTOR = "k05batchk1b-user"
_HEADERS = {"x-actor": _ACTOR, "x-ui-session-token": _TOKEN}
_OWNER = "k05batchk1b"

_HEALTHY = "model-health-healthy"
_IDLE = "gateway-state-idle"
_SCOPE = "local-contact-allowed"
_MEASURED_REF = "store-ref-k05batchk1b-measured-routing-eligibility"


def _drain_k1b() -> None:
    """Stop any active run and cancel this lane's queued reservations."""
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
            except (KeyError, _runner.BenchRefusedError):
                pass


@pytest.fixture()
def k1b_state(monkeypatch):
    """Snapshot-restore every global the k1b proofs touch."""
    _drain_k1b()
    runner_dicts = {}
    for _name in (
        "_RUNS",
        "_PROGRESS",
        "_RUN_ROWS",
        "_RUN_HARDWARE",
        "_RUN_ADMISSION",
        "_RESERVATIONS",
        "_LEASES",
        "_RUN_LEASE",
    ):
        runner_dicts[_name] = copy.deepcopy(getattr(_runner, _name))
    runner_queue = list(_runner._QUEUE)
    runner_active = _runner._ACTIVE_RUN_ID
    runner_steer = dict(_runner._SPLIT_STEER)
    store_records = dict(_cap_store._RECORDS)
    store_by_ref = dict(_cap_store._RECORDS_BY_REF)
    config_store = dict(_config._STORE)
    helper_handles = dict(_helper._HANDLES)
    journal_override = _runner._JOURNAL_PATH_OVERRIDE
    _runner.set_journal_path(None)
    monkeypatch.delenv("AGENT_SI_UI_SESSION_TOKEN", raising=False)
    monkeypatch.delenv(_runner.JOURNAL_ENV_VAR, raising=False)
    monkeypatch.delenv("AGENT_SI_BENCH_RUN_ID", raising=False)
    monkeypatch.delenv("AGENT_SI_TEST_RUN_ID", raising=False)
    yield
    _drain_k1b()
    for _name, _saved in runner_dicts.items():
        _target = getattr(_runner, _name)
        _target.clear()
        _target.update(_saved)
    _runner._QUEUE[:] = runner_queue
    _runner._ACTIVE_RUN_ID = runner_active
    _runner._SPLIT_STEER.clear()
    _runner._SPLIT_STEER.update(runner_steer)
    _cap_store._RECORDS.clear()
    _cap_store._RECORDS.update(store_records)
    _cap_store._RECORDS_BY_REF.clear()
    _cap_store._RECORDS_BY_REF.update(store_by_ref)
    _config._STORE.clear()
    _config._STORE.update(config_store)
    _helper._HANDLES.clear()
    _helper._HANDLES.update(helper_handles)
    _runner.set_journal_path(journal_override)
    importlib.reload(_gateway)


def _served_client():
    """create_app + TestClient on the real served local entry."""
    from agent_si.backend.app import create_app

    app = create_app({"env": "test", "ui_session_token": _TOKEN})
    assert app.state.localbench_mounted is True
    from fastapi.testclient import TestClient

    return TestClient(app)


def test_k05batchk1b_busy_skip(k1b_state) -> None:
    """R-360: served run while busy skips with BUSY_SKIP + evidence."""
    assert TEST_IDS[0] == "k05batchk1b-busy-skip"
    client = _served_client()

    first = client.post(
        "/api/v1/local/bench/runs",
        json={"model_id": "k05batchk1b-first", "level": "Quick"},
        headers=_HEADERS,
    )
    assert first.status_code == 200, first.text
    first_run_id = first.json()["run_id"]
    assert isinstance(first_run_id, str) and first_run_id
    runs_before = client.get("/api/v1/local/bench/history").json()

    second = client.post(
        "/api/v1/local/bench/runs",
        json={"model_id": "k05batchk1b-second", "level": "Quick"},
        headers=_HEADERS,
    )
    assert second.status_code == 409, second.text
    assert "BUSY_SKIP" in second.text

    assert client.get("/api/v1/local/bench/history").json() == runs_before
    assert _runner._ACTIVE_RUN_ID == first_run_id

    row = _cap_store.get_evidence(
        "k05batchk1b-second", _runner._BUSY_SKIP_TASK_CLASS
    )
    assert row is not None
    assert row.evidence_ref
    assert _cap_store.require_current(row.evidence_ref).model_id == (
        "k05batchk1b-second"
    )
    assert json.dumps(
        {"model_id": row.model_id, "tier": row.tier.value,
         "evidence_ref": row.evidence_ref}
    )

    stopped = client.post(
        "/api/v1/local/bench/runs/stop",
        json={"run_id": first_run_id},
        headers=_HEADERS,
    )
    assert stopped.status_code == 200, stopped.text


def test_k05batchk1b_run_profile(k1b_state) -> None:
    """R-371: served runs carry hardware profile + PROXY vs MEASURED."""
    assert TEST_IDS[1] == "k05batchk1b-run-profile"
    client = _served_client()

    started = client.post(
        "/api/v1/local/bench/runs",
        json={"model_id": "k05batchk1b-profile", "level": "Quick"},
        headers=_HEADERS,
    )
    assert started.status_code == 200, started.text
    run_id = started.json()["run_id"]

    hardware = _runner.run_hardware(run_id)
    assert hardware.cpu_only is True
    assert isinstance(hardware.ram_mb, int) and hardware.ram_mb >= 0
    assert json.dumps(
        {"gpu_vendor": hardware.gpu_vendor, "ram_mb": hardware.ram_mb,
         "cpu_only": hardware.cpu_only}
    )

    proxy = _cap_store.get_evidence("k05batchk1b-profile", "localbench:Quick")
    assert proxy is not None
    assert proxy.tier == _cap_store.EvidenceTier.PROXY
    assert proxy.environment_fingerprint
    assert proxy.evidence_ref.startswith("cap:proxy:")

    stopped = client.post(
        "/api/v1/local/bench/runs/stop",
        json={"run_id": run_id},
        headers=_HEADERS,
    )
    assert stopped.status_code == 200, stopped.text

    admitted = _runner.start_run(
        "k05batchk1b-admitted",
        BenchLevel.Quick,
        True,
        admission={
            "capability_store_ref": _MEASURED_REF,
            "health_ref": _HEALTHY,
            "gateway_state_ref": _IDLE,
            "permission_scope": _SCOPE,
        },
    )
    assert isinstance(admitted, _runner.RunHandle)
    verdict = _runner.run_admission(admitted.run_id)
    assert verdict is not None and verdict.admitted is True
    assert verdict.gate_allowed is True
    _runner.stop_run(admitted.run_id)

    runs_before = _runner.list_run_ids()
    with pytest.raises(_runner.BenchRefusedError) as excinfo:
        _runner.start_run(
            "k05batchk1b-refused",
            BenchLevel.Quick,
            True,
            admission={
                "capability_store_ref": _MEASURED_REF,
                "health_ref": _HEALTHY,
                "gateway_state_ref": _IDLE,
                "permission_scope": "wrong-scope",
            },
        )
    assert "ADMISSION_PERMISSION_REFUSED" in str(excinfo.value)
    assert _runner.list_run_ids() == runs_before


def test_k05batchk1b_scan_record(k1b_state, tmp_path) -> None:
    """R-341: scan -> level -> run record with duration + warnings lands."""
    assert TEST_IDS[2] == "k05batchk1b-scan-record"
    client = _served_client()

    models_dir = tmp_path / "models"
    models_dir.mkdir()
    (models_dir / "k05batchk1b-8b.gguf").write_text(
        "fake-weights", encoding="utf-8"
    )

    scanned = client.get(
        "/api/v1/local/bench/scan",
        params={"path": str(models_dir), "allowlist": str(tmp_path)},
    )
    assert scanned.status_code == 200, scanned.text
    assert scanned.json() == ["k05batchk1b-8b.gguf"]

    estimate = client.get(
        "/api/v1/local/bench/estimate",
        params={"model_id": "k05batchk1b-tool", "level": "Quick"},
    )
    assert estimate.status_code == 200, estimate.text
    assert estimate.json()["minutes_min"] >= 5.0

    got = _runner.bench_scan_record(
        allowlist_dirs=[str(tmp_path)],
        requested_path=str(models_dir),
        model_id="k05batchk1b-tool",
        model_params_b=8.0,
        level="Quick",
        pc_in_use=True,
        work_dir=str(tmp_path),
    )
    assert got["models"] == ["k05batchk1b-8b.gguf"]
    assert got["level"] == BenchLevel.Quick.value
    assert (got["floor_minutes_min"], got["floor_minutes_max"]) == (
        level_floor_minutes(BenchLevel.Quick, 8.0)
    )
    codes = [warning["code"] for warning in got["warnings"]]
    assert codes == ["BENCH_DURATION", "BENCH_PC_IN_USE"]
    assert got["duration_s"] >= 0.0
    assert json.dumps(got)

    row = _cap_store.get_evidence("k05batchk1b-tool", got["task_class"])
    assert row is not None
    assert row.tier == _cap_store.EvidenceTier.MEASURED
    assert _cap_store.require_current(got["evidence_ref"]).model_id == (
        "k05batchk1b-tool"
    )

    scaled = _runner.bench_scan_record(
        allowlist_dirs=[str(tmp_path)],
        requested_path=str(models_dir),
        model_id="k05batchk1b-tool-16b",
        model_params_b=16.0,
        level="Quick",
        pc_in_use=False,
        work_dir=str(tmp_path),
    )
    assert scaled["floor_minutes_min"] == 2.0 * got["floor_minutes_min"]
    assert [warning["code"] for warning in scaled["warnings"]] == [
        "BENCH_DURATION"
    ]


def test_k05batchk1b_sched_caps(k1b_state) -> None:
    """ARCH-189/767: excess demand queues under caps; leases own + expire."""
    assert TEST_IDS[3] == "k05batchk1b-sched-caps"
    head = _runner.queue_run(
        "k05batchk1b-q0", BenchLevel.Quick, True, owner=_OWNER
    )
    assert isinstance(head, _runner.RunHandle)
    lease = _runner.lease_for_run(head.run_id)
    assert lease is not None and lease.owner == _OWNER
    assert _runner.lease_is_live(lease.lease_id) is True

    waiting = [
        _runner.queue_run(
            "k05batchk1b-q%d" % index, BenchLevel.Quick, True, owner=_OWNER
        )
        for index in range(1, _runner.MAX_QUEUED_RESERVATIONS + 1)
    ]
    assert all(
        isinstance(rsv, _runner.RunReservation) for rsv in waiting
    )
    with pytest.raises(_runner.BenchBusyError):
        _runner.queue_run(
            "k05batchk1b-qfull", BenchLevel.Quick, True, owner=_OWNER
        )

    waiting[0].expires_at = _runner._now_s() - 1.0
    _runner.stop_run(head.run_id)
    promoted = _runner.pump_queue()
    assert promoted is not None
    assert isinstance(promoted, _runner.RunHandle)
    assert waiting[0].status == "expired"
    assert waiting[1].status == "promoted"
    assert promoted.model_id == waiting[1].model_id
    for rsv in waiting[2:]:
        if rsv.status == "queued":
            _runner.cancel_reservation(rsv.reservation_id, _OWNER)
    _runner.stop_run(promoted.run_id)

    released = _runner.release_lease(lease.lease_id, _OWNER)
    assert released.released is True
    assert json.dumps(
        {"lease_id": lease.lease_id, "owner": lease.owner,
         "released": released.released}
    )


def test_k05batchk1b_config_gates(k1b_state) -> None:
    """111 + BP05-70 + 181: decision required, scope guarded, explicit patch."""
    assert TEST_IDS[4] == "k05batchk1b-config-gates"
    key = "proj-k05batchk1b"
    rec = _config.record_decision(key, "stmt", "reason", "owner")
    assert rec.project_id == key
    assert rec.decision_id.startswith("dec-")
    assert json.dumps(dataclasses.asdict(rec))

    cfg = _config.LocalAIConfig(
        project_key=key,
        endpoint_url="http://127.0.0.1:11434",
        model_id="m",
        permission_scope="local-contact-allowed",
    )
    with pytest.raises(_config.LocalAISettingsError) as excinfo:
        _config.save_config(cfg, None)
    assert excinfo.value.code == _config.LOCAL_AI_DECISION_RECORD_REQUIRED
    _config.save_config(cfg, rec)
    assert _config.load_config(key, key) == cfg
    with pytest.raises(_config.LocalAISettingsError) as excinfo2:
        _config.load_config(key, "proj-other")
    assert excinfo2.value.code == _config.LOCAL_AI_PROJECT_SCOPE_VIOLATION

    with pytest.raises(_config.LocalAISettingsError) as excinfo3:
        _config.validate_endpoint("no-scheme-here")
    assert excinfo3.value.code == _config.LOCAL_AI_INVALID_ENDPOINT
    with pytest.raises(_config.LocalAISettingsError):
        _config.validate_model("")
    with pytest.raises(_config.LocalAISettingsError) as excinfo4:
        _config.validate_permission("wrong-scope")
    assert excinfo4.value.code == _config.LOCAL_AI_INVALID_PERMISSION

    rec2 = _config.record_decision(key, "patch model", "r", "owner")
    updated = _config.update_config(key, {"model_id": "m2"}, rec2)
    assert updated.model_id == "m2"
    with pytest.raises(_config.LocalAISettingsError) as excinfo5:
        _config.update_config(key, {"capability_evidence": "X"}, rec2)
    assert excinfo5.value.code == _config.LOCAL_AI_AMBIGUOUS_FIELD


def test_k05batchk1b_discover_helper(k1b_state, tmp_path, monkeypatch) -> None:
    """BP05-29 + BP03-47: discover gate + helper behind idle gateway."""
    assert TEST_IDS[5] == "k05batchk1b-discover-helper"
    from agent_si.local import adapter as _adapter

    grant = _discover.enter_discover(
        _adapter.LifecycleStage.SCAN, "local-contact-allowed"
    )
    assert grant.stage is _adapter.LifecycleStage.DISCOVER
    assert grant.identity_state == _discover.DISCOVER_IDENTITY_UNKNOWN
    with pytest.raises(_discover.DiscoverError) as excinfo:
        _discover.enter_discover(
            _adapter.LifecycleStage.SCAN, "wrong-scope"
        )
    assert excinfo.value.code == _discover.K05R3_DISCOVER_PERMISSION_REFUSED
    with pytest.raises(_discover.DiscoverError) as excinfo2:
        _discover.enter_discover(
            _adapter.LifecycleStage.DISCOVER, "local-contact-allowed"
        )
    assert excinfo2.value.code == _discover.K05R3_DISCOVER_STAGE_REFUSED

    target = tmp_path / "models"
    target.mkdir()
    (target / "m.gguf").write_text("weights", encoding="utf-8")
    assert _discover.scan_roots([str(tmp_path)], str(target)) == ["m.gguf"]
    creds = tmp_path / "secrets"
    creds.mkdir()
    with pytest.raises(_discover.DiscoverError):
        _discover.scan_roots([str(tmp_path)], str(creds))

    attached = _helper.attach_helper("assign-k05batchk1b-1")
    assert attached.started is False
    assert attached.gateway_reason == _gateway.GATEWAY_IDLE_REASON
    importlib.reload(_gateway)
    started = _helper.start_helper(attached)
    assert started.started is True
    with pytest.raises(_helper.HelperError) as excinfo3:
        _helper.start_helper(attached)
    assert excinfo3.value.code == _helper.K05R3_HELPER_STATE_REFUSED
    importlib.reload(_gateway)
    released = _helper.release_helper(started)
    assert released.started is True
    assert isinstance(released.gateway_reason, str) and released.gateway_reason
    monkeypatch.setenv("AGENT_SI_BENCH_RUN_ID", "user-bench-1")
    with pytest.raises(_helper.HelperError) as excinfo4:
        _helper.attach_helper("assign-k05batchk1b-2")
    assert excinfo4.value.code == _helper.K05R3_HELPER_GATEWAY_BUSY
    with pytest.raises(_helper.HelperError):
        _helper.attach_helper("")


def test_k05batchk1b_localonly(k1b_state) -> None:
    """BP06-44 + BP06-48: used-level gate + activation never mutates store."""
    assert TEST_IDS[6] == "k05batchk1b-localonly"
    key = "proj-k05batchk1b-lo"
    decision = _config.record_decision(key, "enable local-only", "r", "owner")
    _config.save_config(
        _config.LocalAIConfig(
            project_key=key,
            endpoint_url="http://127.0.0.1:11434",
            model_id="llama3.1:8b",
            permission_scope="local-contact-allowed",
            local_only_mode=True,
        ),
        decision,
    )
    cfg = _config.load_config(key, key)
    ok_levels = [
        {"level": "quick", "local_ai_allowed": True},
        {"level": "deep", "local_ai_allowed": True,
         "resource_cap": {"vram_gb": 8.0}},
    ]
    assert _config.require_local_ai_allowed_at_used_levels(cfg, ok_levels) == [
        "quick",
        "deep",
    ]
    with pytest.raises(_config.LocalAISettingsError) as excinfo:
        _config.require_local_ai_allowed_at_used_levels(cfg, [{"level": "q2"}])
    assert excinfo.value.code == _config.LOCAL_AI_LOCAL_ONLY_VIOLATION
    with pytest.raises(_config.LocalAISettingsError):
        _config.require_local_ai_allowed_at_used_levels(
            cfg, [{"level": "x", "local_ai_allowed": True, "resource_cap": {}}]
        )

    before = copy.deepcopy(_config._STORE.get(key))
    assert _config.check_local_only_activation(
        key, [{"level": "q", "local_ai_allowed": True}]
    ) is True
    with pytest.raises(_config.LocalAISettingsError) as excinfo2:
        _config.check_local_only_activation(key, [{"level": "q"}])
    assert excinfo2.value.code == _config.LOCAL_AI_LOCAL_ONLY_VIOLATION
    assert _config._STORE.get(key) == before
