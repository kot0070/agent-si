"""FXRED proof: locks the WIPE/REAL fixes so they cannot silently regress.

Fast static checks (no network, no app, no exe):
- k04kbimport fixtures vendored in-repo (DIRECTOR inbox is git-excluded).
- fxcatalog TRACE seed block present (created _task artifact in this worktree).
- freeze_smoke exe legs marked needs-exe (PRE-RC harness, not source suite).
- k09a K09 files use single package identity agent_si (no src. dual import).
"""
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
_WS = os.path.dirname(_HERE)


def test_kb_sections_vendored_in_repo():
    d = os.path.join(_HERE, "fixtures", "kb_sections")
    assert os.path.isdir(d), "kb fixtures missing: " + d
    names = sorted(f for f in os.listdir(d) if f.endswith(".md"))
    assert len(names) == 20, names
    assert "openai.md" in names
    assert "index.md" in names


def test_fxcatalog_trace_seed_block_present():
    p = os.path.join(_WS, "_task", "FXCATALOG", "TRACE.md")
    assert os.path.isfile(p), "TRACE.md not seeded: " + p
    text = open(p, encoding="utf-8").read()
    assert "<!-- FXCATALOG-COUNTS-START -->" in text
    assert "<!-- FXCATALOG-COUNTS-END -->" in text


def test_freeze_exe_legs_marked_needs_exe():
    p = os.path.join(_HERE, "test_freeze_smoke.py")
    text = open(p, encoding="utf-8").read()
    assert 'reason="needs-exe:' in text
    marks = len(re.findall(r"@NEEDS_EXE", text))
    assert marks == 4, marks


def test_k09a_single_package_identity():
    for name in ("test_k09a_contract.py", "test_k09a_retrieval.py"):
        text = open(os.path.join(_HERE, name), encoding="utf-8").read()
        assert "import src.agent_si" not in text, name
        assert "from src.agent_si" not in text, name
        assert "from src." not in text, name
