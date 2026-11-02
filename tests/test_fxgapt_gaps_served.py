"""FXGAPT gap proofs: code-level tests for the INT_GATE G5 gaps.

Live-drive rows with no literal code-level test at int 8b180bc:
F01 (Tests-tab counters+explainer data), F02 (pinned binding persists
and re-renders), F05 (live rows DURING a run), F06 (watcher rule-card
data), F14 (fresh-profile gate precondition), P16-howitworks (served
side: none — the diagram is a static frontend route; the live row's
expected testid kit-card-howitworks-diagram does not exist in product,
proven RED in frontend/src/app/__tests__/fxgapt.test.tsx).
Plus laptop-list REDs with backend-visible defects.

Every GREEN test drives the REAL app (create_app + TestClient,
raise_server_exceptions=False). The only fake is the provider network
boundary (MockProviderAdapter injection, the documented test seam).

Row-path correction (HD line): live row F02 documents
PUT /api/v1/roles/profile; no src/ file serves that path. The product
route is PUT /api/v1/routing/role (frontend/src/settings/
roleProfilesApi.ts, src/agent_si/backend/pools_routes.py). The test
below proves the REAL route; the row needs the path correction.

RED tests (test_red_*) fail by design: each proves one product defect
at the entry -> observable-result level. The fix lane turns them GREEN;
no product file is touched here.
"""

import json
import os
import sys
import threading
import time

import pytest
from fastapi.testclient import TestClient

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend import agents_live  # noqa: E402
from agent_si.backend import chat_stream as _chat  # noqa: E402
from agent_si.backend.app import create_app  # noqa: E402
from agent_si.backend.orchestration import steplimits as _steplimits  # noqa: E402
from agent_si.providers.adapters.base import (  # noqa: E402
    AdapterConfig,
    make_secret_ref,
)
from agent_si.providers.adapters.mock_provider import (  # noqa: E402
    MockProviderAdapter,
)
from agent_si.runtime.manager import run_task_streamed  # noqa: E402
from agent_si.watcher import journal as _journal  # noqa: E402

TEST_TOKEN = "fxgapt-served-token"
ACTOR = "fxgapt-tester"


def _auth():
    return {"x-actor": ACTOR, "x-ui-session-token": TEST_TOKEN}


def _settings(store_dir):
    return {
        "testing": True,
        "ui_session_token": TEST_TOKEN,
        "store_dir": str(store_dir),
    }


def _mock_adapter(canned=("fxgapt canned reply",)):
    config = AdapterConfig(
        provider_id="mock",
        instance_id="fxgapt",
        model="mock-canned",
        secret_ref=make_secret_ref(
            secret_id="mock-secret", provider_id="mock"),
    )
    return MockProviderAdapter(config, transport=None, canned=canned)


def _configure_budget(project_id, task_max_steps=10):
    outcome = _steplimits.apply_steplimit_config_change({
        "project_id": project_id,
        "authority": "M-MANAGER-CONT",
        "reason": "FXGAPT gap proof budget",
        "task_max_steps": task_max_steps,
        "chat_max_steps": task_max_steps,
    })
    assert outcome.applied, outcome.reason
    from agent_si.runtime import manager as _budget_mgr

    gate = _budget_mgr._BUDGET_GATE
    if gate is not None:
        try:
            gate.get_state(project_id)
        except (KeyError, LookupError):
            gate.configure_project(
                project_id, "USD", "1000000.00", "900000.00", "1000000.00")


@pytest.fixture
def store(tmp_path):
    root = tmp_path / "store"
    root.mkdir()
    return root


