# K04NEXT2 K1 lane (CODER-1 Harrier) — pools-side served row proofs.
# M-P1-25: replay the committed recorded loopback E2E through the real pool
# path (recorded artifact + replay, no live network in this test).
# M-P4-149: pool members carry id-only refs, never inline key material
# (in-repo fakes only; the real store goes through the provisioning
# gateway). M-D-D14 / M-D-D21 have no findable definition in the workspace
# (search mode:regex `M-D-D14|M-D-D21` over the whole tree matches nothing)
# and are NOT-DONE waits-for-definition: no test invents them.
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import pytest

from agent_si.pools import gateway as GW
from agent_si.pools import replay as RP
from agent_si.pools import summary as SM
from agent_si.providers.registry.provider_api import LEFTOVER_RULES
from agent_si.routing import kb_port as KB
from agent_si.routing import pools as P
from agent_si.routing import router as R
from agent_si.routing import store as ST
from agent_si.routing import types as T

_RECORD_PATH = os.path.abspath(os.path.join(
    _HERE, "k04next2_m_p1_25_record.json"))


class FakeKb(KB.KbReader):
    # FAKE-OF: agent_si.routing.kb_port.KbReader (in-memory facts only)
    def __init__(self, facts):
        self._facts = dict(facts)

    def facts(self, provider, model):
        return self._facts.get((provider, model))

    def models(self, provider=None):
        return [f for (p, _m), f in self._facts.items()
                if provider is None or p == provider]


def _deps(kb, provider, model, tmp_path):
    return R.RoutingDeps(
        kb=kb,
        provider_health={provider: T.ProviderHealth(
            provider=provider, status="ONLINE")},
        model_health={(provider, model): T.ModelHealth(
            provider=provider, model=model, status="READY")},
        provider_capabilities={provider: ("text", "tools", "coding")},
        resource_state={"eligible": True, "ref": "rs-k1"},
        budget_state={"eligible": True, "ref": "bs-k1"},
        store=ST.RoutingStore(str(tmp_path / "data")),
        emitter=None)


def _request(strict_min=1.0):
    return R.RoutingRequest(
        project_id="p1", task_id="t1", run_id="r1", role="worker",
        task_class="coding",
        required_capabilities=("text", "tools"),
        required_modalities=("text",),
        task_risk="LOW",
        routing_policy=T.RoutingPolicy(
            policy_id="rp-k1", version=1,
            created_at="2026-10-29T00:00:00+00:00", hash="h",
            task_class="coding", risk_level="LOW",
            strict_min=strict_min, tolerant_min=0.85, confidence_min=0.7,
            sample_min=20, freshness_requirement="CURRENT",
            local_allowed=True, split_allowed=True, cloud_required=False),
        optimization_policy=T.OptimizationPolicy(
            policy_id="op-k1", version=1,
            created_at="2026-10-29T00:00:00+00:00", hash="h",
            required_quality=0.8, max_risk="HIGH",
            weight_quality=1.0, weight_cost=1.0, weight_latency=1.0,
            weight_cloud_tokens=1.0, local_preference=False,
            deadline=None, budget_limit=None),
        candidates=(), mode="AUTO")


# ------------------------------------------------- M-P1-25 recorded replay


