"""FXLOC C6: frozen bundle reads LICENSE/NOTICES/catalog from _MEIPASS.

With sys.frozen faked plus a staged bundle layout, the sidecar About
refs and the catalog paths resolve inside the bundle (and the staged
files exist); unfrozen values stay byte-identical; the sidecar spec
ships LICENSE, NOTICES.md and catalog_v2.json.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

_WS = Path(__file__).resolve().parents[1]
_SRC = _WS / "src"
for _entry in (str(_WS), str(_SRC)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from agent_si import sidecar  # noqa: E402
from agent_si.qa_catalog import catalog_v2  # noqa: E402

SPEC_PATH = _WS / "packaging" / "sidecar" / "agent_si_sidecar.spec"
LICENSE_SRC = _WS / "LICENSE"
NOTICES_SRC = _WS / "docs" / "third_party_notices" / "NOTICES.md"
CATALOG_SRC = _SRC / "agent_si" / "qa_catalog" / "catalog_v2.json"
HOST_SRC = _SRC / "agent_si" / "qa_catalog" / "runners" / "host.py"


def _freeze(monkeypatch, meipass=None):
    """Fake a frozen bundle: sys.frozen True plus a fake sys._MEIPASS."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    if meipass is not None:
        monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
    else:
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)


def _stage_bundle(root: Path) -> Path:
    """Stage a minimal frozen bundle layout from real tree files."""
    meipass = root / "meipass"
    (meipass / "docs" / "third_party_notices").mkdir(parents=True)
    (meipass / "qa_catalog" / "runners").mkdir(parents=True)
    shutil.copyfile(LICENSE_SRC, meipass / "LICENSE")
    shutil.copyfile(NOTICES_SRC,
                    meipass / "docs" / "third_party_notices" / "NOTICES.md")
    shutil.copyfile(CATALOG_SRC, meipass / "qa_catalog" / "catalog_v2.json")
    shutil.copyfile(HOST_SRC, meipass / "qa_catalog" / "runners" / "host.py")
    return meipass


def test_sidecar_about_paths_resolve_inside_bundle(monkeypatch, tmp_path):
    meipass = _stage_bundle(tmp_path)
    _freeze(monkeypatch, meipass=meipass)
    assert sidecar._license_ref() == str(meipass / "LICENSE")
    assert sidecar._notices_ref() == str(
        meipass / "docs" / "third_party_notices" / "NOTICES.md")
    assert os.path.isfile(sidecar._license_ref())
    assert os.path.isfile(sidecar._notices_ref())


def test_sidecar_about_paths_unchanged_unfrozen():
    assert getattr(sys, "frozen", False) is False
    assert sidecar._license_ref() == "LICENSE"
    assert sidecar._notices_ref() == "docs/third_party_notices/NOTICES.md"


def test_catalog_paths_resolve_inside_bundle(monkeypatch, tmp_path):
    meipass = _stage_bundle(tmp_path)
    _freeze(monkeypatch, meipass=meipass)
    assert catalog_v2._catalog_path() == str(
        meipass / "qa_catalog" / "catalog_v2.json")
    assert catalog_v2._host_path() == str(
        meipass / "qa_catalog" / "runners" / "host.py")
    assert os.path.isfile(catalog_v2._catalog_path())
    assert os.path.isfile(catalog_v2._host_path())
    with open(catalog_v2._catalog_path(), encoding="utf-8") as handle:
        doc = json.load(handle)
    assert sum(catalog_v2.validate_catalog(doc).values()) == len(
        doc["tests"])


def test_spec_ships_licence_notices_catalog():
    text = SPEC_PATH.read_text(encoding="utf-8")
    assert "LICENSE" in text, "spec does not ship LICENSE"
    assert "NOTICES.md" in text, "spec does not ship NOTICES.md"
    assert "catalog_v2.json" in text, "spec does not ship catalog_v2.json"
    assert "qa_catalog" in text
