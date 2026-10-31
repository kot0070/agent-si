"""K02NEXT3 Quarry: 8 open K02 rows served (hierarchy_routes + orchestration).

testid k02next3-quarry; one served test per BUILD_PLAN row via create_app
+ HTTP client over the K02NEXT3 seam (register_k02next3_routes). Every
route delegates its row decision to the real module; refusals keep the
frozen USER_WRITE guard shape (401 missing x-actor, 403 bad token).

Rows:
- B0B-UNCOVERED_UI_DELTA-36: non-OpenAI providers route through the one
  generic OpenAI-compatible Chat Completions adapter entry.
- B0B-UNCOVERED_ARCH-57: Chat Completions for non-OpenAI providers; the
  served contract never assumes a Responses API.
- B0B-BP03-4: SDK client max_retries=0; runner retries only through the
  RoutingDecision-bound RunConfig.
- B0B-UNCOVERED_BP06-81: project work reaches roles through a defined
  project-to-role target flow (never a default).
- B0B-SDK-132: architecture conclusions stay within the verified SDK
  surface.
- B0B-BP01-10: TaskPlanner decompose idempotent on package ref + goal
  hash via the existing plan ref.
- B0B-UNCOVERED_ARCH-7: an AgentTask without subtask_id is rejected at
  dispatch; only planned AgentTasks execute.
- B0B-UNCOVERED_ARCH-705: a TaskPackage whose corrections hash mismatches
  the checked hash is rejected at issuance.
"""

import json
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
    from agent_si import hierarchy_routes as _seam
    _SEAM_ERROR = None
except Exception as err:  # seam unserved: every test below fails RED
    _seam = None
    _SEAM_ERROR = err

TEST_TOKEN = "k02next3-quarry-token"

MODEL_ID = "meta/muse-spark-1.3-contributor"


def make_client():
    if _seam is None or not hasattr(_seam, "register_k02next3_routes"):
        raise AssertionError(
            "K02NEXT3 seam unserved: {!r}".format(_SEAM_ERROR))
    app = create_app({"testing": True, "ui_session_token": TEST_TOKEN})
    _seam.register_k02next3_routes(app)
    headers = {"x-actor": "manager-1", "x-ui-session-token": TEST_TOKEN}
    return TestClient(app), headers


def _specs():
    return [
        {"subtask_id": "pkg-q:part-000", "goal": "build quarry",
         "task_class": "general", "risk": "LOW"},
        {"subtask_id": "pkg-q:part-001", "goal": "test quarry",
         "task_class": "general", "risk": "LOW"},
    ]


def _target_flow():
    return {
        role: {"provider": "meta", "model": MODEL_ID}
        for role in ("director", "manager", "worker", "auditor", "watcher")
    }


