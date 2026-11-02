"""FXDEVRUN wire protocol: Director / agent / auditor JSON shapes.

Strict in code, never by model: the engine parses each reply here,
quotes the exact problem back for the single Director repair, and
fails the run honestly when the repair still does not parse.
"""

from __future__ import annotations

import json
import os
from typing import Any


class PlanError(ValueError):
    """One Director plan problem, quotable back to the Director."""

    code: str = "DEVRUN_PLAN_INVALID"


def _clean_path(raw: Any) -> str:
    """Normalized relative path, or empty when the raw value is bad."""
    if not isinstance(raw, str) or not raw.strip():
        return ""
    text = raw.strip().replace("\\", "/")
    if os.path.isabs(raw) or os.path.isabs(text):
        return ""
    if text.startswith("~"):
        return ""
    normalized = os.path.normpath(text).replace("\\", "/")
    if normalized in (".", ""):
        return ""
    if normalized == ".." or normalized.startswith("../"):
        return ""
    return normalized


def parse_director_reply(text: str) -> dict[str, Any]:
    """Parse one Director reply into {"answer"} or {"parts"}.

    Raises PlanError quoting the exact problem (malformed JSON or a
    failed validation: paths outside the project folder, overlapping
    files, non-list argv, unknown or cyclic depends_on).
    """
    try:
        data = json.loads(text)
    except Exception as exc:
        raise PlanError("director reply is not JSON: %s" % (exc,)) from None
    if not isinstance(data, dict):
        raise PlanError("director reply must be a JSON object")
    if "parts" in data and data["parts"] is not None:
        return {"parts": _clean_parts(data.get("parts"))}
    if "answer" in data and data["answer"] is not None:
        answer = data.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            raise PlanError("director answer must be a non-empty string")
        return {"answer": answer.strip()}
    raise PlanError(
        "director reply needs either {\"answer\": text} or "
        "{\"parts\": [...]}")


def _clean_parts(raw: Any) -> list[dict[str, Any]]:
    """Validate the parts list; raise PlanError on the first problem."""
    if not isinstance(raw, list) or not raw:
        raise PlanError("director parts must be a non-empty list")
    seen: set[str] = set()
    claimed: dict[str, str] = {}
    parts: list[dict[str, Any]] = []
    for index, entry in enumerate(raw):
        where = "part %d" % (index,)
        if not isinstance(entry, dict):
            raise PlanError("%s must be an object" % (where,))
        part_id = entry.get("part_id")
        if not isinstance(part_id, str) or not part_id.strip():
            raise PlanError("%s needs a non-empty part_id" % (where,))
        part_id = part_id.strip()
        if part_id in seen:
            raise PlanError("duplicate part_id %r" % (part_id,))
        seen.add(part_id)
        goal = entry.get("goal")
        if not isinstance(goal, str) or not goal.strip():
            raise PlanError("part %r needs a non-empty goal" % (part_id,))
        files = entry.get("files")
        if not isinstance(files, list):
            raise PlanError("part %r files must be a list" % (part_id,))
        clean_files: list[str] = []
        for path in files:
            cleaned = _clean_path(path)
            if not cleaned:
                raise PlanError(
                    "part %r file %r is outside the project folder"
                    % (part_id, path))
            if cleaned in claimed:
                raise PlanError(
                    "file %r claimed by parts %r and %r" % (
                        cleaned, claimed[cleaned], part_id))
            claimed[cleaned] = part_id
            clean_files.append(cleaned)
        commands = entry.get("check_commands", [])
        if not isinstance(commands, list):
            raise PlanError(
                "part %r check_commands must be a list" % (part_id,))
        clean_commands: list[list[str]] = []
        for command in commands:
            if (not isinstance(command, list) or not command
                    or any(not isinstance(word, str) or not word
                           for word in command)):
                raise PlanError(
                    "part %r check_commands must be argv word lists"
                    % (part_id,))
            clean_commands.append([str(word) for word in command])
        depends = entry.get("depends_on", [])
        if not isinstance(depends, list) or any(
                not isinstance(item, str) for item in depends):
            raise PlanError(
                "part %r depends_on must be a list of part ids" % (part_id,))
        why = entry.get("why", "")
        parts.append({
            "part_id": part_id,
            "goal": goal.strip(),
            "files": clean_files,
            "check_commands": clean_commands,
            "depends_on": [str(item) for item in depends],
            "why": str(why) if isinstance(why, str) else "",
        })
    ids = {part["part_id"] for part in parts}
    for part in parts:
        for dep in part["depends_on"]:
            if dep not in ids:
                raise PlanError("part %r depends on unknown part %r"
                                % (part["part_id"], dep))
            if dep == part["part_id"]:
                raise PlanError("part %r depends on itself"
                                % (part["part_id"],))
    _check_acyclic(parts)
    return parts


def _check_acyclic(parts: list[dict[str, Any]]) -> None:
    """Raise PlanError when depends_on edges form a cycle."""
    edges = {part["part_id"]: list(part["depends_on"]) for part in parts}
    visiting: set[str] = set()
    settled: set[str] = set()

    def _visit(node: str, stack: list[str]) -> None:
        if node in settled:
            return
        if node in visiting:
            raise PlanError("depends_on cycle: %s" % (" -> ".join(
                [*stack, node],)))
        visiting.add(node)
        for dep in edges.get(node, []):
            _visit(dep, [*stack, node])
        visiting.discard(node)
        settled.add(node)

    for part in parts:
        _visit(part["part_id"], [])


class AgentError(ValueError):
    """One worker reply problem; the engine retries the turn once."""

    code: str = "DEVRUN_AGENT_INVALID"


def parse_agent_reply(text: str) -> dict[str, Any]:
    """Parse one worker reply into {"actions", "done"}.

    Raises AgentError quoting the exact problem.
    """
    try:
        data = json.loads(text)
    except Exception as exc:
        raise AgentError("agent reply is not JSON: %s" % (exc,)) from None
    if not isinstance(data, dict):
        raise AgentError("agent reply must be a JSON object")
    actions = data.get("actions", [])
    if not isinstance(actions, list):
        raise AgentError("agent actions must be a list")
    clean: list[dict[str, Any]] = []
    for action in actions:
        if not isinstance(action, dict):
            raise AgentError("agent action must be an object")
        name = action.get("action")
        if name not in ("read_file", "list_dir", "write_file", "run"):
            raise AgentError("unknown agent action %r" % (name,))
        clean.append(dict(action))
    done = data.get("done", False)
    if not isinstance(done, bool):
        raise AgentError("agent done must be true or false")
    return {"actions": clean, "done": done}


class AuditError(ValueError):
    """One auditor reply problem; malformed auditor output is FAIL."""

    code: str = "DEVRUN_AUDIT_INVALID"


def parse_auditor_reply(text: str) -> dict[str, Any]:
    """Parse one auditor reply into {"result", "reasons"}.

    Raises AuditError quoting the exact problem; the engine turns
    that into FAIL, never a silent pass.
    """
    try:
        data = json.loads(text)
    except Exception as exc:
        raise AuditError("auditor reply is not JSON: %s" % (exc,)) from None
    if not isinstance(data, dict):
        raise AuditError("auditor reply must be a JSON object")
    result = data.get("result")
    if result not in ("PASS", "FAIL"):
        raise AuditError("auditor result must be PASS or FAIL")
    reasons = data.get("reasons", [])
    if not isinstance(reasons, list) or any(
            not isinstance(item, str) for item in reasons):
        raise AuditError("auditor reasons must be a list of strings")
    return {"result": result, "reasons": list(reasons)}
