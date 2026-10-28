"""K05R5 M-BENCH floors: Q7 floors match BUILD_PLAN (values plus row text).

RED before the bench_protocol row-text fix (the BUILD_PLAN row-text
assertion fails); GREEN after. The behaviour guards (exact floors, linear
size scaling, fail-closed sizes, estimate integration) prove the values
stay BUILD_PLAN values. Fakes live here only, none needed (real entries).
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))

import pytest

from agent_si.backend import localbench_routes as routes
from agent_si.local import bench_protocol as proto
from agent_si.local import bench_runner as runner
from agent_si.local.bench_protocol import BenchLevel
from agent_si.local.bench_runner import Calibration

#: BUILD_PLAN floor row text staged in-repo (expose-check row:
#: _task/FIT_K05_M3.md:5; frozen test pins the values:
#: tests/local/test_iface_m3.py:33-37).
BUILD_PLAN_ROW_TEXT = "Quick ~10-15min@8B, Standard 30-60, Deep 120+"

#: BUILD_PLAN reference minima in minutes at 8B params.
REFERENCE_FLOORS = {
    BenchLevel.Quick: (10.0, 15.0),
    BenchLevel.Standard: (30.0, 60.0),
    BenchLevel.Deep: (120.0, 180.0),
}


def test_row_text_quotes_build_plan() -> None:
    """The floor row text carries the BUILD_PLAN row verbatim (leak 2 fix)."""
    assert BUILD_PLAN_ROW_TEXT in (proto.__doc__ or "")


def test_floors_match_build_plan_at_reference() -> None:
    for level, expected in REFERENCE_FLOORS.items():
        assert proto.level_floor_minutes(level, 8.0) == expected


def test_floors_scale_linearly_with_model_size() -> None:
    for level, (lo, hi) in REFERENCE_FLOORS.items():
        assert proto.level_floor_minutes(level, 4.0) == (lo / 2.0, hi / 2.0)
        assert proto.level_floor_minutes(level, 16.0) == (lo * 2.0, hi * 2.0)


def test_floors_fail_closed_on_unknown_size() -> None:
    for bad in (0.0, -2.0, float("nan")):
        for level, expected in REFERENCE_FLOORS.items():
            assert proto.level_floor_minutes(level, bad) == expected


def test_floors_reject_bad_inputs() -> None:
    with pytest.raises(ValueError):
        proto.level_floor_minutes(BenchLevel.Quick, "8B")
    with pytest.raises(ValueError):
        proto.level_floor_minutes("Quickish", 8.0)


def test_estimates_honor_floors_at_reference_calibration() -> None:
    for level, (lo, hi) in REFERENCE_FLOORS.items():
        cal = Calibration(model_id="FAKE-OF: floors model", seconds_per_case=1.0)
        est = runner.estimate_run("FAKE-OF: floors model", level, cal)
        assert (est.minutes_min, est.minutes_max) == (lo, hi)


def test_routes_estimate_honors_floors() -> None:
    for level, (lo, hi) in REFERENCE_FLOORS.items():
        est = routes.estimate_route("FAKE-OF: floors model", level)
        assert (est.minutes_min, est.minutes_max) == (lo, hi)
