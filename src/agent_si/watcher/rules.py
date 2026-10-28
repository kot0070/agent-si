"""Watcher rules: rule-card evaluation over stored facts.

Owns the REALIZATION_MAP entry ``watcher.evaluate_rule``
(:func:`evaluate`). Every rule card carries its own area, model and hang
window; each verdict is a pure function of the card record, the stored
journal facts and the clock. Each evaluation of a known card records
exactly one WATCH_DECISION journal row and returns the decision; unknown
cards raise.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, Tuple

from agent_si.watcher import journal as journal_store
from agent_si.watcher.journal import ERROR_CODES, WatcherError, append_event

__all__ = (
    "ERROR_CODES",
    "WatcherError",
    "WatchVerdict",
    "WatchDecision",
    "RuleCard",
    "MODELS",
    "HANG_DEFAULT_MINUTES",
    "RULES",
    "describe",
    "verdict_for",
    "evaluate",
    "reset_state",
)


class WatchVerdict(str, Enum):
    """Rule-card verdicts recorded on WATCH_DECISION rows."""

    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    ESCALATE = "ESCALATE"


@dataclass(frozen=True)
class WatchDecision:
    """Rule evaluation outcome plus its WATCH_DECISION row ref."""

    decision_id: str
    project_id: str
    rule_id: str
    verdict: WatchVerdict = WatchVerdict.ALLOW
    journal_entry_id: str = ""
    decided_at: str = ""


@dataclass(frozen=True)
class RuleCard:
    """Stored rule card: own area, model, hang window, base verdict."""

    rule_id: str
    area: str
    model: str = "local"
    hang_minutes: int = 20
    base_verdict: WatchVerdict = WatchVerdict.ALLOW


#: Models a rule card may run under: local model, API model, or OFF.
MODELS = (
    "local",
    "API",
    "OFF",
)

#: Default hang window in minutes carried by every rule card.
HANG_DEFAULT_MINUTES = 20

#: Stored rule cards: card id to its card record.
RULES: Dict[str, RuleCard] = {
    "rule-tamper": RuleCard(
        "rule-tamper", "tamper", "local",
        HANG_DEFAULT_MINUTES, WatchVerdict.ALLOW,
    ),
    "rule-guard": RuleCard(
        "rule-guard", "guard", "local",
        HANG_DEFAULT_MINUTES, WatchVerdict.BLOCK,
    ),
}

#: Decision sequence; restarted by reset_state for probe isolation.
_SEQ = 0


def _utcnow() -> str:
    """Current UTC time rendered like the frozen timestamps."""
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _parse_stamp(stamp: str) -> datetime:
    """Parse one frozen-style UTC stamp."""
    return datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))


def _heartbeat_stale(rows: Tuple, hang_minutes: int, moment: datetime) -> bool:
    """True when no fresh SERVICE_STATE heartbeat covers the moment."""
    beats = []
    for row in rows:
        if row.kind != "SERVICE_STATE":
            continue
        try:
            beats.append(_parse_stamp(row.timestamp))
        except ValueError:
            continue
    if not beats:
        return True
    return (moment - max(beats)) > timedelta(minutes=hang_minutes)


def verdict_for(card: RuleCard, rows: Tuple, now: str) -> WatchVerdict:
    """Pure verdict of one card record over stored facts at one reading."""
    kinds = {row.kind for row in rows}
    if card.area == "tamper" and "TAMPER_ATTEMPT" in kinds:
        return WatchVerdict.BLOCK
    if card.area == "guard" and "GUARD_BLOCK" in kinds:
        return WatchVerdict.BLOCK
    if _heartbeat_stale(rows, card.hang_minutes, _parse_stamp(now)):
        return WatchVerdict.ESCALATE
    return card.base_verdict


def describe(rule_id: str) -> RuleCard:
    """Return the stored card record; raise RULE_NOT_FOUND when unknown."""
    try:
        return RULES[str(rule_id)]
    except KeyError:
        raise WatcherError(
            "RULE_NOT_FOUND", "unknown rule %r" % (rule_id,)
        ) from None


def reset_state() -> None:
    """Restart decision ids; the card registry is definitions, not state."""
    global _SEQ
    _SEQ = 0


def evaluate(project_id: str, rule_id: str) -> WatchDecision:
    """Decide one stored rule card; record one WATCH_DECISION row."""
    card = describe(rule_id)
    verdict = verdict_for(
        card, journal_store.stored_rows(str(project_id)), _utcnow()
    )
    global _SEQ
    _SEQ += 1
    entry = append_event(
        str(project_id), "watcher", "WATCH_DECISION",
        str(rule_id), (str(rule_id),),
    )
    return WatchDecision(
        decision_id="dec-%04d" % _SEQ,
        project_id=str(project_id),
        rule_id=str(rule_id),
        verdict=verdict,
        journal_entry_id=entry.entry_id,
        decided_at=_utcnow(),
    )
