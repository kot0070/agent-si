"""FXTEAM M2: Team off runs one Worker, no Director/Manager/Auditor."""
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
from agent_si.backend import teammode_routes as _team  # noqa: E402
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

TEST_TOKEN = "fxteam-off-token"
ACTOR = "fxteam-off-tester"
PROVIDER = "mock"
MODEL = "mock-canned"


def _auth(token=TEST_TOKEN, actor=ACTOR):
    return {"x-actor": actor, "x-ui-session-token": token}


def _settings(store_dir):
    return {"testing": True, "ui_session_token": TEST_TOKEN, "store_dir": str(store_dir)}


def _apply_limits(project_id):
    outcome = _steplimits.apply_steplimit_config_change({
        "project_id": project_id,
        "authority": "fxteam-off-test",
        "reason": "fxteam off needs budgets",
        "task_max_steps": 10,
        "chat_max_steps": 10,
    })
    assert outcome.applied, outcome.reason


def setup_function(_func):
    agents_live.clear_live_rows()
    _steplimits._reset_state()
    _team._reset_state()


def teardown_function(_func):
    agents_live.clear_live_rows()
    _steplimits._reset_state()
    _team._reset_state()


def _parse_sse(text):
    events = []
    for line in text.splitlines():
        if line.startswith("data:"):
            events.append(json.loads(line[len("data:"):].strip()))
    return events


def _all_text(events):
    return " ".join(str(e.get("text", "")) for e in events if isinstance(e, dict))


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
        # Team-off only needs worker; director/manager/auditor scripts may be absent.
        script = self.scripts.get(role, [json.dumps({"result": "FAIL", "reasons": ["no script"]})])
        config = AdapterConfig(provider_id=provider, instance_id="fxteam-off-%s" % role,
                               model=model,
                               secret_ref=make_secret_ref(secret_id="mock-secret", provider_id=provider))
        return _ScriptedAdapter(config, role, script, self.spy, self.usages.get(role))


def _pin_all(app, project, mode="PINNED", provider=PROVIDER, model=MODEL):
    table = app.state.k04_ctx.role_table
    for role in ("director", "manager", "worker", "auditor"):
        table.set_profile(RoleModelProfile(role=role, project_id=project, mode=mode,
                                           provider=None if mode == "AUTO" else provider,
                                           model=None if mode == "AUTO" else model,
                                           binding="DEFAULT", version=1, hash="fxteam-off-test"))
    return table


def _bound_mock():
    return MockProviderAdapter(AdapterConfig(provider_id=PROVIDER, instance_id="fxteam-off-bound",
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
    _seed_venv(folder)
    return folder


def _seed_venv(folder):
    """Hermetic project interpreter (bare `python` works with no ambient PATH).

    Same reason as test_fxteam_served.py: the engine resolves bare
    python heads to a project `.venv` first and the toolguard refuses
    absolute interpreter paths, so neither bare-PATH-python nor
    sys.executable is portable across grading envs. Stdlib venv
    (`--without-pip`) plus a `.pth` link to the running env's
    site-packages (which has pytest) closes both gaps.
    """
    import subprocess as _sp
    import sysconfig as _sc
    venv_dir = folder / ".venv"
    _sp.run([sys.executable, "-m", "venv", "--without-pip", str(venv_dir)],
            check=True, capture_output=True, timeout=180)
    purelib = _sc.get_paths()["purelib"]
    site_dir = venv_dir / "Lib" / "site-packages"
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "fxteam_hermetic.pth").write_text(
        purelib + "\n", encoding="utf-8")


def _post_chat(client, project, folder, message="build hello.py"):
    return client.post("/api/v1/chat/stream",
                       json={"project": project, "folder": str(folder),
                             "task": "task-%s" % project, "message": message},
                       headers=_auth())


def test_team_default_on_stays_team():
    # Default (no setting) is on: team_enabled_for reads True.
    assert _team.team_enabled_for(None, "unknown-proj") is True
    out = _team.apply_team_change("p1", "off")
    assert out.applied
    assert _team.team_enabled_for(None, "p1") is False
    out2 = _team.apply_team_change("p1", "on")
    assert out2.applied
    assert _team.team_enabled_for(None, "p1") is True
    bad = _team.apply_team_change("p1", "sometimes")
    assert not bad.applied


def test_team_off_worker_only_no_audit(tmp_path):
    project = "fxteam-off"
    folder = _project_dir(tmp_path, project)

    def _worker_solo(n_calls, messages):
        if n_calls == 0:
            return json.dumps({"actions": [{"action": "write_file", "path": "hello.py",
                                            "content": "print('hi')\n"}], "done": False})
        if n_calls == 1:
            return json.dumps({"actions": [{"action": "run", "argv": ["python", "hello.py"]}],
                               "done": False})
        return json.dumps({"actions": [], "done": True})

    factory = _FakeFactory({"worker": [_worker_solo]})
    app = _served_app(tmp_path, project, factory)
    _team.apply_team_change(project, "off")
    _team.persist_saved_team(app, project, "off")
    client = TestClient(app, raise_server_exceptions=False)
    # Team route serves the saved off value.
    got = client.get("/api/v1/projects/%s/team" % project, headers=_auth())
    assert got.status_code == 200, got.text
    assert got.json()["team"] == "off"
    resp = _post_chat(client, project, folder, message="Create hello.py that prints hi, then run it")
    assert resp.status_code == 200, resp.text
    events = _parse_sse(resp.text)
    text = _all_text(events)
    assert "Done, not audited." in text, text
    assert "PASS" not in text, text
    roles = [e.get("role") for e in factory.spy]
    assert roles, "worker ran"
    assert all(r == "worker" for r in roles), roles
    assert (folder / "hello.py").is_file()
    from agent_si.runtime.devrun import records as _records
    runs = _records.runs_for_project(app, project)
    assert runs, "runs row stored"
    assert runs[0].get("manager_why") == "team off", runs


def test_team_on_default_runs_director(tmp_path):
    project = "fxteam-on"
    folder = _project_dir(tmp_path, project)
    plan = [{"part_id": "p1", "goal": "Write test_p1.py",
             "files": ["test_p1.py"],
             "check_commands": [["python", "-m", "pytest", "test_p1.py", "-q", "-p", "no:cacheprovider"]],
             "depends_on": []}]

    def _worker(n_calls, messages):
        if n_calls % 2 == 0:
            return json.dumps({"actions": [{"action": "write_file", "path": "test_p1.py",
                                            "content": "def test_p1():\n    assert 1 + 1 == 2\n"}],
                               "done": False})
        return json.dumps({"actions": [], "done": True})

    factory = _FakeFactory({"director": [json.dumps({"parts": plan})],
                            "manager": [json.dumps({"order": ["p1"]})],
                            "worker": [_worker],
                            "auditor": [json.dumps({"result": "PASS", "reasons": ["ok"]})]})
    app = _served_app(tmp_path, project, factory)
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(client, project, folder)
    assert resp.status_code == 200, resp.text
    roles = {e.get("role") for e in factory.spy}
    assert "director" in roles and "manager" in roles, roles
