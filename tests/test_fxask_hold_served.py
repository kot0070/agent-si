"""FXASK A4/A5/A6 served: run-scoped deny, no ghost files, plain held text.

Through the REAL app (create_app + TestClient + memory secret store)
with fakes ONLY at the model transport (scripted per-role adapters).
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
from agent_si.runtime.devrun import engine as _engine  # noqa: E402
from agent_si.toolguard import permissions as _permissions  # noqa: E402
from agent_si.watcher import journal as _journal  # noqa: E402

TOKEN = "fxask-hold-token"
ACTOR = "fxask-hold-tester"
PROVIDER = "mock"
MODEL = "mock-hold"


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
        return _Scripted(
            AdapterConfig(provider_id=provider,
                          instance_id="fxask-%s" % role, model=model,
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


def _order(n_calls, messages):
    return json.dumps({"order": ["p-npm"]})


def _npm_worker(n_calls, messages):
    blob = " ".join(str(p.get("content", "")) for p in messages
                    if isinstance(p, dict)).lower()
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
    project = "fxask-hold-proj"
    folder = tmp_path / "work"
    folder.mkdir()
    (folder / "package.json").write_text(
        '{"name":"x","version":"1.0.0"}', encoding="utf-8")
    (folder / "checks").mkdir()
    (folder / "checks" / "ping.mjs").write_text("process.exit(0);\n",
                                                encoding="utf-8")
    outcome = _steplimits.apply_steplimit_config_change({
        "project_id": project, "authority": "fxask-test",
        "reason": "hold proofs need step budgets",
        "task_max_steps": 10, "chat_max_steps": 10,
    })
    assert outcome.applied, outcome.reason
    app = create_app({"store_dir": str(store),
                      "ui_session_token": TOKEN,
                      "secret_store": "memory"})
    client = TestClient(app, raise_server_exceptions=False)
    created = client.post("/api/v1/projects",
                          json={"name": project, "folder_ref": "dock-hold"},
                          headers=_auth())
    assert created.status_code == 200, created.text
    pid = created.json()["project"]["project_id"]
    outcome = _steplimits.apply_steplimit_config_change({
        "project_id": pid, "authority": "fxask-test",
        "reason": "hold proofs need step budgets for the record id",
        "task_max_steps": 10, "chat_max_steps": 10,
    })
    assert outcome.applied, outcome.reason
    table = app.state.k04_ctx.role_table
    for role in ("director", "manager", "worker", "auditor"):
        table.set_profile(RoleModelProfile(
            role=role, project_id=pid, mode="PINNED",
            provider=PROVIDER, model=MODEL,
            binding="DEFAULT", version=1, hash="fxask-test"))
    app.state.chat_provider_adapter = MockProviderAdapter(
        AdapterConfig(provider_id=PROVIDER, instance_id="fxask-bound",
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
            entry = _permissions.load_decisions(None).get(tool_id)
        except Exception:
            entry = None
        if entry is None:
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


def _record(rig):
    return (getattr(rig["app"].state, "devrun_runs", None) or {}).get(
        rig["pid"], {})


def _ask_tool_id(events):
    asks = [e for e in events if e.get("type") == "ask"]
    assert asks, [e.get("type") for e in events][-4:]
    return asks[0]


# A6: the held summary is plain command words; the raw tool id rides
# its own field, never the summary or hold reason.
def test_hold_summary_plain_command_id_in_field(rig):
    tool_id = _permissions.install_tool_id(rig["pid"], "npm")
    thread, box = _chat_thread(
        rig, "Install dependencies with npm install", task="t-hold-a6")
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
        ask = _ask_tool_id(events)
        assert ask.get("tool_id") == tool_id, ask
        assert list(ask.get("argv") or []) == ["npm", "install"], ask
        record = _record(rig)
        assert record.get("held") is not True
        assert record.get("success") is True, record.get("summary")
    finally:
        thread.join(timeout=60.0)


def test_hold_fallback_summary_plain(rig, monkeypatch):
    now = [0.0]
    monkeypatch.setattr(_engine, "_ask_wait_clock", lambda: now[0])
    tool_id = _permissions.install_tool_id(rig["pid"], "npm")
    thread, box = _chat_thread(
        rig, "Install dependencies with npm install", task="t-hold-a6b")
    try:
        _wait_pin(rig, thread, tool_id)
        now[0] = 10_000.0
        thread.join(timeout=240.0)
        assert not thread.is_alive()
        assert not box.get("error"), box.get("error")
        first = box.get("resp")
        assert first is not None and first.status_code == 200, first
        events = _parse_sse(first.text)
        assert _types(events)[-1] == "approval", _types(events)[-3:]
        record = _record(rig)
        assert record.get("held") is True, record.get("summary")
        assert record.get("summary") == (
            "run held: waiting for your permission to run npm install"), (
            record.get("summary"))
        assert "install:" not in str(record.get("summary")), (
            record.get("summary"))
        assert record.get("hold_reason") == record.get("summary")
        assert record.get("hold_tool_id") == tool_id
    finally:
        thread.join(timeout=60.0)


# A5: the run's [files: ...] markers never list a file that is absent
# under the folder (a missing declared file still fails honestly by
# name, but no marker presents it as evidence).
def test_absent_planned_file_dropped_from_run_text(rig):
    import re

    def _ghost_plan(n_calls, messages):
        return json.dumps({"parts": [
            {"part_id": "p-npm", "goal": "Run npm install",
             "files": ["package.json",
                       "node_modules/is-even/package.json"],
             "check_commands": [["node", "checks/ping.mjs"]],
             "depends_on": []}]})

    rig["app"].state.devrun_adapter_factory.scripts["director"] = (
        _ghost_plan)
    tool_id = _permissions.install_tool_id(rig["pid"], "npm")
    thread, box = _chat_thread(
        rig, "Install dependencies with npm install", task="t-hold-a5")
    try:
        _wait_pin(rig, thread, tool_id)
        assert _decide(rig, tool_id, "allow").status_code == 200
        thread.join(timeout=240.0)
        assert not thread.is_alive()
        first = box.get("resp")
        assert first is not None and first.status_code == 200, first
        text = _all_text(_parse_sse(first.text))
        markers = re.findall(r"\[files: ([^\]]+)\]", text)
        assert markers, text[:900]
        assert not any("is-even" in marker for marker in markers), (
            markers)
        assert any("package.json" in marker for marker in markers), (
            markers)
    finally:
        thread.join(timeout=60.0)


# A4: a deny covers that run only; the next task asks again, no silent
# refusal and no FAILED without a card.
def test_deny_then_next_task_asks_again(rig):
    tool_id = _permissions.install_tool_id(rig["pid"], "npm")
    thread, box = _chat_thread(
        rig, "Install dependencies with npm install", task="t-deny-a4")
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
        record = _record(rig)
        assert record.get("success") is False, record.get("summary")
        assert "denied" in str(record.get("summary", "")).lower(), (
            record.get("summary"))
        # A new task parks a fresh ask instead of refusing silently.
        thread2, box2 = _chat_thread(
            rig, "Install dependencies with npm install",
            task="t-again-a4")
        try:
            pin = _wait_pin(rig, thread2, tool_id)
            assert thread2.is_alive()
            assert pin.get("decision") is None
            assert _decide(rig, tool_id, "allow").status_code == 200
            thread2.join(timeout=240.0)
            assert not thread2.is_alive()
            again = box2.get("resp")
            assert again is not None and again.status_code == 200
            assert _types(_parse_sse(again.text))[-1] == "done"
        finally:
            thread2.join(timeout=60.0)
    finally:
        thread.join(timeout=60.0)
