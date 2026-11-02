"""FXASKB served proof: install ask holds the run, decision recorded, no ask.

B1 engine hold: a worker install run with no recorded decision ends the
run as held: one status line "Needs your permission to install: <command>"
plus the terminal approval event carrying the tool id (the same shape the
chat client maps), with the ledger line, run_end and journal of any run
end. Served through the real chat stream (create_app + TestClient) with
fakes ONLY at the provider network boundary (scripted per-role adapters).
B2 served half: Allow posts /permissions/decide with the session token,
then the resend runs the stored answer and does not ask again; deny takes
the refusal text path without asking. B3: Accept/Reject under a finished
answer each post one journal row through token-guarded
POST /api/v1/chat/decision. B4 per-call charge: roles.invoke charges with
a per-call id (run id + "-c" + ledger sequence number): 3 priced calls
spend the sum of the 3 charges; repeating the same call id is refused.
"""

import copy
import json
import os
import shutil
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
from agent_si.runtime import manager as _manager  # noqa: E402
from agent_si.runtime.devrun import engine as _engine  # noqa: E402
from agent_si.runtime.devrun import records as _records  # noqa: E402
from agent_si.runtime.devrun import roles as _roles  # noqa: E402
from agent_si.toolguard import permissions as _permissions  # noqa: E402
from agent_si.watcher import journal as _journal  # noqa: E402

TEST_TOKEN = "fxaskb-served-token"
ACTOR = "fxaskb-tester"
PROVIDER = "mock"
MODEL = "mock-canned"

INSTALL_ARGV = ["cargo", "install", "fxaskb-pkg"]
HOLD_STATUS = "Needs your permission to install: cargo install fxaskb-pkg"


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
        "authority": "fxaskb-test",
        "reason": "fxaskb served run needs step budgets",
        "task_max_steps": 10,
        "chat_max_steps": 10,
    })
    assert outcome.applied, outcome.reason


@pytest.fixture(autouse=True)
def _clean_journal():
    _journal.reset_state()
    yield
    _journal.reset_state()


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


def _types(events):
    return [event.get("type") for event in events
            if isinstance(event, dict)]


def _all_text(events):
    return " ".join(
        str(event.get("text", "")) for event in events
        if isinstance(event, dict))


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
            instance_id="fxaskb-%s" % role,
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
            binding="DEFAULT", version=1, hash="fxaskb-test"))
    return table


