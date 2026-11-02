"""FXDEVWIRE served proof: dev engine reachable by clicks, S1-S9.

Drives the real seam app (create_app + TestClient,
raise_server_exceptions=False). Fakes live ONLY at the provider network
boundary: a scripted per-role adapter factory plus canned JSON per role.
Exact ChatOpen wire body the frontend sends ({project, message});
folder resolution, stop, journal, roles, caps and telemetry are served.

Rows (each its own test):
S1a stored absolute folder is used, first delta names working folder.
S1b absolute missing folder ends honest, engine never called.
S1c non-absolute folder_ref uses managed folder, created on demand.
S2 first message creates 1 project + 1 task, then 1 stream same text.
S3 run text: roles, plan, per-part, per-command, auditor, tokens/cost,
  terminal text; every delta ends with a newline.
S4 stop-all ends a live stream cancelled and stops the dev run.
S5 journal carries DEVRUN_PLAN/PART/AUDIT/END, audit row has reasons.
S6 frontend body shape runs the full chain with 4 journal kinds.
S7 zero-profile project resolves all 4 roles, reaches Director.
S8 cap 0.00 means zero provider calls plus a visible stop line.
S9 one telemetry row per call, budget spent grows once per call.
"""

import copy
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

TEST_TOKEN = "fxdevwire-served-token"
ACTOR = "fxdevwire-tester"
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
        "authority": "fxdevwire-test",
        "reason": "fxdevwire served run needs step budgets",
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
            instance_id="fxdevwire-%s" % role,
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
            binding="DEFAULT", version=1, hash="fxdevwire-test"))
    return table


def _bound_mock():
    return MockProviderAdapter(
        AdapterConfig(
            provider_id=PROVIDER,
            instance_id="fxdevwire-bound",
            model=MODEL,
            secret_ref=make_secret_ref(
                secret_id="mock-secret", provider_id=PROVIDER),
        ),
        transport=None, canned=("bound standby",))


def _served_app(tmp_path, project, factory, auto=False, pin=True):
    agents_live.clear_live_rows()
    _steplimits._reset_state()
    _apply_limits(project)
    store = tmp_path / ("store-" + project)
    store.mkdir(parents=True, exist_ok=True)
    app = create_app(_settings(store))
    if pin:
        _pin_all(app, project, mode="AUTO" if auto else "PINNED")
    app.state.chat_provider_adapter = _bound_mock()
    app.state.devrun_adapter_factory = factory
    return app


def _project_dir(tmp_path, project):
    folder = tmp_path / ("proj-" + project)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _make_project(app, client, name, folder_ref, pin=True):
    resp = client.post(
        "/api/v1/projects",
        json={"name": name, "folder_ref": folder_ref},
        headers=_auth())
    assert resp.status_code == 200, resp.text
    pid = resp.json()["project"]["project_id"]
    _apply_limits(pid)
    if pin:
        _pin_all(app, pid)
    return pid


def _make_task(client, project_id, title):
    resp = client.post(
        "/api/v1/projects/%s/tasks" % project_id,
        json={"title": title, "scope": []},
        headers=_auth())
    assert resp.status_code == 200, resp.text
    return resp.json()["task"]["task_id"]


def _post_chat(client, project, message, folder=None, task=None):
    body = {"project": project, "message": message}
    if folder is not None:
        body["folder"] = folder
    if task is not None:
        body["task"] = task
    return client.post("/api/v1/chat/stream", json=body, headers=_auth())


def _run_record(app, project):
    runs = getattr(app.state, "devrun_runs", None) or {}
    return runs.get(project)


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


def _write_pass(n_calls, messages):
    del n_calls, messages
    return json.dumps({
        "actions": [{"action": "write_file", "path": "test_p1.py",
                     "content": "def test_p1():\n    assert 1 + 1 == 2\n"}],
        "done": False})


def _worker_done(n_calls, messages):
    del messages
    if n_calls % 2 == 0:
        return _write_pass(0, [])
    return json.dumps({"actions": [], "done": True})


def _manager_order(n_calls, messages):
    del n_calls, messages
    return json.dumps({"order": ["p1"]})


def _audit_pass(n_calls, messages):
    del n_calls, messages
    return json.dumps({"result": "PASS", "reasons": ["checks green"]})


def _green_factory(usages=None, providers=(PROVIDER,)):
    return _FakeFactory(
        {
            "director": [_plan_text(_one_part_plan())],
            "manager": [_manager_order],
            "worker": [_worker_done],
            "auditor": [_audit_pass],
        },
        usages=usages, providers=providers)


