"""FXPANEL live rows: served RED/GREEN proof for R1/R4/R5.

GET /api/v1/agents/live rows carry the frozen four fields
(agent/scope/deliverable/status) plus the append-only FXPANEL fields
(role/model/step/file/cost/tokens/context/errors/waits). The
control-plane route stays a static dict. The empty-store negative
still serves an empty agents list.
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

from agent_si.backend import agents_live  # noqa: E402
from agent_si.backend.agents_live import live_rows  # noqa: E402
from agent_si.backend.app import create_app  # noqa: E402
from agent_si.backend.orchestration import graph as _graph  # noqa: E402
from agent_si.backend.orchestration.graph import TaskPlanner  # noqa: E402
from agent_si.providers.adapters.base import (  # noqa: E402
    AdapterConfig,
    make_secret_ref,
)
from agent_si.providers.adapters.mock_provider import (  # noqa: E402
    MockProviderAdapter,
)
from agent_si.runtime.manager import run_task_streamed  # noqa: E402

TEST_TOKEN = "fxpanel-live-token"
TEST_SETTINGS = {"testing": True, "ui_session_token": TEST_TOKEN}


# -- FXLOC C5: real budget gate (fail-closed product gate) --------------------
_FXLOC_GATE_PROJECTS = ("fxp-live", "fxp-refused")


def _fxloc_gate():
    """Real gate with this file's projects configured (generous limits)."""
    from agent_si.budget.gate import BudgetGate

    gate = BudgetGate()
    for project in _FXLOC_GATE_PROJECTS:
        gate.configure_project(
            project, "USD", "1000000.00", "900000.00", "1000000.00")
    return gate


@pytest.fixture(autouse=True)
def _fxloc_real_budget_gate():
    """Fail-closed gate needs a real gate: generous limits, restored after."""
    from agent_si.runtime import manager as _mgr

    prev = _mgr._BUDGET_GATE
    _mgr.set_budget_gate(_fxloc_gate())
    yield
    _mgr.set_budget_gate(prev)

FULL_ROW = {
    "agent": "fxp-agent",
    "scope": "fxp-task/fxp-sub",
    "deliverable": "artifact://run/fxp-run/output",
    "status": "RUNNING",
    "role": "manager",
    "model": "mock-canned",
    "step": 2,
    "file": "artifact://run/fxp-run/output",
    "cost": "0.000001",
    "tokens": {"input": 12, "output": 34},
    "context": "artifact:run/fxp-run/input",
    "errors": [],
    "waits": ["approval"],
}


def make_client():
    agents_live.clear_live_rows()
    app = create_app(dict(TEST_SETTINGS))
    headers = {"x-actor": "fxp-tester", "x-ui-session-token": TEST_TOKEN}
    return TestClient(app), headers


def _mock_adapter():
    config = AdapterConfig(
        provider_id="mock",
        instance_id="fxpanel-live-test",
        model="mock-canned",
        secret_ref=make_secret_ref(
            secret_id="mock-secret", provider_id="mock"),
    )
    return MockProviderAdapter(
        config, transport=None, canned=("Mock live reply.",))


def _planned_graph(subtask_id="fxp-sub-001"):
    planner = TaskPlanner()
    _plan_ref, graph = planner.plan(
        "pkg-fxp",
        "fxpanel live run",
        [{"subtask_id": subtask_id, "goal": "serve one canned turn",
          "task_class": "general", "risk": "LOW"}],
    )
    return graph


def test_live_rows_carry_append_only_fields():
    agents_live.clear_live_rows()
    stored = agents_live.record_live_row("fxp-key", dict(FULL_ROW))
    assert stored["agent"] == "fxp-agent"
    assert stored["scope"] == "fxp-task/fxp-sub"
    assert stored["deliverable"] == "artifact://run/fxp-run/output"
    assert stored["status"] == "RUNNING"
    for name in ("role", "model", "step", "file", "cost",
                 "tokens", "context", "errors", "waits"):
        assert name in stored, f"append-only field {name!r} missing"
    assert stored["role"] == "manager"
    assert stored["model"] == "mock-canned"
    assert stored["step"] == 2
    assert stored["tokens"] == {"input": 12, "output": 34}
    assert stored["errors"] == []
    assert stored["waits"] == ["approval"]
    payload = live_rows()
    assert set(payload) == {"agents"}
    assert payload["agents"] == [stored]


def test_live_route_serves_full_row():
    client, _headers = make_client()
    agents_live.record_live_row("fxp-key", dict(FULL_ROW))
    resp = client.get("/api/v1/agents/live")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"agents": [dict(FULL_ROW)]}


def test_control_plane_still_static():
    client, _headers = make_client()
    before = client.get("/api/v1/hierarchy/control-plane")
    assert before.status_code == 200, before.text
    assert before.json() == _graph.control_plane_map()
    agents_live.record_live_row("fxp-key", dict(FULL_ROW))
    after = client.get("/api/v1/hierarchy/control-plane")
    assert after.status_code == 200, after.text
    assert after.json() == _graph.control_plane_map() == before.json()


def test_empty_live_store_serves_empty_agents():
    client, _headers = make_client()
    resp = client.get("/api/v1/agents/live")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"agents": []}


def test_streamed_manager_run_records_full_live_row():
    agents_live.clear_live_rows()
    events = list(run_task_streamed(
        None,
        agent_task={
            "agent_task_id": "agent-task-fxp",
            "subtask_id": "fxp-sub-001",
            "agent_id": "agent-fxp",
            "contract_hash": "hash-fxp",
        },
        graph=_planned_graph(),
        provider_adapter=_mock_adapter(),
        project_id="fxp-live",
        task_id="task-fxp-live",
        message="hello live",
        manager_id="mgr-fxp",
        max_agent_steps=3,
    ))
    assert events and events[-1].event == "done"
    payload = live_rows()
    rows = {row["scope"]: row for row in payload["agents"]}
    assert rows, "a real streamed run records live rows"
    row = next(iter(rows.values()))
    for name in ("agent", "scope", "deliverable", "status",
                 "role", "model", "step", "file", "cost",
                 "tokens", "context", "errors", "waits"):
        assert name in row, f"live field {name!r} missing"
    assert row["role"] == "manager"
    assert row["model"] == "mock-canned"
    assert isinstance(row["step"], int)
    assert isinstance(row["tokens"], dict)
    assert set(row["tokens"]) == {"input", "output"}
    assert row["context"].startswith("artifact:run/")
    assert isinstance(row["errors"], list)
    assert isinstance(row["waits"], list)
    assert isinstance(row["cost"], str) and row["cost"]
    assert isinstance(row["file"], str)


def test_dispatch_rejected_still_records_row_with_errors():
    agents_live.clear_live_rows()
    events = list(run_task_streamed(
        None,
        agent_task={
            "agent_task_id": "agent-task-bare",
            "agent_id": "agent-fxp",
            "contract_hash": "hash-fxp",
        },
        graph=_planned_graph(),
        provider_adapter=_mock_adapter(),
        project_id="fxp-refused",
        task_id="task-fxp-refused",
        message="must not run",
        manager_id="mgr-fxp",
        max_agent_steps=3,
    ))
    assert len(events) == 1
    assert events[0].event == "dispatch_rejected"
    payload = live_rows()
    assert payload["agents"], "a refused run still records a live row"
    row = payload["agents"][0]
    assert row["status"] == "REJECTED"
    assert row["role"] == "manager"
    assert row["errors"], "a refused run names its reason in errors"
    assert "dispatch" in " ".join(row["errors"]).lower()
