"""Lane B coder B1: team-card tests (R-301 contexts + facts-named record).

RED->GREEN: written first against empty stubs, then implemented to GREEN.
Loads the module by file path (stdlib importlib only, no package install).
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TEAMCARD_PATH = ROOT / "src" / "agent_si" / "backend" / "orchestration" / "teamcard.py"


def load_teamcard():
    spec = importlib.util.spec_from_file_location("b1_teamcard", TEAMCARD_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["b1_teamcard"] = module
    spec.loader.exec_module(module)
    return module


tc = load_teamcard()

MODEL_ID = "meta/muse-spark-1.3-contributor"


def make_card(provider="acme", facts=None, budget=None, limits=None):
    return tc.build_team_card(
        provider=provider,
        model_kb_facts=facts if facts is not None else {"ctx": "128k"},
        budget_left=budget if budget is not None else {"units": 100},
        limits=limits if limits is not None else {"max_agents": 4},
    )


def test_model_id_exact():
    assert tc.MODEL_ID == MODEL_ID


def test_team_card_shape():
    card = make_card()
    assert card.provider == "acme"
    assert card.model == MODEL_ID
    assert isinstance(card.model_kb_facts, dict)
    assert card.budget_left == {"units": 100}
    assert card.limits == {"max_agents": 4}


def test_team_card_rejects_wrong_model():
    try:
        tc.build_team_card("acme", {}, {}, {}, model="other/model-x")
    except ValueError as exc:
        assert "model" in str(exc).lower()
    else:
        raise AssertionError("wrong model id must be refused")


def test_director_context_sees_managers_and_workers():
    mgr = make_card(provider="m1p")
    wrk = make_card(provider="w1p")
    ctx = tc.director_context({"m1": mgr}, {"m1": [wrk]})
    assert ctx["managers"]["m1"].provider == "m1p"
    assert ctx["workers"]["m1"][0].provider == "w1p"


def test_manager_context_sees_own_model_and_workers():
    own = make_card(provider="own")
    wrk = make_card(provider="w")
    ctx = tc.manager_context(own, [wrk])
    assert ctx["own"].model == MODEL_ID
    assert [w.provider for w in ctx["workers"]] == ["w"]


def test_worker_context_has_no_team_card():
    assert tc.worker_context() == {}


def test_decomposition_small_part_names_cheap_fact():
    rec = tc.record_decomposition("p-small", size_units=2)
    assert "cheap-models-for-small-parts" in rec.facts_used
    assert "part-size-vs-model" in rec.facts_used
    assert rec.route == "cheap-small-part"


def test_decomposition_long_context_names_routing_fact():
    rec = tc.record_decomposition("p-big", size_units=200, needs_long_context=True)
    assert "long-context-routing" in rec.facts_used
    assert "part-size-vs-model" in rec.facts_used
    assert rec.route == "long-context"


def test_decomposition_standard_part_names_size_fact():
    rec = tc.record_decomposition("p-mid", size_units=20)
    assert "part-size-vs-model" in rec.facts_used
    assert rec.route == "standard"


def test_decomposition_uses_artifact_ref_not_inline():
    rec = tc.record_decomposition("p-small", size_units=2)
    assert rec.artifact_ref.startswith("ARTIFACT_REF:")
    assert "p-small" in rec.artifact_ref


def test_config_breaking_change_refused_without_mutation():
    store = tc.TeamConfigStore()
    before = dict(store.config)
    rows_before = len(store.log.rows)
    outcome = tc.apply_team_config_change(
        store, "kill audit", "test", "tester", {"auditor": "worker", "worker": "worker"}
    )
    assert outcome.accepted is False
    assert outcome.reason != ""
    assert outcome.row is None
    assert store.config == before
    assert len(store.log.rows) == rows_before


def test_config_over_budget_refused():
    store = tc.TeamConfigStore()
    outcome = tc.apply_team_config_change(
        store, "spend", "test", "tester", {"cost": 10**9}
    )
    assert outcome.accepted is False
    assert "budget" in outcome.reason.lower()


def test_config_over_cap_refused():
    store = tc.TeamConfigStore()
    outcome = tc.apply_team_config_change(
        store, "flood", "test", "tester", {"agents": 10**6}
    )
    assert outcome.accepted is False
    assert "cap" in outcome.reason.lower()


def test_config_accepted_persists_one_decision_row():
    store = tc.TeamConfigStore()
    outcome = tc.apply_team_config_change(
        store, "raise cap use", "need room", "tester", {"agents": 2}
    )
    assert outcome.accepted is True
    row = outcome.row
    assert row is not None
    assert (row.decision_id, row.scope, row.statement, row.reason, row.authority) == (
        row.decision_id,
        "team-config",
        "raise cap use",
        "need room",
        "tester",
    )
    assert row.created_at != ""
    assert len(store.log.rows) == 1
    assert store.config["agents"] == 2


def test_decision_ids_unique_per_scope_sequence():
    log = tc.DecisionLog()
    first = log.append("s", "one", "r", "a", "2026-10-26T00:00:00Z")
    second = log.append("s", "two", "r", "a", "2026-10-26T00:00:00Z")
    assert first.decision_id != second.decision_id
    assert first.decision_id.startswith("s-")


def test_surfacing_probe_rejection_reaches_caller_with_reason():
    store = tc.TeamConfigStore()
    outcome = tc.apply_team_config_change(
        store, "kill audit", "test", "tester", {"auditor": "worker", "worker": "worker"}
    )
    surfaced = tc.surface_rejection(outcome)
    assert outcome.reason in surfaced
    assert surfaced != ""


def test_stronger_audit_model_only_when_needed_and_logged():
    log = []
    low = tc.select_audit_model("p-low", "low", log)
    high = tc.select_audit_model("p-high", "high", log)
    assert low.strength == "standard"
    assert high.strength == "strong"
    assert low.model == MODEL_ID
    assert high.model == MODEL_ID
    assert [entry.part_id for entry in log] == ["p-low", "p-high"]
    assert high.reason != ""


def test_register_verbatim_statuses():
    baseline = {"e1": "alpha"}
    negations = {"e1": "NOT alpha"}
    assert tc.register_verbatim("e1", "alpha", baseline)["status"] == "PRESERVED"
    assert tc.register_verbatim("e1", "beta", baseline)["status"] == "CHANGED"
    assert tc.register_verbatim("e9", "alpha", baseline)["status"] == "MISSING"
    assert tc.register_verbatim("e1", "NOT alpha", baseline, negations)["status"] == "CONTRADICTED"


def test_records_use_compact_english():
    rec = tc.record_decomposition("p-small", size_units=2)
    assert tc.is_compact_english(rec.reason)
    assert tc.is_compact_english(tc.surface_rejection(
        tc.apply_team_config_change(
            tc.TeamConfigStore(), "x", "y", "z", {"agents": 10**6}
        )
    ))


def test_secret_ref_never_stores_raw_secret():
    card = tc.build_team_card("acme", {}, {"units": 5}, {}, budget_secret="RAW-SECRET-XYZ")
    assert "RAW-SECRET-XYZ" not in repr(card.budget_left)
    assert card.budget_left["secret_ref"]["secret_ref"] == "budget-store"
