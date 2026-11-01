"""Backend stop-all: user-only or expiring-grant stop over owned processes.

Row R-323 plus row R-326 plus row Q3, lane m_entry, author CODER-2 Sable.
Owns REALIZATION_MAP entry ``stop_all.request_stop`` (:func:`request_stop`).
One call stops every child process the run attached through
:func:`attach_child` (the run's own commands stay attached to the run, so
Emergency Stop leaves 0 of its processes behind) and records one
``STOP_ALL`` journal row; processes never attached are never touched.
USER requests are always accepted; a Director request needs a live grant
from :func:`issue_grant` (missing grants raise ``STOP_REASON_MISSING``;
expired or unknown grants, and any other actor, are refused without
stopping anything). Standard library only.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from typing import Dict, List, Tuple

from agent_si.watcher import journal as journal_store
from agent_si.watcher.journal import WatcherError

__all__ = (
    "StopReceipt",
    "AttachedChild",
    "attach_child",
    "attached",
    "issue_grant",
    "request_stop",
    "request_stop_all",
    "reset_state",
)


@dataclass(frozen=True)
class StopReceipt:
    """Stop-all receipt: accepted plus the reason plus the stop facts."""

    project_id: str
    accepted: bool = False
    reason: str = ""
    stopped_count: int = 0
    journal_entry_id: str = ""
    stopped_at: str = ""


@dataclass
class AttachedChild:
    """One run-owned child process attached for a later stop."""

    run_id: str
    proc: "subprocess.Popen"


#: Expiring Director grants: grant ref to its expiry epoch seconds.
_GRANTS: Dict[str, float] = {}

#: Run-owned child processes per project: project id to attached rows.
_ATTACHED: Dict[str, List[AttachedChild]] = {}


def reset_state() -> None:
    """Drop every grant and every attached child (probe isolation)."""
    _GRANTS.clear()
    _ATTACHED.clear()


def issue_grant(grant_ref: str, ttl_s: float = 600.0) -> str:
    """Store an expiring Director grant; return its ref."""
    ref = str(grant_ref)
    if not ref:
        raise ValueError("grant ref must be a non-empty string")
    _GRANTS[ref] = time.time() + float(ttl_s)
    return ref


def attach_child(project_id: str, run_id: str,
                 proc: "subprocess.Popen") -> int:
    """Attach a run-owned child process; return its attach index."""
    key = str(project_id)
    row = AttachedChild(run_id=str(run_id), proc=proc)
    rows = _ATTACHED.setdefault(key, [])
    rows.append(row)
    return len(rows) - 1


def attached(project_id: str) -> Tuple[str, ...]:
    """Serve the run ids still attached for one project."""
    return tuple(row.run_id for row in _ATTACHED.get(str(project_id), []))


def _utcnow() -> str:
    """Current UTC time rendered like the frozen timestamps."""
    from datetime import datetime, timezone

    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _terminate(proc: "subprocess.Popen", timeout: float = 5.0) -> bool:
    """Stop one attached child; True when it is no longer running."""
    try:
        if proc.poll() is not None:
            return True
        proc.terminate()
    except Exception:
        return proc.poll() is not None
    try:
        proc.wait(timeout=timeout)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
        try:
            proc.wait(timeout=timeout)
        except Exception:
            pass
    return proc.poll() is not None


def _refuse(project_id: str, reason: str) -> StopReceipt:
    """Journal a refused stop-all, then serve the refused receipt."""
    entry = journal_store.append_event(
        project_id, "backend", "STOP_ALL",
        "stop-all refused: %s" % reason, (project_id,),
    )
    return StopReceipt(
        project_id=project_id,
        accepted=False,
        reason=reason,
        stopped_count=0,
        journal_entry_id=entry.entry_id,
        stopped_at=entry.timestamp,
    )


def request_stop(actor: str, project_id: str, grant_ref: str = "",
                 session_token: str = "") -> StopReceipt:
    """Stop every attached child of one project; journal the outcome.

    ``session_token`` is accepted for entry-point parity; refusal of
    missing or invalid tokens is enforced at the route seam, not here.
    """
    key = str(project_id)
    who = str(actor)
    if who == "user":
        pass
    elif who == "director":
        ref = str(grant_ref)
        if not ref:
            journal_store.append_event(
                key, "backend", "STOP_ALL",
                "stop-all refused: director grant missing", (key,),
            )
            raise WatcherError(
                "STOP_REASON_MISSING",
                "director stop needs a live grant ref",
            )
        expiry = _GRANTS.get(ref)
        if expiry is None:
            return _refuse(key, "unknown grant %r" % ref)
        if expiry <= time.time():
            return _refuse(key, "grant expired %r" % ref)
    else:
        return _refuse(key, "actor refused: %s" % who)
    owned = _ATTACHED.pop(key, [])
    stopped = 0
    for row in owned:
        if _terminate(row.proc):
            stopped += 1
    entry = journal_store.append_event(
        key, "backend", "STOP_ALL",
        "stop-all by %s: stopped %d of %d" % (who, stopped, len(owned)),
        (key,),
    )
    return StopReceipt(
        project_id=key,
        accepted=True,
        reason="stop supervised by %s" % who,
        stopped_count=stopped,
        journal_entry_id=entry.entry_id,
        stopped_at=entry.timestamp,
    )


def request_stop_all(actor: str, grant_ref: str = "",
                     session_token: str = "") -> StopReceipt:
    """Stop every attached child of every project; journal the outcome.

    The no-project branch of ``POST /api/v1/stop-all``: the same actor
    rules as :func:`request_stop` (a user is always accepted, a
    Director needs a live grant, anyone else is refused without
    stopping anything), then every attached child of every project is
    stopped and one ``STOP_ALL`` row journals the totals.
    ``session_token`` is accepted for entry-point parity; refusal of
    missing or invalid tokens is enforced at the route seam, not here.
    """
    who = str(actor)
    if who == "user":
        pass
    elif who == "director":
        ref = str(grant_ref)
        if not ref:
            journal_store.append_event(
                "", "backend", "STOP_ALL",
                "stop-all refused: director grant missing", ("",),
            )
            raise WatcherError(
                "STOP_REASON_MISSING",
                "director stop needs a live grant ref",
            )
        expiry = _GRANTS.get(ref)
        if expiry is None:
            return _refuse("", "unknown grant %r" % ref)
        if expiry <= time.time():
            return _refuse("", "grant expired %r" % ref)
    else:
        return _refuse("", "actor refused: %s" % who)
    keys = sorted(_ATTACHED.keys())
    owned_total = 0
    stopped = 0
    for key in keys:
        rows = _ATTACHED.pop(key, [])
        owned_total += len(rows)
        for row in rows:
            if _terminate(row.proc):
                stopped += 1
    entry = journal_store.append_event(
        "", "backend", "STOP_ALL",
        "stop-all by %s: stopped %d of %d across %d projects"
        % (who, stopped, owned_total, len(keys)),
        ("",),
    )
    return StopReceipt(
        project_id="",
        accepted=True,
        reason="stop supervised by %s" % who,
        stopped_count=stopped,
        journal_entry_id=entry.entry_id,
        stopped_at=entry.timestamp,
    )
