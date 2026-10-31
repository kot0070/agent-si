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
from agent_si.watcher import presets as preset_store
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
    "TIMER_FIRED",
    "ACTION_MODE_LOCAL_AI_DEFAULT",
    "WATCHER_ACTION_MODES",
    "TimerFireReceipt",
    "TimerPauseState",
    "WatcherSettings",
    "describe",
    "verdict_for",
    "evaluate",
    "fire_timer",
    "pause_timer",
    "get_watcher_settings",
    "update_watcher_settings",
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
    _TIMER_PAUSED.clear()
    _SETTINGS.clear()


def evaluate(project_id: str, rule_id: str) -> WatchDecision:
    """Decide one stored rule card; record one WATCH_DECISION row.

    The card model governs how the verdict is served: ``local`` (the
    default) evaluates over stored facts; ``API`` falls back to the local
    evaluation when no cloud model is bound; ``OFF`` never blocks. The
    serving model is journaled in the row summary.

    Row 186: the first evaluation on a project with no stored facts
    seeds the default (standard) preset through
    :func:`presets.ensure_seeded` — one SERVICE_STATE row, idempotent,
    never a second seed row. Unknown cards still raise before any
    write; projects that already carry facts are left untouched, so
    the creation-time hook (outside this lane) stays the full fix.
    """
    card = describe(rule_id)
    key = str(project_id)
    if not journal_store.stored_rows(key):
        preset_store.ensure_seeded(key)
    if card.model == "OFF":
        verdict = WatchVerdict.ALLOW
        serving = "OFF"
    else:
        verdict = verdict_for(
            card, journal_store.stored_rows(str(project_id)), _utcnow()
        )
        serving = "local" if card.model == "local" else "API->local"
    global _SEQ
    _SEQ += 1
    entry = append_event(
        str(project_id), "watcher", "WATCH_DECISION",
        "%s model=%s" % (str(rule_id), serving), (str(rule_id),),
    )
    return WatchDecision(
        decision_id="dec-%04d" % _SEQ,
        project_id=str(project_id),
        rule_id=str(rule_id),
        verdict=verdict,
        journal_entry_id=entry.entry_id,
        decided_at=_utcnow(),
    )


#: Row R-335 (BUILD_PLAN 1366): timer/auto-launcher/metric-triggered
#: action event. Firing a watcher timer records one AUTOMATION_RUN
#: journal row whose summary carries this event name.
TIMER_FIRED = "TIMER_FIRED"

#: Row R-335 action mode: timer/metric-triggered actions run on the
#: local-AI default; the mode is journaled on the TIMER_FIRED row.
ACTION_MODE_LOCAL_AI_DEFAULT = "local_ai_default"

#: Row R-336 (BUILD_PLAN 1367): watcher settings action modes served:
#: local-AI-default, cloud-fallback, off.
WATCHER_ACTION_MODES = (
    "local_ai_default",
    "cloud_fallback",
    "off",
)


@dataclass(frozen=True)
class TimerFireReceipt:
    """Timer firing receipt plus its AUTOMATION_RUN journal row ref."""

    timer_id: str
    project_id: str
    event: str = TIMER_FIRED
    action_mode: str = ACTION_MODE_LOCAL_AI_DEFAULT
    journal_entry_id: str = ""
    fired_at: str = ""


@dataclass(frozen=True)
class TimerPauseState:
    """Timer pause flag: a paused timer refuses to fire until resumed."""

    timer_id: str
    project_id: str
    paused: bool = False
    reason: str = ""


@dataclass(frozen=True)
class WatcherSettings:
    """Per-project watcher settings: the action mode (R-336)."""

    project_id: str
    action_mode: str = ACTION_MODE_LOCAL_AI_DEFAULT


#: Pause flags per timer: "project_id\\0timer_id" to the pause reason.
#: A present entry means the timer is paused; absent means live.
_TIMER_PAUSED: Dict[str, str] = {}

#: Watcher settings per project: project id to its action mode.
#: Absent means the local-AI default.
_SETTINGS: Dict[str, str] = {}


def _timer_key(project_id: str, timer_id: str) -> str:
    """Storage key for one project's timer pause flag."""
    return "%s\0%s" % (str(project_id), str(timer_id))


def fire_timer(project_id: str, timer_id: str) -> TimerFireReceipt:
    """Fire one watcher timer; record one TIMER_FIRED journal row.

    Row R-335: the firing is recorded as one AUTOMATION_RUN journal
    row carrying the TIMER_FIRED event plus the project's action mode
    (local_ai_default unless the settings choose otherwise). A paused
    timer refuses with AUTOMATION_PAUSED and records nothing.
    """
    key = str(project_id)
    name = str(timer_id)
    reason = _TIMER_PAUSED.get(_timer_key(key, name))
    if reason is not None:
        raise WatcherError(
            "AUTOMATION_PAUSED",
            "timer %r paused: %s" % (name, reason),
        )
    mode = _SETTINGS.get(key, ACTION_MODE_LOCAL_AI_DEFAULT)
    entry = append_event(
        key, "watcher", "AUTOMATION_RUN",
        "%s timer %s mode=%s" % (TIMER_FIRED, name, mode), (name,),
    )
    return TimerFireReceipt(
        timer_id=name,
        project_id=key,
        event=TIMER_FIRED,
        action_mode=mode,
        journal_entry_id=entry.entry_id,
        fired_at=entry.timestamp,
    )


def pause_timer(project_id: str, timer_id: str, paused: bool,
                reason: str = "") -> TimerPauseState:
    """Pause or resume one watcher timer (row R-335, pausable).

    Pausing needs a non-empty reason (PAUSE_REASON_MISSING otherwise);
    resuming clears the flag. Neither path journals: the refusal plus
    the recorded firings stay the observable facts.
    """
    key = str(project_id)
    name = str(timer_id)
    flag = bool(paused)
    text = str(reason)
    if flag:
        if not text.strip():
            raise WatcherError(
                "PAUSE_REASON_MISSING",
                "pausing timer %r needs a reason" % (name,),
            )
        _TIMER_PAUSED[_timer_key(key, name)] = text
    else:
        _TIMER_PAUSED.pop(_timer_key(key, name), None)
        text = ""
    return TimerPauseState(
        timer_id=name,
        project_id=key,
        paused=flag,
        reason=text,
    )


def get_watcher_settings(project_id: str) -> WatcherSettings:
    """Serve one project's watcher settings (row R-336, open read).

    Unconfigured projects serve the local-AI default; reads journal
    nothing.
    """
    key = str(project_id)
    return WatcherSettings(
        project_id=key,
        action_mode=_SETTINGS.get(key, ACTION_MODE_LOCAL_AI_DEFAULT),
    )


def update_watcher_settings(project_id: str,
                            action_mode: str) -> WatcherSettings:
    """Store one project's watcher action mode (row R-336, token write).

    Accepts local_ai_default, cloud_fallback or off; anything else
    raises SETTING_NOT_FOUND before anything is stored.
    """
    key = str(project_id)
    mode = str(action_mode)
    if mode not in WATCHER_ACTION_MODES:
        raise WatcherError(
            "SETTING_NOT_FOUND", "unknown action mode %r" % (action_mode,)
        )
    _SETTINGS[key] = mode
    return WatcherSettings(project_id=key, action_mode=mode)
