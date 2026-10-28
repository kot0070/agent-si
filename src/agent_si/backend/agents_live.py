"""K02R4 agents-live rows: the live store behind GET /api/v1/agents/live.

Owned by M-MANAGER. The Manager run records one row per yielded event
here, so SSE consumers and the live route see the same run. live_rows
returns the {"agents": [...]} payload: live run rows overlaid on the
served parts register (same row keys agent/scope/deliverable/status),
a read needing no token; never a token in the URL. agents_live_payload
is an alias of the same payload.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_LIVE_ROWS: dict[str, dict[str, Any]] = {}


def record_live_row(key: str, row: Mapping[str, Any]) -> dict[str, Any]:
    """Upsert one live row by key; returns a stored copy."""
    stored = {
        "agent": str(row.get("agent", "")),
        "scope": str(row.get("scope", "")),
        "deliverable": str(row.get("deliverable", "")),
        "status": str(row.get("status", "")),
    }
    _LIVE_ROWS[str(key)] = stored
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
        })
    rows = [dict(item) for item in merged.values()]
    rows.sort(key=lambda item: (item["agent"], item["scope"]))
    return {"agents": rows}


agents_live_payload = live_rows
"""Alias of the same live payload (same callable, same rows)."""


__all__ = [
    "agents_live_payload",
    "clear_live_rows",
    "live_rows",
    "record_live_row",
]
