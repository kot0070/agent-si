"""Lane B coder B1: ledger tests (ROW35/M-P1-17 load + nudge, R-358 writer).

RED->GREEN: written first against empty stubs, then implemented to GREEN.
Loads the module by file path (stdlib importlib only, no package install).
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LEDGER_PATH = ROOT / "src" / "agent_si" / "backend" / "orchestration" / "ledger.py"


def load_ledger():
    spec = importlib.util.spec_from_file_location("b1_ledger", LEDGER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["b1_ledger"] = module
    spec.loader.exec_module(module)
    return module


lg = load_ledger()


def make_ledger():
    ledger = lg.PackageLedger()
    ledger.record_row("pkg-a", agents=3, peak_concurrency=2, wall_time_s=12.5)
    return ledger


def test_ledger_row_fields():
    ledger = make_ledger()
    row = ledger.get_row("pkg-a")
    assert row.package_id == "pkg-a"
    assert isinstance(row.agents, int) and row.agents == 3
    assert isinstance(row.peak_concurrency, int) and row.peak_concurrency == 2
    assert isinstance(row.wall_time_s, float) and row.wall_time_s == 12.5


def test_ledger_row_rejects_bad_values():
    ledger = lg.PackageLedger()
    for bad in (
        {"agents": -1, "peak_concurrency": 1, "wall_time_s": 1.0},
        {"agents": 1, "peak_concurrency": -2, "wall_time_s": 1.0},
        {"agents": 1, "peak_concurrency": 1, "wall_time_s": -0.5},
    ):
        try:
            ledger.record_row("pkg-bad", **bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"bad row accepted: {bad}")
    assert ledger.get_row("pkg-bad") is None


def test_package_report_shows_load():
    report = lg.package_report(make_ledger(), "pkg-a")
    assert report["row"]["agents"] == 3
    assert report["row"]["peak_concurrency"] == 2
    assert report["row"]["wall_time_s"] == 12.5


def test_report_nudge_for_next_package_without_autopush():
    report = lg.package_report(make_ledger(), "pkg-a", next_package_id="pkg-b")
    assert "pkg-b" in report["nudge"]
    assert "pkg-a" in report["nudge"]
    assert report["auto_push"] is False


def test_ledger_writer_breaking_change_refused_without_mutation():
    store = lg.LedgerConfigStore()
    before = dict(store.config)
    rows_before = len(store.log.rows)
    outcome = lg.apply_ledger_config_change(
        store, "drop audit guard", "test", "tester", {"independent_audit": False}
    )
    assert outcome.accepted is False
    assert outcome.reason != ""
    assert outcome.row is None
    assert store.config == before
    assert len(store.log.rows) == rows_before


def test_ledger_writer_over_cap_refused():
    store = lg.LedgerConfigStore()
    outcome = lg.apply_ledger_config_change(
        store, "flood", "test", "tester", {"agents": 10**6}
    )
    assert outcome.accepted is False
    assert "cap" in outcome.reason.lower()


def test_ledger_writer_accepted_persists_one_decision_row():
    store = lg.LedgerConfigStore()
    outcome = lg.apply_ledger_config_change(
        store, "record two agents", "observed", "tester", {"agents": 2}
    )
    assert outcome.accepted is True
    row = outcome.row
    assert row is not None
    assert (row.scope, row.statement, row.reason, row.authority) == (
        "ledger-config",
        "record two agents",
        "observed",
        "tester",
    )
    assert row.decision_id != "" and row.created_at != ""
    assert len(store.log.rows) == 1


def test_surfacing_probe_ledger_rejection_reaches_caller():
    store = lg.LedgerConfigStore()
    outcome = lg.apply_ledger_config_change(
        store, "drop audit guard", "test", "tester", {"independent_audit": False}
    )
    surfaced = lg.surface_rejection(outcome)
    assert outcome.reason in surfaced


def test_bounded_delta_intake_accepts_within_bound():
    taken = []
    result = lg.intake_bounded_delta(taken, {"delta_id": "d1", "items": ["a", "b"]}, 3)
    assert result["accepted"] is True
    assert len(taken) == 1


def test_bounded_delta_intake_refuses_over_bound_without_record():
    taken = []
    result = lg.intake_bounded_delta(
        taken, {"delta_id": "d2", "items": ["a", "b", "c", "d"]}, 3
    )
    assert result["accepted"] is False
    assert result["reason"] != ""
    assert taken == []


def test_hot_write_persists_ledger_roundtrip(tmp_path):
    ledger = make_ledger()
    path = str(tmp_path / "ledger.json")
    lg.persist_ledger(path, ledger)
    reloaded = lg.load_ledger(path)
    row = reloaded.get_row("pkg-a")
    assert (row.agents, row.peak_concurrency, row.wall_time_s) == (3, 2, 12.5)
