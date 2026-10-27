"""K03 catalog lane STEP2: runner library.

Four built-in test bases ship with the catalog; project runners attach on
top. Every runner executes under the published runner contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

#: The four built-in test bases shipped with the catalog.
BUILTIN_BASES = (
    "PYTEST_BASE",
    "CONTRACT_BASE",
    "AI_JUDGE_BASE",
    "HUMAN_SCRIPT_BASE",
)

#: Frozen error-code names for this module (each pinned in its own test).
ERROR_CODES_LIBRARY = (
    "UNKNOWN_RUNNER",
)


class LibraryError(Exception):
    """Library failure carrying the frozen ``.code`` name."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class BuiltinRunner:
    runner_id: str
    base: str
    kind: str


@dataclass(frozen=True)
class AttachedRunner:
    runner_id: str
    project_id: str
    kind: str
    approval_ref: str


#: The four built-in runners, one per base; every runner id below is
#: publishable through the runner contract (the production caller path).
_BUILTIN_RUNNERS = (
    BuiltinRunner(
        runner_id="runner-pytest", base="PYTEST_BASE", kind="CODE"
    ),
    BuiltinRunner(
        runner_id="runner-contract", base="CONTRACT_BASE", kind="CODE"
    ),
    BuiltinRunner(
        runner_id="runner-ai-judge", base="AI_JUDGE_BASE", kind="AI"
    ),
    BuiltinRunner(
        runner_id="runner-human-script",
        base="HUMAN_SCRIPT_BASE",
        kind="HUMAN",
    ),
)


def list_builtin_runners() -> List[BuiltinRunner]:
    """The four built-in runners, one per built-in test base."""
    return list(_BUILTIN_RUNNERS)


def get_runner(runner_id: str) -> BuiltinRunner:
    """Return one built-in runner; else raises UNKNOWN_RUNNER."""
    for runner in _BUILTIN_RUNNERS:
        if runner.runner_id == runner_id:
            return runner
    raise LibraryError("UNKNOWN_RUNNER", "unknown runner %r" % runner_id)


def attached_runners(project_id: str) -> List[AttachedRunner]:
    """Project-attached runners on top of the built-in bases."""
    return []


#: Entry points: logical name -> symbol in this module.
ENTRY_POINTS = {
    "list_builtin_runners": "list_builtin_runners",
    "get_runner": "get_runner",
    "attached_runners": "attached_runners",
}
