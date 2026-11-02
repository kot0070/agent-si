"""FXDEVRUN auditor: a NEW adapter instance and NEW message list.

The auditor judges the part goal, the diff of its files, and the
check commands with their real output; the agent conversation never
rides along. Malformed auditor JSON is FAIL, never a silent pass.
Verdicts persist through the NEW audit_coordinator method
``record_auditor_verdict``; a shared producer/auditor identity is
refused there.
"""

from __future__ import annotations

import difflib
import os
from typing import Any


def snapshot_files(folder: str, files: list[str]) -> dict[str, str | None]:
    """Read the current text of the part's files (None when missing).

    Binary files snapshot as a one-line marker (size plus sha256,
    never contents) so the diff lists them instead of reporting no
    changes; secret-class files stay None, never described.
    """
    from agent_si.runtime.devrun import actions as _actions

    snap: dict[str, str | None] = {}
    for path in files:
        try:
            snap[path] = _actions.read_file(folder, path)
        except _actions.ActionRefused as exc:
            if "binary" not in str(exc).lower():
                snap[path] = None
                continue
            try:
                snap[path] = _actions.describe_binary(folder, path)
            except Exception:
                snap[path] = None
        except Exception:
            snap[path] = None
    return snap


def diff_text(before: dict[str, str | None],
              after: dict[str, str | None]) -> str:
    """Unified diff of the part's files vs the attempt start."""
    chunks: list[str] = []
    for path in sorted(set(before) | set(after)):
        old = before.get(path)
        new = after.get(path)
        if old == new:
            continue
        old_lines = (old or "").splitlines(keepends=True)
        new_lines = (new or "").splitlines(keepends=True)
        chunks.append("".join(difflib.unified_diff(
            old_lines, new_lines,
            fromfile="a/%s" % (path,), tofile="b/%s" % (path,))))
    if not chunks:
        return "(no changes)"
    text = "\n".join(chunks)
    if len(text) > 12000:
        text = text[:12000] + "\n[... diff truncated ...]"
    return text


#: Workspace dirs never snapshotted (caches, history, the run's own
#: outputs, local virtualenvs): undeclared-file detection stays about
#: project work, never tool noise.
_WS_EXCLUDE_DIRS = frozenset({
    "node_modules", ".git", ".devrun", "__pycache__", ".venv",
})

#: Snapshot bounds: per-file bytes plus a file count, so a huge tree
#: cannot stall an attempt.
_WS_FILE_CAP = 256 * 1024
_WS_MAX_FILES = 2000


def _snapshot_one(folder: str, rel: str) -> str | None:
    """Text or binary marker for one workspace file; never contents."""
    from agent_si.runtime.devrun import actions as _actions

    try:
        return _actions.read_file(folder, rel)
    except _actions.ActionRefused as exc:
        if "binary" not in str(exc).lower():
            return None
        try:
            return _actions.describe_binary(folder, rel)
        except Exception:
            return None
    except Exception:
        return None


def snapshot_workspace(folder: str) -> dict[str, str | None]:
    """Map of workspace files to text/marker (declared and not).

    Walks the project folder, skipping the excluded dirs; each file
    snapshots exactly like a declared file (text capped, binaries as
    size+sha markers, unreadable as None). Never raises.
    """
    snap: dict[str, str | None] = {}
    try:
        base = os.path.abspath(str(folder))
    except Exception:
        return snap
    try:
        walker = os.walk(base)
    except Exception:
        return snap
    try:
        for root, dirs, files in walker:
            try:
                dirs[:] = [name for name in dirs
                           if name not in _WS_EXCLUDE_DIRS]
            except Exception:
                pass
            for name in sorted(files):
                if len(snap) >= _WS_MAX_FILES:
                    return snap
                try:
                    full = os.path.join(root, name)
                    rel = os.path.relpath(full, base).replace(
                        os.sep, "/")
                except Exception:
                    continue
                if not rel or rel.startswith(".."):
                    continue
                snap[rel] = _snapshot_one(folder, rel)
    except Exception:
        pass
    return snap


def diff_undeclared(before: dict[str, str | None],
                    after: dict[str, str | None],
                    declared: Any) -> tuple[str, list[str]]:
    """Diff of workspace files outside the declared set, labelled.

    Returns (text, changed paths): entries the part never declared
    are marked "(not in the part's files)" so the auditor judges
    them knowingly. A correct file written elsewhere shows up here
    instead of vanishing into "(no changes)"; a stray or deleted
    file is never invisible. Empty when nothing undeclared changed.
    """
    try:
        declared_set = {str(item) for item in (declared or [])}
    except Exception:
        declared_set = set()
    chunks: list[str] = []
    changed: list[str] = []
    try:
        paths = sorted(set(before) | set(after))
    except Exception:
        return "", []
    for path in paths:
        try:
            if path in declared_set:
                continue
            old = before.get(path)
            new = after.get(path)
            if old == new:
                continue
            changed.append(str(path))
            old_lines = (old or "").splitlines(keepends=True)
            new_lines = (new or "").splitlines(keepends=True)
            chunks.append("".join(difflib.unified_diff(
                old_lines, new_lines,
                fromfile="a/%s (not in the part's files)" % (path,),
                tofile="b/%s (not in the part's files)" % (path,))))
        except Exception:
            continue
    if not chunks:
        return "", changed
    text = "\n".join(chunks)
    if len(text) > 12000:
        text = text[:12000] + "\n[... diff truncated ...]"
    return text, changed


