"""FXSHELLV2 focused breakpoint contract: the narrow collapse lives at 800px.

Guards the exact regression fixed on this lane: 508a0e2 moved the
sidebar/inspector collapse to `@media (max-width: 799px)`, which hid the
FXLAYOUT panels contract at 800x600 and broke
test_fxlayout_three_columns[en-800-600]. The fix restores
`@media (max-width: 800px)` with the small-screens comment.

No build, no browser; parses frontend/src/ui/shell.css with stdlib
only (milliseconds). Live behaviour at 800x600 is proven by
test_fxshellv_sidebar800.py (panels flow, both themes) and
test_fxlayout_visual.py (three-column vs panels matrix).
"""

import os
import re

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS_PATH = os.path.join(WS, "frontend", "src", "ui", "shell.css")

COLLAPSE_QUERY = "@media (max-width: 800px)"
STALE_QUERY = "@media (max-width: 799px)"
WIDE_QUERY = "@media (min-width: 801px)"


def _read_css():
    with open(CSS_PATH, "r", encoding="utf-8") as handle:
        return handle.read()


def _media_block(text, query):
    """Return the brace-matched body of the first query block, or None."""
    start = text.find(query)
    if start < 0:
        return None
    brace = text.find("{", start)
    if brace < 0:
        return None
    depth = 0
    for pos in range(brace, len(text)):
        if text[pos] == "{":
            depth += 1
        elif text[pos] == "}":
            depth -= 1
            if depth == 0:
                return text[brace + 1:pos]
    return None


def check_breakpoint(css_text):
    """Return a list of contract violations (empty = contract holds)."""
    problems = []
    if STALE_QUERY in css_text:
        problems.append("stale 799px collapse present (must be 800px)")
    block = _media_block(css_text, COLLAPSE_QUERY)
    if block is None:
        problems.append("missing @media (max-width: 800px) collapse block")
        return problems
    sidebar_hidden = any(
        'nav[data-testid="sidebar"]' in chunk and "display: none" in chunk
        for chunk in block.split("}")
    )
    if not sidebar_hidden:
        problems.append("800px block does not hide nav[data-testid=sidebar]")
    panels_shown = any(
        ".fx-panels-btn" in chunk and "display: inline-block" in chunk
        for chunk in block.split("}")
    )
    if not panels_shown:
        problems.append("800px block does not show .fx-panels-btn")
    return problems


def test_collapse_breakpoint_is_800px():
    assert check_breakpoint(_read_css()) == []


def test_panels_button_hidden_on_wide_viewports():
    css = _read_css()
    base = css.split("@media")[0]
    assert re.search(r"\.fx-panels-btn\s*\{\s*display:\s*none", base), (
        "base .fx-panels-btn rule must keep display: none"
    )


def test_wide_overflow_pair_intact():
    css = _read_css()
    assert WIDE_QUERY in css, "missing @media (min-width: 801px) wide pair"
    block = _media_block(css, WIDE_QUERY)
    assert block is not None and "overflow" in block and "hidden" in block, (
        "wide pair must keep body overflow hidden"
    )
