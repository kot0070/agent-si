"""K02REST-A hierarchy seam: split/integrate served through create_app.

testid k02rest-a-hierarchy; one served test per BUILD_PLAN row via
create_app + HTTP client. Staged rows reach the hierarchy (M-P2-80),
staged requirement subsets follow the inputs folder (M-P2-82),
governance raw reads stay Director-only with staged rows (M-R-GOV),
hierarchy settings changes persist a decision row (103), the Manager
integration assembles and the phase closes after its PASS (95), and the
largest parallel decomposition runs up to the cap with the rest queued
(32). Writes keep the frozen USER_WRITE guard (401 missing x-actor,
403 bad token).
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
from agent_si.backend.orchestration import hierarchy as hierarchy_mod  # noqa: E402

TEST_TOKEN = "k02rest-a-hierarchy-token"


def make_client():
    app = create_app({"testing": True, "ui_session_token": TEST_TOKEN})
    headers = {"x-actor": "manager-1", "x-ui-session-token": TEST_TOKEN}
    return TestClient(app), headers


def setup_function(_func):
    reset = getattr(hierarchy_mod, "_reset_state", None)
    if callable(reset):
        reset()


def teardown_function(_func):
    reset = getattr(hierarchy_mod, "_reset_state", None)
    if callable(reset):
        reset()


def _parts():
    return [
        {"id": "part-a", "kind": "build"},
        {"id": "part-b", "kind": "test"},
    ]


def test_k02rest_a_staged_rows_to_hierarchy():
    """| M-P2-80 | K02 | governance folder HD-only; staged rows to hierarchy | OPEN | ROWS2: OPEN - no served wiring plus calling test triple proven in int |"""
    client, headers = make_client()
    resp = client.post(
        "/v1/split",
        json={
            "project_id": "k02rest-a-proj-staged",
            "parts": _parts(),
            "staged_rows": [{"row_id": "row-80-a"}, {"row_id": "row-80-b"}],
        },
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["parts"] == [
        {"id": "part-a", "status": "split"},
        {"id": "part-b", "status": "split"},
    ]
    assert body["integration"] == {"by": "manager", "parts": 2}
    assert body["staged"] == [
        {"row_id": "row-80-a",
         "hierarchy_ref": "ARTIFACT_REF:row-80-a/hierarchy"},
        {"row_id": "row-80-b",
         "hierarchy_ref": "ARTIFACT_REF:row-80-b/hierarchy"},
    ]


def test_k02rest_a_staged_requirement_subset():
    """| M-P2-82 | K02 | staged requirement subset per inputs folder | OPEN | ROWS2: OPEN - no served wiring plus calling test triple proven in int |"""
    client, headers = make_client()
    resp = client.post(
        "/v1/split",
        json={
            "project_id": "k02rest-a-proj-subset",
            "parts": _parts(),
            "requirements": [
                {"id": "req-1"},
                {"id": "req-2"},
                {"id": "req-3"},
            ],
            "inputs": ["req-3", "req-1"],
        },
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["requirement_subset"] == ["req-3", "req-1"]


def test_k02rest_a_governance_director_only():
    """| M-R-GOV | K02 | governance raw reads Director-only; staged rows to hierarchy | OPEN | ROWS2: OPEN - no served wiring plus calling test triple proven in int |"""
    client, headers = make_client()
    allowed = client.post(
        "/v1/split",
        json={
            "project_id": "k02rest-a-proj-gov",
            "parts": _parts(),
            "actor": "director",
            "governance": {"raw": "gov-row-1"},
        },
        headers=headers,
    )
    assert allowed.status_code == 200
    assert allowed.json()["governed"] == {
        "row_id": "gov-row-1",
        "hierarchy_ref": "ARTIFACT_REF:gov-row-1/hierarchy",
    }
    refused = client.post(
        "/v1/split",
        json={
            "project_id": "k02rest-a-proj-gov",
            "parts": _parts(),
            "actor": "tool-agent-7",
            "governance": {"raw": "gov-row-1"},
        },
        headers=headers,
    )
    assert refused.status_code == 400
    anonymous = client.post(
        "/v1/split",
        json={
            "project_id": "k02rest-a-proj-gov",
            "parts": _parts(),
            "governance": {"raw": "gov-row-1"},
        },
        headers=headers,
    )
    assert anonymous.status_code == 400
    no_actor = client.post(
        "/v1/split",
        json={"project_id": "k02rest-a-proj-gov", "parts": _parts()},
    )
    assert no_actor.status_code == 401


def test_k02rest_a_settings_persist_decision_row():
    """| 103 | K02 | hierarchy settings changes persist a decision row | OPEN | ROWS2: OPEN - no served wiring plus calling test triple proven in int |"""
    client, headers = make_client()
    first = client.post(
        "/v1/split",
        json={
            "project_id": "k02rest-a-proj-settings",
            "parts": _parts(),
            "settings": {"manager": "manager-2", "cap": 4},
        },
        headers=headers,
    )
    assert first.status_code == 200
    decision = first.json()["decision"]
    assert decision["decision_id"] == "hierarchy-decision-0001"
    assert decision["scope"] == "hierarchy:settings"
    assert decision["statement"]
    assert decision["created_at"]
    second = client.post(
        "/v1/split",
        json={
            "project_id": "k02rest-a-proj-settings",
            "parts": _parts(),
            "settings": {"manager": "manager-3", "cap": 2},
        },
        headers=headers,
    )
    assert second.status_code == 200
    assert second.json()["decision"]["decision_id"] == \
        "hierarchy-decision-0002"


def test_k02rest_a_integration_closes_phase_after_pass():
    """| 95 | K02 | integration Manager assembles; phase closes after its PASS | OPEN | ROWS2: OPEN - no served wiring plus calling test triple proven in int |"""
    client, headers = make_client()
    project_id = "k02rest-a-proj-integrate"
    split = client.post(
        "/v1/split",
        json={"project_id": project_id, "parts": _parts()},
        headers=headers,
    )
    assert split.status_code == 200
    closed = client.post(
        "/v1/integrate",
        json={
            "project_id": project_id,
            "parts": [
                {"id": "part-a", "verdict": "PASS"},
                {"id": "part-b", "verdict": "PASS"},
            ],
        },
        headers=headers,
    )
    assert closed.status_code == 200
    body = closed.json()
    assert body["project_id"] == project_id
    assert body["parts"] == [
        {"id": "part-a", "status": "integrated"},
        {"id": "part-b", "status": "integrated"},
    ]
    assert body["integration"] == {"by": "manager", "parts": 2}
    assert body["phase"] == "closed"
    open_phase = client.post(
        "/v1/integrate",
        json={
            "project_id": project_id,
            "parts": [
                {"id": "part-a", "verdict": "PASS"},
                {"id": "part-b", "verdict": "FAIL"},
            ],
        },
        headers=headers,
    )
    assert open_phase.status_code == 200
    assert open_phase.json()["phase"] == "open"
    assert open_phase.json()["integration"] == {"by": "manager", "parts": 2}


def test_k02rest_a_parallel_decomposition_cap_queues_rest():
    """| 32 | K02 | largest parallel decomposition up to the cap, rest queued | OPEN | ROWS2: OPEN - no served wiring plus calling test triple proven in int |"""
    client, headers = make_client()
    resp = client.post(
        "/v1/split",
        json={
            "project_id": "k02rest-a-proj-decompose",
            "parts": _parts(),
            "cap": 2,
            "tasks": [
                {"id": "task-1", "size": 3},
                {"id": "task-2", "size": 9},
                {"id": "task-3", "size": 5},
                {"id": "task-4", "size": 1},
            ],
        },
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["parallel"] == ["task-2", "task-3"]
    assert resp.json()["queued"] == ["task-1", "task-4"]
    missing_cap = client.post(
        "/v1/split",
        json={
            "project_id": "k02rest-a-proj-decompose",
            "parts": _parts(),
            "tasks": [{"id": "task-1", "size": 3}],
        },
        headers=headers,
    )
    assert missing_cap.status_code == 400
