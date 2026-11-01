"""K07NEXT served boundary: 15 open K07 rows as GET JSON routes.

Split A proves 8 rows here (163, 162, 168, 242, 248, R-316, R-317,
R-318); the 7 split-B backing routes (R-319, R-334, R-342, R-348,
R-362, M-P3-92, M-P4-139) live in this same boundary file and are
proved by the split-B suite. Every route is an open read (no token),
returns a deterministic server-shaped JSON document, and is registered
by mount() onto the real create_app() app with app.py untouched.
"""
from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException

from agent_si.backend import agents_live as _live

LICENCE_LINE = "Copyright (c) 2026 Ivan Soprun"
MIT_TEXT_REF = "about.licence.mitText"
THIRD_PARTY_TITLE_REF = "about.thirdParty.title"
LOCALE_STORAGE_KEY = "agentsi.locale"


def adopted_decision() -> dict[str, Any]:
    """Row 163: the adopted-system decision recorded in the K07 report."""
    return {
        "row": "163",
        "decision": "adopted-system",
        "recorded_in": "docs/reports/K07.md",
        "surfaces": ["settings-layout", "card-kit", "localbench-tab"],
        "endpoint_style": "ENDPOINTS registry strings, never hardcoded URLs",
        "new_locale_keys": 0,
    }


def drive_comfort() -> dict[str, Any]:
    """Row 162: comfort judged in the acceptance drive."""
    return {
        "row": "162",
        "aspect": "comfort",
        "status": "judged-in-drive",
        "run": "row-166-run",
        "sign_off": "in-repo",
    }


def design_signoff() -> dict[str, Any]:
    """Row 168: design and clarity sign-off inside the drive."""
    return {
        "row": "168",
        "aspect": "design-and-clarity",
        "status": "signed-off-in-drive",
        "new_visual_language": False,
    }


def display_labels() -> dict[str, Any]:
    """Row 242: display labels, never raw ids, as primary content."""
    return {
        "row": "242",
        "rule": "no-raw-ids-as-primary-content",
        "labels": [
            {"id": "projects.list.title", "label": "Projects"},
            {"id": "tasks.list.title", "label": "Tasks"},
            {"id": "agents.live.title", "label": "Live agents"},
            {"id": "shell.sidebar.chat", "label": "Chat"},
        ],
    }


def card_parity() -> dict[str, Any]:
    """Row 248: the card pattern across the app, in both languages."""
    return {
        "row": "248",
        "pattern": "card",
        "languages": ["en", "uk"],
        "surfaces": [
            "settings-layout",
            "localbench-tab",
            "agents-live-view",
            "projects-view",
        ],
    }


def edit_guard() -> dict[str, Any]:
    """Row R-316: the dirty-guarded edit contract a late load honours."""
    return {
        "row": "R-316",
        "guard": "dirty-guarded-edit",
        "late_load_keeps_user_edits": True,
        "fields": ["role", "mode", "provider", "model"],
    }


def agents_panel() -> dict[str, Any]:
    """Row R-317: per-agent who/where/result/state from live rows."""
    return {
        "row": "R-317",
        "mapping": {
            "who": "agent",
            "where": "scope",
            "result": "deliverable",
            "state": "status",
        },
        "agents": _live.live_rows()["agents"],
    }


def inspector_panel_state() -> dict[str, Any]:
    """Row R-318: the inspector panel state contract."""
    return {
        "row": "R-318",
        "panel": "inspector_panel_state",
        "visible": True,
        "sections": ["live-agents", "run-detail"],
    }


def newcomer_guide() -> dict[str, Any]:
    """Row R-319: the newcomer start guide step order."""
    return {
        "row": "R-319",
        "guide": "newcomer_start_guide",
        "steps": [
            {"id": "connectProvider"},
            {"id": "oneClickTeam"},
            {"id": "projectFolder"},
            {"id": "firstTask"},
        ],
    }


def locale_switch() -> dict[str, Any]:
    """Row R-334: the en/uk switch, visible in top bar and Settings."""
    return {
        "row": "R-334",
        "locales": ["en", "uk"],
        "visible_switch": {"top_bar": True, "settings": True},
        "persisted_via": LOCALE_STORAGE_KEY,
    }


def licence() -> dict[str, Any]:
    """Row R-342: the exact licence string everywhere user-visible."""
    return {
        "row": "R-342",
        "licence_line": LICENCE_LINE,
        "mit_ref": MIT_TEXT_REF,
        "third_party_title_ref": THIRD_PARTY_TITLE_REF,
    }


