"""K08R3 watcher backend rows 186 / R-322 / R-325 / R-364-backend / SPEC-21.

REAL behaviour tests over the owning lane modules (no canned verdicts, no
frozen fixture ids, no pre-seeded state). Each row below gets at least one
case with real inputs through the real code path.
"""

import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.append(str(SRC))

import agent_si.watcher.engine as engine
import agent_si.watcher.integrity as integrity
import agent_si.watcher.journal as journal
import agent_si.watcher.presets as presets
import agent_si.watcher.rules as rules
import agent_si.watcher.status as status
from agent_si.watcher.journal import WatcherError


@pytest.fixture(autouse=True)
def _reset_lane_state():
    journal.reset_state()
    integrity.reset_state()
    rules.reset_state()
    engine.reset_state()
    presets.reset_state()
    status.reset_state()
    yield


def _code(excinfo):
    return excinfo.value.code


# --- row 186: fresh project auto-seeds the default (standard) preset ---


def test_186_fresh_project_auto_seeds_standard():
    cards = presets.ensure_seeded("k08r3-seed-1")
    assert cards == ("card-hang", "card-guard")
    assert presets.installed_cards("k08r3-seed-1") == cards
    seeded = journal.list_events("k08r3-seed-1", "SERVICE_STATE")
    assert len(seeded) == 1


def test_186_ensure_seeded_idempotent():
    first = presets.ensure_seeded("k08r3-seed-2")
    second = presets.ensure_seeded("k08r3-seed-2")
    assert first == second
    assert len(journal.list_events("k08r3-seed-2", "SERVICE_STATE")) == 1


def test_186_apply_seeds_then_installs_requested():
    cards = presets.apply("k08r3-seed-3", "strict")
    assert cards == ("card-hang", "card-guard", "card-tamper")
    assert presets.installed_cards("k08r3-seed-3") == cards
    assert len(journal.list_events("k08r3-seed-3", "SERVICE_STATE")) == 1


def test_186_installed_cards_isolated_per_project():
    presets.ensure_seeded("k08r3-seed-4a")
    assert presets.installed_cards("k08r3-seed-4b") == ()
    presets.apply("k08r3-seed-4b", "cautious")
    assert presets.installed_cards("k08r3-seed-4a") == ("card-hang", "card-guard")
    assert presets.installed_cards("k08r3-seed-4b") == ("card-hang",)


def test_186_unknown_preset_raises_without_side_effects():
    with pytest.raises(WatcherError) as excinfo:
        presets.apply("k08r3-seed-5", "no-such-preset")
    assert _code(excinfo) == "PRESET_NOT_FOUND"
    assert presets.installed_cards("k08r3-seed-5") == ()
    assert journal.list_events("k08r3-seed-5") == ()


# --- row R-322: untouchable + supervised restart journaled ---


def test_r322_supervised_restart_journaled():
    receipt = engine.supervised_restart("k08r3-restart-1", "supervisor-7")
    assert receipt.accepted is True
    assert receipt.project_id == "k08r3-restart-1"
    assert receipt.supervisor_ref == "supervisor-7"
    service_rows = journal.list_events("k08r3-restart-1", "SERVICE_STATE")
    assert len(service_rows) == 1
    assert receipt.journal_entry_id == service_rows[0].entry_id
    assert journal.list_events("k08r3-restart-1", "STOP_ALL") == ()


def test_r322_empty_supervisor_ref_refused_and_journaled():
    with pytest.raises(WatcherError) as excinfo:
        engine.supervised_restart("k08r3-restart-2", "")
    assert _code(excinfo) == "STOP_REASON_MISSING"
    assert len(journal.list_events("k08r3-restart-2", "SERVICE_STATE")) == 1


def test_r322_restart_blocked_on_integrity_divergence():
    journal.append_event("k08r3-restart-3", "watcher", "SERVICE_STATE", "boot", ())
    integrity.seal("k08r3-restart-3")
    journal._ROWS["k08r3-restart-3"][0]["summary"] = "edited by attacker"
    with pytest.raises(WatcherError) as excinfo:
        engine.supervised_restart("k08r3-restart-3", "supervisor-7")
    assert _code(excinfo) == "GOVERNANCE_MISMATCH"


# --- row R-325: watcher picks script + params per rule ---


def test_r325_resolve_action_derived_from_card_fields():
    action = engine.resolve_action("k08r3-action-1", "rule-tamper")
    card = rules.describe("rule-tamper")
    assert action.card_id == "rule-tamper"
    assert card.area in action.script
    assert action.script != ""
    assert action.params == ("--model", card.model, "--hang-minutes", str(card.hang_minutes))


def test_r325_resolve_action_unknown_card_raises():
    with pytest.raises(WatcherError) as excinfo:
        engine.resolve_action("k08r3-action-2", "rule-missing")
    assert _code(excinfo) == "RULE_NOT_FOUND"


