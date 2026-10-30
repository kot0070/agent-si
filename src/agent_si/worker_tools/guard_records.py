"""K06 worker-tools guard-decision records (MH-3 evidence).

Every deterministic reject of a tool call outside the task-authorized
list is filed here with its named error code before anything executes.
Records are plain data; the served guard-records view reads this store.
"""

from __future__ import annotations

from typing import Any

TOOL_NOT_AUTHORIZED = "TOOL_NOT_AUTHORIZED"

GUARD_RECORD_TESTID = "guard-record"


def record_guard_decision(
    store: list[dict[str, Any]],
    *,
    tool: str,
    decision: str,
    reason: str,
    evidence_ref: str,
    error_code: str | None = None,
) -> dict[str, Any]:
    """Append one guard decision and return it (new dict, store owns it)."""
    record: dict[str, Any] = {
        "testid": GUARD_RECORD_TESTID,
        "tool": tool,
        "decision": decision,
        "reason": reason,
        "evidence_ref": evidence_ref,
    }
    if error_code is not None:
        record["error_code"] = error_code
    store.append(dict(record))
    return record


def list_guard_records(store: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a copy of every filed guard decision, oldest first."""
    return [dict(record) for record in store]
