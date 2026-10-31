"""K06MH1 behaviour tests: MH-1 escalation park + MH-3 toolguard reject.

Served path: create_app + TestClient (loopback only, no keys, no
network). Unit leg proves zero execution on an off-list call.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fastapi.testclient import TestClient

from agent_si.backend.app import create_app
from agent_si.worker_tools import ToolRegistry, guarded_dispatch
from agent_si.worker_tools.escalation import ESCALATED
from agent_si.worker_tools.guard_records import TOOL_NOT_AUTHORIZED
from agent_si.worker_tools.registry import (
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
                "evidence_ref": f"ev-{attempt}",
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
                "evidence_ref": f"ev-{attempt}",
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


# --- M-D-D8: tools only via registry plus guarded dispatcher ---


def test_d8_explicit_task_deny_refuses_first_served():
    client = _client()
    resp = client.post(
        "/api/v1/k06/tools/dispatch",
        json={
            "tool": "status",
            "argv": ["status"],
            "action_class": "R0",
            "auth": _auth_r0(),
            "task_authorized": False,
        },
        headers=_auth(),
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["code"] == "TOOLGUARD_DENIED"


def test_d8_unknown_tool_refused_never_executes():
    registry = ToolRegistry()
    try:
        registry.load("no-such-tool")
    except ToolNotAuthorizedError as exc:
        assert exc.code == TOOL_NOT_AUTHORIZED
    else:
        raise AssertionError("unknown tool was executed or allowed")
    assert len(registry.guard_records) == 1
    assert registry.guard_records[0].code == TOOL_NOT_AUTHORIZED
    store: list = []
    try:
        guarded_dispatch(
            ["no-such-tool"], "R0", _auth_r0(),
            tool="no-such-tool", registry=registry,
            task_authorized=["no-such-tool"], guard_store=store,
        )
    except ToolNotAuthorizedError as exc:
        assert exc.code == TOOL_NOT_AUTHORIZED
    else:
        raise AssertionError("unknown tool was executed or allowed")


# --- M-D-D36: action execution persisted; repeat verified before repeat ---


def test_d36_repeat_runs_verified_then_persisted_served():
    client = _client()
    for _ in range(2):
        resp = client.post(
            "/api/v1/k06/services/acceptance",
            json={
                "service": "status",
                "argv": ["status"],
                "action_class": "R0",
                "auth": _auth_r0(),
            },
            headers=_auth(),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["ok"] is True
    listed = client.get("/api/v1/k06/services/acceptance")
    assert listed.status_code == 200, listed.text
    runs = listed.json()["runs"]
    assert [r["run_id"] for r in runs] == ["acceptance-1", "acceptance-2"]
    assert all(r["evidence_refs"] for r in runs)


# --- M-D-D51: fail-closed with a persisted evaluation, no deadlock ---


def test_d51_parked_attempts_fail_closed_with_escape_served():
    client = _client()
    for attempt in range(2):
        client.post(
            "/api/v1/k06/runs/attempt",
            json={"run_id": "run-d51", "ok": False,
                  "evidence_ref": f"ev-{attempt}", "budget": 1},
            headers=_auth(),
        )
    assert client.get("/api/v1/k06/runs/run-d51").json()["state"] == ESCALATED
    late = client.post(
        "/api/v1/k06/runs/attempt",
        json={"run_id": "run-d51", "ok": False,
              "evidence_ref": "ev-late", "budget": 1},
        headers=_auth(),
    )
    assert late.status_code == 200, late.text
    assert late.json()["state"] == ESCALATED
    assert late.json()["card"]["actions"] == ["resume", "discard"]
    resumed = client.post("/api/v1/k06/runs/run-d51/resume", headers=_auth())
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["state"] == "RUNNING"
    for attempt in range(2):
        client.post(
            "/api/v1/k06/runs/attempt",
            json={"run_id": "run-d51", "ok": False,
                  "evidence_ref": f"ev2-{attempt}", "budget": 1},
            headers=_auth(),
        )
    discarded = client.post("/api/v1/k06/runs/run-d51/discard",
                            headers=_auth())
    assert discarded.status_code == 200, discarded.text
    assert discarded.json()["state"] == "DISCARDED"


def test_d51_channel_evaluation_persisted_before_socket_use():
    import importlib.util
    import json
    import socket
    import tempfile
    from pathlib import Path

    services_dir = (
        Path(__file__).resolve().parent.parent
        / "src" / "agent_si" / "services"
    )
    spec = importlib.util.spec_from_file_location(
        "d51_served_socket", str(services_dir / "channel_socket.py"))
    assert spec is not None and spec.loader is not None
    channel_socket = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(channel_socket)

    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    closed_port = probe.getsockname()[1]
    probe.close()

    fd, store = tempfile.mkstemp(prefix="d51-served-", suffix=".jsonl")
    import os as _os

    _os.close(fd)
    Path(store).unlink()
    try:
        result = channel_socket.open_channel(
            {"host": "127.0.0.1", "port": closed_port},
            store_path=store,
            timeout=2.0,
        )
        assert result["decision"] == "deny"
        rows = [
            json.loads(line)
            for line in Path(store).read_text(
                encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(rows) == 1
        assert rows[0]["decision"] == "allow"
        assert rows[0]["pinned_ip"] == "127.0.0.1"
        assert rows[0]["port"] == closed_port
    finally:
        if Path(store).exists():
            Path(store).unlink()
    denied = channel_socket.open_channel(
        {"host": "127.0.0.1", "port": closed_port},
        store_path=str(Path(tempfile.gettempdir())),
        timeout=2.0,
    )
    assert denied["decision"] == "deny"
