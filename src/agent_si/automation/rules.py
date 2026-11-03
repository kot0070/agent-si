"""FXAUTO rule engine (lane-internal, no frozen surface).

A rule is a no-code row: WHEN (schedule | metric | event) + optional IF text
+ DO action + IF-MISSED policy + on/off. Rules bind to the existing
scheduler/trigger lanes (timers, launchers, metrics, triggers) and fire
through them, so every fire is a recorded, governed, pausable run.
Strong DO actions (pause-project, start-next-task, switch-model, run-audit)
do not run on fire: they open an approval that a user decides in the
Automations page; only the approval executes. Weak actions (checkpoint,
notify, reread-context) execute at once through real lane state.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from agent_si.automation import pause as pause_flags
from agent_si.automation import runner
from agent_si.automation import scheduler as scheduler_lane
from agent_si.automation import triggers as triggers_lane

_IFACE_MODULE = "agent_si.automation.interface"


def _auto_iface():
    try:
        return sys.modules[_IFACE_MODULE]
    except KeyError:
        raise RuntimeError(
            "frozen contract %r is not imported" % (_IFACE_MODULE,)
        )


WHEN_KINDS = ("schedule", "metric", "event")

SCHEDULE_DETAILS = ("every-3h", "every-30m", "daily-22:00")

METRIC_DETAILS = ("budget-90", "context-70", "turns-40")

EVENT_DETAILS = ("app-started", "audit-finished", "audit-failed")

DO_ACTIONS = (
    "start-next-task",
    "reread-context",
    "checkpoint",
    "pause-project",
    "switch-model",
    "run-audit",
    "notify",
)

WEAK_ACTIONS = ("reread-context", "checkpoint", "notify")

STRONG_ACTIONS = (
    "pause-project",
    "start-next-task",
    "switch-model",
    "run-audit",
)

MISS_POLICIES = ("skip", "once")

SCHEDULE_INTERVALS = {
    "every-3h": 10800.0,
    "every-30m": 1800.0,
    "daily-22:00": 86400.0,
}

METRIC_THRESHOLDS = {
    "budget-90": 0.9,
    "context-70": 0.7,
    "turns-40": 40.0,
}

STATE_SENTENCES = {
    "PENDING": "Queued",
    "RUNNING": "Running",
    "PAUSED": "Paused",
    "SUCCEEDED": "Done",
    "FAILED": "Failed",
    "CANCELLED": "Cancelled",
}

_rules: Dict[str, Dict[str, Any]] = {}
_approvals: Dict[str, Dict[str, Any]] = {}
_results: Dict[str, Dict[str, Any]] = {}
_run_rule: Dict[str, str] = {}
_seq = 0
_appr_seq = 0
_state_path: Optional[str] = None
_ctx: Dict[str, Any] = {"checkpoints": None, "journal": None,
                        "keeper_dir": None}
_metric_sources: Dict[str, Callable[[str], Optional[float]]] = {}


def reset_state() -> None:
    """Clear rules, approvals, results, sequences, context and sources."""
    global _seq, _appr_seq, _state_path
    _rules.clear()
    _approvals.clear()
    _results.clear()
    _run_rule.clear()
    _seq = 0
    _appr_seq = 0
    _state_path = None
    _ctx.update({"checkpoints": None, "journal": None,
                 "keeper_dir": None})
    _metric_sources.clear()


def set_context(ctx: Dict[str, Any]) -> None:
    """Bind lane context: checkpoints store, journal hook, keeper dir."""
    _ctx.update(ctx)


def set_state_path(path: Optional[str]) -> None:
    """Bind the JSON path rules persist to after each mutation."""
    global _state_path
    _state_path = path


def set_metric_source(
    detail: str, fn: Optional[Callable[[str], Optional[float]]]
) -> None:
    """Bind a live value source for one metric detail (None clears it)."""
    if fn is None:
        _metric_sources.pop(detail, None)
    else:
        _metric_sources[detail] = fn


def turns_value(project_id: str) -> Optional[float]:
    """Live turns reading: highest open turn count across project runs."""
    best = 0
    seen = False
    for run_id, rec in runner._runs.items():
        if rec.get("project_id") != project_id:
            continue
        seen = True
        try:
            best = max(best, int(rec.get("turn_seq", 0) or 0))
        except (TypeError, ValueError):
            continue
    return float(best) if seen else None


def budget_fraction(project_id: str) -> Optional[float]:
    """Live budget reading: spent fraction from the budget gate, if bound."""
    try:
        from agent_si.runtime import manager as _manager

        gate = _manager._BUDGET_GATE
    except Exception:
        return None
    if gate is None:
        return None
    try:
        state = gate.get_state(str(project_id or ""))
    except Exception:
        return None
    try:
        from decimal import Decimal as _Dec

        def _num(value: Any) -> Optional[_Dec]:
            if value is None or isinstance(value, bool):
                return None
            return _Dec(str(value))

        hard = _num(state.get("hard_limit") if isinstance(
            state, dict) else getattr(state, "hard_limit", None))
        spent = _num(state.get("spent") if isinstance(
            state, dict) else getattr(state, "spent", None))
        reserved = _num(state.get("reserved") if isinstance(
            state, dict) else getattr(state, "reserved", None))
    except Exception:
        return None
    if hard is None or hard <= 0:
        return None
    return float((spent or _Dec(0)) + (reserved or _Dec(0))) / float(hard)


def _journal(project_id: str, summary: str, refs: tuple = ()) -> None:
    hook = _ctx.get("journal")
    if hook is not None:
        hook(project_id, "rules", "AUTOMATION_RUN", summary, refs=refs)


def _next_daily_22(now: float) -> float:
    day = datetime.fromtimestamp(now, tz=timezone.utc).date()
    due = datetime(day.year, day.month, day.day, 22, 0,
                   tzinfo=timezone.utc).timestamp()
    if due <= now:
        due += 86400.0
    return due


def _bind(rule: Dict[str, Any], now: Optional[float]) -> None:
    """(Re)bind one rule to timer/launcher/trigger or metric/trigger rows."""
    project_id = rule["project_id"]
    rule_id = rule["rule_id"]
    at = now if now is not None else time.time()
    if rule["when_kind"] == "schedule":
        interval = SCHEDULE_INTERVALS[rule["when_detail"]]
        first_due = at if rule["when_detail"] != "daily-22:00" \
            else _next_daily_22(at)
        launcher_id = "%s-launcher" % rule_id
        scheduler_lane.register_launcher(launcher_id, project_id, "")
        timer_id = "%s-timer" % rule_id
        try:
            kept = scheduler_lane.get_timer(timer_id)
            first_due = float(kept.get("next_due", first_due))
        except _auto_iface().AutomationError:
            pass
        scheduler_lane.register_timer(
            timer_id, project_id, interval, launcher_id=launcher_id,
            catchup="skip" if rule["miss"] == "skip" else "once",
            first_due=first_due,
        )
        rule["timer_id"] = timer_id
        rule["launcher_id"] = launcher_id
        triggers_lane.register_trigger(
            rule_id, project_id, kind="TIMER", schedule_ref=timer_id)
    elif rule["when_kind"] == "metric":
        metric_id = "%s-metric" % rule_id
        action = "stop" if rule["do"] == "pause-project" else "notify"
        try:
            scheduler_lane.get_metric(metric_id)
        except _auto_iface().AutomationError:
            scheduler_lane.register_metric(
                metric_id, project_id,
                METRIC_THRESHOLDS[rule["when_detail"]], action=action)
        rule["metric_id"] = metric_id
        triggers_lane.register_trigger(
            rule_id, project_id, kind="METRIC", schedule_ref=metric_id)
    else:
        triggers_lane.register_trigger(
            rule_id, project_id, kind="LAUNCHER", schedule_ref="")


def _validate(
    name: str, when_kind: str, when_detail: str, if_text: str, do: str,
    miss: str,
) -> None:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("rule needs a non-empty name")
    if when_kind not in WHEN_KINDS:
        raise ValueError("WHEN kind is schedule, metric or event")
    details = (
        SCHEDULE_DETAILS if when_kind == "schedule"
        else METRIC_DETAILS if when_kind == "metric"
        else EVENT_DETAILS
    )
    if when_detail not in details:
        raise ValueError(
            "WHEN detail %r is not a %s choice" % (when_detail, when_kind))
    if not isinstance(if_text, str):
        raise ValueError("IF text must be text")
    if len(if_text) > 500:
        raise ValueError("IF text is longer than 500 characters")
    if do not in DO_ACTIONS:
        raise ValueError("DO action %r is not offered" % (do,))
    if miss not in MISS_POLICIES:
        raise ValueError("IF-MISSED is skip or run once")


def _persist() -> None:
    if _state_path is not None:
        save_state(_state_path)


def create_rule(
    project_id: str,
    name: str,
    when_kind: str,
    when_detail: str,
    if_text: str = "",
    do: str = "notify",
    miss: str = "once",
    enabled: bool = True,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Store a rule and bind its scheduler rows; validates plainly."""
    _validate(name, when_kind, when_detail, if_text, do, miss)
    global _seq
    _seq += 1
    rule_id = "rule-%04d" % _seq
    rule = {
        "rule_id": rule_id,
        "name": name.strip(),
        "project_id": project_id,
        "when_kind": when_kind,
        "when_detail": when_detail,
        "if_text": if_text,
        "do": do,
        "miss": miss,
        "enabled": bool(enabled),
        "created_at": now if now is not None else time.time(),
        "timer_id": None,
        "launcher_id": None,
        "metric_id": None,
        "last_run_id": None,
        "last_result": None,
    }
    _bind(rule, now)
    _rules[rule_id] = rule
    _journal(project_id, "rule created %s" % name.strip(), refs=(rule_id,))
    _persist()
    return dict(rule)


