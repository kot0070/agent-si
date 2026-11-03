"""Lane B STEP2 trigger registry: named triggers that start recorded runs.

Firing checks the pause first, then records a run through the run registry
and sends a journal notice. Definitions persist as plain JSON across restarts.
"""

import json
import sys

from agent_si.automation import pause as pause_flags
from agent_si.automation import runner
from agent_si.automation import scheduler as scheduler_lane


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

_triggers = {}
_journal = None


def reset_state():
    """Clear trigger definitions and the journal hook."""
    global _journal
    _triggers.clear()
    _journal = None


def set_journal_hook(hook):
    """Set the journal notice hook (or None to silence notices)."""
    global _journal
    _journal = hook


def register_trigger(trigger_id, project_id, kind="TIMER", schedule_ref="", enabled=True):
    """Store a trigger definition that fire_trigger can later fire."""
    _triggers[trigger_id] = {
        "trigger_id": trigger_id,
        "project_id": project_id,
        "kind": kind,
        "schedule_ref": schedule_ref,
        "enabled": enabled,
    }
    return dict(_triggers[trigger_id])


def get_trigger(project_id, trigger_id):
    """Return the stored definition for one trigger."""
    rec = _triggers.get(trigger_id)
    if rec is None or rec["project_id"] != project_id:
        raise _auto_iface().AutomationError(
            code="TRIGGER_NOT_FOUND",
            detail="trigger %s unknown" % trigger_id,
        )
    return dict(rec)


def list_triggers(project_id):
    """Return every stored trigger definition for one project."""
    return [
        dict(rec)
        for trigger_id, rec in sorted(_triggers.items())
        if rec.get("project_id") == project_id
    ]


def _fire_bound(project_id, rec):
    """Fire through the scheduler ledger path; None when unbound/not due."""
    kind = rec.get("kind") or ""
    ref = rec.get("schedule_ref") or ""
    if not ref:
        return None
    try:
        if kind == "TIMER":
            try:
                scheduler_lane.get_timer(ref)
            except _auto_iface().AutomationError as err:
                if err.code == "TRIGGER_NOT_FOUND":
                    return None
                raise
            return scheduler_lane.fire_timer(ref)
        if kind == "METRIC":
            # A manual fire asserts the condition now: a reading forced
            # above any finite threshold, so the metric action records.
            return scheduler_lane.evaluate_metric(ref, float("inf"))
        if kind == "LAUNCHER":
            return scheduler_lane.fire_launcher(ref)
    except _auto_iface().AutomationError as err:
        if err.code == "TRIGGER_NOT_FOUND":
            return None
        raise
    return None


def fire_trigger(project_id, trigger_id):
    """Fire a trigger into a recorded run; refused while paused.

    Triggers bound to a scheduler row (TIMER/METRIC/LAUNCHER with a
    schedule_ref) fire through the scheduler path so the action lands in
    the ledger; anything unbound (or not due) falls back to the direct
    recorded path, never a silent drop.
    """
    rec = _triggers.get(trigger_id)
    if rec is None or rec["project_id"] != project_id:
        raise _auto_iface().AutomationError(
            code="TRIGGER_NOT_FOUND",
            detail="trigger %s unknown" % trigger_id,
        )
    if pause_flags.is_effective(project_id):
        raise _auto_iface().AutomationError(
            code="AUTOMATION_PAUSED",
            detail="automation paused for %s" % project_id,
        )
    bound = _fire_bound(project_id, rec)
    if bound is not None:
        return bound
    pending = runner.create_pending(project_id, trigger_id=trigger_id)
    run = runner.activate_run(project_id, pending.run_id)
    if _journal is not None:
        _journal(
            project_id,
            "triggers",
            "AUTOMATION_RUN",
            "trigger fired %s" % trigger_id,
            refs=(run.run_id,),
        )
    return run


def save_state(path):
    """Persist trigger definitions as plain JSON."""
    payload = {"schema": 1, "triggers": [dict(row) for row in _triggers.values()]}
    with open(path, "w", encoding="utf-8", newline="") as handle:
        json.dump(payload, handle, indent=2)
    return path


def load_state(path):
    """Restore trigger definitions saved by save_state."""
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    reset_state()
    for row in payload.get("triggers", []):
        _triggers[row["trigger_id"]] = dict(row)
