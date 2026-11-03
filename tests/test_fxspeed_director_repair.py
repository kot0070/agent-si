"""FXRUNSPEED S2: director syntax repair without a model call.

Unit: trailing commas, code fences and missing closers parse through
the one bounded repair; a reply with no object still raises PlanError.
Served: a trailing-comma plan runs with ONE director call (no repair
call); a no-object reply still re-asks (two director calls) and the
journal carries one reason-only line, never the model text.
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
from agent_si.runtime.devrun import protocol as _protocol  # noqa: E402
from agent_si.watcher import journal as _journal_store  # noqa: E402

TEST_TOKEN = "fxs2-served-token"
ACTOR = "fxs2-tester"
PROVIDER = "mock"
MODEL = "mock-canned"


def _auth(token=TEST_TOKEN, actor=ACTOR):
    return {"x-actor": actor, "x-ui-session-token": token}


def _settings(store_dir):
    return {"testing": True, "ui_session_token": TEST_TOKEN,
            "store_dir": str(store_dir)}


def _apply_limits(project_id):
    outcome = _steplimits.apply_steplimit_config_change({
        "project_id": project_id, "authority": "fxs2-test",
        "reason": "fxs2 served run needs step budgets",
        "task_max_steps": 10, "chat_max_steps": 10})
    assert outcome.applied, outcome.reason


def setup_function(_func):
    agents_live.clear_live_rows()
    _steplimits._reset_state()


def teardown_function(_func):
    agents_live.clear_live_rows()
    _steplimits._reset_state()


class _ScriptedAdapter(MockProviderAdapter):
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
        self.spy.append({"adapter_id": id(self), "role": self.role,
                         "provider": self.config.provider_id,
                         "model": request["model"],
                         "messages": copy.deepcopy(messages)})
        return AdapterResponse(
            provider_id=self.config.provider_id,
            instance_id=self.config.instance_id,
            model=request["model"], output_text=text,
            finish_reason="stop",
            usage=dict(self.forced_usage)
            if self.forced_usage is not None else dict(MOCK_USAGE),
            mock=True, error_ref=None)


class _FakeFactory:
    def __init__(self, scripts):
        self.scripts = dict(scripts)
        self.spy = []

    def connected_providers(self):
        return [PROVIDER]

    def __call__(self, *, role, provider, model):
        config = AdapterConfig(
            provider_id=provider, instance_id="fxs2-%s" % role,
            model=model,
            secret_ref=make_secret_ref(
                secret_id="mock-secret", provider_id=provider))
        return _ScriptedAdapter(config, role, self.scripts[role], self.spy)


def _pin_all(app, project):
    table = app.state.k04_ctx.role_table
    for role in ("director", "manager", "worker", "auditor"):
        table.set_profile(RoleModelProfile(
            role=role, project_id=project, mode="PINNED",
            provider=PROVIDER, model=MODEL,
            binding="DEFAULT", version=1, hash="fxs2-test"))
    return table


def _served_app(tmp_path, project, factory):
    agents_live.clear_live_rows()
    _steplimits._reset_state()
    _apply_limits(project)
    store = tmp_path / ("store-" + project)
    store.mkdir(parents=True, exist_ok=True)
    app = create_app(_settings(store))
    _pin_all(app, project)
    app.state.chat_provider_adapter = MockProviderAdapter(
        AdapterConfig(
            provider_id=PROVIDER, instance_id="fxs2-bound",
            model=MODEL,
            secret_ref=make_secret_ref(
                secret_id="mock-secret", provider_id=PROVIDER)),
        transport=None, canned=("bound standby",))
    app.state.devrun_adapter_factory = factory
    return app


def _project_dir(tmp_path, project):
    folder = tmp_path / ("proj-" + project)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


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


_CHECK = ["python", "-m", "pytest", "test_note.py",
           "-q", "-p", "no:cacheprovider"]
_PASS_TEST = "def test_note():\n    assert 1 + 1 == 2\n"


def _one_part_plan():
    return [{"part_id": "p1", "goal": "write test_note.py",
             "files": ["test_note.py"],
             "check_commands": [_CHECK],
             "depends_on": []}]


def _worker_write_then_done(n_calls, messages):
    if n_calls == 0:
        return json.dumps({
            "actions": [{"action": "write_file", "path": "test_note.py",
                         "content": _PASS_TEST}],
            "done": False})
    return json.dumps({"actions": [], "done": True})


def _manager_order(messages):
    return json.dumps({"order": ["p1"]})


def _audit_pass(n_calls, messages):
    return json.dumps({"result": "PASS", "reasons": ["checks green"]})


def _run(tmp_path, project, director_script):
    folder = _project_dir(tmp_path, project)
    factory = _FakeFactory({
        "director": director_script,
        "manager": [_manager_order],
        "worker": [_worker_write_then_done],
        "auditor": [_audit_pass],
    })
    app = _served_app(tmp_path, project, factory)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/api/v1/chat/stream",
        json={"project": project, "folder": str(folder),
              "task": "task-%s" % project,
              "message": "write the note file"},
        headers=_auth())
    assert resp.status_code == 200, resp.text
    events = _parse_sse(resp.text)
    record = (getattr(app.state, "devrun_runs", None) or {}).get(project)
    return events, record, factory, folder


def _director_calls(factory):
    return [entry for entry in factory.spy if entry.get("role") == "director"]


# -- unit: the bounded repair -------------------------------------------

def test_trailing_comma_parses():
    raw = ('{"parts": [{"part_id": "p1", "goal": "g", '
           '"files": ["a.md",], "check_commands": [], '
           '"depends_on": [],},]}')
    parsed = _protocol.parse_director_reply(raw)
    assert [part["part_id"] for part in parsed["parts"]] == ["p1"]


def test_fence_parses():
    raw = ('```json\n{"answer": "done"}\n```')
    assert _protocol.parse_director_reply(raw) == {"answer": "done"}


def test_missing_closer_parses():
    raw = ('{"parts": [{"part_id": "p1", "goal": "g", '
           '"files": ["a.md"], "check_commands": [], '
           '"depends_on": []}]')
    parsed = _protocol.parse_director_reply(raw)
    assert [part["part_id"] for part in parsed["parts"]] == ["p1"]


def test_no_object_still_raises_plan_error():
    try:
        _protocol.parse_director_reply(
            "thinking out loud, no object at all")
    except _protocol.PlanError as exc:
        assert "not JSON" in str(exc), exc
    else:
        raise AssertionError("no-object reply must still raise PlanError")


def test_validation_failure_still_raises():
    raw = json.dumps({"parts": [{"part_id": "p1", "goal": "g",
                                  "files": ["../evil.txt"],
                                  "check_commands": [],
                                  "depends_on": []}]})
    try:
        _protocol.parse_director_reply(raw)
    except _protocol.PlanError as exc:
        assert "outside the project folder" in str(exc), exc
    else:
        raise AssertionError("bad validation must still raise PlanError")


# -- served: no second call / still re-asks -----------------------------

def test_trailing_comma_needs_no_second_call(tmp_path):
    project = "fxs2-t1"
    raw = ('{"parts": [{"part_id": "p1", "goal": "write test_note.py", '
           '"files": ["test_note.py",], '
           '"check_commands": [["python", "-m", "pytest", "test_note.py", '
           '"-q", "-p", "no:cacheprovider",],], '
           '"depends_on": [],},]}')
    events, record, factory, folder = _run(tmp_path, project, [raw])
    assert record is not None
    assert record.get("success") is True, record.get("summary")
    assert "success" in _all_text(events).lower()
    assert (folder / "test_note.py").is_file()
    assert len(_director_calls(factory)) == 1, factory.spy


def test_no_object_still_reasks_with_reason_only(tmp_path):
    project = "fxs2-t2"
    garbage = "thinking out loud, no object at all, fxs2-marker-zz9"
    events, record, factory, folder = _run(
        tmp_path, project, [garbage, json.dumps({"parts": _one_part_plan()})])
    assert record is not None
    assert record.get("success") is True, record.get("summary")
    assert (folder / "test_note.py").is_file()
    assert len(_director_calls(factory)) == 2, factory.spy
    repairs = [row for row in
               _journal_store.stored_rows(project, "DEVRUN_PLAN")
               if "re-ask" in (row.summary or "")]
    assert repairs, "one journal line with the re-ask reason"
    for row in repairs:
        assert "fxs2-marker-zz9" not in (row.summary or ""), row.summary
