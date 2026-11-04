"""FXPARALLEL proof: independent parts of one dev run overlap, at most 2.

Real engine with a fake only at the provider boundary: scripted
per-role adapters plus a spy, real files, real pytest as the check
command, real guarded_dispatch, real audit store (same harness shape
as tests/test_fxdevrun_served.py).

Rows T1-T10 plus A2 and A3 (brief BRIEF_D + addendum A1-A7):
T1 two independent parts overlap (provider barrier + record times).
T2 dependent part starts only after its prerequisite PASS.
T3 failed prerequisite gives BLOCKED, the peer still finishes.
T4 three ready parts with limit 2: never three at once, all settle.
T5 stop-all with two running: both stop, children dead, no new
  start, the finished part kept.
T6 budget: cap reached with two running ends the run once, recorded
  spend equals the sum of charges, limit-2/limit-1 spent parity.
T7 many concurrent record appends: seq unique, nothing lost.
T8 stream closed mid-run: threaded part work seen, then no part
  thread left and no child alive.
T9 limit 1: order and event texts equal today's (embedded baseline
  captured from the sequential engine before the change).
T10 exception in one thread: one terminal event, peer not PASS.
A2 two parts with different costs read their own live rows.
A3 stop-all landing between spawn and attach: both parts stopped,
  no child alive.
"""

import contextlib
import copy
import json
import os
import re
import sys
import threading
import time
import types
from datetime import datetime

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
from agent_si.backend import parallelparts_routes as _parallelparts  # noqa: E402
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

TEST_TOKEN = "fxparallel-parts-token"
ACTOR = "fxparallel-tester"
PROVIDER = "mock"
MODEL = "mock-canned"

_SLOW = pytest.mark.timeout(280)


def setup_function(_func):
    agents_live.clear_live_rows()
    _steplimits._reset_state()
    _parallelparts._reset_state()


def teardown_function(_func):
    agents_live.clear_live_rows()
    _steplimits._reset_state()
    _parallelparts._reset_state()
    leaked = [thread.name for thread in threading.enumerate()
              if thread.name.startswith("fxparallel-part-")]
    assert not leaked, "part threads outlived the run: %s" % (leaked,)


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
        "authority": "fxparallel-test",
        "reason": "fxparallel run needs step budgets",
        "task_max_steps": 10,
        "chat_max_steps": 10,
    })
    assert outcome.applied, outcome.reason


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


def _terminal_types(events):
    return [kind for kind in _types(events)
            if kind in ("done", "cancelled", "budget_stop", "error")]


class _ScriptedAdapter(MockProviderAdapter):
    """Network-boundary fake only: scripted text per call, spy records.

    The per-call index is a per-instance counter: the engine builds one
    fresh adapter per part attempt and drops it after, so deriving the
    index from id(self) over the shared spy misfires when CPython reuses
    a freed id (a fresh adapter then observes stale calls and e.g. skips
    its write, which flakes T4 p3 / T9 across orders).
    """

    def __init__(self, config, role, script, spy, usage=None):
        super().__init__(config, transport=None, canned=("standby",))
        self.role = role
        self.script = script
        self.spy = spy
        self.forced_usage = usage
        self.calls_made = 0

    def _usage_for(self, messages):
        if callable(self.forced_usage):
            return dict(self.forced_usage(self.role,
                                          copy.deepcopy(messages)))
        if self.forced_usage is not None:
            return dict(self.forced_usage)
        return dict(MOCK_USAGE)

    def invoke(self, messages, params=None, max_turns=8):
        self._check_messages(messages)
        request = self._resolve_request(messages, params)
        n_calls = self.calls_made
        self.calls_made += 1
        if callable(self.script):
            text = self.script(n_calls, copy.deepcopy(messages))
        else:
            text = self.script[min(n_calls, len(self.script) - 1)]
            if callable(text):
                try:
                    text = text(n_calls, copy.deepcopy(messages))
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
            usage=self._usage_for(messages),
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
            instance_id="fxparallel-%s" % role,
            model=model,
            secret_ref=make_secret_ref(
                secret_id="mock-secret", provider_id=provider),
        )
        return _ScriptedAdapter(
            config, role, self.scripts[role], self.spy,
            self.usages.get(role))


def _pin_all(app, project, provider=PROVIDER, model=MODEL):
    table = app.state.k04_ctx.role_table
    for role in ("director", "manager", "worker", "auditor"):
        table.set_profile(RoleModelProfile(
            role=role, project_id=project, mode="PINNED",
            provider=provider, model=model,
            binding="DEFAULT", version=1, hash="fxparallel-test"))
    return table


def _bound_mock():
    return MockProviderAdapter(
        AdapterConfig(
            provider_id=PROVIDER,
            instance_id="fxparallel-bound",
            model=MODEL,
            secret_ref=make_secret_ref(
                secret_id="mock-secret", provider_id=PROVIDER),
        ),
        transport=None, canned=("bound standby",))


def _served_app(tmp_path, project, factory, provider=PROVIDER,
                model=MODEL):
    agents_live.clear_live_rows()
    _steplimits._reset_state()
    _apply_limits(project)
    store = tmp_path / ("store-" + project)
    store.mkdir(parents=True, exist_ok=True)
    app = create_app(_settings(store))
    _pin_all(app, project, provider, model)
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


def _two_part_plan(check=None):
    check = check or ["python", "-m", "pytest", "test_p%d.py",
                      "-q", "-p", "no:cacheprovider"]
    parts = []
    for n in (1, 2):
        argv = [word % n if "%" in word else word for word in check]
        parts.append(
            {"part_id": "p%d" % n,
             "goal": "Write test_p%d.py with one passing test" % n,
             "files": ["test_p%d.py" % n],
             "check_commands": [argv],
             "depends_on": []})
    return parts


