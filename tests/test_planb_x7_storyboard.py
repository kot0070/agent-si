"""PLANB X7 (DEFECT-36): the film storyboard's result step really opens the
Details log (click_unless_text on the toggle, wait for the auditor line,
scroll to the checks) instead of ensure_open on a node that is hidden.
The storyboard and the driver live outside the repo; the test skips when
they are absent.
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile

import pytest

_R = r"D:\AI_PROJECTS\AGENT_SI_BUILD"
_SB = os.path.join(_R, "DIRECTOR", "RUN", "VID2", "make_storyboard.py")
_DV = os.path.join(_R, "DIRECTOR", "TOOLS", "live_drive", "demo_video.py")
_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

pytestmark = pytest.mark.skipif(
    not (os.path.isfile(_SB) and os.path.isfile(_DV)),
    reason="film storyboard / driver not on this machine")


def _steps():
    out = os.path.join(tempfile.mkdtemp(), "sb.json")
    subprocess.run([sys.executable, _SB, out, "X:\\ws"], check=True,
                   capture_output=True)
    with open(out, encoding="utf-8") as handle:
        return {s["id"]: s["ops"] for s in json.load(handle)["steps"]}


def test_result_step_opens_details_and_scrolls_to_the_checks():
    ops = _steps()["F_RESULT"]
    names = [op[0] for op in ops]
    assert ["click_unless_text", "run-steps-toggle", "Working folder"] in ops
    assert names.index("click_unless_text") < names.index("wait_expect")
    assert ["wait_expect", "Auditor for", 20] in ops
    assert names.index("wait_expect") < names.index("scroll_to_text")
    assert not any(op[0] == "ensure_open" and "run-steps" in op[1:]
                   for op in ops)
    assert len(_steps()) == 14


def test_driver_knows_the_ops_and_the_page_has_the_toggle():
    with open(_DV, encoding="utf-8") as handle:
        driver = handle.read()
    for name in ("click_unless_text", "scroll_to_text", "wait_expect"):
        assert 'name == "%s"' % name in driver
    found = False
    for root, _dirs, files in os.walk(os.path.join(_WS, "frontend", "src")):
        for file in files:
            if file.endswith(".tsx") and "__tests__" not in root:
                with open(os.path.join(root, file), encoding="utf-8") as h:
                    if "run-steps-toggle" in h.read():
                        found = True
    assert found
