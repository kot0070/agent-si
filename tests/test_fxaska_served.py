"""FXASKA served proof: install asks once and the decision is recorded.

A1: the decision ledger in agent_si.toolguard.permissions round-trips
allow/deny values keyed by tool id ({decision, time, project}), reads
unknown ids as none, and survives a reload from the store dir.
A2: POST /api/v1/permissions/decide records one decision (session
token required, bad decision 400) and appends one PERMISSION_DECISION
journal row naming the tool plus the decision; GET
/api/v1/permissions/decisions?project_id= lists them. A3:
spawn_checked asks (InstallAskNeeded, a PermissionError carrying
today's text), runs on allow, and refuses on deny with today's text;
the engine raises _InstallHeld on the ask so the run holds for approval
(status line plus terminal approval event), never as run text. Served
cases drive the real app built by create_app over HTTP; spawn cases
call the real spawn_checked in a temp folder. Durable collateral: kept
and updated whenever this behavior changes.
"""

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

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.runtime.devrun import actions as _actions  # noqa: E402
from agent_si.runtime.devrun import engine as _engine  # noqa: E402
from agent_si.toolguard import permissions as _permissions  # noqa: E402
from agent_si.watcher import journal as _journal  # noqa: E402

TOKEN = "fxaska-served-token"

INSTALL_NONE_TEXT = (
    "refused: install-class command %r needs install "
    "permission (ungranted runs continue without the install)"
)
INLINE_TEXT = (
    "refused: inline code needs approval first "
    "(unapproved runs continue without it)"
)


@pytest.fixture(autouse=True)
def _clean_journal():
    _journal.reset_state()
    yield
    _journal.reset_state()


def _client(tmp_path, token=TOKEN):
    store = tmp_path / "store"
    store.mkdir(exist_ok=True)
    settings = {"ui_session_token": token, "store_dir": str(store)}
    return TestClient(create_app(dict(settings))), token


def _decide(client, token, tool_id, decision, project_id):
    return client.post(
        _permissions.PERMISSIONS_DECIDE_ROUTE,
        json={"tool_id": tool_id, "decision": decision,
              "project_id": project_id},
        headers={"x-ui-session-token": token},
    )


def test_a1_decision_ledger_round_trip_and_reload(tmp_path):
    store = str(tmp_path / "store")
    memory: dict = {}
    tool_id = "install:proj-a1:pip"
    record = _permissions.record_decision(
        store, memory, tool_id, "allow", "proj-a1")
    assert record["decision"] == "allow"
    assert record["project"] == "proj-a1"
    assert isinstance(record["time"], str) and record["time"]
    assert _permissions.get_decision(store, memory, tool_id) == "allow"
    assert _permissions.get_decision(
        store, memory, "install:proj-a1:other") is None
    names = os.listdir(store)
    assert _permissions.DECISIONS_FILENAME in names
    assert [name for name in names if name.endswith(".tmp")] == []
    ledger_path = os.path.join(store, _permissions.DECISIONS_FILENAME)
    with open(ledger_path, encoding="utf-8") as handle:
        payload = json.load(handle)
    assert payload[tool_id] == record
    reloaded = _permissions.load_decisions(store)
    assert reloaded[tool_id]["decision"] == "allow"
    assert _permissions.get_decision(store, {}, tool_id) == "allow"


def test_a1_bad_decision_refused(tmp_path):
    store = str(tmp_path / "store")
    memory: dict = {}
    with pytest.raises(_permissions.PermissionCheckError) as excinfo:
        _permissions.record_decision(
            store, memory, "install:proj-a1:pip", "maybe", "proj-a1")
    assert excinfo.value.status == 400
    assert _permissions.get_decision(
        store, memory, "install:proj-a1:pip") is None


def test_a1_deny_decision_recorded(tmp_path):
    store = str(tmp_path / "store")
    memory: dict = {}
    _permissions.record_decision(
        store, memory, "install:proj-a1:pip", "deny", "proj-a1")
    assert _permissions.get_decision(
        store, memory, "install:proj-a1:pip") == "deny"


def test_a2_decide_200_journal_row_and_list(tmp_path):
    client, token = _client(tmp_path)
    tool_id = "install:proj-a2:cargo"
    resp = _decide(client, token, tool_id, "allow", "proj-a2")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tool_id"] == tool_id
    assert body["decision"] == "allow"
    assert body["project_id"] == "proj-a2"
    assert isinstance(body["time"], str) and body["time"]
    rows = _journal.stored_rows("proj-a2")
    assert len(rows) == 1
    assert "PERMISSION_DECISION" in rows[0].summary
    assert tool_id in rows[0].summary
    assert "allow" in rows[0].summary
    listed = client.get(
        _permissions.PERMISSIONS_DECISIONS_ROUTE,
        params={"project_id": "proj-a2"})
    assert listed.status_code == 200, listed.text
    decisions = listed.json()["decisions"]
    assert decisions == [{
        "tool_id": tool_id, "decision": "allow",
        "project": "proj-a2", "time": body["time"],
    }]


def test_a2_decide_deny_lists_deny(tmp_path):
    client, token = _client(tmp_path)
    tool_id = "install:proj-a2d:pip"
    resp = _decide(client, token, tool_id, "deny", "proj-a2d")
    assert resp.status_code == 200, resp.text
    listed = client.get(
        _permissions.PERMISSIONS_DECISIONS_ROUTE,
        params={"project_id": "proj-a2d"})
    assert listed.status_code == 200, listed.text
    decisions = listed.json()["decisions"]
    assert [row["decision"] for row in decisions
            if row["tool_id"] == tool_id] == ["deny"]


