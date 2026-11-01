"""K06D1SUB guard-refusal proofs for POST /api/v1/tools/tools/dispatch.

Allowlisted-but-unregistered tool refuses honest 404 (never 500
IndexError); registered allowlisted tool still dispatches 200; off-list
(task-denied) tool still refuses 403 with its guard record.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fastapi.testclient import TestClient

from agent_si.backend.app import create_app
from agent_si.worker_tools.guard_records import TOOL_NOT_AUTHORIZED

TEST_TOKEN = "k06d1sub-loopback-token"
ACTOR = "tester-k06d1sub"


def _client():
    return TestClient(create_app({"testing": True, "ui_session_token": TEST_TOKEN}))


def _headers():
    return {"x-actor": ACTOR, "x-ui-session-token": TEST_TOKEN}


def _auth_r0():
    return {"subject": "worker", "task": "k06d1sub-task"}


def test_k06d1sub_allowlisted_but_unregistered_refuses_404_never_500():
    client = _client()
    resp = client.post(
        "/api/v1/tools/tools/dispatch",
        json={
            "tool": "k06d1sub-ghost-tool",
            "argv": ["k06d1sub-ghost-tool"],
            "action_class": "R0",
            "auth": _auth_r0(),
            "task_authorized": ["k06d1sub-ghost-tool"],
        },
        headers=_headers(),
    )
    assert resp.status_code in (403, 404), resp.text
    assert resp.status_code != 500, resp.text
    payload = resp.json()
    assert payload["code"] in ("TOOL_NOT_FOUND", TOOL_NOT_AUTHORIZED), payload
    assert "k06d1sub-ghost-tool" in payload["message"]
    assert "traceback" not in resp.text.lower()


def test_k06d1sub_registered_allowlisted_tool_still_dispatches_200():
    client = _client()
    resp = client.post(
        "/api/v1/tools/tools/dispatch",
        json={
            "tool": "status",
            "argv": ["status"],
            "action_class": "R0",
            "auth": _auth_r0(),
            "task_authorized": ["status"],
        },
        headers=_headers(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is True


def test_k06d1sub_off_list_tool_still_refuses_403_with_guard_record():
    client = _client()
    resp = client.post(
        "/api/v1/tools/tools/dispatch",
        json={
            "tool": "other",
            "argv": ["other", "run"],
            "action_class": "R0",
            "auth": _auth_r0(),
            "task_authorized": ["status"],
        },
        headers=_headers(),
    )
    assert resp.status_code == 403, resp.text
    payload = resp.json()
    assert payload["code"] == TOOL_NOT_AUTHORIZED, payload
    assert payload["guard_record"]["tool"] == "other"
    assert payload["guard_record"]["error_code"] == TOOL_NOT_AUTHORIZED