@pytest.fixture
def client(store):
    app = create_app(_settings(store))
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _clean_globals():
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
    saved_results = {key: list(val) for key, val in
                     _stage._RESULTS.items()}
    saved_assurance = dict(_stage._ASSURANCE_STATUS)
    saved_latest_run = dict(getattr(_stage, "_LATEST_RUN", {}))
    saved_latest_plan = dict(getattr(_planner, "_LATEST_PLAN", {}))
    saved_bound = _manager.bound_provider_adapter()
    saved_live = dict(agents_live._LIVE_ROWS)
    agents_live.clear_live_rows()
    _journal.reset_state()
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
    agents_live._LIVE_ROWS.clear()
    agents_live._LIVE_ROWS.update(saved_live)
    _journal.reset_state()
    _steplimits._reset_state()


# -- F01: Tests-tab counters + explainer data -------------------------------


def test_f01_empty_project_serves_no_plan_or_run(client):
    """F01 RED-first: a fresh project has no staged plan/run, so the
    Tests tab must render its empty state (naming how a run starts),
    never counters."""
    project_id = "fxgapt-f01-empty"
    plan = client.get("/api/v1/teststage/plans/latest",
                      params={"project_id": project_id})
    assert plan.status_code == 404, plan.text
    run = client.get("/api/v1/teststage/runs/latest",
                     params={"project_id": project_id})
    assert run.status_code == 404, run.text


def test_f01_product_run_serves_counters_and_rows(client):
    """F01 GREEN: a real product run writes stage results; plans/latest,
    runs/latest and tests-view serve the counters and rows the Tests
    tab renders (tests-counters + tests-explainer)."""
    project_id = "fxgapt-f01"
    _configure_budget(project_id)
    adapter = _mock_adapter(("fxgapt f01 turn",))
    events = list(run_task_streamed(
        None,
        agent_task=None,
        graph=None,
        provider_adapter=adapter,
        project_id=project_id,
        task_id="task-fxgapt-f01",
        message="serve one canned turn",
    ))
    assert events, "a streamed run always ends with a terminal event"
    assert events[-1].event == "done", events[-1]

    latest_run = client.get(
        "/api/v1/teststage/runs/latest", params={"project_id": project_id})
    assert latest_run.status_code == 200, latest_run.text
    run_id = latest_run.json()["run_id"]
    latest_plan = client.get(
        "/api/v1/teststage/plans/latest", params={"project_id": project_id})
    assert latest_plan.status_code == 200, latest_plan.text
    plan_id = latest_plan.json()["plan_id"]

    view = client.get(
        "/api/v1/teststage/tests-view",
        params={"plan_id": plan_id, "run_id": run_id})
    assert view.status_code == 200, view.text
    body = view.json()
    for key in ("active", "passed", "remaining", "rows"):
        assert key in body, body
    assert body["active"] == body["passed"] + body["remaining"], body
    assert len(body["rows"]) == body["active"], body
    by_id = {row["test_id"]: row for row in body["rows"]}
    assert by_id, "the view serves one row per staged test"
    for row in body["rows"]:
        # Served staged-row shape: test_id + status always; output_ref
        # / reason ride only when recorded. There is no `kind` key on
        # the staged row (the tab renders unknown-kind in that case).
        assert row["test_id"], row
        assert row["status"] in ("PASS", "FAIL", "BLOCKED"), row


# -- F02: pinned binding persists and re-renders ----------------------------

ROLE_PATH = "/api/v1/routing/role"


def test_f02_get_before_put_404s(client):
    """F02 RED-first: no profile stored yet, GET answers 404 (the
    editor shows 'needs both a provider and a model')."""
    resp = client.get(ROLE_PATH, params={"project_id": "fxgapt-f02",
                                         "role": "manager"})
    assert resp.status_code == 404, resp.text


