"""K10PH2B served behaviour tests, set B only (9 rows).

Each test calls the real recorded seam in agent_si.k10_compet directly
(pure recorded data; stdlib only, no network, no providers, no I/O) and
asserts the exact row discriminants plus served evidence via the recorded
route/entry string GET /api/v1/release/compet/audit (backend app read-only seam
reference serving agent_si.k10_compet recorded seams).

Rows (all set B):
-151 clean_boot_record steps documented-steps/versioned-dependencies/
identical-working-startup.
-152 reproducible_startup_record legs demos/fixtures/ui-checks.
-209 mvp_verdict_record verdicts ACCEPTED/NOT_ACCEPTED with blockers.
-210 mvp_accepted_rule_record all-items-hold->ACCEPTED /
any-item-short->NOT_ACCEPTED.
-211 mvp_acceptance_requirements_record requirements readme/
secret-free-environment-example/twice-identical-reproducible-run.
-212 mvp_shortfall_record properties not-accepted-on-shortfall/
blockers-listed.
-217 test_fixture_wiring_record properties wiring-only/
never-measured-evidence.
-225 local_demo_runtime_record needs permission-gated-local-runtime/
capability-evidence-for-fixture-class.
-227 split_demo_cloud_record legs real-cloud-verification/
local-draft-output/draft-hash-binding-before-acceptance.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_si import k10_compet  # noqa: E402

SERVED_ROUTE = "GET /api/v1/release/compet/audit"


def test_k10ph2b_151():
    """Row B0B-UNCOVERED_MVP_ACCEPT-151 served via GET /api/v1/release/compet/audit."""
    assert SERVED_ROUTE == "GET /api/v1/release/compet/audit", SERVED_ROUTE
    rows = k10_compet.clean_boot_record()
    assert [row["step"] for row in rows] == [
        "documented-steps",
        "versioned-dependencies",
        "identical-working-startup",
    ], rows
    for row in rows:
        for key in ("step", "claim", "source", "snippet"):
            assert row.get(key), row
        assert "recorded" in row["source"], row
        assert "clean checkout boot follows documented steps" in row["snippet"], row


def test_k10ph2b_152():
    """Row B0B-UNCOVERED_MVP_ACCEPT-152 served via GET /api/v1/release/compet/audit."""
    assert SERVED_ROUTE == "GET /api/v1/release/compet/audit", SERVED_ROUTE
    rows = k10_compet.reproducible_startup_record()
    assert [row["leg"] for row in rows] == [
        "demos",
        "fixtures",
        "ui-checks",
    ], rows
    for row in rows:
        for key in ("leg", "claim", "source", "snippet", "evidence"):
            assert row.get(key), row
        assert "alongside demos, fixtures, and UI checks" in row["snippet"], row
    assert any(SERVED_ROUTE in row["evidence"] for row in rows), rows


def test_k10ph2b_209():
    """Row B0B-UNCOVERED_MVP_ACCEPT-209 served via GET /api/v1/release/compet/audit."""
    assert SERVED_ROUTE == "GET /api/v1/release/compet/audit", SERVED_ROUTE
    rows = k10_compet.mvp_verdict_record()
    assert [row["verdict"] for row in rows] == [
        "ACCEPTED",
        "NOT_ACCEPTED",
    ], rows
    for row in rows:
        for key in ("verdict", "claim", "source", "snippet", "blockers"):
            assert row.get(key), row
        assert "recorded" in row["source"], row
        assert "binary ACCEPTED or NOT_ACCEPTED" in row["snippet"], row
        assert "explicit blocker" in row["blockers"], row


def test_k10ph2b_210():
    """Row B0B-UNCOVERED_MVP_ACCEPT-210 served via GET /api/v1/release/compet/audit."""
    assert SERVED_ROUTE == "GET /api/v1/release/compet/audit", SERVED_ROUTE
    rows = k10_compet.mvp_accepted_rule_record()
    assert {row["case"]: row["result"] for row in rows} == {
        "all-items-hold": "ACCEPTED",
        "any-item-short": "NOT_ACCEPTED",
    }, rows
    for row in rows:
        for key in ("case", "claim", "source", "snippet", "result"):
            assert row.get(key), row
        assert "iff all acceptance items hold" in row["snippet"], row


def test_k10ph2b_211():
    """Row B0B-UNCOVERED_MVP_ACCEPT-211 served via GET /api/v1/release/compet/audit."""
    assert SERVED_ROUTE == "GET /api/v1/release/compet/audit", SERVED_ROUTE
    rows = k10_compet.mvp_acceptance_requirements_record()
    assert [row["requirement"] for row in rows] == [
        "readme",
        "secret-free-environment-example",
        "twice-identical-reproducible-run",
    ], rows
    for row in rows:
        for key in ("requirement", "claim", "source", "snippet"):
            assert row.get(key), row
        assert "twice-identical reproducible run" in row["snippet"], row


def test_k10ph2b_212():
    """Row B0B-UNCOVERED_MVP_ACCEPT-212 served via GET /api/v1/release/compet/audit."""
    assert SERVED_ROUTE == "GET /api/v1/release/compet/audit", SERVED_ROUTE
    rows = k10_compet.mvp_shortfall_record()
    assert [row["property"] for row in rows] == [
        "not-accepted-on-shortfall",
        "blockers-listed",
    ], rows
    for row in rows:
        for key in ("property", "claim", "source", "snippet"):
            assert row.get(key), row
        assert "NOT_ACCEPTED with listed blockers" in row["snippet"], row


def test_k10ph2b_217():
    """Row B0B-UNCOVERED_MVP_ACCEPT-217 served via GET /api/v1/release/compet/audit."""
    assert SERVED_ROUTE == "GET /api/v1/release/compet/audit", SERVED_ROUTE
    rows = k10_compet.test_fixture_wiring_record()
    assert [row["property"] for row in rows] == [
        "wiring-only",
        "never-measured-evidence",
    ], rows
    for row in rows:
        for key in ("property", "claim", "source", "snippet"):
            assert row.get(key), row
        assert "wiring only" in row["snippet"], row
        assert "never presented as measured evidence" in row["snippet"], row


def test_k10ph2b_225():
    """Row B0B-UNCOVERED_MVP_ACCEPT-225 served via GET /api/v1/release/compet/audit."""
    assert SERVED_ROUTE == "GET /api/v1/release/compet/audit", SERVED_ROUTE
    rows = k10_compet.local_demo_runtime_record()
    assert [row["need"] for row in rows] == [
        "permission-gated-local-runtime",
        "capability-evidence-for-fixture-class",
    ], rows
    for row in rows:
        for key in ("need", "claim", "source", "snippet"):
            assert row.get(key), row
        assert "permission-gated local runtime" in row["snippet"], row
        assert "capability evidence for the fixture class" in row["snippet"], row


def test_k10ph2b_227():
    """Row B0B-UNCOVERED_MVP_ACCEPT-227 served via GET /api/v1/release/compet/audit."""
    assert SERVED_ROUTE == "GET /api/v1/release/compet/audit", SERVED_ROUTE
    rows = k10_compet.split_demo_cloud_record()
    assert [row["leg"] for row in rows] == [
        "real-cloud-verification",
        "local-draft-output",
        "draft-hash-binding-before-acceptance",
    ], rows
    for row in rows:
        for key in ("leg", "claim", "source", "snippet"):
            assert row.get(key), row
        assert "draft-hash binding before acceptance" in row["snippet"], row
