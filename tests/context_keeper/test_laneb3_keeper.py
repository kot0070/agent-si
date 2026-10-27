"""Lane B STEP2 keeper tests (RED before B-S2-3 realisation, GREEN after).

Target: src/agent_si/context_keeper/register.py,
src/agent_si/context_keeper/recovery.py,
src/agent_si/context_keeper/checkpoints.py.
Frozen inputs: src/agent_si/context_keeper/interface.py shapes
(Register.append/read/list_unresolved, Recovery.verify/recover,
Checkpoints.write_checkpoint/read_checkpoint, CONTEXT_VIOLATION_TYPES order,
OK_CODE, RECOVERY_FAILED_CODE, IncidentSeverity LOW/MEDIUM/HIGH/CRITICAL);
K13 manifest f256bab4 plus V5 cd6fbd6d/e9c2d320 (K13 names reused exactly,
never redefined); 0C wins clashes. ROWS cover: verbatim append-only
register read at every level start with schedule/trigger violations
authoritative, recovery check before continuation with HIGH/CRITICAL
unresolved blocking PASS (45A/SPEC45/45A); cancel keeps history (45B);
IncidentSeverity (46); PRESERVED/CHANGED/MISSING/CONTRADICTED (0A);
LOGICAL_ONLY default (4); save-restore benchmarked vs keeper
sourced-or-UNKNOWN (M-P4-160); hash mismatch blocks CONTEXT_RECOVERY_FAILED
(P13); keeper benchmark sourced-or-UNKNOWN.
Reference doubles below are test-only; each carries exactly one FAKE-OF line.
"""

import dataclasses
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_si.context_keeper import interface as ck
from agent_si.context_keeper import checkpoints as keeper_checkpoints
from agent_si.context_keeper import recovery as keeper_recovery
from agent_si.context_keeper import register as keeper_register


