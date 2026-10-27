"""Lane B STEP2 run registry: runs are recorded, governed and pausable.

Every run is stored with its full history, journal notices go out on every
state move, and pause plus budget plus time guards are checked before acting.
Cancel keeps history and finalizes instead of erasing. State is plain JSON
so a restart can pick up where the previous process left off.
"""

import json
import sys
import time

from agent_si.automation import cleanup as cleanup_mod
from agent_si.automation import pause as pause_flags


#: Dotted name of the frozen automation contract module. Product code
#: keeps no static import of it; the module object is resolved late at
#: call time, so raised errors, returned rows and cross-lane calls are
#: the same objects the contract tests use.
_IFACE_MODULE = "agent_si.automation.interface"


def _auto_iface():
    """Return the frozen automation contract module object."""
    try:
        return sys.modules[_IFACE_MODULE]
    except KeyError:
        raise RuntimeError(
            "frozen contract %r is not imported" % (_IFACE_MODULE,)
        )

MODEL_ID = "meta/muse-spark-1.3-contributor"

_DEFAULT_RESUME_WINDOW_S = 3600.0

_templates = {}
_runs = {}
_histories = {}
_finals = {}
_next_seq = 0
_journal = None
_budget = None
_run_temp_base = None


def reset_state():
    """Clear templates, runs, histories, turns, counters and hooks."""
    global _next_seq, _journal, _budget, _run_temp_base
    _templates.clear()
    _runs.clear()
    _histories.clear()
    _finals.clear()
    _next_seq = 0
    _journal = None
    _budget = None
    _run_temp_base = None


def set_journal_hook(hook):
    """Set the journal notice hook (or None to silence notices)."""
    global _journal
    _journal = hook


def set_budget_hook(hook):
    """Set the budget guard hook (or None to allow every resume)."""
    global _budget
    _budget = hook


def register_template(template_id, project_id, name=""):
    """Store a template row that start_run can later instantiate."""
    _templates[template_id] = {
        "template_id": template_id,
        "project_id": project_id,
        "name": name,
        "version": 1,
    }
    return dict(_templates[template_id])


def _next_run_id():
    global _next_seq
    _next_seq += 1
    return "run-%04d" % _next_seq


def _record_to_run(rec):
    return _auto_iface().AutomationRun(
        run_id=rec["run_id"],
        project_id=rec["project_id"],
        template_id=rec.get("template_id") or "",
        trigger_id=rec.get("trigger_id"),
        state=rec["state"],
        started_at=str(rec.get("started_at", "")),
        updated_at=str(rec.get("updated_at", "")),
    )


def _notify(project_id, summary, refs=()):
    if _journal is not None:
        _journal(project_id, "runner", "AUTOMATION_RUN", summary, refs=refs)


def _get_record(project_id, run_id):
    rec = _runs.get(run_id)
    if rec is None or rec["project_id"] != project_id:
        raise _auto_iface().AutomationError(
            code="AUTOMATION_RUN_NOT_FOUND",
            detail="run %s unknown" % run_id,
        )
    return rec


def start_run(project_id, template_id, now=None, resume_window_s=None):
    """Start a recorded run; refused while the pause is effective."""
    if pause_flags.is_effective(project_id):
        raise _auto_iface().AutomationError(
            code="AUTOMATION_PAUSED",
            detail="automation paused for %s" % project_id,
        )
    tpl = _templates.get(template_id)
    if tpl is None or tpl["project_id"] != project_id:
        raise _auto_iface().AutomationError(
            code="TEMPLATE_NOT_FOUND",
            detail="template %s unknown" % template_id,
        )
    at = now if now is not None else time.time()
    window = resume_window_s if resume_window_s is not None else _DEFAULT_RESUME_WINDOW_S
    run_id = _next_run_id()
    _runs[run_id] = {
        "run_id": run_id,
        "project_id": project_id,
        "template_id": template_id,
        "trigger_id": None,
        "state": "RUNNING",
        "started_at": at,
        "updated_at": at,
        "resume_window_s": window,
        "turn_seq": 0,
        "open_turn": None,
        "pending_cancel": None,
    }
    _histories[run_id] = [{"event": "created", "at": at}]
    _finals.pop(run_id, None)
    _notify(project_id, "run started %s" % run_id, refs=(run_id,))
    return _record_to_run(_runs[run_id])


