"""Max agent steps per project with a separate chat value (R-349, R-358).

Task path reads task_max_steps, chat path reads chat_max_steps. The writer
validates audit independence, budget and caps before apply and persists one
DecisionRow per accepted change. A rejection returns applied=false with a
reason code, mutates nothing and persists no row. No provisional defaults:
a limit is readable only after an accepted change set it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from agent_si.backend.orchestration.offload import DecisionRow

TASK_KIND = "task"
CHAT_KIND = "chat"
STEPLIMIT_SCOPE_PREFIX = "steplimits:"
STEP_LIMIT_MIN = 1
STEP_LIMIT_CAP = 10_000

AUDIT_INDEPENDENCE_REJECTED = "AUDIT_INDEPENDENCE_REJECTED"
BUDGET_CAPPED = "BUDGET_CAPPED"
POLICY_CONFLICT = "POLICY_CONFLICT"

_ALLOWED_KEYS = frozenset(
    {
        "project_id",
        "task_max_steps",
        "chat_max_steps",
        "statement",
        "authority",
        "reason",
        "independent_audit",
        "auditor",
        "worker",
        "cost",
        "budget_left",
    }
)


class UnknownLimitKindError(Exception):
    """Unknown step-limit kind; carries the refusal reason."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


UNKNOWN_LIMIT_KIND = UnknownLimitKindError


@dataclass
class StepLimits:
    task_max_steps: int
    chat_max_steps: int


@dataclass
class ApplyOutcome:
    applied: bool
    reason: str
    decision_ref: str | None = None


_PROJECT_LIMITS: dict[str, StepLimits] = {}
_DECISIONS: list[DecisionRow] = []
_SEQ = 0
_LAST_PROJECT: str | None = None


def _reset_state() -> None:
    """Clear module state (test helper; never a product path)."""
    global _SEQ, _LAST_PROJECT
    _PROJECT_LIMITS.clear()
    _DECISIONS.clear()
    _SEQ = 0
    _LAST_PROJECT = None


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _is_compact_english(text: object) -> bool:
    if not isinstance(text, str) or not text:
        return False
    if text != text.strip() or "  " in text:
        return False
    return all(ord(char) < 128 for char in text)


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _refuse(code: str, detail: str) -> ApplyOutcome:
    return ApplyOutcome(applied=False, reason=f"{code}: {detail}", decision_ref=None)


def limits_for(kind: str, project_id: str | None = None) -> int:
    """Read one limit: task reads task_max_steps, chat reads chat_max_steps.

    project_id selects the per-project setting; None uses the project from
    the last accepted change (never a provisional default). Unknown kind
    raises UNKNOWN_LIMIT_KIND; unconfigured project raises KeyError.
    """
    if kind not in (TASK_KIND, CHAT_KIND):
        raise UnknownLimitKindError(f"UNKNOWN_LIMIT_KIND: {kind!r} is not task/chat")
    target = project_id if project_id is not None else _LAST_PROJECT
    if target is None or target not in _PROJECT_LIMITS:
        raise KeyError(f"no step limits configured for project {target!r}")
    limits = _PROJECT_LIMITS[target]
    if kind == TASK_KIND:
        return limits.task_max_steps
    return limits.chat_max_steps


def apply_steplimit_config_change(change: dict) -> ApplyOutcome:
    """Validate one step-limit change, then apply it with a DecisionRow."""
    if not isinstance(change, dict):
        return _refuse(POLICY_CONFLICT, "change must be a dict")
    unknown = sorted(str(key) for key in change if key not in _ALLOWED_KEYS)
    if unknown:
        return _refuse(POLICY_CONFLICT, f"unknown keys: {','.join(unknown)}")
    project_id = change.get("project_id")
    if not isinstance(project_id, str) or not project_id:
        return _refuse(POLICY_CONFLICT, "project_id must be a non-empty string")
    authority = change.get("authority")
    if not _is_compact_english(authority):
        return _refuse(POLICY_CONFLICT, "authority must be compact English")
    reason = change.get("reason")
    if not _is_compact_english(reason):
        return _refuse(POLICY_CONFLICT, "reason must be compact English")
    statement = change.get("statement", f"step limits for project {project_id}")
    if not _is_compact_english(statement):
        return _refuse(POLICY_CONFLICT, "statement must be compact English")
    if "independent_audit" in change and change["independent_audit"] is not True:
        return _refuse(
            AUDIT_INDEPENDENCE_REJECTED, "independent_audit must stay true"
        )
    if "auditor" in change and "worker" in change and change["auditor"] == change["worker"]:  # noqa: E501  # frozen-cite K02
        return _refuse(
            AUDIT_INDEPENDENCE_REJECTED, "auditor must differ from worker"
        )
    if "cost" in change or "budget_left" in change:
        cost = change.get("cost", 0)
        budget_left = change.get("budget_left")
        if not _is_number(cost):
            return _refuse(POLICY_CONFLICT, "cost must be numeric")
        if budget_left is None:
            return _refuse(POLICY_CONFLICT, "cost needs budget_left to check")
        if not _is_number(budget_left):
            return _refuse(POLICY_CONFLICT, "budget_left must be numeric")
        if float(cost) > float(budget_left):
            return _refuse(
                BUDGET_CAPPED,
                f"cost {cost} exceeds budget left {budget_left}",
            )
    values: dict[str, Any] = {}
    for key in ("task_max_steps", "chat_max_steps"):
        if key in change:
            value = change[key]
            if isinstance(value, bool) or not isinstance(value, int):
                return _refuse(BUDGET_CAPPED, f"{key} must be an integer step count")
            if value < STEP_LIMIT_MIN or value > STEP_LIMIT_CAP:
                return _refuse(
                    BUDGET_CAPPED,
                    f"{key} {value} outside cap range "
                    f"{STEP_LIMIT_MIN}..{STEP_LIMIT_CAP}",
                )
            values[key] = value
    current = _PROJECT_LIMITS.get(project_id)
    if current is None and len(values) < 2:
        return _refuse(
            POLICY_CONFLICT,
            "new project needs both task_max_steps and chat_max_steps",
        )
    limits = StepLimits(
        task_max_steps=values.get(
            "task_max_steps", current.task_max_steps if current else 0
        ),
        chat_max_steps=values.get(
            "chat_max_steps", current.chat_max_steps if current else 0
        ),
    )
    global _SEQ, _LAST_PROJECT
    _PROJECT_LIMITS[project_id] = limits
    _LAST_PROJECT = project_id
    _SEQ += 1
    scope = f"{STEPLIMIT_SCOPE_PREFIX}{project_id}"
    row = DecisionRow(
        decision_id=f"{scope}:{_SEQ:06d}",
        scope=scope,
        statement=str(statement),
        reason=str(reason),
        authority=str(authority),
        created_at=_utc_now(),
    )
    _DECISIONS.append(row)
    return ApplyOutcome(applied=True, reason="applied", decision_ref=row.decision_id)
