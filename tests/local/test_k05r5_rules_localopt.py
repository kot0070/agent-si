"""K05R5 M-RULES2 behaviour proofs: 60.CORE_RULES R15-R17, R51, R137, R199, R201.

Each rule below is quoted verbatim from kit PRODUCT_SPEC.md 60.CORE_RULES
and proven through a real owned entry point (no faked product logic; fakes
live here only as FAKE-OF legs for the ab_framework comparison, mirroring
the frozen M5 interface shape). Branch-B tests (static-verified) fail
before the adapter change and pass after it; every other test passes
before and after (characterization of the already-correct path).
"""

from __future__ import annotations

import inspect
import pathlib
import sys
import uuid

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))

from agent_si.ab_framework import run_comparison  # noqa: E402
from agent_si.capability_store import store  # noqa: E402
from agent_si.local import adapter  # noqa: E402
from agent_si.local import config  # noqa: E402
from agent_si.local import gateway  # noqa: E402
from agent_si.local import k05r3_discover as discover  # noqa: E402

IDLE_GATEWAY = "gateway-state-idle"
BUSY_GATEWAY = "gateway-state-user-bench-running"

STATIC_BRANCH_A_REF = "store-ref-heron-measured-branch-a"
STATIC_BRANCH_B_REF = "store-ref-heron-static-verified-branch-b"
STATIC_BRANCH_B_CAP_REF = "cap:heron-model:heron-summarize-static-verified:v1"


def _fresh_key(prefix: str) -> str:
    return "%s-%s" % (prefix, uuid.uuid4().hex[:12])


# --- R15 Local AI is optional. ---


def test_r15_routing_continues_when_local_absent():
    assert adapter.routing_continues(adapter.STATUS_NOT_CONFIGURED) is True


def test_r15_absent_evidence_returns_verdict_not_error():
    verdict = adapter.check_eligibility("store-ref-heron-unknown", IDLE_GATEWAY)
    assert verdict.eligible is False
    assert "UNKNOWN_TIER_INELIGIBLE" in verdict.reason
    assert verdict.evidence_refs == (
        "store-ref-heron-unknown",
        IDLE_GATEWAY,
    )


def test_r15_gateway_contact_never_forced():
    assert "force" not in inspect.signature(gateway.passive_check).parameters


# --- R16 Capability database is optional. ---


def test_r16_store_reports_not_configured_and_routing_continues():
    handle = store.CapabilityStore(base_ref=None, status=store.NOT_CONFIGURED)
    assert handle.status == "NOT_CONFIGURED"
    assert adapter.routing_continues(handle.status) is True


def test_r16_unknown_key_yields_no_row_without_base():
    assert store.get_evidence(_fresh_key("heron-model"), "heron-coding") is None


def test_r16_local_config_roundtrip_without_capability_base():
    project_key = _fresh_key("heron-proj")
    decision = config.record_decision(
        project_key, "heron local-only setup", "r16 optional base", "owner-check"
    )
    saved = config.save_config(
        config.LocalAIConfig(
            project_key=project_key,
            endpoint_url="http://127.0.0.1:11434",
            model_id="heron-model",
            permission_scope="local-contact-allowed",
            local_only_mode=True,
            capability_evidence="UNKNOWN",
        ),
        decision,
    )
    try:
        loaded = config.load_config(project_key, project_key)
        assert loaded == saved
        assert config.local_only_warnings(loaded) != []
    finally:
        del config._STORE[project_key]


# --- R17 No full-drive Local AI scan. ---


def test_r17_full_drive_root_refused(tmp_path):
    import os

    drive = os.path.splitdrive(str(tmp_path))[0] + os.sep
    with pytest.raises(discover.DiscoverError) as excinfo:
        discover.scan_roots([str(tmp_path)], drive)
    assert excinfo.value.code == discover.K05R3_DISCOVER_SCAN_REFUSED


