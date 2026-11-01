"""FXTESTS1 served proof: catalog tests really run, product run reaches them.

testids fxtests1-*; drives the real seam app (create_app) plus the real
lane entries. RED on the hollow tree: run_with_contract answers PASS
without starting a process, run_suite counts without running, and no
run-end hook or result-output route exists. GREEN after: a passing file
-> PASS with an output file holding the real output; a failing file ->
FAIL with the failure text; an unavailable tool/base -> BLOCKED+reason;
run_suite counts real results; a product run with the local-tests switch
on writes stage results+counters, off writes skip; output-route escape
refused; a child-process spy proves a real start per CODE test.
The fake provider lives only at the provider network boundary
(MockProviderAdapter injection, the documented test seam); fixtures live
in this file only.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend.app import create_app  # noqa: E402

TEST_TOKEN = "fxtests1-served-token"


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


@pytest.fixture
def spy_subprocess(monkeypatch):
    """Count real child-process starts while still executing them."""
    calls = []
    real_run = subprocess.run

    def _watch(*args, **kwargs):
        calls.append(args)
        return real_run(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", _watch)
    return calls


def _project_dir(store, project_id):
    path = os.path.join(str(store), "projects", project_id)
    os.makedirs(path, exist_ok=True)
    return path


def _write_script(path, body):
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(body)
    return path


def _profile(project_id, base_id="base-code-fast"):
    return {
        "project_id": project_id,
        "profile_name": "fxtests1",
        "runtime": "local",
        "base_id": base_id,
    }


def _code_run(client, project_dir, project_id, test_id, argv,
              base_id="base-code-fast"):
    return client.post(
        "/api/v1/teststage/runners/run",
        json={
            "profile": _profile(project_id, base_id),
            "test_id": test_id,
            "runner_id": "builtin-fxtests1",
            "argv": argv,
            "project_dir": project_dir,
            "timeout_s": 30,
        },
    )


def _output_path_for(store, evidence_ref):
    assert evidence_ref.startswith("evidence://"), evidence_ref
    rest = evidence_ref[len("evidence://"):]
    project_id, _, rel = rest.partition("/")
    full = os.path.realpath(os.path.join(str(store), "projects",
                                         project_id, rel))
    return full


def _configure_budget(project_id, task_max_steps=2):
    from agent_si.backend.orchestration.steplimits import (
        apply_steplimit_config_change,
    )

    outcome = apply_steplimit_config_change({
        "project_id": project_id,
        "task_max_steps": task_max_steps,
        "chat_max_steps": task_max_steps,
        "authority": "M-MANAGER-CONT",
        "reason": "FXTESTS1 run-end hook proof",
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
        instance_id="fxtests1",
        model="mock-canned",
        secret_ref=make_secret_ref(
            secret_id="mock-secret", provider_id="mock"),
    )
    return MockProviderAdapter(config, transport=None, canned=canned)


# -- F1 executor: passing file -> PASS + real output file --------------------


def test_code_passing_file_passes_with_real_output(
        client, store, clean_globals, spy_subprocess):
    """F1: exit 0 -> PASS and the output file holds the real stdout."""
    project_id = "fxtests1-code-pass"
    project_dir = _project_dir(store, project_id)
    script = _write_script(
        os.path.join(project_dir, "t-boot.py"),
        "print('fxtests1-real-stdout-marker')\n",
    )
    before = len(spy_subprocess)
    resp = _code_run(client, project_dir, project_id, "t-boot",
                     [sys.executable, script])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "PASS", body
    assert len(spy_subprocess) > before, "no child process was started"
    full = _output_path_for(store, body["evidence_ref"])
    assert os.path.isfile(full), body
    with open(full, encoding="utf-8", errors="replace") as handle:
        text = handle.read()
    assert "fxtests1-real-stdout-marker" in text, text
    assert "returncode: 0" in text, text


def test_code_failing_file_fails_with_failure_text(
        client, store, clean_globals, spy_subprocess):
    """F1: nonzero exit -> FAIL and the file holds the real stderr."""
    project_id = "fxtests1-code-fail"
    project_dir = _project_dir(store, project_id)
    script = _write_script(
        os.path.join(project_dir, "t-login.py"),
        "import sys\n"
        "sys.stderr.write('fxtests1-real-failure-marker\\n')\n"
        "sys.exit(3)\n",
    )
    before = len(spy_subprocess)
    resp = _code_run(client, project_dir, project_id, "t-login",
                     [sys.executable, script])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "FAIL", body
    assert len(spy_subprocess) > before, "no child process was started"
    full = _output_path_for(store, body["evidence_ref"])
    assert os.path.isfile(full), body
    with open(full, encoding="utf-8", errors="replace") as handle:
        text = handle.read()
    assert "fxtests1-real-failure-marker" in text, text
    assert "returncode: 3" in text, text


def test_code_shell_string_argv_refused(client, store, clean_globals):
    """F1: argv is a list, never a shell string from user data."""
    project_id = "fxtests1-code-shell"
    project_dir = _project_dir(store, project_id)
    resp = client.post(
        "/api/v1/teststage/runners/run",
        json={
            "profile": _profile(project_id),
            "test_id": "t-boot",
            "runner_id": "builtin-fxtests1",
            "argv": "python t-boot.py",
            "project_dir": project_dir,
        },
    )
    assert resp.status_code == 400, resp.text


def test_code_unknown_base_blocked_with_reason(
        client, store, clean_globals, spy_subprocess):
    """F1: unknown tool/base -> BLOCKED + reason, never PASS."""
    project_id = "fxtests1-code-blocked"
    project_dir = _project_dir(store, project_id)
    before = len(spy_subprocess)
    resp = _code_run(client, project_dir, project_id, "t-boot",
                     [sys.executable, "t-boot.py"],
                     base_id="base-nope-fxtests1")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "BLOCKED", body
    assert body.get("reason"), body
    assert len(spy_subprocess) == before, "blocked runs start no process"


# -- F2 AI/HUMAN kinds --------------------------------------------------------


def test_ai_without_gateway_blocked_with_reason(
        client, store, clean_globals):
    """F2: AI with no bound gateway -> BLOCKED + reason, never PASS."""
    from agent_si.runtime.manager import bound_provider_adapter

    assert bound_provider_adapter() is None
    project_id = "fxtests1-ai-blocked"
    resp = client.post(
        "/api/v1/teststage/runners/run",
        json={
            "profile": _profile(project_id, "base-ai-judge"),
            "test_id": "t-chat",
            "runner_id": "builtin-fxtests1",
            "project_dir": _project_dir(store, project_id),
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "BLOCKED", body
    assert body.get("reason"), body


def test_ai_gateway_judgement_recorded_with_cost(
        client, store, clean_globals):
    """F2: AI via the bound gateway judges the live reply; cost recorded."""
    from agent_si.runtime import manager as _manager

    project_id = "fxtests1-ai-judge"
    project_dir = _project_dir(store, project_id)
    adapter = _mock_adapter(("fxtests1-judge-says-yes",))
    previous = _manager.bind_provider_adapter(adapter)
    try:
        resp = client.post(
            "/api/v1/teststage/runners/run",
            json={
                "profile": _profile(project_id, "base-ai-judge"),
                "test_id": "t-chat",
                "runner_id": "builtin-fxtests1",
                "project_dir": project_dir,
            },
        )
    finally:
        _manager.bind_provider_adapter(previous)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "PASS", body
    full = _output_path_for(store, body["evidence_ref"])
    assert os.path.isfile(full), body
    with open(full, encoding="utf-8", errors="replace") as handle:
        text = handle.read()
    assert "fxtests1-judge-says-yes" in text, text


def test_human_needs_ladder_reason_and_answer(client, store, clean_globals):
    """F2: HUMAN carries reason; no PASS without a real operator answer."""
    from agent_si.test_runners import permission_ladder as _ladder

    project_id = "fxtests1-human"
    project_dir = _project_dir(store, project_id)
    ask = client.post(
        "/api/v1/teststage/permissions/ask",
        json={"project_id": project_id, "asked_at": "2026-11-01T00:00:00Z"},
    )
    assert ask.status_code == 200, ask.text

    def _human(payload):
        return client.post("/api/v1/teststage/runners/run", json=payload)

    base = {
        "profile": _profile(project_id, "base-human-operated"),
        "test_id": "t-export",
        "runner_id": "builtin-fxtests1",
        "project_dir": project_dir,
    }
    # No reason and no answer: refused before any PASS.
    refused = _human(dict(base))
    assert refused.status_code == 400, refused.text
    # Reason but no answer: still no PASS.
    no_answer = _human(dict(base, reason="operator checked the export"))
    assert no_answer.status_code in (200, 400), no_answer.text
    if no_answer.status_code == 200:
        assert no_answer.json()["status"] != "PASS", no_answer.json()
    # Ladder consumed by the direct check above; ask again for the PASS leg.
    _ladder._episode_bus().open_project = None
    _ladder._episode_bus().projects_asked.add(project_id)
    passed = _human(dict(
        base,
        reason="operator checked the export",
        answer="operator sign-off: export matches",
    ))
    assert passed.status_code == 200, passed.text
    body = passed.json()
    assert body["status"] == "PASS", body
    full = _output_path_for(store, body["evidence_ref"])
    assert os.path.isfile(full), body
    with open(full, encoding="utf-8", errors="replace") as handle:
        text = handle.read()
    assert "operator sign-off: export matches" in text, text


def test_human_before_ladder_refused(client, store, clean_globals):
    """F2: HUMAN before the ladder was asked is refused."""
    project_id = "fxtests1-human-noladder"
    resp = client.post(
        "/api/v1/teststage/runners/run",
        json={
            "profile": _profile(project_id, "base-human-operated"),
            "test_id": "t-export",
            "runner_id": "builtin-fxtests1",
            "project_dir": _project_dir(store, project_id),
            "reason": "operator checked",
            "answer": "sign-off",
        },
    )
    assert resp.status_code == 400, resp.text
    assert "HUMAN_BEFORE_LADDER" in resp.text


# -- F3 run_suite counts real results -----------------------------------------


def _seed_suite_project(store, project_id):
    project_dir = _project_dir(store, project_id)
    _write_script(
        os.path.join(project_dir, "t-boot.py"),
        "print('fxtests1-suite-boot-ok')\n",
    )
    _write_script(
        os.path.join(project_dir, "t-login.py"),
        "print('fxtests1-suite-login-ok')\n",
    )
    _write_script(
        os.path.join(project_dir, "t-offline.py"),
        "import sys\nsys.exit(1)\n",
    )
    _write_script(
        os.path.join(project_dir, "t-perf.py"),
        "print('fxtests1-suite-perf-ok')\n",
    )
    return project_dir


def test_run_suite_counts_real_results(store, clean_globals, spy_subprocess):
    """F3: run_suite executes every CODE test; ran counts PASS+FAIL only."""
    from agent_si.qa_catalog import qa_catalog as _catalog

    project_id = "fxtests1-suite"
    _seed_suite_project(store, project_id)
    before = len(spy_subprocess)
    report = _catalog.run_suite(
        "catalog-frozen-v1",
        data_root=str(store),
        project_id=project_id,
        timeout_s=30,
    )
    assert report["ok"] is True, report
    by_id = {row["test_id"]: row for row in report["results"]}
    assert set(by_id) == {"t-boot", "t-chat", "t-export", "t-login",
                          "t-offline", "t-perf"}, report
    assert by_id["t-boot"]["status"] == "PASS", by_id
    assert by_id["t-login"]["status"] == "PASS", by_id
    assert by_id["t-offline"]["status"] == "FAIL", by_id
    assert by_id["t-perf"]["status"] == "PASS", by_id
    # No gateway and no operator session: honest BLOCKEDs with reasons.
    assert by_id["t-chat"]["status"] == "BLOCKED", by_id
    assert by_id["t-chat"]["reason"], by_id
    assert by_id["t-export"]["status"] == "BLOCKED", by_id
    assert by_id["t-export"]["reason"], by_id
    assert report["ran"] == 4, report
    assert len(spy_subprocess) >= before + 4, "one process per CODE test"
    full = _output_path_for(store, by_id["t-boot"]["evidence_ref"])
    assert os.path.isfile(full), by_id
    with open(full, encoding="utf-8", errors="replace") as handle:
        assert "fxtests1-suite-boot-ok" in handle.read()


def test_catalog_run_route_without_context_reports_blocked(client,
                                                           clean_globals):
    """F3: the bare catalog-run route runs nothing but reports honestly."""
    resp = client.post(
        "/api/v1/catalog/run", json={"suite": "catalog-frozen-v1"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True, body
    assert body["ran"] == 0, body
    assert len(body["results"]) == 6, body
    for row in body["results"]:
        assert row["status"] == "BLOCKED", row
        assert row["reason"], row


# -- F5/F7 read routes: latest plan/run, tests-view, confined output ---------


def test_run_end_switch_on_writes_stage_results(
        client, store, clean_globals):
    """F4/F5: product run with the switch on writes stage results+counters."""
    from agent_si.runtime.manager import run_task_streamed

    project_id = "fxtests1-runend-on"
    _configure_budget(project_id)
    adapter = _mock_adapter(("fxtests1 product reply",))
    events = list(run_task_streamed(
        None,
        agent_task=None,
        graph=None,
        provider_adapter=adapter,
        project_id=project_id,
        task_id="task-fxtests1",
        message="serve one canned turn",
    ))
    assert events, "a streamed run always ends with a terminal event"
    assert events[-1].event == "done", events[-1]
    assert adapter.turns_served == 1, "the hook makes no provider call"

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
    body = view.json()
    assert body["active"] == 6, body
    assert body["passed"] == 0, body
    assert body["remaining"] == 6, body
    assert len(body["rows"]) == 6, body
    for row in body["rows"]:
        assert row["status"] == "BLOCKED", row
        assert row["output_ref"], row


def test_run_end_switch_off_records_skip(client, clean_globals):
    """F4: product run with the switch off records a skip, no stage run."""
    from agent_si.qa_catalog import qa_catalog as _catalog
    from agent_si.runtime.manager import run_task_streamed
    from agent_si.test_runners import run_end as _run_end

    project_id = "fxtests1-runend-off"
    _catalog.set_local_tests_enabled(project_id, False, "2026-11-01T00:00Z")
    _configure_budget(project_id)
    adapter = _mock_adapter(("fxtests1 off reply",))
    events = list(run_task_streamed(
        None,
        agent_task=None,
        graph=None,
        provider_adapter=adapter,
        project_id=project_id,
        task_id="task-fxtests1-off",
        message="serve one canned turn",
    ))
    assert events[-1].event == "done", events[-1]
    run_id = events[-1].data.get("run_id")
    assert run_id, events[-1].data
    record = _run_end.last_run_end(run_id)
    assert record is not None, "switch-off must record a skip"
    assert record["skipped"] is True, record
    assert record["stage_run_id"] is None, record
    latest = client.get(
        "/api/v1/teststage/runs/latest", params={"project_id": project_id})
    assert latest.status_code == 404, latest.text


def test_result_output_serves_real_file_and_refuses_escape(
        client, store, clean_globals):
    """F5+F7: output by ref serves the real file; escape is refused."""
    project_id = "fxtests1-output"
    project_dir = _project_dir(store, project_id)
    script = _write_script(
        os.path.join(project_dir, "t-boot.py"),
        "print('fxtests1-output-marker')\n",
    )
    resp = _code_run(client, project_dir, project_id, "t-boot",
                     [sys.executable, script])
    assert resp.status_code == 200, resp.text
    ref = resp.json()["evidence_ref"]
    served = client.get(
        "/api/v1/teststage/result-output", params={"ref": ref})
    assert served.status_code == 200, served.text
    assert "fxtests1-output-marker" in served.json()["output"], served.text
    for evil in (
        "evidence://%s/../../secret" % project_id,
        "evidence:///etc/passwd",
        "evidence://%s/test-output/../../../../x" % project_id,
        "not-a-ref",
    ):
        refused = client.get(
            "/api/v1/teststage/result-output", params={"ref": evil})
        assert refused.status_code in (400, 404), (evil, refused.text)


# -- F6 spec probes -----------------------------------------------------------


def test_probe_unknown_test_id_refused(client, store, clean_globals):
    """F6: an unknown test id is refused, never run."""
    project_id = "fxtests1-probe-unknown"
    resp = client.post(
        "/api/v1/teststage/runners/run",
        json={
            "profile": _profile(project_id),
            "test_id": "t-nope-fxtests1",
            "runner_id": "builtin-fxtests1",
            "project_dir": _project_dir(store, project_id),
        },
    )
    assert resp.status_code == 400, resp.text
    assert "UNKNOWN_TEST_ID" in resp.text
    plan = client.post(
        "/api/v1/teststage/plans",
        json={
            "catalog_ids": ["nope-not-catalog"],
            "project_id": project_id,
            "run_id": "run-fxtests1-probe",
            "catalog_ref": "catalog-frozen-v1",
            "derived_by_model": "meta/muse-spark-1.3-contributor",
        },
    )
    assert plan.status_code == 400, plan.text
    assert "UNKNOWN_TEST_ID" in plan.text


def test_probe_flaky_never_passes_and_status_rules_hold(
        client, clean_globals):
    """F6: FLAKY never validates as PASS; BLOCKED needs a reason."""
    from agent_si.qa_catalog import catalog_validator as _validator

    with pytest.raises(Exception) as exc_info:
        _validator.validate_result("PASS", "FLAKY", "assert-ref", None)
    assert getattr(exc_info.value, "code", "") == "FLAKY_AS_PASS"
    with pytest.raises(Exception) as exc_info:
        _validator.validate_result("PASS", "PASS", None, None)
    assert getattr(exc_info.value, "code", "") == "PASS_WITHOUT_ASSERTION"

    tag = "fxtests1-probe-flaky"
    project_id = "fxtests1-probe-%s" % tag
    plan_id = "plan-fxtests1-probe-%s" % tag
    run_id = "run-fxtests1-probe-%s" % tag
    started = client.post(
        "/api/v1/teststage/runs/start",
        json={"project_id": project_id, "plan_id": plan_id,
              "run_id": run_id},
    )
    assert started.status_code == 200, started.text
    # BLOCKED without a reason is refused on the served route.
    refused = client.post(
        "/api/v1/teststage/runs/results",
        json={"run_id": run_id, "test_id": "t-boot", "status": "BLOCKED",
              "output_ref": None, "reason": None},
    )
    assert refused.status_code == 400, refused.text
    assert "STATUS_REASON_MISSING" in refused.text
    # FLAKY is recorded but never counts as PASS.
    recorded = client.post(
        "/api/v1/teststage/runs/results",
        json={"run_id": run_id, "test_id": "t-boot", "status": "FLAKY",
              "output_ref": "evidence://%s/test-output/x" % project_id,
              "reason": None},
    )
    assert recorded.status_code == 200, recorded.text
    counters = client.get(
        "/api/v1/teststage/runs/counters", params={"run_id": run_id})
    assert counters.status_code == 200, counters.text
    assert counters.json()["passed"] == 0, counters.text


def test_probe_kind_counts_sum_to_catalog_total(client, clean_globals):
    """F6: per-kind counts sum to the catalog total."""
    from agent_si.qa_catalog import qa_catalog as _catalog

    catalog = _catalog.get_catalog("catalog-frozen-v1")
    total = len(catalog.tests)
    assert total == 6, [test.test_id for test in catalog.tests]
    plan = _catalog.derive_plan(
        "catalog-frozen-v1", "web", ["chat", "login", "offline", "perf"],
        "routine",
    )
    counts = _catalog.kind_counts(plan)
    assert sum(counts.values()) == len(plan.test_ids) == total, counts
    resp = client.post(
        "/api/v1/teststage/plans",
        json={
            "catalog_ids": [test.test_id for test in catalog.tests],
            "project_id": "fxtests1-probe-kinds",
            "run_id": "run-fxtests1-probe-kinds",
            "catalog_ref": "catalog-frozen-v1",
            "derived_by_model": "meta/muse-spark-1.3-contributor",
        },
    )
    assert resp.status_code == 200, resp.text
    served_counts = resp.json()["kind_counts"]
    assert sum(served_counts.values()) == 6, resp.text


# -- F4 refix path on real failures -------------------------------------------


def test_run_end_failure_uses_refix_path(store, clean_globals):
    """F4: failing CODE results at run end go back through the refix path."""
    from agent_si.test_runners import run_end as _run_end
    from agent_si.test_runners import stage_runner as _stage

    project_id = "fxtests1-runend-refix"
    project_dir = _project_dir(store, project_id)
    _write_script(
        os.path.join(project_dir, "t-boot.py"),
        "print('fxtests1-refix-boot-ok')\n",
    )
    _write_script(
        os.path.join(project_dir, "t-login.py"),
        "import sys\nsys.exit(7)\n",
    )
    _write_script(
        os.path.join(project_dir, "t-offline.py"),
        "print('fxtests1-refix-offline-ok')\n",
    )
    _write_script(
        os.path.join(project_dir, "t-perf.py"),
        "print('fxtests1-refix-perf-ok')\n",
    )
    record = _run_end.run_local_tests_at_run_end(
        project_id=project_id,
        run_id="run-fxtests1-refix",
        data_root=str(store),
        timeout_s=30,
    )
    assert record["skipped"] is False, record
    assert "plan-" in record["plan_id"], record
    assert record["counters"]["passed"] == 3, record
    assert record["counters"]["remaining"] == 3, record
    assert record["refix"]["failure_ids"] == ("t-login",), record
    stored = _stage._RESULTS.get(record["stage_run_id"], [])
    by_id = {row.test_id: row for row in stored}
    assert by_id["t-login"].status == "FAIL", by_id
