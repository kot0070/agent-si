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
from agent_si.watcher import stats as stats_home
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
    "allowed_actions",
    "configure_watcher_model",
    "watcher_model_config",
    "evaluate",
    "effective_hang_minutes",
    "effective_card",
    "set_card_hang_minutes",
    "HANG_MIN_MINUTES",
    "HANG_MAX_MINUTES",
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

#: Per-project hang-minute overrides: (project id, rule id) to minutes.
#: FXFACTS F6a: the Watcher tab minutes input writes here through
#: set_card_hang_minutes (range-checked); the watch loop reads the
#: effective value, so the loop really uses the saved minutes. The card
#: registry (RULES) stays frozen; absent means the card default.
_HANG_OVERRIDE: Dict[Tuple[str, str], int] = {}

#: Lowest and highest settable hang window in minutes.
HANG_MIN_MINUTES = 1
HANG_MAX_MINUTES = 1440

#: Decision sequence; restarted by reset_state for probe isolation.
_SEQ = 0

#: FXZERO R4: last journaled alert per project+card: (verdict, condition
#: signature). One condition journals one alert; an unchanged repeat
#: journals nothing (the repeat still counts into the per-rule tally).
_LAST_ALERT: Dict[Tuple[str, str], Tuple[str, str]] = {}

#: FXZERO R4: project+card pairs whose latest evaluation was such an
#: unchanged repeat (side channel: the frozen WatchDecision shape is
#: untouched). Cleared with _LAST_ALERT by reset_state.
_REPEAT: set = set()


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
    """True when a fresh SERVICE_STATE heartbeat is overdue at the moment.

    FXFACTS F6b: no beats at all is no evidence of staleness (a run that
    just started has no beats yet), so it never escalates; only beats
    that exist and are older than the hang window count as stale.
    """
    beats = []
    for row in rows:
        if row.kind != "SERVICE_STATE":
            continue
        try:
            beats.append(_parse_stamp(row.timestamp))
        except ValueError:
            continue
    if not beats:
        return False
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


def effective_hang_minutes(project_id: str, rule_id: str) -> int:
    """Hang window one evaluation really uses: the project override when
    set through set_card_hang_minutes, else the card default."""
    card = describe(rule_id)
    try:
        return _HANG_OVERRIDE[(str(project_id), str(rule_id))]
    except KeyError:
        return card.hang_minutes


def effective_card(project_id: str, rule_id: str) -> RuleCard:
    """Card record with the effective hang window (registry untouched)."""
    card = describe(rule_id)
    minutes = effective_hang_minutes(project_id, rule_id)
    if minutes == card.hang_minutes:
        return card
    from dataclasses import replace as _replace
    return _replace(card, hang_minutes=minutes)


def set_card_hang_minutes(project_id: str, rule_id: str,
                          minutes: int) -> RuleCard:
    """Set one project's hang window for one card (additive, range-checked).

    Raises RULE_NOT_FOUND for an unknown card and ValueError outside
    1..1440 minutes. Returns the effective card the loop will use.
    """
    card = describe(rule_id)
    try:
        value = int(minutes)
    except (TypeError, ValueError):
        raise ValueError(
            "hang minutes for %r must be %d..%d, got %r"
            % (rule_id, HANG_MIN_MINUTES, HANG_MAX_MINUTES, minutes)
        ) from None
    if not (HANG_MIN_MINUTES <= value <= HANG_MAX_MINUTES):
        raise ValueError(
            "hang minutes for %r must be %d..%d, got %r"
            % (rule_id, HANG_MIN_MINUTES, HANG_MAX_MINUTES, minutes))
    _HANG_OVERRIDE[(str(project_id), str(rule_id))] = value
    if value == card.hang_minutes:
        return card
    from dataclasses import replace as _replace
    return _replace(card, hang_minutes=value)


