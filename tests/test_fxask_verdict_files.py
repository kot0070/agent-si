"""FXASK A5 + A6 RED: verdict lists only existing files; held text is plain."""

from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agent_si.runtime.devrun import engine as _engine  # noqa: E402


def _touch(root: Path, rel: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x", encoding="utf-8")


def test_existing_plan_files_keeps_only_present(tmp_path):
    _touch(tmp_path, "node-add/package.json")
    files = ["node-add/package.json",
             "node-add/node_modules/is-even/package.json"]
    assert _engine._existing_plan_files(
        str(tmp_path), files) == ["node-add/package.json"]


def test_existing_plan_files_drops_absent_and_outside(tmp_path):
    _touch(tmp_path, "keep.txt")
    sibling = tmp_path.parent / "fxask-sibling-out.txt"
    sibling.write_text("x", encoding="utf-8")
    try:
        files = ["keep.txt", "missing.txt", str(sibling), "../escape.txt",
                 "C:\\Windows\\Temp\\x.txt", "", "keep.txt"]
        assert _engine._existing_plan_files(
            str(tmp_path), files) == ["keep.txt"]
    finally:
        with contextlib.suppress(OSError):
            os.unlink(sibling)


def test_existing_plan_files_never_raises(tmp_path):
    assert _engine._existing_plan_files(str(tmp_path), None) == []
    assert _engine._existing_plan_files(
        os.path.join(str(tmp_path), "no-such-dir"), ["a"]) == []
