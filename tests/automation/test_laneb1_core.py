"""Lane B STEP2 automation runtime core (B-S2-1): timers, launchers, metric
actions and runs, all recorded, governed and pausable.

Covers K08 ROWS R-335 (timers, auto-launchers and metric-triggered actions
are recorded and pausable), R-363 (launchers resume after restart within
budget and time guards), M-P3-94 (missed fires skip or run once per
catch-up setting; timers survive restarts), 45B (cancel keeps history and
finalizes), row 174 (global plus per-project pause; runs recorded under
governance), P5 (a timer fires a launcher and a metric trigger fires its
action; both are recorded and both stop under the global pause, with the
per-project switch respected) and P7 (resume after restart within the
budget and time guards).

Session-token refusal (SESSION_TOKEN_MISSING / SESSION_TOKEN_INVALID)
lives in the route layer (backend/automation_routes), not in this runtime
core, so it is out of scope here.
"""

import json
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.append(str(SRC))

from agent_si.automation import launcher
from agent_si.automation import pause
from agent_si.automation import runner
from agent_si.automation import scheduler
from agent_si.automation import triggers
from agent_si.automation.interface import (
    ERROR_CODES,
    REALIZATION_MAP,
    AutomationError,
)

# K08F1: K02_DOC (RECORDS read) removed — a clean clone has no RECORDS folder.
# The model-id check now uses the in-repo frozen source (see below).


def _code(excinfo):
    return excinfo.value.code


# FAKE-OF: agent_si.watcher.journal.append_event
class FakeJournal:
    """Local journal stand-in: records automation notifications."""

    def __init__(self):
        self.calls = []

    def append_event(self, project_id, source, kind, summary, refs=()):
        receipt = {
            "entry_id": "evt-%04d" % (len(self.calls) + 1),
            "timestamp": "2026-10-27T00:00:00Z",
            "hash": "hash-%04d" % (len(self.calls) + 1),
        }
        self.calls.append(
            {
                "project_id": project_id,
                "source": source,
                "kind": kind,
                "summary": summary,
                "refs": tuple(refs),
                "receipt": receipt,
            }
        )
        return receipt


# FAKE-OF: agent_si.toolguard.escape.check_escape
class FakeGuard:
    """Local guard stand-in: records workspace checks before writes."""

    def __init__(self):
        self.calls = []
        self.allow = True

    def check_escape(self, project_id, path):
        self.calls.append((project_id, path))
        return self.allow


# FAKE-OF: agent_si.backend.stop_all.request_stop
class FakeStopAll:
    """Local stop-all stand-in: records stop requests."""

    def __init__(self):
        self.calls = []

    def request_stop(self, project_id, reason):
        receipt = {"project_id": project_id, "stopped": True, "reason": reason}
        self.calls.append(receipt)
        return receipt


@pytest.fixture(autouse=True)
def _isolated():
    pause.reset_state()
    runner.reset_state()
    triggers.reset_state()
    scheduler.reset_state()
    journal = FakeJournal()
    guard = FakeGuard()
    stopper = FakeStopAll()
    runner.set_journal_hook(journal.append_event)
    runner.set_budget_hook(None)
    launcher.set_journal_hook(journal.append_event)
    launcher.set_guard_hook(guard.check_escape)
    triggers.set_journal_hook(journal.append_event)
    scheduler.set_journal_hook(journal.append_event)
    scheduler.set_stop_hook(stopper.request_stop)
    scheduler.set_clock(None)
    return {"journal": journal, "guard": guard, "stopper": stopper}


def _template(project_id="proj-a", template_id="tpl-nightly"):
    runner.register_template(template_id, project_id, name="nightly")
    return template_id


# --- row 174, first half: global plus per-project pause ---

def test_row174_global_pause_needs_reason():
    with pytest.raises(AutomationError) as excinfo:
        pause.set_global(True, "")
    assert _code(excinfo) == "PAUSE_REASON_MISSING"


