"""FXHIGH item 5: the auditor sees post-images of declared part files.

RED: auditor_messages carries goal + diff (capped 12 KB) + checks, so a
break in an unchanged file (no diff) or beyond a cut diff still PASSes.
Expected: the post-image of each declared part file rides along, 8 KB
per file, 32 KB total, cuts marked in plain words.
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

from agent_si.runtime.devrun import audit as _audit  # noqa: E402


def _text(**files):
    msgs = _audit.auditor_messages(
        "do it", "(no changes)", [], (), "", part_diff="",
        part_files=dict(files))
    assert len(msgs) == 1
    return msgs[0]["content"]


def test_cross_file_break_visible_without_diff():
    body = _text(**{"shared.txt": "BROKEN MARKER XYZ broken helper"})
    assert "BROKEN MARKER XYZ" in body
    assert "shared.txt" in body


def test_per_file_cap_with_cut_line():
    big = "A" * 20000
    body = _text(**{"big.txt": big})
    assert "A" * 8192 in body
    assert "cut" in body
    assert len(body) < 8192 + 8192 + 3000


def test_total_cap_omits_rest():
    files = {"f%d.txt" % i: "B" * 20000 for i in range(5)}
    body = _text(**files)
    assert "cut" in body
    assert "omitted" in body
    shown = [name for name in files if name in body
             and "omitted" not in body.split(name, 1)[1][:60]]
    assert 0 < len(shown) < 5, shown


def test_missing_file_marked():
    body = _text(**{"gone.txt": None})
    assert "gone.txt" in body
    assert "missing" in body


def test_no_part_files_unchanged_shape():
    msgs = _audit.auditor_messages("goal", "diff", [], (), "", part_diff="")
    assert len(msgs) == 1
    assert "post-image" not in msgs[0]["content"]
