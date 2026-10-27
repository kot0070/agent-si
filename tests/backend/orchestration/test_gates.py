import os, sys; sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__),"..","..","..","src")))
"""ROW87/94: gate plus fresh audit per part; no close without PASS."""

import pytest

from agent_si.backend.orchestration.gates import (
    AUDIT_RESULTS,
    AuditRefused,
    GATE_NOT_PASSED,
    INVALID_HIERARCHY_CHAIN,
    MISSING_INTEGRATION_TASK,
    GateAuditLog,
    GateRefused,
    audit_scope_id_of,
    can_close,
    check_hierarchy_activation,
    close_part,
    evaluate_phase_gate,
)


def close_via_log(log, package_id, contract_hash, part_id, gate_v="PASS", audit_v="PASS"):
    # ROW94 pattern: serve the pair via GateAuditLog, build the frozen
    # PartRef dict, close via gates.close_part.
    gate = log.serve_gate(part_id, gate_v)
    audit = log.serve_audit(part_id, audit_v, "auditor-s1", ("producer-s1",), True)
    return close_part(
        {
            "package_id": package_id,
            "contract_hash": contract_hash,
            "gate_verdict_ref": gate.gate_id,
            "audit_verdict_ref": audit.audit_id,
        }
    )


def test_gate_and_audit_pass_close_ok():
    log = GateAuditLog()
    verdict = close_via_log(log, "pkg-g-1", "ch", "pkg-g-1:part-000")
    assert verdict["package_id"] == "pkg-g-1"
    assert verdict["gate"] == "PASS" and verdict["audit"] == "PASS"
    assert isinstance(verdict["decided_at"], str) and verdict["decided_at"]
    assert len(verdict["evidence_refs"]) == 2


def test_close_part_without_any_verdict_refused():
    with pytest.raises(GATE_NOT_PASSED):
        close_part(
            {
                "package_id": "pkg-g-1",
                "contract_hash": "ch",
                "gate_verdict_ref": "gate:unknown-g1",
                "audit_verdict_ref": "audit:unknown-g1",
            }
        )


def test_close_part_gate_only_refused():
    log = GateAuditLog()
    gate = log.serve_gate("pkg-g-1:part-000", "PASS")
    with pytest.raises(GATE_NOT_PASSED):
        close_part(
            {
                "package_id": "pkg-g-1",
                "contract_hash": "ch",
                "gate_verdict_ref": gate.gate_id,
                "audit_verdict_ref": "audit:unknown-g1",
            }
        )


def test_close_part_audit_only_refused():
    log = GateAuditLog()
    audit = log.serve_audit(
        "pkg-g-1:part-000", "PASS", "auditor-s1", ("producer-s1",), True
    )
    with pytest.raises(GATE_NOT_PASSED):
        close_part(
            {
                "package_id": "pkg-g-1",
                "contract_hash": "ch",
                "gate_verdict_ref": "gate:unknown-g1",
                "audit_verdict_ref": audit.audit_id,
            }
        )


def test_close_part_failed_gate_refused():
    log = GateAuditLog()
    with pytest.raises(GATE_NOT_PASSED):
        close_via_log(log, "pkg-g-1", "ch", "pkg-g-1:part-000", gate_v="FAIL")


def test_can_close_matrix():
    assert can_close("PASS", "PASS") == (True, "ok")
    assert can_close(None, "PASS")[0] is False
    assert can_close("PASS", None)[0] is False
    assert can_close("PASS", "REWORK")[0] is False
    assert can_close("BLOCKED", "PASS")[0] is False


def test_self_audit_refused():
    log = GateAuditLog()
    with pytest.raises(AuditRefused):
        log.serve_audit("p", "PASS", "sess-same", ("sess-same",), True)


def test_pass_without_context_integrity_refused():
    log = GateAuditLog()
    with pytest.raises(AuditRefused):
        log.serve_audit("p", "PASS", "auditor-s9", ("producer-s9",), False)


def test_invalid_verdicts_refused():
    log = GateAuditLog()
    with pytest.raises(GateRefused):
        log.serve_gate("p", "MAYBE")
    with pytest.raises(AuditRefused):
        log.serve_audit("p", "MAYBE", "a", ("b",), True)


