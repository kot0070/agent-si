"""K08OPEN7 behaviour: engine tick+decide+resolve via the served watcher interface.

Row R-335: tick plus decide run behind the served watcher interface: the
test resolves the owning lane through agent_si.watcher.interface
REALIZATION_MAP (watcher.engine.tick, watcher.engine.decide), never
importing the engine lane for those two calls; an idle firing journals
nothing while an abnormal firing records its WATCH_DECISION row;
resolve_action carries restart-receipt support.
Row R-336: resolved actions are recorded plus pausable: resolve records
one row, a paused action refuses with AUTOMATION_PAUSED until resumed.
Row R-337: per-service usage stays queryable from stored facts only
(honest empty state with a next step, never invented numbers); protected
paths stay refused through the served guard (decide with an escaping
script is refused and the block is journaled).
Loopback TEST data only. No product doubles.
"""

import importlib
import os
import sys

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from fastapi.testclient import TestClient

from agent_si.backend.app import create_app
from agent_si.watcher import guard as guard_home
from agent_si.watcher import interface as w_iface
from agent_si.watcher import journal as journal_store
from agent_si.watcher import rules as rule_cards
from agent_si.watcher.journal import WatcherError

TESTID = "k08open6-timers"

TEST_TOKEN = "k08open6-token"
PROJ_TICK = "proj-k08open6-tick"
PROJ_ACTION = "proj-k08open6-action"
PROJ_USAGE = "proj-k08open6-usage"
CARD = "rule-tamper"


def _settings():
    return {"testing": True, "ui_session_token": TEST_TOKEN}


def _auth():
    return {"x-ui-session-token": TEST_TOKEN}


def _client():
    return TestClient(create_app(_settings()))


def _entry(func_name):
    """Resolve one served watcher entry through REALIZATION_MAP."""
    from agent_si.watcher import engine as engine_home

    dotted = w_iface.REALIZATION_MAP[func_name]
    module_name, _, attr = dotted.rpartition(".")
    module = importlib.import_module(module_name)
    assert module is engine_home
    return getattr(module, attr)


def setup_function(_func):
    from agent_si.watcher import engine as engine_home

    journal_store.reset_state()
    rule_cards.reset_state()
    engine_home.reset_state()


def teardown_function(_func):
    from agent_si.watcher import engine as engine_home

    journal_store.reset_state()
    rule_cards.reset_state()
    engine_home.reset_state()


def test_r335_tick_decide_served_interface():
    """Row R-335 [k08open6-timers]: tick+decide behind the served interface."""
    assert TESTID == "k08open6-timers"
    from agent_si.watcher import engine as engine_home

    tick = _entry("watcher.engine.tick")
    decide = _entry("watcher.engine.decide")

    fired = tick(PROJ_TICK)
    assert isinstance(fired, engine_home.EngineTick)
    assert fired.project_id == PROJ_TICK
    assert isinstance(fired.fired, tuple)
    assert set(fired.fired) == set(rule_cards.RULES)
    assert fired.checked_at != ""
    # Idle tick: both cards rest on their base verdicts with no trigger
    # facts, so the normal verdicts journal nothing (no row, no call).
    assert journal_store.stored_rows(PROJ_TICK, "WATCH_DECISION") == ()
    journal_store.append_event(
        PROJ_TICK, "agent-x", "TAMPER_ATTEMPT", "tick probe",
        ("ref-k08open6-tick",))
    again = tick(PROJ_TICK)
    assert set(again.fired) == set(rule_cards.RULES)
    watch_rows = journal_store.stored_rows(PROJ_TICK, "WATCH_DECISION")
    assert len(watch_rows) == 1
    assert "rule-tamper" in watch_rows[0].summary

    decision = decide(PROJ_TICK, CARD, "scripts/tamper_check.py", ("--x",))
    assert isinstance(decision, rule_cards.WatchDecision)
    assert decision.rule_id == CARD
    # One condition, one alert (FXZERO item 4): the tick above already
    # journaled this BLOCK, so the identical decide adds no second row.
    assert decision.journal_entry_id == ""
    assert len(journal_store.stored_rows(PROJ_TICK, "WATCH_DECISION")) == 1
    assert engine_home.last_choice(PROJ_TICK) == (
        CARD, "scripts/tamper_check.py", ("--x",),
    )

    resolved = engine_home.resolve_action(PROJ_TICK, CARD)
    assert isinstance(resolved, engine_home.CardAction)
    assert resolved.card_id == CARD
    assert resolved.script != ""
    assert isinstance(resolved.params, tuple)

    receipt = engine_home.supervised_restart(PROJ_TICK, "sup-k08open6")
    assert receipt.accepted is True
    assert receipt.journal_entry_id != ""

    client = _client()
    evaluated = client.post(
        "/api/v1/watcher/rules/%s/evaluate" % CARD,
        json={"project_id": PROJ_TICK},
        headers=_auth(),
    )
    assert evaluated.status_code == 200, evaluated.text
    journal = client.get(
        "/api/v1/watcher/journal",
        params={"project_id": PROJ_TICK, "kind": "WATCH_DECISION"},
    )
    assert journal.status_code == 200, journal.text


def test_r336_recorded_pausable_actions():
    """Row R-336 [k08open6-timers]: resolved actions recorded + pausable."""
    assert TESTID == "k08open6-timers"
    from agent_si.watcher import engine as engine_home

    resolved = engine_home.resolve_action(PROJ_ACTION, CARD)
    recorded = engine_home.recorded_actions(PROJ_ACTION)
    assert resolved in tuple(recorded)
    assert any(
        CARD in row.refs for row in journal_store.stored_rows(PROJ_ACTION)
    )

    paused = engine_home.pause_action(PROJ_ACTION, CARD, True, "k08open6 drill")
    assert paused.paused is True
    try:
        engine_home.resolve_action(PROJ_ACTION, CARD)
    except WatcherError as err:
        assert err.code == "AUTOMATION_PAUSED"
    else:
        raise AssertionError("paused action resolved")

    resumed = engine_home.pause_action(PROJ_ACTION, CARD, False, "")
    assert resumed.paused is False
    again = engine_home.resolve_action(PROJ_ACTION, CARD)
    assert again.card_id == CARD


def test_r337_usage_queryable_protected_refused():
    """Row R-337 [k08open6-timers]: usage served, protected paths refused."""
    assert TESTID == "k08open6-timers"
    from agent_si.watcher import engine as engine_home

    usage = engine_home.service_usage(PROJ_USAGE)
    assert usage.project_id == PROJ_USAGE
    assert tuple(usage.services) == ()
    assert usage.next_step != ""

    refused = guard_home.check_escape(PROJ_USAGE, "../escape", "/srv/app")
    assert refused.allowed is False
    assert any(
        row.kind == "GUARD_BLOCK"
        for row in journal_store.stored_rows(PROJ_USAGE)
    )

    decide = _entry("watcher.engine.decide")
    try:
        decide(PROJ_USAGE, CARD, "../escape.py", ())
    except WatcherError:
        pass
    else:
        raise AssertionError("protected script decided")
    assert any(
        row.kind == "GUARD_BLOCK"
        for row in journal_store.stored_rows(PROJ_USAGE)
    )
