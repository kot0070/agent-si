"""K04NEXT3 C2 served proofs: adapters/budget-side seams.

Rows: R-356, R-357, R-369, R-370, M-P1-23 (adapters/budget-side seams only).
Every claim below drives real product code in src/agent_si/adapters and
src/agent_si/budget. The only injected doubles sit at the network boundary
(transport callables returning wire-shaped replies) and are marked FAKE-OF
per the repo-wide FakeTransport pattern; nothing is doubled inside the
product path. Row definitions: kit/BUILD_PLAN.md coverage table.
"""
import copy
import inspect
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import pytest

from agent_si.adapters import base as _base
from agent_si.adapters import legs as _legs
from agent_si.budget import cheapest as _cheapest
from agent_si.budget import choices as _choices
from agent_si.budget import kb_update as _kb_update
from agent_si.budget import telemetry as _telemetry
from agent_si.budget.gate import BudgetGate
from agent_si.model_kb import kb as _kb
from agent_si.model_kb import loader as _loader

DAY = "2026-10-30T00:00:00Z"
PROVIDER = "c2-shore"
CHEAP = "c2-cheap"
SPENDY = "c2-spendy"


def _secret(provider_id):
    return {"secret_id": "c2-%s-key" % provider_id,
            "provider_id": provider_id, "type": "api_key",
            "scope": "provider", "source": "secret_store"}


def _priced_row(provider, model, price_in, price_out):
    return _kb.make_model_row(provider, model, fields={
        "modalities": _kb.sourced("text", "c2-test", DAY),
        "currency": _kb.sourced("USD", "c2-test", DAY),
        "price_effective_at": _kb.sourced(DAY, "c2-test", DAY),
        "input_token_price": {"value": price_in, "source": "c2-test",
                              "retrieved_at": DAY},
        "output_token_price": {"value": price_out, "source": "c2-test",
                               "retrieved_at": DAY},
    })


def _catalog():
    return _kb.make_catalog(
        [_priced_row(PROVIDER, CHEAP, 0.000002, 0.000004),
         _priced_row(PROVIDER, SPENDY, 0.000005, 0.000015)],
        kb_version=3, updated_at=DAY)


# FAKE-OF: network boundary (wire-shaped reply for the served invoke path).
def _wire_reply(request):
    assert request["provider_id"] in ("c2-shore", "c2-pier", "c2-script")
    assert request["model"]
    assert request["messages"]
    return {"output_text": "served-%s" % request["model"],
            "finish": "stop",
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "raw": {"id": "c2-wire"},
            "raw_safe": True}


# FAKE-OF: network boundary for the function-backed leg.
def _backend_call(request):
    return {"output_text": "served-backend-%s" % request["model"],
            "finish": "stop",
            "usage": {"input_tokens": 4, "output_tokens": 2}}


@pytest.fixture(autouse=True)
def _clean_lane_state():
    _legs.clear_legs()
    _legs.register_leg("c2-shore", openai_compat=True,
                       chat_path="/chat/completions",
                       route_params={"stream": False},
                       endpoint_hint="http://localhost:9/v1")
    _legs.register_leg("c2-pier", openai_compat=True,
                       chat_path="/v1/chat",
                       route_params={"stream": False},
                       endpoint_hint="http://localhost:8/v1")
    _legs.register_leg("c2-script", openai_compat=False,
                       route_params={"tool": "run"},
                       endpoint_hint="in-process")
    yield
    _legs.clear_legs()


# [R-356]-served: no built-in vendor or model default on the adapter seam.
def test_c2_r356_no_builtin_vendor_or_model_default():
    params = inspect.signature(_legs.build_leg).parameters
    assert params["provider_id"].default is inspect.Parameter.empty
    assert params["model"].default is inspect.Parameter.empty
    base_params = inspect.signature(_base.GenericAdapter.__init__).parameters
    assert base_params["provider_id"].default is inspect.Parameter.empty
    assert base_params["model"].default is inspect.Parameter.empty
    leaked = [name for name in dir(_legs)
              if "DEFAULT" in name.upper() and "MODEL" in name.upper()]
    leaked += [name for name in dir(_legs)
               if "DEFAULT" in name.upper() and "PROVIDER" in name.upper()]
    leaked += [name for name in dir(_base)
               if "DEFAULT" in name.upper() and "MODEL" in name.upper()]
    assert leaked == [], leaked
    with pytest.raises(TypeError):
        _legs.build_leg(PROVIDER)
    with pytest.raises(Exception):
        _legs.build_leg("", CHEAP, _secret(PROVIDER), transport=_wire_reply)
    with pytest.raises(Exception) as excinfo:
        _legs.build_leg("no-such-provider", CHEAP, _secret("no-such-provider"),
                        transport=_wire_reply)
    assert "no-such-provider" in str(excinfo.value)


