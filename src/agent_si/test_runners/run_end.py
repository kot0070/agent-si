"""K03 FXTESTS1: product run-end hook for the local-tests switch.

When a product run ends, the local-tests switch decides: switch on runs
a single test stage (plan -> permission -> running -> results -> counters
through the existing stage_runner entries, failures back through the
existing refix path); switch off records a skip. Per-test outcomes are
honest: CODE tests execute only with a staged project folder, AI tests
judge only with an explicit gateway (the hook never re-invokes the bound
product provider behind the run), HUMAN tests need an operator sign-off.
Unavailable context yields BLOCKED plus a reason, never PASS. A hook
failure is recorded on the run (plus a hook row when a stage was
started), never dropped; the run still finishes.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from typing import Any, Dict, List, Mapping, Optional, Sequence

#: Exact shipped-preset model id (never retyped, never a second id).
MODEL_ID = "meta/muse-spark-1.3-contributor"

#: Run-end records by product run id; each names the stage run or a skip.
_RUN_END_RECORDS: Dict[str, Dict[str, Any]] = {}


def _utcnow() -> str:
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


def last_run_end(run_id: str) -> Optional[Dict[str, Any]]:
    """Return the recorded run-end outcome for one product run, if any."""
    stored = _RUN_END_RECORDS.get(run_id)
    if stored is None:
        return None
    return dict(stored)


def _stage_run_id(run_id: str) -> str:
    """Stage run id derived from one product run id."""
    safe = "".join(
        ch if (ch.isalnum() or ch in ("-", "_")) else "-"
        for ch in str(run_id)
    ).strip("-") or "run"
    return "localtests-%s" % safe


def _hook_data_root(explicit: Optional[str]) -> Optional[str]:
    """Data root for the hook: explicit first, then the executor bind
    the app set at startup, then the telemetry bind from the same app."""
    if explicit:
        return explicit
    try:
        from agent_si.test_runners import code_executor as _executor

        bound = _executor.executor_data_root()
    except Exception:
        bound = None
    if bound:
        return bound
    try:
        from agent_si.telemetry import run_store as _store

        return _store.bound_store_dir()
    except Exception:
        return None


def record_hook_error(
    run_id: str,
    project_id: str,
    task_id: str,
    error: Exception,
) -> Dict[str, Any]:
    """Record a hook failure on the product run; never raises, never drops."""
    try:
        text = "%s: %s" % (type(error).__name__, error)
    except Exception:
        text = "hook failed"
    record: Dict[str, Any] = {
        "run_id": str(run_id),
        "project_id": str(project_id or ""),
        "task_id": str(task_id or ""),
        "skipped": False,
        "hook_error": text,
        "reason": None,
        "stage_run_id": None,
        "plan_id": None,
        "state": None,
        "counters": None,
        "results": [],
        "refix": None,
    }
    with contextlib.suppress(Exception):
        _RUN_END_RECORDS[str(run_id)] = dict(record)
    return record


def _record_hook_failure(
    *,
    run_id: str,
    project_id: str,
    task_id: str,
    stage_id: Optional[str],
    plan_id: Optional[str],
    error: Exception,
) -> Dict[str, Any]:
    """Fold a mid-hook failure into the run record plus the stage result.

    The error text lands on the run record and, when a stage run was
    already started, as a BLOCKED hook row in that stage result so the
    Tests view shows it. The run still finishes: this returns a record
    and never raises.
    """
    from agent_si.qa_catalog import qa_catalog as _catalog
    from agent_si.test_runners import stage_runner as _stage

    try:
        text = "%s: %s" % (type(error).__name__, error)
    except Exception:
        text = "hook failed"
    results: List[Dict[str, Any]] = []
    counters: Optional[Dict[str, int]] = None
    try:
        if stage_id and stage_id in _stage._RUNS:
            _stage.record_result(
                stage_id, "local-tests-hook", "BLOCKED", None,
                "hook failed: %s" % text,
            )
            with contextlib.suppress(Exception):
                _catalog.record_status_row(
                    plan_id or "", stage_id,
                    "local-tests-hook", "BLOCKED", None,
                )
            try:
                rows = _stage._RESULTS.get(stage_id, [])
                results = [
                    {
                        "test_id": row.test_id,
                        "status": row.status,
                        "reason": row.reason,
                    }
                    for row in rows
                ]
                counts = _stage.stage_counters(stage_id)
                counters = {
                    "active": counts.active,
                    "passed": counts.passed,
                    "remaining": counts.remaining,
                }
            except Exception:  # keep the recorded rows without counters
                counters = None
    except Exception:
        pass
    record: Dict[str, Any] = {
        "run_id": str(run_id),
        "project_id": str(project_id or ""),
        "task_id": str(task_id or ""),
        "skipped": False,
        "hook_error": text,
        "reason": None,
        "stage_run_id": stage_id,
        "plan_id": plan_id,
        "state": None,
        "counters": counters,
        "results": results,
        "refix": None,
    }
    with contextlib.suppress(Exception):
        _RUN_END_RECORDS[str(run_id)] = dict(record)
    return record


def run_local_tests_at_run_end(
    *,
    project_id: str,
    run_id: str,
    task_id: str = "",
    data_root: Optional[str] = None,
    gateway: Any = None,
    answers: Optional[Mapping[str, str]] = None,
    argv_map: Optional[Mapping[str, Sequence[str]]] = None,
    timeout_s: float = 60.0,
) -> Dict[str, Any]:
    """Drive the local-tests stage for one finished product run.

    Switch on: derive a plan from the frozen catalog, run one stage
    (plan -> permission -> running -> results), record per-test statuses
    plus Tests-view rows, send failures through request_refix, close and
    count. Switch off: record a skip. A hook failure is recorded on the
    run (plus a hook row when a stage was started), never dropped; the
    run still finishes. Returns the recorded outcome dict.
    """
    from agent_si.qa_catalog import qa_catalog as _catalog
    from agent_si.test_runners import code_executor as _executor
    from agent_si.test_runners import stage_runner as _stage
    from agent_si.test_runners import test_planner as _planner

    pid = str(project_id or "")
    if not _catalog.local_tests_enabled(pid):
        record: Dict[str, Any] = {
            "run_id": str(run_id),
            "project_id": pid,
            "task_id": str(task_id or ""),
            "skipped": True,
            "hook_error": None,
            "reason": "local tests are switched off for project %r" % pid,
            "stage_run_id": None,
            "plan_id": None,
            "state": None,
            "counters": None,
            "results": [],
            "refix": None,
        }
        _RUN_END_RECORDS[str(run_id)] = dict(record)
        return record
    root = _hook_data_root(data_root)
    stage_id = _stage_run_id(run_id)
    plan_id: Optional[str] = None
    try:
        catalog = _catalog.get_catalog("catalog-frozen-v1")
        test_ids = [test.test_id for test in catalog.tests]
        kinds = {test.test_id: test.kind for test in catalog.tests}
        intents = {test.test_id: test.intent for test in catalog.tests}
        plan = _planner.derive_plan(
            list(test_ids), pid, stage_id, "catalog-frozen-v1", MODEL_ID)
        plan_id = plan.plan_id
        run = _stage.start_stage(pid, plan.plan_id, stage_id)
        run = _stage.advance_stage(run, _stage.StageState.PERMISSION)
        run = _stage.advance_stage(run, _stage.StageState.RUNNING)
        failures: List[str] = []
        results: List[Dict[str, Any]] = []
        for test_id in plan.test_ids:
            argv = None
            if argv_map is not None:
                raw = argv_map.get(test_id)
                argv = list(raw) if raw is not None else None
            sign_off = None
            if answers is not None:
                sign_off = answers.get(test_id)
            outcome = _executor.execute_catalog_test(
                test_id=test_id,
                kind=kinds.get(test_id, "CODE"),
                intent=intents.get(test_id, test_id),
                project_id=pid,
                data_root=root,
                argv=argv,
                project_dir=None,
                gateway=gateway,
                answer=sign_off,
                assertion_ref=None,
                timeout_s=_executor.test_timeout_for(
                    test_id, timeout_s if timeout_s else 60.0),
                # Hook AI judgement uses the run gateway (pinned
                # turns_served==2) but never bills the user project:
                # one turn keeps one charge and one usage row.
                record_cost=False,
            )
            _stage.record_result(
                stage_id, test_id, outcome["status"],
                outcome["evidence_ref"], outcome["reason"],
            )
            _catalog.record_status_row(
                plan.plan_id, stage_id, test_id, outcome["status"],
                outcome["evidence_ref"],
            )
            results.append({
                "test_id": test_id,
                "kind": outcome["kind"],
                "status": outcome["status"],
                "evidence_ref": outcome["evidence_ref"],
                "reason": outcome["reason"],
                "duration_s": outcome.get("duration_s", 0.0),
            })
            if outcome["status"] == "FAIL":
                failures.append(test_id)
        refix_record: Optional[Dict[str, Any]] = None
        if failures:
            refix = _stage.request_refix(stage_id, failures, _utcnow())
            refix_record = {
                "run_id": refix.run_id,
                "failure_ids": tuple(refix.failure_ids),
                "requested_at": refix.requested_at,
            }
        finished = _stage.finish_stage(stage_id)
        counters = _stage.stage_counters(stage_id)
        record = {
            "run_id": str(run_id),
            "project_id": pid,
            "task_id": str(task_id or ""),
            "skipped": False,
            "hook_error": None,
            "reason": None,
            "stage_run_id": stage_id,
            "plan_id": plan.plan_id,
            "state": (finished.state.value
                      if hasattr(finished.state, "value")
                      else str(finished.state)),
            "counters": {
                "active": counters.active,
                "passed": counters.passed,
                "remaining": counters.remaining,
            },
            "results": results,
            "refix": refix_record,
        }
        _RUN_END_RECORDS[str(run_id)] = dict(record)
        return record
    except Exception as exc:
        return _record_hook_failure(
            run_id=str(run_id),
            project_id=pid,
            task_id=str(task_id or ""),
            stage_id=stage_id,
            plan_id=plan_id,
            error=exc,
        )


#: Entry points: logical name -> symbol in this module.
ENTRY_POINTS = {
    "run_local_tests_at_run_end": "run_local_tests_at_run_end",
    "last_run_end": "last_run_end",
}
