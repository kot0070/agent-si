"""K08R3 R176 behaviour tests (RED before realisation, GREEN after).

Covers Recovery.regenerate_project_state plus the keeper-slice
PROJECT_STATE assembly in agent_si.context_keeper.project_state:
regeneration content equals the authoritative rows, tampered
checkpoints are excluded and reported, recover regenerates before
continuation, and empty projects yield an empty valid state.
"""

import dataclasses
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_si.context_keeper import interface as ck
from agent_si.context_keeper import checkpoints as keeper_checkpoints
from agent_si.context_keeper import project_state as keeper_project_state
from agent_si.context_keeper import recovery as keeper_recovery
from agent_si.context_keeper import register as keeper_register


def _record(project_id, task_id, run_id, event_id, violation,
            severity, expected, actual, missing, conflicting,
            contract_hash):
    return ck.ContextIntegrityRecord(
        context_event_id=event_id,
        incident_ref=None,
        project_id=project_id,
        task_id=task_id,
        run_id=run_id,
        actor="watcher",
        detected_by="watcher",
        type=violation,
        severity=severity,
        expected_context_refs=tuple(expected),
        actual_context_refs=tuple(actual),
        missing_refs=tuple(missing),
        conflicting_refs=tuple(conflicting),
        contract_hash=contract_hash,
        detected_at="2026-03-04T10:00:00Z",
        impact="impact",
        resolution="",
        resolved_at=None,
        evidence_refs=(),
    )


def test_regenerate_content_matches_authoritative_rows():
    register = keeper_register.Register()
    register.append(_record(
        "proj-r176-content", "task-r176-content", "run-r176-content",
        "evt-r176-a1", "CONTEXT_MISSING", ck.IncidentSeverity.MEDIUM,
        ("doc-r176-a",), ("doc-r176-a",), (), (),
        "contract-r176-content"))
    register.append(_record(
        "proj-r176-content", "task-r176-content", "run-r176-content",
        "evt-r176-a2", "CONTEXT_STALE", ck.IncidentSeverity.LOW,
        ("doc-r176-b",), ("doc-r176-b",), (), (),
        "contract-r176-content"))
    checkpoints = keeper_checkpoints.Checkpoints()
    written = checkpoints.write_checkpoint(
        project_id="proj-r176-content",
        task_id="task-r176-content",
        run_id="run-r176-content",
        contract_hash="contract-r176-content",
        context_refs=("doc-r176-a", "doc-r176-b"),
    )
    state = keeper_recovery.Recovery(
        register, checkpoints=checkpoints).regenerate_project_state(
            "proj-r176-content")
    assert state.project_id == "proj-r176-content"
    assert [row.context_event_id for row in state.unresolved] == [
        "evt-r176-a1", "evt-r176-a2"]
    assert state.unresolved == tuple(
        register.list_unresolved("proj-r176-content"))
    assert set(("doc-r176-a", "doc-r176-b")) <= set(state.refs)
    assert state.checkpoint_id == written.checkpoint_id
    assert state.checkpoint == written
    assert state.checkpoint_valid is True
    assert state.excluded == ()
    assert state.verify_ok is True
    assert state.verify_code == ck.OK_CODE
    assert state.blocked is False
    mapping = state.as_mapping()
    assert mapping["project_id"] == "proj-r176-content"
    assert mapping["unresolved_ids"] == ("evt-r176-a1", "evt-r176-a2")
    assert mapping["checkpoint_id"] == written.checkpoint_id


def test_regenerate_excludes_tampered_checkpoint():
    register = keeper_register.Register()
    register.append(_record(
        "proj-r176-tamper", "task-r176-tamper", "run-r176-tamper",
        "evt-r176-t1", "CONTEXT_MISSING", ck.IncidentSeverity.MEDIUM,
        ("doc-r176-keep",), ("doc-r176-keep",), (), (),
        "contract-r176-tamper"))
    checkpoints = keeper_checkpoints.Checkpoints()
    written = checkpoints.write_checkpoint(
        project_id="proj-r176-tamper",
        task_id="task-r176-tamper",
        run_id="run-r176-tamper",
        contract_hash="contract-r176-tamper",
        context_refs=("doc-r176-keep", "doc-r176-untrusted"),
    )
    checkpoints._by_id[written.checkpoint_id] = dataclasses.replace(
        written, hash="0" * 64)
    state = keeper_recovery.Recovery(
        register, checkpoints=checkpoints).regenerate_project_state(
            "proj-r176-tamper")
    assert state.checkpoint_valid is False
    assert state.checkpoint is None
    assert state.excluded != ()
    assert written.checkpoint_id in state.excluded[0]
    assert "doc-r176-untrusted" not in state.refs
    assert "doc-r176-keep" in state.refs
    assert state.verify_ok is False
    assert state.verify_code == ck.RECOVERY_FAILED_CODE


# FAKE-OF: agent_si.context_keeper.register.Register
class _RestoreSpyRegister(keeper_register.Register):
    """Test register: records mark_resolved order."""

    def __init__(self, calls):
        super().__init__()
        self._calls = calls

    def mark_resolved(self, context_event_id, resolution, resolved_at):
        self._calls.append("restore")
        return super().mark_resolved(
            context_event_id, resolution, resolved_at)


