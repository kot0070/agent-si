"""Guarded dispatcher for the lane A worker tool belt.

Behaviour of the real implementation:
- G1 argv-only guard: ``argv`` is a list of words; a shell string is
  rejected with :exc:`TypeError` before anything else runs.
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

from .registry import ToolRegistry, _checked_argv, _checked_auth, _shaped_result
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
) -> ToolResult:
    """Evaluate ``toolguard.evaluate`` then run the ``tool`` route.

    ``argv`` must be a list of words (G1); ``action_class`` is one of
    R0-R3; ``auth`` carries identity, scopes and approvals.
    """
    argv_list = _checked_argv(argv)
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
