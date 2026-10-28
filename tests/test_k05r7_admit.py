"""K05R7 M-ADMIT behaviour proofs: admission gate + verifier link + routing policy.

Rows (Director matrix; K05R7 M-ADMIT lane):
- B0B-BP02-63: admission tier gate (UNKNOWN never admitted).
- B0B-BP02-68: admission health gate (healthy signal only).
- B0B-BP02-77: admission gateway gate (idle only, never forced).
- B0B-BP02-88: admission permission gate (allowlisted scope only).
- B0B-UNCOVERED_MVP_ACCEPT-19: verifier record binds refs via draft hash.
- B0B-UNCOVERED_MVP_ACCEPT-57: verifier re-examines content, confirms link.
- SPEC 26 ROUTING_POLICY: thresholds 100/85/50, NO-DATA branch, A/B/C.

Every proof runs through the real adapter entry points only. No fakes,
no fixtures, no canned product logic.
"""

from __future__ import annotations

import dataclasses
import hashlib
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from agent_si.local import adapter  # noqa: E402

IDLE_GATEWAY = "gateway-state-idle"
BUSY_GATEWAY = "gateway-state-user-bench-running"
HEALTHY = "model-health-healthy"
UNHEALTHY = "model-health-unhealthy"
ALLOWED_SCOPE = "local-contact-allowed"

MEASURED_ADMIT_REF = "store-ref-k05r7-measured-routing-eligibility"
STATIC_ADMIT_REF = "store-ref-k05r7-static-verified-branch-b"


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --- B0B-BP02-63: admission tier gate ---


def test_admit_63_measured_evidence_admits():
    verdict = adapter.check_admission(
        MEASURED_ADMIT_REF, HEALTHY, IDLE_GATEWAY, ALLOWED_SCOPE
    )
    assert verdict.admitted is True
    assert verdict.gate_allowed is True
    assert verdict.admission_refs == (
        MEASURED_ADMIT_REF,
        HEALTHY,
        IDLE_GATEWAY,
        ALLOWED_SCOPE,
    )
    assert verdict.admission_source == "capability-store/health/gateway/permission"


def test_admit_63_unknown_tier_never_admitted():
    verdict = adapter.check_admission(
        "store-ref-k05r7-unknown", HEALTHY, IDLE_GATEWAY, ALLOWED_SCOPE
    )
    assert verdict.admitted is False
    assert "UNKNOWN_TIER_INELIGIBLE" in verdict.reason


def test_admit_63_bare_label_never_admits():
    verdict = adapter.check_admission("measured", HEALTHY, IDLE_GATEWAY, ALLOWED_SCOPE)
    assert verdict.admitted is False
    assert "ROUTING_ELIGIB" in verdict.reason


def test_admit_branch_b_static_verified_admits():
    verdict = adapter.check_admission(
        STATIC_ADMIT_REF, HEALTHY, IDLE_GATEWAY, ALLOWED_SCOPE
    )
    assert verdict.admitted is True
    assert verdict.gate_allowed is True
    assert verdict.admission_refs[0] == STATIC_ADMIT_REF


def test_admit_63_verdict_is_frozen_record():
    verdict = adapter.check_admission(
        MEASURED_ADMIT_REF, HEALTHY, IDLE_GATEWAY, ALLOWED_SCOPE
    )
    assert dataclasses.is_dataclass(verdict)
    with pytest.raises(dataclasses.FrozenInstanceError):
        verdict.admitted = not verdict.admitted


# --- B0B-BP02-68: admission health gate ---


def test_admit_68_healthy_signal_admits():
    verdict = adapter.check_admission(
        MEASURED_ADMIT_REF, HEALTHY, IDLE_GATEWAY, ALLOWED_SCOPE
    )
    assert verdict.admitted is True


def test_admit_68_unhealthy_refused():
    verdict = adapter.check_admission(
        MEASURED_ADMIT_REF, UNHEALTHY, IDLE_GATEWAY, ALLOWED_SCOPE
    )
    assert verdict.admitted is False
    assert "ADMISSION_HEALTH_REFUSED" in verdict.reason


def test_admit_68_missing_signal_refused_fail_closed():
    for health in ("", "model-health-unknown", "model-health-degraded"):
        verdict = adapter.check_admission(
            MEASURED_ADMIT_REF, health, IDLE_GATEWAY, ALLOWED_SCOPE
        )
        assert verdict.admitted is False
        assert "ADMISSION_HEALTH_REFUSED" in verdict.reason


# --- B0B-BP02-77: admission gateway gate ---


def test_admit_77_busy_gateway_refuses():
    verdict = adapter.check_admission(
        MEASURED_ADMIT_REF, HEALTHY, BUSY_GATEWAY, ALLOWED_SCOPE
    )
    assert verdict.admitted is False
    assert verdict.gate_allowed is False
    assert "GATEWAY_BUSY" in verdict.reason


# --- B0B-BP02-88: admission permission gate ---


