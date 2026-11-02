"""OC-K02: served proof triple for R-302 / R-333 / R-349.

Drives the orchestration rows through the real seam app (create_app)
with TestClient, stdlib + pytest only:

- R-302: POST /api/v1/hierarchy/run splits work Director-to-parts
  (split.split_package), runs parts under tool agents subordinate to the
  Manager (graph.route_task with manager_id), and integrates via the
  Manager (HierarchyConfigStore.close_parent); GET control-plane map
  exposes the director.split/director.integrate wiring.
- R-333: PUT per-project per-role offload switch -> GET reads it back ->
  POST /api/v1/offload/maybe records a hand-over for a routine task and
  returns None for non-routine / switched-off / auditor roles.
- R-349: PUT + GET project step-limits (task/chat separate) through the
  served steplimit routes.
"""

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
from agent_si.backend.orchestration import offload as _offload  # noqa: E402
from agent_si.backend.orchestration import steplimits as _steplimits  # noqa: E402
from tests.test_fxautodev_served import (  # noqa: E402
    bind_canned_hierarchy_adapter as _bind_canned,
)

TEST_TOKEN = "ock02-hierarchy-token"
ACTOR = "tester-ock02"


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
    _offload._reset_state()
    _steplimits._reset_state()


def teardown_function(_func):
    _offload._reset_state()
    _steplimits._reset_state()


def _refs(n):
    return ["artifact://pkg-%d/blob" % (i,) for i in range(n)]


def test_r302_hierarchy_run_splits_runs_integrates(tmp_path):
    app = create_app(_settings(tmp_path))
    # FXLOC C5: fail-closed gate needs the default project configured
    # on the app's real gate; generous limits, idempotent.
    try:
        app.state.k04_ctx.budget_state.get_state("run")
    except (KeyError, LookupError):
        app.state.k04_ctx.budget_state.configure_project(
            "run", "USD", "1000000.00", "900000.00", "1000000.00")
    client = TestClient(app)
    _canned_patch = _bind_canned()
    resp = client.get("/api/v1/hierarchy/control-plane")
    assert resp.status_code == 200, resp.text
    plane = resp.json()
    assert plane["director.split"] == "split.split_package"
    assert plane["director.integrate"] == (
        "graph.HierarchyConfigStore.close_parent"
    )
    resp = client.post(
        "/api/v1/hierarchy/run",
        json={
            "package_id": "ock02-pkg",
            "goal": "prove hierarchy split run integrate",
            "context_refs": _refs(4),
            "max_parts": 2,
            "director_id": "director-ock02",
            "manager_id": "manager-ock02",
            "tool_agent_ids": ["tool-a", "tool-b"],
        },
        headers=_auth(),
    )
    _canned_patch.stop()
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["director"] == "director-ock02"
    assert payload["manager"] == "manager-ock02"
    assert len(payload["parts"]) == 2
    assert len(payload["routed"]) == 2
    for routed in payload["routed"]:
        assert routed["subordinate_to"] == "manager-ock02"
    integration = payload["integration"]
    assert integration["parent"] == "closed"
    assert integration["integration_ref"]


def test_r302_hierarchy_run_bad_chain_is_400(tmp_path):
    client = TestClient(create_app(_settings(tmp_path)))
    resp = client.post(
        "/api/v1/hierarchy/run",
        json={
            "package_id": "ock02-bad",
            "goal": "bad chain refused",
            "context_refs": _refs(2),
            "max_parts": 2,
            "director_id": "director-ock02",
            "manager_id": "manager-ock02",
            "tool_agent_ids": ["manager-ock02"],
        },
        headers=_auth(),
    )
    assert resp.status_code == 400, resp.text


def test_r333_offload_switch_handover_recorded(tmp_path):
    client = TestClient(create_app(_settings(tmp_path)))
    resp = client.get(
        "/api/v1/projects/harbor/offload", params={"role": "worker"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["enabled"] is False
    resp = client.put(
        "/api/v1/projects/harbor/offload",
        json={
            "role": "worker",
            "enabled": True,
            "to_role": "cheap-agent",
            "handover_reason": "routine work runs on the cheaper path",
            "task_ids": ["task-1"],
        },
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["decision_ref"]
    resp = client.get(
        "/api/v1/projects/harbor/offload", params={"role": "worker"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["enabled"] is True
    resp = client.post(
        "/api/v1/offload/maybe",
        json={"task_id": "task-1", "role": "worker", "routine": True},
    )
    assert resp.status_code == 200, resp.text
    handover = resp.json()["handover"]
    assert handover is not None
    assert handover["task_id"] == "task-1"
    assert handover["from_role"] == "worker"
    assert handover["to_role"] == "cheap-agent"
    resp = client.post(
        "/api/v1/offload/maybe",
        json={"task_id": "task-1", "role": "worker", "routine": False},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["handover"] is None


def test_r333_offload_auditor_never_offloads(tmp_path):
    client = TestClient(create_app(_settings(tmp_path)))
    resp = client.put(
        "/api/v1/projects/harbor/offload",
        json={"role": "auditor", "enabled": True},
        headers=_auth(),
    )
    assert resp.status_code == 400, resp.text
    resp = client.post(
        "/api/v1/offload/maybe",
        json={"task_id": "task-1", "role": "auditor", "routine": True},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["handover"] is None


def test_r333_offload_guard_401_403(tmp_path):
    client = TestClient(create_app(_settings(tmp_path)))
    body = {"role": "worker", "enabled": True}
    assert (
        client.put("/api/v1/projects/harbor/offload", json=body).status_code
        == 401
    )
    assert (
        client.put(
            "/api/v1/projects/harbor/offload",
            json=body,
            headers=_auth(token="wrong"),
        ).status_code
        == 403
    )


def test_r349_step_limits_task_chat_separate(tmp_path):
    client = TestClient(create_app(_settings(tmp_path)))
    created = client.post(
        "/api/v1/projects",
        json={"name": "harbor", "folder_ref": "dock-7"},
        headers=_auth(),
    )
    assert created.status_code == 200, created.text
    pid = created.json()["project"]["project_id"]
    resp = client.put(
        "/api/v1/projects/%s/step-limits" % (pid,),
        json={"task_max_steps": 60, "chat_max_steps": 9},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    resp = client.get("/api/v1/projects/%s/step-limits" % (pid,))
    assert resp.status_code == 200, resp.text
    assert resp.json()["task_max_steps"] == 60
    assert resp.json()["chat_max_steps"] == 9
    assert resp.json()["task_max_steps"] != resp.json()["chat_max_steps"]
