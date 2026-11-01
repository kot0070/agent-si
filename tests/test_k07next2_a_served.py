# K07NEXT2 split A: 8 backend-boundary rows over create_app + REAL HTTP.
# One test per row: M-P4-159, M-D-D5, HD-APP-ID, M-R-BRAND,
# B0B-BP09-27, B0B-UNCOVERED_BP06-67, B0B-UNCOVERED_ARCH-541,
# B0B-UNCOVERED_ARCH-679.
# The boundary module agent_si.http.k07next2 is mounted onto the real
# seam app (app.py untouched); a uvicorn server on 127.0.0.1 serves it
# in-process and every assertion below drives that socket via urllib
# (no route mocks, no TestClient). RED shape: with the boundary module
# absent the fixture mounts nothing and each test sees an honest 404.
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_WS = os.path.abspath(os.path.join(_HERE, ".."))
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

TEST_TOKEN = "k07next2-solo-token"
BASE_SETTINGS = {
    "testing": True,
    "ui_session_token": TEST_TOKEN,
    "secret_store": "memory",
}


def _load_boundary():
    try:
        from agent_si.http import k07next2 as module
    except Exception:
        return None
    return module


@pytest.fixture(scope="module")
def served():
    from agent_si.backend.app import create_app

    boundary = _load_boundary()
    app = create_app(dict(BASE_SETTINGS))
    if boundary is not None:
        boundary.mount(app)
    import uvicorn

    config = uvicorn.Config(app, host="127.0.0.1", port=0,
                            log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if getattr(server, "started", False):
            break
        time.sleep(0.05)
    assert getattr(server, "started", False), "uvicorn never started"
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=15)


def _get(base, path):
    request = urllib.request.Request(base + path, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return (response.status,
                    json.loads(response.read().decode("utf-8")))
    except urllib.error.HTTPError as err:
        return (err.code, json.loads(err.read().decode("utf-8")))


def test_row_m_p4_159_context_card_served(served):
    status, payload = _get(served, "/api/v1/app/context-card")
    assert status == 200, payload
    assert payload == {
        "row": "M-P4-159",
        "card": "chat-context-card",
        "warn_pct": 70,
        "severe_pct": 85,
        "source": "/api/v1/budget",
        "recorded_action": "one entry per threshold crossing,"
                           " idempotent on re-render",
    }


def test_row_m_d_d5_channel_lane_served(served):
    status, payload = _get(served, "/api/v1/app/channel-lane")
    assert status == 200, payload
    assert payload == {
        "row": "M-D-D5",
        "evaluation": "persisted before socket use",
        "fail_closed": True,
        "pinned_address": True,
        "store": "agent_si_channel_eval.jsonl",
        "socket_timeout_s": 60.0,
    }


def test_row_hd_app_id_served(served):
    status, payload = _get(served, "/api/v1/app/app-id")
    assert status == 200, payload
    assert payload == {
        "row": "HD-APP-ID",
        "app_id": "com.agentsi.app",
        "name": "Agent SI",
    }


def test_row_m_r_brand_served(served):
    status, payload = _get(served, "/api/v1/app/brand")
    assert status == 200, payload
    assert payload == {
        "row": "M-R-BRAND",
        "name": "Agent SI",
        "licence_line": "Copyright (c) 2026 Ivan Soprun",
        "mit_ref": "about.licence.mitText",
    }


def test_row_b0b_bp09_27_retry_policy_served(served):
    status, payload = _get(served, "/api/v1/app/retry-policy")
    assert status == 200, payload
    assert payload == {
        "row": "B0B-BP09-27",
        "section": "Manifest section 16 RetryPolicy",
        "executor_attempt_max": 3,
        "provider_retry_max": 2,
        "format_retry_max": 1,
        "verification_retry_max": 1,
        "verification_correction_max": 2,
        "audit_correction_max": 2,
        "runtime_correction_max": 3,
        "backoff_policy": "",
    }


def test_row_b0b_uncovered_bp06_67_local_config_gate_served(served):
    status, payload = _get(
        served, "/api/v1/app/local-config-gate")
    assert status == 200, payload
    assert payload == {
        "row": "B0B-UNCOVERED_BP06-67",
        "level_id_keys": ["level", "role", "id", "name"],
        "resource_cap_key": "resource_cap",
        "require_gate": "require_local_ai_allowed_at_used_levels",
        "activation_gate": "check_local_only_activation",
        "fail_closed": True,
    }


def test_row_b0b_uncovered_arch_541_planner_router_served(served):
    status, payload = _get(served, "/api/v1/app/planner-router")
    assert status == 200, payload
    assert payload == {
        "row": "B0B-UNCOVERED_ARCH-541",
        "planner": "builds subtask graph,"
                   " never selects provider or model",
        "router": "picks worker class, execution type and needs,"
                  " never a concrete model",
    }


def test_row_b0b_uncovered_arch_679_shell_menus_served(served):
    status, payload = _get(served, "/api/v1/app/shell-menus")
    assert status == 200, payload
    assert payload == {
        "row": "B0B-UNCOVERED_ARCH-679",
        "menus": [
            "menu-chat",
            "menu-agents-live",
            "menu-new-task",
            "menu-projects",
            "menu-tasks",
            "menu-results",
            "menu-settings",
        ],
        "routes": {
            "agentsLive": "/agents/live",
            "projects": "/projects",
            "projectReports": "/projects/:projectId/reports",
        },
    }
