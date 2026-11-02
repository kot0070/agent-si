"""FXOPEN O5 (CRAWL-L6 + HE-C10): no raw routes or mixed language.

Lint over the real en + uk string tables: no value carries a raw
``/api/`` route (settings Local AI line, cost tab, tests empty-how
all read as plain words). Language + theme names are asserted in
the component tests (topbar language options, theme toggle).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_WS = Path(__file__).resolve().parents[1]
LOCALE_DIR = _WS / "frontend" / "src" / "locale"


def _flatten(mapping, prefix=""):
    for key, value in mapping.items():
        if isinstance(value, dict):
            yield from _flatten(value, prefix + key + ".")
        else:
            yield (prefix + key, value)


def _load(name: str) -> dict:
    with open(LOCALE_DIR / name, encoding="utf-8-sig") as handle:
        return json.load(handle)


def test_fxopen_locale_no_api_routes():
    """No /api/ route text in any en or uk user-facing string."""
    offenders = []
    for name in ("en.json", "uk.json"):
        for key, value in _flatten(_load(name)):
            if isinstance(value, str) and "/api/" in value:
                offenders.append("%s:%s=%r" % (name, key, value))
    assert offenders == []


def test_fxopen_locale_language_and_theme_names():
    """Language + theme options resolve to words in both locales."""
    en = _load("en.json")
    uk = _load("uk.json")
    assert en["shell"]["topbar"]["langEn"] == "English"
    assert en["shell"]["topbar"]["langUk"] == "Українська"
    assert uk["shell"]["topbar"]["langEn"] == "English"
    assert uk["shell"]["topbar"]["langUk"] == "Українська"
    assert en["settings"]["appearance"]["dark"] == "dark"
    assert en["settings"]["appearance"]["light"] == "light"
    assert uk["settings"]["appearance"]["dark"] == "темна"
    assert uk["settings"]["appearance"]["light"] == "світла"
    for name, doc in (("en", en), ("uk", uk)):
        for key in ("langEn", "langUk"):
            value = doc["shell"]["topbar"][key]
            assert value not in ("en", "uk"), "%s %s is a raw code" % (
                name, key)
