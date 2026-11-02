"""K02R4 agents-live rows: the live store behind GET /api/v1/agents/live.

Owned by M-MANAGER. The Manager run records one row per yielded event
here, so SSE consumers and the live route see the same run. live_rows
returns the {"agents": [...]} payload: live run rows overlaid on the
served parts register (same row keys agent/scope/deliverable/status),
a read needing no token; never a token in the URL. agents_live_payload
is an alias of the same payload.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping
from typing import Any

_LIVE_ROWS: dict[str, dict[str, Any]] = {}

# FXPARALLEL BEGIN run-lock: concurrent part rows never overwrite.
#: Guards the live-store upsert only; keys and log names unchanged.
_LIVE_LOCK = threading.Lock()
# FXPARALLEL END run-lock.

#: Append-only FXPANEL live fields (the frozen four stay first, untouched).
LIVE_EXTRA_FIELDS = ("role", "model", "step", "file", "cost",
                     "tokens", "context", "errors", "waits")

#: Cost marker when no price was evidenced for the run. The BudgetGate
#: owns pricing; the live sink never invents a cost.
COST_UNAVAILABLE = "UNAVAILABLE"


def _live_tokens(value: Any) -> dict[str, Any]:
    """Normalize a tokens value to {"input", "output"} (Nones unevidenced)."""
    if isinstance(value, Mapping):
        return {"input": value.get("input"), "output": value.get("output")}
    return {"input": None, "output": None}


def _live_strings(value: Any) -> list[str]:
    """Normalize an errors/waits value to a list of strings."""
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    if value is None or value == "":
        return []
    return [str(value)]


def _live_step(value: Any) -> int:
    """Normalize a step value to an int (0 when unevidenced)."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


def live_defaults() -> dict[str, Any]:
    """Default append-only fields for rows with no run evidence."""
    return {
        "role": "",
        "model": "",
        "step": 0,
        "file": "",
        "cost": COST_UNAVAILABLE,
        "tokens": {"input": None, "output": None},
        "context": "",
        "errors": [],
        "waits": [],
    }


def record_live_row(key: str, row: Mapping[str, Any]) -> dict[str, Any]:
    """Upsert one live row by key; returns a stored copy."""
    stored = {
        "agent": str(row.get("agent", "")),
        "scope": str(row.get("scope", "")),
        "deliverable": str(row.get("deliverable", "")),
        "status": str(row.get("status", "")),
        "role": str(row.get("role", "")),
        "model": str(row.get("model", "")),
        "step": _live_step(row.get("step", 0)),
        "file": str(row.get("file", "")),
        "cost": str(row.get("cost", COST_UNAVAILABLE)),
        "tokens": _live_tokens(row.get("tokens")),
        "context": str(row.get("context", "")),
        "errors": _live_strings(row.get("errors")),
        "waits": _live_strings(row.get("waits")),
    }
    # FXPARALLEL BEGIN run-lock: upsert as one unit.
    with _LIVE_LOCK:
        _LIVE_ROWS[str(key)] = stored
    # FXPARALLEL END run-lock.
    return dict(stored)


def clear_live_rows() -> None:
    """Drop all live rows (test/isolation helper, never a product path)."""
    _LIVE_ROWS.clear()


def live_rows() -> dict[str, Any]:
    """Return the {"agents": [...]} payload from the live store."""
    from agent_si.backend.orchestration import parts as _parts

    merged: dict[str, dict[str, Any]] = dict(_LIVE_ROWS)
    for row in _parts.list_parts(None):
        merged.setdefault(row.scope, {
            "agent": row.agent,
            "scope": row.scope,
            "deliverable": row.deliverable,
            "status": row.status,
            **live_defaults(),
        })
    rows = [dict(item) for item in merged.values()]
    rows.sort(key=lambda item: (item["agent"], item["scope"]))
    return {"agents": rows}


agents_live_payload = live_rows
"""Alias of the same live payload (same callable, same rows)."""


__all__ = [
    "COST_UNAVAILABLE",
    "LIVE_EXTRA_FIELDS",
    "agents_live_payload",
    "clear_live_rows",
    "live_defaults",
    "live_rows",
    "record_live_row",
]
