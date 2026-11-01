"""K02NEXT4 served proof: 8 hierarchy rows on the production seam.

testid k02next4-served; one behaviour test per BUILD_PLAN row via
create_app + HTTP client over the K02NEXT4 seam
(register_hierarchy_routes mounted on the real create_app app).

Rows:
- R1 UI_DELTA-23: emergency restoration rebinds each role to its
  configured RoleModelProfile while keeping completed work refs.
- R2 BP01-65: overlapping agent scopes rejected with
  REJECTED_SCOPE_OVERLAP.
- R3 BP01-73: parent closure blocked while the integration task is not
  yet recorded.
- R4 BP06-68: contributor bindings active dev-only, never prod.
- R5 BP06-78: role authority resolves only via configured role models
  (provider: hierarchy_claims.role_authority).
- R6 ARCH-456: agent scopes distinct and non-overlapping
  (provider: hierarchy_claims.check_scopes_distinct).
- R7 ARCH-461: planning/routing subordinate to the Manager hierarchy
  (provider: hierarchy_claims.route_plan).
- R8 ARCH-755: Manager queues demand within caps
  (provider: hierarchy_claims.queue_demand).
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

try:
    from agent_si.backend.orchestration import (  # noqa: E402
        hierarchy_routes as _seam,
    )
    _SEAM_ERROR = None
except Exception as err:  # seam unserved: every test below fails RED
    _seam = None
    _SEAM_ERROR = err

TEST_TOKEN = "k02next4-served-token"

MODEL_ID = "meta/muse-spark-1.3-contributor"


def make_client():
    if _seam is None or not hasattr(_seam, "register_hierarchy_routes"):
        raise AssertionError(
            "K02NEXT4 seam unserved: {!r}".format(_SEAM_ERROR))
    app = create_app({"testing": True, "ui_session_token": TEST_TOKEN})
    _seam.register_hierarchy_routes(app)
    headers = {"x-actor": "manager-1", "x-ui-session-token": TEST_TOKEN}
    return TestClient(app), headers


def setup_function(_func):
    if _seam is not None:
        _seam._reset_state()


def teardown_function(_func):
    if _seam is not None:
        _seam._reset_state()


def _restore_payload():
    return {
        "project_id": "k02next4-proj-restore",
        "roles": ["manager", "worker"],
        "profiles": {
            "manager": {"provider": "meta", "model": MODEL_ID,
                        "mode": "PINNED"},
            "worker": {"provider": "meta", "model": MODEL_ID,
                       "mode": "PINNED"},
        },
        "completed": ["part-001"],
    }


def test_k02next4_served_r1():
    """R1 UI_DELTA-23: emergency restoration rebinds each role to its
    configured RoleModelProfile while keeping completed work refs."""
    client, headers = make_client()
    resp = client.post(
        "/hierarchy/emergency-restore", json=_restore_payload(),
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["restored"] == ["manager", "worker"]
    assert body["completed_kept"] == ["part-001"]
    assert body["profiles"]["manager"].startswith("ROLE_PROFILE:")
    missing = dict(_restore_payload())
    missing["profiles"] = {
        "manager": {"provider": "meta", "model": MODEL_ID,
                    "mode": "PINNED"},
    }
    refused = client.post(
        "/hierarchy/emergency-restore", json=missing, headers=headers,
    )
    assert refused.status_code == 400, refused.text
    no_actor = client.post(
        "/hierarchy/emergency-restore", json=_restore_payload(),
    )
    assert no_actor.status_code == 401


def test_k02next4_served_r2():
    """R2 BP01-65: overlapping agent scopes rejected with
    REJECTED_SCOPE_OVERLAP."""
    client, headers = make_client()
    ok_resp = client.post(
        "/hierarchy/scopes/validate",
        json={"scopes": ["agent-1:build", "agent-2:test"]},
        headers=headers,
    )
    assert ok_resp.status_code == 200, ok_resp.text
    assert ok_resp.json() == {
        "distinct": True, "scopes": ["agent-1:build", "agent-2:test"],
    }
    clash = client.post(
        "/hierarchy/scopes/validate",
        json={"scopes": ["agent-1:build", "agent-1:build"]},
        headers=headers,
    )
    assert clash.status_code == 409, clash.text
    assert clash.json()["detail"]["code"] == "REJECTED_SCOPE_OVERLAP"
    no_actor = client.post(
        "/hierarchy/scopes/validate",
        json={"scopes": ["agent-1:build"]},
    )
    assert no_actor.status_code == 401


def test_k02next4_served_r3():
    """R3 BP01-73: parent closure blocked while the integration task is
    not yet recorded."""
    client, headers = make_client()
    blocked = client.post(
        "/hierarchy/parent-close",
        json={"part_results": {"part-a": "PASS", "part-b": "PASS"}},
        headers=headers,
    )
    assert blocked.status_code == 409, blocked.text
    assert "integration task" in blocked.json()["detail"]["message"]
    closed = client.post(
        "/hierarchy/parent-close",
        json={"part_results": {"part-a": "PASS", "part-b": "PASS"},
              "integration_record": {"record_id": "integration-r3",
                                     "manager_id": "manager-1"}},
        headers=headers,
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["parent"] == "closed"
    assert closed.json()["integration_ref"] == "integration-r3"
    no_actor = client.post(
        "/hierarchy/parent-close",
        json={"part_results": {"part-a": "PASS"},
              "integration_record": {"record_id": "integration-r3"}},
    )
    assert no_actor.status_code == 401


def test_k02next4_served_r4():
    """R4 BP06-68: contributor bindings active dev-only, never prod."""
    client, headers = make_client()
    dev = client.get(
        "/hierarchy/contributor-bindings", params={"env": "dev"},
        headers=headers,
    )
    assert dev.status_code == 200, dev.text
    body = dev.json()
    assert body["env"] == "dev"
    assert body["active"] is True
    assert body["bindings"]
    assert body["bindings"][0]["model"] == MODEL_ID
    prod = client.get(
        "/hierarchy/contributor-bindings", params={"env": "prod"},
        headers=headers,
    )
    assert prod.status_code == 403, prod.text
    blank = client.get("/hierarchy/contributor-bindings", headers=headers)
    assert blank.status_code == 400


def test_k02next4_served_r5():
    """R5 BP06-78: role authority resolves only via configured role
    models."""
    client, headers = make_client()
    restored = client.post(
        "/hierarchy/emergency-restore", json=_restore_payload(),
        headers=headers,
    )
    assert restored.status_code == 200, restored.text
    granted = client.get(
        "/hierarchy/role-authority", params={"role": "manager"},
        headers=headers,
    )
    assert granted.status_code == 200, granted.text
    assert granted.json()["role"] == "manager"
    refused = client.get(
        "/hierarchy/role-authority", params={"role": "no-such-role"},
        headers=headers,
    )
    assert refused.status_code == 403, refused.text


def test_k02next4_served_r6():
    """R6 ARCH-456: agent scopes distinct and non-overlapping."""
    client, headers = make_client()
    ok_resp = client.post(
        "/hierarchy/scopes/distinct",
        json={"scopes": ["agent-1:build", "agent-2:test"]},
        headers=headers,
    )
    assert ok_resp.status_code == 200, ok_resp.text
    assert ok_resp.json()["distinct"] is True
    clash = client.post(
        "/hierarchy/scopes/distinct",
        json={"scopes": ["agent-1:build", "agent-1:build"]},
        headers=headers,
    )
    assert clash.status_code == 409, clash.text
    assert clash.json()["detail"]["code"] == "REJECTED_SCOPE_OVERLAP"
    no_actor = client.post(
        "/hierarchy/scopes/distinct",
        json={"scopes": ["agent-1:build"]},
    )
    assert no_actor.status_code == 401


def test_k02next4_served_r7():
    """R7 ARCH-461: planning/routing subordinate to the Manager
    hierarchy."""
    client, headers = make_client()
    hierarchy = {"manager": "manager-1",
                 "agents": ["agent-1", "agent-2"]}
    ok_resp = client.post(
        "/hierarchy/route-plan",
        json={"plan": {"manager": "manager-1",
                       "steps": [{"to": "agent-1", "by": "manager-1"}]},
              "manager_hierarchy": hierarchy},
        headers=headers,
    )
    assert ok_resp.status_code == 200, ok_resp.text
    ok_body = ok_resp.json()
    assert ok_body["ok"] is True
    assert ok_body["route"]["manager"] == "manager-1"
    assert ok_body["route"]["subordinate"] is True
    bypass = client.post(
        "/hierarchy/route-plan",
        json={"plan": {"manager": "other-manager",
                       "bypass_manager": True,
                       "steps": [{"to": "agent-9", "by": "other-manager"}]},
              "manager_hierarchy": hierarchy},
        headers=headers,
    )
    assert bypass.status_code == 422, bypass.text
    no_actor = client.post(
        "/hierarchy/route-plan",
        json={"plan": {"manager": "manager-1"},
              "manager_hierarchy": hierarchy},
    )
    assert no_actor.status_code == 401


def test_k02next4_served_r8():
    """R8 ARCH-755: Manager queues demand within caps."""
    client, headers = make_client()
    caps = {"max_items": 2}
    ok_resp = client.post(
        "/hierarchy/demand-queue",
        json={"demand": {"items": [{"id": "task-a"},
                                   {"id": "task-b"}]},
              "caps": caps},
        headers=headers,
    )
    assert ok_resp.status_code == 200, ok_resp.text
    ok_body = ok_resp.json()
    assert ok_body["ok"] is True
    assert ok_body["queue"]["cap"] == 2
    assert sorted(ok_body["queue"]["parallel"]) == ["task-a", "task-b"]
    over = client.post(
        "/hierarchy/demand-queue",
        json={"demand": {"items": [{"id": "task-a"},
                                   {"id": "task-b"},
                                   {"id": "task-c"}]},
              "caps": caps},
        headers=headers,
    )
    assert over.status_code == 409, over.text
    no_actor = client.post(
        "/hierarchy/demand-queue",
        json={"demand": {"items": [{"id": "task-a"}]}, "caps": caps},
    )
    assert no_actor.status_code == 401
