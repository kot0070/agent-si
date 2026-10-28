"""K06 Lane A toolguard -- G3 permission ladder.

R0 runs only when task-authorized; R1 needs a TaskContract; R2 is
refused without a Director record; R3 is refused without a user
record; generated commands never gain privilege. Missing or
non-mapping auth is treated as empty (default-deny, never
default-allow). Passes return ok True; refusals return the exact
error code for the failed condition.
"""

from __future__ import annotations

from typing import Any

ACTION_CLASSES: tuple[str, ...] = ("R0", "R1", "R2", "R3")

ERR_R0_NOT_TASK_AUTHORIZED: str = "ERR_R0_NOT_TASK_AUTHORIZED"
ERR_R1_CONTRACT_REQUIRED: str = "ERR_R1_CONTRACT_REQUIRED"
ERR_R2_DIRECTOR_RECORD_REQUIRED: str = "ERR_R2_DIRECTOR_RECORD_REQUIRED"
ERR_R3_USER_RECORD_REQUIRED: str = "ERR_R3_USER_RECORD_REQUIRED"
ERR_GENERATED_PRIVILEGE_DENIED: str = "ERR_GENERATED_PRIVILEGE_DENIED"


def check_permission(
    action_class: str,
    auth: dict[str, Any],
    generated: bool,
) -> dict[str, Any]:
    """Decide whether ``action_class`` may run under ``auth``.

    The generated flag is evaluated first: a generated command is
    refused whatever else it carries. Unknown action classes are
    refused with a reason naming them.
    """
    if generated:
        return {"error": ERR_GENERATED_PRIVILEGE_DENIED}
    if not isinstance(auth, dict):
        auth = {}
    if action_class == "R0":
        if auth.get("task"):
            return {"ok": True, "action_class": "R0"}
        return {"error": ERR_R0_NOT_TASK_AUTHORIZED}
    if action_class == "R1":
        if auth.get("contract"):
            return {"ok": True, "action_class": "R1"}
        return {"error": ERR_R1_CONTRACT_REQUIRED}
    if action_class == "R2":
        if auth.get("contract") and auth.get("director_record"):
            return {"ok": True, "action_class": "R2"}
        return {"error": ERR_R2_DIRECTOR_RECORD_REQUIRED}
    if action_class == "R3":
        if auth.get("contract") and auth.get("user_record"):
            return {"ok": True, "action_class": "R3"}
        return {"error": ERR_R3_USER_RECORD_REQUIRED}
    return {"error": "ERR_UNKNOWN_ACTION_CLASS: %s" % (action_class,)}
