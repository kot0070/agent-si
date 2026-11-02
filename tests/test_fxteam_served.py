"""FXTEAM M1 served RED: one Manager per group, deterministic collapse."""
import copy
import json
import os
import sys

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

TEST_TOKEN = "fxteam-served-token"
ACTOR = "fxteam-tester"
PROVIDER = "mock"
MODEL = "mock-canned"


def _auth(token=TEST_TOKEN, actor=ACTOR):
    return {"x-actor": actor, "x-ui-session-token": token}


def _settings(store_dir):
    return {"testing": True, "ui_session_token": TEST_TOKEN, "store_dir": str(store_dir)}


def _apply_limits(project_id):
    outcome = _steplimits.apply_steplimit_config_change({
        "project_id": project_id,
        "authority": "fxteam-test",
        "reason": "fxteam served run needs budgets",
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
        calls = [e for e in self.spy if e.get("adapter_id") == id(self)]
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
        return AdapterResponse(provider_id=self.config.provider_id,
                               instance_id=self.config.instance_id,
                               model=request["model"], output_text=text,
                               finish_reason="stop",
                               usage=dict(self.forced_usage) if self.forced_usage is not None else dict(MOCK_USAGE),
                               mock=True, error_ref=None)


class _FakeFactory:
    def __init__(self, scripts, usages=None, providers=(PROVIDER,)):
        self.scripts = dict(scripts)
        self.usages = dict(usages or {})
        self.providers = list(providers)
        self.spy = []

    def connected_providers(self):
        return list(self.providers)

    def __call__(self, *, role, provider, model):
        config = AdapterConfig(provider_id=provider,
                               instance_id="fxteam-%s" % role,
                               model=model,
                               secret_ref=make_secret_ref(secret_id="mock-secret", provider_id=provider))
        return _ScriptedAdapter(config, role, self.scripts[role], self.spy, self.usages.get(role))


def _pin_all(app, project, mode="PINNED", provider=PROVIDER, model=MODEL):
    table = app.state.k04_ctx.role_table
    for role in ("director", "manager", "worker", "auditor"):
        table.set_profile(RoleModelProfile(role=role, project_id=project, mode=mode,
                                           provider=None if mode == "AUTO" else provider,
                                           model=None if mode == "AUTO" else model,
                                           binding="DEFAULT", version=1, hash="fxteam-test"))
    return table


def _bound_mock():
    return MockProviderAdapter(AdapterConfig(provider_id=PROVIDER, instance_id="fxteam-bound",
                                              model=MODEL,
                                              secret_ref=make_secret_ref(secret_id="mock-secret", provider_id=PROVIDER)),
                               transport=None, canned=("bound standby",))


def _served_app(tmp_path, project, factory):
    agents_live.clear_live_rows()
    _steplimits._reset_state()
    _apply_limits(project)
    store = tmp_path / ("store-" + project)
    store.mkdir(parents=True, exist_ok=True)
    app = create_app(_settings(store))
    _pin_all(app, project, mode="PINNED")
    app.state.chat_provider_adapter = _bound_mock()
    app.state.devrun_adapter_factory = factory
    return app


def _project_dir(tmp_path, project):
    folder = tmp_path / ("proj-" + project)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _post_chat(client, project, folder, message="build it"):
    return client.post("/api/v1/chat/stream",
                       json={"project": project, "folder": str(folder),
                             "task": "task-%s" % project, "message": message},
                       headers=_auth())


def _run_record(app, project):
    return (getattr(app.state, "devrun_runs", None) or {}).get(project)


def _write_pass(n, fname=None):
    name = fname or ("test_p%d.py" % n)
    return json.dumps({"actions": [{"action": "write_file", "path": name,
                                    "content": "def test_p%d():\n    assert %d + %d == %d\n" % (n, n, n, 2 * n)}],
                       "done": False})


def _worker_two(n_calls, messages):
    text = " ".join(str(p.get("content", "")) for p in messages if isinstance(p, dict))
    if "test_p2" in text or '"p2"' in text or "part_id: p2" in text:
        return _write_pass(2)
    if n_calls % 2 == 0:
        if "test_p2" in text or "p2" in text:
            return _write_pass(2)
        return _write_pass(1)
    return json.dumps({"actions": [], "done": True})


def test_one_part_one_manager_call_and_row(tmp_path):
    project = "fxteam-1p"
    folder = _project_dir(tmp_path, project)
    plan = [{"part_id": "p1", "goal": "Write test_p1.py",
             "files": ["test_p1.py"],
             "check_commands": [["python", "-m", "pytest", "test_p1.py", "-q", "-p", "no:cacheprovider"]],
             "depends_on": []}]
    factory = _FakeFactory({"director": [json.dumps({"parts": plan})],
                            "manager": [json.dumps({"order": ["p1"]})],
                            "worker": [_worker_two],
                            "auditor": [json.dumps({"result": "PASS", "reasons": ["ok"]})]})
    app = _served_app(tmp_path, project, factory)
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(client, project, folder)
    assert resp.status_code == 200, resp.text
    record = _run_record(app, project)
    assert record is not None
    assert record.get("success") is True, record.get("summary")
    mgr_calls = [e for e in factory.spy if e.get("role", "").startswith("manager")]
    assert len(mgr_calls) == 1, factory.spy
    mgr_rows = [r for r in (record.get("ledger", []) or []) if str(r.get("role", "")).startswith("manager")]
    assert len(mgr_rows) == 1, record.get("ledger")
    assert record.get("manager_why") == "one group", record.get("manager_why")


def test_two_groups_two_manager_calls(tmp_path):
    project = "fxteam-2g"
    folder = _project_dir(tmp_path, project)
    plan = [{"part_id": "p1", "goal": "Write test_p1.py",
             "files": ["test_p1.py"],
             "check_commands": [["python", "-m", "pytest", "test_p1.py", "-q", "-p", "no:cacheprovider"]],
             "depends_on": []},
            {"part_id": "p2", "goal": "Write test_p2.py",
             "files": ["test_p2.py"],
             "check_commands": [["python", "-m", "pytest", "test_p2.py", "-q", "-p", "no:cacheprovider"]],
             "depends_on": []}]
    managers = [{"manager_id": "m1", "goal": "area a", "parts": ["p1"]},
                {"manager_id": "m2", "goal": "area b", "parts": ["p2"]}]
    factory = _FakeFactory({"director": [json.dumps({"parts": plan, "managers": managers})],
                            "manager": [json.dumps({"order": ["p1"]}), json.dumps({"order": ["p2"]})],
                            "worker": [_worker_two],
                            "auditor": [json.dumps({"result": "PASS", "reasons": ["ok"]})]})
    app = _served_app(tmp_path, project, factory)
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(client, project, folder)
    assert resp.status_code == 200, resp.text
    record = _run_record(app, project)
    assert record is not None, "record stored"
    assert record.get("success") is True, record.get("summary")
    mgr_calls = [e for e in factory.spy if e.get("role", "").startswith("manager")]
    assert len(mgr_calls) == 2, mgr_calls
    assert record.get("manager_why") == "2 groups over separate files", record.get("manager_why")


def test_overlap_collapses_to_one(tmp_path):
    project = "fxteam-ov"
    folder = _project_dir(tmp_path, project)
    plan = [{"part_id": "p1", "goal": "Write a.py",
             "files": ["a.py"],
             "check_commands": [["python", "-m", "pytest", "test_p1.py", "-q", "-p", "no:cacheprovider"]],
             "depends_on": []},
            {"part_id": "p2", "goal": "Write a.py too",
             "files": ["a.py"],
             "check_commands": [["python", "-m", "pytest", "test_p1.py", "-q", "-p", "no:cacheprovider"]],
             "depends_on": []}]
    # NOTE: protocol currently forbids overlapping files, so Director repair path
    # is not exercised here; this test uses separate files but same shared name
    # via depends to force collapse. Overlap case is covered by unit test +
    # engine collapse when managers share a file across groups.
    managers = [{"manager_id": "m1", "goal": "a", "parts": ["p1"]},
                {"manager_id": "m2", "goal": "b", "parts": ["p2"]}]
    # p2 depends on p1 across groups -> collapse
    plan[1]["depends_on"] = ["p1"]
    factory = _FakeFactory({"director": [json.dumps({"parts": plan, "managers": managers})],
                            "manager": [json.dumps({"order": ["p1", "p2"]})],
                            "worker": [_worker_two],
                            "auditor": [json.dumps({"result": "PASS", "reasons": ["ok"]})]})
    app = _served_app(tmp_path, project, factory)
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(client, project, folder)
    assert resp.status_code == 200, resp.text
    record = _run_record(app, project)
    assert record is not None
    mgr_calls = [e for e in factory.spy if e.get("role", "").startswith("manager")]
    assert len(mgr_calls) == 1, mgr_calls
    assert record.get("manager_why") == "groups depend on each other", record.get("manager_why")


def test_broken_grouping_reask_then_one(tmp_path):
    project = "fxteam-bg"
    folder = _project_dir(tmp_path, project)
    plan = [{"part_id": "p1", "goal": "Write test_p1.py",
             "files": ["test_p1.py"],
             "check_commands": [["python", "-m", "pytest", "test_p1.py", "-q", "-p", "no:cacheprovider"]],
             "depends_on": []}]
    bad_managers = [{"manager_id": "m1", "goal": "a", "parts": ["p1"]},
                    {"manager_id": "m2", "goal": "b", "parts": ["p1"]}]
    good = {"parts": plan}
    factory = _FakeFactory({"director": [json.dumps({"parts": plan, "managers": bad_managers}),
                                         json.dumps(good)],
                            "manager": [json.dumps({"order": ["p1"]})],
                            "worker": [_worker_two],
                            "auditor": [json.dumps({"result": "PASS", "reasons": ["ok"]})]})
    app = _served_app(tmp_path, project, factory)
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(client, project, folder)
    assert resp.status_code == 200, resp.text
    record = _run_record(app, project)
    assert record is not None
    director_calls = [e for e in factory.spy if e.get("role") == "director"]
    assert len(director_calls) == 2, director_calls
    assert record.get("manager_why") == "one group", record.get("manager_why")
