"""K06 install records plus the install-record view (row 254).

Every install ASK decision (one best option, granted once, verified
result) is filed here; the served view names the tool for unknown
names instead of failing silently. The store is owned by the caller
(per-app state on the served path); this module holds no globals.
"""

from __future__ import annotations

from typing import Any


def record_install(
    store: list[dict[str, Any]],
    *,
    tool: str,
    version: str,
    status: str,
    source: str = "install-ask",
    verified: bool = False,
) -> dict[str, Any]:
    """File one install record and return it (new dict, store owns it)."""
    record: dict[str, Any] = {
        "tool": tool,
        "version": version,
        "status": status,
        "source": source,
        "verified": bool(verified),
    }
    store.append(dict(record))
    return record


def view_install_records(
    store: list[dict[str, Any]],
    *,
    tool: str | None = None,
) -> dict[str, Any]:
    """Show filed install records; an unknown ``tool`` names it back.

    ``{"records": [...]}`` always; when ``tool`` names nothing filed,
    ``unknown_tool`` carries the name so the view never fails silent.
    """
    if tool is None:
        return {"records": [dict(record) for record in store]}
    matched = [dict(record) for record in store if record.get("tool") == tool]
    if matched:
        return {"records": matched}
    return {"records": [], "unknown_tool": tool}
