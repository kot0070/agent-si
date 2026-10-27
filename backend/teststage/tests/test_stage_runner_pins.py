"""K03 HD 21:52 verdict pins: FLAKY never PASS + reason/code refusals.

Each frozen error code below is asserted in its own test against the real
``src/agent_si/test_runners/stage_runner.py`` loaded via the loader below
(no copies). MUST PASS on STEP2 code; each test kills its rule-mutation.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

_RUNNERS = (
    pathlib.Path(__file__).resolve().parents[3]
    / "src"
    / "agent_si"
    / "test_runners"
)


def _load(name):
    spec = importlib.util.spec_from_file_location(
        "k03_%s_pins" % name, _RUNNERS / ("%s.py" % name)
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runner = _load("stage_runner")

# FAKE-OF: verdict-pin test data (project/plan/run ids, output refs;
# test-only values).
PROJECT = "proj-k03-pins1"
PLAN = "plan-k03-pins1"


def test_flaky_never_counts_as_pass():
    run_id = "run-k03-pins-flaky"
    runner.start_stage(project_id=PROJECT, plan_id=PLAN, run_id=run_id)
    runner.record_result(
        run_id=run_id, test_id="t-login", status="PASS",
        output_ref="out://t-login", reason=None,
    )
    runner.record_result(
        run_id=run_id, test_id="t-offline", status="FLAKY",
        output_ref="out://t-offline", reason="retried once",
    )
    counters = runner.stage_counters(run_id=run_id)
    assert (counters.passed, counters.remaining, counters.active) == (1, 1, 0)


def test_blocked_without_reason_refused():
    run_id = "run-k03-pins-reason"
    runner.start_stage(project_id=PROJECT, plan_id=PLAN, run_id=run_id)
    with pytest.raises(Exception) as exc_info:
        runner.record_result(
            run_id=run_id, test_id="t-login", status="BLOCKED",
            output_ref="out://t-login", reason=None,
        )
    assert exc_info.value.code == "STATUS_REASON_MISSING"


def test_unknown_test_status_refused():
    run_id = "run-k03-pins-status"
    runner.start_stage(project_id=PROJECT, plan_id=PLAN, run_id=run_id)
    with pytest.raises(Exception) as exc_info:
        runner.record_result(
            run_id=run_id, test_id="t-login", status="MAYBE",
            output_ref="out://t-login", reason=None,
        )
    assert exc_info.value.code == "UNKNOWN_TEST_STATUS"
