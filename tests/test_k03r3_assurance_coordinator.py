"""K03R3 0C assurance coordinator gates: verify leg, audit leg, finalize leg.

Gate one: failed verification leaves the audit store empty and performs
no finalize call. Gate two: a failed audit performs no finalize call and
the refusal is recorded. Gate three: the pass path finalizes only with
bound records, matching contract hashes and caller-supplied settled
flags plus output refs. The run status moves at every phase through the
existing transition writer with run-status members only.
"""

import dataclasses
import enum
import importlib
import shutil
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest

from agent_si.assurance import audit_records
from agent_si.assurance import coordinator as assurance_coordinator
from agent_si.finalization import finalizer
from agent_si.policies import verification
from agent_si.state_machines import run_machine
from iface.frozen_manifest import manifest

_CHECKER_MODULE = "agent_si.assurance.verification.checker"

_VERIFY_CALL_KEYS = frozenset(
    {
        "project_dir",
        "tool_rows",
        "criteria",
        "project_id",
        "task_id",
        "run_id",
        "contract_hash",
    }
)


def _status_value(value):
    return value.value if isinstance(value, enum.Enum) else str(value)


@pytest.fixture
def project_dir():
    path = tempfile.mkdtemp(prefix="k03r3-coord-")
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _run_kwargs(tag, project_dir):
    return dict(
        project_id="P-K03R3-%s" % tag,
        task_id="T-K03R3-%s" % tag,
        run_id="run-k03r3-%s" % tag,
        contract_hash="h-k03r3-%s" % tag,
        artifact_refs=("art-%s-1" % tag,),
        evidence_refs=("ev-%s-1" % tag,),
        work_refs=("work-%s-1" % tag,),
        producer_session_refs=("sess-prod-%s" % tag,),
        tool_rows=({"tool": "read", "ref": "tool-%s-1" % tag},),
        project_dir=project_dir,
        criteria=("criterion-k03r3",),
        task_state=manifest.TaskState.COMPLETED,
        output_refs=("art-%s-1" % tag,),
        metric_refs=("m-%s-1" % tag,),
        accounting_complete=True,
        budget_settled=True,
        resources_released=True,
    )


def _criterion(tag, result):
    return verification.CriterionResult(
        criterion_result_id="cr-%s" % tag,
        ac_id="ac-%s" % tag,
        result=result,
        severity=verification.FailureSeverity.MEDIUM,
        verification_method="DeterministicVerify",
        evidence_refs=("ev-%s-1" % tag,),
    )


def _verification_record(tag, passed, kwargs):
    criterion_result = (
        verification.CriterionVerificationResult.PASS
        if passed
        else verification.CriterionVerificationResult.FAIL
    )
    return verification.VerificationRecord(
        verification_id="v-k03r3-%s" % tag,
        verification_sequence=1,
        project_id=kwargs["project_id"],
        task_id=kwargs["task_id"],
        run_id=kwargs["run_id"],
        verification_scope_id=(
            "TASK:%s:RUN:%s:CONTRACT:%s:RUN_OUTPUT"
            % (
                kwargs["task_id"],
                kwargs["run_id"],
                kwargs["contract_hash"],
            )
        ),
        verification_target_type=(
            verification.VerificationTargetType.RUN_OUTPUT
        ),
        contract_hash=kwargs["contract_hash"],
        criterion_results=(_criterion(tag, criterion_result),),
        result=(
            manifest.VerificationResult.PASS
            if passed
            else manifest.VerificationResult.FAIL
        ),
        handling_disposition=(
            verification.VerificationHandlingDisposition.ACCEPT
            if passed
            else verification.VerificationHandlingDisposition.FAIL
        ),
    )


def _install_checker(monkeypatch, record):
    calls = []

    def verify_run(
        *,
        project_dir,
        tool_rows,
        criteria,
        project_id,
        task_id,
        run_id,
        contract_hash,
        verification_id=None,
        verification_sequence=None,
    ):
        calls.append(
            {
                "project_dir": project_dir,
                "tool_rows": tool_rows,
                "criteria": criteria,
                "project_id": project_id,
                "task_id": task_id,
                "run_id": run_id,
                "contract_hash": contract_hash,
            }
        )
        return record

    module = types.ModuleType(_CHECKER_MODULE)
    module.verify_run = verify_run
    monkeypatch.setitem(sys.modules, _CHECKER_MODULE, module)
    return calls


@pytest.fixture
def finalize_calls(monkeypatch):
    seen = []
    origin = finalizer.Finalizer.finalize_with_records

    def spy(**kwargs):
        result = origin(**kwargs)
        seen.append((kwargs, result))
        return result

    monkeypatch.setattr(
        finalizer.Finalizer, "finalize_with_records", spy
    )
    return seen


