"""Planner builds graph, router picks class only; neither names a model."""
import dataclasses
import inspect
import os
import sys

import pytest

sys.path.insert(
    0,
    os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
    ),
)

from agent_si.backend.orchestration.graph import (
    CycleError,
    DependencyError,
    DispatchRejected,
    PlannedSubtask,
    SubtaskGraph,
    TaskPlanner,
    route_task,
    validate_dispatch,
)


def specs_two(package_id="pkg-p"):
    return [
        {"goal": "first slice", "task_class": "build", "risk": "LOW"},
        {"goal": "second slice", "task_class": "verify", "risk": "MEDIUM",
         "dependency_ids": [f"{package_id}:sub-000"]},
    ]


def flattened(obj):
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield key
            yield from flattened(value)
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            yield from flattened(value)
    else:
        yield obj


def assert_no_model(obj):
    texts = [str(item) for item in flattened(obj)]
    assert not any(item == "provider" for item in flattened(obj))
    assert not any(item == "model" for item in flattened(obj))
    assert not any("meta/muse-spark" in text for text in texts)


def test_planner_builds_ordered_graph():
    planner = TaskPlanner()
    plan_ref, graph = planner.plan("pkg-p", "package goal", specs_two())
    assert plan_ref.startswith("plan-pkg-p-")
    assert graph.order() == ["pkg-p:sub-000", "pkg-p:sub-001"]
    node = graph.nodes["pkg-p:sub-001"]
    assert node.dependency_ids == ["pkg-p:sub-000"]


def test_planner_picks_no_provider_or_model():
    assert "provider" not in inspect.signature(TaskPlanner.plan).parameters
    assert "model" not in inspect.signature(TaskPlanner.plan).parameters
    _, graph = TaskPlanner().plan("pkg-pm", "goal", specs_two("pkg-pm"))
    payload = {
        "nodes": [dataclasses.asdict(node) for node in graph.nodes.values()]
    }
    assert_no_model(payload)


def test_planner_idempotent_on_package_and_goal():
    planner = TaskPlanner()
    first_ref, first_graph = planner.plan(
        "pkg-idem", "same goal", specs_two("pkg-idem")
    )
    second_ref, second_graph = planner.plan(
        "pkg-idem", "same goal", specs_two("pkg-idem")
    )
    assert first_ref == second_ref
    assert list(first_graph.nodes) == list(second_graph.nodes)


def test_planner_rejects_cycle_and_unknown_dep():
    planner = TaskPlanner()
    with pytest.raises(DependencyError):
        planner.plan("pkg-dep", "g", [{"goal": "x", "dependency_ids": ["missing"]}])
    cyclic = [
        {"subtask_id": "a", "goal": "a", "dependency_ids": ["b"]},
        {"subtask_id": "b", "goal": "b", "dependency_ids": ["a"]},
    ]
    with pytest.raises(CycleError):
        planner.plan("pkg-cyc", "g", cyclic)


def test_router_picks_class_only():
    assert "provider" not in inspect.signature(route_task).parameters
    assert "model" not in inspect.signature(route_task).parameters
    _, graph = TaskPlanner().plan("pkg-r", "goal", specs_two("pkg-r"))
    node = graph.nodes["pkg-r:sub-000"]
    decision = route_task(
        node, "worker", "local",
        required_capabilities=["code"], tool_needs=["fs"],
        knowledge_needs=["kb"], manager_id="manager-1",
    )
    payload = dataclasses.asdict(decision)
    assert payload["worker_class"] == "worker"
    assert payload["execution_type"] == "local"
    assert payload["run_config"]["client_max_retries"] == 0
    assert_no_model(payload)


def test_dispatch_rejects_task_without_planned_subtask():
    _, graph = TaskPlanner().plan("pkg-d", "goal", specs_two("pkg-d"))
    with pytest.raises(DispatchRejected):
        validate_dispatch({"agent_task_id": "t1", "agent_id": "a"}, graph)
    with pytest.raises(DispatchRejected):
        validate_dispatch(
            {"agent_task_id": "t1", "subtask_id": "ghost", "agent_id": "a",
             "contract_hash": "c"},
            graph,
        )
    task = validate_dispatch(
        {"agent_task_id": "t1", "subtask_id": "pkg-d:sub-000", "agent_id": "a",
         "contract_hash": "c"},
        graph,
    )
    assert isinstance(task, PlannedSubtask) is False
    assert task.subtask_id == "pkg-d:sub-000"


def test_planned_subtask_carries_no_model_fields():
    fields = {f.name for f in dataclasses.fields(PlannedSubtask)}
    assert "provider" not in fields and "model" not in fields
    graph = SubtaskGraph()
    with pytest.raises(ValueError):
        graph.add("not-a-subtask")  # type: ignore[arg-type]


def test_build_graph_order_and_adjacency():
    from agent_si.backend.orchestration.graph import build_graph

    graph = build_graph(
        ["a", "b", "c"],
        [("b", "a"), ("c", "a"), ("c", "b")],
    )
    assert list(graph) == ["a", "b", "c"]
    assert graph == {"a": [], "b": ["a"], "c": ["a", "b"]}


def test_build_graph_rejects_unknown_dep():
    from agent_si.backend.orchestration.graph import build_graph

    with pytest.raises(DependencyError):
        build_graph(["a"], [("a", "ghost")])
    with pytest.raises(DependencyError):
        build_graph(["a"], [("ghost", "a")])


def test_build_graph_rejects_cycle():
    from agent_si.backend.orchestration.graph import CycleError as GraphCycleError
    from agent_si.backend.orchestration.graph import build_graph

    with pytest.raises(GraphCycleError):
        build_graph(["a", "b"], [("a", "b"), ("b", "a")])
    with pytest.raises(GraphCycleError):
        build_graph(["a"], [("a", "a")])


def test_ready_parts_progression():
    from agent_si.backend.orchestration.graph import build_graph, ready_parts

    graph = build_graph(["a", "b", "c"], [("b", "a"), ("c", "b")])
    assert ready_parts(graph, set()) == ["a"]
    assert ready_parts(graph, {"a"}) == ["b"]
    assert ready_parts(graph, {"a", "b"}) == ["c"]
    assert ready_parts(graph, {"a", "b", "c"}) == []


def test_mark_completed_new_set_semantics():
    from agent_si.backend.orchestration.graph import (
        build_graph,
        mark_completed,
        ready_parts,
    )

    graph = build_graph(["a", "b"], [("b", "a")])
    before = {"a"}
    after = mark_completed(graph, before, "b")
    assert after == {"a", "b"}
    assert before == {"a"}
    assert after is not before
    assert ready_parts(graph, after) == []


def test_mark_completed_rejects_unknown_part():
    from agent_si.backend.orchestration.graph import build_graph, mark_completed

    graph = build_graph(["a"], [])
    with pytest.raises(DependencyError):
        mark_completed(graph, set(), "ghost")


def test_graph_helpers_name_no_provider_or_model():
    import inspect as _inspect

    from agent_si.backend.orchestration import graph as _graph_mod

    for name in ("build_graph", "ready_parts", "mark_completed"):
        params = _inspect.signature(getattr(_graph_mod, name)).parameters
        assert "provider" not in params
        assert "model" not in params
    payload = {
        "graph": _graph_mod.build_graph(["a"], []),
        "ready": _graph_mod.ready_parts({"a": []}, set()),
        "done": sorted(_graph_mod.mark_completed({"a": []}, set(), "a")),
    }
    assert_no_model(payload)
