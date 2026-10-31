# K04CONT1 RED-first served tests (ARCH-441 / ARCH-726 / MVP_ACCEPT-168).
# Served = the served dispatch tables (pools_routes._DISPATCH), the same
# convention as test_k04_iface_contract.py test_w05 (served POST
# /api/v1/routing/decide via _DISPATCH). No network, loopback TEST data
# only; the injected L3 runner is a fake ONLY at the network boundary
# (sdk_call refs, never values), the repo-wide FakeTransport pattern.
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend import pools_routes as PR
from agent_si.budget.gate import BudgetGate
from agent_si.routing import kb_port as KB
from agent_si.routing import roles as RL
from agent_si.routing import types as T
from agent_si.routing.store import RoutingStore


class _FakeKb(KB.KbReader):
    # FAKE-OF: KB.KbReader (in-memory facts dict for served path tests)
    def __init__(self, facts):
        self._facts = dict(facts)

    def facts(self, provider, model):
        return self._facts.get((provider, model))

    def models(self, provider=None):
        return [f for (p, _m), f in self._facts.items()
                if provider is None or p == provider]


def _facts(provider, model, *, state="MEASURED", quality=0.9,
           price_in=0.01, price_out=0.03):
    return KB.KbModelFacts(
        provider=provider, model=model,
        task_fit={"coding": quality, "text": quality,
                  "general": quality},
        strict_pass_rate=quality, tolerant_pass_rate=quality,
        sample_count=50, confidence=0.9, freshness="CURRENT",
        input_price=price_in, output_price=price_out,
        modalities=("text",), assessed_risk="LOW",
        fields_state=state, verified_static=False,
        source="k04fresh1-test", measured_at="2026-10-29T00:00:00+00:00",
        latency_ms=400.0)


def _ctx(tmp_path, kb, models, budget_gate=None):
    return PR.RoutingCtx(
        store=RoutingStore(str(tmp_path)),
        role_table=RL.RoleTable(),
        kb=kb,
        provider_health={"pa": T.ProviderHealth(provider="pa",
                                                status="ONLINE")},
        model_health={(m[0], m[1]): T.ModelHealth(
            provider=m[0], model=m[1], status="READY") for m in models},
        provider_capabilities={"pa": ("text",)},
        resource_state={"eligible": True, "ref": "rs-f1"},
        budget_state=(budget_gate if budget_gate is not None
                      else {"eligible": True, "ref": "bs-f1"}),
        session_token="ui-test-f1")


def _gate(tmp_path):
    gate = BudgetGate(store_dir=str(tmp_path / "ledger"))
    gate.configure_project(
        project_id="p1", currency="USD", budget_limit="10.00",
        soft_limit="7.00", hard_limit="10.00")
    return gate


def _reserve(gate):
    outcome = gate.compare_and_reserve(
        {"project_id": "p1", "task_id": "t1", "run_id": "r1",
         "reservation_id": "res-f1", "estimated_amount": "3.00",
         "reserved_at": "2026-10-26T00:00:00Z",
         "expires_at": "2026-10-27T00:00:00Z"})
    assert outcome.ok
    return outcome.reservation


# ARCH-441: failed gates compensate idempotently to RELEASED with a
# persisted compensation_ref (BUILD_PLAN.md:1593).
def test_k04fresh1_compensation_served(tmp_path):
    gate = _gate(tmp_path)
    _reserve(gate)
    compensate = dict(PR._DISPATCH)[("post", "/api/v1/budget/compensations")]
    ctx = _ctx(tmp_path, _FakeKb({}), [], budget_gate=gate)
    body = {"reservation_id": "res-f1",
            "reason": "gate failed: provider outage",
            "compensation_ref": "cmp-f1"}
    status, payload = compensate(ctx, {}, body)
    assert status == 200, payload
    assert payload["compensation_ref"] == "cmp-f1", payload
    assert payload["status"] == "RELEASED", payload
    # Idempotent repeat: the same ref returns the same record, the
    # reserved amount is released exactly once.
    status2, payload2 = compensate(ctx, {}, dict(body))
    assert status2 == 200, payload2
    assert payload2["compensation_ref"] == "cmp-f1", payload2
    assert gate.get_state("p1").reserved == "0.00"
    # A different ref for the same released reservation conflicts.
    status3, payload3 = compensate(
        ctx, {}, dict(body, compensation_ref="cmp-other"))
    assert status3 == 409, payload3
    # Persisted: a fresh gate over the same dir sees RELEASED + ref.
    gate2 = BudgetGate(store_dir=str(tmp_path / "ledger"))
    assert gate2.get_reservation("res-f1").status == "RELEASED"
    assert gate2.get_compensation("res-f1").compensation_ref == "cmp-f1"
    # Token-less USER writes are refused without touching state.
    ctx_open = _ctx(tmp_path, _FakeKb({}), [], budget_gate=gate)
    ctx_open.session_token = None
    denied, denied_payload = compensate(ctx_open, {}, dict(body))
    assert denied == 401, denied_payload