def get_rule(project_id: str, rule_id: str) -> Dict[str, Any]:
    """Return one stored rule; unknown ids raise TRIGGER_NOT_FOUND."""
    rule = _rules.get(rule_id)
    if rule is None or rule["project_id"] != project_id:
        raise _auto_iface().AutomationError(
            code="TRIGGER_NOT_FOUND",
            detail="rule %s unknown" % rule_id,
        )
    return dict(rule)


def list_rules(project_id: str) -> List[Dict[str, Any]]:
    """Every stored rule for one project, oldest first, with next runs."""
    rows = [rule for rule in _rules.values()
            if rule["project_id"] == project_id]
    rows.sort(key=lambda row: row["rule_id"])
    out = []
    for rule in rows:
        row = dict(rule)
        row["next_run_at"] = _next_run_at(rule)
        out.append(row)
    return out


def _next_run_at(rule: Dict[str, Any]) -> Optional[float]:
    """Next due epoch for an enabled schedule rule, else None."""
    if not rule.get("enabled"):
        return None
    if rule.get("when_kind") != "schedule":
        return None
    timer_id = rule.get("timer_id")
    if not timer_id:
        return None
    try:
        timer = scheduler_lane.get_timer(timer_id)
    except _auto_iface().AutomationError:
        return None
    try:
        return float(timer.get("next_due"))
    except (TypeError, ValueError):
        return None