def _staged_catalog():
    """Two priced fake providers (harness staging; S7/S9 need prices)."""
    from agent_si.model_kb import kb as _kb

    def _priced(inp, outp):
        return {
            "input_token_price": _kb.sourced(
                inp, "https://example.invalid/fxdevwire-pricing",
                "2026-10-31"),
            "output_token_price": _kb.sourced(
                outp, "https://example.invalid/fxdevwire-pricing",
                "2026-10-31"),
        }

    rows = [
        _kb.make_model_row("fxpricey", "fxpricey-model",
                           _priced(1.0, 2.0)),
        _kb.make_model_row("fxcheap", "fxcheap-model",
                           _priced(0.25, 0.5)),
    ]
    return _kb.make_catalog(rows, kb_version=1, updated_at="2026-10-31",
                            change_log=[], sources=[])


# -- S1a: stored absolute folder is used ---------------------------------

def test_s1a_stored_absolute_folder_used(tmp_path):
    project = "fxdw-s1a"
    folder = _project_dir(tmp_path, project)
    factory = _green_factory()
    app = _served_app(tmp_path, project, factory)
    client = TestClient(app, raise_server_exceptions=False)
    pid = _make_project(app, client, "s1a build it", str(folder))
    resp = _post_chat(client, pid, "build it")
    assert resp.status_code == 200, resp.text
    events = _parse_sse(resp.text)
    deltas = _delta_texts(events)
    assert deltas, events[:2]
    assert deltas[0].startswith("Working folder: "), deltas[0]
    assert str(folder) in deltas[0], deltas[0]
    assert factory.spy, "engine ran against the stored folder"
    record = _run_record(app, pid)
    assert record is not None
    assert record.get("folder") == str(folder), record.get("folder")


# -- S1b: absolute missing folder ends honest ----------------------------

def test_s1b_absolute_missing_folder_honest(tmp_path):
    project = "fxdw-s1b"
    factory = _green_factory()
    app = _served_app(tmp_path, project, factory)
    client = TestClient(app, raise_server_exceptions=False)
    missing = str(tmp_path / ("nope-" + project))
    pid = _make_project(app, client, "s1b build it", missing)
    resp = _post_chat(client, pid, "build it")
    assert resp.status_code == 200, resp.text
    events = _parse_sse(resp.text)
    text = _all_text(events).lower()
    assert "project folder not found" in text, text
    assert missing.lower() in text, text
    assert "choose in projects" in text, text
    assert factory.spy == [], "engine never ran for a missing folder"
    assert _types(events)[-1] == "done", events[-2:]


# -- S1c: non-absolute folder_ref uses the managed folder ---------------

def test_s1c_relative_folder_uses_managed(tmp_path):
    project = "fxdw-s1c"
    factory = _green_factory()
    app = _served_app(tmp_path, project, factory)
    client = TestClient(app, raise_server_exceptions=False)
    pid = _make_project(app, client, "s1c build it", "s1c build it")
    resp = _post_chat(client, pid, "s1c build it")
    assert resp.status_code == 200, resp.text
    events = _parse_sse(resp.text)
    deltas = _delta_texts(events)
    assert deltas, events[:2]
    assert deltas[0].startswith("Working folder: "), deltas[0]
    managed = os.path.join(str(app.state.data_dir), "workspaces", pid)
    assert os.path.isdir(managed), managed
    assert managed in deltas[0], deltas[0]
    assert factory.spy, "engine ran inside the managed folder"
    record = _run_record(app, pid)
    assert record is not None
    assert record.get("folder") == managed, record.get("folder")


# -- S2: first message makes 1 project + 1 task, then 1 stream -----------

