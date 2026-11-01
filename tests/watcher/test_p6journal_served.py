"""P6JOURNAL served run grows the watcher journal (RED delta 0 to GREEN delta above 0).

One served assurance run flows through the real run_machine emit into the
real journal store and is served back through the watcher interface entry
``journal.list_events`` (REALIZATION_MAP plus SURFACE_FUNCTIONS). Rows come
from the run itself, never seeded: the journal is reset first and no helper
appends rows. The pass path uses the repo checker plus audit doubles only
for outcome determination (the journal path stays fully real); the refused
path uses the real in-tree checker with no doubles at all.
"""

import dataclasses
import importlib
import shutil
import sys
import tempfile
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import agent_si.watcher.interface as iface  # noqa: E402
import agent_si.watcher.journal as journal  # noqa: E402
from agent_si.assurance import audit_records  # noqa: E402
from agent_si.assurance import coordinator as assurance_coordinator  # noqa: E402
from agent_si.policies import verification  # noqa: E402
from agent_si.state_machines import run_machine  # noqa: E402
from iface.frozen_manifest import manifest  # noqa: E402

_CHECKER_MODULE = "agent_si.assurance.verification.checker"

TAG = "p6journal-served"
PROJECT_ID = "P-P6JOURNAL-SERVED"
TASK_ID = "T-P6JOURNAL-SERVED"
RUN_ID = "run-p6journal-served-1"
CONTRACT_HASH = "h-p6journal-served"


@pytest.fixture(autouse=True)
def _lane():
    journal.reset_state()
    yield
    journal.reset_state()


@pytest.fixture
def project_dir():
    path = tempfile.mkdtemp(prefix="p6journal-served-")
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _served_entries(project_id, kind=""):
    """Serve journal rows through the watcher interface entries."""
    assert iface.SURFACE_FUNCTIONS["journal.list_events"] == "list_events"
    dotted = iface.REALIZATION_MAP["journal.list_events"]
    module_name, _, func_name = dotted.rpartition(".")
    serve = getattr(importlib.import_module(module_name), func_name)
    assert serve is journal.list_events
    return serve(project_id, kind)


def _served_count(project_id, kind=""):
    return len(_served_entries(project_id, kind))


def _phases(project_id):
    return [row.summary for row in journal.stored_rows(project_id)]


def _run_kwargs(project_dir):
    return {
        "project_id": PROJECT_ID,
        "task_id": TASK_ID,
        "run_id": RUN_ID,
        "contract_hash": CONTRACT_HASH,
        "artifact_refs": ("art-p6journal-1",),
        "evidence_refs": ("ev-p6journal-1",),
        "work_refs": ("work-p6journal-1",),
        "producer_session_refs": ("sess-prod-p6journal-1",),
        "tool_rows": ({"tool": "read", "ref": "tool-p6journal-1"},),
        "project_dir": project_dir,
        "criteria": ("criterion-p6",),
        "task_state": manifest.TaskState.COMPLETED,
        "output_refs": ("art-p6journal-1",),
        "metric_refs": ("m-p6journal-1",),
        "accounting_complete": True,
        "budget_settled": True,
        "resources_released": True,
    }


def _passing_record(kwargs):
    criterion = verification.CriterionResult(
        criterion_result_id="cr-p6journal",
        ac_id="ac-p6journal",
        result=verification.CriterionVerificationResult.PASS,
        severity=verification.FailureSeverity.MEDIUM,
        verification_method="DeterministicVerify",
        evidence_refs=("ev-p6journal-1",),
    )
    return verification.VerificationRecord(
        verification_id="v-p6journal",
        verification_sequence=1,
        project_id=kwargs["project_id"],
        task_id=kwargs["task_id"],
        run_id=kwargs["run_id"],
        verification_scope_id=(
            "TASK:{}:RUN:{}:CONTRACT:{}:RUN_OUTPUT".format(
                kwargs["task_id"], kwargs["run_id"], kwargs["contract_hash"]
            )
        ),
        verification_target_type=verification.VerificationTargetType.RUN_OUTPUT,
        contract_hash=kwargs["contract_hash"],
        criterion_results=(criterion,),
        result=manifest.VerificationResult.PASS,
        handling_disposition=verification.VerificationHandlingDisposition.ACCEPT,
    )


def _install_checker(monkeypatch, record):
    module = types.ModuleType(_CHECKER_MODULE)
    module.verify_run = lambda **kwargs: record
    monkeypatch.setitem(sys.modules, _CHECKER_MODULE, module)


@pytest.fixture
def _passing_audit(monkeypatch):
    origin = audit_records._store_record

    def store(record, context_records=()):
        if record.result != audit_records.AuditResult.PASS:
            record = dataclasses.replace(
                record,
                result=audit_records.AuditResult.PASS,
                handling_disposition=(
                    audit_records.AuditHandlingDisposition.COMPLETE
                ),
            )
        return origin(record, context_records)

    monkeypatch.setattr(audit_records, "_store_record", store)


def test_run_lifecycle_grows_journal(monkeypatch, project_dir, _passing_audit):
    before = _served_count(PROJECT_ID)
    assert before == 0
    kwargs = _run_kwargs(project_dir)
    _install_checker(monkeypatch, _passing_record(kwargs))
    outcome = assurance_coordinator.run_assurance(**kwargs)
    assert outcome.ok is True
    assert outcome.phase == "FINALIZED"
    after = _served_count(PROJECT_ID)
    delta = after - before
    assert delta > 0, f"served run journal delta {delta} (expected above 0)"
    summaries = " ".join(_phases(PROJECT_ID))
    for phase in run_machine.RUN_LIFECYCLE_PHASES:
        assert f"run {phase} " in summaries, phase
    rows = journal.stored_rows(PROJECT_ID, "AUTOMATION_RUN")
    assert len(rows) == delta
    assert {row.source for row in rows} == {"run_machine"}
    assert all(RUN_ID in row.refs for row in rows)


def test_refused_run_still_journals_lifecycle(project_dir):
    before = _served_count(PROJECT_ID)
    assert before == 0
    outcome = assurance_coordinator.run_assurance(
        project_id=PROJECT_ID,
        task_id=TASK_ID,
        run_id="run-p6journal-refused-1",
        contract_hash=CONTRACT_HASH,
        project_dir=project_dir,
    )
    assert outcome.ok is False
    after = _served_count(PROJECT_ID)
    delta = after - before
    assert delta > 0, f"refused run journal delta {delta} (expected above 0)"
    summaries = " ".join(_phases("P-P6JOURNAL-SERVED"))
    assert "run plan " in summaries
    assert "run finish " in summaries
