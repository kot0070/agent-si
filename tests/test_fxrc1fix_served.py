"""FXRC1FIX served proof: short team lines, run-end live rows leave RUNNING.

Drives the real seam app (create_app + TestClient,
raise_server_exceptions=False). Fakes live ONLY at the provider network
boundary: a scripted per-role adapter factory plus canned JSON per role.

Rows (each its own test):
P2a all roles on one provider/model collapse to one short Team line
  (role + model names kept, no raw why JSON in chat text).
P2b mixed providers/models yield one short line per role (no raw why
  JSON, role + model names kept).
P2c full why stays in the DEVRUN_PLAN journal row.
P5a a green run ends with zero RUNNING live rows for the run.
P5b a held (install-ask) run ends with zero RUNNING live rows.
"""

import copy
import json
import os
import sys

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
from agent_si.watcher import journal as _journal  # noqa: E402

TEST_TOKEN = "fxrc1fix-served-token"
ACTOR = "fxrc1fix-tester"
PROVIDER = "mock"
MODEL = "mock-canned"
OTHER_PROVIDER = "other"
OTHER_MODEL = "other-model"
INSTALL_ARGV = ["cargo", "install", "fxrc1-pkg"]


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
        "authority": "fxrc1fix-test",
        "reason": "fxrc1fix served run needs step budgets",
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


def _parse_sse(text):
    events = []
    for line in text.splitlines():
        if line.startswith("data:"):
            events.append(json.loads(line[len("data:"):].strip()))
    return events


def _all_text(events):
    return " ".join(
        str(event.get("text", "")) for event in events
        if isinstance(event, dict))


def _types(events):
    return [event.get("type") for event in events
            if isinstance(event, dict)]


def _delta_texts(events):
    return [str(event.get("text", "")) for event in events
            if isinstance(event, dict) and event.get("type") == "delta"]


class _ScriptedAdapter(MockProviderAdapter):
    """Network-boundary fake only: scripted text per call, spy records."""

    def __init__(self, config, role, script, spy, usage=None):
        super().__init__(config, transport=None, canned=("standby",))
        self.role = role
        self.script = script
        self.spy = spy
        self.forced_usage = usage

    def invoke(self, messages, params=None, max_turns=8):
        self._check_messages(messages)
        request = self._resolve_request(messages, params)
        calls = [entry for entry in self.spy
                 if entry.get("adapter_id") == id(self)]
        if callable(self.script):
            text = self.script(len(calls), copy.deepcopy(messages))
        else:
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
            usage=dict(self.forced_usage)
            if self.forced_usage is not None else dict(MOCK_USAGE),
            mock=True,
            error_ref=None,
        )


class _FakeFactory:
    """Per-role scripted adapters; one fresh instance per call."""

    def __init__(self, scripts, usages=None, providers=(PROVIDER,)):
        self.scripts = dict(scripts)
        self.usages = dict(usages or {})
        self.providers = list(providers)
        self.spy = []

    def connected_providers(self):
        return list(self.providers)

    def __call__(self, *, role, provider, model):
        config = AdapterConfig(
            provider_id=provider,
            instance_id="fxrc1fix-%s" % role,
            model=model,
            secret_ref=make_secret_ref(
                secret_id="mock-secret", provider_id=provider),
        )
        return _ScriptedAdapter(
            config, role, self.scripts[role], self.spy,
            self.usages.get(role))


def _pin_all(app, project, mode="PINNED", provider=PROVIDER, model=MODEL):
    table = app.state.k04_ctx.role_table
    for role in ("director", "manager", "worker", "auditor"):
        table.set_profile(RoleModelProfile(
            role=role, project_id=project, mode=mode,
            provider=None if mode == "AUTO" else provider,
            model=None if mode == "AUTO" else model,
            binding="DEFAULT", version=1, hash="fxrc1fix-test"))
    return table


def _bound_mock():
    return MockProviderAdapter(
        AdapterConfig(
            provider_id=PROVIDER,
            instance_id="fxrc1fix-bound",
            model=MODEL,
            secret_ref=make_secret_ref(
                secret_id="mock-secret", provider_id=PROVIDER),
        ),
        transport=None, canned=("bound standby",))


def _served_app(tmp_path, project, factory):
    agents_live.clear_live_rows()
    _steplimits._reset_state()
    _apply_limits(project)
    store = tmp_path / ("store-" + project)
    store.mkdir(parents=True, exist_ok=True)
    app = create_app(_settings(store))
    _pin_all(app, project)
    app.state.chat_provider_adapter = _bound_mock()
    app.state.devrun_adapter_factory = factory
    return app


def _project_dir(tmp_path, project):
    folder = tmp_path / ("proj-" + project)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _make_project(app, client, name, folder_ref):
    resp = client.post(
        "/api/v1/projects",
        json={"name": name, "folder_ref": folder_ref},
        headers=_auth())
    assert resp.status_code == 200, resp.text
    pid = resp.json()["project"]["project_id"]
    _apply_limits(pid)
    _pin_all(app, pid)
    return pid


def _post_chat(client, project, message):
    return client.post(
        "/api/v1/chat/stream",
        json={"project": project, "message": message},
        headers=_auth())


def _plan_text(parts):
    return json.dumps({"parts": parts})


def _one_part_plan():
    return [
        {"part_id": "p1", "goal": "Write test_p1.py with one passing test",
         "files": ["test_p1.py"],
         "check_commands": [["python", "-m", "pytest", "test_p1.py",
                              "-q", "-p", "no:cacheprovider"]],
         "depends_on": []},
    ]


def _worker_done(n_calls, messages):
    del messages
    if n_calls % 2 == 0:
        return json.dumps({
            "actions": [{"action": "write_file", "path": "test_p1.py",
                         "content": "def test_p1():\n    assert 1 + 1 == 2\n"}],
            "done": False})
    return json.dumps({"actions": [], "done": True})


