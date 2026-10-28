"""Lane B STEP2 scheduler: timers, launchers and metric actions.

Timers fire launchers, metric readings fire notify or stop actions, and
every action is recorded in the ledger, governed by the pause, and pausable
per project. Missed fires follow the catch-up setting (skip or run once),
and definitions persist as plain JSON so timers survive restarts.
"""

import json
import sys

from agent_si.automation import launcher
from agent_si.automation import pause as pause_flags
from agent_si.automation import runner


#: Dotted name of the frozen automation contract module. Product code
#: keeps no static import of it; the module object is resolved late at
#: call time, so the raised error is the same class the tests catch.
_IFACE_MODULE = "agent_si.automation.interface"


def _auto_iface():
    """Return the frozen automation contract module object."""
    try:
        return sys.modules[_IFACE_MODULE]
    except KeyError:
        raise RuntimeError(
            "frozen contract %r is not imported" % (_IFACE_MODULE,)
        )

_launchers = {}
_timers = {}
_metrics = {}
_ledger = []
_journal = None
_stop = None
_clock = None


def reset_state():
    """Clear launchers, timers, metrics, the ledger and every hook."""
    global _journal, _stop, _clock
    _launchers.clear()
    _timers.clear()
    _metrics.clear()
    del _ledger[:]
    _journal = None
    _stop = None
    _clock = None


def set_journal_hook(hook):
    """Set the journal notice hook (or None to silence notices)."""
    global _journal
    _journal = hook


def set_stop_hook(hook):
    """Set the stop-action hook (or None to skip stop requests)."""
    global _stop
    _stop = hook


def set_clock(clock):
    """Set the clock source used when a call passes no explicit time."""
    global _clock
    _clock = clock


def _now(now):
    if now is not None:
        return now
    if _clock is not None:
        return _clock()
    return 0.0


def _notify(project_id, summary, refs=()):
    if _journal is not None:
        _journal(project_id, "scheduler", "AUTOMATION_RUN", summary, refs=refs)


def register_launcher(launcher_id, project_id, template_id):
    """Store a launcher that starts runs for one template."""
    _launchers[launcher_id] = {
        "launcher_id": launcher_id,
        "project_id": project_id,
        "template_id": template_id,
    }
    return dict(_launchers[launcher_id])


def register_timer(timer_id, project_id, interval_s, launcher_id=None, catchup="once", first_due=None):
    """Store a repeating timer bound to one launcher."""
    due = first_due if first_due is not None else 0.0
    _timers[timer_id] = {
        "timer_id": timer_id,
        "project_id": project_id,
        "interval_s": float(interval_s),
        "launcher_id": launcher_id,
        "catchup": catchup,
        "next_due": due,
    }
    return dict(_timers[timer_id])


def register_metric(metric_id, project_id, threshold, action="notify"):
    """Store a metric rule that fires once its reading reaches threshold."""
    _metrics[metric_id] = {
        "metric_id": metric_id,
        "project_id": project_id,
        "threshold": float(threshold),
        "action": action,
    }
    return dict(_metrics[metric_id])


def get_timer(timer_id):
    """Return the stored timer row, including its next due time."""
    rec = _timers.get(timer_id)
    if rec is None:
        raise _auto_iface().AutomationError(
            code="TRIGGER_NOT_FOUND",
            detail="timer %s unknown" % timer_id,
        )
    return dict(rec)


def ledger():
    """Return the recorded action ledger, oldest first."""
    return [dict(entry) for entry in _ledger]


def _fire_launcher(launcher_id, now):
    rec = _launchers.get(launcher_id)
    if rec is None:
        raise _auto_iface().AutomationError(
            code="TRIGGER_NOT_FOUND",
            detail="launcher %s unknown" % launcher_id,
        )
    project_id = rec["project_id"]
    if pause_flags.is_effective(project_id):
        raise _auto_iface().AutomationError(
            code="AUTOMATION_PAUSED",
            detail="automation paused for %s" % project_id,
        )
    pending = runner.create_pending(project_id, template_id=rec["template_id"])
    run = launcher.launch(project_id, pending.run_id)
    _ledger.append(
        {"outcome": "launcher-fired", "launcher_id": launcher_id, "at": now}
    )
    _notify(project_id, "launcher fired %s" % launcher_id, refs=(run.run_id,))
    return run


