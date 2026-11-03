"""FXAUTO RED: no-code rule builder + governed run history + approvals.

Behaviour contract for src/agent_si/automation/rules.py + actions.py
(new lane-internal modules; the frozen interface is untouched):
- create/list/on-off rules bound to scheduler rows (timer/launcher/trigger,
  metric/trigger, event trigger);
- Run now always yields a recorded run + executes the DO action;
- due timers fire on tick; missed fires follow skip/run-once;
- global/per-project pause refuses with AUTOMATION_PAUSED;
- strong actions wait for approval; approving pause-project pauses for real;
- rules + approvals + results survive save/load (restart);
- plan templates: five new ids, plan-first order, instantiate+materialize;
- list_triggers(project_id) exists on the triggers lane.
"""
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import agent_si.automation.interface as auto_iface
import agent_si.context_keeper.interface as ck_iface  # noqa: F401
from agent_si.automation import pause, runner, scheduler, templates, triggers


def _fresh():
    for lane in (pause, runner, scheduler, triggers):
        lane.reset_state()


def _rules():
    import agent_si.automation.rules as rules
    import agent_si.automation.actions as actions
    return rules, actions


@pytest.fixture()
def env(tmp_path):
    _fresh()
    rules, actions = _rules()
    rules.reset_state()
    from agent_si.context_keeper import checkpoints as ckpt_home
    store = ckpt_home.Checkpoints()
    journal = []

    def _hook(*args, **kwargs):
        journal.append((args, kwargs))

    rules.set_context(
        {
            "checkpoints": store,
            "journal": _hook,
            "keeper_dir": str(tmp_path / "keeper"),
        }
    )
    yield rules, actions, journal, store


def _schedule(env, **kw):
    rules, _actions, _journal, _store = env
    params = {
        "project_id": "proj-a",
        "name": "half-hour checkpoint",
        "when_kind": "schedule",
        "when_detail": "every-30m",
        "do": "checkpoint",
    }
    params.update(kw)
    return rules.create_rule(**params)


def test_create_schedule_rule_binds_timer_launcher_trigger(env):
    rules, _actions, _journal, _store = env
    rule = _schedule(env)
    assert rule["rule_id"].startswith("rule-")
    assert rule["enabled"] is True
    timer = scheduler.get_timer(rule["timer_id"])
    assert timer["interval_s"] == 1800.0
    assert timer["catchup"] == "once"
    got = triggers.get_trigger("proj-a", rule["rule_id"])
    assert got["kind"] == "TIMER"


def test_create_validates_plain_errors(env):
    rules, _actions, _journal, _store = env
    with pytest.raises(ValueError):
        _schedule(env, name="")
    with pytest.raises(ValueError):
        _schedule(env, if_text="x" * 501)
    with pytest.raises(ValueError):
        _schedule(env, when_detail="every-5m")
    with pytest.raises(ValueError):
        _schedule(env, do="launch-rockets")
    with pytest.raises(ValueError):
        _schedule(env, miss="sometimes")


def test_run_now_records_run_executes_checkpoint(env):
    rules, actions, journal, store = env
    rule = _schedule(env)
    fired = rules.fire_rule("proj-a", rule["rule_id"])
    run = fired["run"]
    assert run["state"] == "RUNNING"
    assert fired["result"]["key"] == "fxauto.results.checkpoint"
    assert store.latest_for_project("proj-a") is not None
    history = runner.get_history("proj-a", run["run_id"])
    assert any("checkpoint" in entry["event"] for entry in history)


def test_run_now_uses_templates_checkpoint_every_30m(env):
    rules, actions, journal, store = env
    draft = templates.builder_draft("tpl-checkpoint-30m")
    rule = rules.create_rule(
        project_id="proj-a",
        name="from template",
        when_kind=draft["when_kind"],
        when_detail=draft["when_detail"],
        do=draft["do"],
    )
    fired = rules.fire_rule("proj-a", rule["rule_id"])
    assert store.latest_for_project("proj-a") is not None
    assert fired["run"]["state"] == "RUNNING"
    assert fired["result"]["key"] == "fxauto.results.checkpoint"


def test_due_timer_fires_on_tick(env):
    rules, _actions, _journal, store = env
    rule = _schedule(env, now=0.0)
    out = rules.tick(now=10_000.0)
    assert len(out) == 1
    assert store.latest_for_project("proj-a") is not None


def test_missed_skip_advances_without_firing(env):
    rules, _actions, _journal, store = env
    rule = _schedule(env, miss="skip")
    out = rules.tick(now=100_000.0)
    assert out == []
    assert store.latest_for_project("proj-a") is None


def test_off_rule_fires_nothing_on_tick_and_refuses_run_now(env):
    rules, _actions, _journal, store = env
    rule = _schedule(env)
    rules.set_enabled("proj-a", rule["rule_id"], False)
    assert rules.tick(now=10_000.0) == []
    with pytest.raises(auto_iface.AutomationError) as excinfo:
        rules.fire_rule("proj-a", rule["rule_id"])
    assert excinfo.value.code == "AUTOMATION_PAUSED"
    assert "turned off" in excinfo.value.detail


