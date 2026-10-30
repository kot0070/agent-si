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


class ToolNotAuthorizedError(PermissionError):
    """Raised when the tool is outside the task-authorized list (MH-3)."""

    code = "TOOL_NOT_AUTHORIZED"


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


_SECRET_KEY_HINTS: tuple[str, ...] = (
    "secret",
    "token",
    "password",
    "passwd",
    "api_key",
    "apikey",
    "api-key",
    "credential",
    "private_key",
    "privatekey",
    "private-key",
)

_SECRET_REF_PREFIX = "secretref:"


def _holds_nested_raw(value: object) -> bool:
    """True when a container hides a raw string that is no opaque handle."""
    if isinstance(value, dict) and set(value.keys()) == {"secretRef"} and isinstance(
        value.get("secretRef"), str
    ):
        return False
    if isinstance(value, str):
        return bool(value) and not value.startswith(_SECRET_REF_PREFIX)
    if isinstance(value, dict):
        return any(_holds_nested_raw(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_holds_nested_raw(item) for item in value)
    return False


def _carries_raw_secret(value: object) -> bool:
    """True when a secret-typed slot holds raw material, not a handle.

    The raw string may sit directly under the secret-typed key or be
    smuggled inside a container under that key; both refuse.
    """
    if isinstance(value, dict):
        if set(value.keys()) == {"secretRef"} and isinstance(
            value.get("secretRef"), str
        ):
            return False
        for key, item in value.items():
            if (
                isinstance(key, str)
                and any(hint in key.lower() for hint in _SECRET_KEY_HINTS)
                and isinstance(item, str)
                and item
                and not item.startswith(_SECRET_REF_PREFIX)
            ):
                return True
            if (
                isinstance(key, str)
                and any(hint in key.lower() for hint in _SECRET_KEY_HINTS)
                and isinstance(item, (dict, list, tuple))
                and _holds_nested_raw(item)
            ):
                return True
            if isinstance(item, (dict, list, tuple)) and _carries_raw_secret(
                item
            ):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(_carries_raw_secret(item) for item in value)
    return False


def _checked_auth(auth: AuthMapping) -> None:
    """Enforce the belt auth rule; refuse closed on any mismatch."""
    if not isinstance(auth, collections.abc.Mapping):
        raise PermissionError("auth must be a mapping with a truthy subject")
    if not auth.get("subject"):
        raise PermissionError("auth must carry a truthy subject")
    if "token" in auth:
        raise PermissionError("this lane mints no bearer tokens")
    if _carries_raw_secret(dict(auth)):
        raise PermissionError(
            "auth must not carry raw secret material "
            "(pass a SecretRef handle, never raw)"
        )
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