def _write_pass(n):
    return json.dumps({
        "actions": [{"action": "write_file", "path": "test_p%d.py" % n,
                     "content": "def test_p%d():\n    assert %d + %d == %d\n"
                     % (n, n, n, 2 * n)}],
        "done": False})


def _part_of(messages, default=1):
    text = " ".join(str(part.get("content", ""))
                    for part in messages if isinstance(part, dict))
    if "part p2" in text:
        return 2
    if "part p3" in text:
        return 3
    if "part p4" in text:
        return 4
    return default


def _manager_order(order):
    def _script(_n_calls, _messages):
        return json.dumps({"order": list(order)})
    return _script


def _audit_pass(_n_calls, _messages):
    return json.dumps({"result": "PASS", "reasons": ["checks green"]})


def _pid_dead(pid):
    # Exit-code liveness: os.kill(pid, 0) reports a reaped Windows
    # child (whose handle the run still holds) as alive, so read the
    # real exit code instead (STILL_ACTIVE 259 means running).
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(0x00100000, False, int(pid))
        if not handle:
            return True
        try:
            code = ctypes.wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle,
                                               ctypes.byref(code)):
                return True
            return code.value != 259
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        pass
    try:
        os.kill(pid, 0)
    except OSError:
        return True
    return False


def _staged_catalog():
    """Two priced fake providers (rows T6/A2 need KB prices)."""
    from agent_si.model_kb import kb as _kb

    def _priced(inp, outp):
        return {
            "input_token_price": _kb.sourced(
                inp, "https://example.invalid/fxparallel-pricing",
                "2026-10-31"),
            "output_token_price": _kb.sourced(
                outp, "https://example.invalid/fxparallel-pricing",
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


def _live_by_scope(project):
    rows = agents_live.live_rows().get("agents", [])
    return [row for row in rows
            if str(row.get("scope", "")).startswith("fxdevrun:%s" % project)]


def _part_times(record):
    def _when(value):
        return datetime.fromisoformat(value) if value else None

    rows = {}
    for part in record.get("parts", []):
        rows[part["part_id"]] = (_when(part.get("started_at")),
                                 _when(part.get("finished_at")))
    return rows


def _overlaps(first, second):
    return first[0] <= second[1] and second[0] <= first[1]


# -- T1: two independent parts overlap --------------------------------

@_SLOW
def test_t1_two_parts_overlap(tmp_path, monkeypatch):
    monkeypatch.setattr(_engine, "_MAX_PART_WORKERS", 2)
    project = "fxpar-t1"
    folder = _project_dir(tmp_path, project)
    barrier = threading.Barrier(2)

    def _worker(n_calls, messages):
        if n_calls == 0:
            barrier.wait(timeout=15)
        n = _part_of(messages)
        if n_calls % 2 == 0:
            return _write_pass(n)
        return json.dumps({"actions": [], "done": True})

    factory = _FakeFactory({
        "director": [_plan_text(_two_part_plan())],
        "manager": [_manager_order(["p1", "p2"])],
        "worker": [_worker],
        "auditor": [_audit_pass],
    })
    app = _served_app(tmp_path, project, factory)
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(client, project, folder)
    assert resp.status_code == 200, resp.text
    record = _run_record(app, project)
    assert record is not None, "devrun run record stored on app state"
    assert record.get("success") is True, record.get("summary")
    times = _part_times(record)
    assert _overlaps(times["p1"], times["p2"]), (
        "independent part times overlap: %s" % (times,))
    auditor_ids = {}
    for entry in factory.spy:
        if entry.get("role") == "auditor":
            text = json.dumps(entry["messages"])
            auditor_ids["p2" if "p2" in text else "p1"] = entry["adapter_id"]
    assert set(auditor_ids) == {"p1", "p2"}, auditor_ids
    assert auditor_ids["p1"] != auditor_ids["p2"], (
        "each part is audited through its own adapter instance")


# -- T2: dependent part starts after its prerequisite PASS -------------

@_SLOW
def test_t2_dependent_starts_after_prereq(tmp_path, monkeypatch):
    monkeypatch.setattr(_engine, "_MAX_PART_WORKERS", 2)
    project = "fxpar-t2"
    folder = _project_dir(tmp_path, project)
    parts = _two_part_plan()
    parts[1]["depends_on"] = ["p1"]

    def _worker(n_calls, messages):
        n = _part_of(messages)
        if n_calls % 2 == 0:
            return _write_pass(n)
        return json.dumps({"actions": [], "done": True})

    factory = _FakeFactory({
        "director": [_plan_text(parts)],
        "manager": [_manager_order(["p1", "p2"])],
        "worker": [_worker],
        "auditor": [_audit_pass],
    })
    app = _served_app(tmp_path, project, factory)
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(client, project, folder)
    assert resp.status_code == 200, resp.text
    record = _run_record(app, project)
    assert record is not None, "devrun run record stored on app state"
    assert record.get("success") is True, record.get("summary")
    rows = {part["part_id"]: part for part in record.get("parts", [])}
    assert rows["p1"]["verdict"] == "PASS", rows
    assert rows["p2"]["verdict"] == "PASS", rows
    times = _part_times(record)
    assert times["p2"][0] >= times["p1"][1], (
        "dependent part starts after its prerequisite PASS: %s" % (times,))


# -- T3: failed prerequisite BLOCKED, peer still finishes --------------

_SLEEPY_FAIL = ("import time\ntime.sleep(20)\n"
                "raise SystemExit('fxparallel red marker')\n")


def _t3_plan():
    slow = ["python", "sleepy20.py"]
    return [
        {"part_id": "p1", "goal": "Write a check that stays red",
         "files": ["sleepy20.py"],
         "check_commands": [slow],
         "depends_on": []},
        {"part_id": "p2", "goal": "Write test_p2.py with one passing test",
         "files": ["test_p2.py"],
         "check_commands": [["python", "-m", "pytest", "test_p2.py",
                              "-q", "-p", "no:cacheprovider"]],
         "depends_on": []},
        {"part_id": "p3", "goal": "Write test_p3.py with one passing test",
         "files": ["test_p3.py"],
         "check_commands": [["python", "-m", "pytest", "test_p3.py",
                              "-q", "-p", "no:cacheprovider"]],
         "depends_on": ["p1"]},
    ]


@_SLOW
def test_t3_failed_prereq_blocked_peer_finishes(tmp_path, monkeypatch):
    monkeypatch.setattr(_engine, "_MAX_PART_WORKERS", 2)
    project = "fxpar-t3"
    folder = _project_dir(tmp_path, project)

    def _worker(n_calls, messages):
        n = _part_of(messages)
        if n == 1:
            if n_calls % 2 == 0:
                return json.dumps({
                    "actions": [{"action": "write_file",
                                 "path": "sleepy20.py",
                                 "content": _SLEEPY_FAIL}],
                    "done": False})
            return json.dumps({"actions": [], "done": True})
        if n_calls % 2 == 0:
            return _write_pass(n)
        return json.dumps({"actions": [], "done": True})

    def _audit(_n_calls, messages):
        text = json.dumps(messages)
        if "stays red" in text:
            return json.dumps({"result": "FAIL",
                               "reasons": ["fxparallel stays red"]})
        return json.dumps({"result": "PASS", "reasons": ["checks green"]})

    factory = _FakeFactory({
        "director": [_plan_text(_t3_plan())],
        "manager": [_manager_order(["p1", "p2", "p3"])],
        "worker": [_worker],
        "auditor": [_audit],
    })
    app = _served_app(tmp_path, project, factory)
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(client, project, folder)
    assert resp.status_code == 200, resp.text
    record = _run_record(app, project)
    assert record is not None, "devrun run record stored on app state"
    rows = {part["part_id"]: part for part in record.get("parts", [])}
    assert rows["p1"]["verdict"] == "FAIL", rows
    assert rows["p2"]["verdict"] == "PASS", rows
    assert rows["p3"]["verdict"] == "BLOCKED", rows
    assert rows["p3"]["reason"] == "blocked: part p1 FAIL", rows["p3"]
    text = _all_text(_parse_sse(resp.text))
    assert "Part p3: BLOCKED (p1 failed)" in text, text
    times = _part_times(record)
    assert _overlaps(times["p1"], times["p2"]), (
        "the peer runs while the failing part still runs: %s" % (times,))
    assert times["p3"] == (None, None), (
        "a BLOCKED part never takes a slot: %s" % (times,))


def _three_part_plan():
    parts = []
    for n in (1, 2, 3):
        parts.append(
            {"part_id": "p%d" % n,
             "goal": "Write test_p%d.py with one passing test" % n,
             "files": ["test_p%d.py" % n],
             "check_commands": [["python", "-m", "pytest",
                                  "test_p%d.py" % n,
                                  "-q", "-p", "no:cacheprovider"]],
             "depends_on": []})
    return parts


# -- T4: three ready parts at limit 2 ----------------------------------

@_SLOW
def test_t4_limit_two_never_three(tmp_path, monkeypatch):
    monkeypatch.setattr(_engine, "_MAX_PART_WORKERS", 2)
    project = "fxpar-t4"
    folder = _project_dir(tmp_path, project)
    gauge = {"current": 0, "peak": 0}
    gauge_lock = threading.Lock()
    # Structural overlap proof: the barrier releases p1/p2 only while
    # both are inside the same worker call; no timing is involved.
    barrier = threading.Barrier(2)
    inside = set()

    def _worker(n_calls, messages):
        n = _part_of(messages)
        if n_calls == 0:
            with gauge_lock:
                gauge["current"] += 1
                gauge["peak"] = max(gauge["peak"], gauge["current"])
            try:
                if n in (1, 2):
                    barrier.wait(timeout=15)
                    with gauge_lock:
                        inside.add("p%d" % n)
            finally:
                with gauge_lock:
                    gauge["current"] -= 1
            return _write_pass(n)
        return json.dumps({"actions": [], "done": True})

    factory = _FakeFactory({
        "director": [_plan_text(_three_part_plan())],
        "manager": [_manager_order(["p1", "p2", "p3"])],
        "worker": [_worker],
        "auditor": [_audit_pass],
    })
    app = _served_app(tmp_path, project, factory)
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(client, project, folder)
    assert resp.status_code == 200, resp.text
    record = _run_record(app, project)
    assert record is not None, "devrun run record stored on app state"
    assert record.get("success") is True, record.get("summary")
    assert gauge["peak"] <= 2, "never three parts at once: %s" % (gauge,)
    assert inside == {"p1", "p2"}, (
        "two parts held the same worker call at once: %s" % (inside,))
    rows = {part["part_id"]: part for part in record.get("parts", [])}
    assert all(row["verdict"] == "PASS" for row in rows.values()), rows


# -- T5: stop-all with two running --------------------------------------

_SLEEPY_LONG = "import time\ntime.sleep(45)\n"


def _t5_plan():
    return [
        {"part_id": "p1", "goal": "Write test_p1.py with one passing test",
         "files": ["test_p1.py"],
         "check_commands": [["python", "-m", "pytest", "test_p1.py",
                              "-q", "-p", "no:cacheprovider"]],
         "depends_on": []},
        {"part_id": "p2", "goal": "Write sleepy2.py then wait",
         "files": ["sleepy2.py"],
         "check_commands": [["python", "sleepy2.py"]],
         "depends_on": []},
        {"part_id": "p3", "goal": "Write sleepy3.py then wait",
         "files": ["sleepy3.py"],
         "check_commands": [["python", "sleepy3.py"]],
         "depends_on": []},
        {"part_id": "p4", "goal": "Write test_p4.py with one passing test",
         "files": ["test_p4.py"],
         "check_commands": [["python", "-m", "pytest", "test_p4.py",
                              "-q", "-p", "no:cacheprovider"]],
         "depends_on": []},
    ]


@_SLOW
def test_t5_stop_all_with_two_running(tmp_path, monkeypatch):
    monkeypatch.setattr(_engine, "_MAX_PART_WORKERS", 2)
    project = "fxpar-t5"
    folder = _project_dir(tmp_path, project)

    def _worker(n_calls, messages):
        n = _part_of(messages)
        if n in (2, 3):
            if n_calls == 0:
                return json.dumps({
                    "actions": [{"action": "write_file",
                                 "path": "sleepy%d.py" % n,
                                 "content": _SLEEPY_LONG}],
                    "done": False})
            return json.dumps({"actions": [], "done": True})
        if n_calls % 2 == 0:
            return _write_pass(n)
        return json.dumps({"actions": [], "done": True})

    factory = _FakeFactory({
        "director": [_plan_text(_t5_plan())],
        "manager": [_manager_order(["p1", "p2", "p3", "p4"])],
        "worker": [_worker],
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
        deadline = time.time() + 60
        while time.time() < deadline:
            record = _run_record(app, project)
            rows = ({part["part_id"]: part
                     for part in (record or {}).get("parts", [])}
                    if record else {})
            checks = (record or {}).get("checks_started") or []
            sleepy = [check for check in checks
                      if "sleepy" in " ".join(check.get("argv", []))]
            sleepy_parts = {check.get("part_id") for check in sleepy}
            if rows.get("p1", {}).get("verdict") == "PASS" \
                    and {"p2", "p3"} <= sleepy_parts:
                break
            time.sleep(0.2)
        record = _run_record(app, project)
        assert record is not None, "run started before stop"
        assert rows.get("p1", {}).get("verdict") == "PASS", rows
        assert {"p2", "p3"} <= sleepy_parts, (
            "two long checks of different parts running before stop")
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
    assert _terminal_types(events) == ["cancelled"], _types(events)
    record = _run_record(app, project)
    assert record is not None
    assert record.get("stopped") is True, record.get("summary")
    rows = {part["part_id"]: part for part in record.get("parts", [])}
    assert rows["p1"]["verdict"] == "PASS", rows
    assert (folder / "test_p1.py").is_file(), "finished part keeps files"
    assert rows["p2"]["verdict"] != "PASS", rows
    assert rows["p3"]["verdict"] != "PASS", rows
    assert rows["p4"]["attempts"] == 0, "no new part starts after stop"
    pids = [check.get("pid") for check in record.get("checks_started", [])
            if "sleepy" in " ".join(check.get("argv", []))]
    assert len(pids) >= 2, record.get("checks_started")
    for pid in pids:
        assert _pid_dead(pid), "check child pid %d is dead" % pid


# -- T6: budget cap with two running ends the run once ------------------

def _t6_scripts(barrier):
    def _worker(n_calls, messages):
        if n_calls == 0:
            barrier.wait(timeout=10)
        return json.dumps({"actions": [], "done": True})

    return {
        "director": [_plan_text(_two_part_plan())],
        "manager": [_manager_order(["p1", "p2"])],
        "worker": [_worker],
        "auditor": [_audit_pass],
    }


def _t6_usages():
    small = {"input_tokens": 10000, "output_tokens": 10000}
    big = {"input_tokens": 1000000, "output_tokens": 1000000}
    return {"director": small, "manager": small,
            "worker": big, "auditor": small}


def _t6_spent(app, project):
    gate = app.state.k04_ctx.budget_state
    state = gate.get_state(project)
    from decimal import Decimal as _Dec
    return _Dec(str(state.spent or "0"))


def _t6_ledger_sum(record):
    from decimal import Decimal as _Dec
    total = _Dec("0")
    for row in record.get("ledger", []):
        cost = row.get("cost")
        if cost is None or (isinstance(cost, str)
                            and cost in ("UNKNOWN", "UNAVAILABLE")):
            continue
        total += _Dec(str(cost))
    return total


@_SLOW
def test_t6_cap_reached_ends_run_once(tmp_path, monkeypatch):
    from agent_si.model_kb import kb as _kb
    previous = _kb.bound_catalog()
    _kb.bind_catalog(_staged_catalog())
    try:
        monkeypatch.setattr(_engine, "_MAX_PART_WORKERS", 2)
        project = "fxpar-t6"
        folder = _project_dir(tmp_path, project)
        barrier = threading.Barrier(2)
        factory = _FakeFactory(
            _t6_scripts(barrier), usages=_t6_usages(),
            providers=["fxpricey"])
        app = _served_app(tmp_path, project, factory,
                           provider="fxpricey", model="fxpricey-model")
        gate = app.state.k04_ctx.budget_state
        gate.configure_project(project, "USD", "2.0", "2.0", "2.0")
        client = TestClient(app, raise_server_exceptions=False)
        resp = _post_chat(client, project, folder)
        assert resp.status_code == 200, resp.text
        events = _parse_sse(resp.text)
        assert _terminal_types(events) == ["budget_stop"], _types(events)
        record = _run_record(app, project)
        assert record is not None, "devrun run record stored on app state"
        rows = {part["part_id"]: part for part in record.get("parts", [])}
        assert rows["p1"]["attempts"] >= 1, rows
        assert rows["p2"]["attempts"] >= 1, rows
        # Recorded spend equals the sum of priced ledger charges
        # (per-call billing, int B4: run-c<seq> ids, every call settles
        # its own reservation; the whole post-call block runs as one
        # locked unit, so two racing charges never interleave).
        assert _t6_spent(app, project) == _t6_ledger_sum(record), (
            record.get("ledger"))

        # Limit-1/limit-2 spent parity: the same scripted run charges
        # the same calls at either limit.
        monkeypatch.setattr(_engine, "_MAX_PART_WORKERS", 1)
        project1 = "fxpar-t6-one"
        folder1 = _project_dir(tmp_path, project1)
        barrier1 = threading.Barrier(2)
        factory1 = _FakeFactory(
            _t6_scripts(barrier1), usages=_t6_usages(),
            providers=["fxpricey"])
        app1 = _served_app(tmp_path, project1, factory1,
                            provider="fxpricey", model="fxpricey-model")
        gate1 = app1.state.k04_ctx.budget_state
        gate1.configure_project(project1, "USD", "2.0", "2.0", "2.0")
        client1 = TestClient(app1, raise_server_exceptions=False)
        resp1 = _post_chat(client1, project1, folder1)
        assert resp1.status_code == 200, resp1.text
        record1 = _run_record(app1, project1)
        assert record1 is not None
        assert _t6_spent(app1, project1) == _t6_spent(app, project), (
            "spent parity across limits")
    finally:
        _kb.bind_catalog(previous)


# -- T7: concurrent record appends keep seq unique ----------------------

def test_t7_concurrent_appends_unique_seq():
    import sys as _sys

    from agent_si.runtime.devrun import records as _records
    record = _records.new_run_record("run-t7", "proj-t7", "task", "folder")
    barrier = threading.Barrier(24)
    errors = []

    def _append(_index):
        try:
            barrier.wait(timeout=15)
            for _ in range(25):
                _records.ledger_add(
                    record, role="worker", provider="mock",
                    model="mock-canned", part="p1", attempt=1,
                    usage={"input_tokens": 1, "output_tokens": 1},
                    cost="0.000001")
                _records.part_add(record, part_id="px", goal="g")
        except Exception as exc:
            errors.append(exc)

    # Tight GIL switching honestly stresses the real len-then-append
    # race window (no product change, interval restored after).
    old_interval = _sys.getswitchinterval()
    _sys.setswitchinterval(0.0001)
    try:
        threads = [threading.Thread(target=_append, args=(n,))
                   for n in range(24)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
    finally:
        _sys.setswitchinterval(old_interval)
    assert not errors, errors
    assert all(not thread.is_alive() for thread in threads)
    ledger = record["ledger"]
    assert len(ledger) == 600, len(ledger)
    assert sorted(row["seq"] for row in ledger) == list(range(1, 601)), (
        "ledger seq unique, nothing lost")
    parts = record["parts"]
    assert len(parts) == 600, "part rows: nothing lost, got %d" % len(parts)


# -- T8: stream closed mid-run leaves no thread -------------------------

def _t8_worker(n_calls, messages):
    n = _part_of(messages)
    if n_calls == 0:
        return json.dumps({
            "actions": [{"action": "write_file",
                         "path": "sleepy%d.py" % n,
                         "content": _SLEEPY_LONG}],
            "done": False})
    return json.dumps({"actions": [], "done": True})


def _t8_plan():
    return [
        {"part_id": "p1", "goal": "Write sleepy1.py then wait",
         "files": ["sleepy1.py"],
         "check_commands": [["python", "sleepy1.py"]],
         "depends_on": []},
        {"part_id": "p2", "goal": "Write sleepy2.py then wait",
         "files": ["sleepy2.py"],
         "check_commands": [["python", "sleepy2.py"]],
         "depends_on": []},
    ]


@_SLOW
def test_t8_stream_close_leaves_no_thread(tmp_path, monkeypatch):
    monkeypatch.setattr(_engine, "_MAX_PART_WORKERS", 2)
    project = "fxpar-t8"
    folder = _project_dir(tmp_path, project)
    factory = _FakeFactory({
        "director": [_plan_text(_t8_plan())],
        "manager": [_manager_order(["p1", "p2"])],
        "worker": [_t8_worker],
        "auditor": [_audit_pass],
    })
    app = _served_app(tmp_path, project, factory)
    request = types.SimpleNamespace(
        project=project, folder=str(folder),
        task="task-%s" % project, message="build it")
    gen = _engine.run_dev_task(request, stream_state={}, app=app)
    try:
        deadline = time.time() + 60
        seen = []
        while time.time() < deadline:
            try:
                next(gen)
            except StopIteration:
                break
            seen = [thread.name for thread in threading.enumerate()
                    if thread.name.startswith("fxparallel-part-")]
            if seen:
                record = _run_record(app, project)
                checks = (record or {}).get("checks_started") or []
                if len(checks) >= 1:
                    break
            time.sleep(0.1)
        assert seen, "part work runs on background threads mid-run"
        gen.close()
        time.sleep(2)
        leaked = [thread.name for thread in threading.enumerate()
                  if thread.name.startswith("fxparallel-part-")]
        assert not leaked, "no part thread outlives the run: %s" % (leaked,)
        record = _run_record(app, project)
        assert record is not None
        for check in record.get("checks_started", []):
            assert _pid_dead(check.get("pid")), (
                "check child pid %s is dead" % (check.get("pid"),))
    finally:
        with contextlib.suppress(Exception):
            gen.close()


# -- T10: one thread exception ends the run once ------------------------

@_SLOW
def test_t10_thread_exception_one_terminal(tmp_path, monkeypatch):
    monkeypatch.setattr(_engine, "_MAX_PART_WORKERS", 2)
    project = "fxpar-t10"
    folder = _project_dir(tmp_path, project)

    def _worker(n_calls, messages):
        n = _part_of(messages)
        if n == 2 and n_calls == 0:
            raise RuntimeError("fxparallel boom")
        if n_calls == 0:
            time.sleep(5)
            return _write_pass(n)
        return json.dumps({"actions": [], "done": True})

    factory = _FakeFactory({
        "director": [_plan_text(_two_part_plan())],
        "manager": [_manager_order(["p1", "p2"])],
        "worker": [_worker],
        "auditor": [_audit_pass],
    })
    app = _served_app(tmp_path, project, factory)
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(client, project, folder)
    assert resp.status_code == 200, resp.text
    events = _parse_sse(resp.text)
    assert _terminal_types(events) == ["done"], _types(events)
    assert "boom" in _all_text(events), _all_text(events)
    record = _run_record(app, project)
    assert record is not None, "devrun run record stored on app state"
    rows = {part["part_id"]: part for part in record.get("parts", [])}
    assert rows["p1"]["verdict"] != "PASS", rows
    assert rows["p2"]["attempts"] >= 1, rows


# -- T9: limit 1 reproduces today's order and event texts ---------------

# Baseline pinned to int's current served shape (refreshed at the
# origin/int merge: one Team line per FXRC1FIX P2, no adapter refs in
# the auditor line; the same shapes test_fxdevwire_served.py asserts
# at :459/:468/:545/:719). Run-unique hex folded to H, the working
# folder line folded to TMP.
_T9_BASELINE = [
    ("start", ""),
    ("delta", "Working folder: TMP\n"),
    ("delta", "Team: director, manager, worker, auditor on "
               "mock/mock-canned (Pinned)\n"),
    ("delta", "Director: plan of 2 parts\n"),
    ("delta", "Part p1: Write test_p1.py with one passing test "
               "(planned: test_p1.py)\n"),
    ("delta", "Part p2: Write test_p2.py with one passing test "
               "(planned: test_p2.py)\n"),
    ("delta", "Part p1: attempt 1\n"),
    ("delta", "Check p1 $ python -m pytest test_p1.py -q -p "
               "no:cacheprovider -> exit 0\n"),
    ("delta", "Auditor for p1: PASS (checks green)\n"),
    ("delta", "Part p1: PASS (checks green, auditor PASS)\n"),
    ("delta", "Part p2: attempt 1\n"),
    ("delta", "Check p2 $ python -m pytest test_p2.py -q -p "
               "no:cacheprovider -> exit 0\n"),
    ("delta", "Auditor for p2: PASS (checks green)\n"),
    ("delta", "Part p2: PASS (checks green, auditor PASS)\n"),
    ("delta", "Total: 0 input + 0 output = 0 tokens; cost not known (no price)\n"),
    ("delta", "run success: all 2 parts PASS\n"),
    ("done", "run success: all 2 parts PASS\n"),
]


def _t9_fold(text):
    if text.startswith("Working folder:"):
        return "Working folder: TMP\n"
    # The engine records the PATH-resolved spawn argv (pre-existing:
    # shutil.which finds a real interpreter under a user PATH and
    # nothing under the sandbox PATH); fold it so the safety switch
    # compares order plus shape, not the machine's python location.
    # The class includes the space: some machines resolve the
    # interpreter under a profile dir like "C:\Users\<name>\...".
    text = re.sub(r"[A-Za-z]:[\\\w\-.\\/ ]*python(\.exe)?",
                  "python", text, flags=re.IGNORECASE)
    return re.sub(r"[0-9a-f]{8,}", "H", text)


@_SLOW
def test_t9_limit_one_matches_today(tmp_path, monkeypatch):
    monkeypatch.setattr(_engine, "_MAX_PART_WORKERS", 1)
    project = "fxpar-t9"
    folder = _project_dir(tmp_path, project)

    def _worker(n_calls, messages):
        n = _part_of(messages)
        if n_calls % 2 == 0:
            return _write_pass(n)
        return json.dumps({"actions": [], "done": True})

    factory = _FakeFactory({
        "director": [_plan_text(_two_part_plan())],
        "manager": [_manager_order(["p1", "p2"])],
        "worker": [_worker],
        "auditor": [_audit_pass],
    })
    app = _served_app(tmp_path, project, factory)
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(client, project, folder)
    assert resp.status_code == 200, resp.text
    events = _parse_sse(resp.text)
    seen = [(str(event.get("type", "")),
             _t9_fold(str(event.get("text", "")))) for event in events]
    assert seen == _T9_BASELINE, (
        "limit 1 reproduces today's order and event texts:\n%s" % (seen,))
    record = _run_record(app, project)
    assert record is not None, "devrun run record stored on app state"
    assert record.get("success") is True, record.get("summary")


# -- A2: each live row carries its own call cost -------------------------

@_SLOW
def test_a2_live_rows_carry_own_cost(tmp_path, monkeypatch):
    from agent_si.model_kb import kb as _kb
    previous = _kb.bound_catalog()
    _kb.bind_catalog(_staged_catalog())
    try:
        monkeypatch.setattr(_engine, "_MAX_PART_WORKERS", 2)
        project = "fxpar-a2"
        folder = _project_dir(tmp_path, project)
        barrier = threading.Barrier(2)
        plan = [
            {"part_id": "p1", "goal": "Probe part one",
             "files": ["a2p1.txt"], "check_commands": [],
             "depends_on": [], "why": "fxparallel a2 probe"},
            {"part_id": "p2", "goal": "Probe part two",
             "files": ["a2p2.txt"], "check_commands": [],
             "depends_on": [], "why": "fxparallel a2 probe"},
        ]

        def _worker(n_calls, messages):
            # Single worker call per part: the two charges interleave
            # on the barrier, then each part writes its declared file
            # (the deterministic PASS gate needs the file on disk).
            barrier.wait(timeout=15)
            text = json.dumps(messages)
            n = 2 if "part p2" in text else 1
            return json.dumps({"actions": [{
                "action": "write_file", "path": "a2p%d.txt" % (n,),
                "content": "fxparallel a2 probe p%d\n" % (n,)}],
                "done": True})

        def _usage(role, messages):
            if role == "worker":
                text = json.dumps(messages)
                if "part p2" in text:
                    return {"input_tokens": 1000000,
                            "output_tokens": 1000000}
                return {"input_tokens": 10000, "output_tokens": 10000}
            return {"input_tokens": 10000, "output_tokens": 10000}

        # Only the worker role is priced here: director/manager/auditor
        # run on the unpriced mock pair (UNAVAILABLE, no reservation).
        # Per-call billing (int B4: run-c<seq> ids): each part worker
        # call settles its own reservation, so both parts are priced.
        # The own-row assertions below are the A2 contract.
        factory = _FakeFactory({
            "director": [_plan_text(plan)],
            "manager": [_manager_order(["p1", "p2"])],
            "worker": [_worker],
            "auditor": [_audit_pass],
        }, usages={"director": _usage, "manager": _usage,
                   "worker": _usage, "auditor": _usage},
            providers=["mock", "fxcheap"])
        app = _served_app(tmp_path, project, factory)
        table = app.state.k04_ctx.role_table
        table.set_profile(RoleModelProfile(
            role="worker", project_id=project, mode="PINNED",
            provider="fxcheap", model="fxcheap-model",
            binding="DEFAULT", version=1, hash="fxparallel-test"))
        gate = app.state.k04_ctx.budget_state
        gate.configure_project(project, "USD", "100.0", "100.0", "100.0")
        client = TestClient(app, raise_server_exceptions=False)
        resp = _post_chat(client, project, folder)
        assert resp.status_code == 200, resp.text
        record = _run_record(app, project)
        assert record is not None, "devrun run record stored on app state"
        assert record.get("success") is True, record.get("summary")
        own = {}
        for row in record.get("ledger", []):
            if row.get("role") == "worker" and row.get("part") in (
                    "p1", "p2"):
                own[row["part"]] = row.get("cost")
        assert set(own) == {"p1", "p2"}, record.get("ledger")
        live = {}
        for row in _live_by_scope(project):
            scope = str(row.get("scope", ""))
            if row.get("role") == "worker" and ":p1:" in scope:
                live["p1"] = row.get("cost")
            elif row.get("role") == "worker" and ":p2:" in scope:
                live["p2"] = row.get("cost")
        assert set(live) == {"p1", "p2"}, _live_by_scope(project)
        assert live["p1"] == own["p1"], (live, own)
        assert live["p2"] == own["p2"], (live, own)
        # Both part worker calls settle (per-call ids); either order
        # is fine, but the rows must differ, match their parts, and
        # carry the exact staged prices.
        priced = [part for part, cost in live.items()
                  if cost not in ("UNKNOWN", "UNAVAILABLE", None)]
        assert len(priced) == 2, (live, own)
        assert live["p1"] != live["p2"], (
            "the two parts carry different costs: %s" % (live,))
        assert live["p1"] == "0.007500", (live, own)
        assert live["p2"] == "0.750000", (live, own)
    finally:
        _kb.bind_catalog(previous)


# -- A3: stop-all between spawn and attach stops both --------------------

@_SLOW
def test_a3_stop_between_spawn_and_attach(tmp_path, monkeypatch):
    import agent_si.runtime.devrun.actions as _actions
    monkeypatch.setattr(_engine, "_MAX_PART_WORKERS", 2)
    project = "fxpar-a3"
    folder = _project_dir(tmp_path, project)
    real_spawn = _actions.spawn_checked
    fired = {"done": False}

    def _racing_spawn(project_id, run_id, folder_arg, argv, log_path,
                      log_rel):
        spawned = real_spawn(project_id, run_id, folder_arg, argv,
                             log_path, log_rel)
        # Stop-all lands after the child is attached to the stop
        # registry but before the engine records the id locally:
        # the real A3 race window, on real threads.
        if not fired["done"] and "-p2-" in str(run_id):
            fired["done"] = True
            from agent_si.backend import stop_all as _stop_all
            _stop_all.request_stop("user", project_id)
        return spawned

    monkeypatch.setattr(_actions, "spawn_checked", _racing_spawn)

    def _worker(n_calls, messages):
        n = _part_of(messages)
        if n_calls == 0:
            return json.dumps({
                "actions": [{"action": "write_file",
                             "path": "sleepy%d.py" % n,
                             "content": _SLEEPY_LONG}],
                "done": False})
        return json.dumps({"actions": [], "done": True})

    factory = _FakeFactory({
        "director": [_plan_text(_t8_plan())],
        "manager": [_manager_order(["p1", "p2"])],
        "worker": [_worker],
        "auditor": [_audit_pass],
    })
    app = _served_app(tmp_path, project, factory)
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(client, project, folder)
    assert resp.status_code == 200, resp.text
    assert fired["done"], "the race window was really hit"
    events = _parse_sse(resp.text)
    assert _terminal_types(events) == ["cancelled"], _types(events)
    record = _run_record(app, project)
    assert record is not None, "devrun run record stored on app state"
    assert record.get("stopped") is True, record.get("summary")
    rows = {part["part_id"]: part for part in record.get("parts", [])}
    assert rows["p1"]["attempts"] >= 1, rows
    assert rows["p2"]["attempts"] >= 1, rows
    assert rows["p1"]["verdict"] != "PASS", rows
    assert rows["p2"]["verdict"] != "PASS", rows
    pids = [check.get("pid") for check in record.get("checks_started", [])]
    assert pids, "both parts spawned before the stop"
    for pid in pids:
        assert _pid_dead(pid), "check child pid %d is dead" % pid


# -- S1/S2/S3: the "parts running at the same time" project setting ----

def _parallel_path(project):
    return "/api/v1/projects/%s/parallel-parts" % (project,)


def _put_parallel(client, project, value, headers=None):
    return client.put(
        _parallel_path(project),
        json={"max_parallel_parts": value},
        headers=_auth() if headers is None else headers)


def _s1_worker(barrier):
    def _worker(n_calls, messages):
        if n_calls == 0:
            barrier.wait(timeout=15)
        n = _part_of(messages)
        if n_calls % 2 == 0:
            return _write_pass(n)
        return json.dumps({"actions": [], "done": True})
    return _worker


@_SLOW
def test_s1_setting_two_via_route_overlaps(tmp_path):
    project = "fxpar-s1"
    folder = _project_dir(tmp_path, project)
    barrier = threading.Barrier(2)
    factory = _FakeFactory({
        "director": [_plan_text(_two_part_plan())],
        "manager": [_manager_order(["p1", "p2"])],
        "worker": [_s1_worker(barrier)],
        "auditor": [_audit_pass],
    })
    app = _served_app(tmp_path, project, factory)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get(_parallel_path(project), headers=_auth())
    assert resp.status_code == 404, resp.text
    resp = _put_parallel(client, project, 2)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"project_id": project,
                           "max_parallel_parts": 2}, resp.text
    resp = client.get(_parallel_path(project), headers=_auth())
    assert resp.status_code == 200, resp.text
    assert resp.json()["max_parallel_parts"] == 2, resp.text
    saved_path = (tmp_path / ("store-" + project)
                  / "devrun_parallel.json")
    with open(str(saved_path), encoding="utf-8") as handle:
        saved = json.load(handle)
    assert saved[project] == 2, saved
    resp = _post_chat(client, project, folder)
    assert resp.status_code == 200, resp.text
    text = _all_text(_parse_sse(resp.text))
    assert "Up to 2 parts at the same time" in text, text
    record = _run_record(app, project)
    assert record is not None, "devrun run record stored on app state"
    assert record.get("success") is True, record.get("summary")
    times = _part_times(record)
    assert _overlaps(times["p1"], times["p2"]), (
        "setting 2 runs two parts at once: %s" % (times,))


@_SLOW
def test_s2_absent_setting_is_sequential(tmp_path):
    project = "fxpar-s2"
    folder = _project_dir(tmp_path, project)
    factory = _FakeFactory({
        "director": [_plan_text(_two_part_plan())],
        "manager": [_manager_order(["p1", "p2"])],
        "worker": [_s1_worker(threading.Barrier(1))],
        "auditor": [_audit_pass],
    })
    app = _served_app(tmp_path, project, factory)
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(client, project, folder)
    assert resp.status_code == 200, resp.text
    text = _all_text(_parse_sse(resp.text))
    assert "Up to" not in text, text
    record = _run_record(app, project)
    assert record is not None, "devrun run record stored on app state"
    assert record.get("success") is True, record.get("summary")
    times = _part_times(record)
    assert times["p2"][0] >= times["p1"][1], (
        "absent setting runs parts one by one: %s" % (times,))


@_SLOW
def test_s3_bad_value_is_one(tmp_path):
    project = "fxpar-s3"
    folder = _project_dir(tmp_path, project)
    factory = _FakeFactory({
        "director": [_plan_text(_two_part_plan())],
        "manager": [_manager_order(["p1", "p2"])],
        "worker": [_s1_worker(threading.Barrier(1))],
        "auditor": [_audit_pass],
    })
    app = _served_app(tmp_path, project, factory)
    client = TestClient(app, raise_server_exceptions=False)
    resp = _put_parallel(client, project, 9)
    assert resp.status_code == 400, resp.text
    assert "POLICY_CONFLICT" in resp.text, resp.text
    resp = _put_parallel(client, project, "many")
    assert resp.status_code == 400, resp.text
    resp = _post_chat(client, project, folder)
    assert resp.status_code == 200, resp.text
    text = _all_text(_parse_sse(resp.text))
    assert "Up to" not in text, text
    record = _run_record(app, project)
    assert record is not None, "devrun run record stored on app state"
    assert record.get("success") is True, record.get("summary")
    times = _part_times(record)
    assert times["p2"][0] >= times["p1"][1], (
        "bad value falls back to sequential: %s" % (times,))
