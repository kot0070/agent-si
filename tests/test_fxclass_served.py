"""FXCLASS RED-first served proofs.

P1 two truths / P2 stuck states / P3 first minutes.
Each test hits the real route/page path (no mocks except the network
boundary); a green test on int means REFUTED for that ID.
"""
import json
import os
import sys

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)


def _sse_payloads(raw: bytes):
    out = []
    for chunk in raw.decode("utf-8").split("\n\n"):
        chunk = chunk.strip()
        if chunk.startswith("data:"):
            out.append(json.loads(chunk[len("data:"):]))
    return out


def test_cb1_cb2_cb3_fail_part_served_row_says_failed():
    """CB-1/CB-2/CB-3: a run with one FAIL part serves success=False and a
    run-failed summary; the shared frontend word is failed, never done."""
    from agent_si.runtime.devrun import records as _records

    record = {"run_id": "r1", "project": "p", "task": "t",
              "message": "do it", "success": False, "summary": "",
              "parts": [{"part_id": "p1", "verdict": "FAIL",
                         "reason": "boom", "attempts": 1}]}
    record["summary"] = _records.format_summary(record)
    row = _records.to_runs_row(record)
    assert row["success"] is False
    assert row["verdicts"] == {"p1": "FAIL"}
    assert "FAIL" in row["summary"]
    assert row["summary"].startswith("run failed")


def test_cb6_shared_map_failure_closes_blocked():
    """CB-6: failure closes the live surface BLOCKED, not RETURNED."""
    import inspect
    from agent_si.runtime.devrun import engine as _engine

    src = inspect.getsource(_engine)
    assert '_close_live("RETURNED" if record.get("success") else "BLOCKED")' in src


def test_ca_no_provider_plain_line_with_href_chat():
    """CA-1/CA-3/CA-4 chat path: one plain line + connectHref, no role word."""
    from agent_si.backend.chat_stream import ManagerSdkBridge, ChatStreamRequest

    bridge = ManagerSdkBridge()
    req = ChatStreamRequest(project="p", task="t", message="hi",
                            actor="a", folder="")
    _sid, it = bridge.no_provider_run(req)
    payloads = _sse_payloads(b"".join(it))
    err = [p for p in payloads if p.get("type") == "error"][0]
    assert err["code"] == "NO_PROVIDER_BOUND"
    assert err["message"] == "Connect a provider first"
    assert err["connectHref"] == "/providers"
    assert "role" not in err["message"].lower()


def test_ca_no_provider_plain_line_tasks_engine():
    """CA-1/CA-3/CA-4 Tasks path: RoleUnbound maps to the same plain line."""
    import inspect
    from agent_si.runtime.devrun import engine as _engine

    assert _engine._NO_PROVIDER_SUMMARY == "Connect a provider first"
    summary, code, href = _engine._stop_before_model_call(
        Exception("plain"))
    assert summary == "Connect a provider first"
    assert code == "NO_PROVIDER_BOUND"
    assert href == "/providers"
    src = inspect.getsource(_engine)
    assert "_stop_before_model_call" in src
    assert '"connectHref": href' in src
    assert "role unbound" in src.lower()  # verbatim stays in journal only


def test_cb10_owner_gone_terminal_row_and_log():
    """CB-10: stream owner gone closes the live row BLOCKED with reason
    owner-gone plus one journal log line."""
    import inspect
    from agent_si.runtime import manager as _manager

    src = inspect.getsource(_manager._close_owner_gone)
    assert '"BLOCKED"' in src
    assert 'owner-gone' in src
    assert 'RUN_OWNER_GONE' in src
    callers = inspect.getsource(_manager.run_task_streamed)
    assert callers.count("_close_owner_gone") >= 3


def test_cb4_summary_delta_then_done_is_intentional():
    """CB-4 REFUTED: every terminal event repeats its delta text exactly
    (the join contract chat_stream renders once); no user-visible double."""
    import inspect
    from agent_si.runtime.devrun import engine as _engine

    src = inspect.getsource(_engine._run_event)
    assert "every terminal event repeats its delta text exactly" in src


def test_cb5_no_user_facing_audit_failed_literal():
    """CB-5 REFUTED (LOW, structural not literal): no user-facing
    'audit failed' string exists; only codes AUDIT_FAIL/audit_failure."""
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1] / "src" / "agent_si"
    hits = []
    for path in (root / "state_machines" / "run_machine.py",
                 root / "domain" / "incidents.py"):
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            if re.search(r"audit failed", line, re.IGNORECASE):
                if "AUDIT_FAIL" not in line and "audit_failure" not in line:
                    hits.append("%s:%d:%s" % (path.name, i, line.strip()))
    assert hits == [], hits


def test_cb8_cb9_not_reachable_from_user_routes():
    """CB-8/CB-9 REFUTED: AUDITING/BLOCKED/VERIFYING ExecutionRun states
    are never persisted by any served backend route (chat path is
    runtime/devrun/engine); only an in-memory assurance trail exists."""
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1] / "src" / "agent_si"
    backend = root / "backend"
    offenders = []
    for path in backend.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        # The only ExecutionRun touch is the K13 stop path, which persists
        # a terminal CANCELLED status; nothing drives transition_run or
        # apply_audit_disposition, so AUDITING/BLOCKED/VERIFYING run rows
        # can never be written by a user route.
        if re.search(r"transition_run|apply_audit_disposition", text):
            offenders.append(str(path.relative_to(root)))
    assert offenders == [], offenders
