"""FXDEVRUN run record: the queryable rows behind every served run.

One record per (project) run lives on ``app.state.devrun_runs`` while
the stream runs and after it ends, keyed by run id (plus a project
alias holding the latest run for older readers). Ledger rows, audits,
parts, checks and the summary below are the new data fields HITS.md
lists; nothing here is invented (no record reads UNKNOWN at the edges).
"""

from __future__ import annotations

import collections.abc
import contextlib
import json
import os
import tempfile
import threading
from datetime import UTC, datetime
from typing import Any

# FXPARALLEL BEGIN run-lock: seq stays unique under part threads.
#: Guards the short len-then-append writes only; never held across a
#: model call, a child process or a file snapshot.
_RECORD_LOCK = threading.Lock()
# FXPARALLEL END run-lock.

#: Snapshot file name for devrun run records under the data dir
#: (file name only; the dir itself comes from app.state.data_dir).
DEVRUN_RUNS_FILE = "devrun_runs.jsonl"

#: Row status when no served cell exists (never a faked zero).
UNKNOWN = "UNKNOWN"


#: Max runs kept per project in state and on file (newest first).
MAX_RUNS_PER_PROJECT = 200


def _utcnow_iso() -> str:
    """Current UTC time as an ISO stamp (served start/end cells)."""
    return datetime.now(UTC).isoformat()


def _install_key(row: Any) -> tuple | None:
    """Dedupe key for one install record row, or None when malformed."""
    try:
        if not isinstance(row, dict):
            return None
        argv = tuple(str(word) for word in (row.get("argv") or []))
        if not argv:
            return None
        return (argv, int(row.get("exit", -1)))
    except Exception:
        return None


def record_install_run(record: Any, argv: Any, exit_code: Any) -> None:
    """Record one real installer run (exit 0 only) on the run record.

    Only genuinely executed installer-class calls land here, never
    model text and never refusals: the engine calls this after a real
    exit 0. Failed installs leave no record (their honest FAIL comes
    from the red checks). Never raises.
    """
    try:
        if not isinstance(record, dict):
            return
        if int(exit_code) != 0:
            return
        words = [str(word) for word in list(argv or [])]
        if not words:
            return
        rows = record.setdefault("install_runs", [])
        if not isinstance(rows, list):
            return
        row = {"argv": words, "exit": 0}
        if _install_key(row) not in {_install_key(item) for item in rows}:
            rows.append(row)
    except Exception:
        pass


def run_install_runs(record: Any) -> list[dict[str, Any]]:
    """Install rows recorded on this run (missing reads empty)."""
    try:
        if isinstance(record, dict):
            rows = record.get("install_runs", []) or []
            return [dict(row) for row in rows if isinstance(row, dict)]
    except Exception:
        pass
    return []


def prior_install_runs(app: Any, project_id: str) -> list[dict[str, Any]]:
    """Install rows from earlier runs of this project (deduped).

    Memory first, then the persisted run file: a rerun after an Allow
    sees what the app really installed, so its brief can say "do not
    install again, verify instead". Never raises.
    """
    seen: list[dict[str, Any]] = []
    keys: set = set()

    def _take(candidate: Any) -> None:
        try:
            if not isinstance(candidate, dict):
                return
            if str(candidate.get("project") or "") != str(project_id):
                return
            for rows in (candidate.get("install_runs", []) or [],
                         candidate.get("install_runs_prior", []) or []):
                for row in rows:
                    key = _install_key(row)
                    if key is None or key in keys:
                        continue
                    keys.add(key)
                    seen.append({"argv": list(key[0]), "exit": key[1]})
        except Exception:
            pass

    try:
        store = getattr(getattr(app, "state", None), "devrun_runs", None)
        for item in (store or {}).values():
            _take(item)
    except Exception:
        pass
    try:
        for item in load_devrun_runs(app).values():
            _take(item)
    except Exception:
        pass
    return seen


def prior_snapshot(record: Any) -> list[dict[str, Any]]:
    """The prior-run installs stashed on this run's record (deduped).

    A rerun snapshots its priors at run start, before its first
    publish overwrites the per-project persisted slot: later lookups
    in this run still see what earlier runs installed. Never raises.
    """
    try:
        if not isinstance(record, dict):
            return []
        out: list[dict[str, Any]] = []
        keys: set = set()
        for row in record.get("install_runs_prior", []) or []:
            key = _install_key(row)
            if key is None or key in keys:
                continue
            keys.add(key)
            out.append({"argv": list(key[0]), "exit": key[1]})
    except Exception:
        return []
    return out


