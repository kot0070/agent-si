"""Watcher engine: due rule cards plus committed choices (lane A STEP2).

Owns REALIZATION_MAP entries ``watcher.engine.tick`` (:func:`tick`) and
``watcher.engine.decide`` (:func:`decide`). A tick evaluates every due
card now, so each firing records one WATCH_DECISION journal row; a decide
commits the chosen script plus params for a fired card and returns the
fresh evaluation of that card.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Tuple

from agent_si.watcher import rules as rule_cards
from agent_si.watcher.journal import ERROR_CODES, WatcherError

__all__ = (
    "ERROR_CODES",
    "WatcherError",
    "EngineTick",
    "DUE_CARDS",
    "tick",
    "decide",
    "last_choice",
    "reset_state",
)


@dataclass(frozen=True)
class EngineTick:
    """Tick outcome: the rule cards fired plus when."""

    project_id: str
    fired: Tuple[str, ...] = ()
    checked_at: str = ""


#: Due rule cards evaluated on every tick.
DUE_CARDS = ("rule-tamper", "rule-guard")

#: Committed choices per project: card id, script, params.
_CHOICES: Dict[str, Tuple[str, str, Tuple[str, ...]]] = {}


def _utcnow() -> str:
    """Current UTC time rendered like the frozen timestamps."""
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def reset_state() -> None:
    """Drop committed choices."""
    _CHOICES.clear()


def tick(project_id: str) -> EngineTick:
    """Fire due rule cards now; each firing records its journal row."""
    fired = []
    for card_id in DUE_CARDS:
        rule_cards.evaluate(project_id, card_id)
        fired.append(card_id)
    return EngineTick(
        project_id=str(project_id),
        fired=tuple(fired),
        checked_at=_utcnow(),
    )


def decide(project_id: str, card_id: str, script: str,
           params: Tuple[str, ...]) -> rule_cards.WatchDecision:
    """Commit the chosen script plus params; return the fresh decision."""
    decision = rule_cards.evaluate(project_id, card_id)
    _CHOICES[str(project_id)] = (str(card_id), str(script), tuple(params))
    return decision


def last_choice(project_id: str):
    """Return the committed choice for one project, or None."""
    return _CHOICES.get(str(project_id))
