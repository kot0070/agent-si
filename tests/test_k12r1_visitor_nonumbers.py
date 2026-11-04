"""K12R1 FXK12: visitor blocks carry no number claims.

Fails on visitor text containing an unmeasured figure (e.g. `80%+`)
inside VISITOR-START/END; passes on the softened number-free wording.
"""

import os
import re

import pytest

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FILES = [
    os.path.join(_WS, "SUBMISSION", "K12", "idea-text.md"),
    os.path.join(_WS, "SUBMISSION", "K12", "presentation.md"),
]

_START = "<!-- VISITOR-START -->"
_END = "<!-- VISITOR-END -->"
_NUM_RE = re.compile(r"\d")


def visitor_lines(path):
    """Return [(line_no, text)] inside the VISITOR markers of path."""
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    inside = False
    block = []
    for no, ln in enumerate(lines, 1):
        if _START in ln:
            inside = True
            continue
        if _END in ln:
            inside = False
            continue
        if inside:
            block.append((no, ln))
    return block


@pytest.mark.parametrize("path", FILES)
def test_visitor_block_has_no_number_claims(path):
    if not os.path.isfile(path):
        pytest.skip("draft text removed from the repo (SUBMISSION/K12, see git history)")
    block = visitor_lines(path)
    assert block, f"empty visitor block in {path}"
    hits = [(no, ln) for no, ln in block if _NUM_RE.search(ln)]
    assert not hits, f"number claims in {path}: {hits!r}"