def create_pending(project_id, template_id="", trigger_id=None, now=None):
    """Queue a run without starting it; launch moves it to RUNNING."""
    at = now if now is not None else time.time()
    run_id = _next_run_id()
    _runs[run_id] = {
        "run_id": run_id,
        "project_id": project_id,
        "template_id": template_id or "",
        "trigger_id": trigger_id,
        "state": "PENDING",
        "started_at": at,
        "updated_at": at,
        "resume_window_s": _DEFAULT_RESUME_WINDOW_S,
        "turn_seq": 0,
        "open_turn": None,
        "pending_cancel": None,
    }
    _histories[run_id] = [{"event": "created", "at": at}]
    _finals.pop(run_id, None)
    return _record_to_run(_runs[run_id])


def activate_run(project_id, run_id, now=None):
    """Move a queued run to RUNNING and record the move."""
    rec = _get_record(project_id, run_id)
    at = now if now is not None else time.time()
    rec["state"] = "RUNNING"
    rec["updated_at"] = at
    _histories[run_id].append({"event": "activated", "at": at})
    _notify(project_id, "run active %s" % run_id, refs=(run_id,))
    return _record_to_run(rec)


def get_run(project_id, run_id):
    """Return the stored record for one run."""
    return _record_to_run(_get_record(project_id, run_id))


def list_runs(project_id):
    """Return every stored run for one project, oldest first."""
    return [_record_to_run(_runs[run_id]) for run_id in sorted(_runs) if _runs[run_id]["project_id"] == project_id]


def get_history(project_id, run_id):
    """Return the recorded event history for one run, oldest first."""
    _get_record(project_id, run_id)
    return [dict(entry) for entry in _histories.get(run_id, [])]


def get_finalization(project_id, run_id):
    """Return the finalization receipt for one run."""
    _get_record(project_id, run_id)
    final = _finals.get(run_id)
    if final is None:
        return {"reason": "", "finalized": False}
    return dict(final)


def set_run_temp_base(base):
    """Set the run-temp base override (None clears it to the default)."""
    global _run_temp_base
    _run_temp_base = base


def begin_turn(project_id, run_id, now=None):
    """Open a new turn on a running run and record the move."""
    rec = _get_record(project_id, run_id)
    at = now if now is not None else time.time()
    if rec["state"] != "RUNNING":
        raise _auto_iface().AutomationError(
            code="AUTOMATION_RUN_ACTIVE",
            detail="run %s is not running" % run_id,
        )
    if rec.get("open_turn") is not None:
        raise _auto_iface().AutomationError(
            code="AUTOMATION_RUN_ACTIVE",
            detail="run %s already has an open turn" % run_id,
        )
    turn = int(rec.get("turn_seq", 0)) + 1
    rec["turn_seq"] = turn
    rec["open_turn"] = {"turn": turn, "started_at": at}
    rec["updated_at"] = at
    _histories[run_id].append({"event": "turn-started:%d" % turn, "at": at})
    _notify(
        project_id,
        "run turn started %s #%d" % (run_id, turn),
        refs=(run_id,),
    )
    return {
        "run_id": run_id,
        "project_id": project_id,
        "turn": turn,
        "started_at": at,
    }