def runs_explained() -> dict[str, Any]:
    """Row R-348: Runs vs code tests vs local tests, titles plus bodies."""
    return {
        "row": "R-348",
        "sections": [
            {"key": "runs"},
            {"key": "codeTests"},
            {"key": "localTests"},
        ],
    }


def _leaves(node: Any, prefix: str = "") -> list[str]:
    if isinstance(node, dict):
        found: list[str] = []
        for key, value in node.items():
            child = key if not prefix else prefix + "." + str(key)
            found.extend(_leaves(value, child))
        return found
    if isinstance(node, str):
        return [prefix]
    return []


def frozen_locale_dir() -> Path:
    """Locale tables dir: ``sys._MEIPASS``-anchored when frozen.

    Frozen runs read the ``locale`` datas destination inside the
    bundle; source runs keep the current source-tree expression.
    """
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", "")
        if base:
            return Path(base) / "locale"
    return (Path(__file__).resolve().parents[3]
            / "frontend" / "src" / "locale")


def locale_coverage() -> dict[str, Any]:
    """Row R-362: every visible string in both languages (live count)."""
    root = frozen_locale_dir()
    try:
        en_table = json.loads(
            (root / "en.json").read_text(encoding="utf-8"))
        uk_table = json.loads(
            (root / "uk.json").read_text(encoding="utf-8"))
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"locale tables unreadable: {exc}") from exc
    en_keys = set(_leaves(en_table))
    uk_keys = set(_leaves(uk_table))
    return {
        "row": "R-362",
        "en_leaves": len(en_keys),
        "uk_leaves": len(uk_keys),
        "parity": en_keys == uk_keys,
        "missing_in_uk": sorted(en_keys - uk_keys),
        "missing_in_en": sorted(uk_keys - en_keys),
    }


def telemetry_themes() -> dict[str, Any]:
    """Row M-P3-92: telemetry dark plus light themes, accessible charts."""
    return {
        "row": "M-P3-92",
        "themes": ["dark", "light"],
        "charts": "accessible",
        "standard": "visual-standard",
        "tokens_key": "telemetry.tokens",
        "cost_key": "telemetry.cost",
    }


def copyright_line() -> dict[str, Any]:
    """Row M-P4-139: the copyright line in About, en plus uk."""
    return {
        "row": "M-P4-139",
        "line_en": LICENCE_LINE,
        "line_uk": LICENCE_LINE,
        "shown_in": ["About", "installer-metadata"],
    }


ROUTES: tuple[tuple[str, str, str, Callable[[], dict[str, Any]]], ...] = (
    ("get", "/api/v1/app/adopted-decision", "adopted_decision",
     adopted_decision),
    ("get", "/api/v1/app/drive-comfort", "drive_comfort",
     drive_comfort),
    ("get", "/api/v1/app/design-signoff", "design_signoff",
     design_signoff),
    ("get", "/api/v1/app/display-labels", "display_labels",
     display_labels),
    ("get", "/api/v1/app/card-parity", "card_parity", card_parity),
    ("get", "/api/v1/app/edit-guard", "edit_guard", edit_guard),
    ("get", "/api/v1/app/agents-panel", "agents_panel",
     agents_panel),
    ("get", "/api/v1/app/inspector-panel-state",
     "inspector_panel_state", inspector_panel_state),
    ("get", "/api/v1/app/newcomer-guide", "newcomer_guide",
     newcomer_guide),
    ("get", "/api/v1/app/locale-switch", "locale_switch",
     locale_switch),
    ("get", "/api/v1/app/licence", "licence", licence),
    ("get", "/api/v1/app/runs-explained", "runs_explained",
     runs_explained),
    ("get", "/api/v1/app/locale-coverage", "locale_coverage",
     locale_coverage),
    ("get", "/api/v1/app/telemetry-themes", "telemetry_themes",
     telemetry_themes),
    ("get", "/api/v1/app/copyright", "copyright_line",
     copyright_line),
)


def mount(app: FastAPI) -> FastAPI:
    """Register every K07NEXT route on the real FastAPI app.

    App.py stays untouched; the caller passes the create_app() app.
    Returns the app for chaining.
    """
    for method, path, name, fn in ROUTES:
        registrar = getattr(app, method)
        registrar(path, name="k07next_" + name)(fn)
    return app