def test_row174_global_pause_takes_effect():
    assert pause.is_effective("proj-a") is False
    pause.set_global(True, "drill")
    assert pause.is_effective("proj-a") is True
    assert pause.is_effective("proj-b") is True
    pause.set_global(False, "")
    assert pause.is_effective("proj-a") is False


def test_row174_per_project_pause_is_scoped():
    pause.set_project("proj-a", True)
    assert pause.is_effective("proj-a") is True
    assert pause.is_effective("proj-b") is False
    pause.set_project("proj-a", False)
    assert pause.is_effective("proj-a") is False


def test_row174_global_or_per_project():
    pause.set_project("proj-a", True)
    pause.set_global(True, "drill")
    pause.set_project("proj-a", False)
    assert pause.is_effective("proj-a") is True
    pause.set_global(False, "")
    assert pause.is_effective("proj-a") is False


# --- row 174, second half: runs recorded under governance ---

def test_row174_runs_recorded_with_journal(_isolated):
    _template()
    run = runner.start_run("proj-a", "tpl-nightly")
    assert run.state == "RUNNING"
    stored = runner.get_run("proj-a", run.run_id)
    assert stored.run_id == run.run_id
    assert [entry["event"] for entry in runner.get_history("proj-a", run.run_id)]
    assert _isolated["journal"].calls, "run start must notify the journal"
    assert runner.list_runs("proj-a")


def test_start_unknown_template_raises():
    with pytest.raises(AutomationError) as excinfo:
        runner.start_run("proj-a", "tpl-missing")
    assert _code(excinfo) == "TEMPLATE_NOT_FOUND"


def test_start_while_paused_raises():
    _template()
    pause.set_global(True, "drill")
    with pytest.raises(AutomationError) as excinfo:
        runner.start_run("proj-a", "tpl-nightly")
    assert _code(excinfo) == "AUTOMATION_PAUSED"


# --- P5: timer fires launcher; metric fires action; both recorded ---

def _wired_timer(now, catchup="once"):
    _template()
    triggers.register_trigger("trg-t1", "proj-a", kind="TIMER")
    scheduler.register_launcher("lch-1", "proj-a", "tpl-nightly")
    scheduler.register_timer(
        "tmr-1", "proj-a", 60.0, launcher_id="lch-1",
        catchup=catchup, first_due=now,
    )
    return "tmr-1"


def test_p5_timer_fires_launcher_recorded(_isolated):
    now = 1000.0
    _wired_timer(now)
    run = scheduler.fire_timer("tmr-1", now=now)
    assert run is not None and run.state == "RUNNING"
    assert runner.get_run("proj-a", run.run_id).state == "RUNNING"
    assert _isolated["journal"].calls
    assert _isolated["guard"].calls, "launch must check the guard first"
    outcomes = [entry["outcome"] for entry in scheduler.ledger()]
    assert "timer-fired" in outcomes and "launcher-fired" in outcomes


def test_p5_metric_fires_action_recorded(_isolated):
    _template()
    scheduler.register_metric("met-1", "proj-a", 80.0, action="notify")
    run = scheduler.evaluate_metric("met-1", 95.0)
    assert run is not None and run.state == "RUNNING"
    assert runner.get_run("proj-a", run.run_id).state == "RUNNING"
    assert _isolated["journal"].calls
    assert (
        scheduler.ledger()[-1]["outcome"] == "metric-fired"
    )


def test_p5_metric_stop_action_requests_stop(_isolated):
    scheduler.register_metric("met-stop", "proj-a", 90.0, action="stop")
    run = scheduler.evaluate_metric("met-stop", 99.0)
    assert run is not None
    assert _isolated["stopper"].calls == [
        {"project_id": "proj-a", "stopped": True, "reason": "metric met-stop"}
    ]


def test_p5_metric_below_threshold_fires_nothing(_isolated):
    scheduler.register_metric("met-1", "proj-a", 80.0, action="notify")
    assert scheduler.evaluate_metric("met-1", 10.0) is None
    assert runner.list_runs("proj-a") == []
    assert scheduler.ledger()[-1]["outcome"] == "metric-below"


