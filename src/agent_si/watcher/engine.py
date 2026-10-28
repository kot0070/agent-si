"""Watcher engine: due rule cards, committed choices, supervised restart.

Owns REALIZATION_MAP entries ``watcher.engine.tick`` (:func:`tick`) and
``watcher.engine.decide`` (:func:`decide`). A tick evaluates every due
card now, so each firing records one WATCH_DECISION journal row; a decide
commits the chosen script plus params for a fired card and returns the
fresh evaluation of that card. Due cards derive from the rule-card
registry, never from hard-coded ids. :func:`resolve_action` picks the
script plus params for one card from the card's own fields.
:func:`supervised_restart` records every supervised restart attempt in
the journal; the watcher itself never stops agents.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Tuple

from agent_si.watcher import integrity as integrity_store
from agent_si.watcher import journal as journal_store
from agent_si.watcher import rules as rule_cards
from agent_si.watcher.journal import ERROR_CODES, WatcherError

__all__ = (
    "ERROR_CODES",
    "WatcherError",
    "EngineTick",
    "CardAction",
    "RestartReceipt",
    "DUE_CARDS",
    "tick",
    "decide",
    "resolve_action",
    "supervised_restart",
    "last_choice",
    "reset_state",
)


@dataclass(frozen=True)
class EngineTick:
    """Tick outcome: the rule cards fired plus when."""

    project_id: str
    fired: Tuple[str, ...] = ()
    checked_at: str = ""


@dataclass(frozen=True)
class CardAction:
    """Per-card action: script plus params from the card's own fields."""

    card_id: str
    script: str
    params: Tuple[str, ...] = ()


@dataclass(frozen=True)
class RestartReceipt:
    """Supervised restart attempt receipt plus its journal row ref."""

    project_id: str
    supervisor_ref: str
    accepted: bool = False
    reason: str = ""
    journal_entry_id: str = ""
    restarted_at: str = ""


#: Due rule cards, derived from the card registry (never hard-coded ids).
DUE_CARDS = tuple(rule_cards.RULES)

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


def resolve_action(project_id: str, card_id: str) -> CardAction:
    """Pick the script plus params for one card from its own fields."""
    card = rule_cards.describe(card_id)
    script = "scripts/%s_check.py" % card.area
    params = ("--model", card.model, "--hang-minutes", str(card.hang_minutes))
    return CardAction(
        card_id=str(card_id),
        script=script,
        params=params,
    )


def supervised_restart(project_id: str, supervisor_ref: str) -> RestartReceipt:
    """Record one supervised restart attempt; the watcher stops nothing."""
    key = str(project_id)
    ref = str(supervisor_ref)
    if not ref:
        entry = journal_store.append_event(
            key, "watcher", "SERVICE_STATE",
            "supervised restart refused: empty supervisor ref", (key,),
        )
        raise WatcherError(
            "STOP_REASON_MISSING",
            "supervised restart needs a supervisor ref",
        )
    try:
        integrity_store.verify(key)
    except WatcherError:
        journal_store.append_event(
            key, "watcher", "SERVICE_STATE",
            "supervised restart blocked: integrity mismatch", (key,),
        )
        raise
    entry = journal_store.append_event(
        key, "watcher", "SERVICE_STATE",
        "supervised restart by %s" % ref, (key,),
    )
    return RestartReceipt(
        project_id=key,
        supervisor_ref=ref,
        accepted=True,
        reason="restart supervised by %s" % ref,
        journal_entry_id=entry.entry_id,
        restarted_at=entry.timestamp,
    )


def last_choice(project_id: str):
    """Return the committed choice for one project, or None."""
    return _CHOICES.get(str(project_id))
