"""Fxdocs link gate: every relative link in README, docs and packaging README must resolve."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = [ROOT / "README.md", ROOT / "packaging" / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]
INLINE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
REFDEF = re.compile(r"(?m)^\s*\[[^\]]+\]:\s*(\S+)")
REFUSE = re.compile(r"\[[^\]]*\]\[([^\]]*)\]")
MACHINE = re.compile(r"^[A-Za-z]:[\\/]|^\\\\")


def targets(text):
    found = INLINE.findall(text) + REFDEF.findall(text)
    found += [m.group(1) for m in REFUSE.finditer(text)]
    return found


def dead_links():
    bad = []
    for page in PAGES:
        if not page.is_file():
            continue
        rel = page.relative_to(ROOT).as_posix()
        for raw in targets(page.read_text(encoding="utf-8")):
            url = raw.split("#")[0].strip()
            if not url or url.startswith(("http://", "https://", "mailto:")):
                continue
            if MACHINE.match(url):
                bad.append(f"{rel} -> {raw}")
                continue
            base = ROOT if url.startswith("/") else page.parent
            if not (base / url.lstrip("/")).exists():
                bad.append(f"{rel} -> {raw}")
    return sorted(set(bad))


def test_fxdocs_links_resolve():
    assert not dead_links(), "dead links:\n" + "\n".join(dead_links())


def test_fxdocs_jury_words():
    lines = (ROOT / "README.md").read_text(encoding="utf-8").splitlines()[:40]
    blob = "\n".join(lines)
    missing = [w for w in ("run", "connect", "evidence", "licence") if w not in blob]
    assert not missing, f"jury words missing from README lines 1-40: {missing}"
