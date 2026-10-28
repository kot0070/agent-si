"""K08R7 keeper GREEN tests: register/checkpoint persistence plus recovery.

Target: src/agent_si/context_keeper/register.py,
src/agent_si/context_keeper/checkpoints.py,
src/agent_si/context_keeper/recovery.py.
Covers append/read/list, checkpoint write/read round-trip (same-instance
and cross-instance through a tmp store dir), Recovery build from stored
checkpoints, verify/recover ok, plus recovery_failed paths (unknown
checkpoint, verify conflict). Reference doubles below are test-only;
each carries exactly one FAKE-OF line.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_si.context_keeper import interface as ck  # noqa: F401  (pins frozen contract)
from agent_si.context_keeper import checkpoints as keeper_checkpoints
from agent_si.context_keeper import recovery as keeper_recovery
from agent_si.context_keeper import register as keeper_register


# FAKE-OF: agent_si.watcher.journal.append_event
class FakeJournal:
    """Test journal: keeps CONTEXT_CHECKPOINT / CONTEXT_RECOVERY rows."""

    def __init__(self):
        self.calls = []

    def append_event(self, project_id, source, kind, summary, refs):
        entry = SimpleNamespace(
            project_id=project_id,
            source=source,
            kind=kind,
            summary=summary,
            refs=tuple(refs),
        )
        self.calls.append(entry)
        return entry


# FAKE-OF: agent_si.toolguard.escape.check_escape
class FakeGuard:
    """Test guard: allows every path inside the workspace."""

    def __init__(self):
        self.calls = []

    def check_escape(self, agent_id, path, workspace_root):
        self.calls.append((agent_id, path, workspace_root))
        return SimpleNamespace(allowed=True, reason="within workspace")


def _record(event_id="evt-001", contract_hash="hash-a", severity=None,
            expected=("ref-a",), actual=("ref-a",),
            missing=(), conflicting=(), resolved_at=None):
    return ck.ContextIntegrityRecord(
        context_event_id=event_id,
        incident_ref=None,
        project_id="proj-1",
        task_id="task-1",
        run_id="run-1",
        actor="watcher",
        detected_by="watcher",
        type="CONTEXT_MISSING",
        severity=ck.IncidentSeverity.HIGH if severity is None else severity,
        expected_context_refs=tuple(expected),
        actual_context_refs=tuple(actual),
        missing_refs=tuple(missing),
        conflicting_refs=tuple(conflicting),
        contract_hash=contract_hash,
        detected_at="2026-01-01T00:00:00Z",
        impact="impact",
        resolution="",
        resolved_at=resolved_at,
        evidence_refs=(),
    )


def _checkpoint(store, refs=("ref-a",), contract_hash="hash-a"):
    return store.write_checkpoint(
        project_id="proj-1",
        task_id="task-1",
        run_id="run-1",
        contract_hash=contract_hash,
        context_refs=tuple(refs),
    )


# --- register: append/read/list ---

def test_append_returns_record_verbatim():
    store = keeper_register.Register()
    record = _record()
    assert store.append(record) == record
    assert type(store.append(record)).__name__ == "ContextIntegrityRecord"


def test_read_returns_appended_and_none_for_missing():
    store = keeper_register.Register()
    store.append(_record(event_id="evt-7"))
    assert store.read("evt-7") == _record(event_id="evt-7")
    assert store.read("evt-missing") is None


def test_list_unresolved_returns_open_rows_only():
    store = keeper_register.Register()
    store.append(_record(event_id="evt-open"))
    store.append(_record(
        event_id="evt-shut", resolved_at="2026-01-02T00:00:00Z"))
    rows = store.list_unresolved("proj-1")
    assert [row.context_event_id for row in rows] == ["evt-open"]


def test_blocking_incidents_returns_unresolved_high_and_critical():
    store = keeper_register.Register()
    store.append(_record(event_id="evt-high"))
    store.append(_record(
        event_id="evt-crit",
        severity=ck.IncidentSeverity.CRITICAL))
    store.append(_record(
        event_id="evt-soft",
        severity=ck.IncidentSeverity.LOW))
    blocking = store.blocking_incidents("proj-1")
    assert {row.context_event_id for row in blocking} == {
        "evt-high", "evt-crit"}


def test_register_instances_stay_isolated_by_default():
    first = keeper_register.Register()
    first.append(_record())
    assert keeper_register.Register().read("evt-001") is None


# --- register: cross-instance file-backed round-trip ---

def test_register_cross_instance_roundtrip(tmp_path):
    first = keeper_register.Register(store_dir=tmp_path)
    first.append(_record())
    second = keeper_register.Register(store_dir=tmp_path)
    found = second.read("evt-001")
    assert found is not None
    assert found.context_event_id == "evt-001"
    assert found == _record()
    assert [row.context_event_id
            for row in second.list_unresolved("proj-1")] == ["evt-001"]


def test_register_resolved_state_survives_reload(tmp_path):
    first = keeper_register.Register(store_dir=tmp_path)
    first.append(_record())
    first.mark_resolved("evt-001", "fixed", "2026-01-02T00:00:00Z")
    second = keeper_register.Register(store_dir=tmp_path)
    assert second.list_unresolved("proj-1") == []
    assert [row.context_event_id
            for row in second.list_all("proj-1")] == ["evt-001"]


# --- checkpoints: write/read round-trip ---

def test_checkpoint_write_read_roundtrip():
    store = keeper_checkpoints.Checkpoints()
    written = _checkpoint(store)
    assert written.checkpoint_id
    assert written.hash
    assert store.read_checkpoint(written.checkpoint_id) == written
    assert store.read_checkpoint("chk-unknown") is None


def test_checkpoint_cross_instance_roundtrip(tmp_path):
    first = keeper_checkpoints.Checkpoints(store_dir=tmp_path)
    written = _checkpoint(first)
    second = keeper_checkpoints.Checkpoints(store_dir=tmp_path)
    back = second.read_checkpoint(written.checkpoint_id)
    assert back is not None
    assert back.checkpoint_id == written.checkpoint_id
    assert back == written


def test_checkpoint_hooks_keep_optional_call_shapes():
    journal = FakeJournal()
    guard = FakeGuard()
    store = keeper_checkpoints.Checkpoints(
        journal_append=journal.append_event,
        guard_check=guard.check_escape,
        workspace_root="/ws/proj-1",
        store_dir=None,
    )
    written = _checkpoint(store)
    assert len(journal.calls) == 1
    assert journal.calls[0].kind == "CONTEXT_CHECKPOINT"
    assert guard.calls == [("context-keeper",
                            "proj-1/%s.json" % written.checkpoint_id,
                            "/ws/proj-1")]


# --- recovery: build/verify/recover ok ---

def test_recovery_builds_from_checkpoints_only():
    checkpoints = keeper_checkpoints.Checkpoints()
    written = _checkpoint(checkpoints)
    recovery = keeper_recovery.Recovery(checkpoints=checkpoints)
    report = recovery.recover("proj-1", written.checkpoint_id)
    assert report.ok is True
    assert report.code == ck.OK_CODE == "OK"


def test_recovery_builds_from_store_dir(tmp_path):
    keeper_checkpoints.Checkpoints(store_dir=tmp_path)
    recovery = keeper_recovery.Recovery(store_dir=tmp_path)
    report = recovery.verify("proj-1")
    assert report.ok is True
    assert report.code == ck.OK_CODE


def test_recovery_verify_ok_on_good_data():
    register = keeper_register.Register()
    register.append(_record())
    checkpoints = keeper_checkpoints.Checkpoints()
    _checkpoint(checkpoints)
    report = keeper_recovery.Recovery(
        register, checkpoints=checkpoints).verify("proj-1")
    assert report.ok is True
    assert report.code == ck.OK_CODE


def test_recover_from_stored_checkpoint_reports_ok(tmp_path):
    checkpoints = keeper_checkpoints.Checkpoints(store_dir=tmp_path)
    written = _checkpoint(checkpoints)
    register = keeper_register.Register(store_dir=tmp_path)
    register.append(_record(
        event_id="evt-rec", expected=("ref-a",), actual=(),
        missing=("ref-a",)))
    journal = FakeJournal()
    recovery = keeper_recovery.Recovery(
        register,
        checkpoints=keeper_checkpoints.Checkpoints(store_dir=tmp_path),
        journal_append=journal.append_event,
    )
    report = recovery.recover("proj-1", written.checkpoint_id)
    assert report.ok is True
    assert report.code == ck.OK_CODE
    assert register.list_unresolved("proj-1") == []
    assert len(journal.calls) == 1
    assert journal.calls[0].kind == "CONTEXT_RECOVERY"


# --- recovery: recovery_failed paths ---

def test_recover_unknown_checkpoint_reports_recovery_failed():
    register = keeper_register.Register()
    register.append(_record())
    report = keeper_recovery.Recovery(
        register,
        checkpoints=keeper_checkpoints.Checkpoints(),
    ).recover("proj-1", "chk-unknown")
    assert report.ok is False
    assert report.code == ck.RECOVERY_FAILED_CODE == "CONTEXT_RECOVERY_FAILED"


def test_verify_conflict_reports_recovery_failed():
    register = keeper_register.Register()
    register.append(_record(event_id="evt-1", contract_hash="hash-a"))
    register.append(_record(event_id="evt-2", contract_hash="hash-b"))
    report = keeper_recovery.Recovery(register).verify("proj-1")
    assert report.ok is False
    assert report.code == ck.RECOVERY_FAILED_CODE


def test_recover_uncovered_conflict_reports_recovery_failed():
    register = keeper_register.Register()
    register.append(_record(event_id="evt-1", contract_hash="hash-a"))
    register.append(_record(
        event_id="evt-2", contract_hash="hash-b",
        expected=("ref-keep",), actual=(), missing=("ref-keep",)))
    checkpoints = keeper_checkpoints.Checkpoints()
    written = _checkpoint(checkpoints)
    report = keeper_recovery.Recovery(
        register, checkpoints=checkpoints).recover(
        "proj-1", written.checkpoint_id)
    assert report.ok is False
    assert report.code == ck.RECOVERY_FAILED_CODE
    assert [row.context_event_id
            for row in register.list_unresolved("proj-1")] == ["evt-2"]