def _record():
    with open(_RECORD_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def test_k1_m_p1_25_recorded_artifact_is_loopback_e2e():
    artifact = _record()
    checked = RP.check_recorded_e2e(artifact)
    assert checked["ok"] is True
    assert checked["row"] == "M-P1-25"
    assert checked["provider_id"] == artifact["provider_id"]
    assert checked["provider_id"] not in ("meta", "openai")
    assert checked["model"] == artifact["model"]
    assert artifact["http"]["status"] == 200


def test_k1_m_p1_25_replay_routes_recorded_model_served(tmp_path):
    artifact = _record()
    binding = RP.recorded_pool_binding(artifact, role="worker",
                                       project_id="p1")
    assert binding.members[0].provider == artifact["provider_id"]
    assert binding.members[0].model == artifact["model"]
    kb = FakeKb({(artifact["provider_id"], artifact["model"]):
                 RP.recorded_kb_facts(artifact)})
    deps = _deps(kb, artifact["provider_id"], artifact["model"], tmp_path)
    # The real local gate holds: a strict-1.0 policy blocks the 0.9-rated
    # recorded loopback (local draft-only without a SPLIT request).
    blocked = P.resolve_pool(binding, _request(strict_min=1.0), deps)
    assert blocked.status == "BLOCKED", blocked.decision.reason
    assert "NO_ELIGIBLE_CANDIDATE" in blocked.decision.reason
    # A matching strict bar serves the recorded pair verbatim.
    out = P.resolve_pool(binding, _request(strict_min=0.9), deps)
    assert out.status == "ROUTED", out.decision.reason
    assert out.decision.selected_model == artifact["model"]
    assert out.decision.selected_provider == artifact["provider_id"]
    view = SM.binding_summary(binding)
    assert view["sentence"], view
    assert view["providers"] == [artifact["provider_id"]], view
    assert view["strategy_label"] == "Fallback order", view


def test_k1_m_p1_25_rejects_meta_openai_and_non_200():
    artifact = _record()
    for bad_provider in ("meta", "openai"):
        tampered = dict(artifact, provider_id=bad_provider)
        try:
            RP.check_recorded_e2e(tampered)
        except ValueError as exc:
            assert "M-P1-25" in str(exc)
        else:
            raise AssertionError(
                "accepted forbidden provider %r" % (bad_provider,))
    tampered = dict(artifact, http=dict(artifact["http"], status=500))
    try:
        RP.check_recorded_e2e(tampered)
    except ValueError as exc:
        assert "M-P1-25" in str(exc)
    else:
        raise AssertionError("accepted non-200 recorded status")


# ------------------------------------------------- M-P4-149 gateway posture


def test_k1_m_p4_149_rule_map_names_gateway():
    assert "M-P4-149" in LEFTOVER_RULES
    assert "gateway" in LEFTOVER_RULES["M-P4-149"]


def test_k1_m_p4_149_member_refs_pass_for_id_only():
    assert GW.check_member_refs(
        {"provider": "pa", "model": "pa/a-1"}) is None
    assert GW.check_member_refs(
        P.PoolMember("pa", "pa/a-1", "primary")) is None
    binding = P.make_binding("worker", "p1", [
        P.PoolMember("pa", "pa/a-1", "primary"),
        P.PoolMember("pb", "pb/b-1", "fallback"),
    ], strategy="FALLBACK_ORDER")
    assert GW.check_binding_refs(binding) == 2


def test_k1_m_p4_149_member_refs_refuse_inline_secret():
    for field in ("api_key", "apikey", "api_secret", "secret_value",
                    "client_secret", "access_token", "password",
                    "authorization", "x-api-key"):
        bad = {"provider": "pa", "model": "pa/a-1", field: "[REDACTED]"}
        try:
            GW.check_member_refs(bad)
        except ValueError as exc:
            assert "M-P4-149" in str(exc), str(exc)
            assert "gateway" in str(exc), str(exc)
        else:
            raise AssertionError("accepted inline field %r" % (field,))
    dirty = P.make_binding("worker", "p1", [
        P.PoolMember("pa", "pa/a-1", "primary"),
    ], strategy="AUTO")
    try:
        GW.check_binding_refs({
            "role": "worker", "project_id": "p1", "strategy": "AUTO",
            "members": [{"provider": "pa", "model": "pa/a-1",
                         "api_key": "[REDACTED]"}]})
    except ValueError as exc:
        assert "M-P4-149" in str(exc)
    else:
        raise AssertionError("dirty dict binding passed the gateway")
    assert dirty is not None
