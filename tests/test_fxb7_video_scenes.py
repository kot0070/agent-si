# FXB7 video scenes: storyboard/script claims pinned against the real route.
# Pure file parsing (stdlib only, no app import, no network): the F05 telemetry
# beat and the F12 token-saving beat cite real routes/testids, the cut totals
# 174s (< 175 cap), and the new voice lines carry no digits.
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEMO = ROOT / "SUBMISSION" / "K12" / "demo-script.md"
PLAN = ROOT / "SUBMISSION" / "K12" / "scene-plan.md"
APP = ROOT / "frontend" / "src" / "app" / "App.tsx"
TELEMETRY_TSX = ROOT / "frontend" / "src" / "k07next2" / "TelemetrySummary.tsx"
READ_ROUTES = ROOT / "src" / "agent_si" / "backend" / "read_routes.py"
PROJECT_VIEW = ROOT / "frontend" / "src" / "projects" / "ProjectView.tsx"

CAP_S = 175

# The old draft script and scene plan were removed from the repo (still in git
# history). Without them there is nothing to pin, so the module skips.
pytestmark = pytest.mark.skipif(
    not (DEMO.is_file() and PLAN.is_file()),
    reason="SUBMISSION/K12 draft was removed from the repo; the pins applied to that draft only",
)


def _row(text, step):
    for line in text.splitlines():
        if re.match(r"\|\s*\d+-\d+\s*\|\s*%s\s*\|" % step, line):
            return line
    raise AssertionError("no demo-script row for %s" % step)


def test_f05_telemetry_beat_on_real_route():
    row = _row(DEMO.read_text(encoding="utf-8"), "F05")
    assert "63-80" in row
    assert "/diagnostics/telemetry" in row
    assert "k07next2-telemetry" in row
    app = APP.read_text(encoding="utf-8")
    assert 'path="/diagnostics/telemetry"' in app
    assert "TelemetrySummary" in app
    assert 'data-testid="k07next2-telemetry"' in TELEMETRY_TSX.read_text(
        encoding="utf-8"
    )
    assert "/api/v1/analytics/telemetry" in READ_ROUTES.read_text(
        encoding="utf-8"
    )


def test_f12_saving_beat_from_served_rows():
    row = _row(DEMO.read_text(encoding="utf-8"), "F12")
    assert "115-132" in row
    assert "project-menu-tokens" in row
    assert "tokens-spent" in row
    view = PROJECT_VIEW.read_text(encoding="utf-8")
    assert 'testId="tokens-spent"' in view
    assert "tokens-row-${index}" in view
    assert "/projects/:projectId/tokens" in APP.read_text(encoding="utf-8")


def test_cut_totals_174_under_cap():
    spans = []
    for line in PLAN.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\d+\.\s*(\d+)-(\d+),\s*(F\d+)", line)
        if m:
            spans.append((int(m.group(1)), int(m.group(2)), m.group(3)))
    assert len(spans) == 14
    total = sum(e - s for s, e, _ in spans)
    assert total == 174
    assert total < CAP_S
    expect = 0
    for s, e, _ in spans:
        assert s == expect
        expect = e


def test_new_voice_lines_number_free():
    text = DEMO.read_text(encoding="utf-8")
    for step in ("F05", "F12"):
        cells = _row(text, step).split("|")
        voice = cells[6]
        assert "«" in voice
        assert not re.search(r"\d", voice)
