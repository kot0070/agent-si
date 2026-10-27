"""Watcher rules: rule-card evaluation over stored facts (lane A STEP2).

Owns the REALIZATION_MAP entry ``watcher.evaluate_rule``
(:func:`evaluate`). Each evaluation of a known card records exactly one
WATCH_DECISION journal row and returns the decision; unknown cards raise.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from agent_si.watcher.journal import ERROR_CODES, WatcherError, append_event

__all__ = (
    "ERROR_CODES",
    "WatcherError",
    "WatchVerdict",
    "WatchDecision",
    "RULES",
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


#: Stored rule cards: card id to its decided verdict.
RULES = {
    "rule-tamper": WatchVerdict.ALLOW,
    "rule-guard": WatchVerdict.BLOCK,
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


def reset_state() -> None:
    """Restart decision ids."""
    global _SEQ
    _SEQ = 0


def evaluate(project_id: str, rule_id: str) -> WatchDecision:
    """Decide one stored rule card; record one WATCH_DECISION row."""
    verdict = RULES.get(rule_id)
    if verdict is None:
        raise WatcherError("RULE_NOT_FOUND", "unknown rule %r" % (rule_id,))
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