def combined_evidence(record: Any) -> list[dict[str, Any]]:
    """This run's installs plus its stashed prior installs (deduped)."""
    merged: list[dict[str, Any]] = []
    keys: set = set()
    for row in run_install_runs(record) + prior_snapshot(record):
        key = _install_key(row)
        if key is None or key in keys:
            continue
        keys.add(key)
        merged.append({"argv": list(key[0]), "exit": key[1]})
    return merged


def install_evidence(app: Any, project_id: str,
                     record: Any) -> list[dict[str, Any]]:
    """This run's install rows plus earlier runs' rows (deduped)."""
    merged: list[dict[str, Any]] = []
    keys: set = set()
    for row in run_install_runs(record) + prior_install_runs(
            app, project_id):
        key = _install_key(row)
        if key is None or key in keys:
            continue
        keys.add(key)
        merged.append({"argv": list(key[0]), "exit": key[1]})
    return merged


def format_install_runs(rows: Any) -> list[str]:
    """One chat/audit line per install row: `$ argv -> exit N`."""
    lines: list[str] = []
    try:
        for row in rows or []:
            key = _install_key(row)
            if key is None:
                continue
            lines.append("$ %s -> exit %s" % (
                " ".join(key[0]), key[1]))
    except Exception:
        pass
    return lines


