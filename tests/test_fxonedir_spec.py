"""FXDIR one-dir gate: the sidecar spec builds BOTH one-file and one-dir.

RED-first for the owner 16:50 one-folder decision: the frozen exe must
also ship as a folder (EXE + COLLECT, AgentSI.exe at the folder root,
SI icon kept) while the one-file output keeps building until the
owner flips the default. Static only: no freeze runs here.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "packaging" / "sidecar" / "agent_si_sidecar.spec"

EXE_NAME = "AgentSI.exe"
ONEDIR_ENV = "AGENT_SI_SIDECAR_ONEDIR"


def _text():
    assert SPEC.is_file(), f"sidecar spec missing: {SPEC}"
    return SPEC.read_text(encoding="utf-8")


def test_spec_names_exe_entry_and_windowed_icon():
    text = _text()
    assert EXE_NAME in text, "spec lost the frozen exe name"
    assert "ENTRY_SCRIPT" in text and "sidecar.py" in text
    assert "console=False" in text, "spec lost windowed output"
    assert "icon=_ICON" in text or "icon = _ICON" in text, \
        "spec lost the SI icon on the exe"


def test_spec_has_collect_onedir_target():
    text = _text()
    assert "COLLECT" in text, "spec has no one-dir COLLECT target"
    assert ONEDIR_ENV in text, "spec has no one-dir switch"
    assert '"AgentSI"' in text or "'AgentSI'" in text, \
        "spec names no AgentSI one-dir folder"


def test_spec_default_stays_onefile():
    text = _text()
    assert "one-file" in text and "one-dir" in text, \
        "spec does not document both targets"
    assert "default" in text.lower(), "spec does not note which is default"


def test_spec_excludes_binaries_only_in_onedir():
    text = _text()
    assert "exclude_binaries" in text, \
        "spec one-dir EXE does not exclude binaries for COLLECT"
