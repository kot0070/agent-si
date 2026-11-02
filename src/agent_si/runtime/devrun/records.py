"""FXDEVRUN run record: the queryable rows behind every served run.

One record per (project) run lives on ``app.state.devrun_runs`` while
the stream runs and after it ends. Ledger rows, audits, parts, checks
and the summary below are the new data fields HITS.md lists; nothing
here is invented (no record reads UNKNOWN at the edges).
"""

from __future__ import annotations

import collections.abc
import contextlib
import json
import os
import tempfile
from datetime import UTC, datetime
from typing import Any

#: Snapshot file name for devrun run records under the data dir
#: (file name only; the dir itself comes from app.state.data_dir).
DEVRUN_RUNS_FILE = "devrun_runs.jsonl"

#: Row status when no served cell exists (never a faked zero).
UNKNOWN = "UNKNOWN"


def _utcnow_iso() -> str:
    """Current UTC time as an ISO stamp (served start/end cells)."""
    return datetime.now(UTC).isoformat()


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
        "started_at": _utcnow_iso(),
        "ended_at": None,
        "plan": None,
        "parts": [],
        "ledger": [],
        "audits": [],
        "checks_started": [],
        "run_end": None,
        "files": [],
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
    return row


def part_add(
    record: dict[str, Any], *, part_id: str, goal: str
) -> dict[str, Any]:
    """Append one part row; return the row for in-place updates."""
    row: dict[str, Any] = {
        "part_id": str(part_id),
        "goal": str(goal),
        "verdict": "PENDING",
        "attempts": 0,
        "auto_why": {},
        "checks": [],
        "reason": "",
    }
    record.setdefault("parts", []).append(row)
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


def sync_files(record: dict[str, Any]) -> list[str]:
    """Merge written artifact paths into the record files list.

    The list is created when absent and never replaced: paths come
    only from what the engine already recorded in ``artifacts``.
    """
    files = record.get("files")
    if not isinstance(files, list):
        files = []
        record["files"] = files
    for entry in record.get("artifacts", []) or []:
        try:
            path = entry.get("path") if isinstance(entry, dict) else None
        except Exception:
            path = None
        if path and path not in files:
            files.append(str(path))
    return files


def mark_ended(record: dict[str, Any]) -> None:
    """Stamp the run end once; a repeat call keeps the first stamp."""
    try:
        if not record.get("ended_at"):
            record["ended_at"] = _utcnow_iso()
    except Exception:
        pass


def ledger_totals(record: dict[str, Any]) -> tuple:
    """Total tokens (int) and cost (str) from the record ledger.

    Either side reads UNKNOWN when no served cell exists: no ledger
    rows, no token integers, or any call without a price. Never a
    faked zero.
    """
    try:
        rows = record.get("ledger", []) if isinstance(record, dict) else []
    except Exception:
        rows = []
    total_in = 0
    total_out = 0
    served_tokens = False
    unknown_cost = not rows
    priced = None
    try:
        from decimal import Decimal as _Dec

        for row in rows or []:
            tokens = row.get("tokens") or {}
            for key, name in (("input", "in"), ("output", "out")):
                try:
                    value = tokens.get(key)
                except Exception:
                    value = None
                if isinstance(value, int) and not isinstance(value, bool):
                    served_tokens = True
                    if name == "in":
                        total_in += value
                    else:
                        total_out += value
            cost = row.get("cost")
            if cost is None or (isinstance(cost, str) and cost in (
                    UNKNOWN, "UNAVAILABLE")):
                unknown_cost = True
                continue
            try:
                amount = _Dec(str(cost))
            except Exception:
                unknown_cost = True
                continue
            priced = amount if priced is None else priced + amount
    except Exception:
        return UNKNOWN, UNKNOWN
    tokens = (total_in + total_out) if served_tokens else UNKNOWN
    cost = UNKNOWN if (unknown_cost or priced is None) else str(priced)
    return tokens, cost


def to_runs_row(record: dict[str, Any]) -> dict[str, Any]:
    """Serve one run record as a runs-ledger row (served cells only)."""
    parts = []
    verdicts: dict = {}
    for part in record.get("parts", []) or []:
        try:
            part_id = str(part.get("part_id"))
            verdict = part.get("verdict")
        except Exception:
            continue
        parts.append({
            "part_id": part_id,
            "verdict": verdict,
            "attempts": part.get("attempts", 0),
            "reason": part.get("reason", ""),
        })
        verdicts[part_id] = verdict
    tokens, cost = ledger_totals(record)
    try:
        files = list(record.get("files", []) or [])
    except Exception:
        files = []
    return {
        "run_id": record.get("run_id"),
        "project": record.get("project"),
        "task": record.get("task"),
        "start": record.get("started_at") or UNKNOWN,
        "end": record.get("ended_at") or UNKNOWN,
        "success": bool(record.get("success")),
        "stopped": bool(record.get("stopped")),
        "summary": record.get("summary") or "",
        "parts": parts,
        "verdicts": verdicts,
        "tokens": tokens,
        "cost": cost,
        "files": files,
    }


def _devrun_store_dir(app: Any) -> str:
    """Data dir bound on app.state (empty keeps runs in-memory only)."""
    state = getattr(app, "state", None)
    for name in ("data_dir", "k02r3_store_dir"):
        try:
            value = getattr(state, name, None)
        except Exception:
            value = None
        if value:
            return str(value)
    return ""


def persist_devrun_runs(app: Any) -> None:
    """Snapshot every in-memory devrun record to the data dir.

    No-op when no store dir is bound or nothing is stored. Atomic
    temp-file + replace write, one JSON object per line. Never raises:
    a persist failure must not break the running stream.
    """
    try:
        store_dir = _devrun_store_dir(app)
        if not store_dir:
            return
        runs = getattr(getattr(app, "state", None), "devrun_runs", None) or {}
        rows = [runs[key] for key in sorted(runs)
                if isinstance(runs.get(key), dict)]
        if not rows:
            return
        os.makedirs(store_dir, exist_ok=True)
        path = os.path.join(store_dir, DEVRUN_RUNS_FILE)
        fd, tmp_path = tempfile.mkstemp(
            dir=store_dir, prefix=".devrun-runs-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(
                        row, sort_keys=True, default=str) + "\n")
            os.replace(tmp_path, path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise
    except Exception:
        pass


def load_devrun_runs(app: Any) -> dict:
    """Read persisted devrun records, keyed by project (missing: {})."""
    try:
        store_dir = _devrun_store_dir(app)
        if not store_dir:
            return {}
        path = os.path.join(store_dir, DEVRUN_RUNS_FILE)
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except Exception:
        return {}
    out: dict = {}
    try:
        for line in text.splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if isinstance(row, dict) and row.get("project"):
                out[str(row["project"])] = row
    except Exception:
        return {}
    return out


def runs_for_project(app: Any, project: str) -> list:
    """Serve rows for one project: persisted file first, memory wins.

    Restart-safe: a fresh app with an empty memory store still serves
    the persisted records of its data dir.
    """
    merged = load_devrun_runs(app)
    try:
        memory = getattr(getattr(app, "state", None), "devrun_runs", None) or {}
        for key, record in memory.items():
            if isinstance(record, dict) and str(
                    record.get("project") or "") == str(project):
                merged[str(key)] = record
    except Exception:
        pass
    rows = [to_runs_row(record) for key, record in merged.items()
            if isinstance(record, dict) and str(
                record.get("project") or "") == str(project)]
    rows.sort(key=lambda row: str(row.get("run_id") or ""))
    return rows
