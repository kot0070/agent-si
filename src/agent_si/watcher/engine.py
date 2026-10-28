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
from typing import Any, Dict, Tuple

from agent_si.automation import cleanup as _cleanup_home
from agent_si.automation import service_status as _service_home
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
    "ScriptResult",
    "DUE_CARDS",
    "STANDARD_SCRIPTS",
    "tick",
    "decide",
    "resolve_action",
    "supervised_restart",
    "last_choice",
    "run_script",
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
    """Drop committed choices and service-watch baselines."""
    _CHOICES.clear()
    _SERVICE_BASELINE.clear()


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


@dataclass(frozen=True)
class ScriptResult:
    """Standard script outcome plus its journal row ref.

    Row Q8, lane m_entry, author CODER-2 Sable.
    """

    project_id: str
    script: str = ""
    outcome: str = ""
    detail: str = ""
    journal_entry_id: str = ""
    ran_at: str = ""


#: Watcher standard script set: restart a hung agent once, signal the
#: higher level, data-leak scan, workspace check, budget watch, temp-file
#: janitor, dependent-service watch. Portable per-project settings come
#: from the preset store; every script journals one row per run.
STANDARD_SCRIPTS = (
    "restart-hung-agent-once",
    "signal-higher-level",
    "data-leak-scan",
    "workspace-check",
    "budget-watch",
    "temp-file-janitor",
    "dependent-service-watch",
)

#: Last notified service states per project for dependent-service-watch.
_SERVICE_BASELINE: Dict[str, Dict[str, str]] = {}


def _script_restart(project_id: str, params: Tuple[str, ...],
                    supervisor_ref: str) -> Tuple[str, str]:
    """Row Q8: restart a hung agent once through supervised restart."""
    del params
    receipt = supervised_restart(project_id, supervisor_ref or "watcher")
    return "restarted", receipt.reason


def _script_signal(project_id: str, params: Tuple[str, ...],
                   supervisor_ref: str) -> Tuple[str, str]:
    """Row Q8: signal the higher level; watchers escalate, never act."""
    del params
    del supervisor_ref
    return "escalated", "higher level signalled for %s" % project_id


def _script_leak_scan(project_id: str, params: Tuple[str, ...],
                      supervisor_ref: str) -> Tuple[str, str]:
    """Row Q8: read-only data-leak scan over the declared descriptor."""
    del supervisor_ref
    service_id = params[0] if params else "svc-container"
    report = _service_home.scan_container(service_id)
    outcome = "clean" if report.verdict == "CLEAN" else "findings"
    return outcome, "scan %s: %s checked=%d findings=%d" % (
        service_id, report.verdict, report.checked, report.findings)


def _script_workspace(project_id: str, params: Tuple[str, ...],
                      supervisor_ref: str) -> Tuple[str, str]:
    """Row Q8: workspace check over stored facts; flag escape rows."""
    del params
    del supervisor_ref
    rows = journal_store.stored_rows(project_id)
    hits = [row for row in rows
            if row.kind in ("TAMPER_ATTEMPT", "GUARD_BLOCK")]
    if hits:
        return "flagged", "workspace check: %d escape rows" % len(hits)
    return "clean", "workspace check: no escape rows"


def _script_budget(project_id: str, params: Tuple[str, ...],
                   supervisor_ref: str) -> Tuple[str, str]:
    """Row Q8: observe-only budget watch; degrades when K04 is absent."""
    del params
    del supervisor_ref
    try:
        from agent_si.budget.gate import BudgetGate
    except ImportError:
        return "unavailable", "budget gate not readable"
    try:
        state = BudgetGate().get_state(project_id)
    except (KeyError, LookupError):
        return "unavailable", "no budget state for %s" % project_id
    if state is None:
        return "unavailable", "no budget state for %s" % project_id
    return "observed", "budget state served for %s" % project_id


def _script_janitor(project_id: str, params: Tuple[str, ...],
                    supervisor_ref: str,
                    run_temp_base: object = None) -> Tuple[str, str]:
    """Row Q8: temp-file janitor through the standard cleanup script."""
    del supervisor_ref
    if not params:
        raise ValueError("temp-file-janitor needs a run id")
    receipt = _cleanup_home.clean_run_temp(
        _cleanup_home.resolve_base(run_temp_base), params[0])
    return "cleaned", "janitor %s: removed=%d free=%d" % (
        params[0], len(receipt["removed"]), int(receipt["free"]))


def _script_dependents(project_id: str, params: Tuple[str, ...],
                       supervisor_ref: str) -> Tuple[str, str]:
    """Row Q8: dependent-service watch; one row per state change."""
    del params
    del supervisor_ref
    states = {}
    for service_id in _service_home.services_for_project(project_id):
        states[service_id] = str(_service_home.get(service_id).state)
    baseline = _SERVICE_BASELINE.get(project_id, {})
    changed = sorted(
        service_id for service_id, state in states.items()
        if baseline.get(service_id) != state)
    _SERVICE_BASELINE[project_id] = states
    if changed:
        return ("changed:%d" % len(changed),
                "dependents changed: %s" % ",".join(changed))
    return "no-change", "dependents steady: %d checked" % len(states)


#: Script name to its runner (row Q8, lane m_entry, author CODER-2 Sable).
_SCRIPT_RUNNERS: Dict[str, Any] = {
    "restart-hung-agent-once": _script_restart,
    "signal-higher-level": _script_signal,
    "data-leak-scan": _script_leak_scan,
    "workspace-check": _script_workspace,
    "budget-watch": _script_budget,
    "temp-file-janitor": _script_janitor,
    "dependent-service-watch": _script_dependents,
}


def run_script(project_id: str, script: str,
               params: Tuple[str, ...] = (),
               supervisor_ref: str = "",
               run_temp_base: object = None) -> ScriptResult:
    """Run one standard script on planted facts; journal one row.

    Row Q8, lane m_entry, author CODER-2 Sable. Unknown scripts raise
    ``RULE_NOT_FOUND``; every run appends one ``SERVICE_STATE`` journal
    row carrying the script name plus the outcome.
    """
    key = str(project_id)
    name = str(script)
    runner = _SCRIPT_RUNNERS.get(name)
    if runner is None:
        raise WatcherError(
            "RULE_NOT_FOUND", "unknown script %r" % (script,))
    if name == "temp-file-janitor":
        outcome, detail = runner(key, tuple(params), str(supervisor_ref),
                                 run_temp_base)
    else:
        outcome, detail = runner(key, tuple(params), str(supervisor_ref))
    entry = journal_store.append_event(
        key, "watcher", "SERVICE_STATE",
        "script %s: %s %s" % (name, outcome, detail), (name,),
    )
    return ScriptResult(
        project_id=key,
        script=name,
        outcome=outcome,
        detail=detail,
        journal_entry_id=entry.entry_id,
        ran_at=entry.timestamp,
    )
