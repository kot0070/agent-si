"""K05 M5 STEP1b contract test: A/B framework interface (RED vs frozen stub).

Contract under test: run_comparison(task_class, acceptance, audit_standard,
settings, repeats) -> ComparisonReport compares a cloud-only arm with a
local-assisted arm on the same task class (same acceptance, audit standard,
settings, repeat count) on tokens, cost, time and quality.

Aggregation rule pinned for the future implementation:
- one repeat of m5_cloud_only = m5_cloud_generate + m5_audit;
  per-repeat tokens/cost are the cloud leg's usage, per-repeat quality is
  the arm's audit score.
- one repeat of m5_local_assisted = m5_local_draft + m5_cloud_verify +
  m5_audit; per-repeat tokens/cost are summed over the arm's legs,
  per-repeat quality is the arm's audit score.
- over N repeats each per-arm report measure is the SUM or the MEAN of the
  per-repeat values; deltas = local-assisted minus cloud-only.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))

import pytest

from agent_si.ab_framework import ComparisonReport, run_comparison


# Distinct per-arm/per-leg usage constants: a hardcoded report cannot match
# both arms at once. Tokens are ints, costs/qualities are floats.
M5_CLOUD_TOKENS = 111
M5_CLOUD_COST = 1.25
M5_CLOUD_QUALITY = 0.81
M5_LOCAL_TOKENS = 222
M5_LOCAL_COST = 0.35
M5_LOCAL_QUALITY = 0.62
M5_VERIFY_TOKENS = 333
M5_VERIFY_COST = 0.75
M5_VERIFY_QUALITY = 0.88
M5_AUDIT_SCORE_CLOUD = 0.91
M5_AUDIT_SCORE_LOCAL = 0.73

M5_CLOUD_ARM_TOKENS_PER_REPEAT = M5_CLOUD_TOKENS
M5_CLOUD_ARM_COST_PER_REPEAT = M5_CLOUD_COST
M5_LOCAL_ARM_TOKENS_PER_REPEAT = M5_LOCAL_TOKENS + M5_VERIFY_TOKENS
M5_LOCAL_ARM_COST_PER_REPEAT = M5_LOCAL_COST + M5_VERIFY_COST

M5_CLOUD_ARM_CALLS = ["m5_cloud_generate", "m5_audit"]
M5_LOCAL_ARM_CALLS = ["m5_local_draft", "m5_cloud_verify", "m5_audit"]


class M5FakeCloudAdapter:  # FAKE-OF: src/agent_si/cloud/adapter.py
    """Test double for the cloud-generation leg used by the cloud-only arm."""

    def __init__(
        self,
        m5_calls,
        m5_tokens=M5_CLOUD_TOKENS,
        m5_cost=M5_CLOUD_COST,
        m5_quality=M5_CLOUD_QUALITY,
    ):
        self.m5_calls = m5_calls
        self.m5_tokens = m5_tokens
        self.m5_cost = m5_cost
        self.m5_quality = m5_quality

    def m5_cloud_generate(self, task_class):
        self.m5_calls.append("m5_cloud_generate")
        return {
            "m5_text": "m5-cloud-answer-for-%s" % (task_class,),
            "m5_tokens": int(self.m5_tokens),
            "m5_cost": float(self.m5_cost),
            "m5_quality": float(self.m5_quality),
        }


class M5FakeLocalAdapter:  # FAKE-OF: src/agent_si/local/adapter.py
    """Test double for the M1 local adapter: produces the local-draft leg."""

    def __init__(
        self,
        m5_calls,
        m5_tokens=M5_LOCAL_TOKENS,
        m5_cost=M5_LOCAL_COST,
        m5_quality=M5_LOCAL_QUALITY,
    ):
        self.m5_calls = m5_calls
        self.m5_tokens = m5_tokens
        self.m5_cost = m5_cost
        self.m5_quality = m5_quality

    def m5_local_draft(self, task_class):
        self.m5_calls.append("m5_local_draft")
        return {
            "m5_draft": "m5-draft-for-%s" % (task_class,),
            "m5_tokens": int(self.m5_tokens),
            "m5_cost": float(self.m5_cost),
            "m5_quality": float(self.m5_quality),
        }


class M5FakeRouter:  # FAKE-OF: src/agent_si/routing/router.py
    """Test double for the K04 router: cloud verification over local output."""

    def __init__(
        self,
        m5_calls,
        m5_tokens=M5_VERIFY_TOKENS,
        m5_cost=M5_VERIFY_COST,
        m5_quality=M5_VERIFY_QUALITY,
    ):
        self.m5_calls = m5_calls
        self.m5_tokens = m5_tokens
        self.m5_cost = m5_cost
        self.m5_quality = m5_quality

    def m5_cloud_verify(self, draft):
        self.m5_calls.append("m5_cloud_verify")
        return {
            "m5_verified": True,
            "m5_draft": draft,
            "m5_tokens": int(self.m5_tokens),
            "m5_cost": float(self.m5_cost),
            "m5_quality": float(self.m5_quality),
        }


class M5FakeAudit:  # FAKE-OF: src/agent_si/assurance/coordinator.py
    """Test double for the K03 assurance audit leg."""

    def __init__(self, m5_calls, m5_score):
        self.m5_calls = m5_calls
        self.m5_score = m5_score

    def m5_audit(self, verified):
        self.m5_calls.append("m5_audit")
        return {
            "m5_pass": True,
            "m5_score": float(self.m5_score),
            "m5_verified": verified,
        }


def m5_arm_config(
    m5_acceptance="m5-ac-1",
    m5_audit_standard="m5-audit-std",
    m5_settings_rev="m5-rev-1",
    m5_repeats=2,
):
    return {
        "m5_acceptance": m5_acceptance,
        "m5_audit_standard": m5_audit_standard,
        "m5_settings_rev": m5_settings_rev,
        "m5_repeats": m5_repeats,
    }


def m5_new_calls():
    """Separate call list per arm: a silent no-op arm stays visible."""
    return {"m5_cloud_only": [], "m5_local_assisted": []}


def m5_settings(m5_calls, m5_cloud=None, m5_local=None):
    m5_cloud_calls = m5_calls["m5_cloud_only"]
    m5_local_calls = m5_calls["m5_local_assisted"]
    return {
        "m5_legs": {
            "m5_cloud_only": {
                "m5_cloud": M5FakeCloudAdapter(m5_cloud_calls),
                "m5_audit": M5FakeAudit(m5_cloud_calls, M5_AUDIT_SCORE_CLOUD),
            },
            "m5_local_assisted": {
                "m5_local": M5FakeLocalAdapter(m5_local_calls),
                "m5_router": M5FakeRouter(m5_local_calls),
                "m5_audit": M5FakeAudit(m5_local_calls, M5_AUDIT_SCORE_LOCAL),
            },
        },
        "m5_arms": {
            "m5_cloud_only": m5_cloud or m5_arm_config(),
            "m5_local_assisted": m5_local or m5_arm_config(),
        },
    }


def m5_run(m5_calls, **m5_kwargs):
    m5_params = {
        "task_class": "m5-task-class",
        "acceptance": "m5-ac-1",
        "audit_standard": "m5-audit-std",
        "settings": m5_settings(m5_calls),
        "repeats": 2,
    }
    m5_params.update(m5_kwargs)
    return run_comparison(**m5_params)


def m5_arm_value(m5_measure, m5_arm):
    if isinstance(m5_measure, dict):
        return m5_measure[m5_arm]
    return getattr(m5_measure, m5_arm)


def m5_reported_repeats(m5_result):
    for m5_attr in ("repeats", "m5_repeats"):
        if hasattr(m5_result, m5_attr):
            return getattr(m5_result, m5_attr)
    m5_values = {
        m5_cfg.get("m5_repeats") for m5_cfg in m5_result.arm_configs.values()
    }
    assert len(m5_values) == 1
    return m5_values.pop()


def test_m5_frozen_names_importable_callable():
    assert isinstance(ComparisonReport, type)
    assert callable(run_comparison)


def test_m5_run_comparison_returns_report():
    m5_calls = m5_new_calls()
    m5_result = m5_run(m5_calls)
    assert m5_result is not None
    assert m5_result is not Ellipsis
    assert isinstance(m5_result, ComparisonReport)


def test_m5_report_fields_deltas_configs_evidence():
    m5_calls = m5_new_calls()
    m5_result = m5_run(m5_calls)
    assert m5_result is not None
    assert m5_result is not Ellipsis
    for m5_field in (
        "tokens",
        "cost",
        "time",
        "quality",
        "deltas",
        "arm_configs",
        "evidence_refs",
    ):
        assert hasattr(m5_result, m5_field), m5_field
    for m5_arm in ("m5_cloud_only", "m5_local_assisted"):
        assert m5_arm in m5_result.arm_configs
        for m5_field in ("tokens", "cost", "time", "quality"):
            assert m5_arm in getattr(m5_result, m5_field)
    for m5_field in ("tokens", "cost", "time", "quality"):
        m5_arm_value(m5_result.deltas, m5_field)
    assert m5_result.evidence_refs


@pytest.mark.parametrize("m5_repeats", [0, -1, -100, "2", 2.0, None, [2]])
def test_m5_repeat_count_invalid(m5_repeats):
    m5_calls = m5_new_calls()
    with pytest.raises(ValueError, match="m5_repeat_count_invalid"):
        m5_run(m5_calls, repeats=m5_repeats)


@pytest.mark.parametrize(
    "m5_key,m5_bad",
    [
        ("m5_acceptance", "m5-ac-2"),
        ("m5_audit_standard", "m5-audit-other"),
        ("m5_settings_rev", "m5-rev-2"),
        ("m5_repeats", 3),
    ],
)
def test_m5_arm_mismatch_rejected(m5_key, m5_bad):
    m5_calls = m5_new_calls()
    m5_local = m5_arm_config()
    m5_local[m5_key] = m5_bad
    with pytest.raises(ValueError, match="m5_acceptance_mismatch"):
        m5_run(m5_calls, settings=m5_settings(m5_calls, m5_local=m5_local))


def test_m5_per_arm_call_sequences_repeats1():
    m5_calls = m5_new_calls()
    m5_run(m5_calls, repeats=1)
    assert m5_calls["m5_cloud_only"] == M5_CLOUD_ARM_CALLS
    assert "m5_local_draft" not in m5_calls["m5_cloud_only"]
    assert m5_calls["m5_local_assisted"] == M5_LOCAL_ARM_CALLS


def test_m5_repeats2_each_arm_ran_twice_and_report_states_repeats():
    m5_calls = m5_new_calls()
    m5_result = m5_run(m5_calls, repeats=2)
    assert m5_calls["m5_cloud_only"] == M5_CLOUD_ARM_CALLS * 2
    assert m5_calls["m5_local_assisted"] == M5_LOCAL_ARM_CALLS * 2
    assert m5_reported_repeats(m5_result) == 2


def test_m5_report_measures_come_from_fake_legs():
    m5_calls = m5_new_calls()
    m5_repeats = 2
    m5_result = m5_run(m5_calls, repeats=m5_repeats)
    m5_expected = {
        "m5_cloud_only": {
            "tokens": M5_CLOUD_ARM_TOKENS_PER_REPEAT,
            "cost": M5_CLOUD_ARM_COST_PER_REPEAT,
            "quality": M5_AUDIT_SCORE_CLOUD,
        },
        "m5_local_assisted": {
            "tokens": M5_LOCAL_ARM_TOKENS_PER_REPEAT,
            "cost": M5_LOCAL_ARM_COST_PER_REPEAT,
            "quality": M5_AUDIT_SCORE_LOCAL,
        },
    }
    for m5_arm in ("m5_cloud_only", "m5_local_assisted"):
        for m5_field in ("tokens", "cost", "quality"):
            m5_actual = m5_arm_value(getattr(m5_result, m5_field), m5_arm)
            m5_per_repeat = m5_expected[m5_arm][m5_field]
            m5_sum = m5_per_repeat * m5_repeats
            assert m5_actual == pytest.approx(m5_sum) or m5_actual == pytest.approx(
                m5_per_repeat
            )
        assert isinstance(
            m5_arm_value(m5_result.tokens, m5_arm), int
        ), "tokens must be int, not a float constant"
        m5_time = m5_arm_value(m5_result.time, m5_arm)
        assert isinstance(m5_time, (int, float))
        assert m5_time > 0, "time must be measured, never a zero constant"


def test_m5_deltas_local_assisted_minus_cloud_only():
    m5_calls = m5_new_calls()
    m5_result = m5_run(m5_calls, repeats=2)
    for m5_field in ("tokens", "cost", "time", "quality"):
        m5_delta = m5_arm_value(m5_result.deltas, m5_field)
        m5_expected = m5_arm_value(
            getattr(m5_result, m5_field), "m5_local_assisted"
        ) - m5_arm_value(getattr(m5_result, m5_field), "m5_cloud_only")
        assert m5_delta == pytest.approx(m5_expected)


@pytest.mark.parametrize(
    "m5_kwarg,m5_bad",
    [
        ("acceptance", "m5-ac-OTHER"),
        ("audit_standard", "m5-audit-OTHER"),
    ],
)
def test_m5_top_level_config_mismatch_rejected(m5_kwarg, m5_bad):
    m5_calls = m5_new_calls()
    with pytest.raises(ValueError, match="m5_acceptance_mismatch"):
        m5_run(m5_calls, **{m5_kwarg: m5_bad})
