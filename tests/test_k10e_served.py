"""K10E served map: one proving test per open row.

Row 131 (B0B-UNCOVERED_MVP_ACCEPT-131): the recorded checkout-root
README seam documents prerequisites, setup steps, demo commands,
fixture commands, and task pointers.
Row 153 (B0B-UNCOVERED_MVP_ACCEPT-153): the recorded startup-sequence
seam covers checkout, configure from environment example, offline
install from lockfiles, and launch.
Row 173 (B0B-UNCOVERED_MVP_ACCEPT-173): the recorded fixture-pack seam
ships the MVP fixture pack under checkout, not as measured evidence.
Row 214 (B0B-UNCOVERED_MVP_ACCEPT-214): the recorded host-blockers seam
names missing permissions, auditor provider, and second provider.
Row 215 (B0B-UNCOVERED_MVP_ACCEPT-215): the recorded attainability-gate
seam holds MVP until local permission, auditor provider, and a second
real provider resolve.
Row HC-4: the recorded licence-check seam is an owner decision.
Each row is listed by agent_si.k10_compet.served_rows() and proven here
through its serving seam. Loopback TEST data only; no network, no installs.
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


def _check_recorded(rows, test_id):
    """Shared recorded-loopback shape: never a live claim."""
    assert isinstance(rows, list) and len(rows) >= 1, rows
    for row in rows:
        assert set(row) == {"claim", "source", "snippet", "evidence"}, row
        for key in ("claim", "source", "snippet", "evidence"):
            assert row.get(key), row
        assert "recorded" in row["source"], row
        assert "loopback" in row["source"], row
        assert "not live" in row["source"], row
        assert row["snippet"].startswith("verbatim recorded: '"), row
        assert row["snippet"].endswith("'"), row
        assert "route GET /k10/compet/audit" in row["evidence"], row
        assert test_id in row["evidence"], row


def test_k10e_readme_root_checks():
    """Row 131 served through the recorded readme-root seam."""
    entry = _served()["131"]
    assert entry["route"] == (
        "agent_si.k10_compet.readme_root_checks recorded seam"
    ), entry
    assert entry["test"] == (
        "tests/test_k10e_served.py::test_k10e_readme_root_checks"
    ), entry
    rows = k10_compet.readme_root_checks()
    _check_recorded(rows, "test_k10e_readme_root_checks")
    assert "README at checkout root" in rows[0]["snippet"], rows


def test_k10e_startup_sequence():
    """Row 153 served through the recorded startup-sequence seam."""
    entry = _served()["153"]
    assert entry["route"] == (
        "agent_si.k10_compet.k10e_startup_sequence_record recorded seam"
    ), entry
    assert entry["test"] == (
        "tests/test_k10e_served.py::test_k10e_startup_sequence"
    ), entry
    rows = k10_compet.k10e_startup_sequence_record()
    _check_recorded(rows, "test_k10e_startup_sequence")
    assert "startup sequence" in rows[0]["snippet"], rows


def test_k10e_fixture_pack():
    """Row 173 served through the recorded fixture-pack seam."""
    entry = _served()["173"]
    assert entry["route"] == (
        "agent_si.k10_compet.k10e_fixture_pack_record recorded seam"
    ), entry
    assert entry["test"] == (
        "tests/test_k10e_served.py::test_k10e_fixture_pack"
    ), entry
    rows = k10_compet.k10e_fixture_pack_record()
    _check_recorded(rows, "test_k10e_fixture_pack")
    assert "fixture pack" in rows[0]["snippet"], rows


def test_k10e_host_blockers():
    """Row 214 served through the recorded host-blockers seam."""
    entry = _served()["214"]
    assert entry["route"] == (
        "agent_si.k10_compet.host_blockers_record recorded seam"
    ), entry
    assert entry["test"] == (
        "tests/test_k10e_served.py::test_k10e_host_blockers"
    ), entry
    rows = k10_compet.host_blockers_record()
    _check_recorded(rows, "test_k10e_host_blockers")
    assert "host blockers" in rows[0]["snippet"], rows


def test_k10e_attainability_gate():
    """Row 215 served through the recorded attainability-gate seam."""
    entry = _served()["215"]
    assert entry["route"] == (
        "agent_si.k10_compet.attainability_gate_record recorded seam"
    ), entry
    assert entry["test"] == (
        "tests/test_k10e_served.py::test_k10e_attainability_gate"
    ), entry
    rows = k10_compet.attainability_gate_record()
    _check_recorded(rows, "test_k10e_attainability_gate")
    assert "not attainable on a host" in rows[0]["snippet"], rows


def test_k10e_licence_check():
    """Row HC-4 served through the recorded licence-check seam."""
    entry = _served()["HC-4"]
    assert entry["route"] == (
        "agent_si.k10_compet.licence_check_record recorded seam"
    ), entry
    assert entry["test"] == (
        "tests/test_k10e_served.py::test_k10e_licence_check"
    ), entry
    rows = k10_compet.licence_check_record()
    _check_recorded(rows, "test_k10e_licence_check")
    assert "licence check" in rows[0]["snippet"], rows
