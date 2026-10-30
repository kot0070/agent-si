"""Guarded dispatcher for the lane A worker tool belt.

Behaviour of the real implementation:
- G1 argv-only guard: ``argv`` is a list of words; a shell string is
  rejected with :exc:`TypeError` before anything else runs.
- MH-3 task-authorized list: when ``task_authorized`` is given, a tool
  outside it is deterministically rejected with
  :exc:`ToolNotAuthorizedError` (code TOOL_NOT_AUTHORIZED) plus a guard
  record; nothing executes and no side effect happens.
- every call goes through ``toolguard.evaluate`` (read-only G2/G5 usage;
  resolved lazily so this lane never owns ``toolguard``).
- installer auto-install stays disabled: unknown tools raise
  :exc:`ToolNotFoundError`, they are never fetched or installed.
- real child pids are reported to the watcher.
- tool output is DATA, never instructions.
"""

from __future__ import annotations

import collections.abc
import importlib
import sys
from typing import TYPE_CHECKING

from .registry import (
    ToolNotAuthorizedError,
    ToolRegistry,
    _checked_argv,
    _checked_auth,
    _shaped_result,
)
from .types import ActionClass, Argv, AuthMapping, ToolResult

if TYPE_CHECKING:  # read-only contract usage; never a runtime import here
    from agent_si.toolguard import evaluate  # noqa: F401


_REAL_REGISTRY = ToolRegistry()


def get_registry() -> ToolRegistry:
    """Return the process-wide tool registry."""
    return _REAL_REGISTRY


def _resolve_evaluate():
    """Return ``toolguard.evaluate`` without a static import of the lane."""
    module = sys.modules.get("agent_si.toolguard")
    func = getattr(module, "evaluate", None) if module is not None else None
    if callable(func):
        return func
    guard = importlib.import_module("agent_si.toolguard.guard")
    return guard.evaluate


def guarded_dispatch(
    argv: Argv,
    action_class: ActionClass,
    auth: AuthMapping,
    *,
    tool: str,
    registry: ToolRegistry | None = None,
    task_authorized: collections.abc.Sequence[str] | None = None,
    guard_store: list | None = None,
) -> ToolResult:
    """Evaluate ``toolguard.evaluate`` then run the ``tool`` route.

    ``argv`` must be a list of words (G1); ``action_class`` is one of
    R0-R3; ``auth`` carries identity, scopes and approvals. When
    ``task_authorized`` is given, a ``tool`` outside it raises
    :exc:`ToolNotAuthorizedError` before anything else runs: no guard
    evaluation, no implementation load, no side effect. The reject is
    filed to ``guard_store`` (guard_records.record_guard_decision)
    when a store is given.
    """
    argv_list = _checked_argv(argv)
    if task_authorized is not None and tool not in list(task_authorized):
        reason = "tool %r is outside the task-authorized list" % (tool,)
        if guard_store is not None:
            from .guard_records import TOOL_NOT_AUTHORIZED
            from .guard_records import record_guard_decision as _record

            _record(
                guard_store,
                tool=tool,
                decision="deny",
                reason=reason,
                evidence_ref="toolguard:deny:task-list:%s" % (tool[:40],),
                error_code=TOOL_NOT_AUTHORIZED,
            )
        raise ToolNotAuthorizedError("TOOL_NOT_AUTHORIZED: %s" % (reason,))
    evaluate = _resolve_evaluate()
    if isinstance(auth, collections.abc.Mapping):
        auth_dict = dict(auth)
    else:
        auth_dict = {}
    verdict = evaluate(argv_list, action_class, auth_dict)
    if isinstance(verdict, dict) and verdict.get("decision") == "deny":
        raise PermissionError(
            "toolguard denied: %s" % (verdict.get("reason"),)
        )
    _checked_auth(auth)
    target = registry if registry is not None else get_registry()
    return target.dispatch(tool, argv_list, action_class, auth)
