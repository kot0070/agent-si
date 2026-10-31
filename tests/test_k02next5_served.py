"""K02NEXT5 served proof: 8 hierarchy/orchestration rows on the seam.

testid k02next5-served; one behaviour test per BUILD_PLAN row via
create_app + HTTP client over the K02NEXT5 seam
(orchestration.hierarchy_routes extended with 8 additive routes).

Rows:
- R1 ARCH-762: reached cap queues newcomers with position and
  estimated start (provider: split.capped_queue).
- R2 ARCH-766: each Manager agent distinct scope and deliverable, no
  duplication (provider: graph.HierarchyConfigStore.activate_chain).
- R3 BP01-72: overlapping decomposition part scopes rejected before
  fan-out (provider: split.split_package + split.validate_disjoint).
- R4 ARCH-704: only the USER appends user corrections
  (provider: graph.HierarchyConfigStore.append_user_correction).
- R5 UI_DELTA-57: routine-work handoff switchable ON/OFF per project
  and role (provider: offload.apply_offload_config_change plus
  offload_enabled/maybe_offload).
- R6 UI_DELTA-59: combined flow of project creation, hierarchy,
  binding, offload toggle, pause, archive (real primitives chained:
  split, activate_chain, grant_role_authority, offload toggle,
  delta apply).
- R7 UI_DELTA-60: hierarchy/binding/offload-toggle changes recorded
  with actor and timestamp, validated (provider:
  delta.apply_config_change persists exactly one decision row).
- R8 UI_DELTA-62: audit-independence and budget rejections surfaced
  to the user (provider: offload.apply_offload_config_change
  returns reason codes, mutates nothing).
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
from agent_si.backend.orchestration import offload as _offload  # noqa: E402

try:
    from agent_si.backend.orchestration import (  # noqa: E402
        hierarchy_routes as _seam,
    )
    _SEAM_ERROR = None
except Exception as err:  # seam unserved: every test below fails RED
    _seam = None
    _SEAM_ERROR = err

TEST_TOKEN = "k02next5-served-token"


def make_client():
    if _seam is None or not hasattr(_seam, "register_hierarchy_routes"):
        raise AssertionError(
            f"K02NEXT5 seam unserved: {_SEAM_ERROR!r}")
    app = create_app({"testing": True, "ui_session_token": TEST_TOKEN})
    _seam.register_hierarchy_routes(app)
    headers = {"x-actor": "manager-1", "x-ui-session-token": TEST_TOKEN}
    return TestClient(app), headers


def setup_function(_func):
    if _seam is not None:
        _seam._reset_state()
    _offload._reset_state()


def teardown_function(_func):
    if _seam is not None:
        _seam._reset_state()
    _offload._reset_state()


def test_k02next5_served_r1():
    """R1 ARCH-762: reached cap queues newcomers with position and
    estimated start."""
    client, headers = make_client()
    refs = [f"ARTIFACT_REF:part-{i:02d}" for i in range(5)]
    resp = client.post(
        "/hierarchy/cap-queue",
        json={"package_id": "k02n5-proj-cap", "goal": "cap queue",
              "context_refs": refs, "max_parts": 5,
              "max_parallel_managers": 2, "wall_time_s": 1.0},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    slots = body["slots"]
    assert len(slots) == 5
    assert [slot["position"] for slot in slots] == [0, 1, 2, 3, 4]
    assert [slot["estimated_start_s"] for slot in slots] == [
        0.0, 0.0, 1.0, 1.0, 2.0]
    assert sorted(body["running"] + body["queued"]) == sorted(
        slot["gate_ref"] for slot in slots)
    assert len(body["queued"]) == 3
    no_actor = client.post(
        "/hierarchy/cap-queue",
        json={"package_id": "k02n5-proj-cap", "goal": "cap queue",
              "context_refs": refs, "max_parts": 5,
              "max_parallel_managers": 2},
    )
    assert no_actor.status_code == 401


def test_k02next5_served_r2():
    """R2 ARCH-766: each Manager agent distinct scope and deliverable,
    no duplication."""
    client, headers = make_client()
    ok_resp = client.post(
        "/hierarchy/chain-activate",
        json={"chain": {"director_id": "director-1",
                       "manager_id": "manager-1",
                       "tool_agent_ids": ["agent-1", "agent-2"]}},
        headers=headers,
    )
    assert ok_resp.status_code == 200, ok_resp.text
    assert ok_resp.json()["accepted"] is True
    dup = client.post(
        "/hierarchy/chain-activate",
        json={"chain": {"director_id": "director-1",
                       "manager_id": "manager-1",
                       "tool_agent_ids": ["agent-1", "agent-1"]}},
        headers=headers,
    )
    assert dup.status_code == 409, dup.text
    as_tool = client.post(
        "/hierarchy/chain-activate",
        json={"chain": {"director_id": "director-1",
                       "manager_id": "manager-1",
                       "tool_agent_ids": ["manager-1", "agent-2"]}},
        headers=headers,
    )
    assert as_tool.status_code == 409, as_tool.text
    no_actor = client.post(
        "/hierarchy/chain-activate",
        json={"chain": {"director_id": "director-1",
                       "manager_id": "manager-1",
                       "tool_agent_ids": ["agent-1"]}},
    )
    assert no_actor.status_code == 401


def test_k02next5_served_r3():
    """R3 BP01-72: overlapping decomposition part scopes rejected
    before fan-out."""
    client, headers = make_client()
    ok_resp = client.post(
        "/hierarchy/parts-disjoint",
        json={"package_id": "k02n5-proj-disjoint", "goal": "disjoint",
              "context_refs": ["ARTIFACT_REF:a", "ARTIFACT_REF:b"],
              "max_parts": 2},
        headers=headers,
    )
    assert ok_resp.status_code == 200, ok_resp.text
    assert ok_resp.json()["disjoint"] is True
    clash = client.post(
        "/hierarchy/parts-disjoint",
        json={"package_id": "k02n5-proj-clash", "goal": "clash",
              "context_refs": ["ARTIFACT_REF:a", "ARTIFACT_REF:a"],
              "max_parts": 2},
        headers=headers,
    )
    assert clash.status_code == 409, clash.text
    assert "SCOPE_OVERLAP" in clash.json()["detail"]["message"]
    no_actor = client.post(
        "/hierarchy/parts-disjoint",
        json={"package_id": "k02n5-proj-disjoint", "goal": "disjoint",
              "context_refs": ["ARTIFACT_REF:a"], "max_parts": 1},
    )
    assert no_actor.status_code == 401


def test_k02next5_served_r4():
    """R4 ARCH-704: only the USER appends user corrections."""
    client, headers = make_client()
    user_headers = dict(headers, **{"x-actor": "user"})
    ok_resp = client.post(
        "/hierarchy/user-correction",
        json={"text": "steer the plan toward cheap models"},
        headers=user_headers,
    )
    assert ok_resp.status_code == 200, ok_resp.text
    body = ok_resp.json()
    assert body["recorded"] is True
    assert body["entry"]["actor"] == "user"
    assert body["entry"]["created_at"]
    refused = client.post(
        "/hierarchy/user-correction",
        json={"text": "manager tries to steer"},
        headers=headers,
    )
    assert refused.status_code == 403, refused.text
    no_actor = client.post(
        "/hierarchy/user-correction", json={"text": "anonymous steer"},
    )
    assert no_actor.status_code == 401


def test_k02next5_served_r5():
    """R5 UI_DELTA-57: routine-work handoff switchable ON/OFF per
    project and role."""
    client, headers = make_client()
    project_id = "k02n5-proj-offload"
    enable = client.post(
        "/hierarchy/offload-switch",
        json={"change": {"project_id": project_id, "role": "worker",
                        "enabled": True, "authority": "manager",
                        "reason": "routine work runs cheaper",
                        "task_ids": ["task-r5"]},
              "probe_task": "task-r5", "probe_role": "worker"},
        headers=headers,
    )
    assert enable.status_code == 200, enable.text
    body = enable.json()
    assert body["applied"] is True
    assert body["decision_ref"]
    assert body["offload_enabled"] is True
    assert body["handover"]["task_id"] == "task-r5"
    assert body["unknown_pair_enabled"] is False
    auditor = client.post(
        "/hierarchy/offload-switch",
        json={"change": {"project_id": project_id, "role": "auditor",
                        "enabled": True, "authority": "manager",
                        "reason": "auditor must stay independent"}},
        headers=headers,
    )
    assert auditor.status_code == 200, auditor.text
    assert auditor.json()["applied"] is False
    assert "AUDIT_INDEPENDENCE_REJECTED" in auditor.json()["reason"]
    off = client.post(
        "/hierarchy/offload-switch",
        json={"change": {"project_id": "k02n5-proj-off",
                        "role": "worker", "enabled": False,
                        "authority": "manager",
                        "reason": "routine work stays manual",
                        "task_ids": ["task-off"]},
              "probe_task": "task-off", "probe_role": "worker"},
        headers=headers,
    )
    assert off.status_code == 200, off.text
    assert off.json()["applied"] is True
    assert off.json()["handover"] is None


def test_k02next5_served_r6():
    """R6 UI_DELTA-59: combined flow of project creation, hierarchy,
    binding, offload toggle, pause, archive."""
    client, headers = make_client()
    project_id = "k02n5-proj-combined"
    resp = client.post(
        "/hierarchy/combined-flow",
        json={"project_id": project_id, "goal": "combined flow",
              "context_refs": ["ARTIFACT_REF:c1", "ARTIFACT_REF:c2"],
              "max_parts": 2,
              "chain": {"director_id": "director-1",
                       "manager_id": "manager-1",
                       "tool_agent_ids": ["agent-1", "agent-2"]},
              "role_models": {"worker": {"model": "cheap-agent"}},
              "binding": {"role": "worker", "binding": {"model": "cheap-agent"}},
              "offload_change": {"role": "worker", "enabled": True,
                                "authority": "manager",
                                "reason": "routine work runs cheaper",
                                "task_ids": ["task-combined"]},
              "lifecycle": {"paused": False, "archived": False}},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["project_id"] == project_id
    assert len(body["parts"]) == 2
    assert body["chain"]["accepted"] is True
    assert body["binding"]["accepted"] is True
    assert body["offload"]["applied"] is True
    assert body["lifecycle"]["applied"] is True
    assert body["lifecycle"]["decision_ref"]
    blocked = client.post(
        "/hierarchy/combined-flow",
        json={"project_id": "k02n5-proj-combined-bad",
              "goal": "combined flow",
              "context_refs": ["ARTIFACT_REF:c1"],
              "max_parts": 1,
              "chain": {"director_id": "director-1",
                       "manager_id": "manager-1",
                       "tool_agent_ids": ["manager-1"]},
              "role_models": {"worker": {"model": "cheap-agent"}},
              "binding": {"role": "worker", "binding": {"model": "cheap-agent"}},
              "offload_change": {"role": "worker", "enabled": True,
                                "authority": "manager",
                                "reason": "routine work runs cheaper"},
              "lifecycle": {"paused": False, "archived": False}},
        headers=headers,
    )
    assert blocked.status_code == 409, blocked.text


def test_k02next5_served_r7():
    """R7 UI_DELTA-60: hierarchy/binding/offload-toggle changes
    recorded with actor and timestamp, validated."""
    client, headers = make_client()
    resp = client.post(
        "/hierarchy/decision-record",
        json={"scope": "hierarchy:settings",
              "statement": "raise the parallel cap",
              "reason": "demand grows past the old cap",
              "authority": "manager-1",
              "patch": {"max_parallel_managers": 4}},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["applied"] is True
    assert body["decision_ref"] == "hierarchy:settings-0001"
    assert len(body["rows"]) == 1
    row = body["rows"][0]
    assert row["authority"] == "manager-1"
    assert row["created_at"]
    refused = client.post(
        "/hierarchy/decision-record",
        json={"scope": "",
              "statement": "blank scope change",
              "reason": "blank scope refused",
              "authority": "manager-1",
              "patch": {"max_parallel_managers": 2}},
        headers=headers,
    )
    assert refused.status_code == 200, refused.text
    assert refused.json()["applied"] is False


def test_k02next5_served_r8():
    """R8 UI_DELTA-62: audit-independence and budget rejections
    surfaced to the user."""
    client, headers = make_client()
    audit = client.post(
        "/hierarchy/rejection-surface",
        json={"change": {"project_id": "k02n5-proj-reject",
                        "role": "worker", "enabled": True,
                        "authority": "manager",
                        "reason": "auditor doubles as worker",
                        "auditor": "agent-1", "worker": "agent-1",
                        "independent_audit": False}},
        headers=headers,
    )
    assert audit.status_code == 200, audit.text
    audit_body = audit.json()
    assert audit_body["applied"] is False
    assert "AUDIT_INDEPENDENCE_REJECTED" in audit_body["reason"]
    assert audit_body["decisions_before"] == audit_body["decisions_after"]
    assert audit_body["surfaced"]
    budget = client.post(
        "/hierarchy/rejection-surface",
        json={"change": {"project_id": "k02n5-proj-reject",
                        "role": "worker", "enabled": True,
                        "authority": "manager",
                        "reason": "cost exceeds what is left",
                        "cost": 50, "budget_left": 10}},
        headers=headers,
    )
    assert budget.status_code == 200, budget.text
    budget_body = budget.json()
    assert budget_body["applied"] is False
    assert "BUDGET_CAPPED" in budget_body["reason"]
    assert budget_body["decisions_before"] == budget_body["decisions_after"]
