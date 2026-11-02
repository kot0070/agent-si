"""FXGOLD golden user path: owner-real-path regression net (BE).

One app + one data folder, same HTTP routes + session token the exe UI
uses, faking ONLY the model transport:

- urlopen-level strict fake: the provider evidence probe must hit a known
  path with a well-formed body and the connected model; a wrong path,
  model or body fails (URLError) the way the real service fails.
- per-role scripted adapters (sanctioned FXASKA/B pattern): unknown role
  or provider/model mismatch raises like the real service; replies are
  scripted per role, one model for all roles.

Each step is its own test_* function sharing one module fixture
(`golden`); no stop at the first failure, so `-k golden` prints N of M.
Real files, real processes, real findstr on Windows.
"""

import copy
import json
import os
import subprocess
import sys
import threading
import urllib.request as _urlreq

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
    ProviderTimeoutError,
    make_secret_ref,
)
from agent_si.providers.adapters.mock_provider import (  # noqa: E402
    MOCK_USAGE,
    MockProviderAdapter,
)
from agent_si.routing.types import RoleModelProfile  # noqa: E402
from agent_si.toolguard import permissions as _permissions  # noqa: E402
from agent_si.watcher import journal as _journal  # noqa: E402

TOKEN = "fxgold-owner-token"
ACTOR = "owner-ui"
PROVIDER = "mock"
MODEL = "mock-golden"
BAIT = "FAKE-FXGOLD-0000-zzzz-not-a-real-key"
PRESET = "openai"
CONNECT_MODEL = "openai/golden-model"
PROJECT = "fxgold-app"
PROJECT2 = "fxgold-second"

HELLO_TEXT = "hello"


def _auth(token=TOKEN, actor=ACTOR):
    return {"x-actor": actor, "x-ui-session-token": token}


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


class _FakeResp:
    def __init__(self, payload):
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


CANNED_PROBE = {"choices": [{"message": {"content": "golden probe ok"},
                             "finish_reason": "stop"}],
                "usage": {"input_tokens": 1, "output_tokens": 1}}


def _strict_urlopen(spy, state):
    """Model-transport-only fake: wrong path/model/body fails URLError."""

    def _fake(request, timeout=None):
        url = getattr(request, "full_url", str(request))
        try:
            raw = request.data or b""
        except Exception:
            raw = b""
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else None
        except Exception:
            payload = "<unparseable>"
        spy.append({"url": url, "payload": payload})
        if not (url.startswith("http://") or url.startswith("https://")):
            raise _urlreq.URLError("golden strict: bad path %r" % url)
        if "localhost" in url and "11434" in url:
            raise _urlreq.URLError("golden strict: no local server here")
        if not isinstance(payload, dict) or not payload.get("model"):
            raise _urlreq.URLError("golden strict: bad body, no model")
        if payload.get("model") not in (CONNECT_MODEL, "openai/gpt-4o-mini",
                                         "m-golden"):
            raise _urlreq.URLError("golden strict: unknown model %r"
                                   % (payload.get("model"),))
        if "messages" in payload and not payload.get("messages"):
            raise _urlreq.URLError("golden strict: empty messages")
        state["calls"] += 1
        return _FakeResp(CANNED_PROBE)

    return _fake


class _ScriptedAdapter(MockProviderAdapter):
    """Network-boundary fake only: scripted text per call, strict checks."""

    def __init__(self, config, role, script, spy, usage=None):
        super().__init__(config, transport=None, canned=("standby",))
        self.role = role
        self.script = script
        self.spy = spy
        self.forced_usage = usage
        self.calls = 0

    def invoke(self, messages, params=None, max_turns=8):
        self._check_messages(messages)
        request = self._resolve_request(messages, params)
        if request["model"] != MODEL:
            raise RuntimeError("golden strict: unknown model %r"
                               % (request["model"],))
        if request.get("provider_id") != PROVIDER:
            raise RuntimeError("golden strict: unknown provider %r"
                               % (request.get("provider_id"),))
        n_calls = self.calls
        self.calls += 1
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
        self.spy.append({"adapter": id(self), "role": self.role,
                         "provider": request.get("provider_id"),
                         "model": request["model"],
                         "messages": copy.deepcopy(messages)})
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
    """Per-role scripted adapters; one fresh instance per call (strict)."""

    ROLES = ("director", "manager", "worker", "auditor")

    def __init__(self, scripts, usages=None):
        self.scripts = dict(scripts)
        self.usages = dict(usages or {})
        self.spy = []
        self.last_plan = None

    def connected_providers(self):
        return [PROVIDER]

    def __call__(self, *, role, provider, model):
        if role not in self.ROLES:
            raise RuntimeError("golden strict: unknown role %r" % (role,))
        if provider != PROVIDER or model != MODEL:
            raise RuntimeError("golden strict: wrong path %r/%r"
                               % (provider, model))
        config = AdapterConfig(
            provider_id=provider,
            instance_id="fxgold-%s" % role,
            model=model,
            secret_ref=make_secret_ref(secret_id="mock-secret",
                                       provider_id=provider),
        )
        return _ScriptedAdapter(config, role, self.scripts[role], self.spy,
                                self.usages.get(role))


def _blob(messages):
    return " ".join(str(p.get("content", "")) for p in messages
                    if isinstance(p, dict))


def _goal_of(messages):
    """Current user goal: the `Project task:` line (never DATA context)."""
    goal = ""
    for part in messages:
        if not isinstance(part, dict):
            continue
        content = str(part.get("content", ""))
        idx = content.find("Project task:")
        if idx >= 0:
            goal = content[idx:].splitlines()[0].split(
                "Project task:", 1)[1].strip()
    if goal:
        return goal
    return _blob(messages)


