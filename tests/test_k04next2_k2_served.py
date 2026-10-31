"""K04NEXT2 K2 (CODER-2 Osprey) served tests: in-lane slices of
[M-R-ANY-API] and [HD-PROVIDERS] served end to end, no network.

Served = a real adapter invocation over an injected transport
(repo-wide FakeTransport pattern, loopback TEST data only) settled
through the real BudgetGate ledger, plus the real facades
bind/resolve/probe/disconnect path. stdlib + pytest only; id-only
SecretRefs; the BudgetGate runs in memory (no store dir, no files).

Row-definition sources (quoted, read-only search mode:regex):
- tests/k04_lane_a/test_registry.py:115 [M-R-ANY-API]: generic
  OpenAI-compatible preset takes a caller base_url.
- tests/k04_lane_a/test_registry.py:130 [M-R-ANY-API]: presets never
  bake in a model; ref is mandatory.
- tests/k04_lane_a/test_registry.py:91,100 [HD-PROVIDERS]: presets
  never self-register: nothing configured, none default. The registry
  module itself sits outside this lane's globs; this file proves the
  in-lane slice: the adapter layer binds nothing on import and the
  budget ledger counts the served usage.
- M-D-D26 / M-D-D28: no in-tree definition found workspace-wide
  (search mode:regex `M-D-D26|M-D-D28` over tests/ plus src/ matched no
  files); marked NOT-DONE waits-for-definition in RETURN_K2.md.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from decimal import Decimal

import pytest

from agent_si.budget.gate import BudgetGate
from agent_si.providers.adapters import facades as facades_mod
from agent_si.providers.adapters import legs as legs_mod
from agent_si.providers.adapters.base import make_secret_ref


@pytest.fixture(autouse=True)
def _clean_lane_state():
    facades_mod.clear_provider_bindings()
    facades_mod.clear_adapter_transports()
    yield
    facades_mod.clear_provider_bindings()
    facades_mod.clear_adapter_transports()


def _secret(provider_id="openai_compatible"):
    return make_secret_ref(
        secret_id="k2-served-secret-1",
        provider_id=provider_id,
        type="api_key",
        scope="provider",
        source="secret_store",
    )


class _FakeTransport:
    def __init__(self):
        self.requests = []

    def __call__(self, request):
        self.requests.append(dict(request))
        return {
            "output_text": "k2 served output",
            "finish": "stop",
            "usage": {"input_tokens": 6, "output_tokens": 3},
            "raw": {"id": "k2-fake"},
            "raw_safe": True,
        }


def _gate():
    gate = BudgetGate()
    gate.configure_project(
        project_id="k2", currency="USD", budget_limit="10.00",
        soft_limit="7.00", hard_limit="10.00")
    return gate


# [M-R-ANY-API]-part + budget slice: caller base_url served, real usage
# settled through the real ledger.
def test_k2_any_api_served_and_settled():
    gate = _gate()
    outcome = gate.compare_and_reserve(
        {"project_id": "k2", "task_id": "t-k2", "run_id": "r-k2",
         "reservation_id": "res-k2-1", "estimated_amount": "0.010",
         "reserved_at": "2026-10-31T00:00:00Z",
         "expires_at": "2026-11-01T00:00:00Z",
         "provider_request_ref": "k2-req-1",
         "provider_id": "openai_compatible"})
    assert outcome.ok
    transport = _FakeTransport()
    facades_mod.bind_provider(
        "openai_compatible", _secret(), transport,
        "https://caller.example/v1")
    adapter = legs_mod.build_any_api_adapter(
        "K2-Served-Model", _secret(), "https://caller.example/v1",
        transport)
    response = adapter.invoke([{"role": "user", "content": "hi"}])
    assert response.mock is False
    assert response.model == "K2-Served-Model"
    assert response.usage["input_tokens"] == 6
    assert transport.requests[0]["base_url"] == "https://caller.example/v1"
    settled = gate.settle(
        {"reservation_id": "res-k2-1",
         "provider_request_ref": "k2-req-1",
         "source": "k2-served",
         "settled_at": "2026-10-31T00:01:00Z",
         "actual_amount": "0.004",
         "provider_usage_evidence_ref": "usage:openai_compatible/r-k2"})
    assert settled.status == "SETTLED"
    assert settled.actual_amount == "0.004"
    state = gate.get_state("k2")
    assert Decimal(state.spent) == Decimal("0.004")
    assert Decimal(state.reserved) == 0


# [HD-PROVIDERS]-part + [M-R-ANY-API]-part: nothing default on import;
# explicit bind serves resolve + usage probe, then fail closed.
def test_k2_providers_served_nothing_default_then_bound():
    assert facades_mod.bound_provider_ids() == []
    catalog = legs_mod.catalog_providers()
    assert [entry["provider_id"] for entry in catalog] == list(
        legs_mod.LEG_IDS)
    assert facades_mod.bound_provider_ids() == []
    facades_mod.bind_provider(
        "openai_compatible", _secret(), _FakeTransport(),
        "https://caller.example/v1")
    assert facades_mod.bound_provider_ids() == [
        {"provider_id": "openai_compatible", "instance_id": "default"}]
    resolved = facades_mod.resolve_model(
        "openai_compatible", "K2-Served-Model")
    assert resolved["provider_id"] == "openai_compatible"
    assert resolved["model_id"] == "K2-Served-Model"
    assert resolved["fields"]["endpoint"] == "https://caller.example/v1"
    usage = facades_mod.probe_usage(
        "openai_compatible", "openai_compatible", False)
    assert usage["provider_id"] == "openai_compatible"
    assert usage["state"] in ("VERIFIED", "PARTIAL", "UNSUPPORTED",
                              "UNKNOWN")
    evidence = facades_mod.disconnect_provider("openai_compatible")
    assert evidence["removed"] is True
    assert facades_mod.bound_provider_ids() == []
    with pytest.raises(ValueError):
        facades_mod.resolve_model("openai_compatible", "K2-Served-Model")


# Negative probes by design: unbound providers and empty pools fail
# closed instead of serving placeholder data.
def test_k2_unbound_and_empty_pool_rejected_by_design():
    with pytest.raises(ValueError):
        facades_mod.resolve_model("never-bound-k2", "m")
    with pytest.raises(ValueError):
        facades_mod.probe_usage("never-bound-k2", "never-bound-k2",
                                False)
    gate = _gate()
    with pytest.raises(ValueError):
        gate.compare_and_reserve(
            {"project_id": "k2", "task_id": "", "run_id": "r-x",
             "estimated_amount": "1.00"})
