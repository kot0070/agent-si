"""K06MH1 behaviour tests: MH-1 escalation park + MH-3 toolguard reject.

Served path: create_app + TestClient (loopback only, no keys, no
network). Unit leg proves zero execution on an off-list call.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.worker_tools import ToolRegistry, guarded_dispatch  # noqa: E402
from agent_si.worker_tools.escalation import ESCALATED  # noqa: E402
from agent_si.worker_tools.guard_records import TOOL_NOT_AUTHORIZED  # noqa: E402
from agent_si.worker_tools.registry import (  # noqa: E402
    ToolNotAuthorizedError,
    ToolNotFoundError,
)

TEST_TOKEN = "k06mh1-loopback-token"
ACTOR = "tester-k06mh1"


def _settings():
    return {"testing": True, "ui_session_token": TEST_TOKEN}


def _auth():
    return {"x-actor": ACTOR, "x-ui-session-token": TEST_TOKEN}


def _client():
    return TestClient(create_app(_settings()))


def _auth_r0():
    return {"subject": "worker", "task": "task-1"}


# --- MH-1: budget exhaustion parks ESCALATED with a card, never silent ---


def test_mh1_exhaustion_parks_escalated_with_card():
    client = _client()
    last = None
    for attempt in range(3):
        resp = client.post(
            "/api/v1/k06/runs/attempt",
            json={
                "run_id": "run-1",
                "ok": False,
                "evidence_ref": "ev-%d" % (attempt,),
                "budget": 2,
            },
            headers=_auth(),
        )
        assert resp.status_code == 200, resp.text
        last = resp.json()
    assert last["state"] == ESCALATED
    card = last["card"]
    assert card is not None
    assert card["testid"] == "escalation-card"
    assert card["state"] == ESCALATED
    assert card["reason"]
    assert card["evidence_refs"] == ["ev-0", "ev-1", "ev-2"]
    assert card["actions"] == ["resume", "discard"]


def test_mh1_card_visible_in_run_view_and_chat():
    client = _client()
    for attempt in range(2):
        resp = client.post(
            "/api/v1/k06/runs/attempt",
            json={
                "run_id": "run-2",
                "ok": False,
                "evidence_ref": "ev-%d" % (attempt,),
                "budget": 1,
            },
            headers=_auth(),
        )
        assert resp.status_code == 200, resp.text
    view = client.get("/api/v1/k06/runs/run-2")
    assert view.status_code == 200, view.text
    assert view.json()["state"] == ESCALATED
    assert view.json()["card"]["testid"] == "escalation-card"
    chat = client.get("/api/v1/k06/chat/cards", params={"run_id": "run-2"})
    assert chat.status_code == 200, chat.text
    cards = chat.json()["cards"]
    assert len(cards) == 1
    assert cards[0]["testid"] == "escalation-card"
    assert cards[0]["reason"]
    assert cards[0]["evidence_refs"]


def test_mh1_resume_and_discard():
    client = _client()
    for _ in range(2):
        client.post(
            "/api/v1/k06/runs/attempt",
            json={"run_id": "run-3", "ok": False,
                  "evidence_ref": "ev", "budget": 0},
            headers=_auth(),
        )
    assert client.get("/api/v1/k06/runs/run-3").json()["state"] == ESCALATED
    resumed = client.post("/api/v1/k06/runs/run-3/resume", headers=_auth())
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["state"] == "RUNNING"
    assert resumed.json()["card"] is None
    client.post(
        "/api/v1/k06/runs/attempt",
        json={"run_id": "run-3", "ok": False,
              "evidence_ref": "ev", "budget": 0},
        headers=_auth(),
    )
    discarded = client.post("/api/v1/k06/runs/run-3/discard",
                            headers=_auth())
    assert discarded.status_code == 200, discarded.text
    assert discarded.json()["state"] == "DISCARDED"


def test_mh1_passing_attempt_never_parks():
    client = _client()
    resp = client.post(
        "/api/v1/k06/runs/attempt",
        json={"run_id": "run-4", "ok": True,
              "evidence_ref": "ev", "budget": 0},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["state"] == "RUNNING"
    assert resp.json()["card"] is None


# --- MH-3: off-list tool calls rejected, named code + record, no exec ---


def test_mh3_served_off_list_rejected_with_code_and_record():
    client = _client()
    resp = client.post(
        "/api/v1/k06/tools/dispatch",
        json={
            "tool": "other",
            "argv": ["other", "run"],
            "action_class": "R0",
            "auth": _auth_r0(),
            "task_authorized": ["status"],
        },
        headers=_auth(),
    )
    assert resp.status_code == 403, resp.text
    payload = resp.json()
    assert payload["code"] == TOOL_NOT_AUTHORIZED
    assert "other" in payload["message"]
    assert payload["guard_record"]["testid"] == "guard-record"
    assert payload["guard_record"]["error_code"] == TOOL_NOT_AUTHORIZED
    listed = client.get("/api/v1/k06/guard-records")
    assert listed.status_code == 200, listed.text
    records = listed.json()["records"]
    assert any(
        r["tool"] == "other" and r["error_code"] == TOOL_NOT_AUTHORIZED
        for r in records
    )


def test_mh3_served_listed_tool_executes():
    client = _client()
    resp = client.post(
        "/api/v1/k06/tools/dispatch",
        json={
            "tool": "status",
            "argv": ["status"],
            "action_class": "R0",
            "auth": _auth_r0(),
            "task_authorized": ["status"],
        },
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is True


def test_mh3_unit_off_list_never_executes():
    calls = []

    def _impl(argv, action_class, auth):
        calls.append((argv, action_class))
        return {"ok": True}

    class _Entry:
        name = "other"
        action_class = "R0"

        def load(self):
            return _impl

    registry = ToolRegistry()
    registry.register(_Entry())
    store: list = []
    try:
        guarded_dispatch(
            ["other", "run"], "R0", _auth_r0(),
            tool="other", registry=registry,
            task_authorized=["status"], guard_store=store,
        )
    except ToolNotAuthorizedError as exc:
        assert "TOOL_NOT_AUTHORIZED" in str(exc)
        assert "other" in str(exc)
    else:
        raise AssertionError("off-list call was not rejected")
    assert calls == []
    assert len(store) == 1
    assert store[0]["testid"] == "guard-record"
    assert store[0]["error_code"] == TOOL_NOT_AUTHORIZED


def test_mh3_unit_no_list_keeps_old_unknown_tool_error():
    from agent_si.worker_tools.registry import ToolNotFoundError as _NF

    try:
        guarded_dispatch(
            ["nope"], "R0", _auth_r0(),
            tool="nope", registry=ToolRegistry(),
        )
    except _NF as exc:
        assert "nope" in str(exc)
    else:
        raise AssertionError("unknown tool was not refused")
    assert ToolNotFoundError is _NF
