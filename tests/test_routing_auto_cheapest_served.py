"""AUTO cheapest-first served proof: 3-provider meta+openai+anthropic.

PART1DRIVE4 F03 (01.11): the AUTO pick took the first catalog row
(gpt-4o) even though the KB priced gpt-4o-mini cheaper. The fix ranks
the seam shortlist cheapest-known-price first, UNKNOWN prices last,
catalog order kept inside ties.

Drives the REAL product entries over the frozen served route
GET /api/v1/routing/auto (explicit `connected` param, the frozen
exact {"manager", "model"} shape) plus one direct pick_auto read of
the why-record (rule + compared prices). No network, no keys.
"""

import os
import sys

from fastapi.testclient import TestClient

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend import routing_auto as _seam  # noqa: E402
from agent_si.backend.app import create_app  # noqa: E402
from agent_si.model_kb import kb as _kb  # noqa: E402

TEST_TOKEN = "routing-cheapest-served-token"

META_MODEL = "muse-spark-1.3-contributor"
OPENAI_MODEL = "gpt-4o"
ANTHROPIC_MODEL = "claude-opus-4-6"

PRICE_SOURCE = "https://example.invalid/pricing"
PRICE_AT = "2026-10-31"


def _priced(in_price, out_price):
    return {
        "input_token_price": _kb.sourced(
            in_price, PRICE_SOURCE, PRICE_AT),
        "output_token_price": _kb.sourced(
            out_price, PRICE_SOURCE, PRICE_AT),
    }


def _test_catalog():
    # Catalog order is deliberately adversarial: the UNKNOWN-priced
    # anthropic row is first, the cheapest known meta row is last.
    rows = [
        _kb.make_model_row("anthropic", ANTHROPIC_MODEL),
        _kb.make_model_row("openai", OPENAI_MODEL,
                           _priced(1.0, 2.0)),
        _kb.make_model_row("meta", META_MODEL,
                           _priced(0.25, 0.5)),
    ]
    return _kb.make_catalog(rows, kb_version=1, updated_at=PRICE_AT,
                            change_log=[], sources=[])


def make_client():
    app = create_app({"testing": True, "ui_session_token": TEST_TOKEN})
    mounted = any(getattr(route, "path", None) == "/api/v1/routing/auto"
                  for route in getattr(app, "routes", []))
    if not mounted:
        _seam.register_routing_auto_routes(app)
    return TestClient(app)


def setup_function(_func):
    _previous = _kb.bound_catalog()
    _func._cheapest_previous = _previous
    _kb.bind_catalog(_test_catalog())


def teardown_function(func):
    _kb.bind_catalog(func._cheapest_previous)


def test_cheapest_known_wins_over_catalog_order():
    """Cheapest KNOWN price wins even when listed last in the catalog."""
    client = make_client()
    resp = client.get("/api/v1/routing/auto",
                      params={"task_type": "coding",
                              "connected": "anthropic,openai,meta"})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"manager": "meta", "model": META_MODEL}


def test_unknown_price_never_above_known():
    """An UNKNOWN-priced row listed first still loses to a known price."""
    client = make_client()
    resp = client.get("/api/v1/routing/auto",
                      params={"task_type": "coding",
                              "connected": "anthropic,meta"})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"manager": "meta", "model": META_MODEL}


def test_why_carries_rule_and_compared_prices():
    """The why-record carries the rule plus the compared per-row prices."""
    pick = _seam.pick_auto(_kb.bound_catalog(),
                           ["anthropic", "openai", "meta"], "coding")
    assert (pick["manager"], pick["model"]) == ("meta", META_MODEL)
    why = pick["why"]
    assert why["rule"] == "cheapest known price first, UNKNOWN prices last"
    compared = {(row["provider"], row["model"]): row["price_in_plus_out"]
                for row in why["compared"]}
    assert compared == {("anthropic", ANTHROPIC_MODEL): None,
                        ("openai", OPENAI_MODEL): 3.0,
                        ("meta", META_MODEL): 0.75}