def test_k02next3_row_ui_delta_36_non_openai_chat_completions():
    """| B0B-UNCOVERED_UI_DELTA-36 | K02 | routes non-OpenAI providers through a generic OpenAI-compatible Chat Completions adapter |"""
    client, headers = make_client()
    for provider in ("meta", "acme-custom", "openai-compatible-x"):
        resp = client.get(
            "/v1/k02next3/sdk-transport",
            params={"provider": provider},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["provider"] == provider
        assert body["transport"] == "chat_completions"
        assert body["entry"] == "transport_for_provider"
    openai = client.get(
        "/v1/k02next3/sdk-transport",
        params={"provider": "openai"},
        headers=headers,
    )
    assert openai.status_code == 200, openai.text
    assert openai.json()["transport"] == "sdk_default"
    blank = client.get(
        "/v1/k02next3/sdk-transport",
        params={"provider": "  "},
        headers=headers,
    )
    assert blank.status_code == 400


def test_k02next3_row_arch_57_never_responses_api():
    """| B0B-UNCOVERED_ARCH-57 | K02 | uses Chat Completions for non-OpenAI providers and never assumes Responses API |"""
    client, headers = make_client()
    for provider in ("meta", "anthropic", "acme-custom"):
        resp = client.get(
            "/v1/k02next3/sdk-transport",
            params={"provider": provider},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["transport"] == "chat_completions"
        assert "responses" not in json.dumps(body).lower()


def test_k02next3_row_bp03_4_max_retries_zero_routing_decision_retries():
    """| B0B-BP03-4 | K02 | sets the SDK client retry limit to max_retries=0 and performs runner retries only through RoutingDecision |"""
    client, headers = make_client()
    decision = {
        "decision_id": "route-pkg-q-part-000",
        "project_id": "pkg-q",
        "task_id": "task-q",
        "run_id": "run-q",
        "selected_provider": "meta",
        "selected_model": MODEL_ID,
        "route": "tool-part",
        "strategy": "single",
    }
    bound = client.post(
        "/v1/k02next3/run-config",
        json={"decision": decision, "executor_attempt_max": 3},
        headers=headers,
    )
    assert bound.status_code == 200, bound.text
    body = bound.json()
    assert body["decision_id"] == "route-pkg-q-part-000"
    assert body["client_max_retries"] == 0
    assert body["max_runner_retries"] == 3
    assert body["transport"] == "chat_completions"
    refused = client.post(
        "/v1/k02next3/run-config",
        json={"decision": decision, "executor_attempt_max": 3,
              "client_max_retries": 1},
        headers=headers,
    )
    assert refused.status_code == 400, refused.text
    assert refused.json()["detail"]["code"] == \
        "SDK_CLIENT_MAX_RETRIES_NONZERO"
    no_actor = client.post(
        "/v1/k02next3/run-config",
        json={"decision": decision, "executor_attempt_max": 3},
    )
    assert no_actor.status_code == 401


def test_k02next3_row_bp06_81_project_to_role_target_flow():
    """| B0B-UNCOVERED_BP06-81 | K02 | Route project work to roles through a defined project-to-role target flow |"""
    client, headers = make_client()
    served = client.post(
        "/v1/k02next3/target-flow",
        json={"project_id": "pkg-q", "target_flow": _target_flow()},
        headers=headers,
    )
    assert served.status_code == 200, served.text
    roles = served.json()["roles"]
    assert sorted(roles) == ["auditor", "director", "manager",
                             "watcher", "worker"]
    for role, resolved in roles.items():
        assert resolved["provider"] == "meta", role
        assert resolved["model"] == MODEL_ID, role
        assert resolved["status"], role
    partial = _target_flow()
    del partial["worker"]
    missing = client.post(
        "/v1/k02next3/target-flow",
        json={"project_id": "pkg-q", "target_flow": partial},
        headers=headers,
    )
    assert missing.status_code == 400, missing.text
    assert missing.json()["detail"]["code"] == "NO_TARGET_FLOW_DEFAULT"
    no_actor = client.post(
        "/v1/k02next3/target-flow",
        json={"project_id": "pkg-q", "target_flow": _target_flow()},
    )
    assert no_actor.status_code == 401


def test_k02next3_row_sdk_132_verified_sdk_surface():
    """| B0B-SDK-132 | K02 | limits architecture conclusions to the verified SDK surface |"""
    from agent_si.sdk_adapter import sdk_adapter as _sdk

    client, headers = make_client()
    resp = client.get("/v1/k02next3/sdk-surface", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["sdk_available"] == _sdk.SDK_AVAILABLE
    assert isinstance(body["sdk_available"], bool)
    surface = body["surface"]
    assert "transport_for_provider" in surface
    assert "OpenAIAgentsSDKAdapter" in surface
    assert "RunConfig" in surface
    assert "CHAT_COMPLETIONS_TRANSPORT" in surface
    for name in surface:
        assert getattr(_sdk, name, None) is not None, name


def test_k02next3_row_bp01_10_planner_idempotent_plan_ref():
    """| B0B-BP01-10 | K02 | TaskPlanner decompose is idempotent on package ref and goal hash via the existing plan ref |"""
    client, headers = make_client()
    first = client.post(
        "/v1/k02next3/plan",
        json={"package_id": "pkg-q", "goal": "quarry goal",
              "specs": _specs()},
        headers=headers,
    )
    assert first.status_code == 200, first.text
    assert first.json()["subtasks"] == ["pkg-q:part-000", "pkg-q:part-001"]
    second = client.post(
        "/v1/k02next3/plan",
        json={"package_id": "pkg-q", "goal": "quarry goal",
              "specs": _specs()},
        headers=headers,
    )
    assert second.status_code == 200, second.text
    assert second.json()["plan_ref"] == first.json()["plan_ref"]
    other = client.post(
        "/v1/k02next3/plan",
        json={"package_id": "pkg-q", "goal": "different goal",
              "specs": _specs()},
        headers=headers,
    )
    assert other.status_code == 200, other.text
    assert other.json()["plan_ref"] != first.json()["plan_ref"]
    no_actor = client.post(
        "/v1/k02next3/plan",
        json={"package_id": "pkg-q", "goal": "quarry goal",
              "specs": _specs()},
    )
    assert no_actor.status_code == 401


def test_k02next3_row_arch_7_dispatch_rejects_unplanned():
    """| B0B-UNCOVERED_ARCH-7 | K02 | An AgentTask without subtask_id is rejected at dispatch and only planned AgentTasks execute |"""
    client, headers = make_client()
    planned = {
        "agent_task_id": "dispatch-pkg-q-part-000",
        "subtask_id": "pkg-q:part-000",
        "agent_id": "agent-1",
        "contract_hash": "hash-q",
    }
    ok_body = {"package_id": "pkg-q", "goal": "quarry goal",
               "specs": _specs(), "agent_task": planned}
    ok_resp = client.post(
        "/v1/k02next3/dispatch", json=ok_body, headers=headers)
    assert ok_resp.status_code == 200, ok_resp.text
    assert ok_resp.json()["subtask_id"] == "pkg-q:part-000"
    bare = dict(planned)
    del bare["subtask_id"]
    missing = client.post(
        "/v1/k02next3/dispatch",
        json={"package_id": "pkg-q", "goal": "quarry goal",
              "specs": _specs(), "agent_task": bare},
        headers=headers,
    )
    assert missing.status_code == 400, missing.text
    assert missing.json()["detail"]["code"] == "DISPATCH_REJECTED"
    unplanned = dict(planned, subtask_id="pkg-q:never-planned")
    refused = client.post(
        "/v1/k02next3/dispatch",
        json={"package_id": "pkg-q", "goal": "quarry goal",
              "specs": _specs(), "agent_task": unplanned},
        headers=headers,
    )
    assert refused.status_code == 400, refused.text
    assert refused.json()["detail"]["code"] == "DISPATCH_REJECTED"
    no_actor = client.post(
        "/v1/k02next3/dispatch", json=ok_body)
    assert no_actor.status_code == 401


def test_k02next3_row_arch_705_corrections_mismatch_rejected():
    """| B0B-UNCOVERED_ARCH-705 | K02 | A TaskPackage whose corrections hash mismatches the checked hash is rejected at issuance |"""
    client, headers = make_client()
    refs = ["ARTIFACT_REF:pkg-q705/shared-a",
            "ARTIFACT_REF:pkg-q705/shared-b"]
    good = client.post(
        "/v1/k02next3/issue",
        json={"package_id": "pkg-q705", "goal": "issue quarry",
              "context_refs": refs, "max_parts": 2,
              "corrections": [{"actor": "user", "text": "fix scope"}]},
        headers=headers,
    )
    assert good.status_code == 200, good.text
    issued = good.json()
    assert len(issued["parts"]) == 2
    assert issued["corrections_hash"]
    stale = client.post(
        "/v1/k02next3/issue",
        json={"package_id": "pkg-q705", "goal": "issue quarry",
              "context_refs": refs, "max_parts": 2,
              "corrections": [{"actor": "user", "text": "fix scope"}],
              "expected_corrections_hash": "deadbeef"},
        headers=headers,
    )
    assert stale.status_code == 400, stale.text
    assert stale.json()["detail"]["code"] == "CORRECTIONS_MISMATCH"
    match = client.post(
        "/v1/k02next3/issue",
        json={"package_id": "pkg-q705b", "goal": "issue quarry",
              "context_refs": refs, "max_parts": 2,
              "corrections": [{"actor": "user", "text": "fix scope"}],
              "expected_corrections_hash": issued["corrections_hash"]},
        headers=headers,
    )
    assert match.status_code == 200, match.text
    assert match.json()["corrections_hash"] == issued["corrections_hash"]
    no_actor = client.post(
        "/v1/k02next3/issue",
        json={"package_id": "pkg-q705", "goal": "issue quarry",
              "context_refs": refs, "max_parts": 2},
    )
    assert no_actor.status_code == 401
