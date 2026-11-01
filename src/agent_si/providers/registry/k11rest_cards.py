"""K11REST health cards: display-only provider/preset/model rows.

One card per known provider preset: the preset key, the provider id,
the pinned catalogue model (or "" when the preset pins none), the time
the card was built, and a staleness flag from the adapter-side
freshness verdict. Building cards never registers, connects, or
otherwise mutates provider state.
"""

from __future__ import annotations

import time
from typing import Any

from agent_si.providers.adapters.k11rest_probe import probe_verdict

from .presets import PRESETS


def build_cards(now: float | None = None,
                evidence: dict | None = None) -> list[dict[str, Any]]:
    """Build one display-only card per provider preset.

    ``evidence`` optionally maps (provider, model) pairs to the last
    healthy-answer timestamp; without it every pin reads unevidenced
    (stale_warn True). The preset table itself is only read.
    """
    at = time.time() if now is None else float(now)
    cards = []
    for key in sorted(PRESETS):
        preset = PRESETS[key]
        catalogue = preset.get("catalogue") or ()
        model = str(catalogue[0]) if catalogue else ""
        last_ok = None
        if evidence is not None:
            last_ok = evidence.get((preset.get("provider_id"), model))
        verdict = probe_verdict(preset.get("provider_id"), model,
                                last_ok_ts=last_ok, now=at)
        cards.append({
            "provider": str(preset.get("provider_id")),
            "preset": str(key),
            "model": verdict["model"],
            "fresh_ts": verdict["fresh_ts"],
            "stale_warn": verdict["stale_warn"],
        })
    return cards