def set_enabled(
    project_id: str, rule_id: str, enabled: bool
) -> Dict[str, Any]:
    """Flip a rule off/on; off rules never fire on tick or Run now."""
    rule = _rules.get(rule_id)
    if rule is None or rule["project_id"] != project_id:
        raise _auto_iface().AutomationError(
            code="TRIGGER_NOT_FOUND",
            detail="rule %s unknown" % rule_id,
        )
    rule["enabled"] = bool(enabled)
    _journal(
        project_id,
        "rule %s %s" % (
            rule["name"], "on" if rule["enabled"] else "off"),
        refs=(rule_id,),
    )
    _persist()
    row = dict(rule)
    row["next_run_at"] = _next_run_at(rule)
    return row


def _run_to_dict(run: Any) -> Dict[str, Any]:
    return {
        "run_id": getattr(run, "run_id", ""),
        "project_id": getattr(run, "project_id", ""),
        "template_id": getattr(run, "template_id", "") or "",
        "trigger_id": getattr(run, "trigger_id", None),
        "state": getattr(run, "state", ""),
        "started_at": getattr(run, "started_at", ""),
        "updated_at": getattr(run, "updated_at", ""),
    }


def _record_action(
    rule: Dict[str, Any], run_id: str, receipt: Dict[str, Any]
) -> None:
    key = "%s\x00%s" % (rule["rule_id"], run_id)
    _results[key] = dict(receipt.get("result") or {})
    rule["last_run_id"] = run_id
    rule["last_result"] = dict(receipt.get("result") or {})
    _run_rule[run_id] = rule["rule_id"]
    try:
        history = runner._histories.get(run_id)
    except AttributeError:
        history = None
    if history is not None:
        history.append({
            "event": "action:%s:%s" % (
                rule["do"], receipt.get("outcome", "done")),
            "at": time.time(),
        })


