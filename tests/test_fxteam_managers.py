"""FXTEAM M1 RED: deterministic manager grouping (Director wish never decides alone)."""
import os
import sys

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)


def _parts_two():
    return [
        {"part_id": "p1", "goal": "write a.py", "files": ["a.py"], "depends_on": []},
        {"part_id": "p2", "goal": "write b.py", "files": ["b.py"], "depends_on": []},
    ]


def test_no_groups_one_manager():
    from agent_si.runtime.devrun import teammanagers as _tm
    n, why, groups = _tm.decide_managers(_parts_two(), None)
    assert n == 1, (n, why)
    assert why == "one group", why


def test_one_group_one_manager():
    from agent_si.runtime.devrun import teammanagers as _tm
    parts = _parts_two()
    managers = [{"manager_id": "m1", "goal": "all", "parts": ["p1", "p2"]}]
    n, why, groups = _tm.decide_managers(parts, managers)
    assert n == 1, (n, why)
    assert why == "one group", why
    assert len(groups) == 1 and groups[0]["manager_id"] == "m1"


def test_two_groups_separate_files():
    from agent_si.runtime.devrun import teammanagers as _tm
    parts = _parts_two()
    managers = [
        {"manager_id": "m1", "goal": "area a", "parts": ["p1"]},
        {"manager_id": "m2", "goal": "area b", "parts": ["p2"]},
    ]
    n, why, groups = _tm.decide_managers(parts, managers)
    assert n == 2, (n, why)
    assert why == "2 groups over separate files", why


def test_overlap_single_manager():
    from agent_si.runtime.devrun import teammanagers as _tm
    parts = [
        {"part_id": "p1", "goal": "write a.py", "files": ["a.py"], "depends_on": []},
        {"part_id": "p2", "goal": "write a.py too", "files": ["a.py"], "depends_on": []},
    ]
    managers = [
        {"manager_id": "m1", "goal": "area a", "parts": ["p1"]},
        {"manager_id": "m2", "goal": "area b", "parts": ["p2"]},
    ]
    n, why, groups = _tm.decide_managers(parts, managers)
    assert n == 1, (n, why)
    assert why == "groups share a.py", why


def test_shared_readonly_input_keeps_two():
    from agent_si.runtime.devrun import teammanagers as _tm
    parts = [
        {"part_id": "p1", "goal": "read shared", "files": ["a.py"], "depends_on": []},
        {"part_id": "p2", "goal": "read shared", "files": ["b.py"], "depends_on": []},
    ]
    managers = [
        {"manager_id": "m1", "goal": "area a", "parts": ["p1"]},
        {"manager_id": "m2", "goal": "area b", "parts": ["p2"]},
    ]
    n, why, groups = _tm.decide_managers(
        parts, managers, read_only_files={"shared.md"})
    # shared.md not in files map, so still 2 groups
    assert n == 2, (n, why)
    # now overlap on shared read-only only -> still 2
    parts2 = [
        {"part_id": "p1", "goal": "x", "files": ["a.py", "shared.md"], "depends_on": []},
        {"part_id": "p2", "goal": "y", "files": ["b.py", "shared.md"], "depends_on": []},
    ]
    n2, why2, _ = _tm.decide_managers(
        parts2, managers, read_only_files={"shared.md"})
    assert n2 == 2, (n2, why2)
    assert why2 == "2 groups over separate files", why2


def test_cross_dependency_single_manager():
    from agent_si.runtime.devrun import teammanagers as _tm
    parts = [
        {"part_id": "p1", "goal": "base", "files": ["a.py"], "depends_on": []},
        {"part_id": "p2", "goal": "top", "files": ["b.py"], "depends_on": ["p1"]},
    ]
    managers = [
        {"manager_id": "m1", "goal": "area a", "parts": ["p1"]},
        {"manager_id": "m2", "goal": "area b", "parts": ["p2"]},
    ]
    n, why, _ = _tm.decide_managers(parts, managers)
    assert n == 1, (n, why)
    assert why == "groups depend on each other", why


def test_five_groups_capped():
    from agent_si.runtime.devrun import teammanagers as _tm
    parts = [
        {"part_id": "p%d" % i, "goal": "g%d" % i,
         "files": ["f%d.py" % i], "depends_on": []}
        for i in range(1, 6)
    ]
    managers = [
        {"manager_id": "m%d" % i, "goal": "area %d" % i,
         "parts": ["p%d" % i]}
        for i in range(1, 6)
    ]
    n, why, _ = _tm.decide_managers(parts, managers)
    assert n == 1, (n, why)
    assert "one group" in why, why
