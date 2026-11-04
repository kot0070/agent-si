"""PLANB: a small model's wrapped action shape is repaired, bad shapes still fail."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agent_si.runtime.devrun import protocol  # noqa: E402


def _reply(actions, done=False):
    return json.dumps({"actions": actions, "done": done})


def test_wrapped_write_file_is_flattened():
    out = protocol.parse_agent_reply(_reply(
        [{"write_file": {"path": "add.js", "content": "x"}}]))
    assert out["actions"] == [
        {"action": "write_file", "path": "add.js", "content": "x"}]


def test_wrapped_run_list_becomes_argv_and_list_dir_string_becomes_path():
    out = protocol.parse_agent_reply(_reply(
        [{"run": ["npm", "test"]}, {"list_dir": "."}, {"read_file": {"path": "a"}}]))
    assert out["actions"] == [
        {"action": "run", "argv": ["npm", "test"]},
        {"action": "list_dir", "path": "."},
        {"action": "read_file", "path": "a"}]


def test_proper_shape_unchanged():
    action = {"action": "run", "argv": ["node", "--test"]}
    assert protocol.parse_agent_reply(_reply([action]))["actions"] == [action]


@pytest.mark.parametrize("bad", [
    {"delete_file": {"path": "a"}},
    {"write_file": 5},
    {"write_file": {"path": "a"}, "extra": 1},
    {"path": "a"},
])
def test_unknown_or_ambiguous_shapes_still_refused(bad):
    with pytest.raises(protocol.AgentError):
        protocol.parse_agent_reply(_reply([bad]))


def test_type_key_instead_of_action_is_repaired():
    out = protocol.parse_agent_reply(_reply(
        [{"type": "write_file", "path": "add.js", "content": "x"},
         {"type": "run", "argv": ["npm", "test"]}]))
    assert out["actions"] == [
        {"action": "write_file", "path": "add.js", "content": "x"},
        {"action": "run", "argv": ["npm", "test"]}]


def test_type_key_with_unknown_name_or_with_action_still_refused():
    with pytest.raises(protocol.AgentError):
        protocol.parse_agent_reply(_reply([{"type": "delete_file", "path": "a"}]))
    out = protocol.parse_agent_reply(_reply(
        [{"action": "read_file", "type": "x", "path": "a"}]))
    assert out["actions"][0]["action"] == "read_file"
