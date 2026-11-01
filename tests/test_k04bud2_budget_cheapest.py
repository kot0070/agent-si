"""K04NEXT M1 CODER-2: served cheapest-optimal-per-block proofs (R-308/309/310).

Drives the real product path only: real model_kb catalog rows
(kb.make_model_row / kb.make_catalog), real loader choice-point reads,
real telemetry.make_snapshot registry, real CostCalculator. No fakes.
Row evidence: budget.cheapest.select_cheapest_optimal + test name each.
"""
import copy
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.budget import cheapest as BCH
from agent_si.budget.telemetry import (
    CostCalculator,
    make_snapshot,
    register_usage,
)
from agent_si.model_kb import kb as _kb
from agent_si.model_kb import loader as _loader

DAY = "2026-10-30"
PROVIDER = "bch-provider"
CHEAP = "bch-cheap"
SPENDY = "bch-spendy"
GHOST = "bch-ghost-model"


def _priced_row(model, price_in, price_out):
    return _kb.make_model_row(PROVIDER, model, fields={
        "modalities": _kb.sourced("text, tools, coding", "bch-test", DAY),
        "currency": _kb.sourced("USD", "bch-test", DAY),
        "price_effective_at": _kb.sourced(DAY, "bch-test", DAY),
        "input_token_price": {"value": price_in, "source": "bch-test",
                              "retrieved_at": DAY},
        "output_token_price": {"value": price_out, "source": "bch-test",
                               "retrieved_at": DAY},
    })


def _catalog():
    return _kb.make_catalog(
        [_priced_row(CHEAP, 0.000002, 0.000004),
         _priced_row(SPENDY, 0.000005, 0.000015)],
        kb_version=7, updated_at=DAY)


def _entries(*models):
    return [{"provider_id": PROVIDER, "model_id": model}
            for model in models]


BLOCK = {"input_tokens": 1000, "output_tokens": 500}


def test_r308_cheapest_optimal_per_block_from_kb():
    """R-308 via budget.cheapest.select_cheapest_optimal."""
    catalog = _catalog()
    out = BCH.select_cheapest_optimal(
        catalog, _entries(CHEAP, SPENDY), BLOCK,
        connected_provider_ids=[PROVIDER], created_at=DAY)
    assert out["pick"] is not None, out
    assert out["pick"]["model_id"] == CHEAP, out
    assert out["pick"]["kb_status"] == _loader.IN_BASE, out
    # Cost path is CostCalculator only: independent oracle agrees exactly.
    usage_ref = register_usage("bch-oracle-usage-%s" % CHEAP, dict(BLOCK))
    snap = make_snapshot(
        "bch-oracle-snap-%s" % CHEAP, PROVIDER, CHEAP, "USD", DAY,
        "bch-oracle", DAY, input_token_price=0.000002,
        output_token_price=0.000004)
    expected = CostCalculator.calculate(usage_ref, snap.pricing_snapshot_id)
    assert out["pick"]["amount"] == expected.amount, out
    assert out["pick"]["amount"] == "0.004000", out
    assert [r["model_id"] for r in out["ranked"]] == [CHEAP, SPENDY], out


def test_r309_unknown_model_marked_unknown_never_picked():
    """R-309 via budget.cheapest.select_cheapest_optimal."""
    catalog = _catalog()
    out = BCH.select_cheapest_optimal(
        catalog, _entries(CHEAP, GHOST), BLOCK,
        connected_provider_ids=[PROVIDER], created_at=DAY)
    ghost_rows = [r for r in out["excluded"]
                  if r["model_id"] == GHOST]
    assert ghost_rows, out
    assert ghost_rows[0]["kb_status"] == _loader.NOT_IN_BASE, out
    assert ghost_rows[0].get("amount") is None, out
    assert out["pick"] is not None and out["pick"]["model_id"] == CHEAP, out


def test_r309_all_unknown_prices_fail_closed_kb_untouched():
    """R-309/R-310: seed-UNKNOWN catalog blocks, KB never written."""
    catalog = _kb.make_catalog(
        [_kb.make_model_row(PROVIDER, CHEAP)], kb_version=1,
        updated_at=DAY)
    before = copy.deepcopy(catalog)
    out = BCH.select_cheapest_optimal(
        catalog, _entries(CHEAP), BLOCK,
        connected_provider_ids=[PROVIDER], created_at=DAY)
    assert out["pick"] is None, out
    assert "BLOCKED" in out["reason"], out
    assert out["ranked"] == [], out
    assert all(r.get("amount") is None for r in out["excluded"]), out
    assert catalog == before, "budget path wrote the KB"
    priced = [r for r in out["excluded"] if r["model_id"] == CHEAP]
    assert priced and priced[0]["kb_status"] == _loader.IN_BASE, out


def test_r310_marks_consistent_at_every_choice_point():
    """R-310 via budget.cheapest.select_cheapest_optimal."""
    catalog = _catalog()
    entries = _entries(SPENDY, CHEAP, GHOST)
    out = BCH.select_cheapest_optimal(
        catalog, entries, BLOCK,
        connected_provider_ids=[PROVIDER], created_at=DAY)
    rows = list(out["ranked"]) + list(out["excluded"])
    if out["pick"] is not None:
        rows.append(out["pick"])
    assert rows, out
    for row in rows:
        assert row["kb_status"] in (
            _loader.IN_BASE, _loader.NOT_IN_BASE), row
        assert row["kb_status"] == _loader.lookup(
            catalog, row["provider_id"],
            row["model_id"])["kb_status"], row