def test_p5_global_pause_stops_timer_launcher_metric():
    now = 1000.0
    _wired_timer(now)
    scheduler.register_metric("met-1", "proj-a", 80.0, action="notify")
    pause.set_global(True, "drill")
    with pytest.raises(AutomationError) as excinfo:
        scheduler.fire_timer("tmr-1", now=now)
    assert _code(excinfo) == "AUTOMATION_PAUSED"
    with pytest.raises(AutomationError) as excinfo:
        scheduler.fire_launcher("lch-1")
    assert _code(excinfo) == "AUTOMATION_PAUSED"
    with pytest.raises(AutomationError) as excinfo:
        scheduler.evaluate_metric("met-1", 95.0)
    assert _code(excinfo) == "AUTOMATION_PAUSED"
    with pytest.raises(AutomationError) as excinfo:
        triggers.fire_trigger("proj-a", "trg-t1")
    assert _code(excinfo) == "AUTOMATION_PAUSED"
    assert runner.list_runs("proj-a") == []


def test_p5_per_project_pause_stops_only_that_project():
    now = 1000.0
    _wired_timer(now)
    _template(project_id="proj-b", template_id="tpl-b")
    scheduler.register_launcher("lch-b", "proj-b", "tpl-b")
    scheduler.register_timer(
        "tmr-b", "proj-b", 60.0, launcher_id="lch-b", first_due=now,
    )
    pause.set_project("proj-a", True)
    with pytest.raises(AutomationError) as excinfo:
        scheduler.fire_timer("tmr-1", now=now)
    assert _code(excinfo) == "AUTOMATION_PAUSED"
    run = scheduler.fire_timer("tmr-b", now=now)
    assert run.state == "RUNNING" and run.project_id == "proj-b"


def test_trigger_fire_records_run(_isolated):
    triggers.register_trigger("trg-1", "proj-a", kind="LAUNCHER")
    run = triggers.fire_trigger("proj-a", "trg-1")
    assert run.state == "RUNNING" and run.trigger_id == "trg-1"
    assert _isolated["journal"].calls


def test_fire_unknown_trigger_raises():
    with pytest.raises(AutomationError) as excinfo:
        triggers.fire_trigger("proj-a", "trg-missing")
    assert _code(excinfo) == "TRIGGER_NOT_FOUND"


def test_launch_active_run_raises():
    _template()
    run = runner.start_run("proj-a", "tpl-nightly")
    with pytest.raises(AutomationError) as excinfo:
        launcher.launch("proj-a", run.run_id)
    assert _code(excinfo) == "AUTOMATION_RUN_ACTIVE"


def test_launch_unknown_run_raises():
    with pytest.raises(AutomationError) as excinfo:
        launcher.launch("proj-a", "run-missing")
    assert _code(excinfo) == "AUTOMATION_RUN_NOT_FOUND"


def test_launch_guard_refusal_blocks(_isolated):
    _template()
    pending = runner.create_pending("proj-a", "tpl-nightly")
    _isolated["guard"].allow = False
    with pytest.raises(AutomationError) as excinfo:
        launcher.launch("proj-a", pending.run_id)
    assert _code(excinfo) == "AUTOMATION_PAUSED"
    assert "guard" in (excinfo.value.detail or "")
    assert runner.get_run("proj-a", pending.run_id).state == "PENDING"


# --- P7: resume after restart within budget and time guards ---

def test_p7_resume_within_guards_after_restart(tmp_path):
    _template()
    started = runner.start_run("proj-a", "tpl-nightly", now=2000.0)
    runner.cancel_run("proj-a", started.run_id, reason="restart")
    run_file = tmp_path / "runs.json"
    runner.save_state(str(run_file))
    runner.reset_state()
    runner.load_state(str(run_file))
    runner.set_budget_hook(lambda project_id: True)
    resumed = runner.resume("proj-a", started.run_id, now=2000.0 + 60.0)
    assert resumed.state == "RUNNING"


