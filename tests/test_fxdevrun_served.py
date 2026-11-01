"""FXDEVRUN served proof: chat Send runs the autonomous dev engine.

Drives the real seam app (create_app + TestClient,
raise_server_exceptions=False) over real throwaway project folders on
the real fs. Fakes live ONLY at the provider network boundary: a
scripted per-role adapter (transport None, canned JSON per role) plus
a spy recording role+model+messages. Real files, real pytest as the
check command, real guarded_dispatch, real audit store.

Rows A-L (each its own test):
A plan+2 parts+files on disk+check output files+audit with
  identity+ledger 4 roles.
B failing output reaches attempt-2 messages then PASS.
C red check + auditor PASS = part FAIL + run not success + text.
D auditor FAIL on green checks re-dispatched with reasons.
E auditor messages carry no agent conversation + a different adapter
  instance than the worker.
F outside-part write refused, nothing written outside on disk.
G double-malformed Director JSON = honest failed run.
H {"answer"} streamed, no parts.
I stop during a long check = child pid dead + run stopped.
J Auto picks the cheapest of two connected fakes, why per part.
K over budget = honest stop.
L live rows show role, model, part and waiting-on during the run.
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

TEST_TOKEN = "fxdevrun-served-token"
ACTOR = "fxdevrun-tester"
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
        "authority": "fxdevrun-test",
        "reason": "fxdevrun served run needs step budgets",
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
            instance_id="fxdevrun-%s" % role,
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
            binding="DEFAULT", version=1, hash="fxdevrun-test"))
    return table


def _bound_mock():
    return MockProviderAdapter(
        AdapterConfig(
            provider_id=PROVIDER,
            instance_id="fxdevrun-bound",
            model=MODEL,
            secret_ref=make_secret_ref(
                secret_id="mock-secret", provider_id=PROVIDER),
        ),
        transport=None, canned=("bound standby",))


def _served_app(tmp_path, project, factory, auto=False):
    agents_live.clear_live_rows()
    _steplimits._reset_state()
    _apply_limits(project)
    store = tmp_path / ("store-" + project)
    store.mkdir(parents=True, exist_ok=True)
    app = create_app(_settings(store))
    _pin_all(app, project,
             mode="AUTO" if auto else "PINNED")
    app.state.chat_provider_adapter = _bound_mock()
    app.state.devrun_adapter_factory = factory
    return app


def _project_dir(tmp_path, project):
    folder = tmp_path / ("proj-" + project)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _post_chat(client, project, folder, message="build it"):
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


def _two_part_plan():
    return [
        {"part_id": "p1", "goal": "Write test_p1.py with one passing test",
         "files": ["test_p1.py"],
         "check_commands": [["python", "-m", "pytest", "test_p1.py",
                              "-q", "-p", "no:cacheprovider"]],
         "depends_on": []},
        {"part_id": "p2", "goal": "Write test_p2.py with one passing test",
         "files": ["test_p2.py"],
         "check_commands": [["python", "-m", "pytest", "test_p2.py",
                              "-q", "-p", "no:cacheprovider"]],
         "depends_on": []},
    ]


def _write_pass(n):
    return json.dumps({
        "actions": [{"action": "write_file", "path": "test_p%d.py" % n,
                     "content": "def test_p%d():\n    assert %d + %d == %d\n"
                     % (n, n, n, 2 * n)}],
        "done": False})


def _worker_two_parts(n_calls, messages):
    text = " ".join(str(part.get("content", ""))
                    for part in messages if isinstance(part, dict))
    if "test_p2" in text or '"p2"' in text or "part_id: p2" in text:
        return _write_pass(2)
    if n_calls % 2 == 0:
        if "test_p2" in text or "p2" in text:
            return _write_pass(2)
        return _write_pass(1)
    return json.dumps({"actions": [], "done": True})


def _manager_order(messages):
    return json.dumps({"order": ["p1", "p2"]})


def _audit_pass(n_calls, messages):
    return json.dumps({"result": "PASS", "reasons": ["checks green"]})


# -- ROW A: full green run -----------------------------------------------


def test_a_full_run_green(tmp_path):
    project = "fxdr-a"
    folder = _project_dir(tmp_path, project)
    factory = _FakeFactory({
        "director": [_plan_text(_two_part_plan())],
        "manager": [_manager_order],
        "worker": [_worker_two_parts],
        "auditor": [_audit_pass],
    })
    app = _served_app(tmp_path, project, factory)
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(client, project, folder)
    assert resp.status_code == 200, resp.text
    events = _parse_sse(resp.text)
    assert _types(events)[0] == "start", events[:2]
    assert _types(events)[-1] == "done", events[-2:]
    assert "success" in _all_text(events).lower(), _all_text(events)
    for name in ("test_p1.py", "test_p2.py"):
        assert (folder / name).is_file(), name
    record = _run_record(app, project)
    assert record is not None, "devrun run record stored on app state"
    assert record.get("success") is True, record.get("summary")
    roles = {row.get("role") for row in record.get("ledger", [])}
    assert {"director", "manager", "worker", "auditor"} <= roles, roles
    assert len(record.get("audits", [])) >= 2, record.get("audits")
    for audit in record.get("audits", []):
        assert audit.get("producer_ref"), audit
        assert audit.get("audit_ref"), audit
        assert audit.get("producer_ref") != audit.get("audit_session"), audit
    outputs = list(folder.glob(".devrun/outputs/*.log"))
    assert len(outputs) >= 2, [str(path) for path in outputs]
    live = client.get("/api/v1/agents/live")
    assert live.status_code == 200, live.text
    assert live.json()["agents"], "live rows recorded"


# -- ROW B: red output reaches attempt 2, then PASS -----------------------

_FAIL_TEST = ("def test_p1():\n    assert 1 == 2, 'fxdevrun red marker'\n")
_PASS_TEST = "def test_p1():\n    assert 1 + 1 == 2\n"


def _worker_red_then_green(n_calls, messages):
    text = " ".join(str(part.get("content", ""))
                    for part in messages if isinstance(part, dict))
    if "attempt 2" in text:
        return json.dumps({
            "actions": [{"action": "write_file", "path": "test_p1.py",
                         "content": _PASS_TEST}],
            "done": False})
    if n_calls % 2 == 0:
        return json.dumps({
            "actions": [{"action": "write_file", "path": "test_p1.py",
                         "content": _FAIL_TEST}],
            "done": False})
    return json.dumps({"actions": [], "done": True})


def _one_part_plan():
    return [
        {"part_id": "p1", "goal": "Write test_p1.py with one passing test",
         "files": ["test_p1.py"],
         "check_commands": [["python", "-m", "pytest", "test_p1.py",
                              "-q", "-p", "no:cacheprovider"]],
         "depends_on": []},
    ]


def test_b_red_output_reaches_attempt_two(tmp_path):
    project = "fxdr-b"
    folder = _project_dir(tmp_path, project)
    factory = _FakeFactory({
        "director": [_plan_text(_one_part_plan())],
        "manager": [json.dumps({"order": ["p1"]})],
        "worker": [_worker_red_then_green],
        "auditor": [_audit_pass],
    })
    app = _served_app(tmp_path, project, factory)
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(client, project, folder)
    assert resp.status_code == 200, resp.text
    record = _run_record(app, project)
    assert record is not None, "devrun run record stored on app state"
    assert record.get("success") is True, record.get("summary")
    worker_calls = [entry for entry in factory.spy
                    if entry.get("role") == "worker"]
    assert len(worker_calls) >= 3, worker_calls
    second_attempt = [entry for entry in worker_calls
                      if "attempt 2" in json.dumps(entry["messages"])]
    assert second_attempt, "attempt-2 worker call exists"
    assert "fxdevrun red marker" in json.dumps(second_attempt[0]["messages"]), (
        "attempt-1 failing output reaches attempt-2 messages")


# -- ROW C: red check + auditor PASS still FAILs the part -----------------

_pytest_timeout = pytest.mark.timeout(280)


def _worker_always_red(n_calls, messages):
    if n_calls % 2 == 0:
        return json.dumps({
            "actions": [{"action": "write_file", "path": "test_p1.py",
                         "content": _FAIL_TEST}],
            "done": False})
    return json.dumps({"actions": [], "done": True})


@_pytest_timeout
def test_c_red_check_plus_audit_pass_is_fail(tmp_path):
    project = "fxdr-c"
    folder = _project_dir(tmp_path, project)
    factory = _FakeFactory({
        "director": [_plan_text(_one_part_plan())],
        "manager": [json.dumps({"order": ["p1"]})],
        "worker": [_worker_always_red],
        "auditor": [_audit_pass],
    })
    app = _served_app(tmp_path, project, factory)
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(client, project, folder)
    assert resp.status_code == 200, resp.text
    record = _run_record(app, project)
    assert record is not None, "devrun run record stored on app state"
    assert record.get("success") is not True, record.get("summary")
    parts = {part["part_id"]: part for part in record.get("parts", [])}
    assert parts["p1"]["verdict"] == "FAIL", parts
    text = _all_text(_parse_sse(resp.text)).lower()
    assert "fail" in text, text
    assert "success" not in text or "not success" in text or \
        "failed" in text, text


# -- ROW D: auditor FAIL on green checks re-dispatched with reasons ------

_AUDIT_REASONS = ["fxdevrun audit reason: missing edge case"]


def _audit_fail_once(n_calls, messages):
    if n_calls == 0:
        return json.dumps({"result": "FAIL", "reasons": _AUDIT_REASONS})
    return json.dumps({"result": "PASS", "reasons": ["fixed"]})


def test_d_auditor_fail_redispatches_with_reasons(tmp_path):
    project = "fxdr-d"
    folder = _project_dir(tmp_path, project)
    factory = _FakeFactory({
        "director": [_plan_text(_one_part_plan())],
        "manager": [json.dumps({"order": ["p1"]})],
        "worker": [_worker_two_parts],
        "auditor": [_audit_fail_once],
    })
    app = _served_app(tmp_path, project, factory)
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(client, project, folder)
    assert resp.status_code == 200, resp.text
    record = _run_record(app, project)
    assert record is not None, "devrun run record stored on app state"
    assert record.get("success") is True, record.get("summary")
    worker_calls = [entry for entry in factory.spy
                    if entry.get("role") == "worker"]
    second_attempt = [entry for entry in worker_calls
                      if "attempt 2" in json.dumps(entry["messages"])]
    assert second_attempt, "auditor FAIL re-dispatched the part"
    assert "missing edge case" in json.dumps(second_attempt[0]["messages"]), (
        "auditor reasons reach the fresh agent loop")


# -- ROW E: auditor sees no agent conversation, fresh instance -----------

_CONVO_MARKER = "fxdevrun secret agent chatter"


def _worker_chatty(n_calls, messages):
    if n_calls % 2 == 0:
        return json.dumps({
            "actions": [{"action": "write_file", "path": "test_p1.py",
                         "content": "def test_p1():\n    assert True\n"}],
            "done": False})
    return json.dumps({"actions": [], "done": True})


def test_e_auditor_isolated_and_fresh(tmp_path):
    project = "fxdr-e"
    folder = _project_dir(tmp_path, project)
    factory = _FakeFactory({
        "director": [_plan_text(_one_part_plan())],
        "manager": [json.dumps({"order": ["p1"]})],
        "worker": [_worker_chatty],
        "auditor": [_audit_pass],
    })
    app = _served_app(tmp_path, project, factory)
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(client, project, folder, message=_CONVO_MARKER)
    assert resp.status_code == 200, resp.text
    auditor_calls = [entry for entry in factory.spy
                     if entry.get("role") == "auditor"]
    worker_calls = [entry for entry in factory.spy
                    if entry.get("role") == "worker"]
    assert auditor_calls and worker_calls, factory.spy
    auditor_blob = json.dumps(
        [entry["messages"] for entry in auditor_calls])
    assert _CONVO_MARKER not in auditor_blob, (
        "auditor messages carry no agent conversation")
    auditor_ids = {entry["adapter_id"] for entry in auditor_calls}
    worker_ids = {entry["adapter_id"] for entry in worker_calls}
    assert auditor_ids.isdisjoint(worker_ids), (
        "auditor runs on a different adapter instance than the worker")


# -- ROW F: outside-part write refused ------------------------------------

def _worker_stray_write(n_calls, messages):
    if n_calls == 0:
        return json.dumps({
            "actions": [
                {"action": "write_file", "path": "../stray.py",
                 "content": "STRAY = 1\n"},
                {"action": "write_file", "path": "test_p1.py",
                 "content": _PASS_TEST}],
            "done": False})
    return json.dumps({"actions": [], "done": True})


def test_f_outside_write_refused(tmp_path):
    project = "fxdr-f"
    folder = _project_dir(tmp_path, project)
    factory = _FakeFactory({
        "director": [_plan_text(_one_part_plan())],
        "manager": [json.dumps({"order": ["p1"]})],
        "worker": [_worker_stray_write],
        "auditor": [_audit_pass],
    })
    app = _served_app(tmp_path, project, factory)
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(client, project, folder)
    assert resp.status_code == 200, resp.text
    assert not (folder / "stray.py").is_file(), "no stray file in folder"
    assert not (folder.parent / "stray.py").is_file(), (
        "no stray file outside the project folder")
    assert not (tmp_path / "stray.py").is_file(), "no stray file in tmp"
    record = _run_record(app, project)
    assert record is not None, "devrun run record stored on app state"
    errors = json.dumps(record.get("parts", []))
    assert "refus" in errors.lower(), (
        "the outside-part write is refused as text: %s" % errors[:500])


# -- ROW G: double-malformed Director JSON --------------------------------

def test_g_malformed_director_honest_fail(tmp_path):
    project = "fxdr-g"
    folder = _project_dir(tmp_path, project)
    factory = _FakeFactory({
        "director": ["not json at all {{{", "still broken }}}{"],
        "manager": [json.dumps({"order": []})],
        "worker": [_worker_chatty],
        "auditor": [_audit_pass],
    })
    app = _served_app(tmp_path, project, factory)
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(client, project, folder)
    assert resp.status_code == 200, resp.text
    events = _parse_sse(resp.text)
    assert _types(events)[-1] in ("error", "done"), events[-2:]
    text = _all_text(events).lower()
    assert "fail" in text, text
    record = _run_record(app, project)
    assert record is not None, "devrun run record stored on app state"
    assert record.get("success") is not True, record.get("summary")


# -- ROW H: plain answer streamed, no parts --------------------------------

def test_h_plain_answer_no_parts(tmp_path):
    project = "fxdr-h"
    folder = _project_dir(tmp_path, project)
    factory = _FakeFactory({
        "director": [json.dumps({"answer": "The sky is blue."})],
        "manager": [json.dumps({"order": []})],
        "worker": [_worker_chatty],
        "auditor": [_audit_pass],
    })
    app = _served_app(tmp_path, project, factory)
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(client, project, folder)
    assert resp.status_code == 200, resp.text
    events = _parse_sse(resp.text)
    assert "The sky is blue." in _all_text(events), _all_text(events)
    record = _run_record(app, project)
    assert record is not None, "devrun run record stored on app state"
    assert record.get("parts", []) == [], record.get("parts")


# -- ROW I: stop during a long check kills the child, run stopped ---------

_SLEEPY = "import time\ntime.sleep(60)\n"


def _worker_sleepy(n_calls, messages):
    if n_calls == 0:
        return json.dumps({
            "actions": [{"action": "write_file", "path": "sleepy.py",
                         "content": _SLEEPY}],
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
        import psutil
    except ImportError:
        psutil = None
    if psutil is not None:
        try:
            return not psutil.Process(pid).is_running()
        except Exception:
            return True
    try:
        os.kill(pid, 0)
    except OSError:
        return True
    return False


@_pytest_timeout
def test_i_stop_during_long_check(tmp_path):
    project = "fxdr-i"
    folder = _project_dir(tmp_path, project)
    factory = _FakeFactory({
        "director": [_plan_text(_sleepy_plan())],
        "manager": [json.dumps({"order": ["p1"]})],
        "worker": [_worker_sleepy],
        "auditor": [_audit_pass],
    })
    app = _served_app(tmp_path, project, factory)
    client = TestClient(app, raise_server_exceptions=False)
    holder = {}

    def _run():
        try:
            holder["resp"] = _post_chat(client, project, folder)
        except Exception as err:
            holder["error"] = err

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    try:
        deadline = time.time() + 45
        while time.time() < deadline:
            record = _run_record(app, project)
            checks = (record or {}).get("checks_started") or []
            if checks:
                break
            time.sleep(0.2)
        record = _run_record(app, project)
        assert record is not None, "run started before stop"
        assert record.get("checks_started"), "check child spawned"
        stop = client.post(
            "/api/v1/stop-all",
            json={"project_id": project, "actor": "user"},
            headers={"x-ui-session-token": TEST_TOKEN})
        assert stop.status_code == 200, stop.text
    finally:
        thread.join(timeout=100)
    assert not thread.is_alive(), "chat stream run finished after stop"
    assert "error" not in holder, holder.get("error")
    events = _parse_sse(holder["resp"].text)
    assert "cancelled" in _types(events), _types(events)
    record = _run_record(app, project)
    assert record is not None
    assert record.get("stopped") is True, record.get("summary")
    pid = (record.get("checks_started") or [{}])[0].get("pid")
    assert isinstance(pid, int) and pid > 0, record.get("checks_started")
    assert _pid_dead(pid), "check child pid %d is dead" % pid


# -- ROW J: Auto picks the cheapest connected fake ------------------------

_PRICE_SOURCE = "https://example.invalid/fxdevrun-pricing"
_PRICE_AT = "2026-10-31"


def _staged_catalog():
    """Two priced fake providers (harness staging; rows J/K need prices)."""
    from agent_si.model_kb import kb as _kb

    def _priced(inp, outp):
        return {
            "input_token_price": _kb.sourced(inp, _PRICE_SOURCE, _PRICE_AT),
            "output_token_price": _kb.sourced(outp, _PRICE_SOURCE,
                                              _PRICE_AT),
        }

    rows = [
        _kb.make_model_row("fxpricey", "fxpricey-model",
                           _priced(1.0, 2.0)),
        _kb.make_model_row("fxcheap", "fxcheap-model",
                           _priced(0.25, 0.5)),
    ]
    return _kb.make_catalog(rows, kb_version=1, updated_at=_PRICE_AT,
                            change_log=[], sources=[])


def _catalog_pairs():
    from agent_si.model_kb import kb as _kb
    catalog = _kb.bound_catalog()
    priced = []
    for row in catalog.get("models", []):
        fields = (row or {}).get("fields") or {}
        try:
            total = float((fields.get("input_token_price") or {})
                          .get("value")) + float(
                              (fields.get("output_token_price") or {})
                              .get("value"))
        except (TypeError, ValueError, AttributeError):
            continue
        priced.append((total, str(row.get("provider_id")),
                       str(row.get("model_id"))))
    priced.sort()
    assert len(priced) >= 2, "catalog holds two priced models"
    return priced


def test_j_auto_picks_cheapest(tmp_path):
    from agent_si.model_kb import kb as _kb
    previous = _kb.bound_catalog()
    _kb.bind_catalog(_staged_catalog())
    try:
        priced = _catalog_pairs()
        cheap = priced[0]
        expensive = priced[-1]
        assert cheap[0] < expensive[0], priced[:3]
        project = "fxdr-j"
        folder = _project_dir(tmp_path, project)
        factory = _FakeFactory(
            {
                "director": [_plan_text(_one_part_plan())],
                "manager": [json.dumps({"order": ["p1"]})],
                "worker": [_worker_chatty],
                "auditor": [_audit_pass],
            },
            providers=[cheap[1], expensive[1]])
        app = _served_app(tmp_path, project, factory, auto=True)
        client = TestClient(app, raise_server_exceptions=False)
        resp = _post_chat(client, project, folder)
        assert resp.status_code == 200, resp.text
        record = _run_record(app, project)
        assert record is not None, "devrun run record stored on app state"
        for part in record.get("parts", []):
            why = part.get("auto_why") or {}
            assert why, "auto why recorded for part %s" % part.get(
                "part_id")
        worker_calls = [entry for entry in factory.spy
                        if entry.get("role") == "worker"]
        assert worker_calls, "worker ran"
        for entry in worker_calls:
            assert entry["provider"] == cheap[1], entry
            assert entry["model"] == cheap[2], entry
    finally:
        _kb.bind_catalog(previous)


# -- ROW K: over budget is an honest stop ---------------------------------

def _priced_pair_with_kb_price():
    from agent_si.runtime import manager as _manager
    for _total, provider, model in _catalog_pairs():
        inp, outp = _manager._kb_price_for_manager(provider, model)
        if inp is not None and outp is not None:
            return provider, model
    raise AssertionError("no catalog pair with a KB price")


def test_k_over_budget_honest_stop(tmp_path):
    from agent_si.model_kb import kb as _kb
    previous = _kb.bound_catalog()
    _kb.bind_catalog(_staged_catalog())
    try:
        provider, model = _priced_pair_with_kb_price()
        project = "fxdr-k"
        folder = _project_dir(tmp_path, project)
        big_usage = {"input_tokens": 1000000, "output_tokens": 1000000}
        factory = _FakeFactory(
            {
                "director": [_plan_text(_one_part_plan())],
                "manager": [json.dumps({"order": ["p1"]})],
                "worker": [_worker_chatty],
                "auditor": [_audit_pass],
            },
            usages={"director": big_usage, "manager": big_usage,
                    "worker": big_usage, "auditor": big_usage},
            providers=[provider])
        app = _served_app(tmp_path, project, factory)
        table = app.state.k04_ctx.role_table
        for role in ("director", "manager", "worker", "auditor"):
            table.set_profile(RoleModelProfile(
                role=role, project_id=project, mode="PINNED",
                provider=provider, model=model,
                binding="DEFAULT", version=1, hash="fxdevrun-test"))
        gate = app.state.k04_ctx.budget_state
        gate.configure_project(project, "USD", "0.000001", "0.000001",
                               "0.000001")
        client = TestClient(app, raise_server_exceptions=False)
        resp = _post_chat(client, project, folder)
        assert resp.status_code == 200, resp.text
        events = _parse_sse(resp.text)
        assert "budget_stop" in _types(events), _types(events)
        assert "budget" in _all_text(events).lower(), _all_text(events)
        record = _run_record(app, project)
        assert record is not None, "devrun run record stored on app state"
        assert record.get("success") is not True, record.get("summary")
    finally:
        _kb.bind_catalog(previous)


# -- ROW L: live rows show role, model, part, waiting-on -------------------

def test_l_live_rows_during_run(tmp_path):
    project = "fxdr-l"
    folder = _project_dir(tmp_path, project)
    factory = _FakeFactory({
        "director": [_plan_text(_two_part_plan())],
        "manager": [_manager_order],
        "worker": [_worker_two_parts],
        "auditor": [_audit_pass],
    })
    app = _served_app(tmp_path, project, factory)
    client = TestClient(app, raise_server_exceptions=False)
    holder = {}

    def _run():
        try:
            holder["resp"] = _post_chat(client, project, folder)
        except Exception as err:
            holder["error"] = err

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    seen = []
    try:
        deadline = time.time() + 45
        while time.time() < deadline:
            live = client.get("/api/v1/agents/live")
            if live.status_code == 200:
                rows = [row for row in live.json().get("agents", [])
                        if str(row.get("scope", "")).startswith(
                            "fxdevrun:%s" % project)]
                if rows:
                    seen = rows
                    break
            time.sleep(0.2)
    finally:
        thread.join(timeout=110)
    assert not thread.is_alive(), "chat stream run finished"
    assert "error" not in holder, holder.get("error")
    assert seen, "live rows visible during the run"
    for row in seen:
        assert row.get("role"), row
        assert row.get("model"), row
        assert "p1" in str(row.get("scope", "")) or \
            "p2" in str(row.get("scope", "")), row
        assert isinstance(row.get("waits"), list), row
