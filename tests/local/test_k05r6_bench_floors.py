"""K05R6 M-FLOORS: hard floors beneath the scaled level floors.

RED before the bench_protocol hard-floor fix (smallest-size assertions fail
on unfixed code); GREEN after. Behaviour tests through the real
level_floor_minutes (+ estimate_run at 8B); no fakes of product logic.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))

from agent_si.local import bench_protocol as proto
from agent_si.local import bench_runner as runner
from agent_si.local.bench_protocol import BenchLevel
from agent_si.local.bench_runner import Calibration

#: Frozen Q7 base floors at 8B (unchanged by M-FLOORS).
_BASE_FLOORS = {
    BenchLevel.Quick: (10.0, 15.0),
    BenchLevel.Standard: (30.0, 60.0),
    BenchLevel.Deep: (120.0, 180.0),
}

#: NEW M-FLOORS rule: one hard floor per level, applied to BOTH bounds.
_HARD_FLOORS = {
    BenchLevel.Quick: 5.0,
    BenchLevel.Standard: 15.0,
    BenchLevel.Deep: 30.0,
}

SMALLEST_B = 1.0
LARGEST_B = 70.0
REFERENCE_B = 8.0


def _scaled(level: BenchLevel, params_b: float) -> tuple[float, float]:
    lo, hi = _BASE_FLOORS[level]
    scale = params_b / 8.0
    return (lo * scale, hi * scale)


def test_smallest_size_class_hits_hard_floors() -> None:
    """At 1.0B every scaled bound falls below its HARD floor, so both clamp."""
    for level, hard in _HARD_FLOORS.items():
        assert proto.level_floor_minutes(level, SMALLEST_B) == (hard, hard)


def test_largest_size_class_uses_scaled_floors() -> None:
    """At 70.0B every scaled bound sits above its HARD floor, so max() is a no-op."""
    for level, hard in _HARD_FLOORS.items():
        got = proto.level_floor_minutes(level, LARGEST_B)
        assert got == _scaled(level, LARGEST_B)
        assert got[0] >= hard and got[1] >= hard


def test_reference_8b_stays_inside_q7_targets() -> None:
    """At 8B max() is a no-op: every HARD floor sits below its scaled bounds."""
    for level, expected in _BASE_FLOORS.items():
        assert proto.level_floor_minutes(level, REFERENCE_B) == expected


def test_fail_closed_sizes_still_never_zero() -> None:
    """Fail-closed sizes (0/negative/NaN -> scale 1.0) stay above HARD floors."""
    for bad in (0.0, -2.0, float("nan")):
        for level, expected in _BASE_FLOORS.items():
            got = proto.level_floor_minutes(level, bad)
            assert got == expected
            assert got[0] >= _HARD_FLOORS[level] and got[1] >= _HARD_FLOORS[level]


def test_estimate_run_unchanged_at_reference_calibration() -> None:
    """Nominal calibration at 8B still yields exactly the Q7 targets."""
    for level, (lo, hi) in _BASE_FLOORS.items():
        cal = Calibration(model_id="FAKE-OF: floors model", seconds_per_case=1.0)
        est = runner.estimate_run("FAKE-OF: floors model", level, cal)
        assert (est.minutes_min, est.minutes_max) == (lo, hi)
