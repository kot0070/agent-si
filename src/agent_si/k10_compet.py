"""K10ST4 M-R-COMPET: recorded competitive audit (loopback TEST data only).

Row: kit BUILD_PLAN M-R-COMPET "competitive audit flow by flow; fetched
source plus snippet per claim". This module carries a small FIXED recorded
dataset: plain in-code strings, stdlib only, no network, no providers, no
I/O, deterministic order. Sources are recorded strings (never fetched live);
snippets are verbatim recorded strings. Pure function, no settings or global
mutation.
"""

from __future__ import annotations


def audit_flows() -> list[dict]:
    """Return the fixed recorded flow-by-flow competitive audit."""
    return [
        {
            "flow": "decompose",
            "claim": (
                "The Director decomposes one task into disjoint parts and "
                "records the WHY behind each provider/model choice."
            ),
            "source": (
                "recorded: kit BUILD_PLAN coverage (loopback fixture, "
                "not fetched live)"
            ),
            "snippet": (
                "verbatim recorded: 'The WHY is recorded and shown in "
                "the run view'"
            ),
        },
        {
            "flow": "route",
            "claim": (
                "The upper level picks the cheapest fitting model of the "
                "connected providers, with the recorded why."
            ),
            "source": (
                "recorded: kit BUILD_PLAN 0.2 AUTO hierarchy (loopback "
                "fixture, not fetched live)"
            ),
            "snippet": (
                "verbatim recorded: 'picks the cheapest fitting model of "
                "the CONNECTED providers from the model knowledge base "
                "(task + price + quality), with the recorded \"why\"'"
            ),
        },
        {
            "flow": "audit",
            "claim": (
                "An independent auditor checks the work; the author of a "
                "change never audits it."
            ),
            "source": (
                "recorded: kit BUILD_PLAN review loop (loopback fixture, "
                "not fetched live)"
            ),
            "snippet": (
                "verbatim recorded: 'The author of a change NEVER audits "
                "it: an independent agent (fresh context) checks it'"
            ),
        },
    ]
