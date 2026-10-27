"""Step-limit settings tests: R-349 task vs chat, R-358 writer (RED->GREEN)."""
from __future__ import annotations

import dataclasses
import os
import sys

import pytest

sys.path.insert(
    0,
    os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
    ),
)

from agent_si.backend.orchestration import offload as offload_mod
from agent_si.backend.orchestration import steplimits as sl
from agent_si.backend.orchestration.steplimits import (
    UNKNOWN_LIMIT_KIND,
    ApplyOutcome,
    StepLimits,
    apply_steplimit_config_change,
    limits_for,
)


@pytest.fixture(autouse=True)
def _clean():
    sl._reset_state()
    yield
    sl._reset_state()


def _change(
    project: str, task: object = None, chat: object = None, **extra: object
) -> dict:
    change: dict = {
        "project_id": project,
        "authority": "manager-b",
        "reason": "set limits for test",
    }
    if task is not None:
        change["task_max_steps"] = task
    if chat is not None:
        change["chat_max_steps"] = chat
    change.update(extra)
    return change


def _accept(project: str, task: int, chat: int, **extra: object) -> ApplyOutcome:
    return apply_steplimit_config_change(_change(project, task, chat, **extra))


def test_frozen_shapes_exact() -> None:
    assert [f.name for f in dataclasses.fields(StepLimits)] == [
        "task_max_steps",
        "chat_max_steps",
    ]
    assert [f.name for f in dataclasses.fields(ApplyOutcome)] == [
        "applied",
        "reason",
        "decision_ref",
    ]
    assert sl.DecisionRow is offload_mod.DecisionRow
    assert [f.name for f in dataclasses.fields(sl.DecisionRow)] == [
        "decision_id",
        "scope",
        "statement",
        "reason",
        "authority",
        "created_at",
    ]


def test_task_kind_reads_task_value() -> None:
    outcome = _accept("proj-a", 2, 5)
    assert outcome.applied is True
    assert limits_for("task", "proj-a") == 2


def test_chat_kind_reads_chat_value() -> None:
    _accept("proj-a", 2, 5)
    assert limits_for("chat", "proj-a") == 5


def test_unknown_kind_raises_and_mutates_nothing() -> None:
    _accept("proj-a", 2, 5)
    before_limits = dict(sl._PROJECT_LIMITS)
    before_rows = list(sl._DECISIONS)
    with pytest.raises(UNKNOWN_LIMIT_KIND):
        limits_for("bogus", "proj-a")
    assert dict(sl._PROJECT_LIMITS) == before_limits
    assert list(sl._DECISIONS) == before_rows


def test_limits_are_per_project() -> None:
    _accept("proj-a", 2, 5)
    _accept("proj-b", 7, 9)
    assert limits_for("task", "proj-a") == 2
    assert limits_for("chat", "proj-a") == 5
    assert limits_for("task", "proj-b") == 7
    assert limits_for("chat", "proj-b") == 9


def test_accept_persists_one_decision_row() -> None:
    outcome = apply_steplimit_config_change(
        _change("proj-a", 2, 3, reason="raise chat cap ok")
    )
    assert outcome.applied is True
    assert outcome.reason == "applied"
    assert outcome.decision_ref
    assert len(sl._DECISIONS) == 1
    row = sl._DECISIONS[0]
    assert row.decision_id == outcome.decision_ref
    assert row.scope == "steplimits:proj-a"
    assert row.statement != ""
    assert row.reason == "raise chat cap ok"
    assert row.authority == "manager-b"
    assert row.created_at != ""
    assert limits_for("task", "proj-a") == 2
    assert limits_for("chat", "proj-a") == 3


def test_partial_update_keeps_other_value() -> None:
    _accept("proj-a", 2, 3)
    outcome = apply_steplimit_config_change(_change("proj-a", chat=4))
    assert outcome.applied is True
    assert limits_for("task", "proj-a") == 2
    assert limits_for("chat", "proj-a") == 4
    assert len(sl._DECISIONS) == 2
    assert sl._DECISIONS[0].decision_id != sl._DECISIONS[1].decision_id


