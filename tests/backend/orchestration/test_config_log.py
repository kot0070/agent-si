import copy
import os
import sys

sys.path.insert(
    0,
    os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
    ),
)

from agent_si.backend.orchestration import delta as dl

MODEL = "meta/muse-spark-1.3-contributor"


def fresh_config(**extra):
    cfg = {
        "budget_left": 100.0,
        "auditor": "aud-1",
        "worker": "work-1",
        "independent_audit": True,
        "model": MODEL,
        "known_nodes": ["n1", "n2"],
        "active_chain": [],
        "claimed_scopes": ["s-claimed"],
        "max_parts": 4,
    }
    cfg.update(extra)
    return cfg


def test_accepted_persists_exactly_one_decision_row():
    config = fresh_config()
    log: list = []
    before = copy.deepcopy(config)
    out = dl.apply_config_change(
        config,
        log,
        "manifest",
        "raise limit",
        "need capacity",
        "director",
        {"cost": 10.0},
    )
    assert out == {
        "applied": True,
        "reason": "applied",
        "decision_ref": "manifest-0001",
    }
    assert len(log) == 1
    row = log[0]
    assert row["decision_id"] == "manifest-0001"
    assert row["scope"] == "manifest"
    assert row["statement"] == "raise limit"
    assert row["reason"] == "need capacity"
    assert row["authority"] == "director"
    assert isinstance(row["created_at"], str) and row["created_at"] != ""
    assert set(row.keys()) == {
        "decision_id",
        "scope",
        "statement",
        "reason",
        "authority",
        "created_at",
    }
    assert config["budget_left"] == before["budget_left"] - 10.0


def test_unique_ids_across_two_applies():
    config = fresh_config()
    log: list = []
    first = dl.apply_config_change(
        config, log, "manifest", "first", "r1", "director", {"cost": 5.0}
    )
    second = dl.apply_config_change(
        config, log, "manifest", "second", "r2", "director", {"cost": 5.0}
    )
    assert first["applied"] and second["applied"]
    assert first["decision_ref"] == "manifest-0001"
    assert second["decision_ref"] == "manifest-0002"
    assert log[0]["decision_id"] != log[1]["decision_id"]
    assert len(log) == 2


def _assert_rejected(config, log, out, before_config, before_len):
    assert out["applied"] is False
    assert out["decision_ref"] is None
    assert isinstance(out["reason"], str) and out["reason"] != ""
    assert config == before_config
    assert len(log) == before_len


def test_reject_audit_independence():
    config = fresh_config()
    log: list = []
    before = copy.deepcopy(config)
    patch = {"auditor": "work-1", "independent_audit": False}
    ok, reason = dl.validate_config_change(patch, config)
    assert ok is False and "AUDIT_INDEPENDENCE_REJECTED" in reason
    out = dl.apply_config_change(
        config, log, "manifest", "s", "r", "director", patch
    )
    _assert_rejected(config, log, out, before, 0)
    assert "AUDIT_INDEPENDENCE_REJECTED" in out["reason"]


def test_reject_budget():
    config = fresh_config(budget_left=10.0)
    log: list = []
    before = copy.deepcopy(config)
    patch = {"cost": 999.0}
    ok, reason = dl.validate_config_change(patch, config)
    assert ok is False and "BUDGET_CAPPED" in reason
    out = dl.apply_config_change(
        config, log, "manifest", "s", "r", "director", patch
    )
    _assert_rejected(config, log, out, before, 0)
    assert "BUDGET_CAPPED" in out["reason"]


def test_reject_caps():
    config = fresh_config()
    log: list = []
    before = copy.deepcopy(config)
    patch = {"max_parts": 0}
    ok, reason = dl.validate_config_change(patch, config)
    assert ok is False and "POLICY_CONFLICT" in reason
    out = dl.apply_config_change(
        config, log, "manifest", "s", "r", "director", patch
    )
    _assert_rejected(config, log, out, before, 0)
    assert "POLICY_CONFLICT" in out["reason"]


def test_reject_unknown_nodes():
    config = fresh_config()
    log: list = []
    before = copy.deepcopy(config)
    patch = {"active_chain": ["n1", "ghost"]}
    ok, reason = dl.validate_config_change(patch, config)
    assert ok is False and "POLICY_CONFLICT" in reason
    out = dl.apply_config_change(
        config, log, "manifest", "s", "r", "director", patch
    )
    _assert_rejected(config, log, out, before, 0)
    assert "POLICY_CONFLICT" in out["reason"]


def test_reject_scope_overlap():
    config = fresh_config()
    log: list = []
    before = copy.deepcopy(config)
    patch = {"scope": "s-claimed"}
    ok, reason = dl.validate_config_change(patch, config)
    assert ok is False and "REJECTED_SCOPE_OVERLAP" in reason
    out = dl.apply_config_change(
        config, log, "manifest", "s", "r", "director", patch
    )
    _assert_rejected(config, log, out, before, 0)
    assert "REJECTED_SCOPE_OVERLAP" in out["reason"]


