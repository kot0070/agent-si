"""FXVIEWS2 served proof: the run writes the facts the tabs read.

Drives the REAL engine + real routes (create_app + TestClient,
raise_server_exceptions=False) over a real throwaway project folder.
Fakes live ONLY at the provider network boundary: a scripted per-role
adapter (transport None, canned JSON per role). One green run proves:

- RED first: runs/ledger holds no devrun row, the task reads CREATED.
- During the run the task reads running; after it the task reads done.
- runs/ledger serves one row: run id, start/end stamps, parts,
  verdicts, tokens (served cells), cost UNKNOWN, written files.
- A fresh app on the same data dir still serves the row (persisted).

Rows A/B of the brief (Overview/Tasks tab status, Runs ledger rows);
C rides the same record (files from artifacts, verdicts from parts);
D is verify-only (see PAIR-RETURN).
"""

import copy
import json
import os
import sys
import threading
import time

from fastapi.testclient import TestClient

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend import agents_live  # noqa: E402
from agent_si.backend.app import create_app  # noqa: E402
from agent_si.backend.orchestration import steplimits as _steplimits  # noqa: E402
from agent_si.providers.adapters.base import (  # noqa: E402
    AdapterConfig,
    AdapterResponse,
    make_secret_ref,
)
from agent_si.providers.adapters.mock_provider import (  # noqa: E402
    MOCK_USAGE,
    MockProviderAdapter,
)
from agent_si.routing.types import RoleModelProfile  # noqa: E402

TEST_TOKEN = "fxviews2-served-token"
ACTOR = "fxviews2-tester"
PROVIDER = "mock"
MODEL = "mock-canned"


def _auth(token=TEST_TOKEN, actor=ACTOR):
    return {"x-actor": actor, "x-ui-session-token": token}


def _settings(store_dir):
    return {
        "testing": True,
        "ui_session_token": TEST_TOKEN,
        "store_dir": str(store_dir),
    }


def _apply_limits(project_id):
    outcome = _steplimits.apply_steplimit_config_change({
        "project_id": project_id,
        "authority": "fxviews2-test",
        "reason": "fxviews2 served run needs step budgets",
        "task_max_steps": 10,
        "chat_max_steps": 10,
    })
    assert outcome.applied, outcome.reason


def setup_function(_func):
    agents_live.clear_live_rows()
    _steplimits._reset_state()


def teardown_function(_func):
    agents_live.clear_live_rows()
    _steplimits._reset_state()


class _ScriptedAdapter(MockProviderAdapter):
    """Network-boundary fake only: scripted text per call, spy records."""

    def __init__(self, config, role, script, spy):
        super().__init__(config, transport=None, canned=("standby",))
        self.role = role
        self.script = script
        self.spy = spy

    def invoke(self, messages, params=None, max_turns=8):
        self._check_messages(messages)
        request = self._resolve_request(messages, params)
        calls = [entry for entry in self.spy
                 if entry.get("adapter_id") == id(self)]
        text = self.script[min(len(calls), len(self.script) - 1)]
        if callable(text):
            try:
                text = text(len(calls), copy.deepcopy(messages))
            except TypeError:
                text = text(copy.deepcopy(messages))
        self.turns_served += 1
        self.spy.append({
            "adapter_id": id(self),
            "role": self.role,
            "provider": self.config.provider_id,
            "model": request["model"],
            "messages": copy.deepcopy(messages),
        })
        return AdapterResponse(
            provider_id=self.config.provider_id,
            instance_id=self.config.instance_id,
            model=request["model"],
            output_text=text,
            finish_reason="stop",
            usage=dict(MOCK_USAGE),
            mock=True,
            error_ref=None,
        )


class _FakeFactory:
    """Per-role scripted adapters; one fresh instance per call."""

    def __init__(self, scripts):
        self.scripts = dict(scripts)
        self.spy = []

    def connected_providers(self):
        return [PROVIDER]

    def __call__(self, *, role, provider, model):
        config = AdapterConfig(
            provider_id=provider,
            instance_id="fxviews2-%s" % role,
            model=model,
            secret_ref=make_secret_ref(
                secret_id="mock-secret", provider_id=provider),
        )
        return _ScriptedAdapter(config, role, self.scripts[role], self.spy)


def _pin_all(app, project):
    table = app.state.k04_ctx.role_table
    for role in ("director", "manager", "worker", "auditor"):
        table.set_profile(RoleModelProfile(
            role=role, project_id=project, mode="PINNED",
            provider=PROVIDER, model=MODEL,
            binding="DEFAULT", version=1, hash="fxviews2-test"))
    return table


def _served_app(store, factory):
    agents_live.clear_live_rows()
    _steplimits._reset_state()
    store.mkdir(parents=True, exist_ok=True)
    app = create_app(_settings(store))
    app.state.chat_provider_adapter = MockProviderAdapter(
        AdapterConfig(
            provider_id=PROVIDER,
            instance_id="fxviews2-bound",
            model=MODEL,
            secret_ref=make_secret_ref(
                secret_id="mock-secret", provider_id=PROVIDER),
        ),
        transport=None, canned=("bound standby",))
    app.state.devrun_adapter_factory = factory
    return app


