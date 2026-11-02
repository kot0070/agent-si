"""FXC1 fix-batch shape proof (P6-F5 rail colour + P4-H4 spec datas).

Proves this lane's two product changes with no browser and no exe:
- the winning `nav[data-testid="sidebar"] a` rule in shell.css resolves
  to the accent token (FXSHELL1 visual contract, FXDESIGN3 S5);
  --fx-accent equals --agent-si-accent in both themes (tokens.css);
- the sidecar spec no longer ships the unread migrations payload while
  the 0390 file stays on disk and its evidence field
  `environment_fingerprint` lives on via capability_store
  (CapabilityEvidenceRecord dataclass field, constructed below).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_WS = Path(__file__).resolve().parents[1]
_SRC = _WS / "src"
for _entry in (str(_WS), str(_SRC)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

SHELL_CSS = _WS / "frontend" / "src" / "ui" / "shell.css"
TOKENS_CSS = _WS / "frontend" / "src" / "ui" / "tokens.css"
SPEC = _WS / "packaging" / "sidecar" / "agent_si_sidecar.spec"
MIGRATION_0390 = (
    _WS / "src" / "agent_si" / "adapters" / "sqlite"
    / "migration_scripts" / "0390_localbench_evidence.sql"
)

_NAV_A_COLOR = re.compile(
    r'nav\[data-testid="sidebar"\] a\s*\{[^}]*?color:\s*([^;]+);',
)


def _nav_a_colors(css: str) -> list[str]:
    return [c.strip() for c in _NAV_A_COLOR.findall(css)]


def test_rail_links_resolve_to_accent_token():
    """The winning sidebar-link colour is the accent token."""
    css = SHELL_CSS.read_text(encoding="utf-8")
    colors = _nav_a_colors(css)
    assert colors, "no nav sidebar-a colour rule left in shell.css"
    assert colors[-1] == "var(--fx-accent)", colors
    assert "var(--fx-ink)" not in colors, colors


def test_accent_tokens_agree_in_both_themes():
    """--fx-accent stays the same value as --agent-si-accent."""
    css = TOKENS_CSS.read_text(encoding="utf-8")
    fx = re.findall(r"--fx-accent:\s*(#[0-9a-fA-F]{6})", css)
    shipped = re.findall(r"--agent-si-accent:\s*(#[0-9a-fA-F]{6})", css)
    assert fx and shipped, "accent tokens missing from tokens.css"
    assert [v.lower() for v in fx] == [v.lower() for v in shipped]


def test_spec_ships_no_unread_migrations_payload():
    """Spec datas drop migration_scripts; the 0390 file itself stays."""
    text = SPEC.read_text(encoding="utf-8")
    assert "migration_scripts" not in text, "spec still stages migrations/"
    assert MIGRATION_0390.is_file(), "0390 migration file must stay on disk"


def test_evidence_fingerprint_field_lives_by_another_path():
    """environment_fingerprint exists on the served evidence record."""
    from agent_si.capability_store.store import (  # noqa: E402
        CapabilityEvidenceRecord,
        EvidenceTier,
    )

    assert "environment_fingerprint" in (
        CapabilityEvidenceRecord.__dataclass_fields__
    )
    row = CapabilityEvidenceRecord(
        model_id="m-fxc1",
        task_class="qa",
        tier=EvidenceTier.MEASURED,
        score=None,
        score_type=None,
        sample_count=None,
        confidence=None,
        benchmark_version=None,
        measured_at=None,
        runtime=None,
        runtime_version=None,
        environment_fingerprint="fp-fxc1",
        freshness_state="fresh",
        evidence_ref="cap:m-fxc1:qa:v1",
        source=None,
    )
    assert row.environment_fingerprint == "fp-fxc1"
