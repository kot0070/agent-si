"""K05 M5 A/B framework: real cloud-only vs local-assisted comparison."""

from __future__ import annotations

import time

M5_CLOUD_ARM = "m5_cloud_only"
M5_LOCAL_ARM = "m5_local_assisted"
M5_ARM_CONFIG_KEYS = (
    "m5_acceptance",
    "m5_audit_standard",
    "m5_settings_rev",
    "m5_repeats",
)


class ComparisonReport:
    """Summed per-arm measures plus local-assisted-minus-cloud-only deltas."""

    def __init__(
        self,
        *,
        tokens,
        cost,
        time,
        quality,
        deltas,
        arm_configs,
        evidence_refs,
        repeats,
    ):
        self.tokens = tokens
        self.cost = cost
        self.time = time
        self.quality = quality
        self.deltas = deltas
        self.arm_configs = arm_configs
        self.evidence_refs = evidence_refs
        self.repeats = repeats
        self.m5_repeats = repeats


def _m5_check_repeats(repeats):
    if type(repeats) is not int or repeats < 1:
        raise ValueError(
            "m5_repeat_count_invalid: repeats must be an int >= 1, got %r"
            % (repeats,)
        )


def _m5_check_configs_match(acceptance, audit_standard, m5_arms):
    m5_cloud_cfg = dict(m5_arms[M5_CLOUD_ARM])
    m5_local_cfg = dict(m5_arms[M5_LOCAL_ARM])
    for m5_key in M5_ARM_CONFIG_KEYS:
        if m5_cloud_cfg.get(m5_key) != m5_local_cfg.get(m5_key):
            raise ValueError(
                "m5_acceptance_mismatch: arms disagree on %s" % (m5_key,)
            )
    if m5_cloud_cfg.get("m5_acceptance") != acceptance:
        raise ValueError(
            "m5_acceptance_mismatch: arm acceptance does not match "
            "top-level acceptance"
        )
    if m5_cloud_cfg.get("m5_audit_standard") != audit_standard:
        raise ValueError(
            "m5_acceptance_mismatch: arm audit standard does not match "
            "top-level audit standard"
        )
    return m5_cloud_cfg, m5_local_cfg


def run_comparison(task_class, acceptance, audit_standard, settings, repeats):
    """Compare cloud-only vs local-assisted arms with summed leg measures."""
    _m5_check_repeats(repeats)
    m5_legs = settings["m5_legs"]
    m5_cloud_cfg, m5_local_cfg = _m5_check_configs_match(
        acceptance, audit_standard, settings["m5_arms"]
    )
    m5_cloud_legs = m5_legs[M5_CLOUD_ARM]
    m5_local_legs = m5_legs[M5_LOCAL_ARM]

    m5_cloud_tokens = 0
    m5_cloud_cost = 0.0
    m5_cloud_quality = 0.0
    m5_start = time.perf_counter()
    for _ in range(repeats):
        m5_generated = m5_cloud_legs["m5_cloud"].m5_cloud_generate(task_class)
        m5_audited = m5_cloud_legs["m5_audit"].m5_audit(m5_generated)
        m5_cloud_tokens += int(m5_generated["m5_tokens"])
        m5_cloud_cost += float(m5_generated["m5_cost"])
        m5_cloud_quality += float(m5_audited["m5_score"])
    m5_cloud_time = time.perf_counter() - m5_start
    if m5_cloud_time <= 0:
        m5_cloud_time = 1e-9

    m5_local_tokens = 0
    m5_local_cost = 0.0
    m5_local_quality = 0.0
    m5_start = time.perf_counter()
    for _ in range(repeats):
        m5_draft = m5_local_legs["m5_local"].m5_local_draft(task_class)
        m5_verified = m5_local_legs["m5_router"].m5_cloud_verify(m5_draft)
        m5_audited = m5_local_legs["m5_audit"].m5_audit(m5_verified)
        m5_local_tokens += int(m5_draft["m5_tokens"]) + int(
            m5_verified["m5_tokens"]
        )
        m5_local_cost += float(m5_draft["m5_cost"]) + float(
            m5_verified["m5_cost"]
        )
        m5_local_quality += float(m5_audited["m5_score"])
    m5_local_time = time.perf_counter() - m5_start
    if m5_local_time <= 0:
        m5_local_time = 1e-9

    m5_tokens = {M5_CLOUD_ARM: m5_cloud_tokens, M5_LOCAL_ARM: m5_local_tokens}
    m5_cost = {M5_CLOUD_ARM: m5_cloud_cost, M5_LOCAL_ARM: m5_local_cost}
    m5_time = {M5_CLOUD_ARM: m5_cloud_time, M5_LOCAL_ARM: m5_local_time}
    m5_quality = {
        M5_CLOUD_ARM: m5_cloud_quality,
        M5_LOCAL_ARM: m5_local_quality,
    }
    m5_deltas = {
        "tokens": m5_local_tokens - m5_cloud_tokens,
        "cost": m5_local_cost - m5_cloud_cost,
        "time": m5_local_time - m5_cloud_time,
        "quality": m5_local_quality - m5_cloud_quality,
    }
    m5_evidence_refs = [
        "m5_evidence:%s:repeat-%d" % (m5_arm, m5_i)
        for m5_arm in (M5_CLOUD_ARM, M5_LOCAL_ARM)
        for m5_i in range(repeats)
    ]
    return ComparisonReport(
        tokens=m5_tokens,
        cost=m5_cost,
        time=m5_time,
        quality=m5_quality,
        deltas=m5_deltas,
        arm_configs={M5_CLOUD_ARM: m5_cloud_cfg, M5_LOCAL_ARM: m5_local_cfg},
        evidence_refs=m5_evidence_refs,
        repeats=repeats,
    )
