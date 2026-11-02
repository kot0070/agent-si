"""FXDIR item-4 gate: installer first, portable second; folder wording.

Owner 16:50: README + release notes say 'unzip the folder, run
AgentSI.exe inside it', never copy the exe out. Static only.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
PACK_README = ROOT / "packaging" / "README.md"
NOTES = ROOT / "docs" / "release" / "RELEASE_NOTES.md"
CHECKLIST = ROOT / "docs" / "release" / "RELEASE_CHECKLIST.md"


def test_readme_installer_first_portable_second():
    text = README.read_text(encoding="utf-8")
    inst = text.find("### Installer")
    port = text.find("### Portable")
    assert inst != -1 and port != -1
    assert inst < port, "installer section must come first"
    portable = text[port:]
    assert "AgentSI.exe inside it" in portable or \
        "run AgentSI.exe inside" in portable, \
        "portable section does not run the exe inside the folder"
    assert "Never copy the exe out" in portable, \
        "portable section misses the never-copy-out rule"


def test_readme_desktop_shortcut_default_checked():
    text = README.read_text(encoding="utf-8")
    inst = text[text.find("### Installer"):text.find("### Portable")]
    assert "desktop" in inst.lower()
    assert "checked by default" in inst.lower(), \
        "installer section misses the default-checked desktop shortcut"


def test_packaging_readme_names_top_folder():
    text = PACK_README.read_text(encoding="utf-8")
    assert "AgentSI/" in text, "packaging notes miss the top folder"
    assert "at its root" in text, "packaging notes miss the exe at root"


def test_release_notes_unzip_folder_run_inside():
    text = NOTES.read_text(encoding="utf-8")
    assert "AgentSI.exe inside it" in text or \
        "run AgentSI.exe inside" in text
    assert "Never copy the exe out" in text
    assert "portable/app" not in text and "app\\AgentSI.exe" not in text, \
        "release notes still point at the old layout"


def test_checklist_row_count_unchanged():
    lines = CHECKLIST.read_text(encoding="utf-8").splitlines()
    rows = [ln for ln in lines if ln.startswith("|")]
    assert len(rows) == 32, f"checklist row count drifted: {len(rows)}"
