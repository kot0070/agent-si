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

try:
    from agent_si import hierarchy_routes as _seam
    _SEAM_ERROR = None
except Exception as err:  # seam unserved: K02NEXT2 tests below fail RED
    _seam = None
    _SEAM_ERROR = err

TEST_TOKEN = "k02open14-hierarchy-token"


def make_client():
    app = create_app({"testing": True, "ui_session_token": TEST_TOKEN})
    headers = {"x-actor": "manager-1", "x-ui-session-token": TEST_TOKEN}
    return TestClient(app), headers


def make_k02rest2_client():
    if _seam is None:
        raise AssertionError(
            f"K02NEXT2 seam unserved: {_SEAM_ERROR!r}")
    app = create_app({"testing": True, "ui_session_token": TEST_TOKEN})
    _seam.register_k02rest2_routes(app)
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


def test_k02open14_hierarchy_row358_team_config_change_validated_first():
    """R-358: every configuration change validated and recorded before
    it applies; a refused change applies nothing and records no row."""
    client, headers = make_k02rest2_client()
    good = client.post(
        "/api/v1/hierarchy/team-config-change",
        json={
            "statement": "raise agent cap for build",
            "reason": "build needs more agents",
            "authority": "director-1",
            "patch": {"max_agents": 6},
        },
        headers=headers,
    )
    assert good.status_code == 200, good.text
    body = good.json()
    assert body["accepted"] is True
    assert body["decision_ref"].startswith("team-config-")
    assert body["reason"] == "applied"
    bad = client.post(
        "/api/v1/hierarchy/team-config-change",
        json={
            "statement": "merge auditor and worker",
            "reason": "short crew for audit",
            "authority": "director-1",
            "patch": {"auditor": "agent-1", "worker": "agent-1"},
        },
        headers=headers,
    )
    assert bad.status_code == 200, bad.text
    refused = bad.json()
    assert refused["accepted"] is False
    assert refused["decision_ref"] is None
    assert "audit independence" in refused["reason"]
    no_actor = client.post(
        "/api/v1/hierarchy/team-config-change",
        json={
            "statement": "raise agent cap for build",
            "reason": "build needs more agents",
            "authority": "director-1",
            "patch": {"max_agents": 6},
        },
    )
    assert no_actor.status_code == 401


def test_k02open14_hierarchy_row359_multi_manager_settings_validated():
    """R-359: multi-manager settings validated; an invalid config is
    blocked with its reason and applies nothing."""
    client, headers = make_k02rest2_client()
    settings = {
        "multi_manager_mode": True,
        "max_parallel_managers": 2,
        "overlap": True,
        "integration_policy": "manager-merge",
        "model_pool_per_manager": {
            "m1": "meta/muse-spark-1.3-contributor"
        },
    }
    good = client.post(
        "/api/v1/hierarchy/multi-manager-settings",
        json={"settings": settings},
        headers=headers,
    )
    assert good.status_code == 200, good.text
    assert good.json() == {"ok": True, "reason": "ok"}
    broken = dict(settings)
    broken["max_parallel_managers"] = 0
    bad = client.post(
        "/api/v1/hierarchy/multi-manager-settings",
        json={"settings": broken},
        headers=headers,
    )
    assert bad.status_code == 200, bad.text
    body = bad.json()
    assert body["ok"] is False
    assert "POLICY_CONFLICT" in body["reason"]
    no_actor = client.post(
        "/api/v1/hierarchy/multi-manager-settings",
        json={"settings": settings},
    )
    assert no_actor.status_code == 401


def test_k02open14_hierarchy_rowmp115_closed_part_ref_frozen():
    """M-P1-15: the frozen closed-part ref shape served over HTTP."""
    client, headers = make_k02rest2_client()
    ref = {
        "package_id": "k02next2-pkg-1",
        "contract_hash": "hash-9",
        "gate_verdict_ref": "gate-1",
        "audit_verdict_ref": "audit-1",
    }
    resp = client.post(
        "/api/v1/hierarchy/closed-part-ref",
        json=ref,
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == ref
    blank = client.post(
        "/api/v1/hierarchy/closed-part-ref",
        json=dict(ref, package_id="  "),
        headers=headers,
    )
    assert blank.status_code == 400
    no_actor = client.post(
        "/api/v1/hierarchy/closed-part-ref",
        json=ref,
    )
    assert no_actor.status_code == 401


def test_k02open14_hierarchy_rowmp117_ledger_persist_load_roundtrip():
    """M-P1-17: ledger rows persist then load back with package ids."""
    client, headers = make_k02rest2_client()
    rows = [
        {"package_id": "k02next2-pkg-b", "agents": 2,
         "peak_concurrency": 2, "wall_time_s": 1.5},
        {"package_id": "k02next2-pkg-a", "agents": 1,
         "peak_concurrency": 1, "wall_time_s": 0.5},
    ]
    resp = client.post(
        "/api/v1/hierarchy/ledger-roundtrip",
        json={"rows": rows},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["package_ids"] == ["k02next2-pkg-a", "k02next2-pkg-b"]
    assert body["rows"] == 2
    bad = client.post(
        "/api/v1/hierarchy/ledger-roundtrip",
        json={"rows": [{"package_id": "k02next2-pkg-c"}]},
        headers=headers,
    )
    assert bad.status_code == 400
    no_actor = client.post(
        "/api/v1/hierarchy/ledger-roundtrip",
        json={"rows": rows},
    )
    assert no_actor.status_code == 401
