# K07NEXT3 split A: 7 backend-boundary rows over create_app + REAL HTTP.
# One test per row: B0B-BP09-30, B0B-UNCOVERED_ARCH-563,
# B0B-UNCOVERED_ARCH-683, B0B-UNCOVERED_ARCH-686, B0B-UNCOVERED_ARCH-716,
# B0B-UNCOVERED_ARCH-718, B0B-UNCOVERED_ARCH-720.
# The boundary module agent_si.http.k07next3 is mounted onto the real
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

TEST_TOKEN = "k07next3-solo-token"
BASE_SETTINGS = {
    "testing": True,
    "ui_session_token": TEST_TOKEN,
    "secret_store": "memory",
}


def _load_boundary():
    try:
        from agent_si.http import k07next3 as module
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


def test_row_b0b_bp09_30_policy_lifecycle_served(served):
    status, payload = _get(served, "/api/v1/app/policy-lifecycle")
    assert status == 200, payload
    assert payload == {
        "row": "B0B-BP09-30",
        "section": "Manifest section 25A PolicyLifecycleEvent",
        "events": ["ACTIVATED", "SUPERSEDED", "RETIRED"],
    }


def test_row_b0b_uncovered_arch_563_gate_verdicts_served(served):
    status, payload = _get(served, "/api/v1/app/gate-verdicts")
    assert status == 200, payload
    assert payload == {
        "row": "B0B-UNCOVERED_ARCH-563",
        "gate_pass": "PASS",
        "gate_verdicts": ["BLOCKED", "FAIL", "PASS"],
        "audit_results": ["BLOCKED", "ESCALATE", "FAIL", "PASS", "REWORK"],
        "model": "meta/muse-spark-1.3-contributor",
    }


def test_row_b0b_uncovered_arch_683_ledger_register_served(served):
    status, payload = _get(served, "/api/v1/app/ledger-register")
    assert status == 200, payload
    assert payload == {
        "row": "B0B-UNCOVERED_ARCH-683",
        "states": ["PRESERVED", "CHANGED", "MISSING", "CONTRADICTED"],
        "ledger_row": ["package_id", "agents", "peak_concurrency",
                       "wall_time_s"],
    }


def test_row_b0b_uncovered_arch_686_step_limits_served(served):
    status, payload = _get(served, "/api/v1/app/step-limits")
    assert status == 200, payload
    assert payload == {
        "row": "B0B-UNCOVERED_ARCH-686",
        "task_kind": "task",
        "chat_kind": "chat",
        "scope_prefix": "steplimits:",
        "min": 1,
        "cap": 10000,
    }


def test_row_b0b_uncovered_arch_716_project_defaults_served(served):
    status, payload = _get(served, "/api/v1/app/project-defaults")
    assert status == 200, payload
    assert payload == {
        "row": "B0B-UNCOVERED_ARCH-716",
        "currency": "USD",
        "budget_limit": "5.00",
        "soft_limit": "4.00",
        "hard_limit": "5.00",
        "task_max_steps": 40,
        "chat_max_steps": 15,
    }


def test_row_b0b_uncovered_arch_718_control_plane_served(served):
    status, payload = _get(served, "/api/v1/app/control-plane")
    assert status == 200, payload
    assert payload == {
        "row": "B0B-UNCOVERED_ARCH-718",
        "risk_levels": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
        "planned": "PLANNED",
        "map": {
            "director.split": "split.split_package",
            "director.route": "graph.route_task",
            "director.policy": "graph.CONTROL_PLANE_MAP",
            "director.integrate": "graph.HierarchyConfigStore.close_parent",
            "director.decide": "teamcard.DecisionLog.append",
        },
    }


def test_row_b0b_uncovered_arch_720_team_card_served(served):
    status, payload = _get(served, "/api/v1/app/team-card")
    assert status == 200, payload
    assert payload == {
        "row": "B0B-UNCOVERED_ARCH-720",
        "shape": ["provider", "model", "model_kb_facts", "budget_left",
                  "limits"],
        "model": "meta/muse-spark-1.3-contributor",
    }
