"""K05 M5 STEP2: error paths not covered by the frozen test_iface_m5.py."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))

import pytest

from agent_si.ab_framework import run_comparison


class M5Step2Cloud:  # FAKE-OF: src/agent_si/cloud/adapter.py
    def __init__(self, m5_calls):
        self.m5_calls = m5_calls

    def m5_cloud_generate(self, task_class):
        self.m5_calls.append("m5_cloud_generate")
        return {"m5_tokens": 1, "m5_cost": 0.5, "m5_quality": 0.5}


class M5Step2Local:  # FAKE-OF: src/agent_si/local/adapter.py
    def __init__(self, m5_calls):
        self.m5_calls = m5_calls

    def m5_local_draft(self, task_class):
        self.m5_calls.append("m5_local_draft")
        return {"m5_draft": "d", "m5_tokens": 1, "m5_cost": 0.5,
                "m5_quality": 0.5}


class M5Step2Router:  # FAKE-OF: src/agent_si/routing/router.py
    def __init__(self, m5_calls):
        self.m5_calls = m5_calls

    def m5_cloud_verify(self, draft):
        self.m5_calls.append("m5_cloud_verify")
        return {"m5_verified": True, "m5_tokens": 1, "m5_cost": 0.5,
                "m5_quality": 0.5}


class M5Step2Audit:  # FAKE-OF: src/agent_si/assurance/coordinator.py
    def __init__(self, m5_calls):
        self.m5_calls = m5_calls

    def m5_audit(self, verified):
        self.m5_calls.append("m5_audit")
        return {"m5_pass": True, "m5_score": 0.5, "m5_verified": verified}


def m5_step2_settings(m5_repeats):
    m5_cfg = {
        "m5_acceptance": "m5-ac-1",
        "m5_audit_standard": "m5-audit-std",
        "m5_settings_rev": "m5-rev-1",
        "m5_repeats": m5_repeats,
    }
    return {
        "m5_legs": {
            "m5_cloud_only": {
                "m5_cloud": M5Step2Cloud([]),
                "m5_audit": M5Step2Audit([]),
            },
            "m5_local_assisted": {
                "m5_local": M5Step2Local([]),
                "m5_router": M5Step2Router([]),
                "m5_audit": M5Step2Audit([]),
            },
        },
        "m5_arms": {
            "m5_cloud_only": dict(m5_cfg),
            "m5_local_assisted": dict(m5_cfg),
        },
    }


@pytest.mark.parametrize("m5_repeats", [True, False])
def test_m5_step2_bool_repeats_rejected(m5_repeats):
    with pytest.raises(ValueError, match="m5_repeat_count_invalid"):
        run_comparison("m5-task-class", "m5-ac-1", "m5-audit-std",
                       m5_step2_settings(2), m5_repeats)


def test_m5_step2_arm_missing_key_mismatches():
    m5_settings = m5_step2_settings(2)
    del m5_settings["m5_arms"]["m5_local_assisted"]["m5_settings_rev"]
    with pytest.raises(ValueError, match="m5_acceptance_mismatch"):
        run_comparison("m5-task-class", "m5-ac-1", "m5-audit-std",
                       m5_settings, 2)