def complete_turn(project_id, run_id, now=None):
    """Complete the open turn; a flagged after-turn cancel stops the run."""
    rec = _get_record(project_id, run_id)
    at = now if now is not None else time.time()
    opened = rec.get("open_turn")
    if rec["state"] != "RUNNING" or opened is None:
        raise _auto_iface().AutomationError(
            code="AUTOMATION_RUN_ACTIVE",
            detail="run %s has no open turn" % run_id,
        )
    turn = opened["turn"]
    rec["open_turn"] = None
    rec["updated_at"] = at
    _histories[run_id].append({"event": "turn-completed:%d" % turn, "at": at})
    _notify(
        project_id,
        "run turn completed %s #%d" % (run_id, turn),
        refs=(run_id,),
    )
    pending = rec.get("pending_cancel")
    if pending is not None:
        rec["pending_cancel"] = None
        _mark_cancelled(project_id, rec, pending, at)
    return {
        "run_id": run_id,
        "project_id": project_id,
        "turn": turn,
        "completed_at": at,
        "state": rec["state"],
    }


def _mark_cancelled(project_id, rec, reason, at):
    """Stop a run at once: history is kept and the receipt is stored."""
    run_id = rec["run_id"]
    rec["state"] = "CANCELLED"
    rec["updated_at"] = at
    rec["pending_cancel"] = None
    event = "cancelled:%s" % reason if reason else "cancelled"
    _histories[run_id].append({"event": event, "at": at})
    _finals[run_id] = {"reason": reason, "finalized": True}
    _notify(project_id, "run cancelled %s" % run_id, refs=(run_id,))
    _clean_owned_temp(project_id, rec)


def _clean_owned_temp(project_id, rec):
    """Clean the run's own temp folder via the standard cleanup script.

    Cancel never breaks on cleanup: a refused or unusable folder only
    records a journal notice.
    """
    run_id = rec["run_id"]
    try:
        receipt = cleanup_mod.clean_run_temp(
            cleanup_mod.resolve_base(_run_temp_base), run_id
        )
    except Exception as exc:
        _notify(
            project_id,
            "run temp clean skipped %s: %s" % (run_id, exc),
            refs=(run_id,),
        )
        return None
    _notify(
        project_id,
        "run temp cleaned %s removed=%d" % (run_id, len(receipt["removed"])),
        refs=(run_id,),
    )
    return receipt


def cancel_run(project_id, run_id, reason="", now=None, mode="immediate"):
    """Cancel a run now (immediate, the default) or after the open turn.

    Immediate cancellation stops at once and leaves an open turn
    uncompleted. After-turn cancellation flags a run that has an open
    turn and stops it when that turn completes; with no open turn it
    stops at once. History is kept and the receipt is stored either way.

    Cancel is a lifecycle move, so it works even while paused.
    """
    if mode not in ("immediate", "after-turn"):
        raise ValueError("cancel mode is immediate or after-turn")
    rec = _get_record(project_id, run_id)
    at = now if now is not None else time.time()
    if (
        mode == "after-turn"
        and rec["state"] == "RUNNING"
        and rec.get("open_turn") is not None
    ):
        rec["pending_cancel"] = reason
        rec["updated_at"] = at
        event = (
            "cancel-requested:%s" % reason if reason else "cancel-requested"
        )
        _histories[run_id].append({"event": event, "at": at})
        _notify(
            project_id, "run cancel after turn %s" % run_id, refs=(run_id,)
        )
        return _record_to_run(rec)
    _mark_cancelled(project_id, rec, reason, at)
    return _record_to_run(rec)


def disk_check_runs(project_id, base=None):
    """Probe the run-temp base disk (free/total/ok) and record the move."""
    info = cleanup_mod.disk_check(
        cleanup_mod.resolve_base(base if base is not None else _run_temp_base)
    )
    _notify(
        project_id,
        "run temp disk %s free=%d total=%d ok=%s"
        % (info["path"], info["free"], info["total"], info["ok"]),
        refs=(),
    )
    return info


