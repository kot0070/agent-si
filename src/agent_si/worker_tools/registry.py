"""Tool registry for the lane A worker tool belt.

Every route reaches its real implementation through a registered entry
point. There is no install / auto-install surface: unknown names raise
:exc:`ToolNotFoundError`.
"""

from __future__ import annotations

import collections.abc
import os
from typing import Callable, Protocol

from .types import ActionClass, Argv, AuthMapping, ToolResult

ToolFunc = Callable[[Argv, ActionClass, AuthMapping], ToolResult]
"""Real tool implementation behind an entry point (argv-only, G1)."""


class ToolNotFoundError(KeyError):
    """Raised when no entry point is registered under the requested name."""


class ToolEntryPoint(Protocol):
    """Entry point through which a route reaches its real implementation."""

    name: str
    action_class: ActionClass

    def load(self) -> ToolFunc:
        """Resolve and return the real tool implementation."""
        ...


def _checked_argv(argv: Argv) -> list[str]:
    """Return ``argv`` as a word list; reject shell strings and non-words."""
    if isinstance(argv, (str, bytes, bytearray)):
        raise TypeError("argv must be a list of words, never a shell string")
    try:
        items = list(argv)
    except TypeError:
        raise TypeError("argv must be a list of words") from None
    for item in items:
        if not isinstance(item, str):
            raise TypeError("argv must be a list of words (non-str element)")
    return items


def _checked_auth(auth: AuthMapping) -> None:
    """Enforce the belt auth rule; refuse closed on any mismatch."""
    if not isinstance(auth, collections.abc.Mapping):
        raise PermissionError("auth must be a mapping with a truthy subject")
    if not auth.get("subject"):
        raise PermissionError("auth must carry a truthy subject")
    if "token" in auth:
        raise PermissionError("this lane mints no bearer tokens")
    if "scopes" in auth:
        scopes = auth.get("scopes")
        try:
            present = "tools:exec" in scopes
        except TypeError:
            present = False
        if not present:
            raise PermissionError("scopes must include 'tools:exec'")


def _shaped_result(
    result: ToolResult,
    argv: list[str],
    action_class: ActionClass,
) -> ToolResult:
    """Keep tool values; fill only missing envelope keys and pids."""
    if not isinstance(result, dict):
        return {
            "ok": True,
            "argv": argv,
            "action_class": action_class,
            "pid": os.getpid(),
            "output": result,
        }
    result.setdefault("argv", argv)
    result.setdefault("action_class", action_class)
    result.setdefault("output", None)
    pid = result.get("pid")
    if not (isinstance(pid, int) and not isinstance(pid, bool) and pid > 0):
        result["pid"] = os.getpid()
    return result


class ToolRegistry:
    """Registry of tool entry points keyed by route name."""

    def __init__(self) -> None:
        """Create an empty registry."""
        self._entries: dict[str, ToolEntryPoint] = {}

    def register(self, entry_point: ToolEntryPoint) -> None:
        """Register one entry point under its ``name``."""
        self._entries[entry_point.name] = entry_point

    def names(self) -> list[str]:
        """Return every registered route name."""
        return list(self._entries.keys())

    def load(self, name: str) -> ToolFunc:
        """Return the real implementation behind ``name``.

        Raises :exc:`ToolNotFoundError` when ``name`` is not registered.
        """
        try:
            entry_point = self._entries[name]
        except KeyError:
            raise ToolNotFoundError(
                "unknown tool: %r (auto-install is disabled)" % (name,)
            ) from None
        return entry_point.load()

    def dispatch(
        self,
        name: str,
        argv: Argv,
        action_class: ActionClass,
        auth: AuthMapping,
    ) -> ToolResult:
        """Load the entry point for ``name`` and call it with ``argv``."""
        argv_list = _checked_argv(argv)
        _checked_auth(auth)
        func = self.load(name)
        return _shaped_result(func(argv_list, action_class, auth), argv_list, action_class)