def test_reject_model_pin():
    config = fresh_config()
    log: list = []
    before = copy.deepcopy(config)
    patch = {"model": "other-model"}
    ok, _reason = dl.validate_config_change(patch, config)
    assert ok is False
    out = dl.apply_config_change(
        config, log, "manifest", "s", "r", "director", patch
    )
    _assert_rejected(config, log, out, before, 0)


def test_invalid_chain_blocked_without_mutation():
    config = fresh_config()
    log: list = []
    before = copy.deepcopy(config)
    patch = {"active_chain": "not-a-list"}
    ok, _reason = dl.validate_config_change(patch, config)
    assert ok is False
    out = dl.apply_config_change(
        config, log, "manifest", "s", "r", "director", patch
    )
    _assert_rejected(config, log, out, before, 0)


def test_validate_accepted_ok():
    config = fresh_config()
    ok, reason = dl.validate_config_change({"cost": 5.0}, config)
    assert (ok, reason) == (True, "ok")


def test_stored_config_accept_persists_exactly_one_row():
    store = dl.HierarchyConfigStore(fresh_config())
    before = store.get_config()
    out = store.apply(
        "manifest", "raise limit", "need capacity", "director", {"cost": 10.0}
    )
    assert out == {
        "applied": True,
        "reason": "applied",
        "decision_ref": "manifest-0001",
    }
    assert len(store.log) == 1
    row = store.log[0]
    assert set(row.keys()) == {
        "decision_id",
        "scope",
        "statement",
        "reason",
        "authority",
        "created_at",
    }
    assert row["decision_id"] == "manifest-0001"
    assert store.get_config()["budget_left"] == before["budget_left"] - 10.0


def test_stored_config_validate_then_apply():
    store = dl.HierarchyConfigStore(fresh_config())
    ok, reason = store.validate({"cost": 5.0})
    assert (ok, reason) == (True, "ok")
    ok, reason = dl.validate_stored_config(store, {"cost": 5.0})
    assert (ok, reason) == (True, "ok")
    out = dl.apply_stored_config(
        store, "manifest", "s", "r", "director", {"cost": 5.0}
    )
    assert out["applied"] is True
    assert len(store.log) == 1


def test_stored_config_reject_mutates_nothing():
    store = dl.HierarchyConfigStore(fresh_config())
    before = store.get_config()
    out = store.apply(
        "manifest",
        "s",
        "r",
        "director",
        {"auditor": "work-1", "independent_audit": False},
    )
    assert out["applied"] is False
    assert out["decision_ref"] is None
    assert "AUDIT_INDEPENDENCE_REJECTED" in out["reason"]
    assert store.get_config() == before
    assert len(store.log) == 0


def test_stored_config_invalid_chain_blocked_without_mutation():
    store = dl.HierarchyConfigStore(fresh_config())
    before = store.get_config()
    ok, reason = store.validate({"active_chain": ["n1", "ghost"]})
    assert ok is False and "POLICY_CONFLICT" in reason
    out = store.apply(
        "manifest", "s", "r", "director", {"active_chain": ["n1", "ghost"]}
    )
    assert out["applied"] is False
    assert store.get_config() == before
    assert len(store.log) == 0


def test_stored_config_budget_reject_mutates_nothing():
    store = dl.HierarchyConfigStore(fresh_config(budget_left=10.0))
    before = store.get_config()
    out = store.apply("manifest", "s", "r", "director", {"cost": 999.0})
    assert out["applied"] is False
    assert "BUDGET_CAPPED" in out["reason"]
    assert store.get_config() == before
    assert len(store.log) == 0


def test_decision_log_unique_scope_sequence():
    backing: list = []
    dlog = dl.DecisionLog(backing)
    first = dlog.add("manifest", "one", "r1", "director")
    second = dlog.add("manifest", "two", "r2", "director")
    other = dlog.add("overlap", "three", "r3", "director")
    assert first["decision_id"] == "manifest-0001"
    assert second["decision_id"] == "manifest-0002"
    assert other["decision_id"] == "overlap-0001"
    assert len({first["decision_id"], second["decision_id"], other["decision_id"]}) == 3
    assert len(backing) == 3


def test_activate_hierarchy_chain_ok_and_rejected():
    config = fresh_config()
    log: list = []
    out = dl.activate_hierarchy_chain(config, log, ["n1", "n2"])
    assert out["applied"] is True
    assert out["decision_ref"] == "hierarchy-0001"
    assert config["active_chain"] == ["n1", "n2"]
    assert len(log) == 1
    config2 = fresh_config()
    log2: list = []
    out2 = dl.activate_hierarchy_chain(config2, log2, ["ghost"])
    assert out2["applied"] is False
    assert config2 == fresh_config()
    assert len(log2) == 0


def test_surface_rejection_and_hot_write(tmp_path):
    assert dl.surface_rejection("BUDGET_CAPPED: cost exceeds budget_left") == (
        "BUDGET_CAPPED: cost exceeds budget_left"
    )
    path = str(tmp_path / "decision.txt")
    assert dl.hot_write_text(path, "row-1\n") == path
    with open(path, "rb") as handle:
        assert b"\r" not in handle.read()
    with open(path, encoding="utf-8") as handle:
        assert handle.read() == "row-1\n"
