"""FXR4A grant-line proofs (served): once-allow consumed, force asks, deny fails.

Through the REAL app (create_app + TestClient + memory secret store)
with fakes ONLY at the model transport (scripted per-role adapters).
One installer (npm), one project per test.
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


def _chat_thread(rig, message, task):
    box: dict = {}

    def _go():
        try:
            box["resp"] = rig["client"].post(
                "/api/v1/chat/stream",
                json={"project": rig["pid"], "folder": rig["folder"],
                      "task": task, "message": message},
                headers=_auth())
        except Exception as exc:  # noqa: BLE001 - surfaced below
            box["error"] = exc

    thread = threading.Thread(target=_go, daemon=True)
    thread.start()
    return thread, box


def _wait_pin(rig, thread, tool_id, timeout=90.0):
    """Wait until the install ask is parked (pin without a decision)."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if not thread.is_alive():
            raise AssertionError("chat stream ended before the ask parked")
        try:
            entry = dict(
                _permissions._BOUND_DECISIONS).get(tool_id)
        except Exception:
            entry = None
        if isinstance(entry, dict) and entry.get("decision") is None:
            return entry
        time.sleep(0.2)
    raise AssertionError("no parked install ask for %s" % (tool_id,))


def _decide(rig, tool_id, decision):
    return rig["client"].post(
        _permissions.PERMISSIONS_DECIDE_ROUTE,
        json={"tool_id": tool_id, "decision": decision,
              "project_id": rig["pid"]},
        headers={"x-ui-session-token": TOKEN})


# D4 (FXASK A8 shape): the once-allow runs the parked install on the
# same run (no resend, stream never closes); the next run asks again.
def test_fxr4a_once_allow_consumed_next_run_asks(rig):
    tool_id = _permissions.install_tool_id(rig["pid"], "npm")
    thread, box = _chat_thread(
        rig, "Install dependencies with npm install", task="t-hold")
    try:
        _wait_pin(rig, thread, tool_id)
        assert _decide(rig, tool_id, "allow").status_code == 200
        thread.join(timeout=240.0)
        assert not thread.is_alive()
        assert not box.get("error"), box.get("error")
        first = box.get("resp")
        assert first is not None and first.status_code == 200, first
        events = _parse_sse(first.text)
        assert _types(events)[-1] == "done"
        assert "approval" not in _types(events)
        assert "exit 0" in _all_text(events)
        record = (getattr(rig["app"].state, "devrun_runs", None)
                  or {}).get(rig["pid"], {})
        assert record.get("success") is True, record.get("summary")
    finally:
        thread.join(timeout=60.0)
    thread2, box2 = _chat_thread(
        rig, "Install dependencies with npm install", task="t-again")
    try:
        # The next run parks on the spent once-allow (no silent
        # refusal, no FAILED): a fresh allow covers it and the same
        # run goes on. The pin keeps the old decision, so there is no
        # decision-less pin to wait for — deciding is safe either way:
        # before the park it covers the spawn, after it the wait.
        time.sleep(8.0)
        assert thread2.is_alive()
        assert _decide(rig, tool_id, "allow").status_code == 200
        thread2.join(timeout=240.0)
        assert not thread2.is_alive()
        again = box2.get("resp")
        assert again is not None and again.status_code == 200, again
        assert _types(_parse_sse(again.text))[-1] == "done"
    finally:
        thread2.join(timeout=60.0)


# D5: --force after an allow must ask with the real words, never run silent.
def test_fxr4a_force_args_ask_with_real_words(rig):
    rig["factory"].scripts["director"] = _force_plan
    tool_id = _permissions.install_tool_id(rig["pid"], "npm")
    thread, box = _chat_thread(
        rig, "Install with npm install --force", task="t-force")
    try:
        pin = _wait_pin(rig, thread, tool_id)
        assert list(pin.get("argv") or []) == [
            "npm", "install", "--force"], pin
        assert _decide(rig, tool_id, "deny").status_code == 200
        thread.join(timeout=240.0)
        assert not thread.is_alive()
        forced = box.get("resp")
        assert forced is not None and forced.status_code == 200
        events = _parse_sse(forced.text)
        assert _types(events)[-1] == "done"
        assert "approval" not in _types(events)
        assert "FAILED" in _all_text(events), _all_text(events)[:900]
    finally:
        thread.join(timeout=60.0)


# FXASK A4 (supersedes D6): a deny covers that run only. A new task
# asks again (parked ask, never a silent refusal); allowing that ask
# runs the install on. The old D6 FAILED-without-card shape is gone on
# purpose: a denied run that is asked again is never a refusal.
def test_fxr4a_deny_next_run_asks_again(rig):
    tool_id = _permissions.install_tool_id(rig["pid"], "npm")
    thread, box = _chat_thread(
        rig, "Install dependencies with npm install", task="t-deny")
    try:
        _wait_pin(rig, thread, tool_id)
        assert _decide(rig, tool_id, "deny").status_code == 200
        thread.join(timeout=240.0)
        assert not thread.is_alive()
        first = box.get("resp")
        assert first is not None and first.status_code == 200, first
        events = _parse_sse(first.text)
        assert _types(events)[-1] == "done"
        assert "approval" not in _types(events)
        record = (getattr(rig["app"].state, "devrun_runs", None)
                  or {}).get(rig["pid"], {})
        assert record.get("success") is False, record.get("summary")
        assert "denied" in str(record.get("summary", "")).lower(), (
            record.get("summary"))
    finally:
        thread.join(timeout=60.0)
    thread2, box2 = _chat_thread(
        rig, "Install dependencies with npm install", task="t-deny2")
    try:
        time.sleep(8.0)
        assert thread2.is_alive()
        assert _decide(rig, tool_id, "allow").status_code == 200
        thread2.join(timeout=240.0)
        assert not thread2.is_alive()
        again = box2.get("resp")
        assert again is not None and again.status_code == 200, again
        events = _parse_sse(again.text)
        assert _types(events)[-1] == "done"
        assert "approval" not in _types(events)
        assert "exit 0" in _all_text(events)
    finally:
        thread2.join(timeout=60.0)