def reset_state() -> None:
    """Restart decision ids; the card registry is definitions, not state."""
    global _SEQ
    _SEQ = 0
    _LAST_ALERT.clear()
    _REPEAT.clear()
    _HANG_OVERRIDE.clear()
    _TIMER_PAUSED.clear()
    _SETTINGS.clear()
    _WATCHER_MODEL.update({
        "transport": None,
        "local_model": "",
        "local_connected": False,
        "cloud_model": "",
        "cloud_connected": False,
        "cloud_fallback": False,
    })
    try:
        from agent_si.watcher import stats as _stats_home

        _stats_home.reset_state()
    except Exception:
        pass


#: Configured watcher model: the ONE transport the abnormal path may
#: call, plus which model names are connected. Facts-only input, one
#: allowed action out, garbage means the rule default. Local answers
#: when connected; a cloud model answers only when the fallback is on
#: (config flag or the project's cloud_fallback setting); otherwise
#: the rule default applies with no call and no load.
_WATCHER_MODEL = {
    "transport": None,
    "local_model": "",
    "local_connected": False,
    "cloud_model": "",
    "cloud_connected": False,
    "cloud_fallback": False,
}


def configure_watcher_model(*, transport=None, local_model="",
                            local_connected=False, cloud_model="",
                            cloud_connected=False,
                            cloud_fallback=False) -> dict:
    """Configure the watcher model transport (composition root/tests).

    Returns the active config snapshot. reset_state clears it.
    """
    _WATCHER_MODEL.update({
        "transport": transport,
        "local_model": str(local_model or ""),
        "local_connected": bool(local_connected),
        "cloud_model": str(cloud_model or ""),
        "cloud_connected": bool(cloud_connected),
        "cloud_fallback": bool(cloud_fallback),
    })
    return watcher_model_config()


def watcher_model_config() -> dict:
    """Serve the active watcher model config snapshot (never a call)."""
    return dict(_WATCHER_MODEL)


def allowed_actions(rule_id: str,
                    hang_minutes: object = None,
                    ) -> Tuple[Tuple[str, Tuple[str, ...]], ...]:
    """The rule's allowed (script, params) actions, default first.

    The own script plus params derive from the card's own fields
    (mirroring engine.resolve_action); the fallback is the
    signal-higher-level default. A model answer outside this list is
    garbage and the default applies; unknown cards raise. An explicit
    hang window (the effective per-project value) rides the params.
    """
    card = describe(rule_id)
    minutes = card.hang_minutes if hang_minutes is None else hang_minutes
    own = ("scripts/%s_check.py" % card.area,
           ("--model", card.model, "--hang-minutes",
            str(minutes)))
    return (own, ("signal-higher-level", ()))


def _trigger_kinds(card: RuleCard) -> Tuple[str, ...]:
    """Stored-fact kinds that trigger this card off its resting verdict."""
    if card.area == "tamper":
        return ("TAMPER_ATTEMPT",)
    if card.area == "guard":
        return ("GUARD_BLOCK",)
    return ()


def _is_abnormal(card: RuleCard, verdict: WatchVerdict,
                 rows: Tuple) -> bool:
    """True when stored facts push the card off its resting verdict.

    A verdict away from base is abnormal; so is a verdict still on
    base while the card's own trigger facts are stored (the guard
    resting at BLOCK still fires on GUARD_BLOCK facts). Anything else
    is the normal background state: no row, no call, no load.
    """
    if verdict != card.base_verdict:
        return True
    kinds = {row.kind for row in rows}
    return any(kind in kinds for kind in _trigger_kinds(card))


def _selected_model(key: str) -> str:
    """The exact watcher model name to ask, or empty for the default.

    The local model when connected; a connected cloud model only when
    the fallback is on (config flag or the project setting); empty
    when no transport is configured, nothing is connected, or the
    project setting is off.
    """
    cfg = _WATCHER_MODEL
    if cfg.get("transport") is None:
        return ""
    if _SETTINGS.get(key) == "off":
        return ""
    if cfg.get("local_connected") and cfg.get("local_model"):
        return str(cfg["local_model"])
    fallback = bool(cfg.get("cloud_fallback")) or (
        _SETTINGS.get(key) == "cloud_fallback")
    if fallback and cfg.get("cloud_connected") and cfg.get("cloud_model"):
        return str(cfg["cloud_model"])
    return ""