# FAKE-OF: agent_si.watcher.journal.append_event
class FakeJournal:
    """Test journal: keeps CONTEXT_CHECKPOINT / CONTEXT_RECOVERY rows."""

    KINDS = ("CONTEXT_CHECKPOINT", "CONTEXT_RECOVERY")

    def __init__(self):
        self.calls = []
        self._seq = 0

    def append_event(self, project_id, source, kind, summary, refs):
        if kind not in self.KINDS:
            raise ValueError("unknown journal kind: %r" % (kind,))
        self._seq += 1
        entry = SimpleNamespace(
            entry_id="evt-%04d" % self._seq,
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
    """Test guard: allows paths inside the workspace, blocks escapes."""

    def __init__(self, denied=()):
        self.calls = []
        self.denied = tuple(denied)

    def check_escape(self, agent_id, path, workspace_root):
        self.calls.append((agent_id, path, workspace_root))
        allowed = path not in self.denied and ".." not in path.split("/")
        return SimpleNamespace(
            allowed=allowed,
            reason="within workspace" if allowed else "workspace escape blocked",
        )


# FAKE-OF: agent_si.backend.stop_all.request_stop
class FakeStopAll:
    """Test stop-all: records stop requests."""

    def __init__(self):
        self.calls = []

    def request_stop(self, project_id, reason):
        self.calls.append((project_id, reason))
        return SimpleNamespace(project_id=project_id, stopped=True, reason=reason)


def _record(code, event_id="evt-001", project_id="proj-1",
            severity=None, contract_hash="hash-a",
            expected=("ref-a",), actual=("ref-a",),
            missing=(), conflicting=(), resolved_at=None):
    return ck.ContextIntegrityRecord(
        context_event_id=event_id,
        incident_ref=None,
        project_id=project_id,
        task_id="task-1",
        run_id="run-1",
        actor="watcher",
        detected_by="watcher",
        type=code,
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


def _checkpoint(store, project_id="proj-1", contract_hash="hash-a",
                refs=("ref-a",)):
    return store.write_checkpoint(
        project_id=project_id,
        task_id="task-1",
        run_id="run-1",
        contract_hash=contract_hash,
        context_refs=tuple(refs),
    )


# --- frozen pins (K13 names reused exactly, never redefined) ---

def test_violation_types_order_exact():
    assert ck.CONTEXT_VIOLATION_TYPES == (
        "CONTEXT_MISSING",
        "CONTEXT_STALE",
        "CONTEXT_CONFLICT",
        "CONTEXT_TRUNCATED",
        "CONTEXT_UNAUTHORIZED_EXPANSION",
        "CONTEXT_WRONG_TASK",
        "CONTEXT_WRONG_CONTRACT_VERSION",
        "CONTEXT_ARTIFACT_UNAVAILABLE",
        "CONTEXT_RECOVERY_FAILED",
        "CONTEXT_SUMMARY_DRIFT",
    )


def test_ok_and_recovery_failed_codes_exact():
    assert ck.OK_CODE == "OK"
    assert ck.RECOVERY_FAILED_CODE == "CONTEXT_RECOVERY_FAILED"


def test_incident_severity_names_exact():
    assert [level.value for level in ck.IncidentSeverity] == [
        "LOW", "MEDIUM", "HIGH", "CRITICAL"]


def test_keeper_reuses_frozen_names():
    assert keeper_register.IncidentSeverity is ck.IncidentSeverity
    assert keeper_register.ContextIntegrityRecord is ck.ContextIntegrityRecord
    assert keeper_recovery.VerifyReport is ck.VerifyReport
    assert keeper_checkpoints.CheckpointRecord is ck.CheckpointRecord


# --- register: verbatim append-only (45A) ---

@pytest.mark.parametrize(
    "code", list(ck.CONTEXT_VIOLATION_TYPES),
    ids=list(ck.CONTEXT_VIOLATION_TYPES),
)
def test_append_returns_record_verbatim(code):
    store = keeper_register.Register()
    record = _record(code, event_id="evt-%s" % code)
    assert store.append(record) == record


def test_append_duplicate_event_id_returns_stored_row():
    store = keeper_register.Register()
    first = _record("CONTEXT_MISSING", event_id="evt-dup")
    second = _record("CONTEXT_STALE", event_id="evt-dup")
    assert store.append(first) == first
    assert store.append(second) == first
    assert store.read("evt-dup") == first


def test_append_rejects_unknown_violation_type():
    store = keeper_register.Register()
    with pytest.raises(ValueError):
        store.append(_record("CONTEXT_NO_SUCH_TYPE", event_id="evt-bad"))


def test_append_rejects_non_severity():
    store = keeper_register.Register()
    record = dataclasses.replace(_record("CONTEXT_MISSING"), severity="HIGH")
    with pytest.raises(ValueError):
        store.append(record)


def test_read_returns_appended_and_none_for_missing():
    store = keeper_register.Register()
    record = _record("CONTEXT_MISSING", event_id="evt-7")
    store.append(record)
    assert store.read("evt-7") == record
    assert store.read("evt-missing") is None


def test_list_unresolved_returns_open_rows_only():
    store = keeper_register.Register()
    store.append(_record("CONTEXT_STALE", event_id="evt-open"))
    store.append(_record("CONTEXT_CONFLICT", event_id="evt-shut",
                         resolved_at="2026-01-02T00:00:00Z"))
    rows = store.list_unresolved("proj-1")
    assert [row.context_event_id for row in rows] == ["evt-open"]


# --- register: read at every level start, violations authoritative (45A) ---

def test_level_start_reinjects_unresolved_verbatim():
    store = keeper_register.Register()
    stale = _record("CONTEXT_STALE", event_id="evt-stale",
                    expected=("schedule-a",), actual=("schedule-a",))
    wrong_task = _record("CONTEXT_WRONG_TASK", event_id="evt-trigger",
                        expected=("trigger-a",), actual=("trigger-a",))
    store.append(stale)
    store.append(wrong_task)
    bundle = store.read_for_level_start("proj-1")
    assert bundle.project_id == "proj-1"
    assert bundle.unresolved == (stale, wrong_task)
    assert "schedule-a" in bundle.refs
    assert "trigger-a" in bundle.refs
    assert bundle.blocked is True


def test_level_start_bundle_empty_project_passes():
    bundle = keeper_register.Register().read_for_level_start("proj-1")
    assert bundle.unresolved == ()
    assert bundle.refs == ()
    assert bundle.blocked is False


@pytest.mark.parametrize("severity", ("HIGH", "CRITICAL"))
def test_level_start_blocked_on_high_and_critical(severity):
    store = keeper_register.Register()
    store.append(_record("CONTEXT_MISSING", event_id="evt-block",
                         severity=ck.IncidentSeverity(severity),
                         expected=("ref-a",), actual=()))
    bundle = store.read_for_level_start("proj-1")
    assert bundle.blocked is True
    assert store.blocking_incidents("proj-1") != []


@pytest.mark.parametrize("severity", ("LOW", "MEDIUM"))
def test_level_start_passes_without_blocking_severity(severity):
    store = keeper_register.Register()
    store.append(_record("CONTEXT_TRUNCATED", event_id="evt-soft",
                         severity=ck.IncidentSeverity(severity),
                         expected=("ref-a",), actual=("ref-a",)))
    bundle = store.read_for_level_start("proj-1")
    assert bundle.blocked is False
    assert store.blocking_incidents("proj-1") == []


# --- cancel keeps history, LOGICAL_ONLY default (45B, 4) ---

def test_cancel_keeps_history():
    store = keeper_register.Register()
    record = _record("CONTEXT_MISSING", event_id="evt-cancel")
    store.append(record)
    retained = store.cancel_run("proj-1", "run-1")
    assert retained == 1
    assert store.read("evt-cancel") == record
    assert [row.context_event_id
            for row in store.list_unresolved("proj-1")] == ["evt-cancel"]
    assert [row.context_event_id
            for row in store.list_all("proj-1")] == ["evt-cancel"]


def test_cancel_defaults_logical_only_and_rejects_physical():
    store = keeper_register.Register()
    store.append(_record("CONTEXT_MISSING", event_id="evt-c"))
    assert keeper_register.CANCEL_SCOPE_DEFAULT == "LOGICAL_ONLY"
    assert store.cancel_run("proj-1", "run-1") == 1
    with pytest.raises(ValueError):
        store.cancel_run("proj-1", "run-1", scope="PHYSICAL")


def test_resolve_keeps_row_in_history():
    store = keeper_register.Register()
    store.append(_record("CONTEXT_MISSING", event_id="evt-r"))
    updated = store.mark_resolved("evt-r", "fixed", "2026-01-02T00:00:00Z")
    assert updated.resolved_at == "2026-01-02T00:00:00Z"
    assert store.list_unresolved("proj-1") == []
    assert [row.context_event_id
            for row in store.list_all("proj-1")] == ["evt-r"]


def test_resolve_unknown_event_id_raises():
    with pytest.raises(KeyError):
        keeper_register.Register().mark_resolved("evt-nope", "fixed", "now")


# --- reference states PRESERVED/CHANGED/MISSING/CONTRADICTED (0A) ---

def test_ref_states_exact():
    assert keeper_register.REF_STATES == (
        "PRESERVED", "CHANGED", "MISSING", "CONTRADICTED")


def test_compare_refs_matrix():
    states, extra = keeper_register.compare_refs(
        ("ref-keep", "ref-edit", "ref-gone", "ref-clash"),
        ("ref-keep", "ref-edit", "ref-extra"),
        conflicting_refs=("ref-clash",),
        changed_refs=("ref-edit",),
    )
    assert states == {
        "ref-keep": "PRESERVED",
        "ref-edit": "CHANGED",
        "ref-gone": "MISSING",
        "ref-clash": "CONTRADICTED",
    }
    assert extra == ("ref-extra",)


def test_compare_refs_empty_is_preserved_free():
    states, extra = keeper_register.compare_refs((), ())
    assert states == {}
    assert extra == ()


# --- provenance: keeper sourced-or-UNKNOWN ---

def test_provenance_sourced_or_unknown():
    store = keeper_register.Register()
    store.append(_record("CONTEXT_MISSING", event_id="evt-p",
                         expected=("ref-a",), actual=("ref-a",)))
    assert store.provenance("proj-1", "ref-a") == keeper_register.SOURCED
    assert store.provenance("proj-1", "ref-ghost") == keeper_register.UNKNOWN
    assert store.provenance("proj-other", "ref-a") == keeper_register.UNKNOWN


# --- checkpoints: pin contract hash plus refs ---

def test_write_checkpoint_returns_pinned_record():
    store = keeper_checkpoints.Checkpoints()
    written = _checkpoint(store)
    assert written.project_id == "proj-1"
    assert written.contract_hash == "hash-a"
    assert written.context_refs == ("ref-a",)
    assert written.checkpoint_id
    assert written.hash


def test_write_checkpoint_is_idempotent():
    store = keeper_checkpoints.Checkpoints()
    assert _checkpoint(store) == _checkpoint(store)


def test_read_checkpoint_returns_written_and_none_for_missing():
    store = keeper_checkpoints.Checkpoints()
    written = _checkpoint(store)
    assert store.read_checkpoint(written.checkpoint_id) == written
    assert store.read_checkpoint("chk-unknown") is None


def test_write_checkpoint_emits_checkpoint_kind_row():
    journal = FakeJournal()
    store = keeper_checkpoints.Checkpoints(journal_append=journal.append_event)
    written = _checkpoint(store)
    assert len(journal.calls) == 1
    assert journal.calls[0].kind == "CONTEXT_CHECKPOINT"
    assert written.checkpoint_id in journal.calls[0].summary


def test_write_checkpoint_guard_allows_inside():
    guard = FakeGuard()
    store = keeper_checkpoints.Checkpoints(
        guard_check=guard.check_escape, workspace_root="/ws/proj-1")
    written = _checkpoint(store)
    assert store.read_checkpoint(written.checkpoint_id) == written
    assert guard.calls == [("context-keeper",
                            "proj-1/%s.json" % written.checkpoint_id,
                            "/ws/proj-1")]


def test_write_checkpoint_guard_denial_blocks_write():
    guard = FakeGuard(denied=("proj-1/chk-x.json",))
    store = keeper_checkpoints.Checkpoints(
        guard_check=guard.check_escape, workspace_root="/ws/proj-1")
    real_hash = keeper_checkpoints.hash_refs
    try:
        keeper_checkpoints.hash_refs = lambda *args: "x" * 64
        with pytest.raises(ValueError):
            _checkpoint(store)
    finally:
        keeper_checkpoints.hash_refs = real_hash
    assert store.latest_for_project("proj-1") is None


def test_latest_for_project_returns_last_write():
    store = keeper_checkpoints.Checkpoints()
    first = _checkpoint(store, refs=("ref-a",))
    second = _checkpoint(store, refs=("ref-b",))
    assert store.latest_for_project("proj-1") == second
    assert store.latest_for_project("proj-other") is None
    assert first != second


# --- save-restore benchmarked vs keeper sourced-or-UNKNOWN (M-P4-160) ---

def test_benchmark_save_restore_roundtrip_ok():
    store = keeper_checkpoints.Checkpoints()
    register = keeper_register.Register()
    register.append(_record("CONTEXT_MISSING", event_id="evt-bm",
                            expected=("ref-a",), actual=("ref-a",)))
    report = store.benchmark_save_restore(
        project_id="proj-1", task_id="task-1", run_id="run-1",
        contract_hash="hash-a", context_refs=("ref-a",),
        provenance_fn=lambda ref: register.provenance("proj-1", ref))
    assert report.restored_ok is True
    assert report.saved_refs == ("ref-a",)
    assert report.restored_refs == ("ref-a",)
    assert report.markers == (("ref-a", keeper_register.SOURCED),)
    assert report.sourced_count == 1
    assert report.unknown_count == 0


def test_benchmark_save_restore_marks_unknown():
    store = keeper_checkpoints.Checkpoints()
    register = keeper_register.Register()
    report = store.benchmark_save_restore(
        project_id="proj-1", task_id="task-1", run_id="run-1",
        contract_hash="hash-a", context_refs=("ref-a", "ref-ghost"),
        provenance_fn=lambda ref: register.provenance("proj-1", ref))
    assert report.restored_ok is True
    assert report.sourced_count == 0
    assert report.unknown_count == 2
    assert report.markers == (("ref-a", keeper_register.UNKNOWN),
                              ("ref-ghost", keeper_register.UNKNOWN))


# --- recovery: check before continuation (45A) ---

def _recovery(register=None, checkpoints=None,
              journal=None, stop_all=None):
    return keeper_recovery.Recovery(
        register if register is not None else keeper_register.Register(),
        checkpoints=checkpoints,
        journal_append=journal.append_event if journal is not None else None,
        request_stop=stop_all.request_stop if stop_all is not None else None,
    )


def test_verify_empty_project_reports_ok():
    report = _recovery().verify("proj-1")
    assert report.ok is True
    assert report.code == ck.OK_CODE == "OK"


def test_verify_consistent_project_reports_ok():
    register = keeper_register.Register()
    register.append(_record("CONTEXT_MISSING", event_id="evt-ok",
                            severity=ck.IncidentSeverity.MEDIUM,
                            expected=("ref-a",), actual=("ref-a",)))
    checkpoints = keeper_checkpoints.Checkpoints()
    _checkpoint(checkpoints)
    report = _recovery(register, checkpoints).verify("proj-1")
    assert report.ok is True
    assert report.code == ck.OK_CODE


def test_verify_high_unresolved_blocks():
    register = keeper_register.Register()
    register.append(_record("CONTEXT_MISSING", event_id="evt-high",
                            severity=ck.IncidentSeverity.HIGH,
                            expected=("ref-a",), actual=("ref-a",)))
    report = _recovery(register).verify("proj-1")
    assert report.ok is False
    assert report.code == ck.RECOVERY_FAILED_CODE == "CONTEXT_RECOVERY_FAILED"


def test_verify_critical_unresolved_blocks():
    register = keeper_register.Register()
    register.append(_record("CONTEXT_CONFLICT", event_id="evt-crit",
                            severity=ck.IncidentSeverity.CRITICAL,
                            expected=("ref-a",), actual=("ref-a",)))
    report = _recovery(register).verify("proj-1")
    assert report.ok is False
    assert report.code == ck.RECOVERY_FAILED_CODE


def test_verify_hash_mismatch_blocks_recovery_failed():
    register = keeper_register.Register()
    register.append(_record("CONTEXT_CONFLICT", event_id="evt-p13",
                            severity=ck.IncidentSeverity.MEDIUM,
                            contract_hash="hash-a",
                            expected=("ref-a",), actual=("ref-a",)))
    checkpoints = keeper_checkpoints.Checkpoints()
    _checkpoint(checkpoints, contract_hash="hash-b", refs=("ref-a",))
    report = _recovery(register, checkpoints).verify("proj-1")
    assert report.ok is False
    assert report.code == ck.RECOVERY_FAILED_CODE


def test_verify_tampered_checkpoint_blocks():
    checkpoints = keeper_checkpoints.Checkpoints()
    written = _checkpoint(checkpoints)
    checkpoints._by_id[written.checkpoint_id] = dataclasses.replace(
        written, hash="0" * 64)
    report = _recovery(keeper_register.Register(), checkpoints).verify("proj-1")
    assert report.ok is False
    assert report.code == ck.RECOVERY_FAILED_CODE


def test_verify_missing_required_ref_blocks():
    register = keeper_register.Register()
    register.append(_record("CONTEXT_MISSING", event_id="evt-req",
                            severity=ck.IncidentSeverity.LOW,
                            expected=("ref-a",), actual=()))
    report = _recovery(register).verify("proj-1")
    assert report.ok is False
    assert report.code == ck.RECOVERY_FAILED_CODE


def test_verify_mixed_contract_hashes_block():
    register = keeper_register.Register()
    register.append(_record("CONTEXT_CONFLICT", event_id="evt-1",
                            severity=ck.IncidentSeverity.MEDIUM,
                            contract_hash="hash-a",
                            expected=("ref-a",), actual=("ref-a",)))
    register.append(_record("CONTEXT_CONFLICT", event_id="evt-2",
                            severity=ck.IncidentSeverity.MEDIUM,
                            contract_hash="hash-b",
                            expected=("ref-a",), actual=("ref-a",)))
    report = _recovery(register).verify("proj-1")
    assert report.ok is False
    assert report.code == ck.RECOVERY_FAILED_CODE


# --- recovery: recover restores refs then verifies ---

def test_recover_from_checkpoint_reports_ok():
    journal = FakeJournal()
    register = keeper_register.Register()
    register.append(_record("CONTEXT_MISSING", event_id="evt-rec",
                            severity=ck.IncidentSeverity.HIGH,
                            expected=("ref-a",), actual=(),
                            missing=("ref-a",)))
    checkpoints = keeper_checkpoints.Checkpoints()
    written = _checkpoint(checkpoints)
    report = _recovery(register, checkpoints, journal).recover(
        "proj-1", written.checkpoint_id)
    assert report.ok is True
    assert report.code == ck.OK_CODE
    assert register.list_unresolved("proj-1") == []
    assert len(journal.calls) == 1
    assert journal.calls[0].kind == "CONTEXT_RECOVERY"
    assert written.checkpoint_id in journal.calls[0].refs


def test_recover_unknown_checkpoint_reports_recovery_failed():
    journal = FakeJournal()
    register = keeper_register.Register()
    register.append(_record("CONTEXT_MISSING", event_id="evt-rec",
                            severity=ck.IncidentSeverity.LOW,
                            expected=("ref-a",), actual=("ref-a",)))
    checkpoints = keeper_checkpoints.Checkpoints()
    report = _recovery(register, checkpoints, journal).recover(
        "proj-1", "chk-unknown")
    assert report.ok is False
    assert report.code == ck.RECOVERY_FAILED_CODE
    assert len(journal.calls) == 1
    assert journal.calls[0].kind == "CONTEXT_RECOVERY"


def test_recover_wrong_project_checkpoint_fails():
    journal = FakeJournal()
    checkpoints = keeper_checkpoints.Checkpoints()
    written = _checkpoint(checkpoints, project_id="proj-other")
    report = _recovery(keeper_register.Register(),
                       checkpoints, journal).recover(
        "proj-1", written.checkpoint_id)
    assert report.ok is False
    assert report.code == ck.RECOVERY_FAILED_CODE


def test_recover_calls_stop_all_on_remaining_critical():
    journal = FakeJournal()
    stop_all = FakeStopAll()
    register = keeper_register.Register()
    register.append(_record("CONTEXT_CONFLICT", event_id="evt-crit",
                            severity=ck.IncidentSeverity.CRITICAL,
                            expected=("ref-keep",), actual=(),
                            missing=("ref-keep",)))
    checkpoints = keeper_checkpoints.Checkpoints()
    written = _checkpoint(checkpoints, refs=("ref-a",))
    report = _recovery(register, checkpoints, journal,
                       stop_all).recover("proj-1", written.checkpoint_id)
    assert report.ok is False
    assert report.code == ck.RECOVERY_FAILED_CODE
    assert stop_all.calls == [
        ("proj-1", "critical context incident unresolved after recovery")]
    assert len(journal.calls) == 1


def test_recover_leaves_uncovered_rows_unresolved():
    register = keeper_register.Register()
    register.append(_record("CONTEXT_MISSING", event_id="evt-keep",
                            severity=ck.IncidentSeverity.MEDIUM,
                            expected=("ref-keep",), actual=(),
                            missing=("ref-keep",)))
    checkpoints = keeper_checkpoints.Checkpoints()
    written = _checkpoint(checkpoints, refs=("ref-a",))
    report = _recovery(register, checkpoints).recover(
        "proj-1", written.checkpoint_id)
    assert report.ok is False
    assert [row.context_event_id
            for row in register.list_unresolved("proj-1")] == ["evt-keep"]
