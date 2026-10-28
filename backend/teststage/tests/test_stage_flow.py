"""K03 STEP1 behaviour contract: TEST stage flow + gateway spend leg + resume.

Rows 246 / M-P4-155 / M-R-REAL-API. MUST FAIL on stubs.

Entry points: real stub symbols are loaded from
``src/agent_si/test_runners/{test_planner,permission_ladder,stage_runner,ask_resume}.py``
via the loader below (no copies). STEP2 error types must expose ``.code``
with the frozen name; each code below is asserted in its own test. STEP1 RED
mechanism per test: stub bodies return None / raise nothing, so every
behaviour test below is marked strict-xfail (reason 'laneB: <row>'): the
frozen suite runs green-with-xfail and each marker flips when STEP2 lands.
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
        "k03_%s_stub" % name, _RUNNERS / ("%s.py" % name)
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


planner = _load("test_planner")
ladder = _load("permission_ladder")
runner = _load("stage_runner")
ask = _load("ask_resume")

# FAKE-OF: stage-flow test data (catalog ids, project/task/run ids, spend
# amounts, timestamps; test-only values).
PROJECT = "proj-k03-stage1"
TASK = "task-k03-stage1"
RUN = "run-k03-stage1"
PLAN = "plan-k03-stage1"
CATALOG_REF = "catalog-frozen-v1"
CATALOG_IDS = ["t-login", "t-offline", "t-perf"]
ASKED_AT = "2026-10-26T00:00:00Z"
MODEL = "meta/muse-spark-1.3-contributor"


def _flow():
    plan = planner.derive_plan(
        catalog_ids=list(CATALOG_IDS),
        project_id=PROJECT,
        run_id=RUN,
        catalog_ref=CATALOG_REF,
        derived_by_model=MODEL,
    )
    ladder.ask_ladder_once(project_id=PROJECT, asked_at=ASKED_AT)
    started = runner.start_stage(project_id=PROJECT, plan_id=plan.plan_id, run_id=RUN)
    permitted = runner.advance_stage(
        run=started, target_state=runner.StageState.PERMISSION
    )
    running = runner.advance_stage(
        run=permitted, target_state=runner.StageState.RUNNING
    )
    return plan, running


def test_stage_flows_plan_permission_running_results():
    plan, running = _flow()
    assert running.state == runner.StageState.RUNNING
    for test_id in CATALOG_IDS:
        recorded = runner.record_result(
            run_id=RUN, test_id=test_id, status="PASS",
            output_ref="out://%s" % test_id, reason=None,
        )
        assert recorded.test_id == test_id
    counters = runner.stage_counters(run_id=RUN)
    assert (counters.active, counters.passed, counters.remaining) == (0, 3, 0)
    finished = runner.finish_stage(run_id=RUN)
    assert finished.state == runner.StageState.RESULTS


def test_unknown_test_id_refused():
    with pytest.raises(Exception) as exc_info:
        planner.derive_plan(
            catalog_ids=["no-such-test"],
            project_id=PROJECT,
            run_id=RUN,
            catalog_ref=CATALOG_REF,
            derived_by_model=MODEL,
        )
    assert exc_info.value.code == "UNKNOWN_TEST_ID"


def test_empty_plan_refused():
    with pytest.raises(Exception) as exc_info:
        planner.derive_plan(
            catalog_ids=[],
            project_id=PROJECT,
            run_id=RUN,
            catalog_ref=CATALOG_REF,
            derived_by_model=MODEL,
        )
    assert exc_info.value.code == "EMPTY_TEST_PLAN"


def test_bad_transition_refused():
    started = runner.start_stage(project_id=PROJECT, plan_id=PLAN, run_id=RUN)
    with pytest.raises(Exception) as exc_info:
        runner.advance_stage(run=started, target_state=runner.StageState.RUNNING)
    assert exc_info.value.code == "STAGE_BAD_TRANSITION"


def test_empty_results_refused():
    runner.start_stage(project_id=PROJECT, plan_id=PLAN, run_id=RUN)
    with pytest.raises(Exception) as exc_info:
        runner.finish_stage(run_id=RUN)
    assert exc_info.value.code == "EMPTY_STAGE_RESULTS"


def test_refix_loop_sends_failures_back():
    _, running = _flow()
    runner.record_result(
        run_id=RUN, test_id="t-perf", status="FAIL",
        output_ref="out://t-perf", reason="over budget",
    )
    refix = runner.request_refix(
        run_id=RUN, failure_ids=["t-perf"], requested_at=ASKED_AT
    )
    assert refix.run_id == RUN
    assert tuple(refix.failure_ids) == ("t-perf",)


def test_refix_without_failures_refused():
    with pytest.raises(Exception) as exc_info:
        runner.request_refix(run_id=RUN, failure_ids=[], requested_at=ASKED_AT)
    assert exc_info.value.code == "NO_FAILURES_FOR_REFIX"


def test_gateway_leg_records_spend_with_exact_model():
    reservation = runner.gateway_spend_leg(
        project_id=PROJECT,
        task_id=TASK,
        run_id=RUN,
        estimated_amount=1.5,
        provider_request_ref="preq-1",
        model=MODEL,
    )
    assert reservation.model == "meta/muse-spark-1.3-contributor"
    assert reservation.estimated_amount == 1.5
    assert reservation.provider_request_ref == "preq-1"


def test_spend_without_reservation_refused():
    settlement = runner.SpendSettlement(
        settlement_id="settle-orphan",
        reservation_id="res-missing",
        provider_usage_evidence_ref=None,
        provider_request_ref="preq-orphan",
        dedupe_key="dedupe-orphan",
        actual_amount=0.5,
        status="PENDING",
    )
    with pytest.raises(Exception) as exc_info:
        runner.settle_spend_leg(settlement=settlement)
    assert exc_info.value.code == "SPEND_WITHOUT_RESERVATION"


def test_cap_ask_unresolved_blocks_settle():
    reservation = runner.gateway_spend_leg(
        project_id=PROJECT,
        task_id=TASK,
        run_id=RUN,
        estimated_amount=999.0,
        provider_request_ref="preq-cap",
        model=MODEL,
    )
    settlement = runner.SpendSettlement(
        settlement_id="settle-cap",
        reservation_id=reservation.reservation_id,
        provider_usage_evidence_ref="usage-cap",
        provider_request_ref="preq-cap",
        dedupe_key="dedupe-cap",
        actual_amount=999.0,
        status="PENDING",
    )
    with pytest.raises(Exception) as exc_info:
        runner.settle_spend_leg(settlement=settlement)
    assert exc_info.value.code == "CAP_ASK_UNRESOLVED"


def test_soft_cap_warns():
    with pytest.raises(Exception) as exc_info:
        runner.gateway_spend_leg(
            project_id=PROJECT,
            task_id=TASK,
            run_id=RUN,
            estimated_amount=50.0,
            provider_request_ref="preq-soft",
            model=MODEL,
        )
    assert exc_info.value.code == "BUDGET_SOFT_WARN"


def test_hard_cap_blocks():
    with pytest.raises(Exception) as exc_info:
        runner.gateway_spend_leg(
            project_id=PROJECT,
            task_id=TASK,
            run_id=RUN,
            estimated_amount=5000.0,
            provider_request_ref="preq-hard",
            model=MODEL,
        )
    assert exc_info.value.code == "BUDGET_HARD_BLOCKED"


def test_duplicate_settlement_refused():
    reservation = runner.gateway_spend_leg(
        project_id=PROJECT,
        task_id=TASK,
        run_id=RUN,
        estimated_amount=1.0,
        provider_request_ref="preq-dupe",
        model=MODEL,
    )
    settlement = runner.SpendSettlement(
        settlement_id="settle-dupe",
        reservation_id=reservation.reservation_id,
        provider_usage_evidence_ref="usage-dupe",
        provider_request_ref="preq-dupe",
        dedupe_key="dedupe-dupe",
        actual_amount=1.0,
        status="PENDING",
    )
    runner.settle_spend_leg(settlement=settlement)
    with pytest.raises(Exception) as exc_info:
        runner.settle_spend_leg(settlement=settlement)
    assert exc_info.value.code == "DUPLICATE_SETTLEMENT_REFUSED"


def test_resume_click_resumes_parked_run():
    parked = ask.park_run(
        run_id=RUN,
        project_id=PROJECT,
        parked_at_state="PERMISSION",
        reason="waiting on permission ASK",
    )
    assert parked.run_id == RUN
    outcome = ask.resume_run(run_id=RUN, decision=ask.AskDecision.ALLOW_ONCE)
    assert outcome.resumed is True
    assert outcome.decision == ask.AskDecision.ALLOW_ONCE
    assert outcome.resume_target_state == "PERMISSION"
    assert ask.typed_input_allowed(run_id=RUN) is True


def test_resume_without_park_refused():
    with pytest.raises(Exception) as exc_info:
        ask.resume_run(run_id="run-never-parked", decision=ask.AskDecision.DENY)
    assert exc_info.value.code == "RESUME_WITHOUT_PARK"


def test_resume_unknown_decision_refused():
    ask.park_run(
        run_id=RUN,
        project_id=PROJECT,
        parked_at_state="PERMISSION",
        reason="waiting on permission ASK",
    )
    with pytest.raises(Exception) as exc_info:
        ask.resume_run(run_id=RUN, decision="maybe")
    assert exc_info.value.code == "RESUME_UNKNOWN_DECISION"


def test_every_route_reaches_entry_point():
    modules = {"agent_si.test_runners.%s" % name: _load(name) for name in (
        "test_planner", "permission_ladder", "stage_runner", "ask_resume",
    )}
    # FAKE-OF: per-route probe payloads (test-only values).
    probes = {
        "POST /api/v1/teststage/plans": (
            {"catalog_ids": list(CATALOG_IDS), "project_id": PROJECT,
             "run_id": RUN, "catalog_ref": CATALOG_REF,
             "derived_by_model": MODEL}, "plan_id"),
        "POST /api/v1/teststage/permissions/ask": (
            {"project_id": PROJECT, "asked_at": ASKED_AT}, "project_id"),
        "POST /api/v1/teststage/runs/start": (
            {"project_id": PROJECT, "plan_id": PLAN, "run_id": RUN}, "state"),
        "POST /api/v1/teststage/runs/advance": None,
        "POST /api/v1/teststage/runs/results": (
            {"run_id": RUN, "test_id": "t-login", "status": "PASS",
             "output_ref": "out://t-login", "reason": None}, "status"),
        "GET /api/v1/teststage/runs/counters": (
            {"run_id": RUN}, "remaining"),
        "POST /api/v1/teststage/runs/finish": (
            {"run_id": RUN}, "state"),
        "POST /api/v1/teststage/runs/refix": (
            {"run_id": RUN, "failure_ids": ["t-perf"],
             "requested_at": ASKED_AT}, "failure_ids"),
        "POST /api/v1/teststage/runs/spend-leg": (
            {"project_id": PROJECT, "task_id": TASK, "run_id": RUN,
             "estimated_amount": 1.5, "provider_request_ref": "preq-1",
             "model": MODEL}, "reservation_id"),
        "POST /api/v1/teststage/runs/spend-settle": None,
        "POST /api/v1/teststage/ask/resume": (
            {"run_id": RUN,
             "decision": modules["agent_si.test_runners.ask_resume"].AskDecision.ALLOW_ONCE},
            "resumed"),
    }
    assert tuple(method + " " + path for method, path in runner.STAGE_ROUTES) == tuple(
        runner.REALIZATION_MAP.keys()
    )
    for route, probe in probes.items():
        dotted = runner.REALIZATION_MAP[route]
        owner, symbol = dotted.rsplit(".", 1)
        target = getattr(modules[owner], symbol)
        assert callable(target), route
        if probe is None:
            continue
        kwargs, field = probe
        record = target(**kwargs)
        assert getattr(record, field) is not None, route
