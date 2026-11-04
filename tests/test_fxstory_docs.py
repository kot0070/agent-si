"""FXSTORY focused gate: owner field report ships with neutralised citations."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORY = ROOT / "docs" / "MUSE_STRESS_STORY.md"
README = ROOT / "README.md"
LINK = "[docs/MUSE_STRESS_STORY.md](docs/MUSE_STRESS_STORY.md)"
CLAUSE = (
    "Owner-observed: over 100 agents at once. In the surviving records "
    "(id-clock recount): 101 Muse live at 10-26 19:49 (104 combined)"
)
BANNED = (
    "DIRECTOR",
    "LESSONS.md",
    "CHANGELOG.md",
    "AGENTS.md",
    "TO_ADVISOR",
    "D:/",
    "_task/",
    "MODEL_KB",
    "AGENT_SI_BUILD",
    "owner 18",
    "owner 2026",
)


def test_fxstory_file_ships():
    assert STORY.is_file(), "docs/MUSE_STRESS_STORY.md missing"


def test_fxstory_readme_section_and_link():
    text = README.read_text(encoding="utf-8")
    assert "## How this was built" in text, "README section missing"
    assert LINK in text, "README relative link missing"
    assert (ROOT / "docs" / "MUSE_STRESS_STORY.md").is_file()


def test_fxstory_readme_clause_exact():
    assert CLAUSE in README.read_text(encoding="utf-8")


def test_fxstory_no_internal_citations():
    blob = STORY.read_text(encoding="utf-8")
    hits = [b for b in BANNED if b in blob]
    assert not hits, f"internal citations left: {hits}"


def test_fxstory_labels_kept():
    blob = STORY.read_text(encoding="utf-8")
    assert "measured" in blob
    assert "owner-observed" in blob or "Owner-observed" in blob


#: FXSCRUB R5: docs/reports stay in the repo but scrubbed of internal
#: folder names (worktree clones, lane task scratch, handoff notes).
#: Product vocabulary (e.g. DIRECTOR_PER_TASK) is NOT banned.
REPORTS = ROOT / "docs" / "reports"
REPORTS_BANNED = (
    "_task/",
    "WT\\",
    "TO_ADVISOR",
    "AGENT_SI_BUILD",
    "MODEL_KB",
    "_director_private",
    "ui_token",
    "cdp_port",
    "C:\\Users",
    "D:\\API",
    "D:\\AI_PROJECTS",
)


def test_fxreports_no_internal_folder_names():
    pages = sorted(REPORTS.glob("*.md"))
    assert pages, "docs/reports/*.md missing"
    bad = []
    for page in pages:
        blob = page.read_text(encoding="utf-8")
        hits = [b for b in REPORTS_BANNED if b in blob]
        if hits:
            bad.append(f"{page.name}: {hits}")
    assert not bad, "internal folder names left:\n" + "\n".join(bad)