# [R-357]-served: every model choice recorded with its reason.
def test_c2_r357_choice_recorded_with_reason():
    catalog = _catalog()
    out = _cheapest.select_cheapest_optimal(
        catalog,
        [{"provider_id": PROVIDER, "model_id": CHEAP},
         {"provider_id": PROVIDER, "model_id": SPENDY}],
        {"input_tokens": 1000, "output_tokens": 500},
        connected_provider_ids=[PROVIDER], created_at=DAY)
    assert out["pick"] is not None, out
    assert out["reason"], out
    log = _telemetry.TelemetryEventLog()
    event = _choices.record_model_choice(
        log, event_id="c2-choice-1", project_id="p1", timestamp=DAY,
        task_id="t1", run_id="r1", role="worker",
        provider=out["pick"]["provider_id"], model=out["pick"]["model_id"],
        reason=out["reason"], usage_ref=out["usage_ref"],
        pricing_snapshot_id=out["pick"]["pricing_snapshot_id"])
    stored = log.get("c2-choice-1")
    assert stored["reason"] == out["reason"], stored
    assert stored["provider"] == PROVIDER, stored
    assert stored["model"] == CHEAP, stored
    assert stored["event_type"] == "routing_decided", stored
    assert event == stored
    plain = _choices.choice_summary_plain(stored)
    assert PROVIDER in plain and CHEAP in plain and out["reason"] in plain
    with pytest.raises(ValueError):
        _choices.record_model_choice(
            log, event_id="c2-choice-2", project_id="p1", timestamp=DAY,
            task_id="t1", run_id="r1", role="worker",
            provider=PROVIDER, model=CHEAP, reason="")


# [R-369]-served: single-provider mode works fully end to end.
def test_c2_r369_single_provider_full_loop_served(tmp_path):
    solo = "c2-shore"
    descriptors = _legs.legs_for_provider(solo)
    assert len(descriptors) == 1, descriptors
    replies = []
    for descriptor in descriptors:
        adapter = _legs.build_leg(
            descriptor["provider_id"], CHEAP, _secret(solo),
            transport=_wire_reply)
        response = adapter.invoke([{"role": "user", "content": "ping"}])
        record = response.to_record()
        replies.append(record)
        assert record["provider_id"] == solo, record
        assert record["model"] == CHEAP, record
        assert record["mock"] is False, record
        assert record["error_ref"] is None, record
    assert replies, "single-provider mode must serve at least one leg"
    catalog = _catalog()
    out = _cheapest.select_cheapest_optimal(
        catalog, [{"provider_id": PROVIDER, "model_id": CHEAP}],
        {"input_tokens": 1000, "output_tokens": 500},
        connected_provider_ids=[PROVIDER], created_at=DAY)
    gate = BudgetGate(store_dir=str(tmp_path / "ledger"))
    gate.configure_project(project_id="p1", currency="USD",
                           budget_limit=out["pick"]["amount"],
                           soft_limit=out["pick"]["amount"],
                           hard_limit=out["pick"]["amount"],
                           provider_spend_caps={PROVIDER: "1.00"})
    reserved = gate.compare_and_reserve(
        {"project_id": "p1", "task_id": "t1", "run_id": "r1",
         "reservation_id": "c2-res-solo",
         "estimated_amount": out["pick"]["amount"],
         "reserved_at": DAY, "expires_at": "2026-10-31T00:00:00Z",
         "provider_id": PROVIDER})
    assert reserved.ok, reserved
    settled = gate.settle(
        {"reservation_id": "c2-res-solo", "source": "provider-receipt",
         "settled_at": DAY, "actual_amount": out["pick"]["amount"],
         "provider_usage_evidence_ref": out["usage_ref"]})
    assert settled.status == "SETTLED", settled
    state = gate.get_state("p1")
    assert state.spent == out["pick"]["amount"], state.to_dict()
    assert gate.provider_committed("p1", PROVIDER) == \
        out["pick"]["amount"], state.to_dict()


