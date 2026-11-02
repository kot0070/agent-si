"""FXDOCS focused gate: lane docs carry no placeholder marks and keep the key-check strings."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LANE_FILES = [
    ROOT / "README.md",
    ROOT / "docs" / "ARCHITECTURE.md",
    ROOT / "docs" / "USER_GUIDE.md",
    ROOT / "docs" / "TROUBLESHOOTING.md",
]


def test_fxdocs_no_placeholder_markers():
    bad = []
    for page in LANE_FILES:
        assert page.is_file(), f"lane file missing: {page}"
        for i, line in enumerate(page.read_text(encoding="utf-8").splitlines(), 1):
            if "<<" in line:
                bad.append(f"{page.name}:{i}: {line.strip()[:120]}")
    assert not bad, "placeholder marks left:\n" + "\n".join(bad)


def test_fxdocs_keycheck_strings_present():
    blob = (ROOT / "README.md").read_text(encoding="utf-8")
    blob += (ROOT / "docs" / "TROUBLESHOOTING.md").read_text(encoding="utf-8")
    for s in (
        "Key checked. Save to connect.",
        "The provider refused this key. Paste the full key again.",
        "Could not reach the provider.",
    ):
        assert s in blob, f"key-check string missing from docs: {s!r}"