def _metered_model_call(key: str, decision_id: str, model_name: str,
                        rule_id: str, allowed: Tuple) -> Tuple[str,
                                                              Tuple[str,
                                                                    ...],
                                                              Any, str, bool]:
    """ONE metered watcher-model call.

    Returns (script, params, usage, note, answered): ``note`` is empty
    on a clean allowed pick; ``answered`` tells whether a model
    answered at all (garbage still answered, so the row names it).
    Facts only in (rule id plus the allowed list), one allowed action
    out. Admit runs before the call (a block means the default), charge
    plus telemetry after it with role "watcher". Any garbage (wrong
    shape, outside the list, transport failure) means the rule default.
    Never raises.
    """
    default = allowed[0]
    note = ""
    try:
        from agent_si.runtime import manager as _manager
        from agent_si.runtime.devrun import roles as _roles

        gate = getattr(_manager, "_BUDGET_GATE", None)
    except Exception:
        _manager = None  # type: ignore[assignment]
        _roles = None  # type: ignore[assignment]
        gate = None
    try:
        if _roles is not None:
            _roles.admit_role_call(
                gate, project_id=key, task_id="", run_id=decision_id,
                role="watcher", provider_id="watcher")
    except Exception as exc:
        return (default[0], tuple(default[1]), {}, "budget blocked: %s"
                % (type(exc).__name__,), False)
    reply: Any = None
    try:
        reply = _WATCHER_MODEL["transport"](
            model_name, str(rule_id), allowed)
    except Exception as exc:
        return (default[0], tuple(default[1]), {}, "call failed: %s"
                % (type(exc).__name__,), False)
    usage: Any = reply.get("usage") or {} if isinstance(reply, dict) else {}
    try:
        if _roles is not None:
            _roles.settle_role_call(
                project_id=key, task_id="", run_id=decision_id,
                role="watcher", provider_id="watcher",
                model=model_name, usage=usage)
    except Exception:
        pass
    try:
        if isinstance(reply, dict):
            script = reply.get("script")
            params = reply.get("params")
            if isinstance(script, str) and isinstance(params, (list, tuple)):
                picked = (script, tuple(str(item) for item in params))
                for action in allowed:
                    if picked == (action[0], tuple(action[1])):
                        return (picked[0], picked[1], usage, "", True)
    except Exception:
        pass
    return (default[0], tuple(default[1]), usage, "garbage reply", True)


def _condition_signature(card: RuleCard, rows: Tuple) -> str:
    """Fingerprint the stored facts one verdict rests on.

    Trigger-fact entry ids plus the latest SERVICE_STATE stamp: new
    trigger facts or a fresh heartbeat change the condition (alert
    again); an identical repeat does not (one condition, one alert).
    """
    try:
        kinds = _trigger_kinds(card)
        hits = sorted(
            str(getattr(row, "entry_id", ""))
            for row in rows
            if getattr(row, "kind", "") in kinds)
    except Exception:
        hits = []
    try:
        beats = sorted(
            str(getattr(row, "timestamp", ""))
            for row in rows
            if getattr(row, "kind", "") == "SERVICE_STATE")
        heartbeat = beats[-1] if beats else ""
    except Exception:
        heartbeat = ""
    return "%s|%s" % (",".join(hits), heartbeat)


def _journal_once(project_id: str, card: RuleCard,
                  verdict: WatchVerdict, rows: Tuple,
                  summary: str) -> Tuple[str, bool]:
    """Journal one alert unless this exact condition already journaled.

    Returns (entry id, repeat): a repeat journals nothing and returns an
    empty id with repeat True (also recorded in the _REPEAT side
    channel for the engine tick).
    """
    key = (str(project_id), str(card.rule_id))
    sig = "%s|%s" % (
        verdict.value, _condition_signature(card, rows))
    if _LAST_ALERT.get(key) == sig:
        _REPEAT.add(key)
        return "", True
    entry = append_event(
        str(project_id), "watcher", "WATCH_DECISION",
        summary, (str(card.rule_id),),
    )
    _LAST_ALERT[key] = sig
    _REPEAT.discard(key)
    return entry.entry_id, False


