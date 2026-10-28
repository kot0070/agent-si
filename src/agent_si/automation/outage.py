"""Automation outage signal (Lane B STEP2): one stop-and-report.

Owns REALIZATION_MAP entry ``outage.signal`` (:func:`signal_outage`). A
single call stops project work through the stop-all lane and records one
``OUTAGE_SIGNAL`` journal row, returning the report that links both. No
other writes happen here.

Cross-lane calls resolve late off the frozen automation contract
module at call time so tests can install doubles.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING

from agent_si.automation import service_status

if TYPE_CHECKING:
    from agent_si.automation import interface as auto_iface


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

__all__ = ("signal_outage", "link_observation_to_outage",)


_seq = 0


def _utcnow() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def signal_outage(
    project_id: str,
    service_id: str,
    severity: object,
    summary: str,
    session_token: Optional[str] = None,
) -> auto_iface.OutageReport:
    """REALIZATION_MAP ``outage.signal``: stop-all plus one journal row.

    ``session_token`` is accepted for entry-point parity; refusal of missing
    or invalid tokens is enforced at the route seam, not here.
    """
    if service_id not in service_status.service_ids():
        raise _auto_iface().AutomationError(
            "SERVICE_NOT_FOUND", "unknown service %r" % (service_id,)
        )
    severity_name = getattr(severity, "value", severity)
    if not isinstance(severity_name, str):
        severity_name = str(severity_name)
    global _seq
    _seq += 1
    report_id = "out-%04d" % _seq
    receipt = _auto_iface().stop_all_request_stop(
        project_id, "outage %s: %s" % (service_id, summary)
    )
    entry = _auto_iface().journal_append_event(
        project_id,
        "automation",
        "OUTAGE_SIGNAL",
        str(summary),
        (service_id, report_id),
    )
    return _auto_iface().OutageReport(
        report_id=report_id,
        project_id=project_id,
        service_id=service_id,
        severity=severity_name,
        journal_entry_id=entry.entry_id,
        stopped=bool(receipt.stopped),
        reported_at=_utcnow(),
    )


_link_seq = 0


def link_observation_to_outage(
    project_id: str,
    service_id: str,
    severity: object,
    summary: str,
    session_token: Optional[str] = None,
) -> auto_iface.OutageReport:
    """Additive outage linkage: tie a DOWN/DEGRADED observation to a report.

    Observe plus notify only: reads the last observed state of a declared
    service and journals one ``OUTAGE_SIGNAL`` row carrying the linked
    report id, returning the report with ``stopped`` False. This path never
    calls stop-all (no auto-stop) and never changes :func:`signal_outage`,
    which stays the only stop-and-report path. A service last observed UP
    refuses with ``SERVICE_CHECK_REFUSED`` (no outage to link); unknown
    services raise ``SERVICE_NOT_FOUND``.

    ``session_token`` is accepted for entry-point parity; refusal of missing
    or invalid tokens is enforced at the route seam, not here.
    """
    if service_id not in service_status.service_ids():
        raise _auto_iface().AutomationError(
            "SERVICE_NOT_FOUND", "unknown service %r" % (service_id,)
        )
    severity_name = getattr(severity, "value", severity)
    if not isinstance(severity_name, str):
        severity_name = str(severity_name)
    state = str(service_status.get(service_id).state)
    if state not in ("DOWN", "DEGRADED"):
        raise _auto_iface().AutomationError(
            "SERVICE_CHECK_REFUSED",
            "no outage to link: service %r is %s" % (service_id, state),
        )
    global _link_seq
    _link_seq += 1
    report_id = "lnk-%04d" % _link_seq
    entry = _auto_iface().journal_append_event(
        project_id,
        "automation",
        "OUTAGE_SIGNAL",
        "link %s state %s: %s" % (service_id, state, summary),
        (service_id, report_id),
    )
    return _auto_iface().OutageReport(
        report_id=report_id,
        project_id=project_id,
        service_id=service_id,
        severity=severity_name,
        journal_entry_id=entry.entry_id,
        stopped=False,
        reported_at=_utcnow(),
    )
