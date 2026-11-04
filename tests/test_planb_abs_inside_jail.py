"""PLANB: an absolute path inside the project folder is the same file; outside stays refused."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agent_si.runtime.devrun import actions  # noqa: E402


def test_absolute_inside_write_lands_in_the_part_file(tmp_path):
    folder = tmp_path / "proj"
    folder.mkdir()
    target = folder / "node-add" / "add.js"
    actions.write_file(
        str(folder), str(target), "x", allowed=["node-add/add.js"],
        run_id="r", part_id="p1", attempt=1)
    assert target.read_text(encoding="utf-8") == "x"


def test_absolute_inside_still_obeys_the_part_file_list(tmp_path):
    folder = tmp_path / "proj"
    folder.mkdir()
    with pytest.raises(actions.ActionRefused):
        actions.write_file(
            str(folder), str(folder / "other.js"), "x", allowed=["add.js"],
            run_id="r", part_id="p1", attempt=1)
    assert not (folder / "other.js").exists()


@pytest.mark.parametrize("raw", [
    "{tmp}/outside.txt", "{tmp}/proj/../outside.txt", "~/x",
    "C:\\Windows\\win.ini"])
def test_other_absolute_paths_stay_refused(tmp_path, raw):
    folder = tmp_path / "proj"
    folder.mkdir()
    with pytest.raises(actions.ActionRefused):
        actions.jail_abs(str(folder), raw.format(tmp=str(tmp_path)))


def test_list_dir_accepts_the_absolute_project_folder_and_subfolder(tmp_path):
    folder = tmp_path / "proj"
    (folder / "sub").mkdir(parents=True)
    (folder / "sub" / "a.txt").write_text("1", encoding="utf-8")
    assert "a.txt" in actions.list_dir(str(folder), str(folder / "sub"))



def test_list_dir_of_the_absolute_project_folder_itself(tmp_path):
    folder = tmp_path / "proj"
    folder.mkdir()
    (folder / "b.txt").write_text("1", encoding="utf-8")
    assert "b.txt" in actions.list_dir(str(folder), str(folder))