def test_p7_launcher_resumes_after_restart(tmp_path):
    _template()
    scheduler.register_launcher("lch-1", "proj-a", "tpl-nightly")
    scheduler.save_state(str(tmp_path / "sched.json"))
    runner.save_state(str(tmp_path / "runs.json"))
    runner.reset_state()
    scheduler.reset_state()
    runner.load_state(str(tmp_path / "runs.json"))
    scheduler.load_state(str(tmp_path / "sched.json"))
    run = scheduler.fire_launcher("lch-1")
    assert run.state == "RUNNING"


def test_p7_resume_budget_guard_refuses():
    _template()
    started = runner.start_run("proj-a", "tpl-nightly", now=2000.0)
    runner.cancel_run("proj-a", started.run_id, reason="restart")
    runner.set_budget_hook(lambda project_id: False)
    with pytest.raises(AutomationError) as excinfo:
        runner.resume("proj-a", started.run_id, now=2000.0 + 60.0)
    assert _code(excinfo) == "AUTOMATION_PAUSED"
    assert "budget" in (excinfo.value.detail or "")


def test_p7_resume_time_guard_refuses():
    _template()
    started = runner.start_run(
        "proj-a", "tpl-nightly", now=2000.0, resume_window_s=10.0
    )
    runner.cancel_run("proj-a", started.run_id, reason="restart")
    with pytest.raises(AutomationError) as excinfo:
        runner.resume("proj-a", started.run_id, now=2000.0 + 3600.0)
    assert _code(excinfo) == "AUTOMATION_PAUSED"
    assert "time" in (excinfo.value.detail or "")


def test_resume_unknown_run_raises():
    with pytest.raises(AutomationError) as excinfo:
        runner.resume("proj-a", "run-missing")
    assert _code(excinfo) == "AUTOMATION_RUN_NOT_FOUND"


# --- M-P3-94: miss catch-up plus restart survival ---

def test_catchup_skip_fires_nothing_and_advances():
    now = 1000.0
    _wired_timer(now - 300.0, catchup="skip")
    assert scheduler.fire_timer("tmr-1", now=now) is None
    assert runner.list_runs("proj-a") == []
    assert scheduler.ledger()[-1]["outcome"] == "catchup-skip"
    assert scheduler.get_timer("tmr-1")["next_due"] == pytest.approx(now + 60.0)


def test_catchup_once_fires_single_run():
    now = 1000.0
    _wired_timer(now - 300.0, catchup="once")
    run = scheduler.fire_timer("tmr-1", now=now)
    assert run is not None and run.state == "RUNNING"
    assert len(runner.list_runs("proj-a")) == 1
    assert scheduler.ledger()[-1]["outcome"] == "catchup-once"


def test_timers_survive_restart(tmp_path):
    now = 1000.0
    _wired_timer(now + 60.0)
    sched_file = tmp_path / "sched.json"
    trig_file = tmp_path / "triggers.json"
    scheduler.save_state(str(sched_file))
    triggers.save_state(str(trig_file))
    scheduler.reset_state()
    triggers.reset_state()
    scheduler.load_state(str(sched_file))
    triggers.load_state(str(trig_file))
    assert scheduler.fire_timer("tmr-1", now=now) is None
    run = scheduler.fire_timer("tmr-1", now=now + 60.0)
    assert run is not None and run.state == "RUNNING"


def test_tick_skips_paused_and_fires_rest():
    now = 1000.0
    _wired_timer(now)
    _template(project_id="proj-b", template_id="tpl-b")
    scheduler.register_launcher("lch-b", "proj-b", "tpl-b")
    scheduler.register_timer(
        "tmr-b", "proj-b", 60.0, launcher_id="lch-b", first_due=now,
    )
    pause.set_project("proj-a", True)
    fired = scheduler.tick_due(now=now)
    assert [run.project_id for run in fired] == ["proj-b"]
    outcomes = [entry["outcome"] for entry in scheduler.ledger()]
    assert "tick-skip" in outcomes


# --- 45B: cancel keeps history and finalizes ---