def test_r325_decide_signature_and_behaviour_preserved():
    decision = engine.decide(
        "k08r3-action-3", "rule-guard", "scripts/custom.py", ("--x", "1")
    )
    assert decision.rule_id == "rule-guard"
    assert isinstance(decision.verdict, rules.WatchVerdict)
    assert engine.last_choice("k08r3-action-3") == (
        "rule-guard", "scripts/custom.py", ("--x", "1"),
    )


# --- row R-364 backend: own area + model + 20-min hang default, derived dues ---


def test_r364_cards_carry_area_model_and_hang_default():
    assert set(rules.RULES) == {"rule-tamper", "rule-guard"}
    for card in rules.RULES.values():
        assert card.area != ""
        assert card.model in ("local", "API", "OFF")
        assert card.hang_minutes == 20


def test_r364_due_cards_derive_from_registry():
    assert engine.DUE_CARDS == tuple(rules.RULES)
    assert "rule-tamper" in engine.DUE_CARDS
    assert "rule-guard" in engine.DUE_CARDS
    tick = engine.tick("k08r3-due-1")
    assert tick.fired == engine.DUE_CARDS


def test_r364_tamper_verdict_follows_stored_facts():
    journal.append_event(
        "k08r3-tamper-1", "watcher", "SERVICE_STATE", "boot", ()
    )
    fresh = rules.evaluate("k08r3-tamper-1", "rule-tamper")
    assert fresh.verdict == rules.WatchVerdict.ALLOW
    journal.append_event(
        "k08r3-tamper-1", "agent-x", "TAMPER_ATTEMPT", "edited log", ("ref-1",)
    )
    flagged = rules.evaluate("k08r3-tamper-1", "rule-tamper")
    assert flagged.verdict == rules.WatchVerdict.BLOCK
    assert flagged.journal_entry_id != fresh.journal_entry_id


def test_r364_guard_blocks_on_guard_facts():
    journal.append_event(
        "k08r3-guard-1", "watcher", "SERVICE_STATE", "boot", ()
    )
    fresh = rules.evaluate("k08r3-guard-1", "rule-guard")
    assert fresh.verdict == rules.WatchVerdict.BLOCK
    journal.append_event(
        "k08r3-guard-1", "agent-x", "GUARD_BLOCK", "escape", ("path-1",)
    )
    flagged = rules.evaluate("k08r3-guard-1", "rule-guard")
    assert flagged.verdict == rules.WatchVerdict.BLOCK


def test_r364_stale_heartbeat_escalates():
    rows = (
        journal.StoredRow(
            kind="SERVICE_STATE", source="watcher", summary="old",
            refs=(), entry_id="evt-0001", timestamp="2026-01-01T00:00:00Z",
        ),
    )
    card = rules.describe("rule-tamper")
    assert rules.verdict_for(card, rows, rules._utcnow()) == rules.WatchVerdict.ESCALATE


# --- row SPEC-21: REAL hash-pinned integrity ---


def test_spec21_seal_and_verify_ok_with_append_growth():
    journal.append_event("k08r3-pin-1", "watcher", "SERVICE_STATE", "boot", ())
    integrity.seal("k08r3-pin-1")
    report = integrity.verify("k08r3-pin-1")
    assert report.ok is True
    assert report.mismatched_refs == ()
    journal.append_event(
        "k08r3-pin-1", "watcher", "WATCH_DECISION", "rule-tamper", ("rule-tamper",)
    )
    grown = integrity.verify("k08r3-pin-1")
    assert grown.ok is True


def test_spec21_tampered_row_raises_with_refs():
    journal.append_event(
        "k08r3-pin-2", "watcher", "SERVICE_STATE", "boot", ("ref-boot",)
    )
    integrity.seal("k08r3-pin-2")
    journal._ROWS["k08r3-pin-2"][0]["summary"] = "rewritten by attacker"
    with pytest.raises(WatcherError) as excinfo:
        integrity.verify("k08r3-pin-2")
    assert _code(excinfo) == "GOVERNANCE_MISMATCH"
    assert "ref-boot" in excinfo.value.detail


def test_spec21_removed_row_raises():
    journal.append_event(
        "k08r3-pin-3", "watcher", "SERVICE_STATE", "boot", ("ref-boot",)
    )
    integrity.seal("k08r3-pin-3")
    journal._ROWS["k08r3-pin-3"].pop()
    with pytest.raises(WatcherError) as excinfo:
        integrity.verify("k08r3-pin-3")
    assert _code(excinfo) == "GOVERNANCE_MISMATCH"


def test_spec21_no_preseeded_entries_and_compat_shim():
    assert integrity.verify("k08r3-fresh-9").ok is True
    integrity.register_mismatch("k08r3-compat-1", ("ref-a",))
    with pytest.raises(WatcherError) as excinfo:
        integrity.verify("k08r3-compat-1")
    assert _code(excinfo) == "GOVERNANCE_MISMATCH"
    integrity.reset_state()
    assert integrity.verify("k08r3-compat-1").ok is True
