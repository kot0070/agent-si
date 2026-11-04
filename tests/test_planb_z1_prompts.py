"""PLANB Z1-Z3: Director plan checks test behaviour, one part by default,
the retry brief quotes the failing check and its exact output."""

import os
import sys

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_WS, os.path.join(_WS, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from agent_si.runtime.devrun import engine as _engine  # noqa: E402


def test_z1_director_checks_run_behaviour_not_implementation_grep():
    prompt = _engine._director_prompt("make add.js with a test")
    assert "never search a file for an implementation detail" in prompt
    assert "implementation detail" in prompt
    assert "module.exports" in prompt
    assert "runs the project's tests or program" in prompt
    assert "never weaken a check" in prompt


def test_z2_director_plans_one_part_unless_separate_deliverables():
    prompt = _engine._director_prompt("make add.js with a test")
    assert "Plan ONE part" in prompt
    assert "separate deliverables" in prompt


def test_z3_retry_brief_quotes_failing_check_and_output():
    spec = {"part_id": "p1", "goal": "g", "files": ["add.js"]}
    check = "Check p1 $ findstr module.exports add.js -> exit 1: FINDSTR: no match"
    prompt = _engine._worker_prompt(
        spec, "build it", 2, [check], ["auditor says no"],
        prior_files=["add.js"], last_fail=check)
    assert "Failing check and its exact output: %s" % (check,) in prompt
    assert "Make that check pass" in prompt


def test_z3_first_attempt_has_no_retry_block():
    spec = {"part_id": "p1", "goal": "g", "files": ["add.js"]}
    prompt = _engine._worker_prompt(spec, "build it", 1, [], [])
    assert "Failing check and its exact output" not in prompt
