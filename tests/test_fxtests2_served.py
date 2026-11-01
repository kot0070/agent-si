"""FXTESTS2 served proof: catalog CODE tests run real commands in a real product run.

testids fxtests2-*; drives the real seam app (create_app) plus the real
lane entries. RED on the hollow tree: the manager hook reaches run-end
with no data root, no gateway and no per-project command, so every CODE
test answers BLOCKED and hook errors vanish; GREEN after: a python
project runs python -m pytest on its suite, a node project with a test
script runs npm test, a matching single file runs as the folder check,
and nothing to run yields BLOCKED with a reason naming the gap; the hook
passes data root plus gateway; a hook failure is recorded on the run and
visible in the stage result while the run still finishes. The fake
provider lives only at the provider network boundary
(MockProviderAdapter injection, the documented test seam); fixtures live
in this file only.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend.app import create_app  # noqa: E402

TEST_TOKEN = "fxtests2-served-token"

PYTHON_PASS_FILE = "test_ok.py"
PYTHON_FAIL_FILE = "test_bad.py"


@pytest.fixture
def store(tmp_path):
    root = tmp_path / "store"
    root.mkdir()
    return root


@pytest.fixture
def client(store):
    from fastapi.testclient import TestClient

    settings = {"ui_session_token": TEST_TOKEN, "store_dir": str(store)}
    app = create_app(dict(settings))
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def clean_globals():
    """Snapshot-restore every global the proofs touch."""
    from agent_si.test_runners import code_executor as _executor
    from agent_si.test_runners import runner_contract as _contract
    from agent_si.qa_catalog import qa_catalog as _catalog
    from agent_si.test_runners import stage_runner as _stage
    from agent_si.test_runners import test_planner as _planner
    from agent_si.runtime import manager as _manager

    saved_approved = dict(_contract._APPROVED_RUNNERS)
    saved_overrides = dict(_catalog._LOCAL_TESTS_OVERRIDES)
    saved_rows = dict(_catalog._RUN_ROWS)
    saved_runs = dict(_stage._RUNS)
    saved_results = {key: list(val) for key, val in _stage._RESULTS.items()}
    saved_assurance = dict(_stage._ASSURANCE_STATUS)
    saved_latest_run = dict(getattr(_stage, "_LATEST_RUN", {}))
    saved_latest_plan = dict(getattr(_planner, "_LATEST_PLAN", {}))
    saved_bound = _manager.bound_provider_adapter()
    saved_root = _executor.executor_data_root()
    saved_timeouts = dict(getattr(_executor, "_TEST_TIMEOUTS", {}))
    try:
        from agent_si.test_runners import run_end as _run_end

        saved_run_end = dict(_run_end._RUN_END_RECORDS)
        have_run_end = True
    except ImportError:
        saved_run_end = {}
        have_run_end = False
    yield
    _contract._APPROVED_RUNNERS.clear()
    _contract._APPROVED_RUNNERS.update(saved_approved)
    _catalog._LOCAL_TESTS_OVERRIDES.clear()
    _catalog._LOCAL_TESTS_OVERRIDES.update(saved_overrides)
    _catalog._RUN_ROWS.clear()
    _catalog._RUN_ROWS.update(saved_rows)
    _stage._RUNS.clear()
    _stage._RUNS.update(saved_runs)
    _stage._RESULTS.clear()
    _stage._RESULTS.update(saved_results)
    _stage._ASSURANCE_STATUS.clear()
    _stage._ASSURANCE_STATUS.update(saved_assurance)
    if hasattr(_stage, "_LATEST_RUN"):
        _stage._LATEST_RUN.clear()
        _stage._LATEST_RUN.update(saved_latest_run)
    if hasattr(_planner, "_LATEST_PLAN"):
        _planner._LATEST_PLAN.clear()
        _planner._LATEST_PLAN.update(saved_latest_plan)
    if have_run_end:
        from agent_si.test_runners import run_end as _run_end

        _run_end._RUN_END_RECORDS.clear()
        _run_end._RUN_END_RECORDS.update(saved_run_end)
    _manager.bind_provider_adapter(saved_bound)
    _executor.bind_data_root(saved_root)
    if hasattr(_executor, "_TEST_TIMEOUTS"):
        _executor._TEST_TIMEOUTS.clear()
        _executor._TEST_TIMEOUTS.update(saved_timeouts)


def _project_dir(store, project_id):
    path = os.path.join(str(store), "projects", project_id)
    os.makedirs(path, exist_ok=True)
    return path


def _write_script(path, body):
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(body)
    return path


def _seed_python_project(store, project_id, failing=True):
    project_dir = _project_dir(store, project_id)
    _write_script(
        os.path.join(project_dir, PYTHON_PASS_FILE),
        "def test_ok():\n"
        "    print('fxtests2-pytest-pass-marker')\n"
        "    assert True\n",
    )
    if failing:
        _write_script(
            os.path.join(project_dir, PYTHON_FAIL_FILE),
            "def test_bad():\n"
            "    print('fxtests2-real-failure-marker')\n"
            "    assert False, 'fxtests2-boom'\n",
        )
    return project_dir


def _seed_node_project(store, project_id, with_test_script=True):
    project_dir = _project_dir(store, project_id)
    scripts = {"test": "node check.js"} if with_test_script else {}
    _write_script(
        os.path.join(project_dir, "package.json"),
        json.dumps({"name": "fxtests2-node", "scripts": scripts}),
    )
    _write_script(
        os.path.join(project_dir, "check.js"),
        "console.log('fxtests2-node-marker');\n"
        "process.exit(0);\n",
    )
    return project_dir


def _configure_budget(project_id, task_max_steps=2):
    from agent_si.backend.orchestration.steplimits import (
        apply_steplimit_config_change,
    )

    outcome = apply_steplimit_config_change({
        "project_id": project_id,
        "task_max_steps": task_max_steps,
        "chat_max_steps": task_max_steps,
        "authority": "M-MANAGER-CONT",
        "reason": "FXTESTS2 run-end hook proof",
    })
    assert outcome.applied, outcome.reason


def _mock_adapter(canned):
    from agent_si.providers.adapters.base import (
        AdapterConfig,
        make_secret_ref,
    )
    from agent_si.providers.adapters.mock_provider import (
        MockProviderAdapter,
    )

    config = AdapterConfig(
        provider_id="mock",
        instance_id="fxtests2",
        model="mock-canned",
        secret_ref=make_secret_ref(
            secret_id="mock-secret", provider_id="mock"),
    )
    return MockProviderAdapter(config, transport=None, canned=canned)


def _run_product(project_id, task_id, message, adapter, **kwargs):
    from agent_si.runtime.manager import run_task_streamed

    _configure_budget(project_id)
    events = list(run_task_streamed(
        None,
        agent_task=None,
        graph=None,
        provider_adapter=adapter,
        project_id=project_id,
        task_id=task_id,
        message=message,
        **kwargs,
    ))
    assert events, "a streamed run always ends with a terminal event"
    return events


def _output_path_for(store, evidence_ref):
    assert evidence_ref.startswith("evidence://"), evidence_ref
    rest = evidence_ref[len("evidence://"):]
    project_id, _, rel = rest.partition("/")
    full = os.path.realpath(os.path.join(str(store), "projects",
                                         project_id, rel))
    return full


def _read_output(store, evidence_ref):
    full = _output_path_for(store, evidence_ref)
    assert os.path.isfile(full), evidence_ref
    with open(full, encoding="utf-8", errors="replace") as handle:
        return handle.read()


# -- F5 resolver: real per-project commands, never shell strings ---------


def test_resolver_maps_python_node_file_and_empty(store, clean_globals):
    """F5: python -> pytest, node -> npm test, file -> direct, else BLOCKED."""
    from agent_si.test_runners import code_executor as _executor

    python_dir = _seed_python_project(store, "fxtests2-resolve-py")
    argv, reason = _executor.resolve_code_command(
        project_dir=python_dir, test_id="t-boot")
    assert reason is None, reason
    assert isinstance(argv, list), argv
    assert argv[:3] == [sys.executable, "-m", "pytest"], argv
    assert all(isinstance(item, str) for item in argv), argv

    node_dir = _seed_node_project(store, "fxtests2-resolve-node")
    argv, reason = _executor.resolve_code_command(
        project_dir=node_dir, test_id="t-boot")
    assert reason is None, reason
    assert isinstance(argv, list) and len(argv) == 2, argv
    assert argv[1] == "test", argv
    assert argv[0].lower().endswith(("npm", "npm.cmd", "npm.exe")), argv

    bare_dir = _project_dir(store, "fxtests2-resolve-file")
    _write_script(
        os.path.join(bare_dir, "t-boot.py"),
        "print('fxtests2-folder-check-ok')\n",
    )
    argv, reason = _executor.resolve_code_command(
        project_dir=bare_dir, test_id="t-boot")
    assert reason is None, reason
    assert argv == [sys.executable,
                    os.path.join(bare_dir, "t-boot.py")], argv

    empty_dir = _project_dir(store, "fxtests2-resolve-empty")
    argv, reason = _executor.resolve_code_command(
        project_dir=empty_dir, test_id="t-boot")
    assert argv is None, argv
    assert reason, "nothing to run needs a reason naming the gap"
    lowered = reason.lower()
    assert "pytest" in lowered and "npm" in lowered, reason


def test_resolver_never_returns_shell_strings(store, clean_globals):
    """F5: every resolved command is an argv list; strings are refused."""
    from agent_si.test_runners import code_executor as _executor

    with pytest.raises(_executor.ExecutorError):
        _executor._check_argv("python -m pytest")
    python_dir = _seed_python_project(store, "fxtests2-resolve-shell")
    argv, _ = _executor.resolve_code_command(
        project_dir=python_dir, test_id="t-login")
    assert isinstance(argv, list), argv
    assert not any(isinstance(item, str) and (" " in item and
                   item.endswith(".py")) for item in argv), argv


def test_node_project_runs_npm_test_served(
        client, store, clean_globals):
    """F5: node project with a test script runs npm test for real."""
    from agent_si.qa_catalog import qa_catalog as _catalog

    project_id = "fxtests2-node-served"
    _seed_node_project(store, project_id)
    report = _catalog.run_suite(
        "catalog-frozen-v1",
        data_root=str(store),
        project_id=project_id,
        timeout_s=60,
    )
    assert report["ok"] is True, report
    assert report["ran"] == 4, report
    by_id = {row["test_id"]: row for row in report["results"]}
    for test_id in ("t-boot", "t-login", "t-offline", "t-perf"):
        row = by_id[test_id]
        assert row["kind"] == "CODE", row
        assert row["status"] == "PASS", row
        text = _read_output(store, row["evidence_ref"])
        assert "fxtests2-node-marker" in text, text


def test_node_project_without_test_script_blocked(
        store, clean_globals):
    """F5: package.json without a test script -> BLOCKED naming the gap."""
    from agent_si.test_runners import code_executor as _executor

    project_id = "fxtests2-node-noscript"
    project_dir = _seed_node_project(store, project_id,
                                     with_test_script=False)
    outcome = _executor.execute_catalog_test(
        test_id="t-boot",
        kind="CODE",
        intent="application boots to a ready state",
        project_id=project_id,
        data_root=str(store),
        argv=None,
        project_dir=project_dir,
        timeout_s=60.0,
    )
    assert outcome["status"] == "BLOCKED", outcome
    assert "test script" in (outcome["reason"] or "").lower(), outcome


def test_empty_folder_blocked_names_gap(store, clean_globals):
    """F5: a folder with nothing to run gives BLOCKED with a reason."""
    from agent_si.test_runners import run_end as _run_end

    project_id = "fxtests2-empty"
    _project_dir(store, project_id)
    record = _run_end.run_local_tests_at_run_end(
        project_id=project_id,
        run_id="run-fxtests2-empty",
        data_root=str(store),
        timeout_s=30,
    )
    assert record["skipped"] is False, record
    by_id = {row["test_id"]: row for row in record["results"]}
    for test_id in ("t-boot", "t-login", "t-offline", "t-perf"):
        assert by_id[test_id]["status"] == "BLOCKED", by_id
        reason = (by_id[test_id]["reason"] or "").lower()
        assert "pytest" in reason and "npm" in reason, by_id


# -- F4 timeout: per-test timeout from settings, default kept -------------


def test_per_test_timeout_from_settings_default_kept(store, clean_globals):
    """F4: a per-test timeout narrows one test; the default still holds."""
    from agent_si.test_runners import code_executor as _executor

    project_id = "fxtests2-timeout"
    project_dir = _project_dir(store, project_id)
    _write_script(
        os.path.join(project_dir, "test_slow.py"),
        "import time\n"
        "def test_slow():\n"
        "    time.sleep(4)\n",
    )
    _write_script(
        os.path.join(project_dir, "test_ok.py"),
        "def test_ok():\n"
        "    assert True\n",
    )
    assert _executor.test_timeout_for(
        "t-boot", 60.0) == _executor.EXECUTOR_DEFAULT_TIMEOUT_S
    _executor.set_test_timeout("t-boot", 1.0)
    assert _executor.test_timeout_for("t-boot", 60.0) == 1.0
    assert _executor.test_timeout_for(
        "t-login", 60.0) == _executor.EXECUTOR_DEFAULT_TIMEOUT_S
    boot = _executor.execute_catalog_test(
        test_id="t-boot",
        kind="CODE",
        intent="application boots to a ready state",
        project_id=project_id,
        data_root=str(store),
        argv=None,
        project_dir=project_dir,
        timeout_s=60.0,
    )
    assert boot["status"] == "FAIL", boot
    assert "timed out" in (boot["reason"] or "").lower(), boot
    login = _executor.execute_catalog_test(
        test_id="t-login",
        kind="CODE",
        intent="login signs in with valid credentials",
        project_id=project_id,
        data_root=str(store),
        argv=None,
        project_dir=project_dir,
        timeout_s=60.0,
    )
    assert login["status"] == "PASS", login


# -- F1/F2 product run: real suite rows, gateway spy, hook wiring --------


def _code_rows_from_view(client, project_id):
    latest_run = client.get(
        "/api/v1/teststage/runs/latest", params={"project_id": project_id})
    assert latest_run.status_code == 200, latest_run.text
    stage_run_id = latest_run.json()["run_id"]
    latest_plan = client.get(
        "/api/v1/teststage/plans/latest", params={"project_id": project_id})
    assert latest_plan.status_code == 200, latest_plan.text
    plan_id = latest_plan.json()["plan_id"]
    view = client.get(
        "/api/v1/teststage/tests-view",
        params={"plan_id": plan_id, "run_id": stage_run_id})
    assert view.status_code == 200, view.text
    return view.json(), plan_id, stage_run_id


def test_python_suite_fail_then_pass_in_product_run(
        client, store, clean_globals):
    """F1/F2: a real product run writes rows where the suite really ran."""
    project_id = "fxtests2-product"
    _seed_python_project(store, project_id, failing=True)
    adapter = _mock_adapter(("fxtests2-judge-says-yes",))

    events = _run_product(
        project_id, "task-fxtests2-fail",
        "serve one canned turn", adapter)
    assert events[-1].event == "done", events[-1]
    run_id = events[-1].data.get("run_id")
    assert run_id, events[-1].data

    body, _plan_id, _stage_id = _code_rows_from_view(client, project_id)
    assert len(body["rows"]) == 6, body
    by_id = {row["test_id"]: row for row in body["rows"]}
    for test_id in ("t-boot", "t-login", "t-offline", "t-perf"):
        assert by_id[test_id]["status"] == "FAIL", by_id
        assert by_id[test_id]["output_ref"], by_id
        text = _read_output(store, by_id[test_id]["output_ref"])
        assert "fxtests2-real-failure-marker" in text, text
        assert "returncode: 1" in text, text
    assert by_id["t-chat"]["status"] == "PASS", by_id
    assert by_id["t-export"]["status"] == "BLOCKED", by_id
    assert adapter.turns_served == 2, "chat turn plus the hook AI test"

    os.unlink(os.path.join(
        str(store), "projects", project_id, PYTHON_FAIL_FILE))
    events = _run_product(
        project_id, "task-fxtests2-pass",
        "serve one canned turn", adapter)
    assert events[-1].event == "done", events[-1]
    body, _, _ = _code_rows_from_view(client, project_id)
    by_id = {row["test_id"]: row for row in body["rows"]}
    for test_id in ("t-boot", "t-login", "t-offline", "t-perf"):
        assert by_id[test_id]["status"] == "PASS", by_id
        text = _read_output(store, by_id[test_id]["output_ref"])
        assert "passed" in text, text


def test_ai_reaches_gateway_spy_with_cost_recorded(
        client, store, clean_globals):
    """F1/F2: one AI test reaches the gateway spy; cost is recorded."""
    from agent_si.telemetry import run_store as _telemetry

    project_id = "fxtests2-ai-spy"
    _seed_python_project(store, project_id, failing=False)
    adapter = _mock_adapter(("fxtests2-judge-says-yes",))
    before = adapter.turns_served
    events = _run_product(
        project_id, "task-fxtests2-ai", "serve one canned turn", adapter)
    assert events[-1].event == "done", events[-1]
    assert adapter.turns_served == before + 2, (
        "one chat turn plus one hook AI judgement")
    stored = _telemetry.load_store(str(store))
    hook_events = [
        row for row in stored.get("telemetry_events", [])
        if isinstance(row, dict)
        and row.get("event_type") == "PROVIDER_USAGE_REPORTED"
        and row.get("task_id") == "local-tests"
        and row.get("project_id") == project_id
    ]
    assert hook_events, "the hook AI call records provider usage"
    body, _, _ = _code_rows_from_view(client, project_id)
    by_id = {row["test_id"]: row for row in body["rows"]}
    assert by_id["t-chat"]["status"] == "PASS", by_id
    text = _read_output(store, by_id["t-chat"]["output_ref"])
    assert "fxtests2-judge-says-yes" in text, text


def test_run_suite_rows_carry_f1_fields(store, clean_globals):
    """F1: rows carry kind, status, output ref, reason text, duration."""
    from agent_si.qa_catalog import qa_catalog as _catalog

    project_id = "fxtests2-rows"
    _seed_python_project(store, project_id, failing=True)
    report = _catalog.run_suite(
        "catalog-frozen-v1",
        data_root=str(store),
        project_id=project_id,
        timeout_s=30,
    )
    assert report["ok"] is True, report
    assert report["ran"] == 4, report
    by_id = {row["test_id"]: row for row in report["results"]}
    assert set(by_id) == {"t-boot", "t-chat", "t-export", "t-login",
                          "t-offline", "t-perf"}, report
    for test_id in ("t-boot", "t-login", "t-offline", "t-perf"):
        row = by_id[test_id]
        assert row["kind"] == "CODE", row
        assert row["status"] == "FAIL", row
        assert row["evidence_ref"].startswith("evidence://"), row
        assert row["reason"], row
        assert row["duration_s"] >= 0, row
        text = _read_output(store, row["evidence_ref"])
        assert "fxtests2-real-failure-marker" in text, text


# -- F3 hook failure: recorded on the run, run still finishes ------------


def test_hook_failure_recorded_and_run_finishes(
        client, store, clean_globals, monkeypatch):
    """F3: a forced hook raise writes error on the run; run finishes."""
    from agent_si.test_runners import run_end as _run_end

    project_id = "fxtests2-hook-boom"
    _seed_python_project(store, project_id, failing=False)

    def _boom(**kwargs):
        raise RuntimeError("fxtests2-forced-hook-boom")

    monkeypatch.setattr(
        _run_end, "run_local_tests_at_run_end", _boom)
    adapter = _mock_adapter(("fxtests2 hook boom reply",))
    events = _run_product(
        project_id, "task-fxtests2-boom", "serve one canned turn", adapter)
    assert events[-1].event == "done", events[-1]
    run_id = events[-1].data.get("run_id")
    record = _run_end.last_run_end(run_id)
    assert record is not None, "hook failure is recorded, never dropped"
    assert "fxtests2-forced-hook-boom" in (
        record.get("hook_error") or ""), record


def test_hook_stage_failure_visible_in_stage_result(
        client, store, clean_globals, monkeypatch):
    """F3: a mid-hook failure shows in the stage result, run finishes."""
    from agent_si.test_runners import run_end as _run_end
    from agent_si.test_runners import stage_runner as _stage

    project_id = "fxtests2-hook-stage"
    _seed_python_project(store, project_id, failing=False)
    real_finish = _stage.finish_stage

    def _fail_finish(run_id, *args, **kwargs):
        real_finish(run_id, *args, **kwargs)
        raise RuntimeError("fxtests2-stage-finish-boom")

    monkeypatch.setattr(_stage, "finish_stage", _fail_finish)
    adapter = _mock_adapter(("fxtests2 stage boom reply",))
    events = _run_product(
        project_id, "task-fxtests2-stage-boom",
        "serve one canned turn", adapter)
    assert events[-1].event == "done", events[-1]
    run_id = events[-1].data.get("run_id")
    record = _run_end.last_run_end(run_id)
    assert record is not None, record
    assert "fxtests2-stage-finish-boom" in (
        record.get("hook_error") or ""), record
    stage_id = record.get("stage_run_id")
    assert stage_id, record
    rows = _stage._RESULTS.get(stage_id, [])
    hook_rows = [row for row in rows
                 if row.test_id == "local-tests-hook"]
    assert hook_rows, "the failure is visible in the stage result"
    assert hook_rows[0].status == "BLOCKED", hook_rows[0]
    assert "fxtests2-stage-finish-boom" in (
        hook_rows[0].reason or ""), hook_rows[0]