def test_global_pause_refuses_run_now(env):
    rules, _actions, _journal, _store = env
    rule = _schedule(env)
    pause.set_global(True, "hd stop")
    try:
        with pytest.raises(auto_iface.AutomationError) as excinfo:
            rules.fire_rule("proj-a", rule["rule_id"])
        assert excinfo.value.code == "AUTOMATION_PAUSED"
    finally:
        pause.set_global(False, "")


def test_per_project_pause_refuses_run_now(env):
    rules, _actions, _journal, _store = env
    rule = _schedule(env)
    pause.set_project("proj-a", True)
    try:
        with pytest.raises(auto_iface.AutomationError) as excinfo:
            rules.fire_rule("proj-a", rule["rule_id"])
        assert excinfo.value.code == "AUTOMATION_PAUSED"
    finally:
        pause.set_project("proj-a", False)


def test_strong_action_waits_for_approval_then_pauses(env):
    rules, _actions, journal, _store = env
    rule = _schedule(env, do="pause-project", when_detail="every-3h")
    fired = rules.fire_rule("proj-a", rule["rule_id"])
    assert fired["approval"] is not None
    assert fired["result"]["key"] == "fxauto.results.waitingApproval"
    assert pause.is_effective("proj-a") is False
    pending = rules.list_approvals("proj-a")
    assert len(pending) == 1
    decided = rules.decide_approval(
        "proj-a", pending[0]["approval_id"], True
    )
    assert pause.is_effective("proj-a") is True
    assert decided["result"]["key"] == "fxauto.results.paused"


def test_metric_rule_fires_on_forced_reading(env):
    rules, _actions, _journal, store = env
    rule = rules.create_rule(
        project_id="proj-a",
        name="budget watch",
        when_kind="metric",
        when_detail="budget-90",
        do="notify",
    )
    fired = rules.fire_rule("proj-a", rule["rule_id"])
    assert fired["run"]["state"] == "RUNNING"
    assert fired["result"]["key"] == "fxauto.results.notified"


def test_metric_tick_uses_live_source(env):
    rules, _actions, _journal, _store = env
    rule = rules.create_rule(
        project_id="proj-a",
        name="budget watch",
        when_kind="metric",
        when_detail="budget-90",
        do="notify",
    )
    rules.set_metric_source("budget-90", lambda project_id: 0.95)
    out = rules.tick()
    assert len(out) == 1
    rules.set_metric_source("budget-90", lambda project_id: 0.10)
    assert rules.tick() == []


def test_app_started_event_fires_on_boot_event(env):
    rules, _actions, _journal, store = env
    rules.create_rule(
        project_id="proj-a",
        name="resume after restart",
        when_kind="event",
        when_detail="app-started",
        do="checkpoint",
    )
    out = rules.fire_event("proj-a", "app-started")
    assert len(out) == 1
    assert store.latest_for_project("proj-a") is not None
    assert rules.fire_event("proj-a", "audit-finished") == []


def test_rules_survive_save_load(tmp_path, env):
    rules, _actions, _journal, store = env
    rule = _schedule(env)
    rules.set_state_path(str(tmp_path / "rules.json"))
    rules.save_state(str(tmp_path / "rules.json"))
    rules.reset_state()
    _fresh()
    rules.set_context(
        {
            "checkpoints": store,
            "journal": lambda *a, **k: None,
            "keeper_dir": None,
        }
    )
    rules.load_state(str(tmp_path / "rules.json"))
    kept = rules.get_rule("proj-a", rule["rule_id"])
    assert kept["enabled"] is True
    assert kept["name"] == "half-hour checkpoint"
    fired = rules.fire_rule("proj-a", rule["rule_id"])
    assert fired["run"]["state"] == "RUNNING"


def test_run_history_lists_rule_state_plain_result(env):
    rules, _actions, _journal, _store = env
    rule = _schedule(env)
    fired = rules.fire_rule("proj-a", rule["rule_id"])
    rows = rules.run_history("proj-a")
    assert len(rows) == 1
    row = rows[0]
    assert row["rule"] == "half-hour checkpoint"
    assert row["state"] == "Running"
    assert isinstance(row["result"], dict) and row["result"]["key"] != ""
    assert "AUTOMATION" not in row["result"]["key"]
    assert row["run_id"] == fired["run"]["run_id"]


def test_list_triggers_for_project(env):
    _rules, _actions, _journal, _store = env
    rule = _schedule(env)
    rows = triggers.list_triggers("proj-a")
    assert [row["trigger_id"] for row in rows] == [rule["rule_id"]]


def test_plan_templates_first_instantiate_materialize():
    ids = templates.list_templates()
    assert ids[:5] == templates.PLAN_TEMPLATE_IDS
    assert set(ids) >= set(templates.BUILTIN_TEMPLATE_IDS)
    for template_id in templates.PLAN_TEMPLATE_IDS:
        template = templates.instantiate("proj-a", template_id)
        assert template.template_id == template_id
        plan = templates.materialize("proj-a", template_id)
        for step in plan["steps"]:
            assert step["action"] in templates.ACTION_CATALOG
    assert templates.BUILTIN_TEMPLATE_IDS == (
        "tpl-nightly",
        "tpl-healthcheck",
        "tpl-container-audit",
        "tpl-usage-report",
        "tpl-watch-sweep",
        "tpl-outage-drill",
    )
