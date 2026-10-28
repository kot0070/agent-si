"""K04 M412 ARCH-412: real estimated_tokens derivation behaviour tests.

Drives the REAL router entries (frozen select facade + decide_and_record)
with known inputs and asserts the exact expected estimate:
estimated_tokens == (max_tokens or 0) + (token_overhead or 0).
No fakes stand in for the proof: the _BKb/_b_* doubles below are input
plumbing only (same shape as tests/test_k04_iface_contract.py); every
assert inspects REAL router output.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import pytest

from agent_si.routing import types as RT
from agent_si.routing import router as _RTR
from agent_si.routing import kb_port as _KBP


def _b_policy(**kw):
    d = dict(policy_id="rp-412", version=1,
             created_at="2026-01-01T00:00:00+00:00", hash="h",
             task_class="coding", risk_level="LOW",
             strict_min=1.0, tolerant_min=0.85, confidence_min=0.7,
             sample_min=20, freshness_requirement="CURRENT",
             local_allowed=True, split_allowed=True, cloud_required=False)
    d.update(kw)
    return RT.RoutingPolicy(**d)


def _b_opt(**kw):
    d = dict(policy_id="op-412", version=1,
             created_at="2026-01-01T00:00:00+00:00", hash="h",
             required_quality=0.8, max_risk="HIGH",
             weight_quality=1.0, weight_cost=1.0, weight_latency=1.0,
             weight_cloud_tokens=1.0, local_preference=False,
             deadline=None, budget_limit=None, token_overhead=200)
    d.update(kw)
    return RT.OptimizationPolicy(**d)


class _BKb:
    # FAKE-OF: agent_si.routing.kb_port.KbReader (named KB rows for tests).
    # Input plumbing only: every assert below inspects REAL router output.
    def __init__(self, rows):
        self._rows = dict(rows)

    def facts(self, provider, model):
        return self._rows.get((provider, model))

    def models(self, provider=None):
        return [f for (p, _m), f in self._rows.items()
                if provider is None or p == provider]


def _b_facts(provider, model, **kw):
    d = dict(provider=provider, model=model,
             task_fit={"coding": 0.9, "text": 0.9, "general": 0.9},
             strict_pass_rate=0.9, tolerant_pass_rate=0.9,
             sample_count=50, confidence=0.9, freshness="CURRENT",
             input_price=0.01, output_price=0.03,
             modalities=("text",), assessed_risk="LOW",
             fields_state="MEASURED", verified_static=True,
             source="arch412", measured_at="2026-01-01T00:00:00+00:00",
             latency_ms=400.0)
    d.update(kw)
    return _KBP.KbModelFacts(**d)


def _b_select(task_extra=None, views=(), kb_rows=None, overhead=200,
              **ctx_extra):
    task = {"project_id": "p1", "task_id": "t1", "run_id": "r1",
            "role": "worker", "task_class": "coding"}
    task.update(task_extra or {})
    ctx = {
        "task_contracts": {"tc-412": task},
        "routing_policies": {"rp-412": _b_policy()},
        "optimization_policies": {"op-412": _b_opt(token_overhead=overhead)},
        "budget_state": {"eligible": True, "ref": "bs-412"},
        "resource_state": {"eligible": True, "ref": "rs-412"},
        "kb": _BKb(kb_rows or {}),
        "provider_health": {"pa": RT.ProviderHealth(provider="pa",
                                                    status="ONLINE")},
        "model_health": {("pa", "m1"): RT.ModelHealth(provider="pa",
                                                      model="m1",
                                                      status="READY")},
        "provider_capabilities": {"pa": ("text",)},
    }
    ctx.update(ctx_extra)
    # Exact 6-ref facade (no **ctx): bind server scope, mechanical only.
    _RTR.bind_select_scope(ctx)
    try:
        return _RTR.select("tc-412", list(views), "rp-412", "op-412",
                           "bs-412", "rs-412")
    finally:
        _RTR.unbind_select_scope()


def _b_views():
    return [{"provider_id": "pa", "model": "m1",
             "modality_ok": True, "rejected": False}]


def _b_rows():
    return {("pa", "m1"): _b_facts("pa", "m1")}


def test_routed_carries_exact_estimate():
    # Canonical case: max_tokens=1500 + token_overhead=200 -> 1700 exactly.
    outcome = _b_select(task_extra={"max_tokens": 1500},
                        views=_b_views(), kb_rows=_b_rows(), overhead=200)
    assert outcome.status == "ROUTED"
    assert outcome.decision.estimated_tokens == 1700


def test_zero_case_is_zero():
    outcome = _b_select(task_extra={"max_tokens": 0},
                        views=_b_views(), kb_rows=_b_rows(), overhead=0)
    assert outcome.status == "ROUTED"
    assert outcome.decision.estimated_tokens == 0


def test_blocked_carries_exact_estimate():
    # BLOCKED via the real decide_and_record entry (empty candidates).
    request = _RTR.RoutingRequest(
        project_id="p1", task_id="t1", run_id="r1", role="worker",
        task_class="coding", routing_policy=_b_policy(),
        optimization_policy=_b_opt(token_overhead=200),
        candidates=(), max_tokens=1500)
    deps = _RTR.RoutingDeps(
        kb=_BKb({}), provider_health={}, model_health={},
        provider_capabilities={}, resource_state=None, budget_state=None)
    outcome = _RTR.decide_and_record(request, deps)
    assert outcome.status == "BLOCKED"
    assert outcome.decision.estimated_tokens == 1700


def test_negative_max_tokens_raises():
    with pytest.raises(ValueError):
        _b_select(task_extra={"max_tokens": -1},
                  views=_b_views(), kb_rows=_b_rows(), overhead=200)


def test_negative_overhead_raises():
    with pytest.raises(ValueError):
        _b_select(task_extra={"max_tokens": 1500},
                  views=_b_views(), kb_rows=_b_rows(), overhead=-1)