def _bound_mock():
    return MockProviderAdapter(
        AdapterConfig(
            provider_id=PROVIDER,
            instance_id="fxaskb-bound",
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


def _post_chat(client, project, folder, message="install the helper"):
    return client.post(
        "/api/v1/chat/stream",
        json={"project": project, "folder": str(folder),
              "task": "task-%s" % project, "message": message},
        headers=_auth())


def _run_record(app, project):
    runs = getattr(app.state, "devrun_runs", None) or {}
    return runs.get(project)


def _plan_text(parts):
    return json.dumps({"parts": parts})


def _one_part_plan():
    return [
        {"part_id": "p1", "goal": "Install the fxaskb helper package",
         "files": ["helper.txt"],
         "check_commands": [["cargo", "cmd"]],
         "depends_on": []},
    ]


def _worker_install(n_calls, messages):
    blob = " ".join(str(part.get("content", ""))
                    for part in messages if isinstance(part, dict))
    if "install fxaskb-pkg: exit" in blob or "refused:" in blob:
        return json.dumps({"actions": [], "done": True})
    return json.dumps({
        "actions": [{"action": "run", "argv": list(INSTALL_ARGV)}],
        "done": False})


def _audit_pass(n_calls, messages):
    return json.dumps({"result": "PASS", "reasons": ["checks green"]})


def _install_factory():
    return _FakeFactory({
        "director": [_plan_text(_one_part_plan())],
        "manager": [json.dumps({"order": ["p1"]})],
        "worker": [_worker_install],
        "auditor": [_audit_pass],
    })


def _bind_cargo_shim(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    shutil.copy(r"C:\Windows\System32\where.exe",
                str(bindir / "cargo.exe"))
    monkeypatch.setenv("PATH", str(bindir) + os.pathsep
                       + os.environ.get("PATH", ""))


def _decide(client, tool_id, decision, project_id, token=TEST_TOKEN):
    return client.post(
        _permissions.PERMISSIONS_DECIDE_ROUTE,
        json={"tool_id": tool_id, "decision": decision,
              "project_id": project_id},
        headers={"x-ui-session-token": token},
    )


# -- B1: the install ask holds the run -------------------------------------

def test_b1_hold_status_line_and_terminal_approval(tmp_path):
    project = "fxaskb-hold"
    folder = _project_dir(tmp_path, project)
    app = _served_app(tmp_path, project, _install_factory())
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(client, project, folder)
    assert resp.status_code == 200, resp.text
    events = _parse_sse(resp.text)
    assert _types(events)[0] == "start", events[:2]
    assert _types(events)[-1] == "approval", _types(events)[-3:]
    held = [event for event in events
            if event.get("type") == "approval"][-1]
    assert held.get("tool_id") == "install:%s:cargo" % project, held
    assert any(str(event.get("text", "")).startswith(HOLD_STATUS)
               for event in events), _all_text(events)[:500]
    assert "Total:" in _all_text(events), _all_text(events)[:500]
    record = _run_record(app, project)
    assert record is not None, "devrun run record stored on app state"
    assert record.get("success") is not True, record.get("summary")
    assert "held" in str(record.get("summary", "")).lower(), (
        record.get("summary"))
    assert record.get("run_end") is not None, "run end ran like any end"
    rows = _journal.stored_rows(project, "DEVRUN_END")
    assert rows, "held run journals its end like any run end"


# -- B1+B2: allow records, resend does not ask again ------------------------

def test_b2_allow_then_resend_does_not_ask(tmp_path, monkeypatch):
    _bind_cargo_shim(tmp_path, monkeypatch)
    project = "fxaskb-allow"
    folder = _project_dir(tmp_path, project)
    app = _served_app(tmp_path, project, _install_factory())
    client = TestClient(app, raise_server_exceptions=False)
    first = _post_chat(client, project, folder)
    assert first.status_code == 200, first.text
    assert "approval" in _types(_parse_sse(first.text)), first.text[:500]
    tool_id = "install:%s:cargo" % project
    resp = _decide(client, tool_id, "allow", project)
    assert resp.status_code == 200, resp.text
    rows = _journal.stored_rows(project)
    assert any("PERMISSION_DECISION" in row.summary
               and tool_id in row.summary and "allow" in row.summary
               for row in rows), [row.summary for row in rows]
    second = _post_chat(client, project, folder)
    assert second.status_code == 200, second.text
    events = _parse_sse(second.text)
    assert "approval" not in _types(events), _types(events)
    assert _types(events)[-1] == "done", _types(events)[-3:]
    assert "exit" in _all_text(events), _all_text(events)[:800]


# -- B2 deny path: refusal text, no hold -----------------------------------

def test_b2_deny_runs_refusal_without_hold(tmp_path):
    project = "fxaskb-deny"
    folder = _project_dir(tmp_path, project)
    app = _served_app(tmp_path, project, _install_factory())
    client = TestClient(app, raise_server_exceptions=False)
    tool_id = "install:%s:cargo" % project
    resp = _decide(client, tool_id, "deny", project)
    assert resp.status_code == 200, resp.text
    rows = _journal.stored_rows(project)
    assert any("PERMISSION_DECISION" in row.summary
               and tool_id in row.summary and "deny" in row.summary
               for row in rows), [row.summary for row in rows]
    text = _engine._run_agent_command(
        record=None, folder=str(folder), project=project,
        run_id="run-deny", argv=list(INSTALL_ARGV),
        state=None, procs=[], attached=set(), stop_seen=None)
    assert "refused: install-class command 'cargo'" in text, text
    second = _post_chat(client, project, folder)
    assert second.status_code == 200, second.text
    assert "approval" not in _types(_parse_sse(second.text)), (
        second.text[:500])


# -- B3: chat decision route journals one row, token-guarded ---------------

CHAT_DECISION_ROUTE = "/api/v1/chat/decision"


def _decision_app(tmp_path):
    store = tmp_path / "store-b3"
    store.mkdir(parents=True, exist_ok=True)
    return TestClient(create_app(_settings(store)),
                      raise_server_exceptions=False)


def test_b3_accept_posts_journal_row(tmp_path):
    client = _decision_app(tmp_path)
    resp = client.post(
        CHAT_DECISION_ROUTE,
        json={"project_id": "proj-b3", "decision": "accepted",
              "proposal": "done deal"},
        headers={"x-ui-session-token": TEST_TOKEN})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("decision") == "accepted", body
    assert body.get("project_id") == "proj-b3", body
    rows = _journal.stored_rows("proj-b3")
    assert any("CHAT_DECISION" in row.summary
               and "accepted" in row.summary for row in rows), (
        [row.summary for row in rows])


def test_b3_reject_posts_journal_row(tmp_path):
    client = _decision_app(tmp_path)
    resp = client.post(
        CHAT_DECISION_ROUTE,
        json={"project_id": "proj-b3r", "decision": "rejected",
              "proposal": "risky plan"},
        headers={"x-ui-session-token": TEST_TOKEN})
    assert resp.status_code == 200, resp.text
    rows = _journal.stored_rows("proj-b3r")
    assert any("CHAT_DECISION" in row.summary
               and "rejected" in row.summary for row in rows), (
        [row.summary for row in rows])


def test_b3_token_and_body_guarded(tmp_path):
    client = _decision_app(tmp_path)
    missing = client.post(
        CHAT_DECISION_ROUTE,
        json={"project_id": "proj-b3", "decision": "accepted"})
    assert missing.status_code == 401, missing.text
    wrong = client.post(
        CHAT_DECISION_ROUTE,
        json={"project_id": "proj-b3", "decision": "accepted"},
        headers={"x-ui-session-token": "wrong-token"})
    assert wrong.status_code == 403, wrong.text
    bad = client.post(
        CHAT_DECISION_ROUTE,
        json={"project_id": "proj-b3", "decision": "maybe"},
        headers={"x-ui-session-token": TEST_TOKEN})
    assert bad.status_code == 400, bad.text
    noproject = client.post(
        CHAT_DECISION_ROUTE,
        json={"decision": "accepted"},
        headers={"x-ui-session-token": TEST_TOKEN})
    assert noproject.status_code == 400, noproject.text
    assert _journal.stored_rows("proj-b3") == (), "no row on refusal"


# -- B4: per-call charge id --------------------------------------------------

B4_PROVIDER = "fxb4prov"
B4_MODEL = "fxb4-priced-model"
B4_USAGE = {"input_tokens": 4000, "output_tokens": 6000}
B4_ONE_CALL = "0.000016"


def _b4_catalog():
    from agent_si.model_kb import kb as _kb

    seed = _kb.bound_catalog()
    row = _kb.make_model_row(B4_PROVIDER, B4_MODEL, fields={
        "input_token_price": {"value": "0.001", "source": "fxaskb-test",
                              "retrieved_at": "2026-10-28"},
        "output_token_price": {"value": "0.002", "source": "fxaskb-test",
                               "retrieved_at": "2026-10-28"},
    })
    catalog = _kb.make_catalog([row] + list(seed.get("models", [])),
                               kb_version=99, updated_at="2026-10-28",
                               change_log=[], sources=[])
    return seed, catalog


class _B4Adapter:
    """Priced-call fake: one fixed usage reply, no network."""

    def __init__(self):
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1

        class _Resp:
            usage = dict(B4_USAGE)

        return _Resp()


def _b4_app(tmp_path):
    from agent_si.model_kb import kb as _kb

    seed, catalog = _b4_catalog()
    _kb.bind_catalog(catalog)
    store = tmp_path / "store-b4"
    store.mkdir(parents=True, exist_ok=True)
    app = create_app(_settings(store))
    gate = app.state.k04_ctx.budget_state
    gate.configure_project("proj-b4", "USD", "100.00", "100.00", "100.00")
    return app, seed


def test_b4_three_calls_spend_sum_repeat_id_refused(tmp_path):
    from decimal import Decimal

    from agent_si.telemetry import run_store as _store

    prev_gate = getattr(_manager, "_BUDGET_GATE", None)
    prev_dir = _store.bound_store_dir()
    app, seed = _b4_app(tmp_path)
    try:
        from agent_si.model_kb import kb as _kb

        folder = _project_dir(tmp_path, "proj-b4")
        record = _records.new_run_record(
            "fxb4-run", "proj-b4", "task", str(folder))
        resolution = {"role": "worker", "provider": B4_PROVIDER,
                      "model": B4_MODEL}
        adapter = _B4Adapter()
        costs = []
        for _ in range(3):
            _response, over = _roles.invoke(
                app, adapter, resolution, [{"role": "user", "content": "hi"}],
                record=record, project_id="proj-b4", run_id="fxb4-run",
                part="p1", attempt=1)
            assert over is not True, "priced call stays under the cap"
            costs.append(record["ledger"][-1]["cost"])
        assert costs == [B4_ONE_CALL] * 3, costs
        gate = app.state.k04_ctx.budget_state
        spent = Decimal(str(gate.get_state("proj-b4").spent))
        assert spent == Decimal("0.000048"), spent
        repeat = _manager._charge_budget_gate(
            "proj-b4", B4_PROVIDER, B4_MODEL, dict(B4_USAGE), "fxb4-run-c1")
        assert repeat == "UNAVAILABLE", repeat
        assert Decimal(str(gate.get_state("proj-b4").spent)) == spent, (
            "repeat of the same call id charges nothing more")
    finally:
        _kb.bind_catalog(seed)
        try:
            _manager.set_budget_gate(prev_gate)
        except Exception:
            pass
        try:
            _store.bind_store_dir(prev_dir)
        except Exception:
            pass
