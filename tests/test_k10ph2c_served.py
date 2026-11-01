"""K10PH2C served proofs: one proving test per set-C row.

Rows B0B-UNCOVERED_MVP_ACCEPT-158/160/161/172/173/229: the recorded
seams already listed by agent_si.k10_compet.served_rows() pointing at
the DONE-lane wave tests; proven here again through the same seams
without retargeting the wave entries.
Rows B0B-UNCOVERED_MVP_ACCEPT-214/215: full-id entries appended after
the 229 entry, proven here through the host-blockers and
attainability-gate seams.
Loopback TEST data only; no network, no installs.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_si import k10_compet  # noqa: E402


def _served():
    return {row["row"]: row for row in k10_compet.served_rows()}


def test_k10ph2c_158_project_analytics():
    """Row B0B-UNCOVERED_MVP_ACCEPT-158 served through the recorded seam."""
    entry = _served()["B0B-UNCOVERED_MVP_ACCEPT-158"]
    assert entry["route"] == (
        "agent_si.k10_compet.project_analytics_record recorded seam"
    ), entry
    assert entry["test"] == (
        "tests/test_k10wave_served.py::"
        "test_k10wave4_project_analytics"
    ), entry
    rows = k10_compet.project_analytics_record()
    assert [row["aggregate"] for row in rows] == [
        "task-counts", "audit-counts", "deterministic-order",
    ], rows
    for row in rows:
        for key in ("aggregate", "claim", "source", "snippet"):
            assert row.get(key), row
        assert "counts deterministically" in row["snippet"], row


def test_k10ph2c_160_model_provider_analytics():
    """Row B0B-UNCOVERED_MVP_ACCEPT-160 served through the recorded seam."""
    entry = _served()["B0B-UNCOVERED_MVP_ACCEPT-160"]
    assert entry["route"] == (
        "agent_si.k10_compet.model_provider_analytics_record recorded seam"
    ), entry
    assert entry["test"] == (
        "tests/test_k10wave_served.py::"
        "test_k10wave4_model_provider_analytics"
    ), entry
    rows = k10_compet.model_provider_analytics_record()
    assert [row["scope"] for row in rows] == [
        "per-model", "per-provider",
    ], rows
    for row in rows:
        for key in ("scope", "claim", "source", "snippet", "metrics"):
            assert row.get(key), row
        assert "cost or UNAVAILABLE" in row["snippet"], row
        assert "cost or UNAVAILABLE" in row["metrics"], row


def test_k10ph2c_161_authoritative_only():
    """Row B0B-UNCOVERED_MVP_ACCEPT-161 served through the recorded seam."""
    entry = _served()["B0B-UNCOVERED_MVP_ACCEPT-161"]
    assert entry["route"] == (
        "agent_si.k10_compet.analytics_authoritative_record recorded seam"
    ), entry
    assert entry["test"] == (
        "tests/test_k10wave_served.py::"
        "test_k10wave4_analytics_authoritative"
    ), entry
    rows = k10_compet.analytics_authoritative_record()
    assert [row["origin"] for row in rows] == [
        "telemetry-events-store", "metric-records-store",
        "never-chat-text", "never-live-rows",
    ], rows
    for row in rows:
        for key in ("origin", "claim", "source", "snippet"):
            assert row.get(key), row
        assert "never from chat text or live rows" in row["snippet"], row


def test_k10ph2c_172_fixture_rows_labelled():
    """Row B0B-UNCOVERED_MVP_ACCEPT-172 served through the recorded seam."""
    entry = _served()["B0B-UNCOVERED_MVP_ACCEPT-172"]
    assert entry["route"] == (
        "agent_si.k10_compet.fixture_capability_rows recorded seam"
    ), entry
    assert entry["test"] == (
        "tests/test_k10wave_served.py::"
        "test_k10wave4_fixture_capability"
    ), entry
    rows = k10_compet.fixture_capability_rows()
    assert [row["fixture"] for row in rows] == [
        "demo-fixture", "command-fixture",
    ], rows
    for row in rows:
        for key in ("fixture", "label", "claim", "source",
                    "snippet", "provenance"):
            assert row.get(key), row
        assert row["label"] == "TEST FIXTURES", row
        assert "never measured evidence" in row["snippet"], row


def test_k10ph2c_173_fixture_pack():
    """Row B0B-UNCOVERED_MVP_ACCEPT-173 served through the recorded seam."""
    entry = _served()["B0B-UNCOVERED_MVP_ACCEPT-173"]
    assert entry["route"] == (
        "agent_si.k10_compet.fixture_pack_record recorded seam"
    ), entry
    assert entry["test"] == (
        "tests/test_k10wave_served.py::"
        "test_k10wave4_fixture_pack"
    ), entry
    rows = k10_compet.fixture_pack_record()
    assert [row["property"] for row in rows] == [
        "ships-under-checkout", "not-measured-evidence",
    ], rows
    for row in rows:
        for key in ("property", "claim", "source", "snippet"):
            assert row.get(key), row
        assert "not measured evidence" in row["snippet"], row


def test_k10ph2c_229_localhost_doubles():
    """Row B0B-UNCOVERED_MVP_ACCEPT-229 served through the recorded seam."""
    entry = _served()["B0B-UNCOVERED_MVP_ACCEPT-229"]
    assert entry["route"] == (
        "agent_si.k10_compet.localhost_doubles_record recorded seam"
    ), entry
    assert entry["test"] == (
        "tests/test_k10wave_served.py::"
        "test_k10wave5_localhost_doubles"
    ), entry
    rows = k10_compet.localhost_doubles_record()
    assert [row["element"] for row in rows] == [
        "condition-unavailable-local-legs", "remedy-localhost-mock-doubles",
        "label-test-fixtures",
    ], rows
    for row in rows:
        for key in ("element", "claim", "source", "snippet"):
            assert row.get(key), row
        assert "labelled localhost mock doubles as TEST FIXTURES" in row[
            "snippet"], row


def test_k10ph2c_214_host_blockers():
    """Row B0B-UNCOVERED_MVP_ACCEPT-214 served through the recorded seam."""
    entry = _served()["B0B-UNCOVERED_MVP_ACCEPT-214"]
    assert entry["route"] == (
        "agent_si.k10_compet.host_blockers_record recorded seam"
    ), entry
    assert entry["test"] == (
        "tests/test_k10ph2c_served.py::"
        "test_k10ph2c_214_host_blockers"
    ), entry
    rows = k10_compet.host_blockers_record()
    assert len(rows) == 1, rows
    for row in rows:
        for key in ("claim", "source", "snippet", "evidence"):
            assert row.get(key), row
        assert "host blockers name missing permissions" in row[
            "snippet"], row
        assert "route GET /k10/compet/audit" in row["evidence"], row
        assert "test_k10ph2c_214_host_blockers" in row["evidence"], row


def test_k10ph2c_215_attainability_gate():
    """Row B0B-UNCOVERED_MVP_ACCEPT-215 served through the recorded seam."""
    entry = _served()["B0B-UNCOVERED_MVP_ACCEPT-215"]
    assert entry["route"] == (
        "agent_si.k10_compet.attainability_gate_record recorded seam"
    ), entry
    assert entry["test"] == (
        "tests/test_k10ph2c_served.py::"
        "test_k10ph2c_215_attainability_gate"
    ), entry
    rows = k10_compet.attainability_gate_record()
    assert len(rows) == 1, rows
    for row in rows:
        for key in ("claim", "source", "snippet", "evidence"):
            assert row.get(key), row
        assert "not attainable on a host" in row["snippet"], row
        assert "route GET /k10/compet/audit" in row["evidence"], row
        assert "test_k10ph2c_215_attainability_gate" in row["evidence"], row
