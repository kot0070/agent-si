"""FXDEVRUN run record: the queryable rows behind every served run.

One record per (project) run lives on ``app.state.devrun_runs`` while
the stream runs and after it ends. Ledger rows, audits, parts, checks
and the summary below are the new data fields HITS.md lists; nothing
here is invented (no record reads UNKNOWN at the edges).
"""

from __future__ import annotations

import collections.abc
import threading
from typing import Any

# FXPARALLEL BEGIN run-lock: seq stays unique under part threads.
#: Guards the short len-then-append writes only; never held across a
#: model call, a child process or a file snapshot.
_RECORD_LOCK = threading.Lock()
# FXPARALLEL END run-lock.


def new_run_record(
    run_id: str, project: str, task: str, folder: str
) -> dict[str, Any]:
    """Blank record for one dev run; the engine fills it as it goes."""
    return {
        "run_id": str(run_id),
        "project": str(project),
        "task": str(task),
        "folder": str(folder),
        "success": False,
        "stopped": False,
        "summary": "",
        "plan": None,
        "parts": [],
        "ledger": [],
        "audits": [],
        "checks_started": [],
        "run_end": None,
    }


def ledger_add(
    record: dict[str, Any],
    *,
    role: str,
    provider: str,
    model: str,
    part: Any = None,
    attempt: int = 0,
    usage: Any = None,
    cost: Any = None,
) -> dict[str, Any]:
    """Append one ledger row for one model call; return the row."""
    tokens = {"input": None, "output": None}
    if isinstance(usage, collections.abc.Mapping):
        for key, name in (("input_tokens", "input"),
                          ("prompt_tokens", "input"),
                          ("output_tokens", "output"),
                          ("completion_tokens", "output")):
            value = usage.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                tokens[name] = value
    # FXPARALLEL BEGIN run-lock: seq taken and appended as one unit.
    with _RECORD_LOCK:
        row = {
            "seq": len(record.get("ledger", [])) + 1,
            "role": str(role),
            "provider": str(provider),
            "model": str(model),
            "part": None if part is None else str(part),
            "attempt": int(attempt),
            "tokens": tokens,
            "cost": "UNKNOWN" if cost is None else str(cost),
        }
        record.setdefault("ledger", []).append(row)
    # FXPARALLEL END run-lock.
    return row


def part_add(
    record: dict[str, Any], *, part_id: str, goal: str
) -> dict[str, Any]:
    """Append one part row; return the row for in-place updates."""
    # FXPARALLEL BEGIN run-lock: timed part rows for overlap proof.
    with _RECORD_LOCK:
        row: dict[str, Any] = {
            "part_id": str(part_id),
            "goal": str(goal),
            "verdict": "PENDING",
            "attempts": 0,
            "auto_why": {},
            "checks": [],
            "reason": "",
            "started_at": None,
            "finished_at": None,
        }
        record.setdefault("parts", []).append(row)
    # FXPARALLEL END run-lock.
    return row


def format_summary(record: dict[str, Any]) -> str:
    """Short human run summary; never claims success on a mixed run."""
    parts = record.get("parts", []) or []
    if record.get("stopped"):
        return "run stopped: %s" % (record.get("summary") or "user stop")
    failed = [part for part in parts
              if part.get("verdict") != "PASS"]
    if not parts:
        return "run failed: no parts ran"
    if failed:
        bits = []
        for part in failed:
            reason = str(part.get("reason") or part.get("verdict"))
            bits.append("part %s %s (%s)" % (
                part.get("part_id"), part.get("verdict"), reason))
        return "run failed: %s" % ("; ".join(bits),)
    return "run success: all %d parts PASS" % (len(parts),)
