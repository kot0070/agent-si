"""PLANB V2i: a worker never sees the engine's own .devrun folder."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agent_si.runtime.devrun import actions, engine  # noqa: E402


def test_listing_drops_the_engine_folder_only():
    text = "\n".join([".devrun", "add.js", "package.json"])
    assert engine._worker_listing(text) == "add.js\npackage.json"
    assert engine._worker_listing("a\n.devrunx\nb") == "a\n.devrunx\nb"


@pytest.mark.parametrize("path", [
    ".devrun", ".devrun/agent", "./.devrun/outputs/x.log", ".devrun\\agent\\p1.jsonl"])
def test_paths_under_the_engine_folder_read_as_absent(path):
    with pytest.raises(actions.ActionRefused):
        engine._refuse_engine_dir(path)


@pytest.mark.parametrize("path", [".", "", "src/.devrun-notes.txt", "add.js", "sub/.devrun"])
def test_project_paths_stay_visible(path):
    engine._refuse_engine_dir(path)


def test_worker_brief_says_a_missing_sibling_file_is_expected():
    spec = {"part_id": "p2", "goal": "write add.js", "files": ["add.js"]}
    prompt = engine._worker_prompt(spec, "task", 1, [], [])
    assert "belongs to another part" in prompt
    assert "reply done true as soon as your own files are written" in prompt
    assert "Files you may write: add.js." in prompt
