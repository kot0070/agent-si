"""Behaviour contract for the context-keeper interface surface.

Covers register.append/read/list_unresolved, recovery.verify/recover and
checkpoint write/read, with every frozen violation code in its own
condition. These tests pin behavior, so they fail while the interface
carries no behavior.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from agent_si.context_keeper import interface as ck

# --- lane-B resolution (import/resolution lines only) ---
# Binds each frozen keeper entry point to the owning-lane realisation;
# shared types stay the frozen interface objects the homes resolve late
# off sys.modules (same class objects, never duplicated classes).
# Register instances stay per-test; checkpoints share one lane store so
# the recovery entry point reads what the test wrote; the store is
# isolated per test through the fixture below.
from agent_si.context_keeper import register as _keeper_register
from agent_si.context_keeper import recovery as _keeper_recovery
from agent_si.context_keeper import checkpoints as _keeper_checkpoints

_checkpoint_by_id = {}
_checkpoint_order = []


class _SharedCheckpoints(_keeper_checkpoints.Checkpoints):
    """Checkpoints over the shared lane store (isolated per test)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._by_id = _checkpoint_by_id
        self._order = _checkpoint_order


class _SharedRecovery:
    """Recovery over the shared register plus the shared checkpoint store."""

    def __init__(self):
        self._impl = _keeper_recovery.Recovery(
            _SharedRegister(), checkpoints=_SharedCheckpoints())

    def verify(self, project_id):
        return self._impl.verify(project_id)

    def recover(self, project_id, checkpoint_id):
        return self._impl.recover(project_id, checkpoint_id)


_register_by_id = {}
_register_order = []


class _SharedRegister(_keeper_register.Register):
    """Register over the shared lane store (isolated per test)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._by_id = _register_by_id
        self._order = _register_order


ck.Register = _keeper_register.Register
ck.Recovery = _SharedRecovery
ck.Checkpoints = _SharedCheckpoints


@pytest.fixture(autouse=True)
def _reset_lane_state():
    _checkpoint_by_id.clear()
    _checkpoint_order.clear()
    _register_by_id.clear()
    _register_order.clear()
    yield


class _SeededRegister:
    """Seed rows into the shared lane register that Recovery reads.
    FAKE-OF: agent_si.context_keeper.register"""

    def __init__(self, rows):
        store = _SharedRegister()
        for row in rows:
            store.append(row)
        self.rows = list(rows)

    def unresolved(self, project_id):
        return [r for r in self.rows
                if r.project_id == project_id and r.resolved_at is None]


def _record(code, event_id="evt-001", contract_hash="hash-a", resolved_at=None):
    return ck.ContextIntegrityRecord(
        context_event_id=event_id,
        incident_ref=None,
        project_id="proj-1",
        task_id="task-1",
        run_id="run-1",
        actor="watcher",
        detected_by="watcher",
        type=code,
        severity=ck.IncidentSeverity.HIGH,
        expected_context_refs=("ref-a",),
        actual_context_refs=("ref-a",),
        missing_refs=(),
        conflicting_refs=(),
        contract_hash=contract_hash,
        detected_at="2026-01-01T00:00:00Z",
        impact="impact",
        resolution="",
        resolved_at=resolved_at,
        evidence_refs=(),
    )


@pytest.mark.parametrize(
    "code", list(ck.ContextViolation), ids=[c.value for c in ck.ContextViolation]
)
def test_register_append_returns_record_verbatim(code):
    assert code.value in ck.CONTEXT_VIOLATION_TYPES
    stored = ck.Register().append(_record(code.value))
    assert stored == _record(code.value)


def test_register_read_returns_appended_record():
    register = ck.Register()
    record = _record(ck.ContextViolation.CONTEXT_MISSING.value, event_id="evt-7")
    register.append(record)
    assert register.read("evt-7") == record


def test_register_list_unresolved_returns_open_rows_only():
    register = ck.Register()
    register.append(_record(
        ck.ContextViolation.CONTEXT_STALE.value, event_id="evt-open"))
    register.append(_record(
        ck.ContextViolation.CONTEXT_CONFLICT.value,
        event_id="evt-shut",
        resolved_at="2026-01-02T00:00:00Z",
    ))
    rows = register.list_unresolved("proj-1")
    assert [r.context_event_id for r in rows] == ["evt-open"]


def test_recovery_verify_consistent_project_reports_ok():
    _SeededRegister([_record(ck.ContextViolation.CONTEXT_MISSING.value)])
    report = ck.Recovery().verify("proj-1")
    assert report.ok is True
    assert report.code == ck.OK_CODE == "OK"


def test_recovery_verify_conflict_reports_recovery_failed():
    _SeededRegister([
        _record(ck.ContextViolation.CONTEXT_CONFLICT.value, contract_hash="hash-a"),
        _record(ck.ContextViolation.CONTEXT_CONFLICT.value,
                event_id="evt-2", contract_hash="hash-b"),
    ])
    report = ck.Recovery().verify("proj-1")
    assert report.ok is False
    assert report.code == ck.RECOVERY_FAILED_CODE == "CONTEXT_RECOVERY_FAILED"


def test_verify_report_carries_ok_and_code():
    report = ck.Recovery().verify("proj-1")
    assert isinstance(report.ok, bool)
    assert isinstance(report.code, str)


def test_checkpoint_write_returns_pinned_record():
    written = ck.Checkpoints().write_checkpoint(
        project_id="proj-1",
        task_id="task-1",
        run_id="run-1",
        contract_hash="hash-a",
        context_refs=("ref-a",),
    )
    assert written.project_id == "proj-1"
    assert written.contract_hash == "hash-a"
    assert written.context_refs == ("ref-a",)
    assert written.checkpoint_id
    assert written.hash


def test_checkpoint_read_returns_written_checkpoint():
    checkpoints = ck.Checkpoints()
    written = checkpoints.write_checkpoint(
        project_id="proj-1",
        task_id="task-1",
        run_id=None,
        contract_hash="hash-a",
        context_refs=("ref-a",),
    )
    assert checkpoints.read_checkpoint(written.checkpoint_id) == written


def test_recovery_from_checkpoint_reports_ok():
    checkpoints = ck.Checkpoints()
    written = checkpoints.write_checkpoint(
        project_id="proj-1",
        task_id="task-1",
        run_id="run-1",
        contract_hash="hash-a",
        context_refs=("ref-a",),
    )
    report = ck.Recovery().recover("proj-1", written.checkpoint_id)
    assert report.ok is True
    assert report.code == ck.OK_CODE


def test_recovery_from_unknown_checkpoint_reports_recovery_failed():
    report = ck.Recovery().recover("proj-1", "chk-unknown")
    assert report.ok is False
    assert report.code == ck.RECOVERY_FAILED_CODE
