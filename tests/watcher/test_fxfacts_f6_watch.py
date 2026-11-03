"""FXFACTS F6b RED: a fresh run start fires zero watcher alerts.

Cause: verdict_for escalates EVERY card when no SERVICE_STATE beat exists
(_heartbeat_stale returns True on empty). A normal run start (DEVRUN rows,
no beats yet) journals two ESCALATE alerts. Expected: no beats means no
evidence of staleness -> base verdicts, zero journal rows; a stored
TAMPER_ATTEMPT still BLOCKs; a stale beat still ESCALATEs.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_WS = os.path.dirname(os.path.dirname(_HERE))
for _p in (_WS, os.path.join(_WS, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from agent_si.watcher import journal as _journal
from agent_si.watcher import rules as _rules


def _fresh(project):
    _journal.reset_state()
    _rules.reset_state()
    _journal.append_event(project, "runner", "DEVRUN_PLAN", "plan", ("r-1",))


def _decisions(project):
    return _journal.stored_rows(project, "WATCH_DECISION")


def test_fresh_run_start_gives_zero_alerts():
    project = "fxf6b-fresh"
    _fresh(project)
    tamper = _rules.evaluate(project, "rule-tamper")
    guard = _rules.evaluate(project, "rule-guard")
    assert tamper.verdict == _rules.WatchVerdict.ALLOW, tamper
    assert guard.verdict == _rules.WatchVerdict.BLOCK, guard
    assert _decisions(project) == (), _decisions(project)


def test_tamper_attempt_still_blocks():
    project = "fxf6b-tamper"
    _fresh(project)
    _journal.append_event(project, "agent-x", "TAMPER_ATTEMPT",
                          "edited log", ("ref-1",))
    flagged = _rules.evaluate(project, "rule-tamper")
    assert flagged.verdict == _rules.WatchVerdict.BLOCK, flagged
    assert len(_decisions(project)) == 1, _decisions(project)


def test_stale_beat_still_escalates_hang():
    stale = (_journal.StoredRow(
        kind="SERVICE_STATE", source="watcher", summary="old", refs=(),
        entry_id="evt-0001", timestamp="2026-01-01T00:00:00Z"),)
    card = _rules.describe("rule-tamper")
    assert _rules.verdict_for(
        card, stale, _rules._utcnow()) == _rules.WatchVerdict.ESCALATE


def test_hang_override_moves_the_loop_threshold():
    import pytest
    from datetime import datetime, timedelta, timezone
    project = "fxf6b-minutes"
    _journal.reset_state()
    _rules.reset_state()
    _journal.append_event(project, "runner", "DEVRUN_PLAN", "plan", ("r-1",))
    now = datetime.now(timezone.utc).replace(microsecond=0)
    old_ts = (now - timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
    old = _journal.StoredRow(
        kind="SERVICE_STATE", source="watcher", summary="old", refs=(),
        entry_id="evt-0002", timestamp=old_ts)
    card = _rules.describe("rule-tamper")
    assert _rules.verdict_for(
        card, (old,), _rules._utcnow()) == _rules.WatchVerdict.ESCALATE
    eff = _rules.set_card_hang_minutes(project, "rule-tamper", 1440)
    assert eff.hang_minutes == 1440
    assert _rules.effective_hang_minutes(project, "rule-tamper") == 1440
    loop_card = _rules.effective_card(project, "rule-tamper")
    assert _rules.verdict_for(
        loop_card, (old,), _rules._utcnow()) == _rules.WatchVerdict.ALLOW
    with pytest.raises(ValueError):
        _rules.set_card_hang_minutes(project, "rule-tamper", 0)
    with pytest.raises(ValueError):
        _rules.set_card_hang_minutes(project, "rule-tamper", 1441)
    with pytest.raises(_rules.WatcherError):
        _rules.set_card_hang_minutes(project, "rule-missing", 20)
