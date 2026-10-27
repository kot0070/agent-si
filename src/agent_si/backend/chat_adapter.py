"""R-315 plain-chat adapter: plain chat writes via offered tools.

Plain chat turns reach file writes only through declared services
routed over the real tool belt (guard plus registry plus
dispatcher). This module adds no belt call site: execution always
goes through ``services.commands.run_declared_service_via_belt``
(imported lazily inside the entry point, the same pattern as
``services/commands.py``), so every call passes the real guard
and guard denials raise fail-closed.

Validation mirrors the services codes before the belt runs
(E_BAD_ARGV, E_BAD_ACTION_CLASS, E_BAD_AUTH); unknown tools come
back from the belt as E_UNKNOWN_SERVICE. Auth is forwarded as a
verbatim copy: this adapter never adds tokens, scopes or
approvals. It never touches the filesystem: when the belt offers
no write tool, the caller gets an error dict, never a fallback
write.
"""

from __future__ import annotations

from typing import Any

ACTION_CLASSES: tuple[str, ...] = ("R0", "R1", "R2", "R3")


def run_chat_tool(
    argv: list[str],
    action_class: str,
    auth: dict[str, Any],
    *,
    tool: str | None = None,
    registry: Any | None = None,
) -> dict[str, Any]:
    """Route one plain-chat tool call through the real tool belt.

    ``argv`` is a list of non-empty words, never a shell string;
    ``action_class`` is one of R0-R3; ``auth`` is a non-empty
    mapping. ``tool`` selects the offered route (default: the
    first argv word); ``registry`` injects the belt registry for
    tests (default: the process registry). Validation failures
    return {"error": <code>} without touching the belt. Valid
    calls run through ``run_declared_service_via_belt`` with a
    verbatim copy of ``auth``; guard denials raise PermissionError
    and are never converted into success values.
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
    if tool is not None and (not isinstance(tool, str) or tool == ""):
        return {"error": "E_BAD_ARGV"}
    name = tool if tool is not None else list(argv)[0]
    from agent_si.services.commands import run_declared_service_via_belt

    return run_declared_service_via_belt(
        list(argv), action_class, dict(auth), tool=name, registry=registry
    )
