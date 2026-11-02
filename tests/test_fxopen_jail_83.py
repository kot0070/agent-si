"""FXOPEN O2 (HE11-1): 8.3 short-path jail must not false-refuse.

A project under an 8.3 segment (``PCIA~1`` vs realpath ``PC IA``)
is legal: jail_abs compares realpath + normcase of both sides.
``..``, absolute and junction escapes stay refused.
"""
from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

import pytest

_WS = Path(__file__).resolve().parents[1]
_SRC = _WS / "src"
for _entry in (str(_WS), str(_SRC)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from agent_si.runtime.devrun.actions import ActionRefused, jail_abs  # noqa: E402


def _short_path(path: str) -> str | None:
    """8.3 short form of a path, or None when unavailable."""
    if os.name != "nt":
        return None
    try:
        GetShortPathNameW = ctypes.windll.kernel32.GetShortPathNameW
    except Exception:
        return None
    buf = ctypes.create_unicode_buffer(512)
    try:
        length = GetShortPathNameW(path, buf, 512)
    except Exception:
        return None
    if not length or length >= 512:
        return None
    return buf.value or None


def test_fxopen_jail_83_short_folder_passes(tmp_path):
    """Legal file under an 8.3 project folder passes the jail."""
    project = tmp_path / "PC IA"
    target = project / "sub" / "note.txt"
    target.parent.mkdir(parents=True)
    target.write_text("hello", encoding="utf-8")
    short = _short_path(str(project))
    if short is None or os.path.normcase(short) == os.path.normcase(str(project)):
        pytest.skip("no 8.3 short form on this volume")
    assert short != str(project)
    got = jail_abs(short, "sub/note.txt")
    assert os.path.isfile(got)


def test_fxopen_jail_aliased_folder_passes(tmp_path):
    """Legal file under an aliased project folder passes the jail.

    Same defect class as the 8.3 form: abspath(folder) differs from
    realpath(folder), so a realpath candidate must be compared against
    the realpath base, never the raw abspath base.
    """
    project = tmp_path / "real project"
    target = project / "sub" / "note.txt"
    target.parent.mkdir(parents=True)
    target.write_text("hello", encoding="utf-8")
    alias = tmp_path / "alias"
    try:
        if os.name == "nt":
            import subprocess
            proc = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(alias), str(project)],
                capture_output=True, timeout=30)
            if proc.returncode != 0:
                pytest.skip("cannot create junction here")
        else:
            os.symlink(str(project), str(alias))
    except (OSError, Exception):
        pytest.skip("cannot create junction here")
    got = jail_abs(str(alias), "sub/note.txt")
    assert os.path.isfile(got)


def test_fxopen_jail_dotdot_still_refused(tmp_path):
    with pytest.raises(ActionRefused):
        jail_abs(str(tmp_path), "../escape.txt")


def test_fxopen_jail_absolute_still_refused(tmp_path):
    with pytest.raises(ActionRefused):
        jail_abs(str(tmp_path), "C:\\Windows\\win.ini")
    with pytest.raises(ActionRefused):
        jail_abs(str(tmp_path), "C:/Windows/win.ini")


def test_fxopen_jail_junction_escape_still_refused(tmp_path):
    """A junction inside the project pointing outside stays refused."""
    project = tmp_path / "proj"
    project.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("x", encoding="utf-8")
    link = project / "link"
    try:
        if os.name == "nt":
            import subprocess
            proc = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
                capture_output=True, timeout=30)
            if proc.returncode != 0:
                pytest.skip("cannot create junction here")
        else:
            os.symlink(str(outside), str(link))
    except (OSError, Exception):
        pytest.skip("cannot create junction here")
    with pytest.raises(ActionRefused):
        jail_abs(str(project), "link/secret.txt")
