"""ROW22/M-P1-42: control-plane mapping documented, control-plane only."""
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
    DIRECTOR_RUNTIME,
    DirectorControlOnly,
    control_plane_map,
    require_explicit_director,
)


def test_control_plane_map_documents_routing_and_policy():
    mapping = control_plane_map()
    assert mapping["director.route"] == "graph.route_task"
    assert mapping["director.policy"] == "graph.CONTROL_PLANE_MAP"
    assert mapping["director.split"] == "split.split_package"
    assert mapping["director.decide"] == "teamcard.DecisionLog.append"
    for target in mapping.values():
        assert "." in target, "every control entry must name serving code"


def test_control_plane_map_is_not_a_runtime_object():
    first = control_plane_map()
    first["director.route"] = "tampered"
    assert control_plane_map()["director.route"] == "graph.route_task"
    assert DIRECTOR_RUNTIME is None


def test_control_plane_carries_no_data_plane():
    mapping = control_plane_map()
    blob = " ".join(mapping.values()).lower()
    assert "relay" not in blob
    assert "artifact payload" not in blob
    assert "manager work" not in blob


def test_no_live_provisional_director():
    with pytest.raises(DirectorControlOnly):
        require_explicit_director(None)
    with pytest.raises(DirectorControlOnly):
        require_explicit_director("provisional")
    assert require_explicit_director("director:explicit-1") == "director:explicit-1"