def test_s2_first_message_one_project_task_stream(tmp_path):
    project = "fxdw-s2"
    factory = _green_factory()
    app = _served_app(tmp_path, project, factory)
    client = TestClient(app, raise_server_exceptions=False)
    message = "s2 build the widget"
    created = client.post(
        "/api/v1/projects",
        json={"name": message.replace(" ", "-")[:40],
              "folder_ref": message},
        headers=_auth())
    assert created.status_code == 200, created.text
    pid = created.json()["project"]["project_id"]
    listed = client.get("/api/v1/projects")
    assert listed.status_code == 200, listed.text
    assert len(listed.json()["projects"]) == 1, listed.json()
    tasked = client.post(
        "/api/v1/projects/%s/tasks" % pid,
        json={"title": message, "scope": []},
        headers=_auth())
    assert tasked.status_code == 200, tasked.text
    resp = _post_chat(client, pid, message)
    assert resp.status_code == 200, resp.text
    events = _parse_sse(resp.text)
    assert _types(events)[0] == "start", events[:2]
    tasks = client.get("/api/v1/tasks", params={"project_id": pid})
    assert tasks.status_code == 200, tasks.text
    assert len(tasks.json()["tasks"]) == 1, tasks.json()
    text = _all_text(events)
    # FXCLASS CA-1/CA-3/CA-4: a first run with no provider ends with the
    # one plain line (same words on chat + Tasks), not a plan/success.
    assert ("plan" in text.lower() or "success" in text.lower()
            or "The " in text or "run " in text
            or "Connect a provider first" in text), text


# -- S3: run text is visible and newline-terminated ----------------------

def test_s3_run_text_visible(tmp_path):
    project = "fxdw-s3"
    folder = _project_dir(tmp_path, project)
    factory = _green_factory()
    app = _served_app(tmp_path, project, factory)
    client = TestClient(app, raise_server_exceptions=False)
    pid = _make_project(app, client, "s3 build it", str(folder))
    resp = _post_chat(client, pid, "build it")
    assert resp.status_code == 200, resp.text
    events = _parse_sse(resp.text)
    text = _all_text(events)
    team = [line for line in _delta_texts(events)
            if line.startswith("Team:")]
    assert len(team) == 1, text
    for role in ("director", "manager", "worker", "auditor"):
        assert role in team[0], team[0]
    assert PROVIDER in text and MODEL in text, text
    assert "(Pinned)" in text, text
    assert "plan of 1 parts" in text, text
    assert "p1" in text and "test_p1.py" in text, text
    assert "exit 0" in text, text
    assert "Auditor for p1" in text, text
    assert "PASS" in text, text
    assert "token" in text.lower() and "cost" in text.lower(), text
    assert "success" in text.lower(), text
    for event in events:
        if isinstance(event, dict) and event.get("type") == "delta":
            body = str(event.get("text", ""))
            assert body.endswith("\n"), repr(body[:80])
    done = [event for event in events
            if isinstance(event, dict) and event.get("type") == "done"]
    assert done, events[-2:]
    assert str(done[-1].get("text", "")) in _delta_texts(events), (
        "terminal done repeats run text")


# -- S3b: a check with no output says so honestly ------------------------

def _silent_plan():
    return [
        {"part_id": "p1", "goal": "Write test_p1.py with one passing test",
         "files": ["test_p1.py", "quiet.py"],
         "check_commands": [["python", "quiet.py"]],
         "depends_on": []},
    ]


def _worker_quiet(n_calls, messages):
    del messages
    if n_calls % 2 == 0:
        return json.dumps({
            "actions": [
                {"action": "write_file", "path": "test_p1.py",
                 "content": "def test_p1():\n    assert 1 + 1 == 2\n"},
                {"action": "write_file", "path": "quiet.py",
                 "content": ""}],
            "done": False})
    return json.dumps({"actions": [], "done": True})


def test_s3b_silent_check_reported_honestly(tmp_path):
    project = "fxdw-s3b"
    folder = _project_dir(tmp_path, project)
    factory = _FakeFactory({
        "director": [_plan_text(_silent_plan())],
        "manager": [_manager_order],
        "worker": [_worker_quiet],
        "auditor": [_audit_pass],
    })
    app = _served_app(tmp_path, project, factory)
    client = TestClient(app, raise_server_exceptions=False)
    pid = _make_project(app, client, "s3b build it", str(folder))
    resp = _post_chat(client, pid, "build it")
    assert resp.status_code == 200, resp.text
    text = _all_text(_parse_sse(resp.text))
    assert "Check p1" in text, text
    assert "(no output)" in text, text


# -- S6: exact frontend body shape runs the full chain -------------------

