"""Lane S storage sweep: every domain has a repo + a migration (Manifest §42/§41).

Covers repositories.py (§42 ports), migrations_k13.sql (additive tables for
every authoritative domain), report_dataset.py (§59 frozen key set), and the
core-imports-no-adapter rule (0C sec 12: core never imports adapters).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest

from agent_si.reports import report_dataset
from agent_si.storage import repositories
from iface.frozen_manifest import manifest

MANIFEST_DOC = ROOT / "iface" / "frozen_manifest" / "K13_MANIFEST.md"
MIGRATION_SQL = ROOT / "src" / "agent_si" / "adapters" / "sqlite" / "migrations_k13.sql"

# domain -> (repository class, migration table)
DOMAIN_COVERAGE = [
    ("projects", repositories.ProjectRepository, "projects"),
    ("contracts", repositories.TaskContractRepository, "task_contracts"),
    ("activations", repositories.ContractActivationLog, "contract_activations"),
    ("transitions", repositories.TaskTransitionLog, "task_transitions"),
    ("runs", repositories.ExecutionRunRepository, "execution_runs"),
    ("attempts", repositories.ExecutionAttemptLog, "execution_attempts"),
    ("amendments", repositories.AmendmentRepository, "amendments"),
    ("policies", repositories.PolicyRepository, "routing_policies"),
    ("policy_lifecycle", repositories.PolicyLifecycleLog, "policy_lifecycle_records"),
    ("counters", repositories.RetryFallbackCounterStore, "rework_counter_records"),
    ("verification", repositories.VerificationLog, "verification_records"),
    ("suspension", repositories.SuspensionLog, "suspension_records"),
    ("routing", repositories.RoutingDecisionLog, "routing_decisions"),
    ("routing_snapshots", repositories.RoutingEvidenceSnapshotLog, "routing_evidence_snapshots"),
    ("leases", repositories.ResourceLeaseRegistry, "resource_leases"),
    ("reservations", repositories.ResourceReservationRegistry, "resource_reservations"),
    ("budget", repositories.BudgetLedger, "budget_reservations"),
    ("telemetry", repositories.TelemetryEventRepository, "telemetry_events"),
    ("metrics", repositories.MetricRecordRepository, "metric_records"),
    ("governance", repositories.GovernanceArtifactLog, "governance_artifacts"),
    ("decisions", repositories.DecisionLog, "decision_records"),
    ("finalization", repositories.FinalizationLog, "finalization_records"),
    ("context_integrity", repositories.ContextIntegrityLog, "context_integrity_records"),
    ("incidents", repositories.IncidentIndex, "incident_records"),
]


def _minimal_record(domain, seq="S-1", version=1):
    return {
        "record_id": "%s-%s" % (domain, seq),
        "project_id": "P1",
        "version": version,
    }


def _transition(seq="T-1", src="CREATED", dst="PACKAGED"):
    """Full frozen transition field set (manifest TRANSITION_FIELDS)."""
    return {
        "record_id": "transitions-%s" % seq,
        "project_id": "P1",
        "version": 1,
        "transition_id": "tr-%s" % seq,
        "task_id": "T1",
        "run_id": None,
        "transition_sequence": 1,
        "expected_from_state": src,
        "expected_state_version": 1,
        "new_state_version": 2,
        "actor": "probe",
        "from": src,
        "to": dst,
        "reason": "probe",
        "timestamp": "2026-10-26T00:00:00Z",
        "evidence_ref": None,
        "suspended_from_state": None,
        "resume_target_state": None,
    }


def test_manifest_verified():
    assert manifest.MANIFEST_SHA256 == "f256bab4d31be3cd9e86c22a1bdcef90b08ad62500a8eca2051705cc0a9b0690"
    assert manifest.verify_manifest(MANIFEST_DOC) is True


def test_every_domain_has_repo():
    for domain, cls, _table in DOMAIN_COVERAGE:
        repo = cls() if cls is not repositories.RetryFallbackCounterStore else cls()
        for op in ("load", "append", "list_by"):
            assert callable(getattr(repo, op, None)), (domain, op)
        # RepositoryPort is a non-runtime-checkable Protocol in the frozen
        # stub: branch on the structural port shape instead of isinstance.
        if hasattr(repo, "compare_and_set"):
            assert callable(repo.compare_and_set)
        else:  # counter port shape
            assert callable(repo.increment)


def test_every_domain_has_migration():
    sql = MIGRATION_SQL.read_text(encoding="utf-8")
    lowered = sql.lower()
    for _domain, _cls, table in DOMAIN_COVERAGE:
        assert "create table if not exists %s" % table in lowered, table
    assert "drop table" not in lowered  # additive only


def test_migration_carries_backup_validation_rollback_notes():
    sql = MIGRATION_SQL.read_text(encoding="utf-8")
    lowered = sql.lower()
    assert "backup" in lowered
    assert "validation" in lowered
    assert "rollback" in lowered


def test_core_imports_no_adapter():
    checked = []
    for path in [
        ROOT / "src" / "agent_si" / "storage" / "repositories.py",
        ROOT / "src" / "agent_si" / "reports" / "report_dataset.py",
    ]:
        src = path.read_text(encoding="utf-8").lower()
        assert "sqlite" not in src, path
        assert "agent_si.adapters" not in src, path
        checked.append(path)
    telemetry_dir = ROOT / "src" / "agent_si" / "telemetry"
    for path in sorted(telemetry_dir.glob("*.py")):
        src = path.read_text(encoding="utf-8").lower()
        assert "sqlite" not in src, path
        assert "agent_si.adapters" not in src, path
        checked.append(path)
    assert checked, "no core files inspected"


def test_repo_ops_roundtrip():
    repo = repositories.ProjectRepository()
    assert repo.load("missing") is None
    stored = repo.append(_minimal_record("projects"))
    assert repo.load(stored["record_id"]) == stored
    # duplicate idempotent key returns the stored record
    assert repo.append(dict(stored, version=99)) == stored
    assert repo.load(stored["record_id"])["version"] == 1


def test_compare_and_set_guards_mutable_aggregates():
    repo = repositories.ExecutionRunRepository()
    record = dict(
        _minimal_record("runs"),
        status="RUNNING",
        from_status="CREATED",
        to_status="RUNNING",
    )
    repo.append(record)
    with pytest.raises(repositories.VersionConflictError):
        repo.compare_and_set(record["record_id"], 999, dict(record, version=2))
    updated = repo.compare_and_set(record["record_id"], 1, dict(record, version=2))
    assert updated["version"] == 2


def test_immutable_logs_reject_rewrite():
    log = repositories.TaskTransitionLog()
    first = _transition()
    log.append(first)
    with pytest.raises(repositories.ImmutableRecordError):
        log.append(dict(first, to="FAILED"))


def test_task_transition_edges_follow_manifest():
    log = repositories.TaskTransitionLog()
    with pytest.raises(repositories.IllegalTransitionError):
        log.append(_transition(seq="bad", src="CREATED", dst="COMPLETED"))


def test_list_by_replays_in_order():
    repo = repositories.DecisionLog()
    repo.append(_minimal_record("decisions", seq="1"))
    repo.append(_minimal_record("decisions", seq="2"))
    rows = repo.list_by({})
    assert [r["record_id"] for r in rows] == [
        "decisions-1",
        "decisions-2",
    ]
    assert repo.list_by({"record_id": "decisions-2"}) == [rows[1]]
    assert repo.list_by({"record_id": "nope"}) == []


def test_counter_increment_atomic_bounded():
    store = repositories.RetryFallbackCounterStore()
    assert store.increment("task:T1", "RETRY", 3) == 1
    assert store.increment("task:T1", "RETRY", 3) == 2
    with pytest.raises(repositories.CounterLimitExceededError):
        store.increment("task:T1", "RETRY", 2)


def test_unit_of_work_is_atomic():
    run_repo = repositories.ExecutionRunRepository()
    decision_repo = repositories.DecisionLog()
    uow = repositories.UnitOfWork()
    run = dict(_minimal_record("runs"), status="CREATED",
               from_state="CREATED", to_state="CREATED")
    uow.stage_append(run_repo, run)
    uow.stage_append(decision_repo, _minimal_record("decisions"))
    uow.commit()
    assert run_repo.load(run["record_id"]) is not None

    failing = repositories.UnitOfWork()
    good = _minimal_record("decisions", seq="good")
    bad = _transition(seq="bad-uow", src="CREATED", dst="COMPLETED")
    failing.stage_append(decision_repo, good)
    failing.stage_append(repositories.TaskTransitionLog(), bad)
    with pytest.raises(repositories.IllegalTransitionError):
        failing.commit()
    assert decision_repo.load(good["record_id"]) is None


def test_report_dataset_frozen_keys_from_records_only():
    builder = report_dataset.ReportDatasetBuilder()
    sections = {key: [] for key in report_dataset.REPORT_KEYS}
    dataset = builder.build(sections)
    assert set(dataset.keys()) == set(report_dataset.REPORT_KEYS)
    assert dataset["COST"] == report_dataset.COST_UNAVAILABLE
    with pytest.raises(report_dataset.DatasetKeyError):
        builder.build({"PROJECT": []})
    with pytest.raises(report_dataset.DatasetKeyError):
        builder.build(dict(sections, EXTRA_KEY=[]))