def test_r17_scan_stays_allowlisted_metadata_only(tmp_path):
    target = tmp_path / "models"
    target.mkdir()
    (target / "b-model").write_text("x", encoding="utf-8")
    (target / "a-model").write_text("x", encoding="utf-8")
    assert discover.scan_roots([str(tmp_path)], str(target)) == ["a-model", "b-model"]
    creds = tmp_path / "credentials"
    creds.mkdir()
    with pytest.raises(discover.DiscoverError) as excinfo:
        discover.scan_roots([str(tmp_path)], str(creds))
    assert excinfo.value.code == discover.K05R3_DISCOVER_SCAN_REFUSED
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    with pytest.raises(discover.DiscoverError) as excinfo:
        discover.scan_roots([str(tmp_path / "models")], str(outside))
    assert excinfo.value.code == discover.K05R3_DISCOVER_SCAN_REFUSED


# --- R51 Local AI without a capability database may use the verified
# non-benchmark eligibility path; UNKNOWN is never assumed capable. ---


def test_r51_static_path_eligible_without_capability_db():
    model = _fresh_key("heron-model")
    assert store.get_evidence(model, "heron-summarize") is None
    verdict = adapter.check_eligibility(STATIC_BRANCH_B_REF, IDLE_GATEWAY)
    assert verdict.eligible is True
    assert verdict.gateway_allowed is True
    assert verdict.evidence_refs == (STATIC_BRANCH_B_REF, IDLE_GATEWAY)


def test_r51_unknown_never_capable_without_db():
    verdict = adapter.check_eligibility("store-ref-heron-unknown", IDLE_GATEWAY)
    assert verdict.eligible is False
    assert "UNKNOWN_TIER_INELIGIBLE" in verdict.reason


def test_r51_busy_gateway_still_refuses_static_path():
    verdict = adapter.check_eligibility(STATIC_BRANCH_B_REF, BUSY_GATEWAY)
    assert verdict.eligible is False
    assert verdict.gateway_allowed is False


# --- R137 Local eligibility is branch-based: benchmark evidence OR verified
# static capability OR explicit pin, with common hard gates. ---


def test_r137_branch_a_benchmark_evidence_eligible():
    verdict = adapter.check_eligibility(STATIC_BRANCH_A_REF, IDLE_GATEWAY)
    assert verdict.eligible is True
    assert "store" in verdict.eligibility_source
    assert "gateway" in verdict.eligibility_source


def test_r137_branch_b_verified_static_eligible():
    verdict = adapter.check_eligibility(STATIC_BRANCH_B_CAP_REF, IDLE_GATEWAY)
    assert verdict.eligible is True
    assert verdict.gateway_allowed is True
    assert isinstance(verdict.evidence_refs, tuple) and verdict.evidence_refs


def test_r137_bare_static_label_not_routing_eligibility():
    verdict = adapter.check_eligibility("static-verified", IDLE_GATEWAY)
    assert verdict.eligible is False
    assert verdict.gateway_allowed is True
    assert "ROUTING_ELIGIB" in verdict.reason


def test_r137_branch_c_explicit_pin_unverified_zero_measured():
    decision = adapter.record_explicit_pin("heron-local-model")
    assert decision.route == adapter.ROUTE_EXPLICIT_PIN
    assert decision.quality_basis == "UNVERIFIED_PIN"
    assert decision.measured_evidence_count == 0
    assert decision.capability_evidence_refs == ("heron-local-model",)


def test_r137_common_hard_gates_busy_and_no_skip():
    assert adapter.check_eligibility(STATIC_BRANCH_A_REF, BUSY_GATEWAY).eligible is False
    assert adapter.check_eligibility(STATIC_BRANCH_B_REF, BUSY_GATEWAY).eligible is False
    with pytest.raises(Exception) as excinfo:
        adapter.advance_lifecycle(
            adapter.LifecycleStage.SCAN, adapter.LifecycleStage.IDENTIFY
        )
    assert "LIFECYCLE_SKIP_REFUSED" in str(excinfo.value)


# --- R199 Economic principle: Manager plus cheaper and local agents absorb
# bulk work; frontier and cloud capacity serve high-risk reasoning and final
# verification. ---


class _HeronCloud:  # FAKE-OF: cloud generate leg (bulk work done expensively)
    def __init__(self, calls):
        self.calls = calls

    def m5_cloud_generate(self, task_class):
        self.calls.append("m5_cloud_generate")
        return {"m5_tokens": 400, "m5_cost": 2.5, "m5_quality": 0.9}


class _HeronLocal:  # FAKE-OF: local draft leg (bulk work done cheaply)
    def __init__(self, calls):
        self.calls = calls

    def m5_local_draft(self, task_class):
        self.calls.append("m5_local_draft")
        return {"m5_draft": "heron-draft", "m5_tokens": 10, "m5_cost": 0.05,
                "m5_quality": 0.6}