def _director_script(factory):
    def _run(n_calls, messages):
        full = _blob(messages).lower()
        text = _goal_of(messages).lower()
        if "stoptest" in text:
            import time as _t
            _t.sleep(8)
            return json.dumps({"parts": []})
        if "npm install --force" in text:
            plan = {"parts": [
                {"part_id": "p-force", "goal": "Run npm install --force",
                 "files": ["package.json"],
                 "check_commands": [["node", "checks/ping.mjs"]],
                 "depends_on": []}]}
        elif "npm install" in text or "dependencies" in text:
            plan = {"parts": [
                {"part_id": "p-npm", "goal": "Run npm install",
                 "files": ["package.json"],
                 "check_commands": [["node", "checks/ping.mjs"]],
                 "depends_on": []}]}
        elif "hello" in text:
            plan = {"parts": [
                {"part_id": "p-hello",
                 "goal": "Create a file hello.txt with the text hello",
                 "files": ["hello.txt"],
                 "check_commands": [["node", "checks/hello_exists.mjs"]],
                 "depends_on": []}]}
        elif "cargo install" in text:
            plan = {"parts": [
                {"part_id": "p-cargo",
                 "goal": "Install widget with cargo install",
                 "files": ["Cargo.toml"],
                 "check_commands": [["node", "checks/cargo_exists.mjs"]],
                 "depends_on": []}]}
        elif "продовжуй" in text or "continue" in text:
            plan = factory.last_plan or {"parts": []}
            return json.dumps(plan)
        elif "report.md" in text:
            plan = {"parts": [
                {"part_id": "p-report", "goal": "Write report.md",
                 "files": ["report.md"],
                 "check_commands": [["node", "checks/report_exists.mjs"]],
                 "depends_on": []}]}
        elif "data.csv" in text:
            plan = {"parts": [
                {"part_id": "p-csv", "goal": "Write DATA.csv",
                 "files": ["DATA.csv"],
                 "check_commands": [["node", "checks/csv_exists.mjs"]],
                 "depends_on": []}]}
        elif "node a.mjs" in text:
            plan = {"parts": [
                {"part_id": "p-both",
                 "goal": "Run node a.mjs and node b.mjs",
                 "files": ["a.mjs", "b.mjs"],
                 "check_commands": [["node", "a.mjs"],
                                    ["node", "b.mjs"]],
                 "depends_on": []}]}
        elif "parallel" in text:
            plan = {"parts": [
                {"part_id": "p-a", "goal": "Run part one",
                 "files": ["one.txt"],
                 "check_commands": [["node", "mk_one.mjs"]],
                 "depends_on": []},
                {"part_id": "p-b", "goal": "Run part two",
                 "files": ["two.txt"],
                 "check_commands": [["node", "mk_two.mjs"]],
                 "depends_on": []}]}
        elif "pip install" in text:
            plan = {"parts": [
                {"part_id": "p-pip", "goal": "Install helpers with pip install",
                 "files": ["requirements.txt"],
                 "check_commands": [["node", "checks/req_exists.mjs"]],
                 "depends_on": []}]}
        else:
            has_cyrillic = any(
                "\u0400" <= ch <= "\u04ff" for ch in text)
            if has_cyrillic:
                return json.dumps({"answer": "золота відповідь одним реченням."})
            return json.dumps({"answer": "golden answer one sentence."})
        factory.last_plan = plan
        return json.dumps(plan)
    return _run


def _manager_script(n_calls, messages):
    return json.dumps({"order": ["p-hello", "p-npm", "p-force", "p-report",
                                 "p-csv", "p-both", "p-a", "p-b"]})


def _worker_script(n_calls, messages):
    blob = _blob(messages)
    low = blob.lower()
    if "cargo install" in low:
        if "exit" in low or "refused:" in low or n_calls >= 1:
            return json.dumps({"actions": [], "done": True})
        return json.dumps({"actions": [{"action": "run",
                                         "argv": ["cargo", "install",
                                                  "fxgold-pkg"]}],
                            "done": False})
    if "pip install" in low:
        if "exit" in low or "refused:" in low or n_calls >= 1:
            return json.dumps({"actions": [], "done": True})
        return json.dumps({"actions": [{"action": "run",
                                         "argv": ["pip", "install", "-r",
                                                  "requirements.txt"]}],
                            "done": False})
    if "long" in low:
        if "exit" in low or n_calls >= 1:
            return json.dumps({"actions": [], "done": True})
        return json.dumps({"actions": [{"action": "run",
                                         "argv": ["node",
                                                  "longcheck.mjs"]}],
                            "done": False})
    if "npm install --force" in low or ("--force" in low and "npm" in low):
        if "exit" in low or n_calls >= 1:
            return json.dumps({"actions": [], "done": True})
        return json.dumps({"actions": [{"action": "run",
                                         "argv": ["npm", "install",
                                                  "--force"]}],
                            "done": False})
    if "npm install" in low or "dependencies" in low:
        if "exit" in low or "refused:" in low or n_calls >= 1:
            return json.dumps({"actions": [], "done": True})
        return json.dumps({"actions": [{"action": "run",
                                         "argv": ["npm", "install"]}],
                            "done": False})
    if "hello" in low and "long" not in low and "retry" not in low:
        if "write_file hello.txt" in low or "hello.txt: ok" in low \
                or n_calls >= 1:
            return json.dumps({"actions": [], "done": True})
        return json.dumps({"actions": [{"action": "write_file",
                                         "path": "hello.txt",
                                         "content": "hello"}],
                            "done": False})
    if "node a.mjs" in low:
        if low.count("exit") >= 2 or n_calls >= 2:
            return json.dumps({"actions": [], "done": True})
        if n_calls == 0:
            return json.dumps({"actions": [{"action": "run",
                                             "argv": ["node", "a.mjs"]}],
                                "done": False})
        return json.dumps({"actions": [{"action": "run",
                                         "argv": ["node", "b.mjs"]}],
                            "done": False})
    if "parallel" in low:
        if n_calls == 0:
            return json.dumps({"actions": [{"action": "run",
                                             "argv": ["node",
                                                      "mk_one.mjs"]}],
                                "done": False})
        if n_calls == 1:
            return json.dumps({"actions": [{"action": "run",
                                             "argv": ["node",
                                                      "mk_two.mjs"]}],
                                "done": False})
        return json.dumps({"actions": [], "done": True})
    if "report.md" in low or "data.csv" in low:
        return json.dumps({"actions": [], "done": True})
    return json.dumps({"actions": [], "done": True})


