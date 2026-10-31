"""Served hierarchy split/integrate (R-302, K02OPEN8).

The Director splits one project into parts; the parts run; the Manager
integrates them. This module is the pure split/integrate step behind
POST /v1/split (wired in agent_si.backend.app.create_app): it validates
the request shape and returns the served payload verbatim, with no I/O,
no secrets and no sandbox paths.
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
    then returns {parts, integration} verbatim. Raises SplitRefused on
    a missing project_id, an empty part list, a part without an id/kind,
    or a duplicated part id.
    """
    if not isinstance(task, dict):
        raise SplitRefused("task must be a {project_id, parts} mapping")
    return split_project(task.get("project_id"), task.get("parts"))


def integrate(parts: object, project_id: object = None) -> dict[str, Any]:
    """Serve one Manager integration: split parts -> integrated result.

    Returns {project_id, parts: [{id, status: "integrated"}],
    integration: {by: "manager", parts: n}}. Raises IntegrateRefused on
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
    return {
        "project_id": project_id,
        "parts": served,
        "integration": {"by": INTEGRATED_BY, "parts": len(served)},
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
