import os
import sys

sys.path.insert(
    0,
    os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
    ),
)

import pytest

from agent_si.backend.orchestration import overlap as ov


@pytest.fixture(autouse=True)
def _clean_registry():
    ov._clear_verdicts()
    yield
    ov._clear_verdicts()


def _ref(gate_ref="gate-a", audit_ref="audit-a"):
    return {
        "package_id": "pkg-a",
        "contract_hash": "hash-a",
        "gate_verdict_ref": gate_ref,
        "audit_verdict_ref": audit_ref,
    }


def _store_both(gate="PASS", audit="PASS", gate_ref="gate-a", audit_ref="audit-a"):
    ov._record_gate_verdict(gate_ref, gate)
    ov._record_audit_verdict(audit_ref, audit)


def test_pass_plus_pass_true():
    _store_both("PASS", "PASS")
    assert ov.may_start_early(_ref()) is True


def test_both_required_gate_pass_audit_not_pass_refused():
    _store_both("PASS", "REWORK")
    assert ov.may_start_early(_ref()) is False


def test_both_required_audit_pass_gate_not_pass_refused():
    _store_both("BLOCKED", "PASS")
    assert ov.may_start_early(_ref()) is False


@pytest.mark.parametrize("verdict", ["REWORK", "BLOCKED", "ESCALATE", "FAIL"])
def test_each_non_pass_gate_refused(verdict):
    _store_both(verdict, "PASS")
    assert ov.may_start_early(_ref()) is False


@pytest.mark.parametrize("verdict", ["REWORK", "BLOCKED", "ESCALATE", "FAIL"])
def test_each_non_pass_audit_refused(verdict):
    _store_both("PASS", verdict)
    assert ov.may_start_early(_ref()) is False


def test_unresolved_gate_ref_false():
    ov._record_audit_verdict("audit-a", "PASS")
    assert ov.may_start_early(_ref()) is False


def test_unresolved_audit_ref_false():
    ov._record_gate_verdict("gate-a", "PASS")
    assert ov.may_start_early(_ref()) is False


def test_unresolved_both_false():
    assert ov.may_start_early(_ref()) is False


def test_malformed_ref_false_and_no_raise():
    _store_both("PASS", "PASS")
    bad_refs = [
        {},
        {"package_id": "pkg-a"},
        {"package_id": "pkg-a", "gate_verdict_ref": "gate-a"},
        {
            "package_id": "pkg-a",
            "gate_verdict_ref": "",
            "audit_verdict_ref": "audit-a",
        },
        {
            "package_id": "pkg-a",
            "gate_verdict_ref": "gate-a",
            "audit_verdict_ref": None,
        },
        "not-a-dict",
        None,
        42,
    ]
    for bad in bad_refs:
        assert ov.may_start_early(bad) is False


def test_unknown_verdict_value_refused():
    _store_both("BOGUS", "PASS")
    assert ov.may_start_early(_ref()) is False
    ov._clear_verdicts()
    _store_both("PASS", "BOGUS")
    assert ov.may_start_early(_ref()) is False
