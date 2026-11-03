"""FXWHERE: a task naming a place outside the project folder is never faked.

Owner live test: "make a file on disk D root koreva.txt hello" returned
`Done - 1 part, 1 passed, files: koreva.txt` with no location, while the
file landed inside the project folder (the jail refuses anything else,
by design). The block stays; the run must SAY where the files went.

Contract (RED first, then GREEN):
- director / worker prompts carry the no-fake rule WITH the folder path;
  folder="" keeps the prompt byte-identical to the pre-fix shape.
- the solo-worker prompt names the project folder too.
- auditor_messages carries the location check: the goal is the user's
  own words, the diffs are relative to the project folder.
- behaviour: an absolute outside write is refused and writes nothing
  outside the folder (jail_abs + write_file).
"""

import os
import sys

import pytest

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.runtime.devrun import actions as _actions  # noqa: E402
from agent_si.runtime.devrun import audit as _audit  # noqa: E402
from agent_si.runtime.devrun import engine as _engine  # noqa: E402

FOLDER = "D:\\agent-si-proj"
OUTSIDE_TASK = "make a file on disk D root koreva.txt hello"


def _worker_spec():
    return {"part_id": "p1", "goal": "g", "files": ["koreva.txt"]}


def test_director_prompt_default_has_no_folder_rule():
    before = _engine._director_prompt("build it")
    assert "Project folder:" not in before


def test_director_prompt_names_folder_and_no_fake_rule():
    prompt = _engine._director_prompt(OUTSIDE_TASK, "", FOLDER)
    assert "Project folder: %s" % (FOLDER,) in prompt
    assert "Agent SI works only inside the project folder" in prompt
    assert FOLDER in prompt
    assert "Never a bare Done" in prompt


def test_worker_prompt_names_folder_and_no_fake_rule():
    prompt = _engine._worker_prompt(
        _worker_spec(), OUTSIDE_TASK, 1, [], [], folder=FOLDER)
    assert "Project folder: %s" % (FOLDER,) in prompt
    assert "never claim the file went there" in prompt


def test_worker_prompt_default_has_no_folder_rule():
    before = _engine._worker_prompt(_worker_spec(), "build it", 1, [], [])
    assert "Project folder:" not in before


def test_auditor_messages_carry_location_check():
    msgs = _audit.auditor_messages(
        "put koreva.txt on disk D root", "diff", [], (), "",
        folder=FOLDER)
    assert msgs, "auditor messages are never empty"
    body = msgs[0]["content"]
    assert "put koreva.txt on disk D root" in body
    assert "Project folder: %s" % (FOLDER,) in body
    assert "Location check" in body


def test_auditor_messages_default_has_no_location_check():
    msgs = _audit.auditor_messages("goal", "diff", [], (), "", part_diff="")
    assert "Location check" not in msgs[0]["content"]


def test_absolute_outside_write_refused_and_writes_nothing(tmp_path):
    folder = tmp_path / "proj"
    folder.mkdir()
    outside = tmp_path / "koreva.txt"
    with pytest.raises(_actions.ActionRefused):
        _actions.write_file(
            str(folder), str(outside), "hello",
            allowed=["koreva.txt"], run_id="r1", part_id="p1", attempt=1)
    assert not outside.exists(), "refused write creates nothing outside"


def test_jail_refuses_windows_absolute_path(tmp_path):
    folder = tmp_path / "proj"
    folder.mkdir()
    with pytest.raises(_actions.ActionRefused):
        _actions.jail_abs(str(folder), "D:\\koreva.txt")
