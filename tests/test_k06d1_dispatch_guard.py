"""K06D1 dispatch guard-before-lookup probe (durable collateral).

Allowlisted-but-unregistered tool on the served dispatch route refuses
honest 404, never 500 IndexError. Registered and task-denied paths keep
their shape (covered by the K06REST contract files).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fastapi.testclient import TestClient

from agent_si.backend.app import create_app

TEST_TOKEN = "k06d1-loopback-token"
ACTOR = "tester-k06d1"


def test_k06d1_allowlisted_but_unregistered_refuses_404_never_500():
    client = TestClient(
        create_app({"testing": True, "ui_session_token": TEST_TOKEN})
    )
    resp = client.post(
        "/api/v1/k06/tools/dispatch",
        json={
            "tool": "k06d1-ghost-tool",
            "argv": ["k06d1-ghost-tool"],
            "action_class": "R0",
            "auth": {"subject": "worker", "task": "k06d1-task"},
            "task_authorized": ["k06d1-ghost-tool"],
        },
        headers={"x-actor": ACTOR, "x-ui-session-token": TEST_TOKEN},
    )
    assert resp.status_code == 404, resp.text
    payload = resp.json()
    assert payload["code"] == "TOOL_NOT_FOUND"
    assert "k06d1-ghost-tool" in payload["message"]
    assert "traceback" not in resp.text.lower()