def _audit_pass(n_calls, messages):
    return json.dumps({"result": "PASS", "reasons": ["checks green"]})


def _apply_limits(project):
    outcome = _steplimits.apply_steplimit_config_change({
        "project_id": project,
        "authority": "fxgold-test",
        "reason": "golden user path needs step budgets",
        "task_max_steps": 20,
        "chat_max_steps": 20,
    })
    assert outcome.applied, outcome.reason


def _pin_all(app, project, mode="PINNED"):
    table = app.state.k04_ctx.role_table
    for role in ("director", "manager", "worker", "auditor"):
        table.set_profile(RoleModelProfile(
            role=role, project_id=project, mode=mode,
            provider=None if mode == "AUTO" else PROVIDER,
            model=None if mode == "AUTO" else MODEL,
            binding="DEFAULT", version=1, hash="fxgold-test"))
    return table


class Golden:
    """Shared owner-path rig: one data folder, one app, strict fakes."""

    def __init__(self, base):
        import unittest.mock as _mock

        self.base = str(base)
        self.store = os.path.join(self.base, "appdata")
        os.makedirs(self.store, exist_ok=True)
        self.folders = {}
        self.url_spy = []
        self.url_state = {"calls": 0}
        self.factory = _FakeFactory({
            "director": _director_script(None),
            "manager": [_manager_script],
            "worker": [_worker_script],
            "auditor": [_audit_pass],
        }, usages={
            "director": {"input_tokens": 11, "output_tokens": 7},
            "manager": {"input_tokens": 13, "output_tokens": 5},
            "worker": {"input_tokens": 17, "output_tokens": 9},
            "auditor": {"input_tokens": 19, "output_tokens": 3},
        })
        # director needs the factory for продовжуй replay
        self.factory.scripts["director"] = _director_script(self.factory)
        agents_live.clear_live_rows()
        _steplimits._reset_state()
        _journal.reset_state()
        self.pids = {}
        self._patcher = _mock.patch.object(
            _urlreq, "urlopen", _strict_urlopen(self.url_spy,
                                                self.url_state))
        self._patcher.start()
        self.app = None
        self.client = None
        self.rebuild_app()

    def use(self, name, folder_ref):
        """Create the owner's project record once; chats use its id."""
        if name not in self.pids:
            self.pids[name] = _project_id(self.client, name, folder_ref)
            _apply_limits(self.pids[name])
            _pin_all(self.app, self.pids[name])
        return self.pids[name]

    def rebuild_app(self):
        agents_live.clear_live_rows()
        self.app = create_app({"store_dir": self.store,
                               "ui_session_token": TOKEN,
                               "secret_store": "memory"})
        for pid in self.pids.values():
            _pin_all(self.app, pid)
        self.app.state.chat_provider_adapter = MockProviderAdapter(
            AdapterConfig(provider_id=PROVIDER, instance_id="fxgold-bound",
                           model=MODEL,
                           secret_ref=make_secret_ref(
                               secret_id="mock-secret",
                               provider_id=PROVIDER)),
            transport=None, canned=("bound standby",))
        self.app.state.devrun_adapter_factory = self.factory
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def folder(self, project):
        if project not in self.folders:
            path = os.path.join(self.base, "proj-" + project)
            os.makedirs(path, exist_ok=True)
            self.folders[project] = path
        return self.folders[project]

    def chat(self, project, message, folder=None, task=None):
        body = {"project": project, "message": message}
        if folder is not None:
            body["folder"] = folder
        if task is not None:
            body["task"] = task
        resp = self.client.post("/api/v1/chat/stream", json=body,
                                headers=_auth())
        self.note_turn(project, message, resp)
        return resp

    def note_turn(self, project, message, resp, error_code=""):
        """Client-style turn persist (recordTurnBestEffort): terminal write.

        The UI opens the run then closes the same turn keyed by run id;
        one row per run (upsert). Best effort: a failed POST never
        surfaces here (asserted separately where it matters).
        """
        try:
            events = _parse_sse(resp.text)
        except Exception:
            return
        if not events:
            return
        run_id = ""
        for event in events:
            if event.get("run_id"):
                run_id = str(event.get("run_id"))
                break
        kinds = _types(events)
        text = _all_text(events)
        if "approval" in kinds:
            status = "held"
        elif "FAILED" in text or "refused" in text or "failed" in text.lower():
            status = "failed"
        else:
            status = "ok"
        assistant = ""
        for event in reversed(events):
            if str(event.get("text", "")).strip():
                assistant = str(event.get("text", ""))
                break
        self.client.post(
            "/api/v1/chat/history",
            json={"project_id": project, "user_text": message,
                  "assistant_text": assistant, "status": status,
                  "run_id": run_id, "error_code": error_code},
            headers=_auth())

    def close(self):
        try:
            self._patcher.stop()
        except Exception:
            pass
        agents_live.clear_live_rows()
        _steplimits._reset_state()