# FAKE-OF: agent_si.context_keeper.recovery.Recovery
class _RegenerateSpyRecovery(keeper_recovery.Recovery):
    """Test recovery: records regenerate order."""

    def __init__(self, register, checkpoints, calls):
        super().__init__(register, checkpoints=checkpoints)
        self._calls = calls

    def regenerate_project_state(self, project_id):
        self._calls.append("regenerate")
        return super().regenerate_project_state(project_id)


def test_recover_regenerates_before_continuation():
    calls = []
    register = _RestoreSpyRegister(calls)
    register.append(_record(
        "proj-r176-order", "task-r176-order", "run-r176-order",
        "evt-r176-o1", "CONTEXT_MISSING", ck.IncidentSeverity.MEDIUM,
        ("doc-r176-rec",), (), ("doc-r176-rec",), (),
        "contract-r176-order"))
    checkpoints = keeper_checkpoints.Checkpoints()
    written = checkpoints.write_checkpoint(
        project_id="proj-r176-order",
        task_id="task-r176-order",
        run_id="run-r176-order",
        contract_hash="contract-r176-order",
        context_refs=("doc-r176-rec",),
    )
    recovery = _RegenerateSpyRecovery(register, checkpoints, calls)
    report = recovery.recover("proj-r176-order", written.checkpoint_id)
    assert report.ok is True
    assert report.code == ck.OK_CODE
    assert calls[0] == "regenerate"
    assert "restore" in calls
    assert calls.index("regenerate") < calls.index("restore")
    assert register.list_unresolved("proj-r176-order") == []


def test_regenerate_empty_project_yields_empty_valid_state():
    state = keeper_recovery.Recovery(
        keeper_register.Register(),
        checkpoints=keeper_checkpoints.Checkpoints(),
    ).regenerate_project_state("proj-r176-empty")
    assert state.project_id == "proj-r176-empty"
    assert state.unresolved == ()
    assert state.refs == ()
    assert state.checkpoint is None
    assert state.checkpoint_id is None
    assert state.checkpoint_valid is True
    assert state.excluded == ()
    assert state.verify_ok is True
    assert state.verify_code == ck.OK_CODE
    assert state.blocked is False
    assert state.generated_at.endswith("Z")


def test_checkpoint_stamp_is_call_time_and_idempotent():
    checkpoints = keeper_checkpoints.Checkpoints()
    first = checkpoints.write_checkpoint(
        project_id="proj-r176-stamp",
        task_id="task-r176-stamp",
        run_id="run-r176-stamp",
        contract_hash="contract-r176-stamp",
        context_refs=("doc-r176-s1",),
    )
    assert first.created_at != "2026-01-01T00:00:00Z"
    assert first.created_at.endswith("Z")
    assert checkpoints.write_checkpoint(
        project_id="proj-r176-stamp",
        task_id="task-r176-stamp",
        run_id="run-r176-stamp",
        contract_hash="contract-r176-stamp",
        context_refs=("doc-r176-s1",),
    ) == first
    second = checkpoints.write_checkpoint(
        project_id="proj-r176-stamp",
        task_id="task-r176-stamp",
        run_id="run-r176-stamp",
        contract_hash="contract-r176-stamp",
        context_refs=("doc-r176-s2",),
    )
    assert second.created_at != "2026-01-01T00:00:00Z"
    assert second != first


def test_recovery_resolution_stamp_is_call_time():
    register = keeper_register.Register()
    register.append(_record(
        "proj-r176-rstamp", "task-r176-rstamp", "run-r176-rstamp",
        "evt-r176-rs1", "CONTEXT_MISSING", ck.IncidentSeverity.MEDIUM,
        ("doc-r176-rs",), (), ("doc-r176-rs",), (),
        "contract-r176-rstamp"))
    checkpoints = keeper_checkpoints.Checkpoints()
    written = checkpoints.write_checkpoint(
        project_id="proj-r176-rstamp",
        task_id="task-r176-rstamp",
        run_id="run-r176-rstamp",
        contract_hash="contract-r176-rstamp",
        context_refs=("doc-r176-rs",),
    )
    report = keeper_recovery.Recovery(
        register, checkpoints=checkpoints).recover(
            "proj-r176-rstamp", written.checkpoint_id)
    assert report.ok is True
    stored = register.read("evt-r176-rs1")
    assert stored.resolved_at != "2026-01-01T00:00:00Z"
    assert stored.resolved_at.endswith("Z")


def test_regenerate_reports_blocked_on_critical():
    register = keeper_register.Register()
    register.append(_record(
        "proj-r176-block", "task-r176-block", "run-r176-block",
        "evt-r176-b1", "CONTEXT_CONFLICT", ck.IncidentSeverity.CRITICAL,
        ("doc-r176-c",), ("doc-r176-c",), (), (),
        "contract-r176-block"))
    state = keeper_project_state.regenerate_project_state(
        "proj-r176-block",
        register,
        checkpoints=keeper_checkpoints.Checkpoints(),
        verify_report=keeper_recovery.Recovery(register).verify(
            "proj-r176-block"),
    )
    assert state.blocked is True
    assert state.unresolved[0].context_event_id == "evt-r176-b1"
    assert state.verify_ok is True
