"""FXR4A grant-line proofs (served): once-allow consumed, force asks, deny fails.

Through the REAL app (create_app + TestClient + memory secret store)
with fakes ONLY at the model transport (scripted per-role adapters).
One installer (npm), one project per test.
"""
import copy
import json
import os
import sys

import pytest
from fastapi.testclient import TestClient

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
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
from agent_si.toolguard import permissions as _permissions  # noqa: E402
from agent_si.watcher import journal as _journal  # noqa: E402

TOKEN = "fxr4a-served-token"
ACTOR = "fxr4a-tester"
PROVIDER = "mock"
MODEL = "mock-r4a"


def _auth():
    return {"x-actor": ACTOR, "x-ui-session-token": TOKEN}


def _parse_sse(text):
    events = []
    for line in text.splitlines():
        if line.startswith("data:"):
            events.append(json.loads(line[len("data:"):].strip()))
    return events


def _types(events):
    return [e.get("type") for e in events if isinstance(e, dict)]


def _all_text(events):
    return " ".join(str(e.get("text", "")) for e in events
                    if isinstance(e, dict))


class _Scripted(MockProviderAdapter):
    def __init__(self, config, role, script):
        super().__init__(config, transport=None, canned=("standby",))
        self.role = role
        self.script = script
        self.calls = 0

    def invoke(self, messages, params=None, max_turns=8):
        self._check_messages(messages)
        request = self._resolve_request(messages, params)
        n_calls = self.calls
        self.calls += 1
        if callable(self.script):
            text = self.script(n_calls, copy.deepcopy(messages))
        else:
            item = self.script[min(n_calls, len(self.script) - 1)]
            if callable(item):
                try:
                    text = item(n_calls, copy.deepcopy(messages))
                except TypeError:
                    text = item(copy.deepcopy(messages))
            else:
                text = item
        self.turns_served += 1
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


class _Factory:
    ROLES = ("director", "manager", "worker", "auditor")

    def __init__(self, scripts):
        self.scripts = dict(scripts)

    def connected_providers(self):
        return [PROVIDER]

    def __call__(self, *, role, provider, model):
        assert role in self.ROLES, role
        assert (provider, model) == (PROVIDER, MODEL), (provider, model)
        return _Scripted(
            AdapterConfig(provider_id=provider,
                          instance_id="fxr4a-%s" % role, model=model,
                          secret_ref=make_secret_ref(
                              secret_id="mock-secret",
                              provider_id=provider)),
            role, self.scripts[role])


def _npm_plan(n_calls, messages):
    return json.dumps({"parts": [
        {"part_id": "p-npm", "goal": "Run npm install",
         "files": ["package.json"],
         "check_commands": [["node", "checks/ping.mjs"]],
         "depends_on": []}]})


def _force_plan(n_calls, messages):
    return json.dumps({"parts": [
        {"part_id": "p-force", "goal": "Run npm install --force",
         "files": ["package.json"],
         "check_commands": [["node", "checks/ping.mjs"]],
         "depends_on": []}]})


def _order(n_calls, messages):
    return json.dumps({"order": ["p-npm", "p-force"]})


def _npm_worker(n_calls, messages):
    blob = " ".join(str(p.get("content", "")) for p in messages
                    if isinstance(p, dict)).lower()
    if "--force" in blob:
        if "exit" in blob or "refused:" in blob or n_calls >= 1:
            return json.dumps({"actions": [], "done": True})
        return json.dumps({"actions": [{"action": "run",
                                         "argv": ["npm", "install",
                                                  "--force"]}],
                            "done": False})
    if "exit" in blob or "refused:" in blob or n_calls >= 1:
        return json.dumps({"actions": [], "done": True})
    return json.dumps({"actions": [{"action": "run",
                                     "argv": ["npm", "install"]}],
                        "done": False})


def _audit(n_calls, messages):
    return json.dumps({"result": "PASS", "reasons": ["checks green"]})


