"""DRF3K05A capability-tier admission + benchmark-steered splits (RED -> GREEN).

Row B0B-BP02-63: the served local path admits a local candidate per role
level only with capability-tier evidence plus health plus gate
(adapter.capability_tier_admit, called by check_admission on the
production admission path).
Row M-P4-129: benchmark results steer the cloud-vs-local split to deeper
levels (bench_runner.split_steer_record written by the queue_run
benchmark path, read by the split decision).

One behaviour test (drf3k05a-admit) through create_app + TestClient on the
real local backend; writes send x-actor + x-ui-session-token. No
FakeBench, no doubles, no skip, no xfail. FAILS on the old tree (no
capability-tier gate, no benchmark steering) and PASSES on the new tree.
"""

from __future__ import annotations

import inspect
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.local import adapter  # noqa: E402
from agent_si.local import bench_runner as runner  # noqa: E402
from agent_si.local.bench_protocol import BenchLevel  # noqa: E402
from agent_si.local.bench_runner import (  # noqa: E402
    BenchRefusedError,
    RunHandle,
    RunReservation,
)
from fastapi.testclient import TestClient  # noqa: E402

_TOKEN = "drf3k05a-ui-session-token-1"
_ACTOR = "drf3k05a-user"
_OWNER = "drf3k05a"
_HEADERS = {"x-actor": _ACTOR, "x-ui-session-token": _TOKEN}

_MEASURED_REF = "store-ref-drf3k05a-measured-routing-eligibility"
_HEALTHY = "model-health-healthy"
_IDLE = "gateway-state-idle"
_BUSY = "gateway-state-user-bench-running"
_SCOPE = "local-contact-allowed"


def _drain_scheduler() -> None:
    """Stop the active run and cancel this lane's queued reservations."""
    try:
        active = runner._ACTIVE_RUN_ID
    except AttributeError:
        active = None
    if active is not None:
        try:
            runner.stop_run(active)
        except KeyError:
            pass
    try:
        reservations = runner.list_reservations()
    except AttributeError:
        return
    for rsv in reservations:
        if rsv.status == "queued" and rsv.owner == _OWNER:
            try:
                runner.cancel_reservation(rsv.reservation_id, rsv.owner)
            except (KeyError, BenchRefusedError):
                pass


@pytest.fixture(autouse=True)
def _drf3k05a_isolation():
    """Clean scheduler slot plus pristine steer record; restore both after."""
    _drain_scheduler()
    prior_steer = dict(getattr(runner, "_SPLIT_STEER", {}) or {})
    initial = getattr(runner, "_SPLIT_STEER_INITIAL", None)
    if isinstance(initial, dict) and isinstance(
        getattr(runner, "_SPLIT_STEER", None), dict
    ):
        runner._SPLIT_STEER.clear()
        runner._SPLIT_STEER.update(initial)
    yield
    _drain_scheduler()
    if prior_steer and isinstance(getattr(runner, "_SPLIT_STEER", None), dict):
        runner._SPLIT_STEER.clear()
        runner._SPLIT_STEER.update(prior_steer)


def test_drf3k05a_admit() -> None:
    """drf3k05a-admit: served local entry admits per role level on tier plus
    health plus gate, and benchmark results steer the split to deeper levels.
    """
    # Served real local backend: app built with test settings carrying the
    # bound token (localbench + local-connect routes mount in create_app).
    app = create_app({"env": "test", "ui_session_token": _TOKEN})
    client = TestClient(app)

    # Served gate first: a write without the bound token is refused loudly.
    refused = client.post(
        "/api/v1/local/bench/runs",
        json={"model_id": "drf3k05a-model", "level": "Deep"},
    )
    assert refused.status_code in (401, 403)
    assert "SESSION_TOKEN_REFUSED" in refused.text

    # Served benchmark entry with the bound token: a Deep run starts.
    started = client.post(
        "/api/v1/local/bench/runs",
        json={"model_id": "drf3k05a-served", "level": "Deep"},
        headers=_HEADERS,
    )
    assert started.status_code == 200, started.text
    served_run_id = started.json()["run_id"]
    assert isinstance(served_run_id, str) and served_run_id

    # Served read at the deeper level needs no token.
    estimate = client.get(
        "/api/v1/local/bench/estimate",
        params={"model_id": "drf3k05a-served", "level": "Deep"},
    )
    assert estimate.status_code == 200, estimate.text
    assert estimate.json()["level"] == "Deep"

    # Served stop with the bound token frees the serial slot again.
    stopped = client.post(
        "/api/v1/local/bench/runs/stop",
        json={"run_id": served_run_id},
        headers=_HEADERS,
    )
    assert stopped.status_code == 200, stopped.text

    # Row B0B-BP02-63: per role level, tier evidence plus health plus gate.
    for role_level in ("quick", "standard", "deep"):
        verdict = adapter.capability_tier_admit(
            role_level, _MEASURED_REF, _HEALTHY, _IDLE
        )
        assert verdict.admitted is True
        assert verdict.gate_allowed is True
    assert (
        adapter.capability_tier_admit(
            "deep", "store-ref-drf3k05a-unknown", _HEALTHY, _IDLE
        ).admitted
        is False
    )
    assert (
        adapter.capability_tier_admit(
            "deep", _MEASURED_REF, "model-health-unhealthy", _IDLE
        ).admitted
        is False
    )
    busy = adapter.capability_tier_admit("deep", _MEASURED_REF, _HEALTHY, _BUSY)
    assert busy.admitted is False
    assert busy.gate_allowed is False
    assert (
        adapter.capability_tier_admit(
            "commander", _MEASURED_REF, _HEALTHY, _IDLE
        ).admitted
        is False
    )

    # Production wiring: check_admission admits through the same tier gate.
    served = adapter.check_admission(_MEASURED_REF, _HEALTHY, _IDLE, _SCOPE)
    assert served.admitted is True
    assert served.gate_allowed is True
    assert served.admission_refs == (_MEASURED_REF, _HEALTHY, _IDLE, _SCOPE)
    assert "capability_tier_admit" in inspect.getsource(adapter.check_admission)

    # Row M-P4-129: with no benchmark queued, even a Deep measured summary
    # stays cloud; the record starts pristine.
    record = runner.split_steer_record()
    assert record["benchmarked"] is False
    deep_summary = {
        "level": "Deep",
        "measured_score": 0.9,
        "proxy_score": 0.5,
        "tier": "MEASURED",
    }
    assert runner.steered_split(deep_summary)["split"] == "cloud"

    # The queue_run benchmark path writes the steering record deeper.
    outcome = runner.queue_run(
        "drf3k05a-model", BenchLevel.Deep, True, owner=_OWNER
    )
    assert isinstance(outcome, (RunHandle, RunReservation))
    record = runner.split_steer_record()
    assert record["benchmarked"] is True
    assert record["level"] == "Deep"
    assert record["depth"] == 2

    # Benchmark results now steer the split: Deep measured goes local while
    # the shallower level and evidence-free summaries stay cloud.
    assert runner.steered_split(deep_summary)["split"] == "local"
    assert (
        runner.steered_split(
            {
                "level": "Quick",
                "measured_score": 0.9,
                "proxy_score": 0.5,
                "tier": "MEASURED",
            }
        )["split"]
        == "cloud"
    )
    assert (
        runner.steered_split({"level": "Deep", "tier": "UNKNOWN"})["split"]
        == "cloud"
    )