def new_run_record(
    run_id: str, project: str, task: str, folder: str,
    title: str = "", message: str = "",
) -> dict[str, Any]:
    """Blank record for one dev run; the engine fills it as it goes.

    ``title`` is the first 80 chars of the user task text (served so
    the UI shows it instead of a hash); ``message`` keeps the full
    user text for the next run's Director brief.
    """
    text = str(title) or str(message) or str(task)
    return {
        "run_id": str(run_id),
        "project": str(project),
        "task": str(task),
        "message": str(message),
        "title": text[:80],
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
    try:
        title = record.get("title")
        if not title:
            fallback = record.get("message") or record.get("task") or ""
            title = str(fallback)[:80]
        else:
            title = str(title)[:80]
    except Exception:
        title = ""
    return {
        "run_id": record.get("run_id"),
        "project": record.get("project"),
        "task": record.get("task"),
        "title": title,
        "folder": record.get("folder") or "",
        "start": record.get("started_at") or UNKNOWN,
        "end": record.get("ended_at") or UNKNOWN,
        "interrupted": bool(record.get("interrupted", False)),
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


def _run_sort_key(record: dict[str, Any]) -> str:
    """Newest-first order key: start stamp, then run id (never raises)."""
    try:
        stamp = str(record.get("started_at") or "")
    except Exception:
        stamp = ""
    try:
        run_id = str(record.get("run_id") or "")
    except Exception:
        run_id = ""
    return "%s\x00%s" % (stamp, run_id)


def _unique_run_records(store: Any) -> list[dict[str, Any]]:
    """Dedupe a store's values to one record per run id (never raises).

    The state holds run-id keys plus one project alias per project
    pointing at the latest record; both read the same object, so the
    dedupe is by run id (alias entries collapse onto their run).
    """
    try:
        values = list(store.values())
    except Exception:
        return []
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for record in values:
        if not isinstance(record, dict):
            continue
        try:
            run_id = str(record.get("run_id") or "")
        except Exception:
            continue
        if not run_id or run_id in seen:
            continue
        seen.add(run_id)
        out.append(record)
    return out


def prune_old_runs(store: Any, project: str) -> None:
    """Drop runs past the per-project cap, oldest first (never raises).

    Keeps the newest MAX_RUNS_PER_PROJECT records of one project plus
    its project alias on the latest; other projects stay untouched.
    """
    try:
        mine = [record for record in _unique_run_records(store)
                if str(record.get("project") or "") == str(project)]
        if len(mine) <= MAX_RUNS_PER_PROJECT:
            return
        mine.sort(key=_run_sort_key, reverse=True)
        drop = {str(record.get("run_id")) for record in
                mine[MAX_RUNS_PER_PROJECT:]}
        for key in list(store.keys()):
            try:
                record = store.get(key)
            except Exception:
                continue
            if isinstance(record, dict) and str(
                    record.get("run_id") or "") in drop:
                with contextlib.suppress(Exception):
                    del store[key]
        latest = mine[0]
        with contextlib.suppress(Exception):
            store[str(project)] = latest
    except Exception:
        pass


def latest_run_for_project(app: Any, project: str) -> Any:
    """Newest run record of one project, or None (never raises)."""
    try:
        memory = getattr(getattr(app, "state", None), "devrun_runs", None) or {}
        aliased = memory.get(str(project))
        if isinstance(aliased, dict) and str(
                aliased.get("project") or "") == str(project):
            return aliased
    except Exception:
        pass
    try:
        rows = runs_for_project(app, project)
    except Exception:
        return None
    if not rows:
        return None
    # Rows are newest-first dicts; map back to the stored record.
    newest_id = rows[0].get("run_id")
    try:
        memory = getattr(getattr(app, "state", None), "devrun_runs", None) or {}
        for record in _unique_run_records(memory):
            if str(record.get("run_id")) == str(newest_id):
                return record
    except Exception:
        pass
    return None


def persist_devrun_runs(app: Any) -> None:
    """Snapshot every known devrun record to the data dir.

    Merge-first: the file's rows plus the in-memory rows (memory wins
    per run id), so a fresh app after a restart never wipes the runs
    it has not loaded yet when its first run publishes. No-op when no
    store dir is bound or nothing is stored anywhere. Atomic temp-file
    + replace write, one JSON object per line, newest first per
    project, capped at MAX_RUNS_PER_PROJECT. Never raises:
    a persist failure must not break the running stream.
    """
    try:
        store_dir = _devrun_store_dir(app)
        if not store_dir:
            return
        merged: dict[str, dict[str, Any]] = {}
        try:
            path = os.path.join(store_dir, DEVRUN_RUNS_FILE)
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            for line in text.splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                if isinstance(row, dict) and row.get("project"):
                    try:
                        key = str(row.get("run_id") or row["project"])
                    except Exception:
                        continue
                    if key and key not in merged:
                        merged[key] = row
        except Exception:
            pass
        try:
            runs = getattr(getattr(app, "state", None),
                           "devrun_runs", None) or {}
            for record in _unique_run_records(runs):
                try:
                    key = str(record.get("run_id") or "")
                except Exception:
                    continue
                if key:
                    merged[key] = record
        except Exception:
            pass
        by_project: dict[str, list[dict[str, Any]]] = {}
        for record in merged.values():
            try:
                by_project.setdefault(
                    str(record.get("project") or ""), []).append(record)
            except Exception:
                continue
        rows: list[dict[str, Any]] = []
        for records_of_project in by_project.values():
            records_of_project.sort(key=_run_sort_key, reverse=True)
            rows.extend(records_of_project[:MAX_RUNS_PER_PROJECT])
        rows.sort(key=lambda row: (
            str(row.get("project") or ""), _run_sort_key(row)),
            reverse=True)
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
    """Read persisted devrun records, keyed by run id (missing: {}).

    Old one-row-per-project files still load: the key is the record's
    own run id (falling back to the project when a row has none), so
    one surviving row reads as that project's single run.
    """
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
                try:
                    key = str(row.get("run_id") or row["project"])
                except Exception:
                    continue
                if key and key not in out:
                    out[key] = row
    except Exception:
        return {}
    return out


def runs_for_project(app: Any, project: str) -> list:
    """Serve rows for one project: persisted file first, memory wins.

    Restart-safe: a fresh app with an empty memory store still serves
    the persisted records of its data dir. Newest first, capped at
    MAX_RUNS_PER_PROJECT per project.
    """
    merged = load_devrun_runs(app)
    try:
        memory = getattr(getattr(app, "state", None), "devrun_runs", None) or {}
        for record in _unique_run_records(memory):
            if str(record.get("project") or "") != str(project):
                continue
            try:
                key = str(record.get("run_id") or "")
            except Exception:
                continue
            if key:
                merged[key] = record
    except Exception:
        pass
    records = [record for record in merged.values()
               if isinstance(record, dict) and str(
                   record.get("project") or "") == str(project)]
    records.sort(key=_run_sort_key, reverse=True)
    records = records[:MAX_RUNS_PER_PROJECT]
    return [to_runs_row(record) for record in records]
