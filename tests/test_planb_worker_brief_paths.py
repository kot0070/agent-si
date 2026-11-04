"""PLANB W5 (DEFECT-10): the worker brief says "Relative paths only" and also
names the absolute project folder. With a folder the brief must say plainly
that the folder is for information and every action path stays relative.
"""

import os
import sys

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_WS, os.path.join(_WS, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from agent_si.runtime.devrun import engine as _engine  # noqa: E402

FOLDER = "D:\\agent-si-proj"
SPEC = {"part_id": "p1", "goal": "g", "files": ["add.js"]}
NOTE = "never type this absolute path or any absolute path in an action"


def test_worker_brief_with_folder_resolves_the_contradiction():
    prompt = _engine._worker_prompt(SPEC, "task", 1, [], [], folder=FOLDER)
    assert "Relative paths only" in prompt
    assert "Project folder: %s" % (FOLDER,) in prompt
    assert NOTE in prompt
    assert prompt.index(NOTE) > prompt.index("Project folder: %s" % (FOLDER,))


def test_worker_brief_without_folder_is_unchanged():
    prompt = _engine._worker_prompt(SPEC, "task", 1, [], [])
    assert NOTE not in prompt
    assert "Project folder:" not in prompt


def test_solo_worker_brief_has_the_same_note():
    src = open(_engine.__file__, encoding="utf-8").read()
    start = src.index("You are the worker. Project task: %s. Work in the")
    flat = "".join(
        ch for ch in src[start:start + 2500] if ch not in " \n\"")
    assert NOTE.replace(" ", "") in flat
