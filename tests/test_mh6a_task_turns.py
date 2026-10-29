"""MH6A task turn triples: stored plan/action/observation records plus counter.

A task with two stored turns serves both triples in order plus 2/40; a
task with none serves an empty list plus 0/40; an unknown task is an
honest 404. A real streamed Manager run records one triple per executed
turn (plan ref, tool-call ref, result ref) that the read route serves.
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

from agent_si.backend import task_turns  # noqa: E402
from agent_si.backend.app import create_app  # noqa: E402
from agent_si.backend.orchestration.graph import TaskPlanner  # noqa: E402
from agent_si.providers.adapters.base import (  # noqa: E402
    AdapterConfig,
    make_secret_ref,
)
from agent_si.providers.adapters.mock_provider import (  # noqa: E402
    MockProviderAdapter,
)
from agent_si.runtime.manager import run_task_streamed  # noqa: E402

TEST_TOKEN = "mh6a-turns-token"
TEST_SETTINGS = {"testing": True, "ui_session_token": TEST_TOKEN}
ACTOR = "tester-mh6a"


def _auth(token=TEST_TOKEN, actor=ACTOR):
    headers = {}
    if actor is not None:
        headers["x-actor"] = actor
    if token is not None:
        headers["x-ui-session-token"] = token
    return headers


@pytest.fixture
def client():
    app = create_app(dict(TEST_SETTINGS))
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clean_turns():
    task_turns.clear_task_turns()
    yield
    task_turns.clear_task_turns()


def _create_project(client, name="mh6a-harbor", folder="mh6a-folder"):
    resp = client.post(
        "/api/v1/projects",
        json={"name": name, "folder_ref": folder},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["project"]


def _create_task(client, project_id, title="mh6a task"):
    resp = client.post(
        "/api/v1/projects/%s/tasks" % project_id,
        json={"title": title, "scope": []},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["task"]


def _mock_adapter(canned=None):
    config = AdapterConfig(
        provider_id="mock",
        instance_id="mh6a-turns-test",
        model="mock-canned",
        secret_ref=make_secret_ref(
            secret_id="mock-secret", provider_id="mock"),
    )
    if canned is None:
        return MockProviderAdapter(config, transport=None)
    return MockProviderAdapter(config, transport=None, canned=canned)


def test_two_stored_turns_return_in_order_with_counter(client):
    project = _create_project(client)
    task = _create_task(client, project["project_id"])
    task_id = task["task_id"]
    task_turns.record_turn(task_id, "plan-a", "action-a", "obs-a")
    task_turns.record_turn(task_id, "plan-b", "action-b", "obs-b")

    resp = client.get("/api/v1/tasks/%s/turns" % task_id)

    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "turns": [
            {"plan": "plan-a", "action": "action-a",
             "observation": "obs-a"},
            {"plan": "plan-b", "action": "action-b",
             "observation": "obs-b"},
        ],
        "used": 2,
        "limit": 40,
    }


def test_task_with_no_turns_returns_empty_with_zero_counter(client):
    project = _create_project(client)
    task = _create_task(client, project["project_id"])

    resp = client.get("/api/v1/tasks/%s/turns" % task["task_id"])

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"turns": [], "used": 0, "limit": 40}


def test_unknown_task_turns_is_404(client):
    resp = client.get("/api/v1/tasks/no-such-task/turns")
    assert resp.status_code == 404


def test_manager_run_records_one_triple_per_executed_turn(client):
    project = _create_project(client)
    task = _create_task(client, project["project_id"])
    planner = TaskPlanner()
    _plan_ref, graph = planner.plan(
        "pkg-mh6a",
        "mh6a manager run",
        [{"subtask_id": "mh6a-sub-001",
          "goal": "serve one canned turn",
          "task_class": "general", "risk": "LOW"}],
    )
    agent_task = {
        "agent_task_id": "agent-task-mh6a",
        "subtask_id": "mh6a-sub-001",
        "agent_id": "agent-mh6a",
        "contract_hash": "hash-mh6a",
    }
    mock = _mock_adapter(canned=("Mock mh6a reply.",))
    events = list(run_task_streamed(
        None,
        agent_task=agent_task,
        graph=graph,
        provider_adapter=mock,
        project_id=project["project_id"],
        task_id=task["task_id"],
        message="hello mh6a",
        manager_id="mgr-mh6a",
        max_agent_steps=3,
    ))
    assert events and events[-1].event == "done"

    resp = client.get("/api/v1/tasks/%s/turns" % task["task_id"])

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["used"] == 1
    assert body["limit"] == 40
    (triple,) = body["turns"]
    assert triple["plan"].startswith("plan-")
    assert "route-mh6a-sub-001" in triple["action"]
    assert "provider.invoke" in triple["action"]
    assert "artifact:run/" in triple["observation"]