def test_f02_pinned_manager_persists_and_reads_back(client):
    """F02 GREEN: PUT PINNED provider+model through the real route the
    Settings editor uses; GET returns the saved binding (mode,
    provider, model) for the chat role line to re-render."""
    project_id = "fxgapt-f02"
    put = client.put(ROLE_PATH, json={
        "project_id": project_id, "role": "manager", "mode": "PINNED",
        "provider": "meta", "model": "meta/muse-spark-1.3-contributor",
    }, headers=_auth())
    assert put.status_code == 200, put.text
    assert put.json().get("ok") is True, put.text
    saved = put.json()["profile"]
    assert saved["mode"] == "PINNED", put.text
    assert saved["provider"] == "meta", put.text
    assert saved["model"] == "meta/muse-spark-1.3-contributor", put.text

    readback = client.get(ROLE_PATH, params={"project_id": project_id,
                                             "role": "manager"})
    assert readback.status_code == 200, readback.text
    profile = readback.json()["profile"]
    assert profile["mode"] == "PINNED", readback.text
    assert profile["provider"] == "meta", readback.text
    assert profile["model"] == "meta/muse-spark-1.3-contributor", \
        readback.text


def test_f02_pinned_without_model_refused(client):
    """F02 GREEN negative: PINNED without a model never stores (400),
    so the chat role line can never render a half binding."""
    resp = client.put(ROLE_PATH, json={
        "project_id": "fxgapt-f02", "role": "manager", "mode": "PINNED",
        "provider": "meta",
    }, headers=_auth())
    assert resp.status_code == 400, resp.text
    missing = client.get(ROLE_PATH, params={"project_id": "fxgapt-f02",
                                            "role": "manager"})
    assert missing.status_code == 404, missing.text


# -- F05: live rows DURING a run --------------------------------------------