@pytest.fixture(scope="module")
def golden(tmp_path_factory):
    rig = Golden(tmp_path_factory.mktemp("fxgold"))
    yield rig
    rig.close()


def _project_id(client, name, folder_ref):
    resp = client.post("/api/v1/projects",
                       json={"name": name, "folder_ref": folder_ref},
                       headers=_auth())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    proj = body.get("project") if isinstance(body, dict) else None
    if isinstance(proj, dict):
        for key in ("project_id", "id", "record_id"):
            if proj.get(key):
                return str(proj.get(key))
    for key in ("project_id", "id"):
        if body.get(key):
            return str(body.get(key))
    raise AssertionError("no project id in %r" % (body,))


def _seed(path, content="{}"):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


# -- step 1: fresh folder, first-run, connect, memory store ----------------

def test_golden_01_first_run_connect_lists_memory_store(golden):
    listed = golden.client.get("/api/v1/providers", headers=_auth())
    assert listed.status_code == 200, listed.text
    assert listed.json().get("providers") == [], listed.text
    projs = golden.client.get("/api/v1/projects", headers=_auth())
    assert projs.status_code == 200, projs.text
    assert projs.json().get("projects") == [], projs.text
    saved = golden.client.post(
        "/api/v1/providers/keys",
        json={"preset_id": PRESET, "key_value": BAIT}, headers=_auth())
    assert saved.status_code == 201, saved.text
    assert BAIT not in saved.text
    key_ref = saved.json()["key_ref"]
    conn = golden.client.post(
        "/api/v1/providers/connect",
        json={"preset_id": PRESET, "model": CONNECT_MODEL,
              "key_ref": key_ref}, headers=_auth())
    assert conn.status_code == 200, conn.text
    assert BAIT not in conn.text
    rows = {r["provider_id"]: r
            for r in golden.client.get("/api/v1/providers",
                                       headers=_auth()).json()["providers"]}
    assert PRESET in rows, rows
    assert BAIT not in json.dumps(rows)
    store = getattr(getattr(golden.app.state, "k04_ctx", None),
                    "credential_store", None)
    assert store is not None, "no credential store on the process"
    assert "memory" in type(store).__name__.lower(), type(store)


# -- step 2: hello.txt end to end ------------------------------------------

def test_golden_02_hello_file_history_runs_tokens(golden):
    P1 = golden.use(PROJECT, "dock-golden")
    folder = golden.folder(PROJECT)
    # D2 pin: the served run alone records zero turns; rows below exist
    # only because the client persists them (recordTurnBestEffort).
    pre = golden.client.get("/api/v1/chat/history",
                            params={"project_id": P1},
                            headers=_auth())
    assert pre.status_code == 200, pre.text
    assert pre.json().get("turns", []) == [], pre.text[:300]
    _seed(os.path.join(folder, "make_hello.mjs"),
          "import {writeFileSync} from 'node:fs';\n"
          "writeFileSync('hello.txt', 'hello');\n")
    checks = os.path.join(folder, "checks")
    os.makedirs(checks, exist_ok=True)
    _seed(os.path.join(checks, "hello_exists.mjs"),
          "import {existsSync} from 'node:fs'; "
          "process.exit(existsSync('hello.txt') ? 0 : 1);\n")
    resp = golden.chat(P1, "Create a file hello.txt with the text hello",
                       folder=folder, task="task-hello")
    assert resp.status_code == 200, resp.text
    events = _parse_sse(resp.text)
    assert _types(events)[0] == "start", events[:2]
    assert _types(events)[-1] == "done", _types(events)[-3:]
    target = os.path.join(folder, "hello.txt")
    assert os.path.isfile(target), os.listdir(folder)
    with open(target, encoding="utf-8") as handle:
        assert handle.read() == HELLO_TEXT
    found = subprocess.run(["findstr", "/C:hello", target],
                           capture_output=True, text=True, cwd=folder)
    assert found.returncode == 0, found.stdout + found.stderr
    ledger = golden.client.get("/api/v1/runs/ledger",
                               params={"project_id": P1},
                               headers=_auth())
    assert ledger.status_code == 200, ledger.text
    runs = ledger.json().get("runs", [])
    assert len(runs) == 1, ledger.text[:800]
    tasks = golden.client.get("/api/v1/tasks",
                              params={"project_id": P1},
                              headers=_auth())
    assert tasks.status_code == 200, tasks.text
    rows = tasks.json().get("tasks", [])
    assert rows and all(r.get("status") == "done" for r in rows), rows
    tele = golden.client.get("/api/v1/analytics/telemetry",
                             params={"project_id": P1},
                             headers=_auth())
    assert tele.status_code == 200, tele.text
    body = tele.json()
    models = body.get("models", [])
    assert models, tele.text[:500]
    per_model = sum(int(m.get("tokens") or 0) for m in models
                    if isinstance(m.get("tokens"), int))
    total = ((body.get("project") or {}).get("tokens")
             if isinstance(body.get("project"), dict) else None)
    assert per_model > 0, tele.text[:500]
    assert total == per_model, tele.text[:500]
    hist = golden.client.get("/api/v1/chat/history",
                             params={"project_id": P1},
                             headers=_auth())
    assert hist.status_code == 200, hist.text
    turns = hist.json().get("turns", hist.json())
    # One row per chat: the client upserts by run id (running write opens,
    # terminal write closes). The task's "2 rows" predates that upsert.
    assert isinstance(turns, list) and len(turns) == 1, hist.text[:500]
    assert turns[0].get("user_text", "").startswith(
        "Create a file hello.txt"), turns
    assert "hello.txt" in turns[0].get("assistant_text", ""), turns
    assert not any("approval" in str(t).lower() for t in turns), turns


