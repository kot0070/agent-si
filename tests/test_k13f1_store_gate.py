"""Lane K13F1 store commit gates: compare_and_set refuses illegal writes.

F1 flow: validate -> version -> MUTABLE -> _extra_check(stored, data) ->
write. A gate failure raises (CommitGateError family) and lands no write.

RED-first: this module imports CommitGateError, which does not exist until
the gate fix lands in src/agent_si/storage/repositories.py.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest

from agent_si.storage import repositories


def _base(rid, project="P1", version=1):
    return {"record_id": rid, "project_id": project, "version": version}


def _amendment(rid="amendments-A1", status="PENDING", **over):
    rec = dict(
        _base(rid),
        amendment_id="am-%s" % rid,
        amendment_sequence=1,
        scope="TASK",
        effective_from="IMMEDIATE",
        target="task:T1",
        change="retry",
        reason="probe",
        created_at="2026-10-26T00:00:00Z",
        source="probe",
        status=status,
    )
    rec.update(over)
    return rec


def test_commit_gate_error_is_value_error():
    assert issubclass(repositories.CommitGateError, ValueError)
    assert issubclass(
        repositories.IllegalTransitionError, repositories.CommitGateError
    )


def test_identity_record_id_swap_refused_no_write():
    repo = repositories.ProjectRepository()
    stored = repo.append(_base("projects-P1"))
    with pytest.raises(repositories.CommitGateError):
        repo.compare_and_set(
            "projects-P1", 1, dict(stored, record_id="projects-EVIL")
        )
    assert repo.load("projects-P1") == stored


def test_identity_project_swap_refused_no_write():
    repo = repositories.ProjectRepository()
    stored = repo.append(_base("projects-P1"))
    with pytest.raises(repositories.CommitGateError):
        repo.compare_and_set(
            "projects-P1", 1, dict(stored, project_id="P-EVIL")
        )
    assert repo.load("projects-P1") == stored


def test_run_illegal_edge_raises_commit_gate_no_write():
    repo = repositories.ExecutionRunRepository()
    stored = repo.append(dict(_base("runs-R1"), status="CREATED"))
    with pytest.raises(repositories.CommitGateError):
        repo.compare_and_set(
            "runs-R1", 1, dict(stored, status="SUCCEEDED")
        )
    assert repo.load("runs-R1") == stored


def test_amendment_bogus_status_refused():
    repo = repositories.AmendmentRepository()
    stored = repo.append(_amendment(status="PENDING"))
    with pytest.raises(repositories.CommitGateError):
        repo.compare_and_set(
            stored["record_id"], 1, dict(stored, status="BOGUS")
        )
    assert repo.load(stored["record_id"]) == stored


def test_amendment_no_return_to_pending():
    repo = repositories.AmendmentRepository()
    stored = repo.append(_amendment(status="APPLIED"))
    with pytest.raises(repositories.CommitGateError):
        repo.compare_and_set(
            stored["record_id"], 1, dict(stored, status="PENDING")
        )
    assert repo.load(stored["record_id"]) == stored


def test_amendment_scope_change_refused():
    repo = repositories.AmendmentRepository()
    stored = repo.append(_amendment(status="PENDING"))
    with pytest.raises(repositories.CommitGateError):
        repo.compare_and_set(
            stored["record_id"], 1, dict(stored, scope="GLOBAL")
        )
    assert repo.load(stored["record_id"]) == stored


def test_amendment_pending_to_applied_accepted():
    repo = repositories.AmendmentRepository()
    stored = repo.append(_amendment(status="PENDING"))
    updated = repo.compare_and_set(
        stored["record_id"], 1, dict(stored, status="APPLIED", version=2)
    )
    assert updated["status"] == "APPLIED"
    assert repo.load(stored["record_id"])["status"] == "APPLIED"


def test_lease_expired_to_active_refused():
    repo = repositories.ResourceLeaseRegistry()
    stored = repo.append(dict(_base("leases-L1"), status="EXPIRED"))
    with pytest.raises(repositories.CommitGateError):
        repo.compare_and_set("leases-L1", 1, dict(stored, status="ACTIVE"))
    assert repo.load("leases-L1") == stored


def test_lease_released_to_active_refused():
    repo = repositories.ResourceLeaseRegistry()
    stored = repo.append(dict(_base("leases-L2"), status="RELEASED"))
    with pytest.raises(repositories.CommitGateError):
        repo.compare_and_set("leases-L2", 1, dict(stored, status="ACTIVE"))
    assert repo.load("leases-L2") == stored


def test_lease_orphaned_to_expired_accepted():
    repo = repositories.ResourceLeaseRegistry()
    stored = repo.append(dict(_base("leases-L3"), status="ORPHANED"))
    updated = repo.compare_and_set(
        "leases-L3", 1, dict(stored, status="EXPIRED", version=2)
    )
    assert updated["status"] == "EXPIRED"


def test_lease_created_to_active_accepted():
    repo = repositories.ResourceLeaseRegistry()
    stored = repo.append(dict(_base("leases-L4"), status="CREATED"))
    updated = repo.compare_and_set(
        "leases-L4", 1, dict(stored, status="ACTIVE", version=2)
    )
    assert updated["status"] == "ACTIVE"


def test_reservation_fulfilled_to_active_refused():
    repo = repositories.ResourceReservationRegistry()
    stored = repo.append(dict(_base("reservations-V1"), status="FULFILLED"))
    with pytest.raises(repositories.CommitGateError):
        repo.compare_and_set(
            "reservations-V1", 1, dict(stored, status="ACTIVE")
        )
    assert repo.load("reservations-V1") == stored


def test_budget_reservation_id_change_refused():
    repo = repositories.BudgetLedger()
    stored = repo.append(
        dict(
            _base("budget-B1"),
            status="CREATED",
            reservation_id="res-1",
            provider_usage_evidence_ref="ev-1",
        )
    )
    with pytest.raises(repositories.CommitGateError):
        repo.compare_and_set(
            "budget-B1", 1, dict(stored, reservation_id="res-2")
        )
    assert repo.load("budget-B1") == stored


def test_budget_evidence_ref_change_refused():
    repo = repositories.BudgetLedger()
    stored = repo.append(
        dict(
            _base("budget-B2"),
            status="CREATED",
            reservation_id="res-1",
            provider_usage_evidence_ref="ev-1",
        )
    )
    with pytest.raises(repositories.CommitGateError):
        repo.compare_and_set(
            "budget-B2", 1, dict(stored, provider_usage_evidence_ref="ev-2")
        )
    assert repo.load("budget-B2") == stored


def test_budget_created_to_active_accepted():
    repo = repositories.BudgetLedger()
    stored = repo.append(
        dict(
            _base("budget-B3"),
            status="CREATED",
            reservation_id="res-1",
            provider_usage_evidence_ref="ev-1",
        )
    )
    updated = repo.compare_and_set(
        "budget-B3", 1, dict(stored, status="ACTIVE", version=2)
    )
    assert updated["status"] == "ACTIVE"


def test_project_unarchive_refused():
    repo = repositories.ProjectRepository()
    stored = repo.append(dict(_base("projects-P9"), archived=True))
    with pytest.raises(repositories.CommitGateError):
        repo.compare_and_set(
            "projects-P9", 1, dict(stored, archived=False)
        )
    assert repo.load("projects-P9") == stored


def test_project_archive_accepted():
    repo = repositories.ProjectRepository()
    stored = repo.append(dict(_base("projects-P8"), archived=False))
    updated = repo.compare_and_set(
        "projects-P8", 1, dict(stored, archived=True, version=2)
    )
    assert updated["archived"] is True