def test_admit_88_allowlisted_scope_admits():
    assert adapter.ADMISSION_ALLOWED_PERMISSION_SCOPES == ("local-contact-allowed",)
    verdict = adapter.check_admission(
        MEASURED_ADMIT_REF, HEALTHY, IDLE_GATEWAY, ALLOWED_SCOPE
    )
    assert verdict.admitted is True


def test_admit_88_other_scope_refused():
    verdict = adapter.check_admission(
        MEASURED_ADMIT_REF, HEALTHY, IDLE_GATEWAY, "cloud-contact-allowed"
    )
    assert verdict.admitted is False
    assert "ADMISSION_PERMISSION_REFUSED" in verdict.reason


def test_admit_role_config_refs_raise():
    with pytest.raises(Exception) as excinfo:
        adapter.check_admission("model_id", HEALTHY, IDLE_GATEWAY, ALLOWED_SCOPE)
    assert "CAPABILITY_ROLE_CONFIG_AS_TASK_CLASS_REFUSED" in str(excinfo.value)
    with pytest.raises(Exception) as excinfo:
        adapter.check_admission(
            MEASURED_ADMIT_REF, HEALTHY, IDLE_GATEWAY, "permission_scope"
        )
    assert "CAPABILITY_ROLE_CONFIG_AS_TASK_CLASS_REFUSED" in str(excinfo.value)


# --- B0B-UNCOVERED_MVP_ACCEPT-19: verifier record refs draft hash ---


def test_admit_19_record_binds_refs_via_hash():
    record = adapter.record_verifier_decision(
        "verify-ref-k05r7-1", "draft-ref-k05r7-1", "draft-hash-k05r7-1"
    )
    assert (record.verifier_ref, record.draft_ref, record.draft_hash) == (
        "verify-ref-k05r7-1",
        "draft-ref-k05r7-1",
        "draft-hash-k05r7-1",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.draft_hash = "tampered"


def test_admit_19_empty_refs_raise():
    with pytest.raises(ValueError):
        adapter.record_verifier_decision("", "draft-ref-k05r7-1", "draft-hash-k05r7-1")
    with pytest.raises(ValueError):
        adapter.record_verifier_decision(
            "verify-ref-k05r7-1", "", "draft-hash-k05r7-1"
        )
    with pytest.raises(ValueError):
        adapter.record_verifier_decision("verify-ref-k05r7-1", "draft-ref-k05r7-1", "")


# --- B0B-UNCOVERED_MVP_ACCEPT-57: re-examines content + confirms link ---


def test_admit_57_matching_content_reexamines_true():
    content = "k05r7 local draft body"
    record = adapter.record_verifier_decision(
        "verify-ref-k05r7-2", "draft-ref-k05r7-2", _digest(content)
    )
    assert adapter.reexamine_verifier_content(record, content, _digest(content)) is True


def test_admit_57_tampered_content_reexamines_false():
    record = adapter.record_verifier_decision(
        "verify-ref-k05r7-3", "draft-ref-k05r7-3", _digest("original")
    )
    assert (
        adapter.reexamine_verifier_content(record, "tampered", _digest("tampered"))
        is False
    )
    assert adapter.reexamine_verifier_content(record, "", _digest("original")) is False


def test_admit_57_confirms_link():
    record = adapter.record_verifier_decision(
        "verify-ref-k05r7-4", "draft-ref-k05r7-4", "draft-hash-k05r7-4"
    )
    assert adapter.confirm_verifier_link(record, "draft-ref-k05r7-4") is True
    assert adapter.confirm_verifier_link(record, "draft-ref-k05r7-other") is False


def test_admit_57_record_shape_misuse_raises():
    with pytest.raises(ValueError):
        adapter.reexamine_verifier_content("not-a-record", "x", "y")
    with pytest.raises(ValueError):
        adapter.confirm_verifier_link("not-a-record", "draft-ref-k05r7-4")


# --- SPEC 26 ROUTING_POLICY: thresholds 100/85/50, NO-DATA, A/B/C ---


def test_admit_spec26_thresholds_exact():
    assert adapter.ROUTING_POLICY_THRESHOLDS == (100, 85, 50)
    assert adapter.ROUTING_POLICY_BRANCHES == ("A", "B", "C")
    assert adapter.ROUTING_POLICY_NO_DATA_BRANCH == "NO-DATA"


def test_admit_spec26_branches():
    assert adapter.route_by_policy(100) == "A"
    assert adapter.route_by_policy(140) == "A"
    assert adapter.route_by_policy(85) == "B"
    assert adapter.route_by_policy(99) == "B"
    assert adapter.route_by_policy(50) == "C"
    assert adapter.route_by_policy(84) == "C"


def test_admit_spec26_no_data_branch():
    assert adapter.route_by_policy(None) == "NO-DATA"
    assert adapter.route_by_policy(49) == "NO-DATA"
    assert adapter.route_by_policy(0) == "NO-DATA"
    assert adapter.route_by_policy(float("nan")) == "NO-DATA"


def test_admit_spec26_bad_score_raises():
    for bad in (True, False, "85", (85,), object()):
        with pytest.raises(ValueError):
            adapter.route_by_policy(bad)
