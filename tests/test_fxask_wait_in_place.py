"""FXASK A8 RED: the run waits in place on an install ask.

The engine generator is driven in a worker thread (as production
drives it); the test thread answers through the decision ledger.
"""

from __future__ import annotations

import copy
import json
import os
import sys
import threading
import time
from types import SimpleNamespace

import pytest

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

TOKEN = "fxask-wait-token"
PROVIDER = "mock"
MODEL = "mock-wait"
TERMINAL = ("done", "cancelled", "error", "approval", "budget_stop")


class _Scripted(MockProviderAdapter):
    def __init__(self, config, role, script, counts):
        super().__init__(config, transport=None, canned=("standby",))
        self.role = role
        self.script = script
        self.counts = counts
        self.calls = 0

    def invoke(self, messages, params=None, max_turns=8):
        request = self._resolve_request(messages, params)
        self.counts[self.role] = int(self.counts.get(self.role, 0)) + 1
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

    def __init__(self, scripts, counts):
        self.scripts = dict(scripts)
        self.counts = counts

    def connected_providers(self):
        return [PROVIDER]

    def __call__(self, *, role, provider, model):
        return _Scripted(
            AdapterConfig(provider_id=provider,
                          instance_id="fxask-%s" % role, model=model,
                          secret_ref=make_secret_ref(
                              secret_id="mock-secret",
                              provider_id=provider)),
            role, self.scripts[role], self.counts)


def _plan(n_calls, messages):
    return json.dumps({"parts": [
        {"part_id": "p-npm", "goal": "Run npm install",
         "files": ["package.json"],
         "check_commands": [["node", "checks/ping.mjs"]],
         "depends_on": []}]})


def _order(n_calls, messages):
    return json.dumps({"order": ["p-npm"]})


def _worker_install_once(n_calls, messages):
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
    project = "fxask-wait-proj"
    folder = tmp_path / "work"
    folder.mkdir()
    (folder / "package.json").write_text(
        '{"name":"x","version":"1.0.0"}', encoding="utf-8")
    (folder / "checks").mkdir()
    (folder / "checks" / "ping.mjs").write_text("process.exit(0);\n",
                                                encoding="utf-8")
    outcome = _steplimits.apply_steplimit_config_change({
        "project_id": project, "authority": "fxask-test",
        "reason": "wait proofs need step budgets",
        "task_max_steps": 10, "chat_max_steps": 10,
    })
    assert outcome.applied, outcome.reason
    app = create_app({"store_dir": str(store),
                      "ui_session_token": TOKEN,
                      "secret_store": "memory"})
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    created = client.post("/api/v1/projects",
                          json={"name": project, "folder_ref": "dock-wait"},
                          headers={"x-actor": "t",
                                   "x-ui-session-token": TOKEN})
    assert created.status_code == 200, created.text
    pid = created.json()["project"]["project_id"]
    outcome = _steplimits.apply_steplimit_config_change({
        "project_id": pid, "authority": "fxask-test",
        "reason": "wait proofs need step budgets for the record id",
        "task_max_steps": 10, "chat_max_steps": 10,
    })
    assert outcome.applied, outcome.reason
    table = app.state.k04_ctx.role_table
    for role in ("director", "manager", "worker", "auditor"):
        table.set_profile(RoleModelProfile(
            role=role, project_id=pid, mode="PINNED",
            provider=PROVIDER, model=MODEL,
            binding="DEFAULT", version=1, hash="fxask-test"))
    counts: dict = {}
    factory = _Factory({"director": _plan, "manager": [_order],
                        "worker": [_worker_install_once],
                        "auditor": [_audit]}, counts)
    app.state.devrun_adapter_factory = factory
    request = SimpleNamespace(project=pid, folder=str(folder),
                              task="t-wait", message="Install with npm")
    state: dict = {}
    yield {"app": app, "pid": pid, "folder": str(folder),
           "counts": counts, "request": request, "state": state}


def _drive(rig):
    collected: list = []
    errors: list = []

    def _go():
        try:
            gen = _engine.run_dev_task(
                rig["request"], stream_state=rig["state"],
                app=rig["app"])
            for event in gen:
                collected.append(event)
        except Exception as exc:  # noqa: BLE001 - surfaced below
            errors.append(exc)

    thread = threading.Thread(target=_go, daemon=True)
    thread.start()
    return thread, collected, errors


