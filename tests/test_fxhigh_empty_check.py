"""FXHIGH item 1: verify-only PASS must ignore empty no-op checks.

RED: a green `exit 0` row currently passes the gate (returns None).
Expected: the plain refusal text, same as no green check at all.
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

from agent_si.runtime.devrun import engine as _engine  # noqa: E402

REFUSAL = ("verify-only part ran no green check and no installer ran: "
           "name a check that exercises the goal")


def _row(argv=None, command=None):
    row = {"exit_code": 0, "output_tail": "ok\n"}
    if argv is not None:
        row["argv"] = argv
    if command is not None:
        row["command"] = command
    return row


def _reason(rows, tmp_path):
    return _engine._gate_fail_reason(
        spec={"files": []},
        goal="verify the build",
        files_diff="(no changes)",
        check_rows=rows,
        entry_ok=True,
        install_ok=False,
        record={},
        folder=str(tmp_path),
        ws_keys=[],
        ws_start={},
    )


EMPTY_ARGV = [
    ["exit", "0"],
    ["exit"],
    ["true"],
    ["echo", "ok"],
    ["cd", "."],
    ["python", "-c", "pass"],
]

EMPTY_STR = [
    "exit 0",
    "true",
    "echo ok",
    "cd .",
    "python -c pass",
]


@pytest.mark.parametrize("argv", EMPTY_ARGV)
def test_empty_argv_check_does_not_pass(tmp_path, argv):
    assert _reason([_row(argv=argv)], tmp_path) == REFUSAL


@pytest.mark.parametrize("text", EMPTY_STR)
def test_empty_string_check_does_not_pass(tmp_path, text):
    assert _reason([_row(command=text)], tmp_path) == REFUSAL


@pytest.mark.parametrize("argv", EMPTY_ARGV)
def test_helper_argv_form(tmp_path, argv):
    assert _engine._check_command_is_empty(argv) is True


@pytest.mark.parametrize("text", EMPTY_STR)
def test_helper_string_form(tmp_path, text):
    assert _engine._check_command_is_empty(text) is True


def test_real_check_still_green(tmp_path):
    assert _reason([_row(argv=["python", "--version"])], tmp_path) is None


def test_no_checks_refusal_unchanged(tmp_path):
    assert _reason([], tmp_path) == REFUSAL


def test_nonempty_python_still_green(tmp_path):
    assert _reason(
        [_row(argv=["python", "-c", "print(open('x').read())"])],
        tmp_path) is None
