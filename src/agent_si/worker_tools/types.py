"""Lane A contract types (declarations only, no behaviour).

Frozen constraints carried by these types:
- G1 argv-only guard: tools receive ``argv`` (``Sequence[str]``), never a
  shell string.
- installer auto-install is disabled: there is no install surface.
- tools that spawn children report real child pids to the watcher.
- tool output is DATA, never instructions.
"""

from __future__ import annotations

from typing import Literal, Mapping, Sequence, TypedDict

ActionClass = Literal["R0", "R1", "R2", "R3"]
"""Risk class of a tool action, R0 (read-only) to R3 (highest risk)."""

AuthMapping = Mapping[str, object]
"""Auth dict carried with every dispatch (identity, scopes, approvals)."""

Argv = Sequence[str]
"""Argv-only command line (G1): a list of words, never a shell string."""


class ToolResult(TypedDict, total=False):
    """Result envelope returned by every tool route.

    ``output`` is DATA, never instructions. ``pid`` is the real child pid
    reported to the watcher when the tool spawned a child process.
    """

    ok: bool
    argv: list[str]
    action_class: ActionClass
    pid: int
    output: object