def test_reject_out_of_range_mutates_nothing() -> None:
    _accept("proj-a", 2, 3)
    before_limits = dict(sl._PROJECT_LIMITS)
    before_rows = list(sl._DECISIONS)
    for bad in (0, -3, True, 10_001, "7", 2.5):
        outcome = apply_steplimit_config_change(_change("proj-a", task=bad))
        assert outcome.applied is False
        assert "BUDGET_CAPPED" in outcome.reason
        assert outcome.decision_ref is None
    assert dict(sl._PROJECT_LIMITS) == before_limits
    assert list(sl._DECISIONS) == before_rows
    assert limits_for("task", "proj-a") == 2


def test_reject_audit_independence() -> None:
    _accept("proj-a", 2, 3)
    before_limits = dict(sl._PROJECT_LIMITS)
    before_rows = list(sl._DECISIONS)
    outcome = apply_steplimit_config_change(
        _change("proj-a", 4, 4, independent_audit=False)
    )
    assert outcome.applied is False
    assert "AUDIT_INDEPENDENCE_REJECTED" in outcome.reason
    assert outcome.decision_ref is None
    outcome = apply_steplimit_config_change(
        _change("proj-a", 4, 4, auditor="w-1", worker="w-1")
    )
    assert outcome.applied is False
    assert "AUDIT_INDEPENDENCE_REJECTED" in outcome.reason
    assert dict(sl._PROJECT_LIMITS) == before_limits
    assert list(sl._DECISIONS) == before_rows


def test_reject_malformed_change_policy_conflict() -> None:
    _accept("proj-a", 2, 3)
    before_limits = dict(sl._PROJECT_LIMITS)
    before_rows = list(sl._DECISIONS)
    bad_changes = [
        {"authority": "manager-b", "reason": "x", "task_max_steps": 2},
        {"project_id": "", "authority": "m", "reason": "x", "task_max_steps": 2},
        {"project_id": "proj-a", "reason": "x", "task_max_steps": 2},
        {"project_id": "proj-a", "authority": "m", "task_max_steps": 2},
        dict(_change("proj-a", 2, 3), unknown_key=1),
        "not-a-dict",
    ]
    for bad in bad_changes:
        outcome = apply_steplimit_config_change(bad)  # type: ignore[arg-type]
        assert outcome.applied is False
        assert "POLICY_CONFLICT" in outcome.reason
        assert outcome.decision_ref is None
    assert dict(sl._PROJECT_LIMITS) == before_limits
    assert list(sl._DECISIONS) == before_rows


def test_reject_non_compact_english() -> None:
    before_rows = list(sl._DECISIONS)
    outcome = apply_steplimit_config_change(
        _change("proj-a", 2, 3, reason="  spaced  out  ")
    )
    assert outcome.applied is False
    assert "POLICY_CONFLICT" in outcome.reason
    outcome = apply_steplimit_config_change(
        _change("proj-a", 2, 3, reason="triage \u00abok\u00bb")
    )
    assert outcome.applied is False
    assert list(sl._DECISIONS) == before_rows


def test_no_provisional_director_default() -> None:
    assert [n for n in dir(sl) if n.startswith("DEFAULT")] == []
    outcome = apply_steplimit_config_change(_change("proj-new", chat=4))
    assert outcome.applied is False
    assert "POLICY_CONFLICT" in outcome.reason
    assert sl._PROJECT_LIMITS == {}
    assert sl._DECISIONS == []
    with pytest.raises(KeyError):
        limits_for("task", "proj-new")
    with pytest.raises(KeyError):
        limits_for("chat")


def test_budget_capped_on_cost_overrun() -> None:
    _accept("proj-a", 2, 3)
    before_limits = dict(sl._PROJECT_LIMITS)
    before_rows = list(sl._DECISIONS)
    outcome = apply_steplimit_config_change(
        _change("proj-a", 4, 4, cost=50, budget_left=10)
    )
    assert outcome.applied is False
    assert "BUDGET_CAPPED" in outcome.reason
    assert outcome.decision_ref is None
    assert dict(sl._PROJECT_LIMITS) == before_limits
    assert list(sl._DECISIONS) == before_rows


def test_cost_without_budget_refused() -> None:
    outcome = apply_steplimit_config_change(_change("proj-a", 2, 3, cost=5))
    assert outcome.applied is False
    assert "POLICY_CONFLICT" in outcome.reason
    assert sl._PROJECT_LIMITS == {}