def test_cancel_keeps_history_and_finalizes(_isolated):
    _template()
    run = runner.start_run("proj-a", "tpl-nightly")
    cancelled = runner.cancel_run("proj-a", run.run_id, reason="user-stop")
    assert cancelled.state == "CANCELLED"
    assert runner.get_run("proj-a", run.run_id).state == "CANCELLED"
    events = [entry["event"] for entry in runner.get_history("proj-a", run.run_id)]
    assert "created" in events and "cancelled:user-stop" in events
    final = runner.get_finalization("proj-a", run.run_id)
    assert final["reason"] == "user-stop" and final["finalized"] is True
    assert _isolated["journal"].calls


def test_cancel_works_while_paused():
    _template()
    run = runner.start_run("proj-a", "tpl-nightly")
    pause.set_global(True, "drill")
    assert runner.cancel_run("proj-a", run.run_id).state == "CANCELLED"


# --- frozen contracts: names, codes and the exact model id ---

def test_realization_map_names_runtime_core():
    assert REALIZATION_MAP["pause.set_global"] == "agent_si.automation.pause.set_global"
    assert REALIZATION_MAP["pause.is_effective"] == "agent_si.automation.pause.is_effective"
    assert REALIZATION_MAP["automation.run.start"] == "agent_si.automation.runner.start_run"
    assert REALIZATION_MAP["automation.trigger.fire"] == "agent_si.automation.triggers.fire_trigger"
    assert REALIZATION_MAP["automation.launch"] == "agent_si.automation.launcher.launch"
    assert REALIZATION_MAP["automation.resume"] == "agent_si.automation.runner.resume"


def test_error_codes_cover_runtime_core():
    for code in (
        "AUTOMATION_PAUSED",
        "AUTOMATION_RUN_NOT_FOUND",
        "AUTOMATION_RUN_ACTIVE",
        "TRIGGER_NOT_FOUND",
        "TEMPLATE_NOT_FOUND",
        "PAUSE_REASON_MISSING",
        "SESSION_TOKEN_MISSING",
        "SESSION_TOKEN_INVALID",
    ):
        assert code in ERROR_CODES


def test_model_id_matches_repo_exact():
    # K08F1: clean-clone fix — compare runner.MODEL_ID with the K02 model id
    # from the in-repo frozen source src/agent_si/assurance/assurance_iface.py:19
    # (K02 sec 2 pin; never a RECORDS read, never a retyped literal).
    from agent_si.assurance.assurance_iface import MODEL_ID as K02_MODEL_ID
    assert runner.MODEL_ID == K02_MODEL_ID


def test_product_sources_stay_clean():
    banned = ("todo", "fixme", "stub", "fake", "tmpdir", "tempfile", "/tmp")
    package = Path(__file__).resolve().parents[2] / "src" / "agent_si" / "automation"
    for name in ("pause.py", "runner.py", "launcher.py", "triggers.py", "scheduler.py"):
        text = (package / name).read_text(encoding="utf-8").lower()
        hits = [word for word in banned if word in text]
        assert not hits, (name, hits)


def test_product_sources_are_crlf():
    # K08F1: clean-clone fix — .gitattributes:4 (*.py text eol=lf) governs LF
    # checkouts, so the CRLF-presence demand is dropped; the no-mixed-or-stray-CR
    # assertion is kept, valid for both LF and CRLF checkouts.
    package = Path(__file__).resolve().parents[2] / "src" / "agent_si" / "automation"
    for name in ("pause.py", "runner.py", "launcher.py", "triggers.py", "scheduler.py"):
        raw = (package / name).read_bytes()
        assert raw.replace(b"\r\n", b"\n").find(b"\r") == -1, name


def test_saved_state_is_plain_json(tmp_path):
    _template()
    runner.start_run("proj-a", "tpl-nightly", now=2000.0)
    run_file = tmp_path / "runs.json"
    runner.save_state(str(run_file))
    payload = json.loads(run_file.read_text(encoding="utf-8"))
    assert payload["schema"] == 1
    assert payload["runs"][0]["project_id"] == "proj-a"