def test_audit_seq_monotonic_and_scope_deterministic():
    log = GateAuditLog()
    first = log.serve_audit("p", "REWORK", "a1", ("prod",), True)
    second = log.serve_audit("p", "PASS", "a2", ("prod",), True)
    assert (first.audit_seq, second.audit_seq) == (1, 2)
    assert first.scope_id == second.scope_id == audit_scope_id_of("p")
    assert log.has_fresh_audit("p") is True
    assert log.has_fresh_audit("other-part") is False
    assert set(AUDIT_RESULTS) == {"PASS", "REWORK", "BLOCKED", "ESCALATE", "FAIL"}


# --- ROW94: gates.close_part over frozen PartRef refs ---


def _serve_pair(log, part_id, gate_v="PASS", audit_v="PASS"):
    gate = log.serve_gate(part_id, gate_v)
    audit = log.serve_audit(part_id, audit_v, "auditor-g1", ("producer-g1",), True)
    return gate, audit


def _part_ref(package_id, contract_hash, gate_id, audit_id):
    return {
        "package_id": package_id,
        "contract_hash": contract_hash,
        "gate_verdict_ref": gate_id,
        "audit_verdict_ref": audit_id,
    }


def test_close_part_pass_returns_gate_verdict():
    log = GateAuditLog()
    gate, audit = _serve_pair(log, "pkg-cp-pass:part-000")
    verdict = close_part(
        _part_ref("pkg-cp-pass", "ch-cp", gate.gate_id, audit.audit_id)
    )
    assert verdict["package_id"] == "pkg-cp-pass"
    assert verdict["gate"] == "PASS"
    assert verdict["audit"] == "PASS"
    assert isinstance(verdict["decided_at"], str) and verdict["decided_at"]
    assert verdict["evidence_refs"] == [gate.gate_id, audit.audit_id]


def test_close_part_missing_refs_refused():
    with pytest.raises(GATE_NOT_PASSED):
        close_part(_part_ref("pkg-cp-miss", "ch", "gate:unknown-1", "audit:unknown-1"))


def test_gates_close_part_gate_only_refused():
    log = GateAuditLog()
    gate = log.serve_gate("pkg-cp-gonly:part-000", "PASS")
    with pytest.raises(GATE_NOT_PASSED):
        close_part(_part_ref("pkg-cp-gonly", "ch", gate.gate_id, "audit:unknown-2"))


def test_gates_close_part_audit_only_refused():
    log = GateAuditLog()
    audit = log.serve_audit(
        "pkg-cp-aonly:part-000", "PASS", "auditor-g1", ("producer-g1",), True
    )
    with pytest.raises(GATE_NOT_PASSED):
        close_part(_part_ref("pkg-cp-aonly", "ch", "gate:unknown-3", audit.audit_id))


@pytest.mark.parametrize(
    "gate_v,audit_v",
    [("FAIL", "PASS"), ("BLOCKED", "PASS"), ("PASS", "REWORK"), ("PASS", "FAIL")],
)
def test_close_part_non_pass_refused(gate_v, audit_v):
    log = GateAuditLog()
    gate, audit = _serve_pair(log, "pkg-cp-np:part-000", gate_v, audit_v)
    with pytest.raises(GATE_NOT_PASSED):
        close_part(_part_ref("pkg-cp-np", "ch", gate.gate_id, audit.audit_id))


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"package_id": "pkg-cp-bad"},
        {"package_id": "pkg-cp-bad", "gate_verdict_ref": "g"},
        {
            "package_id": "pkg-cp-bad",
            "contract_hash": "ch",
            "gate_verdict_ref": "",
            "audit_verdict_ref": "audit:x",
        },
        {
            "package_id": "pkg-cp-bad",
            "contract_hash": "ch",
            "gate_verdict_ref": "gate:x",
            "audit_verdict_ref": None,
        },
        None,
        "not-a-ref",
        42,
    ],
)
def test_close_part_malformed_ref_refused(bad):
    with pytest.raises(GATE_NOT_PASSED):
        close_part(bad)