def auditor_messages(
    goal: str,
    files_diff: str,
    checks: list[dict[str, Any]],
    install_runs: Any = (),
    prior_install_runs: Any = (),
    part_diff: str = "",
) -> list[dict[str, str]]:
    """The auditor's NEW message list: goal, diff, checks with output.

    Installers the app ran carry their own evidence section, built
    only from the engine's real install record, never from model
    text: an empty diff with such a record is explained, without one
    it stays empty work. Installs already run for the project ride a
    second section (the rerun must verify, not reinstall).
    """
    from agent_si.runtime.devrun import records as _records

    lines = [
        "You are the auditor for one development part.",
        "Goal: %s" % (goal,),
        "Files (diff vs attempt start):",
        files_diff,
        "Files (whole part changes since part start):",
        part_diff if part_diff else "(no changes)",
        "Checks (command, exit code, real output tail):",
    ]
    if not checks:
        lines.append("(no check commands)")
    for check in checks:
        lines.append("$ %s" % (" ".join(check.get("argv", [])),))
        lines.append("exit: %s" % (check.get("exit_code"),))
        tail = str(check.get("output_tail") or "")
        lines.append(tail if tail else "(no output)")
    install_lines = _records.format_install_runs(install_runs)
    if install_lines:
        lines.append("Installers the app ran for this run:")
        lines.extend(install_lines)
    prior_lines = _records.format_install_runs(prior_install_runs)
    if prior_lines:
        lines.append("Installers already run for this project "
                     "(do not reinstall, verify instead):")
        lines.extend(prior_lines)
    lines.append(
        'Return ONLY JSON: {"result": "PASS"|"FAIL", '
        '"reasons": ["..."]}. Judge the real files and real outputs '
        "above, nothing else.")
    from agent_si.runtime.devrun import roles as _roles
    lines.append(_roles.reply_language_line())
    return [{"role": "user", "content": "\n".join(lines)}]


def fresh_coordinator() -> Any:
    """One fresh auditor coordinator (adds no behaviour)."""
    from agent_si.assurance import audit_coordinator as _ac

    class _FreshAuditor(_ac.AuditCoordinator):
        """Fresh auditor instance per part; adds no behavior."""

    return _FreshAuditor()


def judge(
    app: Any,
    coordinator: Any,
    adapter: Any,
    resolution: dict[str, Any],
    *,
    record: Any,
    project_id: str,
    run_id: str,
    task_id: str,
    part_id: str,
    attempt: int,
    producer_ref: str,
    auditor_ref: str,
    contract_hash: str,
    goal: str,
    files_diff: str,
    checks: list[dict[str, Any]],
    artifact_refs: list[str],
    part_diff: str = "",
    lock: Any = None,
    timeout_s: Any = None,
    stop_seen: Any = None,
    on_waiting: Any = None,
) -> dict[str, Any]:
    """Run one audit: invoke, parse, store; return the stored row.

    The audit call shares the bounded model timeout (a stall raises
    ModelTimeout to the caller); waiting notices and the stop hook
    ride the same parameters as any role call.
    """
    from agent_si.runtime.devrun import protocol as _protocol
    from agent_si.runtime.devrun import records as _install_records
    from agent_si.runtime.devrun import roles as _roles

    evidence = _install_records.run_install_runs(record)
    prior = _install_records.prior_snapshot(record)
    messages = auditor_messages(goal, files_diff, checks, evidence,
                                prior, part_diff=part_diff)
    # FXPARALLEL BEGIN charge-lock: auditor charges under the run lock.
    response, over, _row = _roles.invoke_owned(
        app, adapter, resolution, messages, record=record,
        project_id=project_id, run_id=run_id, part=part_id,
        attempt=attempt, lock=lock, timeout_s=timeout_s,
        stop_seen=stop_seen, on_waiting=on_waiting)
    # FXPARALLEL END charge-lock.
    entry: dict[str, Any] = {
        "part_id": str(part_id), "attempt": int(attempt),
        "producer_ref": str(producer_ref),
        "auditor_ref": str(auditor_ref),
        "result": "FAIL", "reasons": [], "over_cap": bool(over),
    }
    try:
        parsed = _protocol.parse_auditor_reply(response.output_text or "")
        entry["result"] = parsed["result"]
        entry["reasons"] = parsed["reasons"]
    except _protocol.AuditError as exc:
        entry["result"] = "FAIL"
        entry["reasons"] = ["auditor output malformed: %s" % (exc,)]
    stored = coordinator.record_auditor_verdict(
        project_id=str(project_id), task_id=str(task_id),
        run_id=str(run_id), part_id=str(part_id), attempt=int(attempt),
        producer_ref=str(producer_ref), auditor_ref=str(auditor_ref),
        result=str(entry["result"]), reasons=list(entry["reasons"]),
        artifact_refs=list(artifact_refs),
        evidence_refs=[str(check.get("output_file") or "")
                       for check in checks
                       if check.get("output_file")],
        contract_hash=str(contract_hash))
    entry["audit_id"] = stored.get("audit_id", "")
    entry["audit_session"] = stored.get("audit_session", "")
    return entry


def artifact_full_path(folder: str, rel: str) -> str:
    """Absolute path for one recorded relative artifact path."""
    return os.path.abspath(os.path.join(str(folder), *rel.split("/")))
