"""FXZERO item 4 (H91) served proof: one condition = one alert.

Repeats of an unchanged abnormal condition journal no new WATCH_DECISION
row; the repeat still counts into the per-rule fired tally; a finished
run (RETURNED live rows) is not watched. Fakes live ONLY at the provider
network boundary; here no provider is involved at all (pure watcher).
"""

import os
import sys

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)
_WS = os.path.dirname(_TESTS_DIR)
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend import agents_live  # noqa: E402
from agent_si.watcher import engine as _watch_engine  # noqa: E402
from agent_si.watcher import journal as _watch_journal  # noqa: E402
from agent_si.watcher import rules as _watch_rules  # noqa: E402
from agent_si.watcher import stats as _watch_stats  # noqa: E402
from agent_si.watcher import status as _watch_status  # noqa: E402


def setup_function(_func):
    agents_live.clear_live_rows()
    _watch_journal.reset_state()
    _watch_rules.reset_state()
    _watch_engine.reset_state()
    _watch_stats.reset_state()


def teardown_function(_func):
    agents_live.clear_live_rows()
    _watch_journal.reset_state()
    _watch_rules.reset_state()
    _watch_engine.reset_state()
    _watch_stats.reset_state()


def test_fxzero_repeat_condition_single_alert_row():
    pid = "fxzero-i4"
    _watch_journal.append_event(pid, "watcher", "SERVICE_STATE", "boot", ())
    _watch_journal.append_event(pid, "agent-x", "TAMPER_ATTEMPT",
                               "edited log", ("ref-1",))
    _watch_engine.tick(pid)
    _watch_engine.tick(pid)
    rows = list(_watch_journal.stored_rows(pid, "WATCH_DECISION"))
    assert len(rows) == 1, [str(row.summary) for row in rows]
    served = _watch_status.get(pid)
    assert served.checks_done == 4, served.checks_done
    assert served.alerts_raised == 1, served.alerts_raised
    fired = dict(served.rules_fired)
    assert fired.get("rule-tamper", 0) == 2, fired


def test_fxzero_changed_condition_alerts_again():
    pid = "fxzero-i4b"
    _watch_journal.append_event(pid, "watcher", "SERVICE_STATE", "boot", ())
    _watch_journal.append_event(pid, "agent-x", "TAMPER_ATTEMPT",
                               "edited log", ("ref-1",))
    _watch_engine.tick(pid)
    _watch_journal.append_event(pid, "agent-x", "TAMPER_ATTEMPT",
                               "second edit", ("ref-2",))
    _watch_engine.tick(pid)
    rows = list(_watch_journal.stored_rows(pid, "WATCH_DECISION"))
    assert len(rows) == 2, [str(row.summary) for row in rows]
    served = _watch_status.get(pid)
    assert served.alerts_raised == 2, served.alerts_raised


def test_fxzero_returned_rows_not_watched():
    agents_live.record_live_row("fxzero-i4w/run/worker", {
        "agent": "worker-plan",
        "scope": "fxzero:plan:worker",
        "deliverable": "artifact://run/r1/plan",
        "status": "RETURNED",
    })
    try:
        served = _watch_status.get("fxzero-i4w")
        assert served.watched_agents == 0, served.watched_agents
        assert served.watched_runs == 0, served.watched_runs
    finally:
        agents_live.clear_live_rows()


def test_fxzero_running_rows_still_watched():
    agents_live.record_live_row("fxzero-i4c/run/worker", {
        "agent": "worker-p1",
        "scope": "fxzero:p1:worker",
        "deliverable": "artifact://run/r2/p1",
        "status": "RUNNING",
    })
    try:
        served = _watch_status.get("fxzero-i4c")
        assert served.watched_agents == 1, served.watched_agents
    finally:
        agents_live.clear_live_rows()
