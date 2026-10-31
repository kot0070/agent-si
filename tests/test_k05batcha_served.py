"""K05BATCH Onyx behaviour tests (ids k05batcha-busy-skip, k05batcha-run-profile).

Row R-360 (local-AI safety): a served bench run arriving while the
machine is busy is skipped by the passive check with skip reason
BUSY_SKIP; the skip records capability evidence; nothing is pulled or
deleted.
Row R-371 (hardware/runtime evidence): served bench runs carry their
hardware profile with PROXY vs MEASURED evidence via check_admission
on the production call path.

Both proofs run through create_app + TestClient on the real local
backend (no fakes, no doubles in mount files, no skip, no xfail).
Globals touched get a snapshot-restore fixture; entries stay
JSON-serializable.
"""

from __future__ import annotations

import copy
import inspect
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from agent_si.capability_store import store as _cap_store  # noqa: E402
from agent_si.local import bench_runner as _runner  # noqa: E402
from agent_si.local.bench_protocol import BenchLevel  # noqa: E402

TEST_IDS = ("k05batcha-busy-skip", "k05batcha-run-profile")

_TOKEN = "tok-k05batcha-1"
_ACTOR = "k05batcha-user"
_HEADERS = {"x-actor": _ACTOR, "x-ui-session-token": _TOKEN}

_HEALTHY = "model-health-healthy"
_IDLE = "gateway-state-idle"
_SCOPE = "local-contact-allowed"
_MEASURED_REF = "store-ref-k05batcha-measured-routing-eligibility"


@pytest.fixture()
def batcha_state():
    """Snapshot-restore every global the batcha proofs touch."""
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
    _runner._SPLIT_STEER.clear()
    _runner._SPLIT_STEER.update(runner_steer)
    _cap_store._RECORDS.clear()
    _cap_store._RECORDS.update(store_records)
    _cap_store._RECORDS_BY_REF.clear()
    _cap_store._RECORDS_BY_REF.update(store_by_ref)


def _served_client():
    """create_app + TestClient on the real served local entry."""
    from agent_si.backend.app import create_app

    app = create_app({"env": "test", "ui_session_token": _TOKEN})
    assert app.state.localbench_mounted is True
    from fastapi.testclient import TestClient

    return TestClient(app)


def test_k05batcha_busy_skip(batcha_state) -> None:
    """R-360: served run while busy skips with BUSY_SKIP + evidence."""
    assert TEST_IDS[0] == "k05batcha-busy-skip"
    client = _served_client()

    first = client.post(
        "/api/v1/local/bench/runs",
        json={"model_id": "k05batcha-first", "level": "Quick"},
        headers=_HEADERS,
    )
    assert first.status_code == 200, first.text
    first_run_id = first.json()["run_id"]
    assert isinstance(first_run_id, str) and first_run_id
    runs_before = client.get("/api/v1/local/bench/history").json()

    second = client.post(
        "/api/v1/local/bench/runs",
        json={"model_id": "k05batcha-second", "level": "Quick"},
        headers=_HEADERS,
    )
    assert second.status_code == 409, second.text
    assert "BUSY_SKIP" in second.text

    assert client.get("/api/v1/local/bench/history").json() == runs_before
    assert _runner._ACTIVE_RUN_ID == first_run_id

    row = _cap_store.get_evidence("k05batcha-second", _runner._BUSY_SKIP_TASK_CLASS)
    assert row is not None
    assert row.evidence_ref
    assert json.dumps(
        {"model_id": row.model_id, "task_class": row.task_class,
         "tier": row.tier.value, "evidence_ref": row.evidence_ref}
    )
    assert _cap_store.require_current(row.evidence_ref).model_id == "k05batcha-second"

    stopped = client.post(
        "/api/v1/local/bench/runs/stop",
        json={"run_id": first_run_id},
        headers=_HEADERS,
    )
    assert stopped.status_code == 200, stopped.text


def test_k05batcha_run_profile(batcha_state, tmp_path) -> None:
    """R-371: served runs carry hardware profile with PROXY vs MEASURED."""
    assert TEST_IDS[1] == "k05batcha-run-profile"
    client = _served_client()

    started = client.post(
        "/api/v1/local/bench/runs",
        json={"model_id": "k05batcha-profile", "level": "Quick"},
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

    proxy = _cap_store.get_evidence("k05batcha-profile", "localbench:Quick")
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

    assert "check_admission" in inspect.getsource(_runner.start_run)
    admitted = _runner.start_run(
        "k05batcha-admitted",
        BenchLevel.Quick,
        True,
        admission={
            "capability_store_ref": _MEASURED_REF,
            "health_ref": _HEALTHY,
            "gateway_state_ref": _IDLE,
            "permission_scope": _SCOPE,
        },
    )
    assert not isinstance(admitted, _runner.RunSkip)
    verdict = _runner.run_admission(admitted.run_id)
    assert verdict is not None and verdict.admitted is True
    assert verdict.gate_allowed is True
    _runner.stop_run(admitted.run_id)

    runs_before = _runner.list_run_ids()
    with pytest.raises(_runner.BenchRefusedError) as excinfo:
        _runner.start_run(
            "k05batcha-refused",
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

    models_dir = tmp_path / "models"
    models_dir.mkdir()
    (models_dir / "batcha-8b.gguf").write_text("fake-weights", encoding="utf-8")
    results_csv = tmp_path / "results.csv"
    results_csv.write_text(
        "case_id,kind,model_id\nq1,MEASURED,k05batcha-profile\n"
        "q2,MEASURED,k05batcha-profile\n",
        encoding="utf-8",
    )
    (tmp_path / "manifest.json").write_text(
        json.dumps({"level": "Quick"}), encoding="utf-8"
    )
    imported = client.post(
        "/api/v1/local/bench/import",
        json={"path": str(results_csv)},
        headers=_HEADERS,
    )
    assert imported.status_code == 200, imported.text

    measured = _cap_store.get_evidence("k05batcha-profile", "localbench:Quick")
    assert measured is not None
    assert measured.tier == _cap_store.EvidenceTier.MEASURED
    assert _cap_store.require_current(measured.evidence_ref).model_id == (
        "k05batcha-profile"
    )