class _GatedMock(MockProviderAdapter):
    """Mock that blocks inside invoke until released (mid-run probe)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.entered = threading.Event()
        self.release = threading.Event()

    def invoke(self, messages, params=None, max_turns=8):
        self.entered.set()
        assert self.release.wait(timeout=60), "probe released the turn"
        return super().invoke(messages, params=params,
                              max_turns=max_turns)


def test_f05_empty_store_serves_no_rows(client):
    """F05 RED-first: with no run, the live route serves an empty agent
    list, so the panel renders its empty state (empty is FAIL on the
    live row, never a pass)."""
    resp = client.get("/api/v1/agents/live")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"agents": []}, resp.text


def test_f05_live_row_visible_during_run(client):
    """F05 GREEN: while a real streamed turn is in flight, the live
    route serves its RUNNING row (agent/scope/deliverable/status plus
    role/model/step/file/cost/tokens/context/errors/waits); the run
    then completes."""
    project_id = "fxgapt-f05"
    _configure_budget(project_id)
    gate = _GatedMock(
        AdapterConfig(
            provider_id="mock", instance_id="fxgapt-f05",
            model="mock-canned",
            secret_ref=make_secret_ref(secret_id="mock-secret",
                                       provider_id="mock")),
        transport=None, canned=("fxgapt f05 mid-run turn",))
    outcomes = {}

    def _run():
        try:
            outcomes["events"] = list(run_task_streamed(
                None, agent_task=None, graph=None,
                provider_adapter=gate, project_id=project_id,
                task_id="task-fxgapt-f05", message="mid-run probe"))
        except Exception as exc:  # pragma: no cover - probe plumbing
            outcomes["error"] = exc

    worker = threading.Thread(target=_run, daemon=True)
    worker.start()
    try:
        assert gate.entered.wait(timeout=60), "the turn started"
        deadline = time.time() + 30
        running = []
        while time.time() < deadline:
            resp = client.get("/api/v1/agents/live")
            assert resp.status_code == 200, resp.text
            rows = resp.json()["agents"]
            running = [row for row in rows
                       if row.get("status") == "RUNNING"]
            if running:
                break
            time.sleep(0.2)
        assert running, "a RUNNING row is served mid-run"
        row = running[0]
        for key in ("agent", "scope", "deliverable", "status", "role",
                    "model", "step", "file", "cost", "tokens", "context",
                    "errors", "waits"):
            assert key in row, (key, row)
        assert "task-fxgapt-f05" in str(row["scope"]), row
    finally:
        gate.release.set()
        worker.join(timeout=120)
    assert "error" not in outcomes, outcomes.get("error")
    assert outcomes["events"][-1].event == "done", outcomes["events"][-1]


# -- F06: watcher status + journal served -----------------------------------

def test_f06_journal_entry_served_in_status_and_journal(client):
    """F06 GREEN: an appended watcher event is served verbatim: the
    journal lists it (entry_id/timestamp/hash) and status carries it
    as journal_head (the per-card model source for rule cards)."""
    project_id = "fxgapt-f06"
    receipt = _journal.append_event(project_id, "fxgapt", "WATCH_DECISION",
                                    "gap probe decision", ("ref-1",))
    journal = client.get("/api/v1/watcher/journal",
                         params={"project_id": project_id})
    assert journal.status_code == 200, journal.text
    rows = journal.json()
    assert isinstance(rows, list) and rows, rows
    served = [row for row in rows
              if row.get("entry_id") == receipt.entry_id]
    assert served, rows
    assert served[0]["hash"] == receipt.hash, served
    assert served[0]["timestamp"] == receipt.timestamp, served

    status = client.get("/api/v1/watcher/status",
                        params={"project_id": project_id})
    assert status.status_code == 200, status.text
    body = status.json()
    assert body["project_id"] == project_id, body
    assert body["journal_head"] == receipt.entry_id, body
    assert body["generated_at"] == receipt.timestamp, body
    assert isinstance(body["integrity_ok"], bool), body


# -- F14: fresh-profile gate precondition -----------------------------------

def test_f14_fresh_store_serves_empty_projects_and_providers(client):
    """F14 GREEN: a fresh profile stores nothing, so FirstRunGate (the
    / route with zero connected providers) sends a newcomer to
    /firstrun by itself. Served proof of the gate precondition."""
    projects = client.get("/api/v1/projects")
    assert projects.status_code == 200, projects.text
    assert projects.json().get("projects") == [], projects.text
    providers = client.get("/api/v1/providers", headers=_auth())
    assert providers.status_code == 200, providers.text
    assert providers.json().get("providers") == [], providers.text


# -- Laptop REDs (backend-visible) ------------------------------------------


def _served_chat_client(tmp_path, monkeypatch):
    """Real app with the orchestration path forced (manager loaders off)."""
    monkeypatch.setattr(
        _chat, "_load_manager_run_task_streamed", lambda: None)
    monkeypatch.setattr(
        _chat, "_load_manager_bound_provider", lambda: None)
    app = create_app(_settings(tmp_path))
    app.state.chat_provider_adapter = _mock_adapter()
    return app, TestClient(app, raise_server_exceptions=False)


def test_laptop_ukrainian_task_kept_across_restart(tmp_path, monkeypatch):
    """LAPTOP-B GREEN: a Ukrainian task round-trips verbatim and one
    entry per task survives an app rebuild on the same store
    (restart-kept, no duplicates)."""
    from agent_si.backend.orchestration import steplimits as _limits

    _app, client = _served_chat_client(tmp_path, monkeypatch)
    project = client.post("/api/v1/projects", json={
        "name": "uk-project", "folder_ref": "dock-fxgapt-uk",
    }, headers=_auth())
    assert project.status_code == 200, project.text
    pid = project.json()["project"]["project_id"]
    outcome = _limits.apply_steplimit_config_change({
        "project_id": pid, "authority": "fxgapt", "reason": "uk task",
        "task_max_steps": 10, "chat_max_steps": 10,
    })
    assert outcome.applied, outcome.reason
    msg = "План українською: перевірити паркан"
    resp = client.post("/api/v1/chat/stream",
                       json={"message": msg, "project": pid},
                       headers=_auth())
    assert resp.status_code == 200, resp.text
    listed = client.get("/api/v1/tasks", params={"project_id": pid})
    assert listed.status_code == 200, listed.text
    rows = listed.json()["tasks"]
    assert len(rows) == 1, rows
    assert msg in rows[0]["title"], rows

    rebuilt = TestClient(create_app(_settings(tmp_path)),
                         raise_server_exceptions=False)
    again = rebuilt.get("/api/v1/tasks", params={"project_id": pid})
    assert again.status_code == 200, again.text
    rows2 = again.json()["tasks"]
    assert len(rows2) == 1, rows2
    assert rows2[0]["task_id"] == rows[0]["task_id"], (rows, rows2)
    assert msg in rows2[0]["title"], rows2


def _sse_texts(text):
    events = []
    for line in text.splitlines():
        if line.startswith("data:"):
            try:
                events.append(json.loads(line[len("data:"):].strip()))
            except ValueError:
                pass
    return events


def test_red_laptop_chat_echoes_absolute_folder(tmp_path, monkeypatch):
    """LAPTOP-B (was RED, now GREEN): the honest missing-folder line
    names the folder, never the host absolute path
    (chat_stream._devrun_folder via _chat_folder_label).

    NOTE: must run through the bound-provider orchestration path
    (_served_chat_client): with no provider bound the route takes
    no_provider_run (NO_PROVIDER_BOUND only, devrun entry never
    evaluated) and the probe would pass vacuously."""
    from agent_si.backend.orchestration import steplimits as _limits

    _app, client = _served_chat_client(tmp_path, monkeypatch)
    created = client.post("/api/v1/projects", json={
        "name": "laptop-path", "folder_ref": "dock-fxgapt-path",
    }, headers=_auth())
    assert created.status_code == 200, created.text
    project_id = created.json()["project"]["project_id"]
    outcome = _limits.apply_steplimit_config_change({
        "project_id": project_id,
        "authority": "fxgapt", "reason": "path leak probe",
        "task_max_steps": 2, "chat_max_steps": 2,
    })
    assert outcome.applied, outcome.reason
    missing = str(tmp_path / "no-such-folder-xyz")
    resp = client.post("/api/v1/chat/stream", json={
        "project": project_id, "folder": missing,
        "message": "hello",
    }, headers=_auth())
    assert resp.status_code == 200, resp.text
    texts = " ".join(str(event.get("text", "")) + " " +
                     str(event.get("detail", ""))
                     for event in _sse_texts(resp.text))
    assert "project folder not found" in texts, (
        "the honest folder entry never fired: %r" % texts[:500])
    assert "no-such-folder-xyz" in texts, (
        "the folder name is shown: %r" % texts[:500])
    assert missing not in texts, (
        "chat text echoes the absolute host folder path: %r" % texts[:500])
    assert "D:\\" not in texts and "C:\\" not in texts, (
        "no drive prefix in chat text: %r" % texts[:500])


def test_laptop_working_folder_shows_name_only(tmp_path):
    """LAPTOP-B GREEN: the first stream delta names the working folder
    by its base name, never a drive-letter host path (the engine still
    runs against the absolute folder; scripted factory, no real run)."""
    from tests.test_fxdevwire_served import (
        _all_text,
        _delta_texts,
        _green_factory,
        _make_project,
        _parse_sse,
        _post_chat,
        _served_app,
    )

    project = "fxgapt-workname"
    folder = tmp_path / ("ws-" + project)
    folder.mkdir(parents=True, exist_ok=True)
    app = _served_app(tmp_path, project, _green_factory())
    client = TestClient(app, raise_server_exceptions=False)
    pid = _make_project(app, client, "workname build", str(folder))
    resp = _post_chat(client, pid, "build it", folder=str(folder))
    assert resp.status_code == 200, resp.text
    events = _parse_sse(resp.text)
    deltas = _delta_texts(events)
    assert deltas and deltas[0].startswith("Working folder: "), deltas[:2]
    assert deltas[0] == "Working folder: %s\n" % folder.name, deltas[0]
    assert "D:\\" not in deltas[0] and "C:\\" not in deltas[0], deltas[0]
    assert str(folder) not in _all_text(events), deltas[0]
