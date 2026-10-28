"""Per-project per-role routine offload switch (R-333, M-P1-28, R-358).

When the switch is on for a task's project and role, a routine part hands
over to a cheaper agent and the hand-over is recorded with its reason. When
the switch is off (the only default; no provisional Director default), or
the part is not routine, maybe_offload returns None and records nothing.
Every toggle change is validated (audit independence, budget, caps, scope)
before it applies and persists one DecisionRow; a rejection returns
applied=False with a reason code, mutates nothing and persists no row.
DecisionRow keeps the frozen shape shared with the lanes; the integration
Manager dedups it into common. The change mapping carries no secrets.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

AUDIT_INDEPENDENCE_REJECTED = "AUDIT_INDEPENDENCE_REJECTED"
BUDGET_CAPPED = "BUDGET_CAPPED"
POLICY_CONFLICT = "POLICY_CONFLICT"
REJECTED_SCOPE_OVERLAP = "REJECTED_SCOPE_OVERLAP"

_SCOPE_PREFIX = "offload:"
_FALLBACK_TO_ROLE = "cheap-agent"
_FALLBACK_HANDOVER_REASON = "routine work runs on the cheaper path"

_ALLOWED_KEYS = frozenset(
    {
        "project_id",
        "role",
        "enabled",
        "to_role",
        "handover_reason",
        "task_ids",
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


@dataclass
class DecisionRow:
    decision_id: str
    scope: str
    statement: str
    reason: str
    authority: str
    created_at: str


@dataclass
class HandoverRecord:
    task_id: str
    from_role: str
    to_role: str
    reason: str
    created_at: str


@dataclass
class ApplyOutcome:
    applied: bool
    reason: str
    decision_ref: str | None = None


@dataclass
class _SwitchSetting:
    enabled: bool
    to_role: str
    handover_reason: str


_SWITCHES: dict[tuple[str, str], _SwitchSetting] = {}
_TASK_PROJECT: dict[str, str] = {}
_HANDOVERS: list[HandoverRecord] = []
_DECISIONS: list[DecisionRow] = []
_ACCEPT_ORDER: list[tuple[str, str]] = []
_SEQ = 0


def _reset_state() -> None:
    """Clear module state (test helper; never a product path)."""
    global _SEQ
    _SWITCHES.clear()
    _TASK_PROJECT.clear()
    _HANDOVERS.clear()
    _DECISIONS.clear()
    _ACCEPT_ORDER.clear()
    _SEQ = 0


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


def offload_enabled(project_id: str, role: str) -> bool:
    """Read the switch for one project and role; unknown pairs stay off."""
    if not isinstance(project_id, str) or not isinstance(role, str):
        return False
    setting = _SWITCHES.get((project_id, role))
    return setting.enabled if setting is not None else False


def _effective_setting(task_id: str, role: str) -> _SwitchSetting | None:
    project_id = _TASK_PROJECT.get(task_id)
    if project_id is not None:
        setting = _SWITCHES.get((project_id, role))
        if setting is not None and setting.enabled:
            return setting
        return None
    for scope in reversed(_ACCEPT_ORDER):
        if scope[1] != role:
            continue
        setting = _SWITCHES.get(scope)
        if setting is not None and setting.enabled:
            return setting
    return None


def maybe_offload(task_id: str, role: str, routine: bool) -> HandoverRecord | None:
    """Hand a routine task over when the switch is on; else explicit None.

    A bound task uses its own project's switch; an unbound task uses the
    role's newest enabled setting. Anything else (not routine, switch off,
    unknown task or role) returns None and records nothing.
    """
    if routine is not True:
        return None
    if not isinstance(task_id, str) or not task_id:
        return None
    if not isinstance(role, str) or not role:
        return None
    if role == "auditor":
        return None
    setting = _effective_setting(task_id, role)
    if setting is None:
        return None
    record = HandoverRecord(
        task_id=task_id,
        from_role=role,
        to_role=setting.to_role,
        reason=setting.handover_reason,
        created_at=_utc_now(),
    )
    _HANDOVERS.append(record)
    return record


def apply_offload_config_change(change: dict) -> ApplyOutcome:
    """Validate one offload toggle change, then apply it with a DecisionRow."""
    if not isinstance(change, dict):
        return _refuse(POLICY_CONFLICT, "change must be a dict")
    unknown = sorted(str(key) for key in change if key not in _ALLOWED_KEYS)
    if unknown:
        return _refuse(POLICY_CONFLICT, f"unknown keys: {','.join(unknown)}")
    project_id = change.get("project_id")
    if not isinstance(project_id, str) or not project_id:
        return _refuse(POLICY_CONFLICT, "project_id must be a non-empty string")
    role = change.get("role")
    if not isinstance(role, str) or not role:
        return _refuse(POLICY_CONFLICT, "role must be a non-empty string")
    if role == "auditor":
        return _refuse(
            AUDIT_INDEPENDENCE_REJECTED, "auditor role never offloads"
        )
    if "enabled" not in change or not isinstance(change["enabled"], bool):
        return _refuse(POLICY_CONFLICT, "enabled must be an explicit true or false")
    enabled = change["enabled"]
    authority = change.get("authority")
    if not _is_compact_english(authority):
        return _refuse(POLICY_CONFLICT, "authority must be compact English")
    reason = change.get("reason")
    if not _is_compact_english(reason):
        return _refuse(POLICY_CONFLICT, "reason must be compact English")
    statement = change.get(
        "statement", f"routine offload for role {role} in project {project_id}"
    )
    if not _is_compact_english(statement):
        return _refuse(POLICY_CONFLICT, "statement must be compact English")
    to_role = change.get("to_role", _FALLBACK_TO_ROLE)
    if not _is_compact_english(to_role):
        return _refuse(POLICY_CONFLICT, "to_role must be compact English")
    handover_reason = change.get("handover_reason", _FALLBACK_HANDOVER_REASON)
    if not _is_compact_english(handover_reason):
        return _refuse(POLICY_CONFLICT, "handover_reason must be compact English")
    task_ids: list[str] = []
    if "task_ids" in change:
        raw_ids = change["task_ids"]
        if not isinstance(raw_ids, list) or not all(
            isinstance(item, str) and item for item in raw_ids
        ):
            return _refuse(POLICY_CONFLICT, "task_ids must be a list of ids")
        task_ids = list(raw_ids)
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
    for task_id in task_ids:
        owner = _TASK_PROJECT.get(task_id)
        if owner is not None and owner != project_id:
            return _refuse(
                REJECTED_SCOPE_OVERLAP,
                f"task {task_id} already bound to project {owner}",
            )
    global _SEQ
    _SWITCHES[(project_id, role)] = _SwitchSetting(
        enabled=enabled,
        to_role=str(to_role),
        handover_reason=str(handover_reason),
    )
    _ACCEPT_ORDER.append((project_id, role))
    for task_id in task_ids:
        _TASK_PROJECT[task_id] = project_id
    _SEQ += 1
    scope = f"{_SCOPE_PREFIX}{project_id}:{role}"
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