@pytest.fixture
def transition_calls(monkeypatch):
    seen = []
    origin = run_machine.transition_run

    def spy(run, **kwargs):
        seen.append(
            (
                _status_value(run.status),
                _status_value(kwargs["to_status"]),
            )
        )
        return origin(run, **kwargs)

    monkeypatch.setattr(run_machine, "transition_run", spy)
    return seen


@pytest.fixture
def passing_audit_store(monkeypatch):
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


def test_checker_module_name_is_documented():
    assert assurance_coordinator.CHECKER_MODULE == _CHECKER_MODULE


def test_checker_unavailable_refuses_before_any_work(
    monkeypatch, project_dir, finalize_calls, transition_calls
):
    monkeypatch.delitem(sys.modules, _CHECKER_MODULE, raising=False)
    origin_import = importlib.import_module

    def fake_import(name, *args, **kwargs):
        if name == _CHECKER_MODULE:
            raise ImportError("blocked for test: %s" % name)
        return origin_import(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", fake_import)
    kwargs = _run_kwargs("nochecker", project_dir)
    with pytest.raises(assurance_coordinator.AssuranceRefused) as excinfo:
        assurance_coordinator.run_assurance(**kwargs)
    assert _CHECKER_MODULE in str(excinfo.value)
    assert audit_records._records_for_run(kwargs["run_id"]) == ()
    assert finalize_calls == []
    assert transition_calls == []


def test_verify_raise_refuses_before_any_audit_or_finalize(
    monkeypatch, project_dir, finalize_calls, transition_calls
):
    kwargs = _run_kwargs("verifyraise", project_dir)
    boom = types.ModuleType(_CHECKER_MODULE)

    def verify_run(**call_kwargs):
        raise RuntimeError("boom-%s" % call_kwargs["run_id"])

    boom.verify_run = verify_run
    monkeypatch.setitem(sys.modules, _CHECKER_MODULE, boom)
    outcome = assurance_coordinator.run_assurance(**kwargs)
    assert outcome.ok is False
    assert outcome.phase == "VERIFY_REFUSED"
    assert outcome.verification_id is None
    assert outcome.audit_id is None
    assert outcome.finalization_id is None
    assert audit_records._records_for_run(kwargs["run_id"]) == ()
    assert finalize_calls == []
    assert outcome.status_trail == ("RUNNING", "VERIFYING", "FAILED")
    assert transition_calls == [
        ("RUNNING", "VERIFYING"),
        ("VERIFYING", "FAILED"),
    ]
    assert outcome.records


def test_audit_raise_records_refusal_without_finalize(
    monkeypatch, project_dir, finalize_calls, transition_calls
):
    kwargs = _run_kwargs("auditraise", project_dir)
    kwargs["work_refs"] = ()
    kwargs["artifact_refs"] = ()
    record = _verification_record("auditraise", True, kwargs)
    _install_checker(monkeypatch, record)
    outcome = assurance_coordinator.run_assurance(**kwargs)
    assert outcome.ok is False
    assert outcome.phase == "AUDIT_REFUSED"
    assert outcome.verification_id == record.verification_id
    assert outcome.audit_id is None
    assert outcome.finalization_id is None
    assert audit_records._records_for_run(kwargs["run_id"]) == ()
    assert finalize_calls == []
    assert outcome.status_trail == (
        "RUNNING",
        "VERIFYING",
        "AUDITING",
        "FAILED",
    )
    assert transition_calls == [
        ("RUNNING", "VERIFYING"),
        ("VERIFYING", "AUDITING"),
        ("AUDITING", "FAILED"),
    ]


def test_failed_verification_skips_audit_and_finalize(
    monkeypatch, project_dir, finalize_calls, transition_calls
):
    kwargs = _run_kwargs("verifyfail", project_dir)
    record = _verification_record("verifyfail", False, kwargs)
    checker_calls = _install_checker(monkeypatch, record)
    outcome = assurance_coordinator.run_assurance(**kwargs)
    assert outcome.ok is False
    assert outcome.phase == "VERIFY_REFUSED"
    assert outcome.verification_id == record.verification_id
    assert outcome.audit_id is None
    assert outcome.finalization_id is None
    assert audit_records._records_for_run(kwargs["run_id"]) == ()
    assert finalize_calls == []
    assert outcome.status_trail == ("RUNNING", "VERIFYING", "FAILED")
    assert transition_calls == [
        ("RUNNING", "VERIFYING"),
        ("VERIFYING", "FAILED"),
    ]
    assert outcome.records
    assert len(checker_calls) == 1
    assert set(checker_calls[0]) == _VERIFY_CALL_KEYS
    assert checker_calls[0]["run_id"] == kwargs["run_id"]
    assert checker_calls[0]["contract_hash"] == kwargs["contract_hash"]


def test_failed_audit_skips_finalize_and_records_refusal(
    monkeypatch, project_dir, finalize_calls, transition_calls
):
    kwargs = _run_kwargs("auditfail", project_dir)
    record = _verification_record("auditfail", True, kwargs)
    _install_checker(monkeypatch, record)
    outcome = assurance_coordinator.run_assurance(**kwargs)
    assert outcome.ok is False
    assert outcome.phase == "AUDIT_REFUSED"
    assert outcome.verification_id == record.verification_id
    assert outcome.audit_id is not None
    stored = audit_records._records_for_run(kwargs["run_id"])
    assert len(stored) == 1
    assert stored[0].audit_id == outcome.audit_id
    assert stored[0].result == audit_records.AuditResult.BLOCKED
    assert finalize_calls == []
    assert outcome.status_trail == (
        "RUNNING",
        "VERIFYING",
        "AUDITING",
        "FAILED",
    )
    assert transition_calls == [
        ("RUNNING", "VERIFYING"),
        ("VERIFYING", "AUDITING"),
        ("AUDITING", "FAILED"),
    ]
    assert any(
        outcome.audit_id in step.note for step in outcome.records
    )


def test_pass_path_finalizes_with_bound_records(
    monkeypatch,
    project_dir,
    finalize_calls,
    transition_calls,
    passing_audit_store,
):
    kwargs = _run_kwargs("passpath", project_dir)
    record = _verification_record("passpath", True, kwargs)
    _install_checker(monkeypatch, record)
    outcome = assurance_coordinator.run_assurance(**kwargs)
    assert outcome.ok is True
    assert outcome.phase == "FINALIZED"
    assert outcome.verification_id == record.verification_id
    assert outcome.audit_id is not None
    assert len(finalize_calls) == 1
    passed_kwargs, finalization = finalize_calls[0]
    assert "audit_result" not in passed_kwargs
    assert passed_kwargs["verification_record"] is record
    loaded = audit_records._fetch_record(outcome.audit_id)
    assert loaded is not None
    assert loaded.result == audit_records.AuditResult.PASS
    assert passed_kwargs["audit_ref"] is loaded
    assert passed_kwargs["audit_record"] is loaded
    assert passed_kwargs["verification_ref"] == record.verification_id
    assert record.contract_hash == kwargs["contract_hash"]
    assert loaded.contract_hash == kwargs["contract_hash"]
    assert passed_kwargs["project_id"] == kwargs["project_id"]
    assert passed_kwargs["task_id"] == kwargs["task_id"]
    assert passed_kwargs["run_id"] == kwargs["run_id"]
    assert passed_kwargs["task_state"] == manifest.TaskState.COMPLETED
    assert passed_kwargs["output_refs"] == tuple(kwargs["output_refs"])
    assert passed_kwargs["metric_refs"] == tuple(kwargs["metric_refs"])
    assert passed_kwargs["accounting_complete"] is True
    assert passed_kwargs["budget_settled"] is True
    assert passed_kwargs["resources_released"] is True
    assert outcome.finalization_id == finalization.finalization_id
    assert finalization.completion_disposition == (
        manifest.CompletionDisposition.VERIFIED_PASS
    )
    assert outcome.status_trail == (
        "RUNNING",
        "VERIFYING",
        "AUDITING",
        "SUCCEEDED",
    )
    assert transition_calls == [
        ("RUNNING", "VERIFYING"),
        ("VERIFYING", "AUDITING"),
        ("AUDITING", "SUCCEEDED"),
    ]


def test_status_trail_uses_manifest_run_statuses_only(
    monkeypatch, project_dir, passing_audit_store
):
    run_statuses = {item.value for item in manifest.ExecutionRunStatus}
    audit_spellings = {item.value for item in manifest.AuditResult}
    fail_kwargs = _run_kwargs("statusfail", project_dir)
    _install_checker(
        monkeypatch,
        _verification_record("statusfail", False, fail_kwargs),
    )
    fail_trail = assurance_coordinator.run_assurance(
        **fail_kwargs
    ).status_trail
    pass_kwargs = _run_kwargs("statuspass", project_dir)
    _install_checker(
        monkeypatch,
        _verification_record("statuspass", True, pass_kwargs),
    )
    pass_trail = assurance_coordinator.run_assurance(
        **pass_kwargs
    ).status_trail
    assert fail_trail == ("RUNNING", "VERIFYING", "FAILED")
    assert pass_trail == ("RUNNING", "VERIFYING", "AUDITING", "SUCCEEDED")
    for trail in (fail_trail, pass_trail):
        for status in trail:
            assert status in run_statuses
            assert status not in audit_spellings
        for before, after in zip(trail, trail[1:]):
            allowed = manifest.RUN_ALLOWED[
                manifest.ExecutionRunStatus(before)
            ]
            assert manifest.ExecutionRunStatus(after) in allowed
