"""K02NEXT7 served proof: rows 1-5 (orchestration+hierarchy lane).

testid k02next7-served; one behaviour test per BUILD_PLAN row via
create_app + HTTP client over the real served app (orchestration seam
register_k02next7_routes; every route delegates its row decision to
the real module; refusals keep the frozen USER_WRITE guard shape
(401 missing x-actor, 403 bad token).

Rows (CODER-1 Sable owns rows 1-5; one served test per row):
- R1 B0B-UNCOVERED_UI_DELTA-36: route GET /hierarchy/k02next7/sdk-transport,
  test test_k02next7_served_r1_ui_delta_36. Non-OpenAI providers route
  through the generic OpenAI-compatible Chat Completions adapter.
- R2 B0B-BP03-4: route POST /hierarchy/k02next7/run-config,
  test test_k02next7_served_r2_bp03_4. SDK client max_retries=0;
  runner retries only through the RoutingDecision-bound RunConfig.
- R3 B0B-UNCOVERED_BP06-81: route POST /hierarchy/k02next7/target-flow,
  test test_k02next7_served_r3_bp06_81. Project work reaches roles
  through the defined project-to-role target flow, never a default.
- R4 B0B-SDK-132: route GET /hierarchy/k02next7/sdk-surface,
  test test_k02next7_served_r4_sdk_132. Architecture conclusions stay
  within the verified SDK surface.
- R5 B0B-UNCOVERED_ARCH-57: route GET /hierarchy/k02next7/sdk-transport,
  test test_k02next7_served_r5_arch_57. Chat Completions for non-OpenAI
  providers; the served contract never assumes a Responses API.
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
    from agent_si.backend.orchestration import (
        hierarchy_routes as _seam,
    )
    _SEAM_ERROR = None
except Exception as err:  # seam unserved: every test below fails RED
    _seam = None
    _SEAM_ERROR = err

TEST_TOKEN = "k02next7-served-token"

MODEL_ID = "meta/muse-spark-1.3-contributor"


def make_client():
    if _seam is None or not hasattr(_seam, "register_k02next7_routes"):
        raise AssertionError(
            f"K02NEXT7 seam unserved: {_SEAM_ERROR!r}")
    app = create_app({"testing": True, "ui_session_token": TEST_TOKEN})
    _seam.register_k02next7_routes(app)
    headers = {"x-actor": "manager-1", "x-ui-session-token": TEST_TOKEN}
    return TestClient(app), headers


def _target_flow():
    return {
        role: {"provider": "meta", "model": MODEL_ID}
        for role in ("director", "manager", "worker", "auditor", "watcher")
    }


def test_k02next7_served_r1_ui_delta_36():
    """R1 B0B-UNCOVERED_UI_DELTA-36: non-OpenAI via Chat Completions adapter."""
    from agent_si.providers.adapters import base as _base
    from agent_si.providers.adapters import openai_compat as _compat

    client, headers = make_client()
    for provider in ("meta", "acme-custom", "openai-compatible-x"):
        resp = client.get(
            "/hierarchy/k02next7/sdk-transport",
            params={"provider": provider},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["provider"] == provider
        assert body["transport"] == "chat_completions"
        assert body["entry"] == "transport_for_provider"
        assert body["adapter_kind"] == "openai_compat"
        assert body["openai_compat"] is True
        assert body["chat_path"] == "/chat/completions"
    openai = client.get(
        "/hierarchy/k02next7/sdk-transport",
        params={"provider": "openai"},
        headers=headers,
    )
    assert openai.status_code == 200, openai.text
    assert openai.json()["transport"] == "sdk_default"
    blank = client.get(
        "/hierarchy/k02next7/sdk-transport",
        params={"provider": "  "},
        headers=headers,
    )
    assert blank.status_code == 400
    config = _base.AdapterConfig(
        provider_id="acme-custom",
        model=MODEL_ID,
        base_url="http://localhost:9",
        secret_ref=_base.make_secret_ref("sid-1", "acme-custom"),
    )
    assert config.max_retries == 0
    seen: dict = {}

    def echo_transport(request):
        seen.update(request)
        return {"output_text": "hello", "finish": "stop", "usage": {}}

    adapter = _compat.OpenAICompatAdapter(config, echo_transport)
    out = adapter.invoke([{"role": "user", "content": "hi"}])
    assert out.output_text == "hello"
    assert seen["chat_path"] == "/chat/completions"


def test_k02next7_served_r2_bp03_4():
    """R2 B0B-BP03-4: client max_retries=0, retries via RoutingDecision."""
    client, headers = make_client()
    decision = {
        "decision_id": "route-pkg-n7-part-000",
        "project_id": "pkg-n7",
        "task_id": "task-n7",
        "run_id": "run-n7",
        "selected_provider": "meta",
        "selected_model": MODEL_ID,
        "route": "tool-part",
        "strategy": "single",
    }
    bound = client.post(
        "/hierarchy/k02next7/run-config",
        json={"decision": decision, "executor_attempt_max": 3},
        headers=headers,
    )
    assert bound.status_code == 200, bound.text
    body = bound.json()
    assert body["decision_id"] == "route-pkg-n7-part-000"
    assert body["client_max_retries"] == 0
    assert body["max_runner_retries"] == 3
    assert body["transport"] == "chat_completions"
    refused = client.post(
        "/hierarchy/k02next7/run-config",
        json={"decision": decision, "executor_attempt_max": 3,
              "client_max_retries": 1},
        headers=headers,
    )
    assert refused.status_code == 400, refused.text
    assert refused.json()["detail"]["code"] == \
        "SDK_CLIENT_MAX_RETRIES_NONZERO"
    no_actor = client.post(
        "/hierarchy/k02next7/run-config",
        json={"decision": decision, "executor_attempt_max": 3},
    )
    assert no_actor.status_code == 401


def test_k02next7_served_r3_bp06_81():
    """R3 B0B-UNCOVERED_BP06-81: project work via the target flow."""
    client, headers = make_client()
    served = client.post(
        "/hierarchy/k02next7/target-flow",
        json={"project_id": "pkg-n7", "target_flow": _target_flow()},
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
        "/hierarchy/k02next7/target-flow",
        json={"project_id": "pkg-n7", "target_flow": partial},
        headers=headers,
    )
    assert missing.status_code == 400, missing.text
    assert missing.json()["detail"]["code"] == "NO_TARGET_FLOW_DEFAULT"
    no_actor = client.post(
        "/hierarchy/k02next7/target-flow",
        json={"project_id": "pkg-n7", "target_flow": _target_flow()},
    )
    assert no_actor.status_code == 401


def test_k02next7_served_r4_sdk_132():
    """R4 B0B-SDK-132: conclusions stay within the verified SDK surface."""
    from agent_si.sdk_adapter import sdk_adapter as _sdk

    client, headers = make_client()
    resp = client.get("/hierarchy/k02next7/sdk-surface", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["sdk_available"] == _sdk.SDK_AVAILABLE
    assert isinstance(body["sdk_available"], bool)
    assert body["entry"] == "verified_sdk_surface"
    surface = body["surface"]
    assert "transport_for_provider" in surface
    assert "OpenAIAgentsSDKAdapter" in surface
    assert "RunConfig" in surface
    assert "CHAT_COMPLETIONS_TRANSPORT" in surface
    for name in surface:
        assert getattr(_sdk, name, None) is not None, name


def test_k02next7_served_r5_arch_57():
    """R5 B0B-UNCOVERED_ARCH-57: Chat Completions, never Responses API."""
    client, headers = make_client()
    for provider in ("meta", "anthropic", "acme-custom"):
        resp = client.get(
            "/hierarchy/k02next7/sdk-transport",
            params={"provider": provider},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["transport"] == "chat_completions"
        assert "responses" not in json.dumps(body).lower()