# ARCH-726: high-risk reasoning plus final verification run only on
# measured capable candidates (BUILD_PLAN.md:1605).
def test_k04fresh1_capable_gate_served(tmp_path):
    kb = _FakeKb({
        ("pa", "pa/m1"): _facts("pa", "pa/m1", state="MEASURED",
                                quality=0.9),
        ("pa", "pa/cheap"): _facts("pa", "pa/cheap", state="PROXY",
                                   quality=0.5, price_in=None,
                                   price_out=None),
    })
    decide = dict(PR._DISPATCH)[("post", "/api/v1/routing/decide")]
    models = [("pa", "pa/m1"), ("pa", "pa/cheap")]
    ctx = _ctx(tmp_path, kb, models)

    def body_for(model):
        return {"project_id": "p1", "task_id": "t1", "run_id": "r1",
                "role": "worker", "task_class": "coding",
                "task_risk": "HIGH",
                "candidates": [{"provider": "pa", "model": model}]}

    # Unmeasured cheap candidate: high-risk reasoning refuses it. The
    # served BLOCKED reason names the CAPABLE_GATE refusal.
    status, payload = decide(ctx, {}, body_for("pa/cheap"))
    assert status == 200, payload
    assert payload["status"] == "BLOCKED", payload
    assert "CAPABLE_GATE" in payload["reason"], payload
    triple = ctx.store.why_replay(payload["decision_id"])
    assert triple is not None, payload
    # Measured capable candidate: routed, final verification required.
    status2, payload2 = decide(ctx, {}, body_for("pa/m1"))
    assert status2 == 200, payload2
    assert payload2["status"] == "ROUTED", payload2
    assert payload2["selected_model"] == "pa/m1", payload2
    triple2 = ctx.store.why_replay(payload2["decision_id"])
    assert triple2 is not None, payload2
    decision2, _a2, _s2 = triple2
    assert decision2.required_verification == "FINAL_VERIFICATION", \
        decision2


# MVP_ACCEPT-168: L3 independent audit runs through a separate provider
# path with its own key ref (BUILD_PLAN.md:1684).
def test_k04fresh1_l3_audit_served(tmp_path):
    post_l3 = dict(PR._DISPATCH)[("post", "/api/v1/routing/l3-audit")]
    ctx = _ctx(tmp_path, _FakeKb({}), [])

    def body_for(provider, model="pb/audit"):
        return {"project_id": "p1", "task_id": "t1", "run_id": "r1",
                "decision_id": "rd-1",
                "selected_provider": "pa", "selected_model": "pa/m1",
                "l3_provider": provider, "l3_model": model,
                "key_ref": {"secret_id": "s-l3", "provider_id": provider,
                            "type": "api_key", "scope": "audit",
                            "source": "os_store",
                            "created_at": "2026-10-26T00:00:00Z",
                            "last_rotated_at": "2026-10-26T00:00:00Z"}}

    # The L3 path must differ from the decided provider.
    status, payload = post_l3(ctx, {}, body_for("pa", "pa/audit"))
    assert status == 400, payload
    assert payload["code"] == "L3_PROVIDER_MUST_DIFFER", payload
    # The L3 path needs its own key ref (records, never inline values).
    no_key = body_for("pb")
    del no_key["key_ref"]
    status2, payload2 = post_l3(ctx, {}, no_key)
    assert status2 == 400, payload2
    assert payload2["code"] == "L3_KEY_REF_REQUIRED", payload2
    # Success through the served entry with the runner injected ONLY at
    # the network boundary (sdk_call refs, never values).
    seen = []

    def fake_sdk_call(call):
        seen.append(call)
        return {"ok": True, "output_text": "l3-audit-pass"}

    ctx.l3_runner = fake_sdk_call
    status3, payload3 = post_l3(ctx, {}, body_for("pb"))
    assert status3 == 200, payload3
    assert payload3["provider"] == "pb", payload3
    assert payload3["model"] == "pb/audit", payload3
    assert payload3["output_ref"] == "artifact:run/r1/output", payload3
    assert seen and seen[0]["secret_ids"] == ("s-l3",), seen
    assert seen[0]["provider"] == "pb", seen
    assert "s-l3" not in str({k: v for k, v in seen[0].items()
                              if k != "secret_ids"}), seen
