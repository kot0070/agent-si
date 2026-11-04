"""FXASK A4 RED: a deny covers that run only; the next run asks again."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agent_si.runtime.devrun import actions  # noqa: E402
from agent_si.runtime.devrun.actions import InstallAskNeeded  # noqa: E402
from agent_si.runtime.devrun import engine as _engine  # noqa: E402
from agent_si.toolguard import permissions  # noqa: E402

PROJECT = "fxask-a4-proj"
TOOL = "install:%s:npm" % PROJECT
ARGV = ["npm", "install", "is-odd", "--save"]


def _tool(tag):
    return TOOL if tag is None else "%s-%s" % (TOOL, tag)


def _clear(tag):
    permissions._BOUND_DECISIONS.pop(_tool(tag), None)


def _deny_for_run(run, tag=None):
    tool = _tool(tag)
    permissions.record_install_request(
        tool_id=tool, argv=list(ARGV), project_id=PROJECT, run_id=run)
    return permissions.record_decision(
        tool_id=tool, decision="deny", project_id=PROJECT)


def test_pin_carries_run_and_decision_preserves_it():
    _deny_for_run("run-1", "pin")
    try:
        assert permissions.decision_denies_run(
            tool_id=_tool("pin"), run_id="run-1") is True
        assert permissions.decision_denies_run(
            tool_id=_tool("pin"), run_id="run-2") is False
    finally:
        _clear("pin")


def test_legacy_deny_without_run_still_denies():
    tool = _tool("legacy")
    permissions.record_decision(
        tool_id=tool, decision="deny", project_id=PROJECT)
    try:
        assert permissions.decision_denies_run(
            tool_id=tool, run_id="run-9") is True
    finally:
        _clear("legacy")


def _folder(tmp_path):
    folder = tmp_path / "work"
    folder.mkdir(exist_ok=True)
    return str(folder)


def test_next_run_asks_again_not_refused(tmp_path):
    _deny_for_run("run-1")
    try:
        with pytest.raises(InstallAskNeeded):
            actions.spawn_checked(
                PROJECT, "run-2", _folder(tmp_path), list(ARGV),
                str(tmp_path / "run2.log"), "run2.log",
                grant_run_id="run-2")
    finally:
        permissions._BOUND_DECISIONS.pop(TOOL, None)


def test_denied_run_closes_refused(tmp_path):
    _deny_for_run("run-1")
    try:
        with pytest.raises(PermissionError):
            actions.spawn_checked(
                PROJECT, "run-1x", _folder(tmp_path), list(ARGV),
                str(tmp_path / "run1.log"), "run1.log",
                grant_run_id="run-1")
    finally:
        permissions._BOUND_DECISIONS.pop(TOOL, None)


def test_spent_allow_repin_covers_deny_for_new_run(tmp_path):
    project = "fxask-a4-spent"
    tool = "install:%s:npm" % project
    permissions.record_install_request(
        tool_id=tool, argv=list(ARGV), project_id=project, run_id="run-1")
    permissions.record_decision(
        tool_id=tool, decision="allow", project_id=project)
    assert permissions.decision_allows_run(
        tool_id=tool, run_id="run-1") is True
    # run-1 spends the once-allow.
    assert permissions.note_decision_consumed(
        tool_id=tool, run_id="run-1") is not None
    assert permissions.decision_allows_run(
        tool_id=tool, run_id="run-2") is False
    # run-2 sees the spent allow: ask again, pin re-pointed at run-2.
    with pytest.raises(InstallAskNeeded):
        actions.spawn_checked(
            project, "run-2x", _folder(tmp_path), list(ARGV),
            str(tmp_path / "run2.log"), "run2.log",
            grant_run_id="run-2")
    assert permissions.get_decision(tool_id=tool) is None
    # A deny now lands on run-2 (not on run-1's stale pin).
    permissions.record_decision(
        tool_id=tool, decision="deny", project_id=project)
    assert permissions.decision_denies_run(
        tool_id=tool, run_id="run-2") is True
    assert permissions.decision_denies_run(
        tool_id=tool, run_id="run-1") is False
    permissions._BOUND_DECISIONS.pop(tool, None)


def test_install_denied_line_is_run_scoped(tmp_path):
    _deny_for_run("run-1")
    try:
        line = _engine._install_denied(
            PROJECT, _folder(tmp_path), list(ARGV), scope="run-1")
        assert "install permission denied" in line, line
        assert _engine._install_denied(
            PROJECT, _folder(tmp_path), list(ARGV),
            scope="run-2") == ""
    finally:
        permissions._BOUND_DECISIONS.pop(TOOL, None)