def _one_part_plan():
    return [
        {"part_id": "p1", "goal": "Write test_p1.py with one passing test",
         "files": ["test_p1.py"],
         "check_commands": [["python", "-m", "pytest", "test_p1.py",
                              "-q", "-p", "no:cacheprovider"]],
         "depends_on": []},
    ]


def _worker_write_then_done(n_calls, messages):
    del messages
    if n_calls % 2 == 0:
        return json.dumps({
            "actions": [{"action": "write_file", "path": "test_p1.py",
                         "content": "def test_p1():\n    assert 1 + 1 == 2\n"}],
            "done": False})
    return json.dumps({"actions": [], "done": True})


def _parse_sse(text):
    events = []
    for line in text.splitlines():
        if line.startswith("data:"):
            events.append(json.loads(line[len("data:"):].strip()))
    return events


def test_fxviews2_run_writes_task_status_and_ledger_row(tmp_path):
    project = "fxv2"
    folder = tmp_path / ("proj-" + project)
    folder.mkdir(parents=True, exist_ok=True)
    factory = _FakeFactory({
        "director": [json.dumps({"parts": _one_part_plan()})],
        "manager": [json.dumps({"order": ["p1"]})],
        "worker": [_worker_write_then_done],
        "auditor": [json.dumps({"result": "PASS",
                                 "reasons": ["checks green"]})],
    })
    app = _served_app(tmp_path / ("store-" + project), factory)
    client = TestClient(app, raise_server_exceptions=False)

    created = client.post(
        "/api/v1/projects",
        json={"name": "fxviews2", "folder_ref": str(folder)},
        headers=_auth())
    assert created.status_code == 200, created.text
    project_id = created.json()["project"]["project_id"]
    assert project_id, created.text
    _apply_limits(project_id)
    _pin_all(app, project_id)

    tasked = client.post(
        "/api/v1/projects/%s/tasks" % project_id,
        json={"title": "build it", "scope": []},
        headers=_auth())
    assert tasked.status_code == 200, tasked.text
    task_id = tasked.json()["task"]["task_id"]
    assert tasked.json()["task"]["status"] == "CREATED", tasked.text

    # RED first: no devrun row served, task still queued.
    before = client.get(
        "/api/v1/runs/ledger", params={"project_id": project_id})
    assert before.status_code == 200, before.text
    assert before.json() == {"rows": []}, before.text

    holder = {}

    def _run():
        try:
            holder["resp"] = client.post(
                "/api/v1/chat/stream",
                json={"project": project_id, "folder": str(folder),
                      "task": task_id, "message": "build it"},
                headers=_auth())
        except Exception as err:  # never silent: the join asserts
            holder["error"] = err

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    try:
        seen_running = False
        deadline = time.time() + 60
        while time.time() < deadline:
            row = client.get("/api/v1/tasks/%s" % task_id)
            if row.status_code == 200 and \
                    row.json()["task"]["status"] == "running":
                seen_running = True
                break
            if not thread.is_alive():
                break
            time.sleep(0.2)
    finally:
        thread.join(timeout=110)
    assert not thread.is_alive(), "chat stream run finished"
    assert "error" not in holder, holder.get("error")
    resp = holder["resp"]
    assert resp.status_code == 200, resp.text
    assert seen_running, "task read running while the run streamed"

    done = client.get("/api/v1/tasks/%s" % task_id)
    assert done.status_code == 200, done.text
    assert done.json()["task"]["status"] == "done", done.text

    served = client.get(
        "/api/v1/runs/ledger", params={"project_id": project_id})
    assert served.status_code == 200, served.text
    body = served.json()
    assert isinstance(body.get("runs"), list) and \
        len(body["runs"]) == 1, body
    row = body["runs"][0]
    assert row["task"] == task_id, row
    assert row["start"] not in (None, "UNKNOWN"), row
    assert row["end"] not in (None, "UNKNOWN"), row
    assert row["end"] >= row["start"], row
    assert row["parts"] == [{
        "part_id": "p1", "verdict": "PASS",
        "attempts": 1, "reason": "checks green, auditor PASS"}], row
    assert row["verdicts"] == {"p1": "PASS"}, row
    assert isinstance(row["tokens"], int), row  # served mock cells sum
    assert row["cost"] == "UNKNOWN", row  # unpriced: never a faked 0
    assert "test_p1.py" in row["files"], row
    assert row["success"] is True, row

    # Restart keeps them: a fresh app on the same data dir serves it.
    app2 = create_app(_settings(tmp_path / ("store-" + project)))
    client2 = TestClient(app2, raise_server_exceptions=False)
    again = client2.get(
        "/api/v1/runs/ledger", params={"project_id": project_id})
    assert again.status_code == 200, again.text
    assert isinstance(again.json().get("runs"), list) and \
        len(again.json()["runs"]) == 1, again.text
    assert again.json()["runs"][0]["verdicts"] == {"p1": "PASS"}, again.text
    retasked = client2.get("/api/v1/tasks/%s" % task_id)
    assert retasked.status_code == 200, retasked.text
    assert retasked.json()["task"]["status"] == "done", retasked.text
