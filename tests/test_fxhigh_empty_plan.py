"""FXHIGH item 7: an empty-specs plan is refused, never cached.

RED: TaskPlanner.plan with no subtask specs caches an empty graph as
valid. Expected: a plain refusal and nothing cached.
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

import pytest  # noqa: E402

from agent_si.backend.orchestration import graph as _graph  # noqa: E402


def test_empty_specs_refused_nothing_cached():
    planner = _graph.TaskPlanner()
    with pytest.raises(ValueError) as excinfo:
        planner.plan("pkg-empty", "do it", [])
    assert "non-empty" in str(excinfo.value)
    assert planner._plans == {}


def test_nonempty_specs_still_plan_and_cache():
    planner = _graph.TaskPlanner()
    specs = [{"goal": "write it", "task_class": "general"}]
    first_ref, first_graph = planner.plan("pkg-ok", "do it", specs)
    second_ref, second_graph = planner.plan("pkg-ok", "do it", specs)
    assert first_ref == second_ref
    assert first_graph is second_graph
    assert len(first_graph.nodes) == 1
