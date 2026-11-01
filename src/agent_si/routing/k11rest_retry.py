"""K11REST retry simulation over transient provider refusals.

For a retryable refusal code the lane replays the frozen policy: one
visible retry of the same model after the served Retry-After delay,
then advance to the next model of the same provider pool. Retry is
never a per-role default (every role resolves OFF), and the ledger is
bounded by an attempts cap plus a spend cap. Pure: no network, no
provider calls.
"""

from __future__ import annotations

from typing import Any

#: Served Retry-After delay in seconds per retryable refusal code.
RETRY_AFTER = {429: 1, 503: 5, 529: 3}

#: Lane pool: (provider, model) pairs in fallback order. The single
#: shipped pin is the only entry, so advancing wraps back to it.
LANE_POOL = (("meta", "meta/muse-spark-1.3-contributor"),)

#: Ledger bounds: at most this many attempts, at most this much spend.
MAX_ATTEMPTS = 3
SPEND_PER_ATTEMPT = 1
SPEND_CAP = 3


def role_retry_default(role: str) -> bool:
    """Per-role retry default: always OFF (never set from the role)."""
    return False


def next_pool_model(provider: str, current: str,
                    pool: tuple = LANE_POOL) -> str:
    """Next model of the same provider after ``current`` (wrap-around)."""
    same = [model for item_provider, model in pool
            if item_provider == provider]
    if not same:
        raise ValueError("pool holds no model for provider %r" % (provider,))
    if current not in same:
        return same[0]
    return same[(same.index(current) + 1) % len(same)]


def simulate_retry(code: Any, attempts_cap: int = MAX_ATTEMPTS,
                   spend_cap: int = SPEND_CAP) -> dict[str, Any]:
    """Replay one retryable refusal into its served attempt ledger.

    Raises ValueError for a code outside the retryable set. The ledger
    holds the visible same-model retry first (after the Retry-After
    delay), then the advance to the same-provider next pool model; both
    caps trim the ledger, never below one attempt.
    """
    try:
        numeric = int(code)
    except (TypeError, ValueError):
        raise ValueError("unknown retry code: %r" % (code,)) from None
    if numeric not in RETRY_AFTER:
        raise ValueError("unknown retry code: %r" % (code,))
    provider, model = LANE_POOL[0]
    wait = RETRY_AFTER[numeric]
    ledger = [
        {"model": model, "visible": True, "after": wait},
        {"model": next_pool_model(provider, model), "visible": True,
         "after": 0},
    ]
    bound = max(1, min(int(attempts_cap), MAX_ATTEMPTS))
    spend_bound = max(1, int(spend_cap) // SPEND_PER_ATTEMPT)
    ledger = ledger[:min(bound, spend_bound, len(ledger))]
    return {
        "attempts": ledger,
        "final_model": ledger[-1]["model"],
        "provider_same": True,
        "role_default_off": not role_retry_default("worker"),
    }
