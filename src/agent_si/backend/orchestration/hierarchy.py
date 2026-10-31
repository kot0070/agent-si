"""Served hierarchy split/integrate (R-302, K02OPEN8; K02REST-A rows).

The Director splits one project into parts; the parts run; the Manager
integrates them. This module is the pure split/integrate step behind
POST /v1/split (wired in agent_si.backend.app.create_app): it validates
the request shape and returns the served payload verbatim, with no I/O,
no secrets and no sandbox paths. Optional split fields stage governance
rows to the hierarchy, select a staged requirement subset, keep
governance raw reads Director-only, persist hierarchy settings changes
as decision rows, and decompose tasks up to a parallel cap with the
rest queued; integrate reports whether the phase closed after PASS.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

SPLIT_BAD_REQUEST = "SPLIT_BAD_REQUEST"
INTEGRATED_BY = "manager"
PART_STATUS_SPLIT = "split"
DIRECTOR_ACTOR = "director"
DECISION_SCOPE_SETTINGS = "hierarchy:settings"
PHASE_CLOSED = "closed"
PHASE_OPEN = "open"

_DECISIONS: list[dict[str, str]] = []
_SEQ = 0


def _reset_state() -> None:
    """Clear module state (test helper; never a product path)."""
    global _SEQ
    _DECISIONS.clear()
    _SEQ = 0


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _compact(text: str) -> str:
    return " ".join(
        "".join(char if char.isascii() and not char.isspace() else " "
                if char.isspace() else "-" for char in text).split()
    )


def _stage_rows(rows: object) -> list[dict[str, str]]:
    """Stage governance rows to the hierarchy, returning row refs."""
    if not isinstance(rows, list) or not rows:
        raise SplitRefused("staged_rows must be a non-empty list")
    staged: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise SplitRefused("each staged row must be a {row_id} mapping")
        row_id = row.get("row_id")
        if not isinstance(row_id, str) or not row_id.strip():
            raise SplitRefused("each staged row needs a non-empty row_id")
        clean = row_id.strip()
        staged.append({"row_id": clean,
                       "hierarchy_ref": f"ARTIFACT_REF:{clean}/hierarchy"})
    return staged


def _requirement_subset(requirements: object, inputs: object) -> list[str]:
    """Select the staged requirement subset named by the inputs folder."""
    if not isinstance(requirements, list) or not requirements:
        raise SplitRefused("requirements must be a non-empty list")
    if not isinstance(inputs, list) or not inputs:
        raise SplitRefused("inputs must be a non-empty list")
    known: set[str] = set()
    for req in requirements:
        if not isinstance(req, dict):
            raise SplitRefused("each requirement must be an {id} mapping")
        req_id = req.get("id")
        if not isinstance(req_id, str) or not req_id.strip():
            raise SplitRefused("each requirement needs a non-empty id")
        known.add(req_id.strip())
    subset: list[str] = []
    for name in inputs:
        if not isinstance(name, str) or not name.strip():
            raise SplitRefused("each input needs a non-empty id")
        if name.strip() in known:
            subset.append(name.strip())
    return subset


def _governed_stage(task: dict[str, Any]) -> dict[str, str]:
    """Stage one governance raw read; Director-only, refused otherwise."""
    actor = task.get("actor")
    if actor != DIRECTOR_ACTOR:
        raise SplitRefused("governance raw reads are Director-only")
    governance = task.get("governance")
    if not isinstance(governance, dict):
        raise SplitRefused("governance must be a {raw} mapping")
    raw = governance.get("raw")
    if not isinstance(raw, str) or not raw.strip():
        raise SplitRefused("governance raw read needs a non-empty raw row")
    clean = raw.strip()
    return {"row_id": clean,
            "hierarchy_ref": f"ARTIFACT_REF:{clean}/hierarchy"}


def _record_settings_decision(settings: object, actor: object) -> dict[str, str]:
    """Persist one hierarchy settings change as a decision row."""
    global _SEQ
    if not isinstance(settings, dict) or not settings:
        raise SplitRefused("settings must be a non-empty mapping")
    keys = sorted(_compact(str(key)) for key in settings)
    if not all(keys):
        raise SplitRefused("settings keys must be non-empty strings")
    authority = actor if isinstance(actor, str) and actor.strip() \
        else INTEGRATED_BY
    _SEQ += 1
    row = {
        "decision_id": f"hierarchy-decision-{_SEQ:04d}",
        "scope": DECISION_SCOPE_SETTINGS,
        "statement": f"hierarchy settings change: {', '.join(keys)}",
        "reason": "hierarchy settings change recorded",
        "authority": authority.strip(),
        "created_at": _utc_now(),
    }
    _DECISIONS.append(row)
    return dict(row)


def _decompose(tasks: object, cap: object) -> tuple[list[str], list[str]]:
    """Split tasks into parallel (largest first, up to cap) and queued."""
    if not isinstance(tasks, list) or not tasks:
        raise SplitRefused("tasks must be a non-empty list")
    if isinstance(cap, bool) or not isinstance(cap, int) or cap < 1:
        raise SplitRefused("cap must be a positive integer")
    sized: list[tuple[str, float, int]] = []
    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            raise SplitRefused("each task must be an {id, size} mapping")
        task_id = task.get("id")
        size = task.get("size")
        if not isinstance(task_id, str) or not task_id.strip():
            raise SplitRefused("each task needs a non-empty id")
        if isinstance(size, bool) or not isinstance(size, (int, float)):
            raise SplitRefused("each task needs a numeric size")
        sized.append((task_id.strip(), float(size), index))
    ordered = sorted(sized, key=lambda item: (-item[1], item[2]))
    parallel = [task_id for task_id, _, _ in ordered[:cap]]
    queued = [task_id for task_id, _, _ in ordered[cap:]]
    return parallel, queued


class SplitRefused(ValueError):
    """Refused split request; the served route maps this to a 400."""


class IntegrateRefused(ValueError):
    """Refused integrate request; the served route maps this to a 400."""

INTEGRATE_BAD_REQUEST = "INTEGRATE_BAD_REQUEST"
INTEGRATED_STATUS = "integrated"


def split_project(project_id: object, parts: object) -> dict[str, Any]:
    """Split a project into parts and record the manager integration.

    Returns {parts: [{id, status}], integration: {by: "manager", parts: n}}
    where every part carries status "split". Raises SplitRefused on a
    missing project_id, an empty part list, a part without an id/kind,
    or a duplicated part id.
    """
    if not isinstance(project_id, str) or not project_id.strip():
        raise SplitRefused("project_id must be a non-empty string")
    if not isinstance(parts, list) or not parts:
        raise SplitRefused("parts must be a non-empty list")
    seen: set[str] = set()
    served: list[dict[str, str]] = []
    for part in parts:
        if not isinstance(part, dict):
            raise SplitRefused("each part must be an {id, kind} mapping")
        part_id = part.get("id")
        kind = part.get("kind")
        if not isinstance(part_id, str) or not part_id.strip():
            raise SplitRefused("each part must carry a non-empty id")
        if not isinstance(kind, str) or not kind.strip():
            raise SplitRefused("each part must carry a non-empty kind")
        if part_id in seen:
            raise SplitRefused(f"duplicated part id: {part_id}")
        seen.add(part_id)
        served.append({"id": part_id, "status": PART_STATUS_SPLIT})
    return {
        "parts": served,
        "integration": {"by": INTEGRATED_BY, "parts": len(served)},
    }


def split(task: object) -> dict[str, Any]:
    """Serve one Director split request: {project_id, parts} -> split payload.

    Thin Director entry over split_project: checks the request shape,
    then returns {parts, integration} plus any requested hierarchy rows:
    staged (M-P2-80), requirement_subset (M-P2-82), governed (M-R-GOV,
    Director-only), decision (row 103), parallel/queued (row 32).
    Raises SplitRefused on a missing project_id, an empty part list, a
    part without an id/kind, a duplicated part id, or a malformed
    optional field.
    """
    if not isinstance(task, dict):
        raise SplitRefused("task must be a {project_id, parts} mapping")
    served = split_project(task.get("project_id"), task.get("parts"))
    if task.get("staged_rows") is not None:
        served["staged"] = _stage_rows(task.get("staged_rows"))
    if task.get("requirements") is not None or task.get("inputs") is not None:
        served["requirement_subset"] = _requirement_subset(
            task.get("requirements"), task.get("inputs"))
    if task.get("governance") is not None:
        served["governed"] = _governed_stage(task)
    if task.get("settings") is not None:
        served["decision"] = _record_settings_decision(
            task.get("settings"), task.get("actor"))
    if task.get("tasks") is not None:
        parallel, queued = _decompose(task.get("tasks"), task.get("cap"))
        served["parallel"] = parallel
        served["queued"] = queued
    return served


def integrate(parts: object, project_id: object = None) -> dict[str, Any]:
    """Serve one Manager integration: split parts -> integrated result.

    Returns {project_id, parts: [{id, status: "integrated"}],
    integration: {by: "manager", parts: n}, phase}. The Manager always
    assembles; the phase closes only after every part verdict is PASS
    (row 95), staying open otherwise. Raises IntegrateRefused on
    a missing project_id, an empty part list, a part without an id, or
    a duplicated part id.
    """
    if not isinstance(project_id, str) or not project_id.strip():
        raise IntegrateRefused("project_id must be a non-empty string")
    if not isinstance(parts, list) or not parts:
        raise IntegrateRefused("parts must be a non-empty list")
    seen: set[str] = set()
    served: list[dict[str, str]] = []
    for part in parts:
        if not isinstance(part, dict):
            raise IntegrateRefused("each part must be an {id} mapping")
        part_id = part.get("id")
        if not isinstance(part_id, str) or not part_id.strip():
            raise IntegrateRefused("each part must carry a non-empty id")
        if part_id in seen:
            raise IntegrateRefused(f"duplicated part id: {part_id}")
        seen.add(part_id)
        served.append({"id": part_id, "status": INTEGRATED_STATUS})
    if all(isinstance(part, dict) and part.get("verdict") == "PASS"
           for part in parts):
        phase = PHASE_CLOSED
    else:
        phase = PHASE_OPEN
    return {
        "project_id": project_id,
        "parts": served,
        "integration": {"by": INTEGRATED_BY, "parts": len(served)},
        "phase": phase,
    }


class SnapshotError(ValueError):
    """Refused project snapshot write/read; served route maps this to 400."""


class SnapshotMissing(SnapshotError):
    """No snapshot stored for the project; served route maps this to 404."""


_SNAPSHOT_SUFFIX = ".snapshot.json"
_SNAPSHOT_DIGEST_LEN = 32


def _snapshot_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _clean_snapshot_args(
    store_dir: object, project_id: object
) -> tuple[str, str]:
    """Validate the caller-supplied store dir and project id."""
    if not isinstance(store_dir, str) or not store_dir.strip():
        raise SnapshotError("store_dir must be a non-empty string")
    if not isinstance(project_id, str) or not project_id.strip():
        raise SnapshotError("project_id must be a non-empty string")
    clean_dir = store_dir.strip()
    if not os.path.isdir(clean_dir):
        raise SnapshotError("store_dir is not a readable directory")
    return clean_dir, project_id.strip()


def _snapshot_file(clean_dir: str, clean_project: str) -> str:
    """Snapshot file name: sha256 hex so ids can never traverse paths."""
    digest = sha256(clean_project.encode("utf-8")).hexdigest()[
        :_SNAPSHOT_DIGEST_LEN
    ]
    return os.path.join(
        clean_dir,
        f"project-{digest}{_SNAPSHOT_SUFFIX}",
    )


def save_project_snapshot(
    store_dir: object, project_id: object, snapshot: object
) -> dict[str, Any]:
    """Write one created project snapshot to disk under the caller dir.

    Hot-write: the payload lands in a temp file in the same dir and is
    then moved over the target with os.replace, so a restart reads back
    exactly what was written. Raises SnapshotError on a bad dir, id,
    or snapshot (served as HTTP 400). Success returns {saved, project_id,
    file, saved_at}.
    """
    clean_dir, clean_project = _clean_snapshot_args(store_dir, project_id)
    if not isinstance(snapshot, dict):
        raise SnapshotError("snapshot must be a JSON object mapping")
    try:
        encoded = json.dumps(snapshot)
    except (TypeError, ValueError) as err:
        raise SnapshotError(
            f"snapshot is not JSON-serializable: {err}"
        ) from None
    payload = {
        "project_id": clean_project,
        "snapshot": json.loads(encoded),
        "saved_at": _snapshot_now(),
    }
    target = _snapshot_file(clean_dir, clean_project)
    try:
        fd, tmp = tempfile.mkstemp(
            dir=clean_dir, prefix=".snapshot-", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, sort_keys=True))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, target)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise
    except SnapshotError:
        raise
    except OSError as err:
        raise SnapshotError(
            f"snapshot write refused: {err}"
        ) from None
    return {
        "saved": True,
        "project_id": clean_project,
        "file": target,
        "saved_at": payload["saved_at"],
    }


def load_project_snapshot(
    store_dir: object, project_id: object
) -> dict[str, Any]:
    """Read one created project snapshot back from disk.

    Raises SnapshotMissing when no snapshot is stored for the id (served
    as HTTP 404) and SnapshotError on a bad dir, id, or unreadable
    payload (served as HTTP 400). Success returns {project_id, snapshot,
    saved_at}.
    """
    clean_dir, clean_project = _clean_snapshot_args(store_dir, project_id)
    target = _snapshot_file(clean_dir, clean_project)
    if not os.path.isfile(target):
        raise SnapshotMissing(
            f"no snapshot stored for project {clean_project!r}"
        )
    try:
        with open(target, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError) as err:
        raise SnapshotError(
            f"snapshot read refused: {err}"
        ) from None
    if (
        not isinstance(payload, dict)
        or payload.get("project_id") != clean_project
        or not isinstance(payload.get("snapshot"), dict)
        or not isinstance(payload.get("saved_at"), str)
    ):
        raise SnapshotError("snapshot payload malformed")
    return {
        "project_id": clean_project,
        "snapshot": payload["snapshot"],
        "saved_at": payload["saved_at"],
    }
