"""K09-B behaviour contract, STEP1.

RED until STEP2 implements src/agent_si/kb/telemetry.py,
src/agent_si/kb/savings.py and tools/kb_validator/iface.py: every test
asserts real behaviour, so the signatures-only contract files (each body
the literal Ellipsis, hence returning None) fail.
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
from tools.kb_validator.iface import (
    KB_MANIFEST_MISSING,
    KB_PURPOSE_MISSING,
    KB_SECTIONS_MISSING,
    KbValidationResult,
    validate_kb_dir,
)

FIX = os.path.join(_WS, "tests", "fixtures", "k09b")


# FAKE-OF: RECORDS/day1/K04_INTERFACE_STUB_v2.py
@dataclass
class FakePricingSnapshot:
    """Test-local stand-in for the K04 PricingSnapshot.

    Shapes from RECORDS/day1/K04_INTERFACE.md sec 3.5/2 CostLine and
    PricingSnapshot; behaviour-free (signatures-only = not PASS).
    """

    pricing_snapshot_id: str
    provider_id: str
    model_id: str
    currency: str
    effective_at: str
    source: str
    input_token_price: Optional[str] = None
    output_token_price: Optional[str] = None
    cached_token_price: Optional[str] = None
    reasoning_token_price: Optional[str] = None
    request_price: Optional[str] = None


# FAKE-OF: RECORDS/day1/K04_INTERFACE_STUB_v2.py
@dataclass
class FakeCostLine:
    """Test-local stand-in for the K04 CostLine (amount null = UNAVAILABLE)."""

    amount: Optional[float]
    currency: str
    pricing_snapshot_id: Optional[str]


def test_validator_accepts_wellformed_kb():
    result = validate_kb_dir(os.path.join(FIX, "good"))
    assert isinstance(result, KbValidationResult)
    assert result.ok is True
    assert result.error_code is None


def test_validator_rejects_missing_manifest():
    result = validate_kb_dir(os.path.join(FIX, "no-manifest"))
    assert isinstance(result, KbValidationResult)
    assert result.ok is False
    assert result.error_code == KB_MANIFEST_MISSING


def test_validator_rejects_missing_sections():
    result = validate_kb_dir(os.path.join(FIX, "no-sections"))
    assert isinstance(result, KbValidationResult)
    assert result.ok is False
    assert result.error_code == KB_SECTIONS_MISSING


def test_validator_rejects_missing_purpose():
    result = validate_kb_dir(os.path.join(FIX, "no-purpose"))
    assert isinstance(result, KbValidationResult)
    assert result.ok is False
    assert result.error_code == KB_PURPOSE_MISSING


def test_record_calls_store_typed_records():
    before = list_records()
    assert isinstance(before, list)
    record_hit("dev", "agent-1", 100, 0.02)
    record_miss("dev", "agent-1", 50, 0.01)
    record_web_fallback("dev", "agent-1", 25, 0.005)
    after = list_records()
    assert isinstance(after, list)
    assert len(after) == len(before) + 3
    assert [r.kind for r in after[len(before):]] == ["hit", "miss", "web_fallback"]
    assert isinstance(after[-1], KbTelemetryRecord)
    assert (after[-1].role, after[-1].agent, after[-1].tokens) == ("dev", "agent-1", 25)


def test_savings_report_reads_stored_records_only():
    before = list_records()
    assert isinstance(before, list)
    base_hits = sum(1 for r in before if r.kind == "hit")
    base_misses = sum(1 for r in before if r.kind == "miss")
    base_fallbacks = sum(1 for r in before if r.kind == "web_fallback")
    base_tokens = sum(r.tokens for r in before)
    base_cost = sum(r.cost for r in before)
    record_hit("dev", "agent-2", 100, 0.02)
    record_miss("dev", "agent-2", 50, 0.01)
    record_web_fallback("dev", "agent-2", 25, 0.005)
    records = list_records()
    assert isinstance(records, list)
    report = savings_report()
    assert isinstance(report, dict)
    assert report["hits"] == base_hits + 1
    assert report["hits"] == sum(1 for r in records if r.kind == "hit")
    assert report["misses"] == base_misses + 1
    assert report["misses"] == sum(1 for r in records if r.kind == "miss")
    assert report["web_fallbacks"] == base_fallbacks + 1
    assert report["web_fallbacks"] == sum(1 for r in records if r.kind == "web_fallback")
    assert report["tokens"] == base_tokens + 175
    assert report["tokens"] == sum(r.tokens for r in records)
    assert report["cost"] == pytest.approx(base_cost + 0.035)
    assert report["cost"] == pytest.approx(sum(r.cost for r in records))


def test_keeper_price_lookup_flows_through_costline():
    snapshot = FakePricingSnapshot(
        pricing_snapshot_id="snap-k09b-1",
        provider_id="p1",
        model_id="m1",
        currency="USD",
        effective_at="2026-01-01",
        source="keeper",
        input_token_price="0.001",
        output_token_price="0.002",
    )
    line = FakeCostLine(
        amount=0.02,
        currency=snapshot.currency,
        pricing_snapshot_id=snapshot.pricing_snapshot_id,
    )
    assert line.pricing_snapshot_id == snapshot.pricing_snapshot_id
    before = list_records()
    assert isinstance(before, list)
    record_hit("keeper", "price-agent", 100, line.amount)
    records = list_records()
    assert isinstance(records, list)
    assert line.amount in [r.cost for r in records[len(before):]]
    report = savings_report()
    assert isinstance(report, dict)
    assert report["cost"] == pytest.approx(sum(r.cost for r in records))
