"""FXASK A1 RED: manager path flags skipped before reading the verb.

`npm --prefix node-add test` is a project script run, not an installer
refusal; flag-led installs resolve their subcommand so a project grant
covers them; `npm --prefix ../out test` stays refused (outside root).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agent_si.toolguard import guard, permissions  # noqa: E402
from agent_si.backend.app import create_app  # noqa: E402
from agent_si.runtime.devrun import actions  # noqa: E402

TASK_AUTH = {"task": "t1"}


def test_prefix_test_is_script_run():
    assert guard._is_script_run(
        "npm", ["npm", "--prefix", "node-add", "test"]) is True


def test_prefix_run_build_is_script_run():
    assert guard._is_script_run(
        "npm", ["npm", "--prefix", "sub", "run", "build"]) is True


def test_prefix_equals_form_is_script_run():
    assert guard._is_script_run(
        "npm", ["npm", "--prefix=sub", "test"]) is True


def test_cwd_flag_is_script_run():
    assert guard._is_script_run(
        "npm", ["npm", "-C", "sub", "test"]) is True


def test_prefix_install_is_not_script_run():
    assert guard._is_script_run(
        "npm", ["npm", "--prefix", "sub", "install", "x"]) is False


def test_plain_npm_test_unchanged():
    assert guard._is_script_run("npm", ["npm", "test"]) is True
    assert guard._is_script_run("npm", ["npm", "install", "x"]) is False


def test_prefix_test_passes_guard_not_installer_denied():
    verdict = guard.evaluate(
        ["npm", "--prefix", "node-add", "test"], "R0", dict(TASK_AUTH))
    assert verdict["decision"] == "allow", verdict
    assert "installer and fetch" not in str(verdict.get("reason", ""))


def test_prefix_outside_root_still_refused(tmp_path):
    outside = tmp_path / "out"
    verdict = guard.evaluate(
        ["npm", "--prefix", str(outside), "test"], "R0", dict(TASK_AUTH))
    assert verdict["decision"] == "deny", verdict


def test_prefix_real_outside_refused():
    verdict = guard.evaluate(
        ["npm", "--prefix", "../out", "test"], "R0", dict(TASK_AUTH))
    assert verdict["decision"] == "deny", verdict
    assert "outside the workspace root" in str(
        verdict.get("reason", "")), verdict


def test_install_subcommand_skips_prefix_flags():
    assert permissions._install_subcommand(
        ["npm", "--prefix", "sub", "install", "y"]) == "install"


def test_install_subcommand_reads_verb_by_name():
    assert permissions._install_subcommand(
        ["npm", "--prefix", "sub", "test"]) == "test"


def test_flag_led_run_matches_no_install_grant():
    project = "fxask-a1-norun"
    permissions.record_project_grant(None, None, project, "npm", "install")
    try:
        assert permissions.install_grant_allows(
            project, ["npm", "--prefix", "sub", "test"]) is False
    finally:
        permissions.remove_project_grant(None, None, project, "npm",
                                         "install")


def test_project_grant_covers_prefix_install():
    project = "fxask-a1-grant"
    permissions.record_project_grant(None, None, project, "npm", "install")
    try:
        assert permissions.install_grant_allows(
            project, ["npm", "--prefix", "sub", "install", "y"]) is True
    finally:
        permissions.remove_project_grant(None, None, project, "npm",
                                         "install")
    assert permissions.install_grant_allows(
        project, ["npm", "--prefix", "sub", "install", "y"]) is False


def test_classify_prefix_install_is_install():
    assert actions.classify_argv(
        ["npm", "--prefix", "sub", "install", "y"]) == "install"


def test_classify_prefix_test_is_not_install():
    assert actions.classify_argv(
        ["npm", "--prefix", "sub", "test"]) != "install"


def test_script_runs_install_skips_prefix_flags(tmp_path):
    pkg = tmp_path / "proj"
    pkg.mkdir()
    (pkg / "package.json").write_text(
        '{"scripts": {"test": "npm install --no-save x"}}',
        encoding="utf-8")
    assert actions._script_runs_install(
        str(pkg), ["npm", "--prefix", "sub", "test"]) is True
    clean = tmp_path / "clean"
    clean.mkdir()
    (clean / "package.json").write_text(
        '{"scripts": {"test": "node checks/ping.mjs"}}', encoding="utf-8")
    assert actions._script_runs_install(
        str(clean), ["npm", "--prefix", "sub", "test"]) is False


def test_grant_route_resolves_flag_led_subcommand(tmp_path):
    from fastapi.testclient import TestClient

    token = "fxask-a1-token"
    project = "fxask-a1-route"
    tool_id = "install:%s:npm" % project
    app = create_app({"testing": True, "ui_session_token": token,
                      "store_dir": str(tmp_path)})
    client = TestClient(app, raise_server_exceptions=False)
    permissions.record_install_request(
        tool_id=tool_id,
        argv=["npm", "--prefix", "sub", "install", "y"],
        project_id=project)
    resp = client.post(
        "/api/v1/permissions/project-grant",
        json={"project_id": project, "tool_id": tool_id},
        headers={"x-ui-session-token": token})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["installer"] == "npm", body
    assert body["subcommand"] == "install", body