def test_a2_decide_bad_decision_400(tmp_path):
    client, token = _client(tmp_path)
    resp = _decide(client, token, "install:proj-a2:pip", "maybe", "proj-a2")
    assert resp.status_code == 400, resp.text
    assert _journal.stored_rows("proj-a2") == ()


def test_a2_decide_missing_token_401(tmp_path):
    client, _token = _client(tmp_path)
    resp = client.post(
        _permissions.PERMISSIONS_DECIDE_ROUTE,
        json={"tool_id": "install:proj-a2:pip", "decision": "allow",
              "project_id": "proj-a2"})
    assert resp.status_code == 401, resp.text


def test_a2_decide_wrong_token_403(tmp_path):
    client, _token = _client(tmp_path)
    resp = client.post(
        _permissions.PERMISSIONS_DECIDE_ROUTE,
        json={"tool_id": "install:proj-a2:pip", "decision": "allow",
              "project_id": "proj-a2"},
        headers={"x-ui-session-token": "wrong-token"})
    assert resp.status_code == 403, resp.text


def test_a2_decisions_needs_project(tmp_path):
    client, _token = _client(tmp_path)
    missing = client.get(_permissions.PERMISSIONS_DECISIONS_ROUTE)
    assert missing.status_code == 400, missing.text
    empty = client.get(
        _permissions.PERMISSIONS_DECISIONS_ROUTE,
        params={"project_id": "proj-a2-unknown"})
    assert empty.status_code == 200, empty.text
    assert empty.json() == {"decisions": []}


def test_a3_install_without_decision_asks(tmp_path):
    _client(tmp_path)
    folder = str(tmp_path / "work")
    os.makedirs(folder, exist_ok=True)
    log_path = os.path.join(folder, "logs", "spawn.log")
    with pytest.raises(_actions.InstallAskNeeded) as excinfo:
        _actions.spawn_checked(
            "proj-a3-none", "run-1", folder,
            ["cargo", "install", "fake-pkg"], log_path, "logs/spawn.log")
    assert isinstance(excinfo.value, PermissionError)
    assert str(excinfo.value) == INSTALL_NONE_TEXT % "cargo"
    assert excinfo.value.tool_id == "install:proj-a3-none:cargo"


def test_a3_allow_runs_fake_installer(tmp_path, monkeypatch):
    client, token = _client(tmp_path)
    project = "proj-a3-allow"
    tool_id = "install:" + project + ":cargo"
    resp = _decide(client, token, tool_id, "allow", project)
    assert resp.status_code == 200, resp.text
    bindir = tmp_path / "bin"
    bindir.mkdir()
    shutil.copy(r"C:\Windows\System32\where.exe",
                str(bindir / "cargo.exe"))
    monkeypatch.setenv("PATH", str(bindir) + os.pathsep
                       + os.environ.get("PATH", ""))
    folder = str(tmp_path / "work")
    os.makedirs(folder, exist_ok=True)
    log_path = os.path.join(folder, "logs", "spawn.log")
    row = _actions.spawn_checked(
        project, "run-allow", folder, ["cargo", "install", "fake-pkg"],
        log_path, "logs/spawn.log")
    assert row["class"] == "install"
    assert row["pid"] > 0
    assert os.path.basename(row["argv"][0]).lower() == "cargo.exe"
    assert _actions.wait_proc(row["proc"], 30.0) == "exited"
    assert os.path.isfile(log_path)


def test_a3_deny_refuses_with_today_text(tmp_path):
    client, token = _client(tmp_path)
    project = "proj-a3-deny"
    tool_id = "install:" + project + ":cargo"
    resp = _decide(client, token, tool_id, "deny", project)
    assert resp.status_code == 200, resp.text
    folder = str(tmp_path / "work")
    os.makedirs(folder, exist_ok=True)
    log_path = os.path.join(folder, "logs", "spawn.log")
    with pytest.raises(PermissionError) as excinfo:
        _actions.spawn_checked(
            project, "run-1", folder, ["cargo", "install", "fake-pkg"],
            log_path, "logs/spawn.log")
    assert type(excinfo.value) is PermissionError
    assert str(excinfo.value) == INSTALL_NONE_TEXT % "cargo"


def test_a3_inline_code_refused_unchanged(tmp_path):
    _client(tmp_path)
    folder = str(tmp_path / "work")
    os.makedirs(folder, exist_ok=True)
    log_path = os.path.join(folder, "logs", "spawn.log")
    with pytest.raises(PermissionError) as excinfo:
        _actions.spawn_checked(
            "proj-a3-inline", "run-1", folder,
            ["python", "-c", "print(1)"], log_path, "logs/spawn.log")
    assert type(excinfo.value) is PermissionError
    assert str(excinfo.value) == INLINE_TEXT


def test_a3_engine_run_continues_on_ask(tmp_path):
    _client(tmp_path)
    folder = str(tmp_path / "work")
    os.makedirs(folder, exist_ok=True)
    with pytest.raises(_engine._InstallHeld) as excinfo:
        _engine._run_agent_command(
            record=None, folder=folder, project="proj-a3-eng",
            run_id="run-eng", argv=["cargo", "install", "fake-pkg"],
            state=None, procs=[], attached=set(), stop_seen=None)
    assert excinfo.value.tool_id == "install:proj-a3-eng:cargo"
    assert "install permission needed" in str(excinfo.value)
    assert "install:proj-a3-eng:cargo" in str(excinfo.value)
