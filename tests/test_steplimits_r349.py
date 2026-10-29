"""R349A: project step-limits GET+PUT + start-hook saved-value restore.

Drives the step-limits surface through the real seam app (create_app)
with TestClient, stdlib + pytest only:

- create -> GET returns the starting values (task 40, chat 15);
- PUT change -> GET reads it back; success persists steplimits.json;
- restart on the same store_dir restores the SAVED values (not defaults);
- invalid PUT (out-of-range, missing field, non-int) -> 400 with reason;
- PUT without x-actor -> 401, with a wrong token -> 403;
- GET needs no token; GET unknown project -> 404.
"""

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

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.backend.orchestration import steplimits as _steplimits  # noqa: E402

TEST_TOKEN = "r349a-steplimits-token"
ACTOR = "tester-r349a"


def _auth(token=TEST_TOKEN, actor=ACTOR):
    headers = {}
    if actor is not None:
        headers["x-actor"] = actor
    if token is not None:
        headers["x-ui-session-token"] = token
    return headers


def _settings(store_dir=None):
    settings = {"testing": True, "ui_session_token": TEST_TOKEN}
    if store_dir is not None:
        settings["store_dir"] = str(store_dir)
    return settings


def setup_function(_func):
    _steplimits._reset_state()


def teardown_function(_func):
    _steplimits._reset_state()


def _create_project(client, name="harbor", folder="dock-7"):
    resp = client.post(
        "/api/v1/projects",
        json={"name": name, "folder_ref": folder},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["project"]


def _limits_path(pid):
    return "/api/v1/projects/%s/step-limits" % (pid,)


def test_get_returns_starting_values_after_create(tmp_path):
    _steplimits._reset_state()
    client = TestClient(create_app(_settings(tmp_path)))
    created = _create_project(client)
    pid = created["project_id"]
    resp = client.get(_limits_path(pid))
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "project_id": pid,
        "task_max_steps": 40,
        "chat_max_steps": 15,
    }


def test_get_needs_no_token_and_unknown_project_is_404(tmp_path):
    _steplimits._reset_state()
    client = TestClient(create_app(_settings(tmp_path)))
    assert client.get(_limits_path("no-such-project")).status_code == 404
    created = _create_project(client)
    resp = client.get(_limits_path(created["project_id"]))
    assert resp.status_code == 200, resp.text


def test_put_change_reads_back_and_persists(tmp_path):
    _steplimits._reset_state()
    client = TestClient(create_app(_settings(tmp_path)))
    created = _create_project(client)
    pid = created["project_id"]
    resp = client.put(
        _limits_path(pid),
        json={"task_max_steps": 100, "chat_max_steps": 20},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["project_id"] == pid
    assert payload["task_max_steps"] == 100
    assert payload["chat_max_steps"] == 20
    assert payload["decision_ref"]
    resp = client.get(_limits_path(pid))
    assert resp.status_code == 200, resp.text
    assert resp.json()["task_max_steps"] == 100
    assert resp.json()["chat_max_steps"] == 20
    saved_path = os.path.join(str(tmp_path), "steplimits.json")
    with open(saved_path, encoding="utf-8") as handle:
        saved = json.load(handle)
    assert saved[pid] == {"task": 100, "chat": 20}


def test_restart_restores_saved_values_not_defaults(tmp_path):
    _steplimits._reset_state()
    client1 = TestClient(create_app(_settings(tmp_path)))
    created = _create_project(client1)
    pid = created["project_id"]
    resp = client1.put(
        _limits_path(pid),
        json={"task_max_steps": 100, "chat_max_steps": 20},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    _steplimits._reset_state()
    client2 = TestClient(create_app(_settings(tmp_path)))
    resp = client2.get(_limits_path(pid))
    assert resp.status_code == 200, resp.text
    assert resp.json()["task_max_steps"] == 100
    assert resp.json()["chat_max_steps"] == 20


def test_put_invalid_is_400_with_reason(tmp_path):
    _steplimits._reset_state()
    client = TestClient(create_app(_settings(tmp_path)))
    created = _create_project(client)
    pid = created["project_id"]
    resp = client.put(
        _limits_path(pid),
        json={"task_max_steps": 0, "chat_max_steps": 20},
        headers=_auth(),
    )
    assert resp.status_code == 400, resp.text
    assert "BUDGET_CAPPED" in resp.json()["detail"]
    resp = client.put(
        _limits_path(pid),
        json={"task_max_steps": 100},
        headers=_auth(),
    )
    assert resp.status_code == 400, resp.text
    resp = client.put(
        _limits_path(pid),
        json={"task_max_steps": "many", "chat_max_steps": 20},
        headers=_auth(),
    )
    assert resp.status_code == 400, resp.text
    resp = client.get(_limits_path(pid))
    assert resp.status_code == 200, resp.text
    assert resp.json()["task_max_steps"] == 40
    assert resp.json()["chat_max_steps"] == 15


def test_put_guard_401_missing_actor_403_bad_token(tmp_path):
    _steplimits._reset_state()
    client = TestClient(create_app(_settings(tmp_path)))
    created = _create_project(client)
    pid = created["project_id"]
    body = {"task_max_steps": 100, "chat_max_steps": 20}
    assert client.put(_limits_path(pid), json=body).status_code == 401
    assert (
        client.put(
            _limits_path(pid), json=body, headers=_auth(token="wrong")
        ).status_code
        == 403
    )
    resp = client.put(_limits_path(pid), json=body, headers=_auth())
    assert resp.status_code == 200, resp.text