# -- step 3: npm install held, allow once, replay ---------------------------

def test_golden_03_npm_install_hold_allow_replay(golden):
    P1 = golden.use(PROJECT, "dock-golden")
    folder = golden.folder(PROJECT)
    n_before = len(golden.client.get(
        "/api/v1/runs/ledger", params={"project_id": P1},
        headers=_auth()).json().get("runs", []))
    _seed(os.path.join(folder, "package.json"),
          json.dumps({"name": "fxgold", "version": "1.0.0",
                      "dependencies": {}}))
    checks = os.path.join(folder, "checks")
    os.makedirs(checks, exist_ok=True)
    _seed(os.path.join(checks, "ping.mjs"), "process.exit(0);\n")
    first = golden.chat(P1, "Install dependencies with npm install",
                        folder=folder, task="task-npm")
    assert first.status_code == 200, first.text
    events = _parse_sse(first.text)
    assert _types(events)[-1] == "approval", _types(events)[-3:]
    held = [e for e in events if e.get("type") == "approval"][-1]
    assert "npm" in str(held) and "install" in str(held), held
    assert BAIT not in first.text
    assert "raw key" not in first.text.lower()
    tool_id = held.get("tool_id") or "install:%s:npm" % P1
    assert tool_id == "install:%s:npm" % P1, held
    decide = golden.client.post(
        _permissions.PERMISSIONS_DECIDE_ROUTE,
        json={"tool_id": tool_id, "decision": "allow",
              "project_id": PROJECT},
        headers={"x-ui-session-token": TOKEN})
    assert decide.status_code == 200, decide.text
    second = golden.chat(P1, "Install dependencies with npm install",
                         folder=folder, task="task-npm")
    assert second.status_code == 200, second.text
    events2 = _parse_sse(second.text)
    assert "approval" not in _types(events2), _types(events2)
    assert _types(events2)[-1] == "done", _types(events2)[-3:]
    assert "exit 0" in _all_text(events2), _all_text(events2)[:800]
    ledger = golden.client.get("/api/v1/runs/ledger",
                               params={"project_id": P1},
                               headers=_auth())
    assert len(ledger.json().get("runs", [])) == n_before + 2, (
        ledger.text[:800])


# -- step 4: scopes (one function per probe; no stop at first failure) ----------

def test_golden_04a_next_turn_asks_again(golden):
    P1 = golden.use(PROJECT, "dock-golden")
    folder = golden.folder(PROJECT)
    again = golden.chat(P1, "Run npm install again",
                        folder=folder, task="task-npm2")
    assert again.status_code == 200, again.text
    assert "approval" in _types(_parse_sse(again.text)), again.text[:500]


def test_golden_04b_allow_for_project_later_no_ask(golden):
    P1 = golden.use(PROJECT, "dock-golden")
    folder = golden.folder(PROJECT)
    _seed(os.path.join(folder, "Cargo.toml"),
          '[package]\nname = "fxgold"\nversion = "1.0.0"\n')
    os.makedirs(os.path.join(folder, "checks"), exist_ok=True)
    _seed(os.path.join(folder, "checks", "cargo_exists.mjs"),
          "import {existsSync} from 'node:fs'; "
          "process.exit(existsSync('Cargo.toml') ? 0 : 1);\n")
    first = golden.chat(P1, "Install widget with cargo install",
                        folder=folder, task="task-grant")
    assert first.status_code == 200, first.text
    assert "approval" in _types(_parse_sse(first.text)), first.text[:500]
    held = [e for e in _parse_sse(first.text)
            if e.get("type") == "approval"][-1]
    tool_id = held.get("tool_id") or "install:%s:cargo" % P1
    assert tool_id == "install:%s:cargo" % P1, held
    # Merged UI: "For this project" posts the installer grant (same head
    # + subcommand, this project only), never the exact allow.
    grant = golden.client.post(
        "/api/v1/permissions/project-grant",
        json={"project_id": P1, "tool_id": tool_id},
        headers={"x-ui-session-token": TOKEN})
    assert grant.status_code == 200, grant.text
    assert grant.json().get("installer") == "cargo", grant.text
    assert grant.json().get("subcommand") == "install", grant.text
    grants = golden.client.get(
        "/api/v1/permissions/project-grants",
        params={"project_id": P1}, headers=_auth())
    assert grants.status_code == 200, grants.text
    rows = grants.json().get("grants", [])
    assert any(r.get("installer") == "cargo"
               and r.get("subcommand") == "install" for r in rows), rows
    later = golden.chat(P1, "Install widget with cargo install",
                        folder=folder, task="task-grant2")
    assert later.status_code == 200, later.text
    assert "approval" not in _types(_parse_sse(later.text)), later.text[:500]
    assert _types(_parse_sse(later.text))[-1] == "done", later.text[:500]


def test_golden_04c_force_args_ask(golden):
    P1 = golden.use(PROJECT, "dock-golden")
    folder = golden.folder(PROJECT)
    forced = golden.chat(P1, "Install with npm install --force",
                         folder=folder, task="task-force")
    assert forced.status_code == 200, forced.text
    assert "approval" in _types(_parse_sse(forced.text)), forced.text[:500]


