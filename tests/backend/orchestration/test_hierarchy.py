import os, sys; sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__),"..","..","..","src")))
"""R-302/R-303: real hierarchy, sizing WHY, invalid chain blocked intact."""

import copy

import pytest

from agent_si.backend.orchestration.graph import (
    HierarchyChain,
    HierarchyConfigStore,
    HierarchyRefused,
    ParentClosureBlocked,
    RoutingRefused,
    route_task,
    stage_rows_to_hierarchy,
)
from agent_si.backend.orchestration.graph import (
    TaskPlanner as Planner,
)


def make_chain():
    return HierarchyChain(
        director_id="director-1",
        manager_id="manager-1",
        tool_agent_ids=["tool-1", "tool-2"],
    )


def test_valid_chain_activates_and_records_row():
    store = HierarchyConfigStore()
    outcome = store.activate_chain(make_chain(), actor="director-1")
    assert outcome.accepted is True
    assert outcome.row is not None and outcome.row.scope == "hierarchy"
    assert store.config["director"] == "director-1"
    assert store.config["manager"] == "manager-1"
    assert store.config["tool_agents"] == ["tool-1", "tool-2"]


def test_invalid_chain_blocked_config_unchanged():
    bad_chains = [
        HierarchyChain("", "manager-1", ["tool-1"]),
        HierarchyChain("director-1", "", ["tool-1"]),
        HierarchyChain("director-1", "manager-1", []),
        HierarchyChain("director-1", "manager-1", ["tool-1", "tool-1"]),
        HierarchyChain("director-1", "manager-1", ["manager-1"]),
    ]
    for chain in bad_chains:
        store = HierarchyConfigStore()
        before = copy.deepcopy(store.config)
        with pytest.raises(HierarchyRefused):
            store.activate_chain(chain, actor="director-1")
        assert store.config == before
        assert store.log.rows == []


def test_close_parent_needs_all_pass_plus_integration():
    store = HierarchyConfigStore()
    store.activate_chain(make_chain(), actor="director-1")
    with pytest.raises(ParentClosureBlocked):
        store.close_parent({"a": "PASS", "b": "REWORK"}, {"record_id": "int-1"})
    with pytest.raises(ParentClosureBlocked):
        store.close_parent({"a": "PASS"}, None)
    done = store.close_parent({"a": "PASS"}, {"record_id": "int-1"})
    assert done["parent"] == "closed"


def test_sizing_records_why():
    store = HierarchyConfigStore()
    sizing = store.size_team("block-b1", 3, "HIGH", actor="manager-1")
    assert sizing.members == 3
    assert sizing.why, "sizing must record WHY"
    assert "block-b1" in sizing.why and "HIGH" in sizing.why
    assert store.log.rows and store.log.rows[-1].scope == "team-sizing"


def test_sizing_invalid_risk_refused():
    with pytest.raises(ValueError):
        HierarchyConfigStore().size_team("b", 2, "EXTREME", actor="m")


def test_user_correction_channel_user_only():
    store = HierarchyConfigStore()
    before = copy.deepcopy(store.config)
    with pytest.raises(HierarchyRefused):
        store.append_user_correction("manager-1", "change this")
    assert store.config == before
    outcome = store.append_user_correction("user", "pause after step two")
    assert outcome.accepted is True


def test_role_authority_needs_configured_role():
    store = HierarchyConfigStore(
        config={"role_models": {"worker": {"model": "m", "purpose": "dev"}}}
    )
    before = copy.deepcopy(store.config)
    with pytest.raises(HierarchyRefused):
        store.grant_role_authority("auditor", {"model": "m"}, actor="director-1")
    assert store.config == before


def test_contributor_production_binding_refused():
    from agent_si.backend.orchestration.graph import MODEL_ID

    store = HierarchyConfigStore(
        config={"role_models": {"worker": {"model": "m", "purpose": "dev"}}}
    )
    before = copy.deepcopy(store.config)
    with pytest.raises(HierarchyRefused):
        store.grant_role_authority(
            "worker", {"model": MODEL_ID, "purpose": "production"}, actor="director-1"
        )
    assert store.config == before


def test_routing_subordinate_to_manager_hierarchy():
    _, g = Planner().plan("pkg-h", "goal", [{"goal": "s", "task_class": "t"}])
    (node,) = list(g.nodes.values())
    with pytest.raises(RoutingRefused):
        route_task(node, "worker", "local", manager_id="")
    decision = route_task(node, "worker", "local", manager_id="manager-1")
    assert decision.subordinate_to == "manager-1"


def test_staged_rows_to_hierarchy_are_refs():
    staged = stage_rows_to_hierarchy([{"row_id": "r1"}, {"row_id": "r2"}])
    assert [s["row_id"] for s in staged] == ["r1", "r2"]
    assert all(v.startswith("ARTIFACT_REF:") for s in staged for v in [s["hierarchy_ref"]])


def test_graph_api_names_no_provider_or_model():
    import inspect

    from agent_si.backend.orchestration import graph as graph_mod

    for name in ("build_graph", "ready_parts", "mark_completed"):
        assert callable(getattr(graph_mod, name)), name
        params = inspect.signature(getattr(graph_mod, name)).parameters
        assert "provider" not in params
        assert "model" not in params
