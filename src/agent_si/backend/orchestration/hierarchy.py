"""Served hierarchy split/integrate (R-302, K02OPEN8).

The Director splits one project into parts; the parts run; the Manager
integrates them. This module is the pure split/integrate step behind
POST /v1/split (wired in agent_si.backend.app.create_app): it validates
the request shape and returns the served payload verbatim, with no I/O,
no secrets and no sandbox paths.
"""

from __future__ import annotations

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
