"""K06OPEN10 triple: served env-merge plus belt run evidence plus ASK click round-trip.

testid: k06open10-resume-demo

One behaviour test drives create_app plus the HTTP client on loopback
TEST data only, over the real registry and dispatcher path: the served
detected-environment page plus the served per-project merge, the full
tool-belt chain as run evidence through the chat entry, and the ASK
approval card click round-trip (create, approve click, resume).
"""

from __future__ import annotations

import os
import sys
from typing import Any

import pytest

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from fastapi.testclient import TestClient  # noqa: E402

from agent_si.backend import (  # noqa: E402
    chat_adapter,
    ui_session,
)
from agent_si.backend.app import create_app  # noqa: E402
from agent_si.portability import detection  # noqa: E402
from agent_si.portability.detection import (  # noqa: E402
    ENVIRONMENT_MATRIX,
)
from agent_si.services import commands as services_commands  # noqa: E402
from agent_si.worker_tools.registry import ToolRegistry  # noqa: E402

TESTID = "k06open10-resume-demo"
TEST_ACTOR = "k06open10-tester"
TEST_TASK = "k06open10-demo"
TEST_SUMMARY = "Approve the lane demo plan?"
TEST_OPTIONS = [
    {"option_id": "yes", "label": "Yes"},
    {"option_id": "no", "label": "No"},
]


def _auth() -> dict[str, Any]:
    return {
        "subject": TEST_ACTOR,
        "task": TEST_TASK,
        "contract": "contract-k06open10",
    }


def _alarms(payload: Any) -> list[Any]:
    found: list[Any] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key == "alarm":
                found.append(value)
            else:
                found.extend(_alarms(value))
    elif isinstance(payload, (list, tuple)):
        for value in payload:
            found.extend(_alarms(value))
    return found


def test_testid_present() -> None:
    assert TESTID == "k06open10-resume-demo"


def test_k06open10_resume_demo_triple(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    assert TESTID == "k06open10-resume-demo"
    monkeypatch.setenv("AGENT_SI_SESSION_STORE", str(tmp_path / "sessions"))
    monkeypatch.setenv("AGENT_SI_SECRET_STORE", "memory")
    app = create_app()
    client = TestClient(app)
    headers = {
        "x-actor": TEST_ACTOR,
        "x-ui-session-token": str(app.state.ui_session_token),
    }

    live = client.get("/api/v1/sessions")
    assert live.status_code == 200, live.text

    page = client.get("/api/v1/portability/environment")
    assert page.status_code == 200, page.text
    body = page.json()
    detected = body["detected"]
    assert detected["status"] in ("KNOWN", "UNKNOWN")
    assert detected["alarm"] is False
    assert detected["state"] == detection.detect_this_pc()["state"]
    assert body["matrix"] == list(ENVIRONMENT_MATRIX)
    assert len(body["matrix"]) == 7
    assert set(body["states"]) == set(ENVIRONMENT_MATRIX)
    assert all(v == "UNKNOWN" for v in body["states"].values())
    assert body["check"]["dry_run"] is True
    assert body["check"]["status"] == "green"
    assert all(v is False for v in _alarms(body))

    merged = client.post(
        "/api/v1/portability/run",
        json={
            "argv": ["merge", TEST_TASK],
            "action_class": "R0",
            "task": TEST_TASK,
        },
        headers={"x-actor": TEST_ACTOR},
    )
    assert merged.status_code == 200, merged.text
    outcome = merged.json()
    assert outcome["route"] == "merge"
    assert outcome["project_id"] == TEST_TASK
    assert outcome["environment"]["project_id"] == TEST_TASK
    assert outcome["environment"]["state"] == detected["state"]
    assert outcome["detected"] == detected
    assert all(v is False for v in _alarms(outcome))

    registry = ToolRegistry()
    direct = services_commands.run_declared_service_via_belt(
        ["status"], "R0", _auth(), registry=registry
    )
    assert direct["ok"] is True
    assert direct["service"] == "status"
    assert direct["services"] == services_commands.list_commands()
    assert direct["argv"] == ["status"]
    assert direct["action_class"] == "R0"
    assert isinstance(direct["pid"], int) and direct["pid"] > 0
    assert direct["environment"]["project_id"] == TEST_TASK
    assert direct["environment"]["detected"] == detected
    assert direct["environment"]["environment"] == {
        **detected["state"],
        "project_id": TEST_TASK,
    }
    assert "status" in registry.names()

    via_chat = chat_adapter.run_chat_tool(
        ["status"], "R0", _auth(), registry=ToolRegistry()
    )
    assert via_chat["ok"] is True
    assert via_chat["service"] == "status"
    assert via_chat["environment"]["project_id"] == TEST_TASK

    with pytest.raises(PermissionError, match="ERR_R1_CONTRACT_REQUIRED"):
        services_commands.run_declared_service_via_belt(
            ["status"],
            "R1",
            {"subject": TEST_ACTOR, "scopes": ["tools:exec"]},
            registry=ToolRegistry(),
        )

    created = client.post(
        "/api/v1/asks",
        json={
            "kind": "approval",
            "summary": TEST_SUMMARY,
            "options": TEST_OPTIONS,
        },
        headers=headers,
    )
    assert created.status_code == 200, created.text
    card = created.json()
    assert card["kind"] == "approval"
    assert card["summary"] == TEST_SUMMARY
    assert [o["option_id"] for o in card["options"]] == ["yes", "no"]
    ask_id = card["ask_id"]
    resume_token = card["resume_token"]
    assert ask_id and resume_token

    seen: list[str] = []
    real_resume = ui_session.resume_ask

    def _spy(*, resume_token: str):
        seen.append(resume_token)
        return real_resume(resume_token=resume_token)

    monkeypatch.setattr(ui_session, "resume_ask", _spy)
    decided = client.post(
        f"/api/v1/asks/{ask_id}/approve",
        json={"option_id": "yes", "resume_token": resume_token},
        headers=headers,
    )
    assert decided.status_code == 200, decided.text
    result = decided.json()
    assert result["ask_id"] == ask_id
    assert result["approved_option_id"] == "yes"
    assert result["resume_token"] == resume_token
    assert seen == [resume_token]

    resumed = ui_session.resume_ask(resume_token=resume_token)
    assert resumed.ask_id == ask_id
    assert resumed.kind == "approval"
    assert resumed.summary == TEST_SUMMARY
    assert [o.option_id for o in resumed.options] == ["yes", "no"]

    forged = client.post(
        f"/api/v1/asks/{ask_id}/approve",
        json={
            "option_id": "yes",
            "resume_token": "resume-forged-k06open10-test-only",
        },
        headers=headers,
    )
    assert forged.status_code in (401, 403)
