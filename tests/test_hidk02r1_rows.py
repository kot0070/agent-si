"""HIDK02R1 row 102/117 behaviour checks through delta.close_with_linkcheck."""

from agent_si.backend.orchestration import delta


def test_hidk02r1_row102_joint_failure_preserved():
    taken = delta.intake_bounded_delta(["h102-joint"], True)
    verdict = {
        "package_id": "h102",
        "gate": "FAIL",
        "audit": "FAIL",
        "decided_at": "h102-t",
        "evidence_refs": ["h102-evidence"],
    }
    closed = delta.close_with_linkcheck(dict(taken), dict(verdict))
    assert closed["gate"] == "FAIL"
    assert closed["audit"] == "FAIL"
    assert "h102-evidence" in closed["evidence_refs"]


def test_hidk02r1_row102_empty_evidence_still_blocked():
    taken = delta.intake_bounded_delta(["h102-joint"], True)
    verdict = {
        "package_id": "h102",
        "gate": "FAIL",
        "audit": "FAIL",
        "decided_at": "h102-t",
        "evidence_refs": [],
    }
    closed = delta.close_with_linkcheck(dict(taken), dict(verdict))
    assert closed["gate"] == "BLOCKED" and closed["audit"] == "BLOCKED"


def test_hidk02r1_row102_mixed_still_blocked():
    pkg = delta.intake_bounded_delta(["h102-mixed"], False)
    mixed_gate = {
        "package_id": "h102",
        "gate": "FAIL",
        "audit": "PASS",
        "decided_at": "h102-t",
        "evidence_refs": ["h102-evidence"],
    }
    closed_gate = delta.close_with_linkcheck(dict(pkg), dict(mixed_gate))
    assert closed_gate["gate"] == "BLOCKED"
    mixed_audit = {
        "package_id": "h102",
        "gate": "PASS",
        "audit": "REWORK",
        "decided_at": "h102-t",
        "evidence_refs": ["h102-evidence"],
    }
    closed_audit = delta.close_with_linkcheck(dict(pkg), dict(mixed_audit))
    assert closed_audit["gate"] == "BLOCKED"


def test_hidk02r1_row117_valid_evidence_passes():
    first = delta.intake_bounded_delta(["h117-a"], False)
    verdict = {
        "package_id": "h117",
        "gate": "PASS",
        "audit": "PASS",
        "decided_at": "h117-t",
        "evidence_refs": ["h117-evidence"],
    }
    closed = delta.close_with_linkcheck(dict(first), dict(verdict))
    assert closed["gate"] == "PASS" and closed["audit"] == "PASS"
    assert "linkcheck:ok" in closed["evidence_refs"]


def test_hidk02r1_row117_empty_evidence_blocked():
    taken = delta.intake_bounded_delta(["h117-c"], False)
    verdict = {
        "package_id": "h117",
        "gate": "PASS",
        "audit": "PASS",
        "decided_at": "h117-t",
        "evidence_refs": [],
    }
    closed = delta.close_with_linkcheck(dict(taken), dict(verdict))
    assert closed["gate"] == "BLOCKED" and closed["audit"] == "BLOCKED"
