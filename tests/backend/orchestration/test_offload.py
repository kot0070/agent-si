"""Routine offload switch tests: R-333 on/off + record, R-358 writer (RED->GREEN)."""
from __future__ import annotations

import dataclasses
import os
import sys

_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
sys.path.insert(0, os.path.join(_ROOT, "src"))

import pytest

from agent_si.backend.orchestration import offload as mod
from agent_si.backend.orchestration.offload import (
    AUDIT_INDEPENDENCE_REJECTED,
    BUDGET_CAPPED,
    POLICY_CONFLICT,
    REJECTED_SCOPE_OVERLAP,
    ApplyOutcome,
    DecisionRow,
    HandoverRecord,
    apply_offload_config_change,
    maybe_offload,
    offload_enabled,
)


@pytest.fixture(autouse=True)
def _clean():
    mod._reset_state()
    yield
    mod._reset_state()


def _change(
    project: str,
    role: str,
    enabled: object = True,
    **extra: object,
) -> dict:
    change: dict = {
        "project_id": project,
        "role": role,
        "enabled": enabled,
        "authority": "manager-b",
        "reason": "route routine subtasks cheaper",
    }
    change.update(extra)
    return change


def _accept(project: str, role: str, enabled: object = True, **extra: object) -> ApplyOutcome:
    outcome = apply_offload_config_change(_change(project, role, enabled, **extra))
    assert outcome.applied is True
    return outcome


def _snapshot() -> tuple:
    return (dict(mod._SWITCHES), dict(mod._TASK_PROJECT), list(mod._HANDOVERS), list(mod._DECISIONS))


def test_frozen_shapes_exact() -> None:
    assert [f.name for f in dataclasses.fields(HandoverRecord)] == [
        "task_id",
        "from_role",
        "to_role",
        "reason",
        "created_at",
    ]
    assert [f.name for f in dataclasses.fields(DecisionRow)] == [
        "decision_id",
        "scope",
        "statement",
        "reason",
        "authority",
        "created_at",
    ]
    assert [f.name for f in dataclasses.fields(ApplyOutcome)] == [
        "applied",
        "reason",
        "decision_ref",
    ]
    assert mod.DecisionRow is DecisionRow
    assert len({AUDIT_INDEPENDENCE_REJECTED, BUDGET_CAPPED, POLICY_CONFLICT, REJECTED_SCOPE_OVERLAP}) == 4


def test_switch_on_routine_hands_over_with_record() -> None:
    _accept(
        "proj-on",
        "worker",
        task_ids=["task-1"],
        to_role="cheap-agent",
        handover_reason="routine triage runs cheaper",
    )
    assert offload_enabled("proj-on", "worker") is True
    record = maybe_offload("task-1", "worker", True)
    assert record is not None
    assert record.task_id == "task-1"
    assert record.from_role == "worker"
    assert record.to_role == "cheap-agent"
    assert record.reason == "routine triage runs cheaper"
    assert record.created_at != ""
    assert mod._HANDOVERS == [record]


def test_switch_off_returns_none_and_records_nothing() -> None:
    assert offload_enabled("proj-fresh", "worker") is False
    assert maybe_offload("task-fresh", "worker", True) is None
    assert mod._HANDOVERS == []
    _accept("proj-off", "worker", task_ids=["task-2"])
    assert offload_enabled("proj-off", "worker") is True
    outcome = apply_offload_config_change(_change("proj-off", "worker", False))
    assert outcome.applied is True
    assert offload_enabled("proj-off", "worker") is False
    assert maybe_offload("task-2", "worker", True) is None
    assert [h for h in mod._HANDOVERS if h.task_id == "task-2"] == []


def test_non_routine_returns_none_even_when_on() -> None:
    _accept("proj-nr", "worker", task_ids=["task-3"])
    for not_routine in (False, None, 0, "yes"):
        assert maybe_offload("task-3", "worker", not_routine) is None  # type: ignore[arg-type]
    assert mod._HANDOVERS == []


def test_per_project_and_per_role_isolation() -> None:
    _accept("proj-a", "worker", task_ids=["task-a"])
    _accept("proj-b", "worker", False, task_ids=["task-b"])
    assert offload_enabled("proj-a", "worker") is True
    assert offload_enabled("proj-b", "worker") is False
    assert offload_enabled("proj-a", "auditor") is False
    assert maybe_offload("task-a", "worker", True) is not None
    assert maybe_offload("task-b", "worker", True) is None
    assert maybe_offload("task-a", "auditor", True) is None
    assert [h.task_id for h in mod._HANDOVERS] == ["task-a"]


def test_unbound_task_uses_role_switch() -> None:
    _accept("proj-u", "worker")
    assert offload_enabled("proj-u", "worker") is True
    record = maybe_offload("task-unbound", "worker", True)
    assert record is not None
    assert record.task_id == "task-unbound"
    assert record.from_role == "worker"
    assert record.to_role != ""
    assert record.reason != ""
    assert mod._HANDOVERS == [record]


