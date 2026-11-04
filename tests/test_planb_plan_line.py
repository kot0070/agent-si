"""PLANB: the plan line names planned files; the [files:] marker still lists only existing ones."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agent_si.runtime.devrun import engine  # noqa: E402

PART = {"part_id": "p1", "goal": "build", "files": ["package.json", "add.js"]}


def test_nothing_on_disk_shows_planned_files_not_an_empty_marker(tmp_path):
    line = engine._plan_part_line(PART, str(tmp_path))
    assert line == "Part p1: build (planned: package.json, add.js)"
    assert "[files:" not in line


def test_existing_files_keep_the_marker_and_drop_absent_ones(tmp_path):
    (tmp_path / "add.js").write_text("x", encoding="utf-8")
    line = engine._plan_part_line(PART, str(tmp_path))
    assert line == "Part p1: build [files: add.js]"
    assert "package.json" not in line


def test_part_without_files_keeps_the_old_empty_marker(tmp_path):
    line = engine._plan_part_line(
        {"part_id": "p2", "goal": "g", "files": []}, str(tmp_path))
    assert line == "Part p2: g [files: ]"
