"""MH6A per-task turn triples (M-TRACE).

Each executed Manager turn of a task is stored here as one
plan/action/observation triple, in record order. The read route serves
these triples verbatim; the UI renders them verbatim. Task rows stay in
the existing K13 ports: this module holds only the per-turn records,
keyed by task_id, and no task or project row.

``clear_task_turns`` is a test helper only, never a product path.
"""

from __future__ import annotations

from typing import Any

_TURNS: dict[str, list[dict[str, str]]] = {}


def _checked(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("%s must be a non-empty string" % name)
    return value


def record_turn(
    task_id: str, plan: str, action: str, observation: str
) -> dict[str, str]:
    """Append one turn triple for a task; returns the stored triple."""
    triple = {
        "plan": _checked(plan, "plan"),
        "action": _checked(action, "action"),
        "observation": _checked(observation, "observation"),
    }
    key = _checked(task_id, "task_id")
    _TURNS.setdefault(key, []).append(triple)
    return dict(triple)


def list_turns(task_id: str) -> list[dict[str, str]]:
    """Return the stored triples for a task, oldest first."""
    key = _checked(task_id, "task_id")
    return [dict(triple) for triple in _TURNS.get(key, [])]


def clear_task_turns() -> None:
    """Drop every stored triple (test helper; never a product path)."""
    _TURNS.clear()


__all__ = [
    "clear_task_turns",
    "list_turns",
    "record_turn",
]