def fire_rule(
    project_id: str, rule_id: str, reason: str = "manual",
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Run now: fire one rule into a recorded run and execute its DO.

    Refused with AUTOMATION_PAUSED while the pause is effective or the
    rule is turned off. Strong DO actions open an approval instead of a
    run; the approval executes on decide.
    """
    from agent_si.automation import actions as actions_lane

    rule = _rules.get(rule_id)
    if rule is None or rule["project_id"] != project_id:
        raise _auto_iface().AutomationError(
            code="TRIGGER_NOT_FOUND",
            detail="rule %s unknown" % rule_id,
        )
    if not rule.get("enabled"):
        raise _auto_iface().AutomationError(
            code="AUTOMATION_PAUSED",
            detail="rule %s is turned off" % rule["name"],
        )
    if pause_flags.is_effective(project_id):
        raise _auto_iface().AutomationError(
            code="AUTOMATION_PAUSED",
            detail="automation paused for %s" % project_id,
        )
    if rule["do"] in STRONG_ACTIONS:
        approval = _request_approval(rule, reason, now)
        _persist()
        return {
            "rule_id": rule_id,
            "run": None,
            "result": {
                "key": "fxauto.results.waitingApproval",
                "params": {"name": rule["name"]},
            },
            "approval": dict(approval),
        }
    run = triggers_lane.fire_trigger(project_id, rule_id)
    fired = _run_to_dict(run)
    receipt = actions_lane.do_action(rule, fired, _ctx)
    _record_action(rule, fired["run_id"], receipt)
    _journal(project_id, "rule fired %s (%s)" % (rule["name"], reason),
             refs=(fired["run_id"],))
    _persist()
    return {
        "rule_id": rule_id,
        "run": fired,
        "result": dict(receipt["result"]),
        "approval": None,
    }


def _request_approval(
    rule: Dict[str, Any], reason: str, now: Optional[float]
) -> Dict[str, Any]:
    global _appr_seq
    _appr_seq += 1
    approval_id = "appr-%04d" % _appr_seq
    approval = {
        "approval_id": approval_id,
        "rule_id": rule["rule_id"],
        "rule_name": rule["name"],
        "project_id": rule["project_id"],
        "action": rule["do"],
        "reason": reason,
        "state": "pending",
        "created_at": now if now is not None else time.time(),
        "decided_at": None,
        "run_id": None,
        "result": None,
    }
    _approvals[approval_id] = approval
    _journal(
        rule["project_id"],
        "approval requested %s for rule %s" % (rule["do"], rule["name"]),
        refs=(approval_id,),
    )
    return approval


def list_approvals(project_id: str) -> List[Dict[str, Any]]:
    """Pending-first approvals for one project, oldest first."""
    rows = [dict(row) for row in _approvals.values()
            if row["project_id"] == project_id]
    rows.sort(key=lambda row: (
        0 if row["state"] == "pending" else 1, row["approval_id"]))
    return rows


def decide_approval(
    project_id: str, approval_id: str, approved: bool,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Decide a pending approval; an approved pause pauses for real."""
    from agent_si.automation import actions as actions_lane

    approval = _approvals.get(approval_id)
    if approval is None or approval["project_id"] != project_id:
        raise _auto_iface().AutomationError(
            code="TRIGGER_NOT_FOUND",
            detail="approval %s unknown" % approval_id,
        )
    if approval["state"] != "pending":
        return dict(approval)
    if pause_flags.is_effective(project_id):
        raise _auto_iface().AutomationError(
            code="AUTOMATION_PAUSED",
            detail="automation paused for %s" % project_id,
        )
    rule = _rules.get(approval["rule_id"])
    if rule is None:
        raise _auto_iface().AutomationError(
            code="TRIGGER_NOT_FOUND",
            detail="rule %s unknown" % approval["rule_id"],
        )
    at = now if now is not None else time.time()
    if not approved:
        approval["state"] = "rejected"
        approval["decided_at"] = at
        approval["result"] = {
            "key": "fxauto.results.rejected",
            "params": {"name": rule["name"]},
        }
        _journal(project_id, "approval rejected %s" % approval_id,
                 refs=(approval_id,))
        _persist()
        return dict(approval)
    run = triggers_lane.fire_trigger(project_id, rule["rule_id"])
    fired = _run_to_dict(run)
    receipt = actions_lane.execute_approved(rule, fired, _ctx)
    approval["state"] = "approved"
    approval["decided_at"] = at
    approval["run_id"] = fired["run_id"]
    approval["result"] = dict(receipt["result"])
    _record_action(rule, fired["run_id"], receipt)
    _journal(project_id, "approval granted %s" % approval_id,
             refs=(fired["run_id"],))
    _persist()
    return dict(approval)


def _metric_value(
    rule: Dict[str, Any], overrides: Optional[Dict[str, float]]
) -> Optional[float]:
    detail = rule["when_detail"]
    if overrides is not None and detail in overrides:
        return overrides[detail]
    source = _metric_sources.get(detail)
    if source is None:
        return None
    try:
        return source(rule["project_id"])
    except Exception:
        return None


def tick(
    now: Optional[float] = None,
    metric_values: Optional[Dict[str, float]] = None,
) -> List[Dict[str, Any]]:
    """Fire every due rule: due timers, then metrics with live readings.

    A refused or not-due row is skipped without failing the tick; the
    skip count rides the return for the UI tick probe.
    """
    from agent_si.automation import actions as actions_lane

    at = now if now is not None else time.time()
    fired: List[Dict[str, Any]] = []
    skipped = 0
    for rule_id in sorted(_rules):
        rule = _rules[rule_id]
        if not rule.get("enabled"):
            continue
        project_id = rule["project_id"]
        try:
            run = None
            if rule["when_kind"] == "schedule":
                timer_id = rule.get("timer_id")
                if timer_id is None:
                    continue
                maybe = scheduler_lane.fire_timer(timer_id, now=at)
                run = _run_to_dict(maybe) if maybe is not None else None
            elif rule["when_kind"] == "metric":
                metric_id = rule.get("metric_id")
                if metric_id is None:
                    continue
                value = _metric_value(rule, metric_values)
                if value is None:
                    continue
                maybe = scheduler_lane.evaluate_metric(metric_id, value)
                run = _run_to_dict(maybe) if maybe is not None else None
            else:
                continue
        except _auto_iface().AutomationError:
            skipped += 1
            continue
        if run is None:
            continue
        if rule["do"] in STRONG_ACTIONS:
            approval = _request_approval(rule, "due", at)
            fired.append({
                "rule_id": rule_id,
                "run": None,
                "result": {
                    "key": "fxauto.results.waitingApproval",
                    "params": {"name": rule["name"]},
                },
                "approval": dict(approval),
            })
            continue
        receipt = actions_lane.do_action(rule, run, _ctx)
        _record_action(rule, run["run_id"], receipt)
        fired.append({
            "rule_id": rule_id,
            "run": run,
            "result": dict(receipt["result"]),
            "approval": None,
        })
    if _state_path is not None:
        save_state(_state_path)
    return fired


def fire_event(
    project_id: str, event_name: str, now: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Fire every enabled event rule matching one event (boot, audit)."""
    out = []
    for rule in list_rules(project_id):
        if rule["when_kind"] != "event":
            continue
        if rule["when_detail"] != event_name:
            continue
        out.append(fire_rule(project_id, rule["rule_id"],
                             reason=event_name, now=now))
    return out


def _result_text(result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if isinstance(result, dict) and result.get("key"):
        return {"key": result["key"],
                "params": dict(result.get("params") or {})}
    return {"key": "fxauto.results.unknown", "params": {}}


def run_history(project_id: str) -> List[Dict[str, Any]]:
    """Every recorded automation run: time, rule, state, plain result."""
    rows = []
    for run in runner.list_runs(project_id):
        try:
            stamp = float(run.started_at)
        except (TypeError, ValueError):
            stamp = 0.0
        rule_id = run.trigger_id
        if rule_id not in _rules:
            rule_id = _run_rule.get(run.run_id)
        rule = _rules.get(rule_id or "")
        result = None
        if rule_id is not None:
            result = _results.get("%s\x00%s" % (rule_id, run.run_id))
        if result is None and rule is not None \
                and rule.get("last_run_id") == run.run_id:
            result = rule.get("last_result")
        rows.append({
            "run_id": run.run_id,
            "time": stamp,
            "rule": rule["name"] if rule is not None else "",
            "state": STATE_SENTENCES.get(run.state, run.state),
            "result": _result_text(result),
        })
    return rows


def save_state(path: str) -> str:
    """Persist rules, approvals, results and sequences as plain JSON."""
    payload = {
        "schema": 1,
        "seq": _seq,
        "appr_seq": _appr_seq,
        "rules": [dict(rule) for rule in _rules.values()],
        "approvals": [dict(row) for row in _approvals.values()],
        "results": dict(_results),
        "run_rule": dict(_run_rule),
    }
    with open(path, "w", encoding="utf-8", newline="") as handle:
        json.dump(payload, handle, indent=2)
    global _state_path
    _state_path = path
    return path


def load_state(path: str) -> str:
    """Restore rules saved by save_state and rebind their scheduler rows."""
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    global _seq, _appr_seq
    keep_ctx = dict(_ctx)
    keep_sources = dict(_metric_sources)
    reset_state()
    _ctx.update(keep_ctx)
    _metric_sources.update(keep_sources)
    _seq = int(payload.get("seq", 0))
    _appr_seq = int(payload.get("appr_seq", 0))
    for row in payload.get("rules", []):
        rule = dict(row)
        _bind(rule, None)
        _rules[rule["rule_id"]] = rule
    for row in payload.get("approvals", []):
        _approvals[row["approval_id"]] = dict(row)
    for key, value in payload.get("results", {}).items():
        _results[str(key)] = dict(value)
    for key, value in payload.get("run_rule", {}).items():
        _run_rule[str(key)] = str(value)
    global _state_path
    _state_path = path
    return path
