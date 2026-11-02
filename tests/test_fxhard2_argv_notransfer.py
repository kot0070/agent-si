"""FXHARD2-FIX1: install approval never transfers to a wider argv.

Approval for ["npm", "install"] must NOT run ["npm", "install", "--force"]:
the exact approved argv runs (real npm, rc 0, package-lock created) and
any wider argv refuses (PermissionError, nothing spawned).

RED-first: pre-fix the wider spawn runs rc 0 (TRANSFER).
"""

import json
import os
import sys

import pytest

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.runtime.devrun import actions as _actions  # noqa: E402
from agent_si.toolguard import permissions as _permissions  # noqa: E402
from agent_si.watcher import journal as _journal  # noqa: E402

TOKEN = "fxhard2-argv-token"


@pytest.fixture(autouse=True)
def _clean_journal():
    _journal.reset_state()
    yield
    _journal.reset_state()


def _client(tmp_path, token=TOKEN):
    store = tmp_path / "store"
    store.mkdir(exist_ok=True)
    settings = {"ui_session_token": token, "store_dir": str(store)}
    return create_app(dict(settings)), token


def _decide(app, token, tool_id, decision, project_id):
    from fastapi.testclient import TestClient

    client = TestClient(app)
    return client.post(
        _permissions.PERMISSIONS_DECIDE_ROUTE,
        json={"tool_id": tool_id, "decision": decision,
              "project_id": project_id},
        headers={"x-ui-session-token": token},
    )


def test_install_allow_exact_runs_wider_refused(tmp_path):
    app, token = _client(tmp_path)
    project = "proj-fxhard2-argv"
    tool_id = "install:" + project + ":npm"
    folder = str(tmp_path / "work")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "package.json"), "w",
              encoding="utf-8") as handle:
        json.dump({"name": "fxhard2-probe", "version": "0.0.0"}, handle)

    exact_log = os.path.join(folder, "logs", "exact.log")
    wider_log = os.path.join(folder, "logs", "wider.log")

    with pytest.raises(_actions.InstallAskNeeded):
        _actions.spawn_checked(
            project, "run-ask", folder, ["npm", "install"],
            exact_log, "logs/exact.log")

    resp = _decide(app, token, tool_id, "allow", project)
    assert resp.status_code == 200, resp.text

    row = _actions.spawn_checked(
        project, "run-exact", folder, ["npm", "install"],
        exact_log, "logs/exact.log")
    assert row["class"] == "install"
    assert _actions.wait_proc(row["proc"], 120.0) == "exited"
    assert row["proc"].returncode == 0
    assert os.path.isfile(
        os.path.join(folder, "package-lock.json"))

    with pytest.raises(PermissionError) as excinfo:
        _actions.spawn_checked(
            project, "run-wider", folder,
            ["npm", "install", "--force"], wider_log, "logs/wider.log")
    assert "approval" in str(excinfo.value).lower()
    assert not os.path.exists(wider_log)
