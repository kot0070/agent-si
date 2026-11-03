"""FXFACTS F1 RED: shipped price for the preset contributor on fresh seed.

Fresh install binds SEED_CATALOG (all UNKNOWN) so the first run charges
UNAVAILABLE for meta/muse-spark-1.3-contributor although the shipped
catalog prices it at 0.10/0.20 per 1M. Expected: the seed row carries the
shipped sourced price, so a fake-usage charge on a fresh store is numeric.
"""
import copy
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_WS = os.path.dirname(_HERE)
for _p in (_WS, os.path.join(_WS, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from agent_si.model_kb import kb as _kb
from agent_si.runtime import manager as _manager


def _fresh_seed():
    previous = _kb._BOUND_CATALOG
    _kb._BOUND_CATALOG = None
    return previous


def test_fresh_seed_prices_preset_contributor():
    previous = _fresh_seed()
    try:
        inp, outp = _manager._kb_price_for_manager(
            "meta", "muse-spark-1.3-contributor")
        assert (inp, outp) == (0.1, 0.2), (inp, outp)
    finally:
        _kb._BOUND_CATALOG = previous


def test_fresh_seed_charge_is_numeric_not_unavailable():
    previous = _fresh_seed()
    old_gate = _manager._BUDGET_GATE
    charged = {}

    class _State:
        hard_limit = "5"
        spent = "0"
        reserved = "0"

    class _Gate:
        def get_state(self, pid):
            return _State()

        def compare_and_reserve(self, payload):
            charged["reserved"] = payload["estimated_amount"]

        def settle(self, payload):
            charged["settled"] = payload["actual_amount"]

    _manager._BUDGET_GATE = _Gate()
    try:
        cost = _manager._charge_budget_gate(
            "p-fxfacts", "meta", "muse-spark-1.3-contributor",
            {"input_tokens": 769, "output_tokens": 4381}, "run-fx1")
        assert cost not in (None, "UNAVAILABLE"), cost
        assert cost == "0.000953", cost
    finally:
        _manager._BUDGET_GATE = old_gate
        _kb._BOUND_CATALOG = previous


def test_unknown_model_stays_unknown_on_fresh_seed():
    previous = _fresh_seed()
    try:
        assert _manager._kb_price_for_manager(
            "ghost", "ghost-model") == (None, None)
    finally:
        _kb._BOUND_CATALOG = previous
