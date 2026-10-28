"""Lane B services prefix (frozen interface G1).

Every services command routes argv-only through the injected Lane A
guard callable (G1): evaluate(argv, action_class, auth) -> dict with
decision (allow|ask|deny), reason, evidence_ref. This module keeps no
local state, holds no shell strings, and never imports guard code: the
caller injects the guard callable, so each invocation produces exactly
one guard evaluation and repeated identical calls cannot duplicate a
mutation locally.

Error codes: E_BAD_ARGV, E_BAD_ACTION_CLASS, E_BAD_AUTH.
Secrets travel inside auth only by reference and are never copied into
results: success results carry exactly decision, reason, evidence_ref.
Argument strings pass through verbatim (backslash-exact, no
normalisation of any kind).
"""

from __future__ import annotations

from typing import Any, Callable, Literal

GuardEvaluate = Callable[
    [list[str], Literal["R0", "R1", "R2", "R3"], dict[str, Any]], dict[str, Any]
]

ACTION_CLASSES: tuple[str, ...] = ("R0", "R1", "R2", "R3")


def list_commands() -> list[str]:
    """Return the declared services command set (non-empty list of names)."""
    return ["status", "list", "start", "stop", "restart", "enable", "disable"]


def run_command(
    argv: list[str],
    action_class: str,
    auth: dict[str, Any],
    guard_evaluate: GuardEvaluate,
) -> dict[str, Any]:
    """Route one services invocation through the injected guard.

    Validation failures return {"error": <code>} without calling the
    guard. Valid calls forward a verbatim copy of argv plus the action
    class and a copy of auth to guard_evaluate exactly once and return
    only the guard verdict keys decision, reason, evidence_ref.
    """
    if (
        not isinstance(argv, (list, tuple))
        or len(argv) == 0
        or any(not isinstance(item, str) or item == "" for item in argv)
    ):
        return {"error": "E_BAD_ARGV"}
    if not isinstance(action_class, str) or action_class not in ACTION_CLASSES:
        return {"error": "E_BAD_ACTION_CLASS"}
    if not isinstance(auth, dict) or len(auth) == 0:
        return {"error": "E_BAD_AUTH"}
    verdict = guard_evaluate(list(argv), action_class, dict(auth))
    return {
        "decision": verdict["decision"],
        "reason": verdict["reason"],
        "evidence_ref": verdict["evidence_ref"],
    }


def run_declared_service_via_belt(
    argv: list[str],
    action_class: str,
    auth: dict[str, Any],
    *,
    tool: str | None = None,
    registry: Any | None = None,
) -> dict[str, Any]:
    """Run one declared services command through the real tool belt.

    Validation failures return {"error": <code>} without touching the
    belt (E_BAD_ARGV, E_BAD_ACTION_CLASS, E_BAD_AUTH, plus
    E_UNKNOWN_SERVICE when the route is outside list_commands()).
    Valid calls resolve the route through the worker_tools registry
    and execute it via guarded_dispatch, so every call passes the
    Lane A guard. The belt is imported lazily so this module never
    takes a top-level dependency on Lane A.
    """
    if (
        not isinstance(argv, (list, tuple))
        or len(argv) == 0
        or any(not isinstance(item, str) or item == "" for item in argv)
    ):
        return {"error": "E_BAD_ARGV"}
    if not isinstance(action_class, str) or action_class not in ACTION_CLASSES:
        return {"error": "E_BAD_ACTION_CLASS"}
    if not isinstance(auth, dict) or len(auth) == 0:
        return {"error": "E_BAD_AUTH"}
    name = tool if tool is not None else list(argv)[0]
    if name not in list_commands():
        return {"error": "E_UNKNOWN_SERVICE"}
    from agent_si.worker_tools.dispatcher import get_registry, guarded_dispatch
    target = registry if registry is not None else get_registry()
    target.load(name)
    return guarded_dispatch(
        list(argv), action_class, dict(auth), tool=name, registry=target
    )
