"""K11REST adapter-side freshness verdicts for pinned provider models.

Pure helpers: given a pinned (provider, model) identity plus the last
time it returned a healthy answer, decide whether the pin reads stale.
No network, no stored state.
"""

from __future__ import annotations

import time
from typing import Any

#: Seconds after which a pinned model with no fresh healthy answer reads stale.
PINNED_FRESH_TTL_S = 3600.0


def probe_verdict(provider_id: str, model: str,
                  last_ok_ts: float | None = None,
                  now: float | None = None,
                  ttl_s: float = PINNED_FRESH_TTL_S) -> dict[str, Any]:
    """Freshness verdict for one pinned identity.

    ``last_ok_ts`` is the last time the identity answered healthy, or
    None when it never has. ``stale_warn`` is True when no model is
    pinned, when the pin was never evidenced, or when the evidence is
    older than ``ttl_s``.
    """
    at = time.time() if now is None else float(now)
    if not model:
        stale = True
    elif last_ok_ts is None:
        stale = True
    else:
        stale = (at - float(last_ok_ts)) > float(ttl_s)
    return {
        "provider": str(provider_id),
        "model": str(model),
        "fresh_ts": at,
        "stale_warn": stale,
    }
