"""The teststage chain (the live F04 path) grows the watcher journal.

PART1DRIVE4 F06 (01.11): a full F04 chain through /api/v1/teststage/runs/start,
advance, results and finish left the journal [] because only
assurance.coordinator.run_assurance emitted run lifecycle rows. The stage runner
now journals every served step; rows are read back through the watcher interface
entry journal.list_events, never seeded.
"""

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import agent_si.watcher.interface as iface  # noqa: E402
import agent_si.watcher.journal as journal  # noqa: E402
from agent_si.test_runners import stage_runner  # noqa: E402

PROJECT_ID = "P-STAGE-JOURNAL"
RUN_ID = "run-stage-journal-1"


@pytest.fixture(autouse=True)
def _lane():
    journal.reset_state()
    yield
    journal.reset_state()


def _served(project_id):
    dotted = iface.REALIZATION_MAP["journal.list_events"]
    module_name, _, func_name = dotted.rpartition(".")
    serve = getattr(importlib.import_module(module_name), func_name)
    return serve(project_id, "")


def test_stage_chain_writes_journal_rows():
    assert _served(PROJECT_ID) == [] or len(_served(PROJECT_ID)) == 0
    run = stage_runner.start_stage(PROJECT_ID, "plan-stage-journal", RUN_ID)
    run = stage_runner.advance_stage(run, stage_runner.StageState.PERMISSION)
    run = stage_runner.advance_stage(run, stage_runner.StageState.RUNNING)
    stage_runner.record_result(RUN_ID, "t-boot", "PASS", "out://t-boot", None)
    stage_runner.finish_stage(RUN_ID)
    rows = _served(PROJECT_ID)
    summaries = " | ".join(row.summary for row in journal.stored_rows(PROJECT_ID))
    assert len(rows) >= 4, summaries
    for phase in ("run plan", "run start", "run finish"):
        assert phase in summaries, summaries
    assert RUN_ID in summaries


def test_finish_stage_keeps_its_name_for_route_maps():
    assert stage_runner.finish_stage.__name__ == "finish_stage"