class _HeronVerify:  # FAKE-OF: frontier cloud verification leg
    def __init__(self, calls):
        self.calls = calls
        self.seen = []

    def m5_cloud_verify(self, draft):
        self.calls.append("m5_cloud_verify")
        self.seen.append(draft)
        return {"m5_verified": True, "m5_draft": draft, "m5_tokens": 60,
                "m5_cost": 0.4, "m5_quality": 0.85}


class _HeronAudit:  # FAKE-OF: final audit leg recording what it audited
    def __init__(self, calls, score):
        self.calls = calls
        self.score = score
        self.audited = []

    def m5_audit(self, verified):
        self.calls.append("m5_audit")
        self.audited.append(verified)
        return {"m5_pass": True, "m5_score": self.score, "m5_verified": verified}


def _heron_settings():
    cfg = {
        "m5_acceptance": "heron-ac",
        "m5_audit_standard": "heron-audit-std",
        "m5_settings_rev": "heron-rev",
        "m5_repeats": 2,
    }
    cloud_calls: list = []
    local_calls: list = []
    verify = _HeronVerify(local_calls)
    audit_local = _HeronAudit(local_calls, 0.7)
    return (
        {
            "m5_legs": {
                "m5_cloud_only": {
                    "m5_cloud": _HeronCloud(cloud_calls),
                    "m5_audit": _HeronAudit(cloud_calls, 0.9),
                },
                "m5_local_assisted": {
                    "m5_local": _HeronLocal(local_calls),
                    "m5_router": verify,
                    "m5_audit": audit_local,
                },
            },
            "m5_arms": {
                "m5_cloud_only": dict(cfg),
                "m5_local_assisted": dict(cfg),
            },
        },
        local_calls,
        verify,
        audit_local,
    )


def test_r199_local_arm_savings_recorded_same_standard():
    settings, _, _, _ = _heron_settings()
    report = run_comparison("heron-task", "heron-ac", "heron-audit-std", settings, 2)
    assert report.tokens["m5_local_assisted"] == (10 + 60) * 2
    assert report.tokens["m5_cloud_only"] == 400 * 2
    assert report.cost["m5_local_assisted"] == pytest.approx((0.05 + 0.4) * 2)
    assert report.cost["m5_cloud_only"] == pytest.approx(2.5 * 2)
    assert report.cost["m5_local_assisted"] < report.cost["m5_cloud_only"]
    assert report.deltas["cost"] == pytest.approx(
        report.cost["m5_local_assisted"] - report.cost["m5_cloud_only"]
    )
    assert len(report.evidence_refs) == 4


def test_r199_arm_standard_mismatch_rejected():
    settings, _, _, _ = _heron_settings()
    settings["m5_arms"]["m5_local_assisted"]["m5_acceptance"] = "heron-ac-other"
    with pytest.raises(ValueError, match="m5_acceptance_mismatch"):
        run_comparison("heron-task", "heron-ac", "heron-audit-std", settings, 2)


# --- R201 Every SPLIT includes real cloud verification of local output. ---


def test_r201_cloud_verify_runs_before_audit_on_verified_output():
    settings, local_calls, verify, audit_local = _heron_settings()
    run_comparison("heron-task", "heron-ac", "heron-audit-std", settings, 2)
    assert local_calls == ["m5_local_draft", "m5_cloud_verify", "m5_audit"] * 2
    assert len(verify.seen) == 2
    assert len(audit_local.audited) == 2
    for audited, draft in zip(audit_local.audited, verify.seen):
        assert audited["m5_verified"] is True
        assert audited["m5_draft"] is draft


def test_r201_split_assignment_requires_cloud_verify_ref():
    split = adapter.record_split_decision("heron-draft", "heron-verify", "heron-hash")
    assert (split.local_draft_ref, split.cloud_verify_ref) == (
        "heron-draft",
        "heron-verify",
    )
    assert split.draft_hash == "heron-hash"
    with pytest.raises(ValueError):
        adapter.record_split_decision("heron-draft", "", "heron-hash")
    with pytest.raises(ValueError):
        adapter.record_split_decision("", "heron-verify", "heron-hash")
