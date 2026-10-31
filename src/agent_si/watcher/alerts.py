"""Watcher alerts: read-only alert rows over stored facts.

Row R-324: serves one alert row per due rule card over the stored journal
facts. :func:`list_alerts` reads the stored rows plus the rule-card
registry and returns one alert row per due card carrying its pure verdict
(:func:`rules.verdict_for` performs no journal write). The watcher never
calls ``stop_all.request_stop`` and never terminates processes: this
module imports only journal plus rules, so serving alerts writes no rows,
stops nothing and leaves every attached agent running.
Standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Tuple

from agent_si.watcher import journal as journal_store
from agent_si.watcher import rules as rule_cards
from agent_si.watcher.journal import ERROR_CODES, WatcherError

__all__ = (
    "ERROR_CODES",
    "WatcherError",
    "Alert",
    "ALERT_CARDS",
    "list_alerts",
    "reset_state",
)


@dataclass(frozen=True)
class Alert:
    """One read-only alert row: the due card plus its pure verdict."""

    alert_id: str
    project_id: str
    rule_id: str
    verdict: str = "ALLOW"
    detail: str = ""


#: Due rule cards, derived from the card registry (never hard-coded ids).
ALERT_CARDS = tuple(rule_cards.RULES)


def _utcnow() -> str:
    """Current UTC time rendered like the frozen timestamps."""
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def reset_state() -> None:
    """Alerts keep no per-run state; present for probe isolation."""
    return None


def list_alerts(project_id: str) -> Tuple[Alert, ...]:
    """Serve one alert row per due card; write nothing, stop nothing."""
    key = str(project_id)
    rows = journal_store.stored_rows(key)
    moment = _utcnow()
    alerts = []
    for card_id in ALERT_CARDS:
        card = rule_cards.describe(card_id)
        verdict = rule_cards.verdict_for(card, rows, moment)
        alerts.append(
            Alert(
                alert_id="alert-%s" % card_id,
                project_id=key,
                rule_id=str(card_id),
                verdict=verdict.value,
                detail="%s %s over %d stored rows"
                % (card_id, verdict.value, len(rows)),
            )
        )
    return tuple(alerts)
