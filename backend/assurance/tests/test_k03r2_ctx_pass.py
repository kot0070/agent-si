"""K03R2 ctx-integrity PASS block: mapping plus persisted-path enforcement.

K13 45A: an unresolved HIGH violation in the audited scope forces REWORK,
an unresolved CRITICAL forces BLOCKED, and PASS is allowed only when the
scope has no unresolved HIGH/CRITICAL and context_integrity reads PASS.
The real audit-result entry point (AuditLog.append) enforces the mapping on
the persisted path: a refused PASS raises and is never stored.

Entry points: real symbols are loaded from
``src/agent_si/assurance/audit_records.py`` via the loader below (no copies,
no mocks of the unit under test). Each test uses a thin concrete subclass of
the real AuditLog Protocol. Registering the loaded module in
``sys.modules`` under its synthetic name is required: the module uses
``from __future__ import annotations`` with dataclasses, which resolves
string annotations through ``sys.modules``.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types

import pytest

_ASSURANCE = (
    pathlib.Path(__file__).resolve().parents[3]
    / "src"
    / "agent_si"
    / "assurance"
)

#: Exact shipped-preset model id (never retyped, never a second id).
MODEL = "meta/muse-spark-1.3-contributor"

PROJECT = "proj-k03-ctx1"
TASK = "task-k03-ctx1"
RUN = "run-k03-ctx1"
CONTRACT_HASH = "contract-hash-k03-ctx1"
SCOPE = "scope-k03-ctx1"
OTHER_SCOPE = "scope-k03-ctx-other"


def _load(name):
    path = _ASSURANCE / ("%s.py" % name)
    assert path.is_file(), "module missing: %s" % path
    module_name = "k03_assurance_%s" % name
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_cache = {}


def _mod(name):
    if name not in _cache:
        _cache[name] = _load(name)
    return _cache[name]


def _log():
    module = _mod("audit_records")

    class _ConcreteLog(module.AuditLog):
        pass

    return _ConcreteLog(), module


def _record(module, audit_id, scope=SCOPE, integrity="PASS", result="PASS"):
    return module.AuditRecord(
        audit_id=audit_id,
        project_id=PROJECT,
        task_id=TASK,
        run_id=RUN,
        audit_scope_id=scope,
        audit_sequence=1,
        supersedes_audit_id=None,
        context_session_ref="sess-audit-ctx",
        producer_session_refs=("sess-producer-1",),
        implementer_model_ids=(MODEL,),
        contract_hash=CONTRACT_HASH,
        audit_policy_ref="audit-policy-ctx",
        artifact_refs=("art-ctx-1",),
        evidence_refs=("ev-ctx-1",),
        requirement_verdicts=(),
        context_integrity=integrity,
        result=module.AuditResult[result],
        handling_disposition=module.AuditHandlingDisposition.COMPLETE,
        failure_class=None,
        created_at="2026-10-26T00:00:00Z",
    )


def _viol(severity, resolved, scope=SCOPE):
    return {"severity": severity, "resolved": resolved, "scope_id": scope}


def test_high_unresolved_maps_rework_and_refuses_pass():
    records = _mod("audit_records")
    log, _ = _log()
    assert records.decide_context_integrity([_viol("HIGH", False)]) == "REWORK"
    with pytest.raises(ValueError):
        log.append(
            _record(records, "audit-ctx-high-1"), [_viol("HIGH", False)]
        )
    assert log.load("audit-ctx-high-1") is None


def test_critical_unresolved_maps_blocked_and_refuses_pass():
    records = _mod("audit_records")
    log, _ = _log()
    assert (
        records.decide_context_integrity([_viol("CRITICAL", False)])
        == "BLOCKED"
    )
    with pytest.raises(ValueError):
        log.append(
            _record(records, "audit-ctx-crit-1"), [_viol("CRITICAL", False)]
        )
    assert log.load("audit-ctx-crit-1") is None


def test_all_resolved_allows_pass():
    records = _mod("audit_records")
    log, _ = _log()
    context = [_viol("HIGH", True), _viol("CRITICAL", True)]
    assert records.decide_context_integrity(context) == "PASS"
    stored = log.append(_record(records, "audit-ctx-ok-1"), context)
    assert stored.result == records.AuditResult.PASS
    assert log.load("audit-ctx-ok-1").result == records.AuditResult.PASS


def test_empty_list_allows_pass():
    records = _mod("audit_records")
    log, _ = _log()
    assert records.decide_context_integrity(()) == "PASS"
    assert records.decide_context_integrity([]) == "PASS"
    stored = log.append(_record(records, "audit-ctx-empty-1"), [])
    assert stored.result == records.AuditResult.PASS


def test_integrity_outside_set_rejected_never_stored():
    records = _mod("audit_records")
    log, _ = _log()
    for bad in ("UNKNOWN", "pass", ""):
        tag = bad or "empty"
        with pytest.raises(ValueError):
            records.decide_audit_result((), bad)
        with pytest.raises(ValueError):
            log.append(
                _record(
                    records,
                    "audit-ctx-bad-%s" % tag,
                    integrity=bad,
                    result="BLOCKED",
                )
            )
        assert log.load("audit-ctx-bad-%s" % tag) is None


def test_pass_refused_when_integrity_not_pass():
    records = _mod("audit_records")
    log, _ = _log()
    assert (
        records.decide_audit_result((), "REWORK")
        == records.AuditResult.REWORK
    )
    with pytest.raises(ValueError):
        log.append(
            _record(records, "audit-ctx-mismatch-1", integrity="REWORK")
        )
    assert log.load("audit-ctx-mismatch-1") is None
    stored = log.append(
        _record(
            records,
            "audit-ctx-rework-1",
            integrity="REWORK",
            result="REWORK",
        )
    )
    assert stored.result == records.AuditResult.REWORK


def test_other_scope_violations_do_not_block():
    records = _mod("audit_records")
    log, _ = _log()
    foreign = [_viol("CRITICAL", False, scope=OTHER_SCOPE)]
    assert records.decide_context_integrity(foreign, SCOPE) == "PASS"
    stored = log.append(_record(records, "audit-ctx-scope-1"), foreign)
    assert stored.result == records.AuditResult.PASS


def test_status_string_and_attribute_variants():
    records = _mod("audit_records")
    log, _ = _log()
    open_rec = {"severity": "HIGH", "status": "open", "scope_id": SCOPE}
    assert records.decide_context_integrity([open_rec]) == "REWORK"
    with pytest.raises(ValueError):
        log.append(_record(records, "audit-ctx-open-1"), [open_rec])
    assert log.load("audit-ctx-open-1") is None
    shut_rec = types.SimpleNamespace(
        severity="HIGH", status="resolved", scope_id=SCOPE
    )
    assert records.decide_context_integrity([shut_rec]) == "PASS"
    stored = log.append(_record(records, "audit-ctx-shut-1"), [shut_rec])
    assert stored.result == records.AuditResult.PASS


def test_decide_audit_result_mapping():
    records = _mod("audit_records")
    assert (
        records.decide_audit_result([_viol("CRITICAL", False)], "PASS")
        == records.AuditResult.BLOCKED
    )
    assert (
        records.decide_audit_result([_viol("HIGH", False)], "PASS")
        == records.AuditResult.REWORK
    )
    assert (
        records.decide_audit_result((), "PASS") == records.AuditResult.PASS
    )
    assert (
        records.decide_audit_result((), "BLOCKED")
        == records.AuditResult.BLOCKED
    )
