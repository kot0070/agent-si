"""FXR1A-G6: user-facing gate/hold lines stay plain words.

Every FAIL/hold line names its subject (tool, check, file, part) plus
the next step; never raw exit text ("exit None"), never a stack
("Traceback"), never the retired "auditor only" line.
"""

import os
import sys

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import pytest  # noqa: E402

from agent_si.runtime.devrun import actions as _actions  # noqa: E402
from agent_si.runtime.devrun import engine as _engine  # noqa: E402


def _gate(**kw):
    base = {"spec": {"files": ["a.txt"],
                     "check_commands": [["python", "--version"]]},
            "goal": "do it", "files_diff": "(no changes)", "check_rows": [],
            "entry_ok": True, "install_ok": False, "record": {"reads": []},
            "folder": ".", "ws_keys": [], "ws_start": {}}
    base.update(kw)
    return _engine._gate_fail_reason(**base)


def _plain(line):
    assert line, "empty line"
    assert "exit None" not in str(line), line
    assert "Traceback" not in str(line), line
    assert "auditor only" not in str(line), line


def test_missing_tool_names_tool_source_next_step():
    line = str(_actions.SpawnNotInstalled("node"))
    assert "node" in line and "nodejs.org" in line, line
    assert "install it, then send the task again" in line, line
    _plain(line)
    line = str(_actions.SpawnNotInstalled("python"))
    assert "python.org" in line, line
    _plain(line)
    line = str(_actions.SpawnNotInstalled("fxdevrun-no-such-thing"))
    assert "fxdevrun-no-such-thing" in line, line
    assert "install it, then send the task again" in line, line
    _plain(line)


def test_no_start_names_tool_and_next_step():
    line = _gate(check_rows=[{
        "argv": ["fxdevrun-no-such-tool-xyz"], "exit_code": None,
        "could_not_start": True,
        "output_tail": "could not start: "
                       "fxdevrun-no-such-tool-xyz is not installed"}])
    assert line is not None, "no-start must fail the gate"
    assert "fxdevrun-no-such-tool-xyz" in line, line
    assert "next step" in line, line
    _plain(line)


def test_refused_names_argv():
    line = _gate(
        spec={"files": ["a.txt"],
              "check_commands": [["python", "-c", "print(1)"]]},
        check_rows=[{"argv": ["python", "-c", "print(1)"],
                     "exit_code": None, "refused": True,
                     "refusal": "refused: inline code needs approval"}])
    assert line is not None, "refused must fail the gate"
    assert "python" in line, line
    _plain(line)


def test_verify_only_names_the_gap():
    line = _gate(spec={"files": [], "check_commands": []},
                 check_rows=[])
    assert line is not None, "zero-evidence verify-only must fail"
    assert "verify-only" in line and "green check" in line, line
    _plain(line)


def test_declared_missing_names_file():
    line = _gate(
        spec={"files": ["fxwording-no-such-file-xyz.txt"],
              "check_commands": [["python", "--version"]]},
        check_rows=[{"argv": ["python", "--version"], "exit_code": 0}],
        files_diff="x")
    assert line is not None
    assert "fxwording-no-such-file-xyz.txt" in line, line
    _plain(line)