def test_close_part_accepts_partref_object():
    from agent_si.backend.orchestration.split import PartRef as SplitPartRef

    log = GateAuditLog()
    gate, audit = _serve_pair(log, "pkg-cp-obj:part-000")
    ref = SplitPartRef(
        package_id="pkg-cp-obj",
        contract_hash="ch",
        gate_verdict_ref=gate.gate_id,
        audit_verdict_ref=audit.audit_id,
    )
    verdict = close_part(ref)
    assert (verdict["package_id"], verdict["gate"], verdict["audit"]) == (
        "pkg-cp-obj",
        "PASS",
        "PASS",
    )


# --- ROW87: gates.evaluate_phase_gate closes only after integration PASS ---


def _serve_phase(
    log,
    package_id,
    parts=("part-000", "part-001"),
    gate_v="PASS",
    audit_v="PASS",
    integration=True,
    int_gate_v="PASS",
    int_audit_v="PASS",
):
    for part in parts:
        _serve_pair(log, package_id + ":" + part, gate_v, audit_v)
    if integration:
        return _serve_pair(log, package_id + ":integration", int_gate_v, int_audit_v)
    return (None, None)


def test_phase_gate_closes_after_integration_pass():
    log = GateAuditLog()
    gate, audit = _serve_phase(log, "pkg-ph-ok")
    verdict = evaluate_phase_gate(["pkg-ph-ok"])
    assert verdict["package_id"] == "pkg-ph-ok"
    assert verdict["gate"] == "PASS" and verdict["audit"] == "PASS"
    assert isinstance(verdict["decided_at"], str) and verdict["decided_at"]
    assert gate.gate_id in verdict["evidence_refs"]
    assert audit.audit_id in verdict["evidence_refs"]


def test_phase_gate_missing_integration_task():
    log = GateAuditLog()
    _serve_phase(log, "pkg-ph-noint", integration=False)
    with pytest.raises(MISSING_INTEGRATION_TASK):
        evaluate_phase_gate(["pkg-ph-noint"])


def test_phase_gate_refuses_non_pass_parts():
    log = GateAuditLog()
    _serve_phase(log, "pkg-ph-badpart", parts=("part-000",), gate_v="FAIL")
    with pytest.raises(GATE_NOT_PASSED):
        evaluate_phase_gate(["pkg-ph-badpart"])


def test_phase_gate_refuses_failed_integration():
    log = GateAuditLog()
    _serve_phase(log, "pkg-ph-badint", int_gate_v="FAIL")
    with pytest.raises(GATE_NOT_PASSED):
        evaluate_phase_gate(["pkg-ph-badint"])


def test_phase_gate_empty_input_refused():
    with pytest.raises(GATE_NOT_PASSED):
        evaluate_phase_gate([])


# --- hierarchy activation chain shape (no mutation) ---


def test_hierarchy_valid_chain_returns_none():
    assert (
        check_hierarchy_activation(["director-1", "manager-1", "tool-1"]) is None
    )
    assert (
        check_hierarchy_activation(["director-1", "manager-1", "tool-1", "tool-2"])
        is None
    )


@pytest.mark.parametrize(
    "bad",
    [
        [],
        ["director-1"],
        ["director-1", "manager-1"],
        ["director-1", "", "tool-1"],
        ["director-1", "   ", "tool-1"],
        ["director-1", "manager-1", "manager-1"],
        ["", "", ""],
        ["director-1", "manager-1", None],
        ["director-1", "manager-1", 42],
        "director-1",
        None,
    ],
)
def test_hierarchy_invalid_chain_refused(bad):
    with pytest.raises(INVALID_HIERARCHY_CHAIN):
        check_hierarchy_activation(bad)


def test_hierarchy_activation_mutates_nothing():
    log = GateAuditLog()
    gate, audit = _serve_pair(log, "pkg-hm-nm:part-000")
    ref = _part_ref("pkg-hm-nm", "ch", gate.gate_id, audit.audit_id)
    before = close_part(ref)
    chain = ["director-1", "manager-1", "tool-1"]
    snapshot = list(chain)
    check_hierarchy_activation(chain)
    for bad in ([], ["d", "m"], ["d", "m", "m"]):
        with pytest.raises(INVALID_HIERARCHY_CHAIN):
            check_hierarchy_activation(bad)
    assert chain == snapshot
    after = close_part(ref)
    assert after["evidence_refs"] == before["evidence_refs"]
    assert after["gate"] == after["audit"] == "PASS"
