"""FXAUTO DO executor (lane-internal): what a fired rule really does.

Weak actions run at once: ``checkpoint`` writes a real checkpoint row,
``notify`` emits a real journal notice, ``reread-context`` reloads the
keeper register plus checkpoints from disk and reports the counts.
Strong actions never run here: rules open an approval first and
:func:`execute_approved` runs only after the user approves. Approved
``pause-project`` pauses for real; approved start-next-task, switch-model
and run-audit have no in-process executor, so they are recorded as
journaled, governed runs (never a faked audit, task or model switch).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from typing import Any, Dict, Optional

from agent_si.automation import pause as pause_flags

_WEAK = ("reread-context", "checkpoint", "notify")

_STRONG = (
    "pause-project",
    "start-next-task",
    "switch-model",
    "run-audit",
)

#: Plain approval sentences per strong action (UI localizes the frame).
_STRONG_NEEDS = {
    "pause-project": "pausing the project",
    "start-next-task": "starting the next task",
    "switch-model": "switching the model",
    "run-audit": "running an audit",
}


def _journal(ctx: Dict[str, Any], project_id: str, summary: str,
             refs: tuple = ()) -> None:
    hook = ctx.get("journal")
    if hook is not None:
        hook(project_id, "actions", "AUTOMATION_RUN", summary, refs=refs)


def _rule_hash(rule: Dict[str, Any]) -> str:
    material = json.dumps(
        {
            "rule_id": rule["rule_id"],
            "when_kind": rule["when_kind"],
            "when_detail": rule["when_detail"],
            "if_text": rule.get("if_text", ""),
            "do": rule["do"],
        },
        sort_keys=True,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def do_checkpoint(
    rule: Dict[str, Any], run: Dict[str, Any], ctx: Dict[str, Any]
) -> Dict[str, Any]:
    """Write a real checkpoint row for a fired rule."""
    store = ctx.get("checkpoints")
    if store is None:
        raise ValueError("checkpoint store is not bound")
    record = store.write_checkpoint(
        project_id=rule["project_id"],
        task_id=rule["rule_id"],
        run_id=run.get("run_id"),
        contract_hash=_rule_hash(rule),
        context_refs=(
            "rule:%s" % rule["rule_id"],
            "run:%s" % run.get("run_id", ""),
        ),
    )
    _journal(ctx, rule["project_id"],
             "checkpoint %s for rule %s" % (
                 record.checkpoint_id, rule["name"]),
             refs=(run.get("run_id", ""),))
    return {
        "done": True,
        "outcome": "checkpoint",
        "result": {
            "key": "fxauto.results.checkpoint",
            "params": {
                "name": rule["name"],
                "id": record.checkpoint_id,
            },
        },
    }


def do_notify(
    rule: Dict[str, Any], run: Dict[str, Any], ctx: Dict[str, Any]
) -> Dict[str, Any]:
    """Emit a real journal notice for a fired rule."""
    _journal(ctx, rule["project_id"],
             "rule %s fired (%s)" % (rule["name"], rule["do"]),
             refs=(run.get("run_id", ""),))
    return {
        "done": True,
        "outcome": "notified",
        "result": {
            "key": "fxauto.results.notified",
            "params": {"name": rule["name"]},
        },
    }


def _count_rows(path: str) -> Optional[int]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            rows = json.load(handle)
    except (FileNotFoundError, ValueError, OSError):
        return None
    return len(rows) if isinstance(rows, list) else None


def do_reread(
    rule: Dict[str, Any], run: Dict[str, Any], ctx: Dict[str, Any]
) -> Dict[str, Any]:
    """Re-read keeper state from disk and report what came back."""
    keeper_dir = ctx.get("keeper_dir")
    requirements = register_rows = checkpoint_rows = None
    if keeper_dir is not None:
        from agent_si.context_keeper import checkpoints as ckpt_home
        from agent_si.context_keeper import register as register_home

        register_home.Register(store_dir=str(keeper_dir))
        ckpt_home.Checkpoints(store_dir=str(keeper_dir))
        register_rows = _count_rows(
            os.path.join(str(keeper_dir), "register_rows.json"))
        checkpoint_rows = _count_rows(
            os.path.join(str(keeper_dir), "checkpoints.json"))
        requirements = register_rows
    _journal(ctx, rule["project_id"],
             "context re-read for rule %s" % rule["name"],
             refs=(run.get("run_id", ""),))
    return {
        "done": True,
        "outcome": "reread",
        "result": {
            "key": "fxauto.results.reread",
            "params": {
                "name": rule["name"],
                "register": -1 if register_rows is None
                else register_rows,
                "checkpoints": -1 if checkpoint_rows is None
                else checkpoint_rows,
            },
        },
    }


def do_action(
    rule: Dict[str, Any], run: Dict[str, Any], ctx: Dict[str, Any]
) -> Dict[str, Any]:
    """Execute a weak DO action; strong actions are never executed here."""
    if pause_flags.is_effective(rule["project_id"]):
        from agent_si.automation import rules as rules_home

        raise rules_home._auto_iface().AutomationError(
            code="AUTOMATION_PAUSED",
            detail="automation paused for %s" % rule["project_id"],
        )
    if rule["do"] == "checkpoint":
        return do_checkpoint(rule, run, ctx)
    if rule["do"] == "notify":
        return do_notify(rule, run, ctx)
    if rule["do"] == "reread-context":
        return do_reread(rule, run, ctx)
    raise ValueError(
        "strong action %r needs an approval first" % (rule["do"],))


def execute_approved(
    rule: Dict[str, Any], run: Dict[str, Any], ctx: Dict[str, Any]
) -> Dict[str, Any]:
    """Run an approved strong action: pause for real, the rest recorded."""
    if rule["do"] == "pause-project":
        pause_flags.set_project(rule["project_id"], True)
        _journal(ctx, rule["project_id"],
                 "project paused by rule %s" % rule["name"],
                 refs=(run.get("run_id", ""),))
        return {
            "done": True,
            "outcome": "paused",
            "result": {
                "key": "fxauto.results.paused",
                "params": {
                    "name": rule["name"],
                    "project": rule["project_id"],
                },
            },
        }
    _journal(ctx, rule["project_id"],
             "approved action recorded: %s for rule %s "
             "(no in-process executor; handed to the owning lane)" % (
                 rule["do"], rule["name"]),
             refs=(run.get("run_id", ""),))
    return {
        "done": True,
        "outcome": "recorded",
        "result": {
            "key": "fxauto.results.approvedRecorded",
            "params": {"name": rule["name"], "action": rule["do"]},
        },
    }
