"""FXB5 release-hygiene pins (P3-C5/C6/C7): fail if the release blockers return.

- env.example carries no machine-local absolute path (P3-C6).
- the tool shipped under docs/third_party_notices/ carries no internal
  DIRECTOR refs (P3-C7).
- the shipped release notes state the unsigned build honestly and HASH.json
  keeps the UNSIGNED-BLOCKED signature block (P3-C5).
Stdlib only, read-only.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MACHINE_PATH_BITS = ("D:/", "D:\\", "C:/", "C:\\", "MUSE_TOOLS")


def test_env_example_holds_no_machine_local_path():
    lines = (ROOT / "env.example").read_text(encoding="utf-8").splitlines()
    bad = [
        line for line in lines
        if line and not line.startswith("#")
        and any(bit in line for bit in MACHINE_PATH_BITS)
    ]
    assert not bad, "machine-local path in env.example: " + "; ".join(bad)
    assert "AGENT_SI_NPM_CACHE=./.npm-cache" in lines


def test_shipped_docs_tool_holds_no_director_refs():
    text = (
        ROOT / "docs" / "third_party_notices" / "gen_release_report.py"
    ).read_text(encoding="utf-8")
    assert "DIRECTOR" not in text


def test_shipped_release_notes_state_unsigned_smartscreen():
    text = (
        ROOT / "docs" / "third_party_notices" / "RELEASE_NOTES.md"
    ).read_text(encoding="utf-8")
    assert "UNSIGNED" in text
    assert "SmartScreen" in text
    envelope = json.loads(
        (ROOT / "packaging" / "installer_manifest" / "HASH.json")
        .read_text(encoding="utf-8")
    )
    assert envelope["signature"]["status"] == "UNSIGNED-BLOCKED"