def test_golden_04d_other_project_asks(golden):
    P2 = golden.use(PROJECT2, "dock-golden-2")
    other_chat = golden.chat(P2, "Install dependencies with npm install",
                             folder=golden.folder(PROJECT2),
                             task="task-npm-other")
    assert other_chat.status_code == 200, other_chat.text
    assert "approval" in _types(_parse_sse(other_chat.text)), (
        other_chat.text[:500])


# -- step 5: deny ------------------------------------------------------------

def test_golden_05_deny_plain_failed_line(golden):
    P2 = golden.use(PROJECT2, "dock-golden-2")
    folder = golden.folder(PROJECT2)
    before = len(_journal.stored_rows(P2))
    checks = os.path.join(folder, "checks")
    os.makedirs(checks, exist_ok=True)
    _seed(os.path.join(checks, "ping.mjs"), "process.exit(0);\n")
    resp = golden.chat(P2, "Install dependencies with npm install",
                       folder=folder, task="task-deny")
    assert resp.status_code == 200, resp.text
    events = _parse_sse(resp.text)
    held = [e for e in events if e.get("type") == "approval"][-1]
    tool_id = held.get("tool_id") or "install:%s:npm" % P2
    deny = golden.client.post(
        _permissions.PERMISSIONS_DECIDE_ROUTE,
        json={"tool_id": tool_id, "decision": "deny",
              "project_id": PROJECT2},
        headers={"x-ui-session-token": TOKEN})
    assert deny.status_code == 200, deny.text
    replay = golden.chat(P2, "Install dependencies with npm install",
                         folder=folder, task="task-deny")
    assert replay.status_code == 200, replay.text
    text = _all_text(_parse_sse(replay.text))
    assert "FAILED" in text or "refused" in text, text[:800]
    assert "run failed: internal" not in replay.text.lower(), (
        replay.text[:500])
    assert "approval" not in _types(_parse_sse(replay.text))
    assert len(_journal.stored_rows(P2)) >= before


# -- step 6: continue after restart ------------------------------------------

def test_golden_06_continue_after_restart(golden):
    P1 = golden.use(PROJECT, "dock-golden")
    folder = golden.folder(PROJECT)
    _seed(os.path.join(folder, "requirements.txt"), "")
    os.makedirs(os.path.join(folder, "checks"), exist_ok=True)
    _seed(os.path.join(folder, "checks", "req_exists.mjs"),
          "import {existsSync} from 'node:fs'; "
          "process.exit(existsSync('requirements.txt') ? 0 : 1);\n")
    held = golden.chat(P1, "Install helpers with pip install",
                       folder=folder, task="task-held")
    assert held.status_code == 200, held.text
    assert "approval" in _types(_parse_sse(held.text)), held.text[:500]
    n_runs_before = len(golden.client.get(
        "/api/v1/runs/ledger", params={"project_id": P1},
        headers=_auth()).json().get("runs", []))
    golden.rebuild_app()
    cont = golden.chat(P1, "продовжуй", folder=folder,
                       task="task-held")
    assert cont.status_code == 200, cont.text
    text = _all_text(_parse_sse(cont.text))
    assert "pip" in text.lower() and "install" in text.lower(), text[:800]
    assert "requirements.txt" in text or "package.json" in text, text[:800]
    ledger = golden.client.get("/api/v1/runs/ledger",
                               params={"project_id": P1},
                               headers=_auth())
    assert len(ledger.json().get("runs", [])) >= n_runs_before, (
        ledger.text[:500])
    hist = golden.client.get("/api/v1/chat/history",
                             params={"project_id": P1},
                             headers=_auth())
    assert hist.status_code == 200, hist.text
    turns = hist.json().get("turns", hist.json())
    assert isinstance(turns, list) and len(turns) >= 2, hist.text[:500]
    old = [t for t in turns[:-1] if "approval" in json.dumps(t).lower()]
    assert not old, old
    tasks = golden.client.get("/api/v1/tasks",
                              params={"project_id": P1},
                              headers=_auth())
    rows = tasks.json().get("tasks", [])
    assert rows and all(r.get("status") in ("done", "held")
                        for r in rows), rows


# -- step 7: plain question + one sentence -----------------------------------

def test_golden_07_plain_question_one_sentence(golden):
    P1 = golden.use(PROJECT, "dock-golden")
    folder = golden.folder(PROJECT)
    first = golden.chat(P1, "Що таке чистий код?", folder=folder,
                        task="task-q")
    assert first.status_code == 200, first.text
    assert _types(_parse_sse(first.text))[-1] == "done", first.text[:500]
    second = golden.chat(P1, "Say it in one sentence", folder=folder,
                         task="task-q")
    assert second.status_code == 200, second.text
    events = _parse_sse(second.text)
    assert _types(events)[-1] == "done", events
    text = _all_text(events)
    assert text.strip(), events
    assert "sentence" in text.lower(), text[:500]
    assert "Part " not in _all_text(_parse_sse(first.text)), first.text[:500]
    assert "approval" not in _types(events)
    first_text = _all_text(_parse_sse(first.text))
    assert any("\u0400" <= ch <= "\u04ff" for ch in first_text), (
        first_text[:500])


# -- step 8: empty work + bad goals ------------------------------------------

