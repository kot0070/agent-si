"""K08R3 SPEC 0A keep tests: verbatim user-requirement register + audit gate.

Target: src/agent_si/context_keeper/requirements.py (new) as exposed
through src/agent_si/context_keeper/register.py. Each test builds its
own realistic requirement sentences inline; no shared fixtures.
"""

import dataclasses
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_si.context_keeper import interface as ck  # noqa: F401  (pins frozen contract)
from agent_si.context_keeper import requirements as keeper_requirements
from agent_si.context_keeper import register as keeper_register


def test_append_stores_requirement_text_verbatim():
    store = keeper_requirements.RequirementRegister()
    row = keeper_requirements.RequirementRow(
        requirement_id="req-keep-verbatim",
        text="The dashboard shall show the pump pressure in bar, updated every 2 s.",
    )
    assert store.append(row) == row
    assert store.read("req-keep-verbatim") == row
    assert store.read("req-keep-verbatim").text == \
        "The dashboard shall show the pump pressure in bar, updated every 2 s."


def test_duplicate_id_returns_stored_row_without_overwrite():
    store = keeper_requirements.RequirementRegister()
    first = keeper_requirements.RequirementRow(
        requirement_id="req-duplicate-pump",
        text="The operator shall acknowledge every high-pressure alarm within 60 s.",
    )
    second = keeper_requirements.RequirementRow(
        requirement_id="req-duplicate-pump",
        text="The operator may ignore alarms during the night shift.",
    )
    assert store.append(first) == first
    assert store.append(second) == first
    assert store.read("req-duplicate-pump") == first
    assert store.list_all() == [first]


def test_requirement_rows_are_immutable():
    row = keeper_requirements.RequirementRow(
        requirement_id="req-frozen-valve",
        text="The inlet valve shall close automatically when the tank reaches 95% level.",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        row.text = "changed"


def test_history_is_never_rewritten():
    store = keeper_requirements.RequirementRegister()
    first = keeper_requirements.RequirementRow(
        requirement_id="req-history-boiler",
        text="The boiler shall trip when the outlet temperature exceeds 110 C.",
    )
    second = keeper_requirements.RequirementRow(
        requirement_id="req-history-conveyor",
        text="The conveyor shall stop when the guard door is opened.",
    )
    store.append(first)
    store.append(second)
    store.append(keeper_requirements.RequirementRow(
        requirement_id="req-history-boiler",
        text="A rewritten boiler rule that must never replace the stored row.",
    ))
    assert store.list_all() == [first, second]
    assert store.read("req-history-boiler").text == \
        "The boiler shall trip when the outlet temperature exceeds 110 C."


def test_audit_all_preserved_leaves_pass_unblocked():
    report = keeper_requirements.audit_requirements(
        expected={"req-audit-trend": "The trend view shall keep 24 h of flow samples."},
        actual={"req-audit-trend": "The trend view shall keep 24 h of flow samples."},
    )
    assert report.states == {"req-audit-trend": "PRESERVED"}
    assert report.blocked is False


def test_audit_changed_text_blocks():
    report = keeper_requirements.audit_requirements(
        expected={"req-audit-interlock": "The mixer interlock shall engage before the agitator starts."},
        actual={"req-audit-interlock": "The mixer interlock shall engage after the agitator starts."},
    )
    assert report.states == {"req-audit-interlock": "CHANGED"}
    assert report.blocked is True


def test_audit_missing_requirement_blocks():
    report = keeper_requirements.audit_requirements(
        expected={"req-audit-siren": "The hall siren shall sound for 30 s on evacuation."},
        actual={},
    )
    assert report.states == {"req-audit-siren": "MISSING"}
    assert report.blocked is True


def test_audit_contradicted_requirement_blocks():
    report = keeper_requirements.audit_requirements(
        expected={"req-audit-relay": "The safety relay shall remain energised while the gate is shut."},
        actual={"req-audit-relay": "The safety relay shall remain energised while the gate is shut."},
        conflicting_ids=("req-audit-relay",),
    )
    assert report.states == {"req-audit-relay": "CONTRADICTED"}
    assert report.blocked is True


def test_audit_flagged_changed_id_blocks_despite_equal_text():
    report = keeper_requirements.audit_requirements(
        expected={"req-audit-filter": "The filter differential pressure shall be logged each shift."},
        actual={"req-audit-filter": "The filter differential pressure shall be logged each shift."},
        changed_ids=("req-audit-filter",),
    )
    assert report.states == {"req-audit-filter": "CHANGED"}
    assert report.blocked is True


def test_audit_matrix_combined_states():
    report = keeper_requirements.audit_requirements(
        expected={
            "req-matrix-level": "The sump level shall be displayed in centimetres.",
            "req-matrix-fan": "The exhaust fan shall run for 5 min after shutdown.",
            "req-matrix-lamp": "The beacon lamp shall flash while the crane moves.",
            "req-matrix-drain": "The drain pump shall start on high sump level.",
        },
        actual={
            "req-matrix-level": "The sump level shall be displayed in centimetres.",
            "req-matrix-fan": "The exhaust fan shall run for 10 min after shutdown.",
            "req-matrix-drain": "The drain pump shall start on high sump level.",
        },
        conflicting_ids=("req-matrix-drain",),
    )
    assert report.states == {
        "req-matrix-level": "PRESERVED",
        "req-matrix-fan": "CHANGED",
        "req-matrix-lamp": "MISSING",
        "req-matrix-drain": "CONTRADICTED",
    }
    assert report.blocked is True


def test_audit_empty_expected_is_not_blocked():
    report = keeper_requirements.audit_requirements(expected={}, actual={})
    assert report.states == {}
    assert report.blocked is False


def test_register_module_exposes_requirement_gate():
    assert keeper_register.RequirementRegister is keeper_requirements.RequirementRegister
    assert keeper_register.RequirementRow is keeper_requirements.RequirementRow
    assert keeper_register.RequirementAudit is keeper_requirements.RequirementAudit
    assert keeper_register.audit_requirements is keeper_requirements.audit_requirements
    report = keeper_register.audit_requirements(
        expected={"req-gate-torque": "The coupling torque limit shall be 400 Nm."},
        actual={"req-gate-torque": "The coupling torque limit shall be 400 Nm."},
    )
    assert report.states == {"req-gate-torque": "PRESERVED"}
    assert report.blocked is False
