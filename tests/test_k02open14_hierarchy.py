"""K02OPEN14 served proof: R-302 split/integrate, R-333 switch, R-349 steps.

testid k02open14-hierarchy; one behaviour test per row via create_app +
HTTP client. Served Director split with Manager integration (R-302),
routine offload behind a per-project switch with recorded hand-overs
(R-333), and per-project max agent steps enforced separately for chat
(R-349).
"""

import os
import sys

from fastapi.testclient import TestClient

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.backend.orchestration import offload as offload_mod  # noqa: E402
from agent_si.backend.orchestration import steplimits as steplimits_mod  # noqa: E402

TEST_TOKEN = "k02open14-hierarchy-token"


def make_client():
    app = create_app({"testing": True, "ui_session_token": TEST_TOKEN})
    headers = {"x-actor": "manager-1", "x-ui-session-token": TEST_TOKEN}
    return TestClient(app), headers


def setup_function(_func):
    offload_mod._reset_state()
    steplimits_mod._reset_state()


def teardown_function(_func):
    offload_mod._reset_state()
    steplimits_mod._reset_state()


def test_k02open14_hierarchy_row302_director_split_manager_integrate():
    client, headers = make_client()
    project_id = "k02open14-proj-split"
    split = client.post(
        "/api/v1/split",
        json={
            "project_id": project_id,
            "parts": [
                {"id": "part-a", "kind": "build"},
                {"id": "part-b", "kind": "test"},
            ],
        },
        headers=headers,
    )
    assert split.status_code == 200
    assert split.json()["parts"] == [
        {"id": "part-a", "status": "split"},
        {"id": "part-b", "status": "split"},
    ]
    assert split.json()["integration"] == {"by": "manager", "parts": 2}
    integrate = client.post(
        "/api/v1/integrate",
        json={"project_id": project_id, "parts": split.json()["parts"]},
        headers=headers,
    )
    assert integrate.status_code == 200
    body = integrate.json()
    assert body["project_id"] == project_id
    assert body["parts"] == [
        {"id": "part-a", "status": "integrated"},
        {"id": "part-b", "status": "integrated"},
    ]
    assert body["integration"] == {"by": "manager", "parts": 2}
    refused = client.post(
        "/api/v1/split",
        json={"project_id": project_id, "parts": []},
        headers=headers,
    )
    assert refused.status_code == 400


def test_k02open14_hierarchy_row333_routine_offload_switch():
    client, headers = make_client()
    project_id = "k02open14-proj-offload"
    assert offload_mod.routine_offload_enabled(project_id) is False
    refused = client.post(
        "/api/v1/offload",
        json={"project_id": project_id, "routine": "nightly-docs"},
        headers=headers,
    )
    assert refused.status_code == 409
    assert refused.json()["detail"]["code"] == "OFFLOAD_DISABLED"
    switch = client.put(
        "/api/v1/offload-switch",
        json={"project_id": project_id, "enabled": True},
        headers=headers,
    )
    assert switch.status_code == 200
    assert switch.json() == {
        "project_id": project_id,
        "routine_offload_enabled": True,
    }
    assert offload_mod.routine_offload_enabled(project_id) is True
    handed = client.post(
        "/api/v1/offload",
        json={"project_id": project_id, "routine": "nightly-docs"},
        headers=headers,
    )
    assert handed.status_code == 200
    assert handed.json()["routine"] == "nightly-docs"
    assert handed.json()["by"] == "manager"
    rows = client.get(
        "/api/v1/handovers", params={"project_id": project_id}, headers=headers
    )
    assert rows.status_code == 200
    assert rows.json()["handovers"] == [
        {
            "routine": "nightly-docs",
            "at": handed.json()["at"],
            "by": "manager",
        }
    ]


def test_k02open14_hierarchy_row349_agent_step_limits():
    client, headers = make_client()
    project_id = "k02open14-proj-steps"
    configured = client.put(
        "/api/v1/step-limits",
        json={
            "project_id": project_id,
            "max_agent_steps": 1,
            "max_chat_steps": 2,
        },
        headers=headers,
    )
    assert configured.status_code == 200
    assert configured.json() == {
        "project_id": project_id,
        "max_agent_steps": 1,
        "max_chat_steps": 2,
    }
    first = client.post(
        "/api/v1/agent-steps", json={"project_id": project_id}, headers=headers
    )
    assert first.status_code == 200
    assert first.json() == {
        "project_id": project_id,
        "kind": "agent",
        "steps": 1,
    }
    second = client.post(
        "/api/v1/agent-steps", json={"project_id": project_id}, headers=headers
    )
    assert second.status_code == 429
    assert second.json()["detail"]["code"] == "STEP_LIMIT_EXCEEDED"
    chat_one = client.post(
        "/api/v1/chat-steps", json={"project_id": project_id}, headers=headers
    )
    assert chat_one.status_code == 200
    assert chat_one.json()["steps"] == 1
    chat_two = client.post(
        "/api/v1/chat-steps", json={"project_id": project_id}, headers=headers
    )
    assert chat_two.status_code == 200
    assert chat_two.json()["steps"] == 2
    chat_three = client.post(
        "/api/v1/chat-steps", json={"project_id": project_id}, headers=headers
    )
    assert chat_three.status_code == 429
    assert chat_three.json()["detail"]["code"] == "STEP_LIMIT_EXCEEDED"
    unknown = client.post(
        "/api/v1/agent-steps",
        json={"project_id": "k02open14-proj-never-set"},
        headers=headers,
    )
    assert unknown.status_code == 404