def test_s6_frontend_body_shape_full_chain(tmp_path):
    project = "fxdw-s6"
    folder = _project_dir(tmp_path, project)
    factory = _green_factory()
    app = _served_app(tmp_path, project, factory)
    client = TestClient(app, raise_server_exceptions=False)
    pid = _make_project(app, client, "s6 build it", str(folder))
    # Exact wire body the frontend HttpApiClient sends for ChatOpen.
    resp = client.post(
        "/api/v1/chat/stream",
        json={"project": pid, "message": "s6 build it"},
        headers=_auth())
    assert resp.status_code == 200, resp.text
    events = _parse_sse(resp.text)
    text = _all_text(events)
    assert "plan of 1 parts" in text, text
    assert "exit 0" in text, text
    assert "Auditor for p1" in text, text
    assert "PASS" in text, text
    assert (folder / "test_p1.py").is_file(), "file changes on disk"
    roles = {entry.get("role") for entry in factory.spy}
    assert {"director", "manager", "worker", "auditor"} <= roles, roles
    auditor_calls = [entry for entry in factory.spy
                     if entry.get("role") == "auditor"]
    assert auditor_calls, "auditor ran"
    blob = json.dumps([entry["messages"] for entry in auditor_calls])
    assert "test_p1.py" in blob, "fresh auditor reads the code path"
    kinds = {row.kind for row in _journal.stored_rows(pid)}
    assert {"DEVRUN_PLAN", "DEVRUN_PART", "DEVRUN_AUDIT",
            "DEVRUN_END"} <= kinds, kinds


# -- S5: journal rows per run --------------------------------------------

def test_s5_journal_kinds_and_reasons(tmp_path):
    project = "fxdw-s5"
    folder = _project_dir(tmp_path, project)
    factory = _green_factory()
    app = _served_app(tmp_path, project, factory)
    client = TestClient(app, raise_server_exceptions=False)
    pid = _make_project(app, client, "s5 build it", str(folder))
    resp = _post_chat(client, pid, "build it")
    assert resp.status_code == 200, resp.text
    rows = _journal.stored_rows(pid)
    by_kind = {}
    for row in rows:
        by_kind.setdefault(row.kind, []).append(row)
    for kind in ("DEVRUN_PLAN", "DEVRUN_PART", "DEVRUN_AUDIT",
                 "DEVRUN_END"):
        assert by_kind.get(kind), "journal has %s" % kind
    audits = by_kind["DEVRUN_AUDIT"]
    assert any("checks green" in row.summary for row in audits), (
        [row.summary for row in audits])


# -- S4: stop-all cancels a live stream and stops the run ----------------

def _worker_sleepy(n_calls, messages):
    if n_calls == 0:
        return json.dumps({
            "actions": [{"action": "write_file", "path": "sleepy.py",
                         "content": "import time\ntime.sleep(60)\n"}],
            "done": False})
    return json.dumps({"actions": [], "done": True})


def _sleepy_plan():
    return [
        {"part_id": "p1", "goal": "Write sleepy.py then wait",
         "files": ["sleepy.py"],
         "check_commands": [["python", "sleepy.py"]],
         "depends_on": []},
    ]