def fire_launcher(launcher_id, now=None):
    """Fire one launcher into a recorded run; refused while paused."""
    at = _now(now)
    return _fire_launcher(launcher_id, at)


def fire_timer(timer_id, now=None):
    """Fire a due timer through its launcher.

    Returns None when the timer is not due yet. A timer past due follows
    its catch-up setting: "skip" advances without firing, anything else
    fires exactly one run. Refused while the pause is effective.
    """
    rec = _timers.get(timer_id)
    if rec is None:
        raise _auto_iface().AutomationError(
            code="TRIGGER_NOT_FOUND",
            detail="timer %s unknown" % timer_id,
        )
    at = _now(now)
    project_id = rec["project_id"]
    if pause_flags.is_effective(project_id):
        raise _auto_iface().AutomationError(
            code="AUTOMATION_PAUSED",
            detail="automation paused for %s" % project_id,
        )
    interval = rec["interval_s"]
    if at < rec["next_due"]:
        return None
    missed = at - rec["next_due"]
    if missed >= interval:
        rec["next_due"] = at + interval
        if rec["catchup"] == "skip":
            _ledger.append(
                {"outcome": "catchup-skip", "timer_id": timer_id, "at": at}
            )
            return None
        run = _fire_launcher(rec["launcher_id"], at)
        _ledger.append(
            {"outcome": "catchup-once", "timer_id": timer_id, "at": at}
        )
        return run
    rec["next_due"] = at + interval
    _ledger.append({"outcome": "timer-fired", "timer_id": timer_id, "at": at})
    return _fire_launcher(rec["launcher_id"], at)


def evaluate_metric(metric_id, value):
    """Evaluate one metric reading; fires the action at or above threshold.

    Returns None below threshold. The "stop" action requests a stop through
    the stop hook; every other action records a notify run.
    """
    rec = _metrics.get(metric_id)
    if rec is None:
        raise _auto_iface().AutomationError(
            code="TRIGGER_NOT_FOUND",
            detail="metric %s unknown" % metric_id,
        )
    project_id = rec["project_id"]
    if pause_flags.is_effective(project_id):
        raise _auto_iface().AutomationError(
            code="AUTOMATION_PAUSED",
            detail="automation paused for %s" % project_id,
        )
    if value < rec["threshold"]:
        _ledger.append(
            {"outcome": "metric-below", "metric_id": metric_id, "at": value}
        )
        return None
    pending = runner.create_pending(project_id)
    run = launcher.launch(project_id, pending.run_id)
    if rec["action"] == "stop" and _stop is not None:
        _stop(project_id, "metric %s" % metric_id)
    _ledger.append(
        {"outcome": "metric-fired", "metric_id": metric_id, "at": value}
    )
    _notify(project_id, "metric fired %s" % metric_id, refs=(run.run_id,))
    return run


def tick_due(now=None):
    """Fire every due timer, skipping paused projects without failing.

    Returns the runs that fired; paused timers are ledgered as tick-skip.
    """
    at = _now(now)
    fired = []
    for timer_id in sorted(_timers):
        rec = _timers[timer_id]
        if at < rec["next_due"]:
            continue
        if pause_flags.is_effective(rec["project_id"]):
            _ledger.append(
                {"outcome": "tick-skip", "timer_id": timer_id, "at": at}
            )
            continue
        run = fire_timer(timer_id, now=at)
        if run is not None:
            fired.append(run)
    return fired


def save_state(path):
    """Persist launchers, timers, metrics and the ledger as plain JSON."""
    payload = {
        "schema": 1,
        "launchers": [dict(row) for row in _launchers.values()],
        "timers": [dict(row) for row in _timers.values()],
        "metrics": [dict(row) for row in _metrics.values()],
        "ledger": [dict(entry) for entry in _ledger],
    }
    with open(path, "w", encoding="utf-8", newline="") as handle:
        json.dump(payload, handle, indent=2)
    return path


def load_state(path):
    """Restore state saved by save_state, replacing current state."""
    global _journal, _stop, _clock
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    hooks = (_journal, _stop, _clock)
    reset_state()
    for row in payload.get("launchers", []):
        _launchers[row["launcher_id"]] = dict(row)
    for row in payload.get("timers", []):
        _timers[row["timer_id"]] = dict(row)
    for row in payload.get("metrics", []):
        _metrics[row["metric_id"]] = dict(row)
    _ledger.extend(dict(entry) for entry in payload.get("ledger", []))
    _journal, _stop, _clock = hooks
