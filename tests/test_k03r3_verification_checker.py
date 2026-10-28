"""K03R3 M-CHECK verification checker: own tool rows plus files on disk.

``checker.verify_run`` checks one run: every required evidence ref must
resolve to a matching ok tool row or to a real file under the project
dir, each artifact grounded through the shared grounding module. Missing
evidence fails the criterion fail-closed; unreadable inputs give BLOCKED
with VERIFICATION_INFRA_FAILURE; the PASS record binds the ids that
record-bound finalization requires.

RED->GREEN: pre-fix the checker package is absent so collection fails
(import error, quoted in RETURN); post-fix every case below is GREEN.

Fixtures use real I/O only: a temp project dir under the process temp dir
holds real evidence files, and real tool rows travel through a JSONL file
in that dir (read back before the checker call; never in-memory-only rows
for the happy path).
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import importlib.util
import json
import os
import re
import shutil
import tempfile

import pytest

from agent_si.assurance import audit_records
from agent_si.assurance.verification import checker
from agent_si.finalization import finalizer
from agent_si.policies import verification
from iface.frozen_manifest import manifest

PROJECT = "proj-k03r3-mcheck"
CONTRACT = "contract-hash-k03r3-mcheck"


def _rows():
    return [
        {"tool": "writer", "evidence_ref": "tool-ev-1", "ok": True},
        {
            "tool": "reviewer",
            "evidence_ref": "tool-ev-2",
            "ok": True,
            "output": "looks good",
        },
    ]


def _criteria():
    return [
        {
            "ac_id": "ac-1",
            "evidence_required": True,
            "evidence_refs": ["tool-ev-1", "result.json"],
            "severity": "MEDIUM",
            "verification_method": "grounded-evidence",
        },
        {
            "ac_id": "ac-2",
            "evidence_required": True,
            "evidence_refs": ["tool-ev-2", "report.md"],
            "severity": "HIGH",
            "verification_method": "grounded-evidence",
        },
    ]


def _files():
    return {
        "result.json": '{"ok": true}\n',
        "report.md": "# report\n",
    }


def _mk_project(files, rows):
    proj = tempfile.mkdtemp(prefix="k03r3-mcheck-")
    try:
        with open(
            os.path.join(proj, "tool_rows.jsonl"), "w", encoding="utf-8"
        ) as handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")
        for name, text in files.items():
            with open(
                os.path.join(proj, name), "w", encoding="utf-8"
            ) as handle:
                handle.write(text)
    except BaseException:
        shutil.rmtree(proj, ignore_errors=True)
        raise
    return proj


def _read_rows(proj):
    out = []
    with open(
        os.path.join(proj, "tool_rows.jsonl"), encoding="utf-8"
    ) as handle:
        for line in handle:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _run_checker(proj, rows, criteria, task, run):
    return checker.verify_run(
        project_dir=proj,
        tool_rows=rows,
        criteria=criteria,
        project_id=PROJECT,
        task_id=task,
        run_id=run,
        contract_hash=CONTRACT,
    )


def _audit_record(task, run):
    return audit_records.AuditRecord(
        audit_id="aud-mcheck-%s" % run,
        project_id=PROJECT,
        task_id=task,
        run_id=run,
        audit_scope_id="scope-mcheck-%s" % run,
        audit_sequence=1,
        supersedes_audit_id=None,
        context_session_ref="sess-audit-mcheck",
        producer_session_refs=("sess-prod-1",),
        implementer_model_ids=("impl-model-1",),
        contract_hash=CONTRACT,
        audit_policy_ref="pol-mcheck",
        artifact_refs=("result.json",),
        evidence_refs=("tool-ev-1",),
        requirement_verdicts=(),
        context_integrity="PASS",
        result=audit_records.AuditResult.PASS,
        handling_disposition=(
            audit_records.AuditHandlingDisposition.COMPLETE
        ),
        failure_class=None,
        created_at="2026-10-28T00:00:00Z",
        decided_at=None,
    )


def test_happy_path_pass_record_finalizes():
    proj = _mk_project(_files(), _rows())
    try:
        rows = _read_rows(proj)
        assert len(rows) == 2
        record = _run_checker(
            proj, rows, _criteria(), "task-mcheck-happy", "run-mcheck-happy"
        )
        assert isinstance(record, verification.VerificationRecord)
        assert record.result == manifest.VerificationResult.PASS
        assert record.handling_disposition == (
            verification.VerificationHandlingDisposition.ACCEPT
        )
        assert record.verification_scope_id == (
            verification.run_output_scope_id(
                "task-mcheck-happy", "run-mcheck-happy", CONTRACT
            )
        )
        assert [c.ac_id for c in record.criterion_results] == [
            "ac-1",
            "ac-2",
        ]
        assert all(
            c.result == verification.CriterionVerificationResult.PASS
            for c in record.criterion_results
        )
        assert record.failure_class is None
        assert record.project_id == PROJECT
        assert record.task_id == "task-mcheck-happy"
        assert record.run_id == "run-mcheck-happy"
        assert record.contract_hash == CONTRACT
        audit = _audit_record("task-mcheck-happy", "run-mcheck-happy")
        done = finalizer.Finalizer.finalize_with_records(
            verification_record=record,
            audit_record=audit,
            finalization_id="fin-mcheck-happy",
            project_id=PROJECT,
            task_id="task-mcheck-happy",
            run_id="run-mcheck-happy",
            task_state=manifest.TaskState.COMPLETED,
            audit_result=manifest.AuditResult.PASS,
            audit_ref=audit,
            verification_ref=record.verification_id,
            output_refs=("result.json",),
            metric_refs=("m-1",),
            accounting_complete=True,
            budget_settled=True,
            resources_released=True,
            completed_at="t9",
        )
        assert done.completion_disposition == (
            manifest.CompletionDisposition.VERIFIED_PASS
        )
        assert done.audit_result == manifest.AuditResult.PASS
        assert done.verification_ref == record.verification_id
    finally:
        shutil.rmtree(proj, ignore_errors=True)


def test_missing_file_evidence_fails():
    proj = _mk_project(_files(), _rows())
    try:
        rows = _read_rows(proj)
        criteria = _criteria()
        criteria[0]["evidence_refs"] = ["tool-ev-1", "absent-file.bin"]
        record = _run_checker(
            proj, rows, criteria, "task-mcheck-mfile", "run-mcheck-mfile"
        )
        by_ac = {c.ac_id: c for c in record.criterion_results}
        assert by_ac["ac-1"].result == (
            verification.CriterionVerificationResult.FAIL
        )
        assert by_ac["ac-2"].result == (
            verification.CriterionVerificationResult.PASS
        )
        assert record.result == manifest.VerificationResult.FAIL
        assert record.handling_disposition == (
            verification.VerificationHandlingDisposition.FAIL
        )
    finally:
        shutil.rmtree(proj, ignore_errors=True)


def test_missing_tool_row_fails():
    proj = _mk_project(_files(), _rows())
    try:
        rows = _read_rows(proj)
        criteria = _criteria()
        criteria[1]["evidence_refs"] = ["tool-ev-absent", "report.md"]
        record = _run_checker(
            proj, rows, criteria, "task-mcheck-mrow", "run-mcheck-mrow"
        )
        by_ac = {c.ac_id: c for c in record.criterion_results}
        assert by_ac["ac-2"].result == (
            verification.CriterionVerificationResult.FAIL
        )
        assert record.result == manifest.VerificationResult.FAIL
    finally:
        shutil.rmtree(proj, ignore_errors=True)


def test_not_ok_tool_row_fails():
    proj = _mk_project(_files(), _rows())
    try:
        rows = _read_rows(proj)
        rows = [r for r in rows if r["evidence_ref"] != "tool-ev-1"]
        rows.append(
            {"tool": "writer", "evidence_ref": "tool-ev-1", "ok": False}
        )
        record = _run_checker(
            proj, rows, _criteria(), "task-mcheck-notok", "run-mcheck-notok"
        )
        by_ac = {c.ac_id: c for c in record.criterion_results}
        assert by_ac["ac-1"].result == (
            verification.CriterionVerificationResult.FAIL
        )
        assert record.result == manifest.VerificationResult.FAIL
    finally:
        shutil.rmtree(proj, ignore_errors=True)


def test_empty_evidence_refs_required_fails():
    proj = _mk_project(_files(), _rows())
    try:
        rows = _read_rows(proj)
        criteria = _criteria()
        criteria.append(
            {
                "ac_id": "ac-3",
                "evidence_required": True,
                "evidence_refs": [],
                "severity": "LOW",
                "verification_method": "grounded-evidence",
            }
        )
        record = _run_checker(
            proj, rows, criteria, "task-mcheck-empty", "run-mcheck-empty"
        )
        by_ac = {c.ac_id: c for c in record.criterion_results}
        empty = by_ac["ac-3"]
        assert empty.result == verification.CriterionVerificationResult.FAIL
        assert empty.result.value == "FAIL"
        assert empty.result.value == (
            audit_records.CriterionVerificationResult.FAIL.value
        )
        assert audit_records.CriterionVerificationResult.FAIL.value == "FAIL"
        assert record.result == manifest.VerificationResult.FAIL
    finally:
        shutil.rmtree(proj, ignore_errors=True)


def test_unreadable_project_dir_blocked():
    proj = _mk_project(_files(), _rows())
    try:
        rows = _read_rows(proj)
        missing = os.path.join(proj, "no-such-dir")
        record = checker.verify_run(
            project_dir=missing,
            tool_rows=rows,
            criteria=_criteria(),
            project_id=PROJECT,
            task_id="task-mcheck-nodir",
            run_id="run-mcheck-nodir",
            contract_hash=CONTRACT,
        )
        assert record.result == manifest.VerificationResult.BLOCKED
        assert record.failure_class == (
            verification.VerificationFailureClass.VERIFICATION_INFRA_FAILURE
        )
        assert record.handling_disposition == (
            verification.VerificationHandlingDisposition.BLOCK
        )
        assert all(
            c.result == verification.CriterionVerificationResult.BLOCKED
            for c in record.criterion_results
        )
    finally:
        shutil.rmtree(proj, ignore_errors=True)


def test_unreadable_tool_rows_blocked():
    proj = _mk_project(_files(), _rows())
    try:
        record = checker.verify_run(
            project_dir=proj,
            tool_rows=None,
            criteria=_criteria(),
            project_id=PROJECT,
            task_id="task-mcheck-norows",
            run_id="run-mcheck-norows",
            contract_hash=CONTRACT,
        )
        assert record.result == manifest.VerificationResult.BLOCKED
        assert record.failure_class == (
            verification.VerificationFailureClass.VERIFICATION_INFRA_FAILURE
        )
    finally:
        shutil.rmtree(proj, ignore_errors=True)


@pytest.mark.parametrize(
    "field,value",
    [
        ("project_id", ""),
        ("task_id", "  "),
        ("run_id", ""),
        ("contract_hash", ""),
    ],
)
def test_blank_ids_raise_value_error(field, value):
    proj = _mk_project(_files(), _rows())
    try:
        rows = _read_rows(proj)
        kwargs = dict(
            project_dir=proj,
            tool_rows=rows,
            criteria=_criteria(),
            project_id=PROJECT,
            task_id="task-mcheck-blank",
            run_id="run-mcheck-blank",
            contract_hash=CONTRACT,
        )
        kwargs[field] = value
        with pytest.raises(ValueError):
            checker.verify_run(**kwargs)
    finally:
        shutil.rmtree(proj, ignore_errors=True)


def test_empty_criteria_vacuous_pass():
    proj = _mk_project(_files(), _rows())
    try:
        rows = _read_rows(proj)
        record = _run_checker(
            proj, rows, [], "task-mcheck-vac", "run-mcheck-vac"
        )
        assert record.result == manifest.VerificationResult.PASS
        assert record.criterion_results == ()
        assert record.handling_disposition == (
            verification.VerificationHandlingDisposition.ACCEPT
        )
    finally:
        shutil.rmtree(proj, ignore_errors=True)


def test_none_criteria_blocked():
    proj = _mk_project(_files(), _rows())
    try:
        rows = _read_rows(proj)
        record = checker.verify_run(
            project_dir=proj,
            tool_rows=rows,
            criteria=None,
            project_id=PROJECT,
            task_id="task-mcheck-nonecrit",
            run_id="run-mcheck-nonecrit",
            contract_hash=CONTRACT,
        )
        assert record.result == manifest.VerificationResult.BLOCKED
        assert record.failure_class == (
            verification.VerificationFailureClass.VERIFICATION_INFRA_FAILURE
        )
    finally:
        shutil.rmtree(proj, ignore_errors=True)


def test_no_second_grounding_module():
    roots = [ROOT / "src" / "agent_si", ROOT / "backend"]
    definers = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if re.search(r"^class Grounding(Port|Request)\b", text, re.M):
                definers.append(path.relative_to(ROOT).as_posix())
    assert definers == ["src/agent_si/assurance/grounding.py"]


def test_deterministic_scope_and_criteria():
    proj = _mk_project(_files(), _rows())
    try:
        rows = _read_rows(proj)
        first = _run_checker(
            proj, rows, _criteria(), "task-mcheck-det", "run-mcheck-det"
        )
        second = _run_checker(
            proj, rows, _criteria(), "task-mcheck-det", "run-mcheck-det"
        )
        assert first.verification_scope_id == second.verification_scope_id
        key = lambda r: [  # noqa: E731 -- local test helper
            (c.ac_id, c.result.value, tuple(c.evidence_refs))
            for c in r.criterion_results
        ]
        assert key(first) == key(second)
        assert second.verification_sequence == first.verification_sequence + 1
        assert second.verification_id != first.verification_id
    finally:
        shutil.rmtree(proj, ignore_errors=True)


def test_checker_works_under_synthetic_loader():
    path = (
        ROOT
        / "src"
        / "agent_si"
        / "assurance"
        / "verification"
        / "checker.py"
    )
    module_name = "k03_assurance_checker_probe"
    spec = importlib.util.spec_from_file_location(
        module_name, str(path)
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        proj = _mk_project(_files(), _rows())
        try:
            rows = _read_rows(proj)
            record = module.verify_run(
                project_dir=proj,
                tool_rows=rows,
                criteria=_criteria(),
                project_id=PROJECT,
                task_id="task-mcheck-synth",
                run_id="run-mcheck-synth",
                contract_hash=CONTRACT,
            )
            assert isinstance(record, verification.VerificationRecord)
            assert record.result == manifest.VerificationResult.PASS
        finally:
            shutil.rmtree(proj, ignore_errors=True)
    finally:
        sys.modules.pop(module_name, None)