def cleanup_run_temp(project_id, run_id, base=None):
    """Remove files inside one run's own temp folder; record the move."""
    resolved = cleanup_mod.resolve_base(
        base if base is not None else _run_temp_base
    )
    cleanup_mod.run_dir_for(resolved, run_id)
    _get_record(project_id, run_id)
    receipt = cleanup_mod.clean_run_temp(resolved, run_id)
    _notify(
        project_id,
        "run temp cleaned %s removed=%d" % (run_id, len(receipt["removed"])),
        refs=(run_id,),
    )
    return receipt


def resume(project_id, run_id, now=None):
    """Resume a run within the budget guard and the resume time window."""
    rec = _get_record(project_id, run_id)
    if pause_flags.is_effective(project_id):
        raise _auto_iface().AutomationError(
            code="AUTOMATION_PAUSED",
            detail="automation paused for %s" % project_id,
        )
    if _budget is not None and not _budget(project_id):
        raise _auto_iface().AutomationError(
            code="AUTOMATION_PAUSED",
            detail="budget guard refused resume for %s" % project_id,
        )
    at = now if now is not None else time.time()
    window = rec.get("resume_window_s", _DEFAULT_RESUME_WINDOW_S)
    started = rec.get("started_at", at)
    if at - started > window:
        raise _auto_iface().AutomationError(
            code="AUTOMATION_PAUSED",
            detail="time guard refused resume: resume window elapsed",
        )
    rec["state"] = "RUNNING"
    rec["updated_at"] = at
    _histories[run_id].append({"event": "resumed", "at": at})
    _notify(project_id, "run resumed %s" % run_id, refs=(run_id,))
    return _record_to_run(rec)


def save_state(path):
    """Persist templates, runs, histories and receipts as plain JSON."""
    payload = {
        "schema": 1,
        "seq": _next_seq,
        "templates": [dict(row) for row in _templates.values()],
        "runs": [
            {
                "run_id": rec["run_id"],
                "project_id": rec["project_id"],
                "template_id": rec["template_id"],
                "trigger_id": rec["trigger_id"],
                "state": rec["state"],
                "started_at": rec["started_at"],
                "updated_at": rec["updated_at"],
                "resume_window_s": rec.get("resume_window_s", _DEFAULT_RESUME_WINDOW_S),
                "turn_seq": int(rec.get("turn_seq", 0)),
                "open_turn": dict(rec["open_turn"]) if rec.get("open_turn") else None,
                "pending_cancel": rec.get("pending_cancel"),
                "history": [dict(entry) for entry in _histories.get(run_id, [])],
                "finalization": dict(_finals[run_id]) if run_id in _finals else None,
            }
            for run_id, rec in sorted(_runs.items())
        ],
    }
    with open(path, "w", encoding="utf-8", newline="") as handle:
        json.dump(payload, handle, indent=2)
    return path


def load_state(path):
    """Restore state saved by save_state, replacing current state."""
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    reset_state()
    global _next_seq
    _next_seq = int(payload.get("seq", 0))
    for row in payload.get("templates", []):
        _templates[row["template_id"]] = dict(row)
    for row in payload.get("runs", []):
        run_id = row["run_id"]
        _runs[run_id] = {
            "run_id": run_id,
            "project_id": row["project_id"],
            "template_id": row.get("template_id") or "",
            "trigger_id": row.get("trigger_id"),
            "state": row["state"],
            "started_at": row.get("started_at", 0.0),
            "updated_at": row.get("updated_at", row.get("started_at", 0.0)),
            "resume_window_s": row.get("resume_window_s", _DEFAULT_RESUME_WINDOW_S),
            "turn_seq": int(row.get("turn_seq", 0)),
            "open_turn": dict(row["open_turn"]) if row.get("open_turn") else None,
            "pending_cancel": row.get("pending_cancel"),
        }
        _histories[run_id] = [dict(entry) for entry in row.get("history", [])]
        if row.get("finalization") is not None:
            _finals[run_id] = dict(row["finalization"])
