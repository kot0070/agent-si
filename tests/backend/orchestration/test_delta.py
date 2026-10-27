import copy
import os
import sys

import pytest

sys.path.insert(
    0,
    os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
    ),
)

from agent_si.backend.orchestration import delta as dl


def _verdict(package_id, gate="PASS", audit="PASS", refs=None):
    return {
        "package_id": package_id,
        "gate": gate,
        "audit": audit,
        "decided_at": "2026-01-01T00:00:00Z",
        "evidence_refs": ["ev:1"] if refs is None else refs,
    }


def test_bound_16_ok():
    scope = [f"s-{i:02d}" for i in range(16)]
    pkg = dl.intake_bounded_delta(scope, False)
    assert pkg["scope"] == scope
    assert pkg["keep"] == scope
    assert pkg["patch"] == []
    assert pkg["blocking"] is False
    assert isinstance(pkg["delta_id"], str) and pkg["delta_id"].startswith("delta-")
    assert isinstance(pkg["created_at"], str) and pkg["created_at"] != ""


def test_bound_17_raises():
    scope = [f"s-{i:02d}" for i in range(17)]
    with pytest.raises(dl.DELTA_OVER_BOUND):
        dl.intake_bounded_delta(scope, False)


def test_intake_idempotent_same_input_same_id():
    a = dl.intake_bounded_delta(["alpha", "beta"], False)
    b = dl.intake_bounded_delta(["alpha", "beta"], False)
    assert a["delta_id"] == b["delta_id"]


def test_distinct_scopes_distinct_ids():
    a = dl.intake_bounded_delta(["alpha"], False)
    b = dl.intake_bounded_delta(["beta"], False)
    assert a["delta_id"] != b["delta_id"]


def test_blocking_flag_changes_id():
    a = dl.intake_bounded_delta(["alpha"], False)
    b = dl.intake_bounded_delta(["alpha"], True)
    assert a["delta_id"] != b["delta_id"]


def test_parallel_independence():
    a = dl.intake_bounded_delta(["pa"], False)
    b = dl.intake_bounded_delta(["pb"], False)
    assert a["delta_id"] != b["delta_id"]
    a["keep"].append("MUT")
    a["scope"].append("MUT")
    fresh = dl.intake_bounded_delta(["pa"], False)
    assert fresh["keep"] == ["pa"]
    assert fresh["scope"] == ["pa"]
    assert b["keep"] == ["pb"]


def test_close_pass_link_ok():
    pkg = dl.intake_bounded_delta(["x"], False)
    verdict = _verdict(pkg["delta_id"], "PASS", "PASS", ["ev:1"])
    closed = dl.close_with_linkcheck(pkg, verdict)
    assert closed["package_id"] == pkg["delta_id"]
    assert closed["gate"] == "PASS"
    assert closed["audit"] == "PASS"
    assert "ev:1" in closed["evidence_refs"]
    assert "linkcheck:ok" in closed["evidence_refs"]
    assert isinstance(closed["decided_at"], str) and closed["decided_at"] != ""


def test_close_broken_link_blocked():
    pkg = dl.intake_bounded_delta(["x"], False)
    verdict = _verdict(pkg["delta_id"], "PASS", "PASS", [])
    closed = dl.close_with_linkcheck(pkg, verdict)
    assert closed["gate"] == "BLOCKED"
    assert closed["package_id"] == pkg["delta_id"]
    assert isinstance(closed["evidence_refs"], list) and len(closed["evidence_refs"]) > 0


def test_close_non_pass_gate_blocked():
    pkg = dl.intake_bounded_delta(["x"], False)
    verdict = _verdict(pkg["delta_id"], "FAIL", "PASS", ["ev:1"])
    closed = dl.close_with_linkcheck(pkg, verdict)
    assert closed["gate"] == "BLOCKED"


def test_close_non_pass_audit_blocked():
    pkg = dl.intake_bounded_delta(["x"], False)
    verdict = _verdict(pkg["delta_id"], "PASS", "REWORK", ["ev:1"])
    closed = dl.close_with_linkcheck(pkg, verdict)
    assert closed["gate"] == "BLOCKED"


def test_close_malformed_never_raises():
    closed = dl.close_with_linkcheck({}, {})
    assert closed["gate"] == "BLOCKED"
    assert isinstance(closed["evidence_refs"], list)


def test_cross_check_clean():
    gates = [_verdict("a"), _verdict("b")]
    assert dl.cross_check(["a", "b"], gates) == []


def test_cross_check_conflicts_missing_and_failed():
    gates = [_verdict("a", "PASS", "PASS"), _verdict("b", "FAIL", "PASS")]
    result = dl.cross_check(["a", "b", "c"], gates)
    assert result == ["b", "c"]


def test_cross_check_non_pass_audit_conflict():
    gates = [_verdict("a", "PASS", "REWORK")]
    assert dl.cross_check(["a"], gates) == ["a"]


def test_cross_check_sorted():
    gates = [_verdict("z", "FAIL", "FAIL")]
    result = dl.cross_check(["m", "z", "a"], gates)
    assert result == sorted(result) == ["a", "m", "z"]