def _manager_order(n_calls, messages):
    del n_calls, messages
    return json.dumps({"order": ["p1"]})


def _audit_pass(n_calls, messages):
    del n_calls, messages
    return json.dumps({"result": "PASS", "reasons": ["checks green"]})


def _green_factory():
    return _FakeFactory({
        "director": [_plan_text(_one_part_plan())],
        "manager": [_manager_order],
        "worker": [_worker_done],
        "auditor": [_audit_pass],
    })


def _run_live_rows(client, pid):
    live = client.get("/api/v1/agents/live")
    assert live.status_code == 200, live.text
    return [row for row in live.json().get("agents", [])
            if str(row.get("scope", "")).startswith("fxdevrun:")]


# -- P2a: one Team line when all roles share provider/model -------------

def test_p2a_single_team_line_when_same(tmp_path):
    project = "fxrc1-p2a"
    folder = _project_dir(tmp_path, project)
    app = _served_app(tmp_path, project, _green_factory())
    client = TestClient(app, raise_server_exceptions=False)
    pid = _make_project(app, client, "p2a build it", str(folder))
    resp = _post_chat(client, pid, "build it")
    assert resp.status_code == 200, resp.text
    text = _all_text(_parse_sse(resp.text))
    team = [line for line in _delta_texts(_parse_sse(resp.text))
            if line.startswith("Team:")]
    assert len(team) == 1, text
    line = team[0]
    for role in ("director", "manager", "worker", "auditor"):
        assert role in line, line
    assert PROVIDER in line and MODEL in line, line
    assert "why: {" not in text and "(PINNED why:" not in text, text
    assert "(Auto why:" not in text and '"connected"' not in text, text


# -- P2b: one short line per role when models differ ---------------------

def test_p2b_per_role_lines_when_mixed(tmp_path):
    project = "fxrc1-p2b"
    folder = _project_dir(tmp_path, project)
    app = _served_app(tmp_path, project, _green_factory())
    client = TestClient(app, raise_server_exceptions=False)
    pid = _make_project(app, client, "p2b build it", str(folder))
    app.state.k04_ctx.role_table.set_profile(RoleModelProfile(
        role="director", project_id=pid, mode="PINNED",
        provider=OTHER_PROVIDER, model=OTHER_MODEL,
        binding="DEFAULT", version=1, hash="fxrc1fix-test"))
    resp = _post_chat(client, pid, "build it")
    assert resp.status_code == 200, resp.text
    events = _parse_sse(resp.text)
    text = _all_text(events)
    assert not any(line.startswith("Team:")
                   for line in _delta_texts(events)), text
    for role in ("director", "manager", "worker", "auditor"):
        assert ("Role %s:" % role) in text, text
    assert OTHER_PROVIDER in text and OTHER_MODEL in text, text
    assert PROVIDER in text and MODEL in text, text
    assert "why: {" not in text and "why:" not in text.lower(), text


# -- P2c: full why stays in DEVRUN_PLAN ----------------------------------

def test_p2c_full_why_in_plan_journal(tmp_path):
    project = "fxrc1-p2c"
    folder = _project_dir(tmp_path, project)
    app = _served_app(tmp_path, project, _green_factory())
    client = TestClient(app, raise_server_exceptions=False)
    pid = _make_project(app, client, "p2c build it", str(folder))
    resp = _post_chat(client, pid, "build it")
    assert resp.status_code == 200, resp.text
    rows = _journal.stored_rows(pid, "DEVRUN_PLAN")
    assert rows, "plan journal row recorded"
    assert any("director" in row.summary.lower()
               and PROVIDER in row.summary for row in rows), (
        [row.summary for row in rows])


# -- P5a: green run leaves no RUNNING live rows ---------------------------

def test_p5a_green_run_leaves_no_running_rows(tmp_path):
    project = "fxrc1-p5a"
    folder = _project_dir(tmp_path, project)
    app = _served_app(tmp_path, project, _green_factory())
    client = TestClient(app, raise_server_exceptions=False)
    pid = _make_project(app, client, "p5a build it", str(folder))
    resp = _post_chat(client, pid, "build it")
    assert resp.status_code == 200, resp.text
    rows = _run_live_rows(client, pid)
    assert rows, "the run tracked live rows"
    assert [row for row in rows
            if row.get("status") == "RUNNING"] == [], rows


# -- P5b: held run leaves no RUNNING live rows ----------------------------

def _worker_install(n_calls, messages):
    blob = " ".join(str(part.get("content", ""))
                    for part in messages if isinstance(part, dict))
    if "install fxrc1-pkg: exit" in blob or "refused:" in blob:
        return json.dumps({"actions": [], "done": True})
    return json.dumps({
        "actions": [{"action": "run", "argv": list(INSTALL_ARGV)}],
        "done": False})


def test_p5b_held_run_leaves_no_running_rows(tmp_path):
    project = "fxrc1-p5b"
    folder = _project_dir(tmp_path, project)
    factory = _FakeFactory({
        "director": [_plan_text(_one_part_plan())],
        "manager": [_manager_order],
        "worker": [_worker_install],
        "auditor": [_audit_pass],
    })
    app = _served_app(tmp_path, project, factory)
    client = TestClient(app, raise_server_exceptions=False)
    pid = _make_project(app, client, "p5b install it", str(folder))
    resp = _post_chat(client, pid, "install it")
    assert resp.status_code == 200, resp.text
    assert "approval" in _types(_parse_sse(resp.text)), resp.text[:500]
    rows = _run_live_rows(client, pid)
    assert rows, "the held run tracked live rows"
    assert [row for row in rows
            if row.get("status") == "RUNNING"] == [], rows