def test_accept_persists_one_decision_row() -> None:
    outcome = apply_offload_config_change(
        _change("proj-d", "worker", True, task_ids=["task-d"], reason="cut cost ok")
    )
    assert outcome.applied is True
    assert outcome.reason == "applied"
    assert outcome.decision_ref
    assert len(mod._DECISIONS) == 1
    row = mod._DECISIONS[0]
    assert row.decision_id == outcome.decision_ref
    assert row.scope == "offload:proj-d:worker"
    assert row.statement != ""
    assert row.reason == "cut cost ok"
    assert row.authority == "manager-b"
    assert row.created_at != ""
    second = apply_offload_config_change(_change("proj-d", "worker", False))
    assert second.applied is True
    assert len(mod._DECISIONS) == 2
    assert mod._DECISIONS[0].decision_id != mod._DECISIONS[1].decision_id


def test_reject_audit_independence_mutates_nothing() -> None:
    _accept("proj-i", "worker", task_ids=["task-i"])
    before = _snapshot()
    outcome = apply_offload_config_change(
        _change("proj-i", "worker", True, independent_audit=False)
    )
    assert outcome.applied is False
    assert AUDIT_INDEPENDENCE_REJECTED in outcome.reason
    assert outcome.decision_ref is None
    outcome = apply_offload_config_change(
        _change("proj-i", "worker", True, auditor="w-1", worker="w-1")
    )
    assert outcome.applied is False
    assert AUDIT_INDEPENDENCE_REJECTED in outcome.reason
    assert outcome.decision_ref is None
    assert _snapshot() == before


def test_reject_budget_capped_mutates_nothing() -> None:
    _accept("proj-c", "worker", task_ids=["task-c"])
    before = _snapshot()
    outcome = apply_offload_config_change(
        _change("proj-c", "worker", True, cost=50, budget_left=10)
    )
    assert outcome.applied is False
    assert BUDGET_CAPPED in outcome.reason
    assert outcome.decision_ref is None
    assert _snapshot() == before


def test_reject_malformed_change_policy_conflict() -> None:
    _accept("proj-m", "worker", task_ids=["task-m"])
    before = _snapshot()
    bad_changes = [
        {"project_id": "proj-m", "role": "worker", "authority": "manager-b",
         "reason": "no enabled flag"},
        {"project_id": "proj-m", "role": "worker", "enabled": "yes",
         "authority": "manager-b", "reason": "bad"},
        {"role": "worker", "enabled": True, "authority": "manager-b", "reason": "x"},
        {"project_id": "", "role": "worker", "enabled": True,
         "authority": "m", "reason": "x"},
        {"project_id": "proj-m", "role": "worker", "enabled": True, "reason": "x"},
        {"project_id": "proj-m", "role": "worker", "enabled": True,
         "authority": "manager-b"},
        dict(_change("proj-m", "worker", True), unknown_key=1),
        dict(_change("proj-m", "worker", True), api_key="raw-secret"),
        "not-a-dict",
    ]
    for bad in bad_changes:
        outcome = apply_offload_config_change(bad)  # type: ignore[arg-type]
        assert outcome.applied is False
        assert POLICY_CONFLICT in outcome.reason
        assert outcome.decision_ref is None
    assert _snapshot() == before


def test_reject_scope_overlap_mutates_nothing() -> None:
    _accept("proj-s1", "worker", task_ids=["task-s"])
    before = _snapshot()
    outcome = apply_offload_config_change(
        _change("proj-s2", "worker", True, task_ids=["task-s"])
    )
    assert outcome.applied is False
    assert REJECTED_SCOPE_OVERLAP in outcome.reason
    assert outcome.decision_ref is None
    assert offload_enabled("proj-s2", "worker") is False
    assert _snapshot() == before


def test_no_provisional_director_default() -> None:
    assert [n for n in dir(mod) if n.startswith("DEFAULT")] == []
    assert offload_enabled("proj-new", "worker") is False
    assert maybe_offload("task-new", "worker", True) is None
    assert mod._HANDOVERS == []
    outcome = apply_offload_config_change(
        {"project_id": "proj-new", "role": "worker",
         "authority": "manager-b", "reason": "missing enabled"}
    )
    assert outcome.applied is False
    assert POLICY_CONFLICT in outcome.reason
    assert mod._SWITCHES == {}
    assert mod._DECISIONS == []


def test_auditor_role_never_offloads() -> None:
    before = _snapshot()
    outcome = apply_offload_config_change(
        _change("proj-audit", "auditor", True, task_ids=["task-audit"])
    )
    assert outcome.applied is False
    assert AUDIT_INDEPENDENCE_REJECTED in outcome.reason
    assert outcome.decision_ref is None
    assert _snapshot() == before
    assert offload_enabled("proj-audit", "auditor") is False
    assert maybe_offload("task-audit", "auditor", True) is None
    assert mod._HANDOVERS == []
    _accept("proj-audit", "worker", task_ids=["task-w"])
    assert maybe_offload("task-w", "auditor", True) is None
    assert [h.task_id for h in mod._HANDOVERS] == []
