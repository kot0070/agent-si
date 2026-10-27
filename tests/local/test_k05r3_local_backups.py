"""K05R3 backup tests: versioned backups plus owner gate (M-D-D16)."""
from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))

from agent_si.local import config  # noqa: E402
from agent_si.local import k05r3_backups as backups  # noqa: E402


def _decision(project, gate_id, statement=None, authority="owner"):
    return config.record_decision(
        project,
        statement if statement is not None else "answer %s: proceed" % gate_id,
        "owner resolution",
        authority,
    )


def test_keep_and_serve_current():
    store = backups.VersionedBackupStore()
    ref = store.keep("kb-main", "content-v1")
    assert ref == "kb-main@v1"
    assert store.current_ref("kb-main") == ref
    assert store.serve_current(ref) == "content-v1"


def test_stale_never_served_as_current():
    store = backups.VersionedBackupStore()
    old = store.keep("kb-main", "content-v1")
    new = store.keep("kb-main", "content-v2")
    assert store.list_versions("kb-main") == (old, new)
    assert store.serve_current(new) == "content-v2"
    with pytest.raises(backups.BackupError) as excinfo:
        store.serve_current(old)
    assert excinfo.value.code == backups.K05R3_BACKUP_STALE_AS_CURRENT_REFUSED
    assert store.serve_backup(old) == "content-v1"
    assert store.serve_backup(new) == "content-v2"


def test_unknown_keys_and_refs_refused():
    store = backups.VersionedBackupStore()
    for call in (
        lambda: store.serve_current("kb-missing@v1"),
        lambda: store.serve_current("not-a-ref"),
        lambda: store.serve_backup("kb-missing@v1"),
        lambda: store.current_ref("kb-missing"),
        lambda: store.list_versions("kb-missing"),
    ):
        with pytest.raises(backups.BackupError) as excinfo:
            call()
        assert excinfo.value.code == backups.K05R3_BACKUP_UNKNOWN_REFUSED
    with pytest.raises(backups.BackupError) as excinfo:
        store.keep("", "x")
    assert excinfo.value.code == backups.K05R3_BACKUP_UNKNOWN_REFUSED


def test_owner_gate_closes_on_owner_decision():
    book = backups.OwnerGateBook()
    gate = book.open_gate("gate-1", "proj-a", "stale copy kb-main: keep as backup?")
    assert gate.state == backups.GATE_OPEN
    assert gate.asked_to == "owner"
    assert book.state_of("gate-1").state == backups.GATE_OPEN
    closed = book.close_gate("gate-1", _decision("proj-a", "gate-1"))
    assert closed.state == backups.GATE_CLOSED
    assert closed.decided_by is not None
    assert book.state_of("gate-1").state == backups.GATE_CLOSED


def test_owner_gate_close_refused_without_matching_decision():
    book = backups.OwnerGateBook()
    book.open_gate("gate-1", "proj-a", "stale copy kb-main: keep as backup?")
    with pytest.raises(backups.OwnerGateError) as excinfo:
        book.close_gate("gate-1", {"decision_id": "dec-1"})
    assert excinfo.value.code == backups.K05R3_OWNER_GATE_DECISION_REFUSED
    with pytest.raises(backups.OwnerGateError) as excinfo:
        book.close_gate("gate-1", _decision("proj-other", "gate-1"))
    assert excinfo.value.code == backups.K05R3_OWNER_GATE_DECISION_REFUSED
    with pytest.raises(backups.OwnerGateError) as excinfo:
        book.close_gate("gate-1", _decision("proj-a", "gate-1", statement="unrelated"))
    assert excinfo.value.code == backups.K05R3_OWNER_GATE_DECISION_REFUSED
    with pytest.raises(backups.OwnerGateError) as excinfo:
        book.close_gate(
            "gate-1", _decision("proj-a", "gate-1", authority="someone-else")
        )
    assert excinfo.value.code == backups.K05R3_OWNER_GATE_DECISION_REFUSED
    with pytest.raises(backups.OwnerGateError) as excinfo:
        book.close_gate("gate-1", _decision("proj-a", "gate-1", authority=""))
    assert excinfo.value.code == backups.K05R3_OWNER_GATE_DECISION_REFUSED
    assert book.state_of("gate-1").state == backups.GATE_OPEN


def test_owner_gate_state_edges():
    book = backups.OwnerGateBook()
    with pytest.raises(backups.OwnerGateError) as excinfo:
        book.state_of("gate-missing")
    assert excinfo.value.code == backups.K05R3_OWNER_GATE_STATE_REFUSED
    book.open_gate("gate-1", "proj-a", "question?")
    with pytest.raises(backups.OwnerGateError) as excinfo:
        book.open_gate("gate-1", "proj-a", "question?")
    assert excinfo.value.code == backups.K05R3_OWNER_GATE_STATE_REFUSED
    book.close_gate("gate-1", _decision("proj-a", "gate-1"))
    with pytest.raises(backups.OwnerGateError) as excinfo:
        book.close_gate("gate-1", _decision("proj-a", "gate-1"))
    assert excinfo.value.code == backups.K05R3_OWNER_GATE_STATE_REFUSED


def test_error_codes_new_module_only():
    assert tuple(backups.ERROR_CODES_K05R3_BACKUPS) == (
        "K05R3_BACKUP_STALE_AS_CURRENT_REFUSED",
        "K05R3_BACKUP_UNKNOWN_REFUSED",
        "K05R3_OWNER_GATE_DECISION_REFUSED",
        "K05R3_OWNER_GATE_STATE_REFUSED",
    )
