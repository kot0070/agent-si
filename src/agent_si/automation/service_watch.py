"""Automation service watch (Lane B STEP2): observe plus notify only.

:func:`tick` reads every stored service row scoped to one project through
``service_status.get`` (no probes, no writes to services) and appends one
``SERVICE_STATE`` journal row per service whose state changed since the last
notification. It never starts or stops external services.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from agent_si.automation import service_status


#: Dotted name of the frozen automation contract module. Product code
#: keeps no static import of it; the module object is resolved late at
#: call time, so raised errors, returned rows and cross-lane calls are
#: the same objects the contract tests use.
_IFACE_MODULE = "agent_si.automation.interface"


def _auto_iface():
    """Return the frozen automation contract module object."""
    try:
        return sys.modules[_IFACE_MODULE]
    except KeyError:
        raise RuntimeError(
            "frozen contract %r is not imported" % (_IFACE_MODULE,)
        )


def _utcnow() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )

__all__ = ("ServiceWatchSummary", "tick", "reset_baseline", "probe_disk")

#: Free-bytes floor for the observe-only disk probe: a volume holding fewer
#: free bytes than this reads as not-ok and journals once per call.
_DISK_LOW_BYTES = 100 * 1024 * 1024


@dataclass(frozen=True)
class ServiceWatchSummary:
    """One watch pass: what was checked and what changed."""

    project_id: str
    checked: int
    changed: Tuple[str, ...] = ()
    journal_entry_ids: Tuple[str, ...] = ()
    checked_at: str = ""


#: Last notified state per (project_id, service_id): notification baseline.
_LAST_NOTIFIED: Dict[Tuple[str, str], str] = {}


def reset_baseline(project_id: str = "") -> None:
    """Clear the notification baseline (whole lane, or one project)."""
    if project_id:
        for key in [key for key in _LAST_NOTIFIED if key[0] == project_id]:
            del _LAST_NOTIFIED[key]
    else:
        _LAST_NOTIFIED.clear()


def tick(project_id: str) -> ServiceWatchSummary:
    """Observe project services once; journal one row per state change."""
    changed: List[str] = []
    entry_ids: List[str] = []
    checked = 0
    for service_id in service_status.services_for_project(project_id):
        status = service_status.get(service_id)
        checked += 1
        key = (project_id, service_id)
        if _LAST_NOTIFIED.get(key) == status.state:
            continue
        entry = _auto_iface().journal_append_event(
            project_id,
            "automation",
            "SERVICE_STATE",
            "state %s" % status.state,
            (service_id,),
        )
        entry_ids.append(entry.entry_id)
        _LAST_NOTIFIED[key] = status.state
        changed.append(service_id)
    return ServiceWatchSummary(
        project_id=project_id,
        checked=checked,
        changed=tuple(changed),
        journal_entry_ids=tuple(entry_ids),
        checked_at=_utcnow(),
    )


def probe_disk(
    project_id: str, path: object = None, low_bytes: object = _DISK_LOW_BYTES
) -> Dict[str, Any]:
    """Observe-only disk probe: real free/total read, journal only when low.

    Reads the volume holding ``path`` (default: the current working
    directory, never a machine-pinned location) through
    :func:`shutil.disk_usage` and returns ``path``/``total``/``free``/``ok``.
    Journals one ``SERVICE_STATE`` row only when free space falls below
    ``low_bytes``; the ok path journals nothing and neither path writes to
    services. :func:`tick` and :func:`reset_baseline` semantics are unchanged.
    ``ValueError`` for a negative ``low_bytes`` floor.
    """
    if low_bytes is None:
        raise ValueError("low_bytes must not be None")
    floor = int(low_bytes)
    if floor < 0:
        raise ValueError("low_bytes must not be negative")
    target = os.getcwd() if path is None else str(path)
    usage = shutil.disk_usage(target)
    ok = usage.free >= floor
    if not ok:
        _auto_iface().journal_append_event(
            project_id,
            "automation",
            "SERVICE_STATE",
            "disk low: free %d of %d bytes at %s"
            % (usage.free, usage.total, target),
            (target,),
        )
    return {
        "path": target,
        "total": usage.total,
        "free": usage.free,
        "ok": bool(ok),
    }