def last_was_repeat(project_id: str, rule_id: str) -> bool:
    """True when the latest evaluation was an unchanged repeat (no row)."""
    return (str(project_id), str(rule_id)) in _REPEAT


def evaluate(project_id: str, rule_id: str) -> WatchDecision:
    """Decide one stored rule card; row only off the resting verdict.

    The card model governs how the verdict is served: ``local`` (the
    default) evaluates over stored facts; ``API`` falls back to the
    local evaluation when no cloud model is bound; ``OFF`` never
    blocks and journals its marker. A verdict on the card's resting
    base with none of the card's trigger facts stored is normal: no
    journal row, no model call, no load. Anything else is abnormal:
    exactly ONE call to the configured watcher model for one action
    plus params from the rule's allowed list (local when connected, a
    connected cloud model only when the fallback is on, else the rule
    default with the ``no watcher model: default action`` line). The
    row names the exact model that answered; the call carries budget
    admit plus charge plus a telemetry row; a garbage reply means the
    default and the model can never pick outside the list.

    Row 186: the first evaluation on a project with no stored facts
    seeds the default (standard) preset through
    :func:`presets.ensure_seeded` — one SERVICE_STATE row, idempotent,
    never a second seed row. Unknown cards still raise before any
    write; projects that already carry facts are left untouched, so
    the creation-time hook (outside this lane) stays the full fix.
    """
    card = describe(rule_id)
    key = str(project_id)
    if card.model != "OFF":
        card = effective_card(key, rule_id)
    if not journal_store.stored_rows(key):
        preset_store.ensure_seeded(key)
    global _SEQ
    _SEQ += 1
    decision_id = "dec-%04d" % _SEQ
    if card.model == "OFF":
        verdict = WatchVerdict.ALLOW
        rows = journal_store.stored_rows(str(project_id))
        entry_id, _ = _journal_once(
            str(project_id), card, verdict, rows,
            "%s ALLOW OFF" % (str(rule_id),))
        return WatchDecision(
            decision_id=decision_id,
            project_id=str(project_id),
            rule_id=str(rule_id),
            verdict=verdict,
            journal_entry_id=entry_id,
            decided_at=_utcnow(),
        )
    rows = journal_store.stored_rows(str(project_id))
    verdict = verdict_for(card, rows, _utcnow())
    if not _is_abnormal(card, verdict, rows):
        return WatchDecision(
            decision_id=decision_id,
            project_id=str(project_id),
            rule_id=str(rule_id),
            verdict=verdict,
            journal_entry_id="",
            decided_at=_utcnow(),
        )
    allowed = allowed_actions(rule_id, card.hang_minutes)
    default = allowed[0]
    model_name = _selected_model(key)
    if not model_name:
        script, params = default[0], tuple(default[1])
        summary = "%s %s no watcher model: default action" % (
            str(rule_id), verdict.value)
    else:
        script, _params, _usage, note, answered = _metered_model_call(
            key, decision_id, model_name, str(rule_id), allowed)
        if answered:
            # FXCARDS C4: an answered watcher-model call is always counted
            # in stats: every decision row naming model= has its counted
            # call, so the card can never read a model name beside 0 calls.
            stats_home.record_model_call(key, _usage)
        if not note:
            summary = "%s %s model=%s action=%s" % (
                str(rule_id), verdict.value, model_name, script)
        elif answered:
            summary = "%s %s model=%s action=%s default (%s)" % (
                str(rule_id), verdict.value, model_name, script, note)
        else:
            summary = "%s %s no watcher model: default action (%s)" % (
                str(rule_id), verdict.value, note)
    if card.model == "API":
        summary = "%s API->local" % summary
    entry_id, _ = _journal_once(
        str(project_id), card, verdict, rows, summary)
    return WatchDecision(
        decision_id=decision_id,
        project_id=str(project_id),
        rule_id=str(rule_id),
        verdict=verdict,
        journal_entry_id=entry_id,
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
