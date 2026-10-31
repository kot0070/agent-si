"""Watcher outage: one clear stop-and-report through the real lane.

Row 181: :func:`signal_outage` stops project work once through the real
stop-all lane (``agent_si.backend.stop_all.request_stop`` is called as a
read-only caller, never reimplemented here) and journals exactly one
``OUTAGE_SIGNAL`` row named ``STOP_AND_REPORT``. A repeated signal for the
same (service, summary) outage replays the stored report without stopping
or journaling again: an outage means one stop-and-report, never a double.
Standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from agent_si.watcher import journal as journal_store
from agent_si.watcher.journal import ERROR_CODES, WatcherError

__all__ = (
    "ERROR_CODES",
    "WatcherError",
    "OutageReport",
    "signal_outage",
    "reset_state",
)


@dataclass(frozen=True)
class OutageReport:
    """One stop-and-report outcome plus its OUTAGE_SIGNAL row ref."""

    report_id: str = ""
    project_id: str = ""
    service_id: str = ""
    summary: str = ""
    stopped: bool = False
    journal_entry_id: str = ""
    reported_at: str = ""


#: Report-id sequence; restarted by reset_state for probe isolation.
_SEQ = 0


def _utcnow() -> str:
    """Current UTC time rendered like the frozen timestamps."""
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def reset_state() -> None:
    """Restart report ids; stored rows stay the dedupe facts."""
    global _SEQ
    _SEQ = 0


def _prior_report(project_id: str, service_id: str, summary: str):
    """Return the stored STOP_AND_REPORT row for a repeat signal, or None."""
    for row in journal_store.stored_rows(str(project_id), "OUTAGE_SIGNAL"):
        if (
            row.refs == (str(service_id), str(summary))
            and row.summary.startswith("STOP_AND_REPORT")
        ):
            return row
    return None


def signal_outage(project_id: str, service_id: str,
                  summary: str) -> OutageReport:
    """Stop once through the real stop-all lane; journal one report row.

    The first signal for one (service, summary) outage calls the real
    ``agent_si.backend.stop_all.request_stop`` for a user stop and appends
    one ``OUTAGE_SIGNAL`` row named ``STOP_AND_REPORT``. A repeat signal
    replays the stored report (``stopped`` False, the original row ref)
    without stopping or journaling again.
    """
    key = str(project_id)
    service = str(service_id)
    text = str(summary)
    prior = _prior_report(key, service, text)
    global _SEQ
    _SEQ += 1
    if prior is not None:
        return OutageReport(
            report_id="out-%04d" % _SEQ,
            project_id=key,
            service_id=service,
            summary=text,
            stopped=False,
            journal_entry_id=prior.entry_id,
            reported_at=_utcnow(),
        )
    from agent_si.backend import stop_all as stop_home
    receipt = stop_home.request_stop("user", key)
    entry = journal_store.append_event(
        key, "watcher", "OUTAGE_SIGNAL",
        "STOP_AND_REPORT %s: %s" % (service, text),
        (service, text),
    )
    return OutageReport(
        report_id="out-%04d" % _SEQ,
        project_id=key,
        service_id=service,
        summary=text,
        stopped=bool(receipt.accepted),
        journal_entry_id=entry.entry_id,
        reported_at=entry.timestamp,
    )