# [R-370]-served: per-field source and date; updater applies only by user.
def test_c2_r370_provenance_and_user_applied_proposal():
    catalog = _catalog()
    provenance = _kb_update.field_provenance(catalog, PROVIDER, CHEAP)
    assert provenance["kb_status"] == _loader.IN_BASE, provenance
    price_field = provenance["fields"]["input_token_price"]
    assert price_field["source"] == "c2-test", provenance
    assert price_field["retrieved_at"] == DAY, provenance
    for name in ("input_token_price", "output_token_price", "currency",
                 "price_effective_at", "modalities"):
        assert name not in provenance["unsourced"], (name, provenance)
    for name in provenance["unsourced"]:
        assert provenance["fields"][name]["source"] == "UNKNOWN", name
        assert provenance["fields"][name]["retrieved_at"] == "UNKNOWN", name
    seed = _kb.make_catalog([_kb.make_model_row(PROVIDER, "c2-seed")],
                            kb_version=1, updated_at=DAY)
    seed_provenance = _kb_update.field_provenance(
        seed, PROVIDER, "c2-seed")
    assert seed_provenance["kb_status"] == _loader.IN_BASE, seed_provenance
    assert seed_provenance["unsourced"], seed_provenance
    for name in seed_provenance["unsourced"]:
        assert seed_provenance["fields"][name]["source"] == "UNKNOWN", name
    proposal = {"proposal_ref": "c2-prop-1",
                "changes": [{"provider_id": PROVIDER, "model_id": CHEAP,
                             "field": "input_token_price", "new": 0.000001,
                             "source": "c2-refresh",
                             "retrieved_at": DAY}]}
    with pytest.raises(ValueError):
        _kb_update.apply_proposal(catalog, proposal, approved_by="",
                                  applied_at=DAY)
    before = copy.deepcopy(catalog)
    applied = _kb_update.apply_proposal(catalog, proposal,
                                        approved_by="user-click",
                                        applied_at=DAY)
    assert catalog == before, "apply must never mutate the input catalog"
    assert applied["version"]["kb_version"] == 4, applied["version"]
    assert applied["version"]["change_log"], applied["version"]
    entry = applied["version"]["change_log"][-1]
    assert entry["approved_by"] == "user-click", entry
    assert entry["proposal_ref"] == "c2-prop-1", entry
    changed = [row for row in applied["models"]
               if row["model_id"] == CHEAP][0]
    assert changed["fields"]["input_token_price"]["value"] == 0.000001
    assert changed["fields"]["input_token_price"]["source"] == "c2-refresh"


# [M-P1-23]-served: generic adapter plus one provider-specific leg each.
def test_c2_m_p1_23_generic_adapter_per_provider_legs():
    seen = []
    for descriptor in _legs.catalog_legs():
        provider_id = descriptor["provider_id"]
        model = "Served-Verbatim-%s" % provider_id
        if descriptor["openai_compat"]:
            adapter = _legs.build_leg(
                provider_id, model, _secret(provider_id),
                transport=_wire_reply)
        else:
            adapter = _legs.build_leg(
                provider_id, model, _secret(provider_id),
                backend_call=_backend_call)
        response = adapter.invoke([{"role": "user", "content": "ping"}])
        record = response.to_record()
        assert record["provider_id"] == provider_id, record
        assert record["model"] == model, record
        assert record["mock"] is False, record
        assert record["error_ref"] is None, record
        described = _legs.describe_leg(adapter)
        assert described["provider_id"] == provider_id, described
        assert described["model"] == model, described
        assert described["openai_compat"] is descriptor["openai_compat"]
        seen.append(provider_id)
    assert sorted(seen) == ["c2-pier", "c2-script", "c2-shore"], seen
