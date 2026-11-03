"""FXREPORTS shape gate: K10/K11 reports keep sibling shape and corrected anchors."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
K10 = ROOT / "docs" / "reports" / "K10.md"
K11 = ROOT / "docs" / "reports" / "K11.md"
INLINE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")

#: Real placeholder markers look like <<NAME>> (shipped NOTICES once
#: carried <<FINAL...>>); prose that merely names the marker check
#: (backtick-quoted "<<", K10.md:64) is not a placeholder.
PLACEHOLDER = re.compile(r"<<[^`\s]*>>")

K13_SHA = "f256bab4d31be3cd9e86c22a1bdcef90b08ad62500a8eca2051705cc0a9b0690"
K04_SHA = "931cac1eec2532f6f5cdc98038725628435f6d4db91f8c64f6147c0838f01d7c10207348ab"


def _text(page):
    return page.read_text(encoding="utf-8")


def test_fxreports_files_exist():
    assert K10.is_file(), "docs/reports/K10.md missing"
    assert K11.is_file(), "docs/reports/K11.md missing"


def test_fxreports_titles_and_sections():
    for page, title in ((K10, "# K10 package report"), (K11, "# K11 package report")):
        text = _text(page)
        assert text.startswith(title + "\n"), page.name
        for sec in ("## 1.", "## 2.", "## 3.", "## 4.", "## 5."):
            assert sec in text, f"{page.name} missing {sec}"


def test_fxreports_no_placeholder_markers():
    for page in (K10, K11):
        for i, line in enumerate(_text(page).splitlines(), 1):
            assert not PLACEHOLDER.search(line), f"{page.name}:{i}: {line}"


def test_fxreports_no_dead_links():
    bad = []
    for page in (K10, K11):
        for raw in INLINE.findall(_text(page)):
            url = raw.split("#")[0].strip()
            if not url or url.startswith(("http://", "https://", "mailto:")):
                continue
            base = ROOT if url.startswith("/") else page.parent
            if not (base / url.lstrip("/")).exists():
                bad.append(f"{page.name} -> {raw}")
    assert not bad, "dead links:\n" + "\n".join(bad)


def test_fxreports_k11_corrected_anchors():
    text = _text(K11)
    assert K13_SHA in text, "K11 missing current K13 anchor"
    assert K04_SHA in text, "K11 missing current K04 refreeze anchor"
    assert "NOT-DONE" in text, "K11 missing NOT-DONE"


def test_fxreports_k10_waits_for_exe_marked():
    text = _text(K10)
    assert "waits-for-exe" in text, "K10 must mark exe-only items waits-for-exe"
    assert "NOT-DONE" in text, "K10 missing NOT-DONE"