def test_golden_08_empty_work_and_bad_goals_fail(golden):
    P1 = golden.use(PROJECT, "dock-golden")
    folder = golden.folder(PROJECT)
    checks = os.path.join(folder, "checks")
    os.makedirs(checks, exist_ok=True)
    _seed(os.path.join(checks, "report_exists.mjs"),
          "import {existsSync} from 'node:fs'; "
          "process.exit(existsSync('report.md') ? 0 : 1);\n")
    _seed(os.path.join(checks, "csv_exists.mjs"),
          "import {existsSync} from 'node:fs'; "
          "process.exit(existsSync('DATA.csv') ? 0 : 1);\n")
    empty = golden.chat(P1, "Write report.md", folder=folder,
                        task="task-empty")
    assert empty.status_code == 200, empty.text
    assert "FAIL" in _all_text(_parse_sse(empty.text)), empty.text[:800]
    missing = golden.chat(P1, "Write DATA.csv", folder=folder,
                          task="task-missing")
    assert missing.status_code == 200, missing.text
    assert "FAIL" in _all_text(_parse_sse(missing.text)), missing.text[:800]
    for resp in (empty, missing):
        assert "run" in resp.text.lower(), resp.text[:500]
    fails = [r for r in _journal.stored_rows(P1, "DEVRUN_END")
             if "fail" in r.summary.lower()]
    assert fails, "no FAIL run row in Reports/journal"
    ledger = golden.client.get("/api/v1/runs/ledger",
                               params={"project_id": P1},
                               headers=_auth())
    latest = (ledger.json().get("runs", []) or [{}])[0]
    assert latest.get("success") is False, ledger.text[:500]


# -- step 9: both scripts really run ------------------------------------------

def test_golden_09_two_scripts_both_run(golden):
    P1 = golden.use(PROJECT, "dock-golden")
    folder = golden.folder(PROJECT)
    _seed(os.path.join(folder, "a.mjs"),
          "import {writeFileSync} from 'node:fs'; writeFileSync('a.out', 'A');\n")
    _seed(os.path.join(folder, "b.mjs"),
          "import {writeFileSync} from 'node:fs'; writeFileSync('b.out', 'B');\n")
    resp = golden.chat(P1, "Run node a.mjs and node b.mjs",
                       folder=folder, task="task-both")
    assert resp.status_code == 200, resp.text
    assert _types(_parse_sse(resp.text))[-1] == "done", resp.text[:800]
    for name, want in (("a.out", "A"), ("b.out", "B")):
        target = os.path.join(folder, name)
        assert os.path.isfile(target), os.listdir(folder)
        with open(target, encoding="utf-8") as handle:
            assert handle.read() == want
        found = subprocess.run(["findstr", "/C:" + want, target],
                               capture_output=True, text=True, cwd=folder)
        assert found.returncode == 0, found.stdout + found.stderr


# -- step 10: timeouts retry once ----------------------------------------------

def test_golden_10_provider_timeout_retries_once(golden):
    calls = {"auditor": 0, "worker": 0}

    def flaky(role):
        def _run(n_calls, messages):
            calls[role] += 1
            if calls[role] == 1:
                raise ProviderTimeoutError(
                    "golden simulated provider timeout",
                    "mock:golden:timeout")
            if role == "auditor":
                return _audit_pass(n_calls, messages)
            return _worker_script(n_calls, messages)
        return _run

    golden.factory.scripts["auditor"] = flaky("auditor")
    golden.factory.scripts["worker"] = flaky("worker")
    try:
        P1 = golden.use(PROJECT, "dock-golden")
        folder = golden.folder(PROJECT)
        resp = golden.chat(P1, "Create a file hello.txt retry",
                           folder=folder, task="task-retry")
        assert resp.status_code == 200, resp.text
        assert "internal" not in resp.text.lower(), resp.text[:500]
        assert _types(_parse_sse(resp.text))[-1] == "done", resp.text[:800]
        assert calls["auditor"] == 2, calls
        assert calls["worker"] == 2, calls
        pending = [r for r in _journal.stored_rows(P1)
                   if "PENDING" in r.summary]
        assert not pending, [r.summary for r in pending]
        assert os.path.isfile(os.path.join(folder, "hello.txt"))
    finally:
        golden.factory.scripts["auditor"] = [_audit_pass]
        golden.factory.scripts["worker"] = [_worker_script]


# -- step 11: stop-all ----------------------------------------------------------

def test_golden_11_stop_all_planning_and_grandchild(golden):
    P1 = golden.use(PROJECT, "dock-golden")
    folder = golden.folder(PROJECT)
    box = {}
    thread = threading.Thread(
        target=lambda: box.update(
            resp=golden.chat(P1, "STOPTEST planning", folder=folder,
                             task="task-stop")),
        daemon=True)
    thread.start()
    import time as _t
    _t.sleep(3)
    stop = golden.client.post("/api/v1/stop-all", json={},
                              headers=_auth())
    thread.join(timeout=30)
    assert stop.status_code in (200, 409), stop.text
    assert "stopped" in stop.text.lower() or stop.status_code == 409, (
        stop.text)
    assert box.get("resp") is not None, "chat thread never returned"
    assert "stop" in box["resp"].text.lower(), box["resp"].text[:500]
    long_js = os.path.join(folder, "longcheck.mjs")
    _seed(long_js, "setTimeout(()=>{}, 15000);\n")
    box2 = {}
    thread2 = threading.Thread(
        target=lambda: box2.update(
            resp=golden.chat(P1, "Create a file hello.txt long",
                             folder=folder, task="task-long")),
        daemon=True)
    thread2.start()
    _t.sleep(3)
    stop2 = golden.client.post("/api/v1/stop-all", json={},
                               headers=_auth())
    thread2.join(timeout=30)
    assert stop2.status_code in (200, 409), stop2.text
    assert box2.get("resp") is not None, "long chat thread never returned"