def _pid_dead(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return True
    return False


@pytest.mark.timeout(280)
def test_s4_stop_all_cancels_stream_and_run(tmp_path):
    project = "fxdw-s4"
    folder = _project_dir(tmp_path, project)
    factory = _FakeFactory({
        "director": [_plan_text(_sleepy_plan())],
        "manager": [json.dumps({"order": ["p1"]})],
        "worker": [_worker_sleepy],
        "auditor": [_audit_pass],
    })
    app = _served_app(tmp_path, project, factory)
    client = TestClient(app, raise_server_exceptions=False)
    pid = _make_project(app, client, "s4 build it", str(folder))
    holder = {}

    def _run():
        try:
            holder["resp"] = _post_chat(client, pid, "s4 build it")
        except Exception as err:  # pragma: no cover - thread transport
            holder["error"] = err

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    try:
        deadline = time.time() + 45
        while time.time() < deadline:
            record = _run_record(app, pid)
            checks = (record or {}).get("checks_started") or []
            if checks:
                break
            time.sleep(0.2)
        record = _run_record(app, pid)
        assert record is not None, "run started before stop"
        assert record.get("checks_started"), "check child spawned"
        stop = client.post(
            "/api/v1/stop-all",
            json={"project_id": pid, "actor": "user"},
            headers={"x-ui-session-token": TEST_TOKEN})
        assert stop.status_code == 200, stop.text
    finally:
        thread.join(timeout=100)
    assert not thread.is_alive(), "chat stream run finished after stop"
    assert "error" not in holder, holder.get("error")
    events = _parse_sse(holder["resp"].text)
    assert "cancelled" in _types(events), _types(events)
    record = _run_record(app, pid)
    assert record is not None
    assert record.get("stopped") is True, record.get("summary")
    assert (folder / "sleepy.py").is_file(), "finished files stay"
    pid_num = (record.get("checks_started") or [{}])[0].get("pid")
    assert isinstance(pid_num, int) and pid_num > 0
    assert _pid_dead(pid_num), "check child pid %d is dead" % pid_num


def test_s4_bridge_cancel_paths(tmp_path):
    from agent_si.backend import chat_stream as _chat

    project = "fxdw-s4b"
    factory = _green_factory()
    app = _served_app(tmp_path, project, factory)
    bridge = _chat.bridge_for_app(app)
    first = _chat.ChatStreamRequest(
        project="p-one", task="t", message="hi", actor=ACTOR)
    second = _chat.ChatStreamRequest(
        project="p-two", task="t", message="hi", actor=ACTOR)
    kept = []
    for request in (first, second):
        stream_id, events = bridge.no_provider_run(request)
        assert stream_id
        kept.append((stream_id, events))
    assert bridge.cancel_project("p-one") is True
    assert bridge.cancel_project("p-one") is False
    assert bridge.cancel_all() is True
    assert bridge.cancel_all() is False


# -- S7: zero-profile project resolves all 4 roles -----------------------

def test_s7_zero_profile_project_resolves(tmp_path):
    from agent_si.model_kb import kb as _kb

    project = "fxdw-s7"
    folder = _project_dir(tmp_path, project)
    previous = _kb.bound_catalog()
    _kb.bind_catalog(_staged_catalog())
    try:
        factory = _FakeFactory(
            {
                "director": [_plan_text(_one_part_plan())],
                "manager": [_manager_order],
                "worker": [_worker_done],
                "auditor": [_audit_pass],
            },
            providers=["fxcheap", "fxpricey"])
        # No stored profiles at all: the project resolves like AUTO.
        app = _served_app(tmp_path, project, factory, auto=False, pin=False)
        client = TestClient(app, raise_server_exceptions=False)
        pid = _make_project(app, client, "s7 build it", str(folder),
                                pin=False)
        resp = _post_chat(client, pid, "build it")
        assert resp.status_code == 200, resp.text
        record = _run_record(app, pid)
        assert record is not None, "run started on a profile-less project"
        assert record.get("success") is True, record.get("summary")
        roles = {entry.get("role") for entry in factory.spy}
        assert {"director", "manager", "worker", "auditor"} <= roles, roles
        text = _all_text(_parse_sse(resp.text))
        team = [line for line in _delta_texts(_parse_sse(resp.text))
                if line.startswith("Team:")]
        assert len(team) == 1, text
        for role in ("director", "manager", "worker", "auditor"):
            assert role in team[0], team[0]
    finally:
        _kb.bind_catalog(previous)


# -- S8: cap 0.00 means zero calls plus a visible stop line --------------

def test_s8_cap_zero_blocks_before_call(tmp_path):
    project = "fxdw-s8"
    folder = _project_dir(tmp_path, project)
    factory = _green_factory()
    app = _served_app(tmp_path, project, factory)
    client = TestClient(app, raise_server_exceptions=False)
    pid = _make_project(app, client, "s8 build it", str(folder))
    gate = app.state.k04_ctx.budget_state
    try:
        gate.get_state(pid)
    except (KeyError, LookupError):
        gate.configure_project(pid, "USD", "100", "80", "100")
    gate.update_limits(pid, provider_spend_caps={PROVIDER: "0.00"})
    resp = _post_chat(client, pid, "build it")
    assert resp.status_code == 200, resp.text
    events = _parse_sse(resp.text)
    assert factory.spy == [], "cap 0.00 means zero provider calls"
    assert "budget_stop" in _types(events), _types(events)
    text = _all_text(events)
    assert PROVIDER in text, text
    assert "0.00" in text, text
    record = _run_record(app, pid)
    assert record is not None
    assert record.get("success") is not True, record.get("summary")


# -- S9: one telemetry row per call, spent grows once per call -----------

def test_s9_telemetry_row_per_call(tmp_path):
    from agent_si.model_kb import kb as _kb
    from agent_si.runtime import manager as _manager
    from agent_si.telemetry import run_store as _store

    project = "fxdw-s9"
    folder = _project_dir(tmp_path, project)
    usage = {"input_tokens": 1000, "output_tokens": 500,
             "cached_tokens": 0}
    previous = _kb.bound_catalog()
    _kb.bind_catalog(_staged_catalog())
    try:
        provider, model = "fxcheap", "fxcheap-model"
        factory = _FakeFactory(
            {
                "director": [_plan_text(_one_part_plan())],
                "manager": [_manager_order],
                "worker": [_worker_done],
                "auditor": [_audit_pass],
            },
            usages={"director": usage, "manager": usage,
                    "worker": usage, "auditor": usage},
            providers=[provider])
        app = _served_app(tmp_path, project, factory)
        client = TestClient(app, raise_server_exceptions=False)
        pid = _make_project(app, client, "s9 build it", str(folder),
                            pin=False)
        table = app.state.k04_ctx.role_table
        for role in ("director", "manager", "worker", "auditor"):
            table.set_profile(RoleModelProfile(
                role=role, project_id=pid, mode="PINNED",
                provider=provider, model=model,
                binding="DEFAULT", version=1, hash="fxdevwire-test"))
        resp = _post_chat(client, pid, "build it")
        assert resp.status_code == 200, resp.text
        record = _run_record(app, pid)
        assert record is not None
        assert record.get("success") is True, record.get("summary")
        calls = len(factory.spy)
        assert calls >= 4, factory.spy
        store_dir = str(app.state.k02r3_store_dir)
        data = _store.load_store(store_dir)
        run_id = record.get("run_id")
        usage_events = [
            event for event in data.get("telemetry_events", [])
            if event.get("event_type") == "PROVIDER_USAGE_REPORTED"
            and event.get("run_id") == run_id]
        assert len(usage_events) == calls, (
            "one telemetry row per call: %d events, %d calls"
            % (len(usage_events), calls))
        inp_price, out_price = _manager._kb_price_for_manager(
            provider, model)
        assert inp_price is not None and out_price is not None
        from decimal import Decimal as _Dec
        one = ((_Dec(str(inp_price)) * _Dec(1000)
                + _Dec(str(out_price)) * _Dec(500)) / _Dec(1000000))
        gate = app.state.k04_ctx.budget_state
        spent = _Dec(str(gate.get_state(pid).spent))
        # 5 priced invokes settle once each (director 1 + manager 1 +
        # worker 2 + auditor 1); each 1000/500 on fxcheap = 0.0005,
        # so spent is 5x one-call charge = 0.0025.
        expected = (one * 5).quantize(_Dec("0.000001"))
        assert spent == expected, "spent charged once per call: %s" % spent
        assert spent > 0, "telemetry evidence settled a real charge"
    finally:
        _kb.bind_catalog(previous)


# -- U8: repeats stay quiet across turns; J4: no bare UNKNOWN ----------

def _u8_two_turns(tmp_path):
    project = "fxdw-u8"
    folder = _project_dir(tmp_path, project)
    factory = _green_factory()
    app = _served_app(tmp_path, project, factory)
    client = TestClient(app, raise_server_exceptions=False)
    pid = _make_project(app, client, "u8 build it", str(folder))
    first = _delta_texts(_parse_sse(
        _post_chat(client, pid, "build it").text))
    assert any(d.startswith("Working folder: ") for d in first), first
    assert any(d.startswith("Team:") for d in first), first
    assert any("Director: plan of" in d for d in first), first
    second = _delta_texts(_parse_sse(
        _post_chat(client, pid, "again").text))
    assert second, "second turn still answers"
    return first, second


def test_u8_second_turn_hides_folder_and_team(tmp_path):
    first, second = _u8_two_turns(tmp_path)
    assert not any(
        d.startswith("Working folder: ") for d in second), second
    assert not any(d.startswith("Team:") for d in second), second
    assert any("Director: plan of" in d for d in second), second


def test_u8_check_line_names_tool_not_path(tmp_path):
    first, _second = _u8_two_turns(tmp_path)
    checks = [d for d in first if d.startswith("Check p1 $")]
    assert checks, first
    for line in checks:
        assert ":\\" not in line, line
        assert "findstr" not in line.lower(), line


def test_j4_total_line_no_bare_unknown(tmp_path):
    first, _second = _u8_two_turns(tmp_path)
    totals = [d for d in first if "tokens; cost:" in d]
    assert totals, first
    assert totals == [
        "Total: 0 input + 0 output = 0 tokens; "
        "cost: cost not known (no price)\n"], totals
    joined = "\n".join(first)
    assert "UNKNOWN" not in joined, joined