@pytest.fixture()
def rig(tmp_path):
    agents_live.clear_live_rows()
    _steplimits._reset_state()
    _journal.reset_state()
    store = tmp_path / "store"
    store.mkdir()
    project = "fxr4a-proj"
    folder = tmp_path / "work"
    folder.mkdir()
    (folder / "package.json").write_text(
        '{"name":"x","version":"1.0.0","dependencies":{}}',
        encoding="utf-8")
    (folder / "checks").mkdir()
    (folder / "checks" / "ping.mjs").write_text("process.exit(0);\n",
                                                encoding="utf-8")
    outcome = _steplimits.apply_steplimit_config_change({
        "project_id": project, "authority": "fxr4a-test",
        "reason": "grant proofs need step budgets",
        "task_max_steps": 10, "chat_max_steps": 10,
    })
    assert outcome.applied, outcome.reason
    app = create_app({"store_dir": str(store),
                      "ui_session_token": TOKEN,
                      "secret_store": "memory"})
    client = TestClient(app, raise_server_exceptions=False)
    created = client.post("/api/v1/projects",
                          json={"name": project, "folder_ref": "dock-r4a"},
                          headers=_auth())
    assert created.status_code == 200, created.text
    pid = created.json()["project"]["project_id"]
    outcome = _steplimits.apply_steplimit_config_change({
        "project_id": pid, "authority": "fxr4a-test",
        "reason": "grant proofs need step budgets for the record id",
        "task_max_steps": 10, "chat_max_steps": 10,
    })
    assert outcome.applied, outcome.reason
    table = app.state.k04_ctx.role_table
    for role in ("director", "manager", "worker", "auditor"):
        table.set_profile(RoleModelProfile(
            role=role, project_id=pid, mode="PINNED",
            provider=PROVIDER, model=MODEL,
            binding="DEFAULT", version=1, hash="fxr4a-test"))
    app.state.chat_provider_adapter = MockProviderAdapter(
        AdapterConfig(provider_id=PROVIDER, instance_id="fxr4a-bound",
                      model=MODEL,
                      secret_ref=make_secret_ref(
                          secret_id="mock-secret",
                          provider_id=PROVIDER)),
        transport=None, canned=("bound standby",))
    factory = _Factory({"director": _npm_plan, "manager": [_order],
                        "worker": [_npm_worker], "auditor": [_audit]})
    app.state.devrun_adapter_factory = factory
    yield {"app": app, "client": client, "pid": pid,
           "folder": str(folder), "factory": factory}


def _chat(rig, message, task):
    return rig["client"].post(
        "/api/v1/chat/stream",
        json={"project": rig["pid"], "folder": rig["folder"],
              "task": task, "message": message},
        headers=_auth())


def _decide(rig, tool_id, decision):
    return rig["client"].post(
        _permissions.PERMISSIONS_DECIDE_ROUTE,
        json={"tool_id": tool_id, "decision": decision,
              "project_id": rig["pid"]},
        headers={"x-ui-session-token": TOKEN})


def _held_tool_id(resp):
    events = _parse_sse(resp.text)
    assert _types(events)[-1] == "approval", _types(events)[-3:]
    held = [e for e in events if e.get("type") == "approval"][-1]
    assert "npm" in str(held) and "install" in str(held), held
    return held.get("tool_id")


# D4: allow once is consumed by the replay; the next run asks again.
def test_fxr4a_once_allow_consumed_next_run_asks(rig):
    first = _chat(rig, "Install dependencies with npm install",
                  task="t-hold")
    assert first.status_code == 200, first.text
    tool_id = _held_tool_id(first)
    assert _decide(rig, tool_id, "allow").status_code == 200
    replay = _chat(rig, "Install dependencies with npm install",
                   task="t-hold")
    assert replay.status_code == 200, replay.text
    assert "approval" not in _types(_parse_sse(replay.text))
    assert _types(_parse_sse(replay.text))[-1] == "done"
    assert "exit 0" in _all_text(_parse_sse(replay.text))
    again = _chat(rig, "Install dependencies with npm install",
                  task="t-again")
    assert again.status_code == 200, again.text
    assert "approval" in _types(_parse_sse(again.text)), again.text[:600]


# D5: --force after an allow must ask with the real words, never run silent.
def test_fxr4a_force_args_ask_with_real_words(rig):
    rig["factory"].scripts["director"] = _force_plan
    forced = _chat(rig, "Install with npm install --force",
                   task="t-force")
    assert forced.status_code == 200, forced.text
    events = _parse_sse(forced.text)
    assert "approval" in _types(events), forced.text[:600]
    held = [e for e in events if e.get("type") == "approval"][-1]
    assert "npm" in str(held) and "install" in str(held), held
    assert "--force" in str(held), held


# D6: deny replay closes the part FAILED with a plain line, no loop.
def test_fxr4a_deny_replay_fails_plain(rig):
    first = _chat(rig, "Install dependencies with npm install",
                  task="t-deny")
    assert first.status_code == 200, first.text
    tool_id = _held_tool_id(first)
    assert _decide(rig, tool_id, "deny").status_code == 200
    replay = _chat(rig, "Install dependencies with npm install",
                   task="t-deny2")
    assert replay.status_code == 200, replay.text
    text = _all_text(_parse_sse(replay.text))
    assert "FAILED" in text, text[:900]
    assert "internal" not in replay.text.lower(), replay.text[:600]
    assert "approval" not in _types(_parse_sse(replay.text))
    assert _types(_parse_sse(replay.text))[-1] in ("done", "error")
    record = (getattr(rig["app"].state, "devrun_runs", None) or {}).get(
        rig["pid"], {})
    assert record.get("success") is False, record.get("summary")
    assert "denied" in str(record.get("summary", "")).lower(), (
        record.get("summary"))