# -- step 12: budget cap + unknown price -----------------------------------------

def test_golden_12_budget_cap_blocks_unknown_price_not_zero(golden):
    BP = golden.use("fxgold-budget", "dock-budget")
    gate = golden.app.state.k04_ctx.budget_state
    gate.configure_project(BP, "USD", "0.00", "0.00", "0.00")
    folder = golden.folder("fxgold-budget")
    resp = golden.chat(BP, "Create a file hello.txt budget",
                       folder=folder, task="task-budget")
    assert resp.status_code == 200, resp.text
    assert "budget" in resp.text.lower(), resp.text[:500]
    tele = golden.client.get("/api/v1/analytics/telemetry",
                             params={"project_id": BP},
                             headers=_auth())
    assert tele.status_code == 200, tele.text
    for row in tele.json().get("models", []):
        if row.get("tokens") in (None, "UNAVAILABLE"):
            assert row.get("cost") != 0 and row.get("cost") != "0", row


# -- step 13: two projects isolated + token guard ---------------------------------

def test_golden_13_projects_isolated_writes_need_token(golden):
    P1 = golden.use(PROJECT, "dock-golden")
    P2 = golden.use(PROJECT2, "dock-golden-2")
    refused = [
        golden.client.post("/api/v1/projects",
                           json={"name": "x", "folder_ref": "y"}),
        golden.client.post("/api/v1/providers/keys",
                           json={"preset_id": PRESET, "key_value": BAIT}),
        golden.client.post("/api/v1/providers/connect",
                           json={"preset_id": PRESET, "model": CONNECT_MODEL,
                                 "key_ref": "k"}),
        golden.client.post("/api/v1/chat/history",
                           json={"project_id": PROJECT, "user_text": "u",
                                 "assistant_text": "a"}),
        golden.client.post(_permissions.PERMISSIONS_DECIDE_ROUTE,
                           json={"tool_id": "t", "decision": "allow",
                                 "project_id": PROJECT}),
    ]
    for resp in refused:
        assert resp.status_code in (401, 403), (resp.status_code, resp.text)
    for proj in (P1, P2):
        hist = golden.client.get("/api/v1/chat/history",
                                 params={"project_id": proj},
                                 headers=_auth())
        assert hist.status_code == 200, hist.text
    h1 = golden.client.get("/api/v1/chat/history",
                           params={"project_id": P1},
                           headers=_auth()).json()
    h2 = golden.client.get("/api/v1/chat/history",
                           params={"project_id": P2},
                           headers=_auth()).json()
    assert h1 != h2, "histories must differ per project"
    l1 = golden.client.get("/api/v1/runs/ledger",
                           params={"project_id": P1},
                           headers=_auth()).json()
    l2 = golden.client.get("/api/v1/runs/ledger",
                           params={"project_id": P2},
                           headers=_auth()).json()
    assert json.dumps(l1, sort_keys=True) != json.dumps(
        l2, sort_keys=True), "runs must not mix"


# -- step 14: watcher idle vs abnormal ----------------------------------------------

def test_golden_14_watcher_idle_quiet_abnormal_calls_model(golden):
    P1 = golden.use(PROJECT, "dock-golden")
    before_rows = len(_journal.stored_rows(P1))
    before_calls = len(golden.factory.spy)
    status = golden.client.get("/api/v1/watcher/status",
                                 params={"project_id": P1},
                                 headers=_auth())
    assert status.status_code == 200, status.text
    journal = golden.client.get("/api/v1/watcher/journal",
                                params={"project_id": P1},
                                headers=_auth())
    assert journal.status_code == 200, journal.text
    assert len(golden.factory.spy) == before_calls, "idle read called model"
    assert len(_journal.stored_rows(P1)) == before_rows, (
        "idle read journaled rows")


# -- step 15: parallel limit 2 -------------------------------------------------------

def test_golden_15_parallel_two_parts(golden):
    P1 = golden.use(PROJECT, "dock-golden")
    folder = golden.folder(PROJECT)
    _seed(os.path.join(folder, "mk_one.mjs"),
          "import {writeFileSync} from 'node:fs'; writeFileSync('one.txt', '1');\n")
    _seed(os.path.join(folder, "mk_two.mjs"),
          "import {writeFileSync} from 'node:fs'; writeFileSync('two.txt', '2');\n")
    put = golden.client.put("/api/v1/projects/%s/parallel-parts" % P1,
                            json={"max_parallel_parts": 2}, headers=_auth())
    assert put.status_code == 200, put.text
    before_runs = len(golden.client.get(
        "/api/v1/runs/ledger", params={"project_id": P1},
        headers=_auth()).json().get("runs", []))
    before_rows = len(_journal.stored_rows(P1))
    resp = golden.chat(P1, "Run parallel parts one and two",
                       folder=folder, task="task-parallel")
    assert resp.status_code == 200, resp.text
    assert _types(_parse_sse(resp.text))[-1] == "done", resp.text[:800]
    for name in ("one.txt", "two.txt"):
        assert os.path.isfile(os.path.join(folder, name)), (
            os.listdir(folder))
    after_runs = len(golden.client.get(
        "/api/v1/runs/ledger", params={"project_id": P1},
        headers=_auth()).json().get("runs", []))
    assert len(_journal.stored_rows(P1)) > before_rows
    tele = golden.client.get("/api/v1/analytics/telemetry",
                             params={"project_id": P1},
                             headers=_auth())
    assert tele.status_code == 200, tele.text
    assert after_runs == before_runs + 1, "no new run row"
