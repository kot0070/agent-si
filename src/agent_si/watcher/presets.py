"""Watcher presets: named rule-card bundles (lane A STEP2).

Owns the REALIZATION_MAP entry ``watcher.preset.apply`` (:func:`apply`).
Applies install the preset's rule cards and return the installed card
ids; unknown presets raise.
"""

from __future__ import annotations

from typing import Tuple

from agent_si.watcher.journal import ERROR_CODES, WatcherError

__all__ = (
    "ERROR_CODES",
    "WatcherError",
    "PRESETS",
    "TABLE",
    "apply",
    "reset_state",
)


#: Preset names: a fresh project seeds the default preset.
PRESETS = (
    "cautious",
    "standard",
    "strict",
)

#: Preset name to the rule cards it installs.
TABLE = {
    "cautious": ("card-hang",),
    "standard": ("card-hang", "card-guard"),
    "strict": ("card-hang", "card-guard", "card-tamper"),
}


def reset_state() -> None:
    """Presets keep no per-run state; present for probe isolation."""
    return None


def apply(project_id: str, preset_id: str) -> Tuple[str, ...]:
    """Install the preset's rule cards; return the installed card ids."""
    try:
        cards = TABLE[preset_id]
    except KeyError:
        raise WatcherError(
            "PRESET_NOT_FOUND", "unknown preset %r" % (preset_id,)
        ) from None
    return tuple(cards)
