"""K09-B STEP2 telemetry tests (owned by coder B).

Proves per-role+agent hits/misses/web-fallbacks with tokens+cost,
web fallback as a counted marker, and savings figures == stored
records exactly. All assertions are delta-based: the telemetry store
is module-global and shared with tests/test_k09b_contract.py.
"""

import os
import sys
from dataclasses import dataclass
from typing import Optional

import pytest

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)

from src.agent_si.kb.savings import savings_report
from src.agent_si.kb.telemetry import (
    KbTelemetryRecord,
    list_records,
    record_hit,
    record_miss,
    record_web_fallback,
)


# FAKE-OF: RECORDS/day1/K04_INTERFACE_STUB_v2.py
@dataclass
class FakeCostLine:
    """Test-local stand-in for the K04 CostLine (amount null = UNAVAILABLE)."""

    amount: Optional[float]
    currency: str
    pricing_snapshot_id: Optional[str]


def _counts(records):
    return {
        "hits": sum(1 for r in records if r.kind == "hit"),
        "misses": sum(1 for r in records if r.kind == "miss"),
        "web_fallbacks": sum(1 for r in records if r.kind == "web_fallback"),
        "tokens": sum(r.tokens for r in records),
        "cost": sum(r.cost for r in records),
    }


def test_per_role_agent_hits_misses_fallbacks_with_tokens_cost():
    before = list_records()
    record_hit("k09b-dev", "k09b-a1", 100, 0.02)
    record_hit("k09b-dev", "k09b-a1", 200, 0.04)
    record_miss("k09b-dev", "k09b-a1", 50, 0.01)
    record_web_fallback("k09b-ops", "k09b-a2", 25, 0.005)
    record_hit("k09b-ops", "k09b-a2", 10, 0.002)
    after = list_records()
    assert len(after) == len(before) + 5
    new = after[len(before):]
    assert all(isinstance(r, KbTelemetryRecord) for r in new)
    assert [(r.role, r.agent, r.tokens, r.cost, r.kind) for r in new] == [
        ("k09b-dev", "k09b-a1", 100, 0.02, "hit"),
        ("k09b-dev", "k09b-a1", 200, 0.04, "hit"),
        ("k09b-dev", "k09b-a1", 50, 0.01, "miss"),
        ("k09b-ops", "k09b-a2", 25, 0.005, "web_fallback"),
        ("k09b-ops", "k09b-a2", 10, 0.002, "hit"),
    ]
    dev_a1 = [r for r in new if r.role == "k09b-dev" and r.agent == "k09b-a1"]
    assert sum(1 for r in dev_a1 if r.kind == "hit") == 2
    assert sum(1 for r in dev_a1 if r.kind == "miss") == 1
    assert sum(1 for r in dev_a1 if r.kind == "web_fallback") == 0
    assert sum(r.tokens for r in dev_a1) == 350
    assert sum(r.cost for r in dev_a1) == pytest.approx(0.07)
    ops_a2 = [r for r in new if r.role == "k09b-ops" and r.agent == "k09b-a2"]
    assert sum(1 for r in ops_a2 if r.kind == "hit") == 1
    assert sum(1 for r in ops_a2 if r.kind == "web_fallback") == 1
    assert sum(r.tokens for r in ops_a2) == 35
    assert sum(r.cost for r in ops_a2) == pytest.approx(0.007)


def test_web_fallback_is_counted_marker():
    before = list_records()
    base = _counts(before)
    record_web_fallback("k09b-web", "k09b-w1", 33, 0.003)
    records = list_records()
    assert (records[-1].role, records[-1].agent) == ("k09b-web", "k09b-w1")
    assert (records[-1].tokens, records[-1].cost) == (33, 0.003)
    assert records[-1].kind == "web_fallback"
    report = savings_report()
    assert report["web_fallbacks"] == base["web_fallbacks"] + 1
    assert report["web_fallbacks"] == sum(1 for r in records if r.kind == "web_fallback")
    assert report["hits"] == base["hits"] + 0
    assert report["misses"] == base["misses"] + 0


def test_savings_figures_equal_stored_records_exactly():
    before = list_records()
    base = _counts(before)
    line = FakeCostLine(amount=0.0125, currency="USD", pricing_snapshot_id="snap-k09b-t")
    record_hit("k09b-keeper", "k09b-price", 80, line.amount)
    record_miss("k09b-keeper", "k09b-price", 40, 0.005)
    record_web_fallback("k09b-keeper", "k09b-price", 20, 0.0025)
    records = list_records()
    assert line.amount in [r.cost for r in records[len(before):]]
    expected = _counts(records)
    report = savings_report()
    assert report == expected
    assert report["hits"] == base["hits"] + 1
    assert report["misses"] == base["misses"] + 1
    assert report["web_fallbacks"] == base["web_fallbacks"] + 1
    assert report["tokens"] == base["tokens"] + 140
    assert report["tokens"] == sum(r.tokens for r in records)
    assert report["cost"] == sum(r.cost for r in records)


def test_list_records_returns_shallow_copy():
    before = list_records()
    snapshot = list_records()
    snapshot.clear()
    assert list_records() == before
    assert isinstance(list_records(), list)
