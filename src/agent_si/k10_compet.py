"""K10ST4 M-R-COMPET plus K10R351 R-351: recorded audit (loopback TEST data).

Row M-R-COMPET: kit BUILD_PLAN "competitive audit flow by flow; fetched
source plus snippet per claim".
Row R-351: kit BUILD_PLAN "acceptance on the tech-handbook copy, all
functions, n8n excluded, final evidence table". The final evidence table
is evidence_table(): one row per served K10 function (n8n excluded; no
n8n content exists in this checkout), each row with an artifact link
(serving route plus proving test). Served through the named route
GET /k10/compet/audit (backend app, read-only seam reference).
This module carries a small FIXED recorded dataset: plain in-code strings,
stdlib only, no network, no providers, no I/O, deterministic order.
Sources are recorded strings (never fetched live); snippets are verbatim
recorded strings. Pure functions, no settings or global mutation.
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


def evidence_table() -> list[dict]:
    """Return the fixed recorded R-351 final evidence table.

    One row per served K10 function (n8n excluded), each row with an
    artifact link naming the serving route plus the proving test.
    """
    return [
        {
            "function": "accept",
            "claim": (
                "Final acceptance status is served over Docker plus "
                "declared services plus PowerShell."
            ),
            "source": (
                "recorded: k10 served suite test_k10st4_accept_served "
                "(loopback fixture, not probed live)"
            ),
            "snippet": (
                "verbatim recorded: 'final acceptance covers Docker, "
                "declared services, PowerShell'"
            ),
            "artifact": (
                "route GET /k10/accept proven by "
                "tests/test_k10st4_accept_compet.py::"
                "test_k10st4_accept_served"
            ),
        },
        {
            "function": "combine",
            "claim": (
                "Every package combines best plus KB plus benchmark plus "
                "Watcher on DEFAULT."
            ),
            "source": (
                "recorded: k10 served suite "
                "test_k10st4_combine_default_served (loopback fixture, "
                "not routed live)"
            ),
            "snippet": (
                "verbatim recorded: 'combines best plus KB plus benchmark "
                "plus Watcher on DEFAULT'"
            ),
            "artifact": (
                "route GET /k10/combine proven by "
                "tests/test_k10st4_accept_compet.py::"
                "test_k10st4_combine_default_served"
            ),
        },
        {
            "function": "compet-audit",
            "claim": (
                "Competitive audit claims each carry a recorded source "
                "plus snippet, flow by flow."
            ),
            "source": (
                "recorded: k10 served suite test_k10st4_compet_audit_served "
                "(loopback fixture, not fetched live)"
            ),
            "snippet": (
                "verbatim recorded: 'competitive audit flow by flow; "
                "fetched source plus snippet per claim'"
            ),
            "artifact": (
                "route GET /k10/compet/audit proven by "
                "tests/test_k10st4_accept_compet.py::"
                "test_k10st4_compet_audit_served"
            ),
        },
        {
            "function": "start-demo",
            "claim": (
                "A clean start brings the demo project to green inside "
                "the acceptance drive."
            ),
            "source": (
                "recorded: k10 served suite "
                "test_k10open4_start_demo_brought_to_green (loopback "
                "fixture, not run live)"
            ),
            "snippet": (
                "verbatim recorded: 'demo project brought to green inside "
                "the acceptance drive'"
            ),
            "artifact": (
                "route POST /k10/start/demo proven by "
                "tests/test_k10open4_start_path.py::"
                "test_k10open4_start_demo_brought_to_green"
            ),
        },
        {
            "function": "start-evidence",
            "claim": (
                "A clean start keeps release evidence (screenshots) from "
                "the end-to-end run."
            ),
            "source": (
                "recorded: k10 served suite "
                "test_k10open4_start_evidence_keeps_screenshots (loopback "
                "fixture, not run live)"
            ),
            "snippet": (
                "verbatim recorded: 'clean start keeps release evidence "
                "(screenshots)'"
            ),
            "artifact": (
                "route GET /k10/start/evidence proven by "
                "tests/test_k10open4_start_path.py::"
                "test_k10open4_start_evidence_keeps_screenshots"
            ),
        },
        {
            "function": "start-migrate",
            "claim": (
                "First start migrates settings plus keys, originals kept "
                "(copy, never move)."
            ),
            "source": (
                "recorded: k10 served suites "
                "test_k10open4_start_migrates_settings_keys plus "
                "test_k10st1_migrate_datadir (loopback fixture, not run "
                "live)"
            ),
            "snippet": (
                "verbatim recorded: 'first start migrates settings plus "
                "keys, originals kept'"
            ),
            "artifact": (
                "route GET /k10/start/migrate proven by "
                "tests/test_k10open4_start_path.py::"
                "test_k10open4_start_migrates_settings_keys"
            ),
        },
    ]
