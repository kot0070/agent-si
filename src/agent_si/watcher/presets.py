"""Watcher presets: named rule-card bundles.

Owns the REALIZATION_MAP entry ``watcher.preset.apply`` (:func:`apply`).
TABLE stays the preset definitions. A fresh project auto-seeds the
default (standard) preset through :func:`ensure_seeded`: idempotent, kept
in a per-project installed-cards store, with the seeding journaled as
one SERVICE_STATE row. :func:`apply` seeds fresh projects first, then
installs the requested preset's cards; unknown presets raise before any
write.
"""

from __future__ import annotations

from typing import Dict, Tuple

from agent_si.watcher import journal as journal_store
from agent_si.watcher.journal import ERROR_CODES, WatcherError

__all__ = (
    "ERROR_CODES",
    "WatcherError",
    "PRESETS",
    "DEFAULT_PRESET",
    "TABLE",
    "apply",
    "ensure_seeded",
    "installed_cards",
    "reset_state",
)


#: Preset names: a fresh project seeds the default preset.
PRESETS = (
    "cautious",
    "standard",
    "strict",
)

#: Default preset seeded on fresh projects.
DEFAULT_PRESET = "standard"

#: Preset name to the rule cards it installs.
TABLE = {
    "cautious": ("card-hang",),
    "standard": ("card-hang", "card-guard"),
    "strict": ("card-hang", "card-guard", "card-tamper"),
}

#: Installed cards per project: project id to its installed card ids.
_INSTALLED: Dict[str, Tuple[str, ...]] = {}


def reset_state() -> None:
    """Drop per-project installed cards."""
    _INSTALLED.clear()


def installed_cards(project_id: str) -> Tuple[str, ...]:
    """Serve one project's installed cards, or () when never seeded."""
    return _INSTALLED.get(str(project_id), ())


def ensure_seeded(project_id: str) -> Tuple[str, ...]:
    """Seed the default preset once per project; replay the install after."""
    key = str(project_id)
    if key in _INSTALLED:
        return _INSTALLED[key]
    cards = tuple(TABLE[DEFAULT_PRESET])
    _INSTALLED[key] = cards
    journal_store.append_event(
        key, "watcher", "SERVICE_STATE", "seed standard preset", cards,
    )
    return cards


def apply(project_id: str, preset_id: str) -> Tuple[str, ...]:
    """Install the preset's rule cards; return the installed card ids."""
    try:
        cards = tuple(TABLE[preset_id])
    except KeyError:
        raise WatcherError(
            "PRESET_NOT_FOUND", "unknown preset %r" % (preset_id,)
        ) from None
    ensure_seeded(str(project_id))
    _INSTALLED[str(project_id)] = cards
    return cards