def _wait_for(collected, kind, timeout=90.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        for event in list(collected):
            if getattr(event, "event", None) == kind:
                return event
        time.sleep(0.2)
    raise AssertionError("no %r event in %s" % (
        kind, [getattr(e, "event", None) for e in collected]))


def _event_types(collected):
    return [getattr(e, "event", None) for e in collected]


def _event_text(collected):
    return "\n".join(str(getattr(e, "detail", "")
                         or (e.data.get("text", "")
                             if isinstance(getattr(e, "data", None),
                                            dict) else ""))
                     for e in collected)


def _run_ids(collected):
    ids = set()
    for event in collected:
        data = getattr(event, "data", None)
        if isinstance(data, dict) and data.get("run_id"):
            ids.add(str(data["run_id"]))
    return ids


# A8: install ask + Allow: the director is called once, the run id
# never changes, the install runs once, the stream never closes first.
def test_wait_in_place_allow_runs_on(rig):
    thread, collected, errors = _drive(rig)
    try:
        ask = _wait_for(collected, "ask")
        assert _event_types(collected)[-1] not in TERMINAL
        assert rig["counts"].get("director") == 1, rig["counts"]
        tool_id = ask.data["tool_id"]
        assert "npm" in str(tool_id)
        assert list(ask.data["argv"]) == ["npm", "install"]
        assert _permissions.record_decision(
            tool_id=tool_id, decision="allow",
            project_id=rig["pid"])["decision"] == "allow"
        thread.join(timeout=240.0)
        assert not thread.is_alive(), _event_types(collected)[-5:]
        assert not errors, errors
        assert _event_types(collected)[-1] == "done"
        assert "approval" not in _event_types(collected)
        assert len(_run_ids(collected)) == 1
        record = (getattr(rig["app"].state, "devrun_runs", None)
                  or {}).get(rig["pid"], {})
        installs = [row for row in (record.get("install_runs") or [])
                    if list(row.get("argv") or []) == ["npm", "install"]]
        assert len(installs) == 1, record.get("install_runs")
        assert record.get("success") is True, record.get("summary")
        assert rig["counts"].get("director") == 1, rig["counts"]
    finally:
        rig["state"]["cancelled"] = True
        thread.join(timeout=60.0)


# A8: project grant: the next install of the same manager runs with no
# card (no second ask event).
def test_wait_in_place_project_grant_no_second_ask(rig):
    seen_outs: list = []

    def _worker_two_installs(n_calls, messages):
        blob = " ".join(str(p.get("content", "")) for p in messages
                        if isinstance(p, dict)).lower()
        outs = blob.count("run npm install: exit 0")
        seen_outs.append(outs)
        if outs >= 2 or "refused:" in blob:
            return json.dumps({"actions": [], "done": True})
        return json.dumps({"actions": [{"action": "run",
                                        "argv": ["npm", "install"]}],
                           "done": False})

    rig["app"].state.devrun_adapter_factory.scripts["worker"] = [
        _worker_two_installs]
    thread, collected, errors = _drive(rig)
    try:
        ask = _wait_for(collected, "ask")
        tool_id = ask.data["tool_id"]
        _permissions.record_project_grant(
            None, None, rig["pid"], "npm", "install")
        thread.join(timeout=240.0)
        assert not thread.is_alive(), _event_types(collected)[-5:]
        assert not errors, errors
        assert _event_types(collected)[-1] == "done"
        assert _event_types(collected).count("ask") == 1
        # The worker saw two exit-0 install outcomes: the grant covered
        # the second install with no new card.
        assert max(seen_outs or [0]) >= 2, seen_outs
        record = (getattr(rig["app"].state, "devrun_runs", None)
                  or {}).get(rig["pid"], {})
        assert record.get("success") is True, record.get("summary")
    finally:
        rig["state"]["cancelled"] = True
        thread.join(timeout=60.0)


# A8: Stop during the wait stops the run (no hang, no install).
def test_wait_in_place_stop_during_wait(rig):
    thread, collected, errors = _drive(rig)
    try:
        ask = _wait_for(collected, "ask")
        assert ask.data["tool_id"]
        worker_calls = int(rig["counts"].get("worker", 0))
        rig["state"]["cancelled"] = True
        thread.join(timeout=240.0)
        assert not thread.is_alive(), _event_types(collected)[-5:]
        assert not errors, errors
        assert _event_types(collected)[-1] == "cancelled"
        assert "approval" not in _event_types(collected)
        assert int(rig["counts"].get("worker", 0)) == worker_calls, (
            rig["counts"])
    finally:
        rig["state"]["cancelled"] = True
        thread.join(timeout=60.0)


# A8: 15 min without an answer falls back to today's hold (approval
# terminal, resend path stays for that case only).
def test_wait_in_place_fallback_hold_after_timeout(rig, monkeypatch):
    now = [0.0]
    monkeypatch.setattr(
        _engine, "_ask_wait_clock", lambda: now[0])
    thread, collected, errors = _drive(rig)
    try:
        ask = _wait_for(collected, "ask")
        assert ask.data["tool_id"]
        now[0] = 10_000.0
        thread.join(timeout=240.0)
        assert not thread.is_alive(), _event_types(collected)[-5:]
        assert not errors, errors
        assert _event_types(collected)[-1] == "approval"
        record = (getattr(rig["app"].state, "devrun_runs", None)
                  or {}).get(rig["pid"], {})
        assert record.get("held") is True, record.get("summary")
    finally:
        rig["state"]["cancelled"] = True
        thread.join(timeout=60.0)
def test_wait_in_place_deny_fails_plain(rig):
    thread, collected, errors = _drive(rig)
    try:
        ask = _wait_for(collected, "ask")
        worker_calls = int(rig["counts"].get("worker", 0))
        tool_id = ask.data["tool_id"]
        assert _permissions.record_decision(
            tool_id=tool_id, decision="deny",
            project_id=rig["pid"])["decision"] == "deny"
        thread.join(timeout=240.0)
        assert not thread.is_alive(), _event_types(collected)[-5:]
        assert not errors, errors
        assert _event_types(collected)[-1] == "done"
        text = _event_text(collected)
        assert "install permission denied for npm install" in text, (
            text[-900:])
        assert "internal" not in text.lower(), text[-900:]
        assert int(rig["counts"].get("worker", 0)) == worker_calls, (
            rig["counts"])
        record = (getattr(rig["app"].state, "devrun_runs", None)
                  or {}).get(rig["pid"], {})
        assert record.get("success") is False, record.get("summary")
    finally:
        rig["state"]["cancelled"] = True
        thread.join(timeout=60.0)
