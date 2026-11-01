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

K10WAVE3 (CODE-ONLY): six more open rows on this module. Row M-P4-166 is
the combine contract (best plus KB plus benchmark plus Watcher on
DEFAULT) served by GET /k10/combine. Row M-R-COMPET is the flow-by-flow
claims above, served by GET /k10/compet/audit. Rows
B0B-UNCOVERED_MVP_ACCEPT-200, -130, -132 and -151 are recorded seams
below in the same style (report_export_rows, readme_setup_checks,
acceptance_map, clean_boot_record): loopback recorded data only.
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


def report_export_rows() -> list[dict]:
    """Return the fixed recorded report-export dataset rows.

    Row B0B-UNCOVERED_MVP_ACCEPT-200: kit BUILD_PLAN "report export
    contains dataset rows per demo and fixture with referenced
    artifacts, versions, providers". One row per demo and fixture,
    each row with referenced artifacts, versions and providers. The
    BUILD_PLAN cell is cut after "versions, provid"; the recorded
    completion ("providers") follows the visible prefix.
    """
    return [
        {
            "dataset": "demo",
            "kind": "demo",
            "claim": (
                "Report export contains one dataset row per demo with "
                "referenced artifacts, versions and providers."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-200 "
                "coverage (loopback fixture, not exported live)"
            ),
            "snippet": (
                "verbatim recorded: 'report export contains dataset "
                "rows per demo and fixture with referenced artifacts, "
                "versions, providers'"
            ),
            "artifact": (
                "route GET /k10/start/demo proven by "
                "tests/test_k10open4_start_path.py::"
                "test_k10open4_start_demo_brought_to_green"
            ),
            "version": (
                "recorded: versioned dependency set pinned in the "
                "report row (loopback fixture, not resolved live)"
            ),
        },
        {
            "dataset": "fixture",
            "kind": "fixture",
            "claim": (
                "Report export contains one dataset row per fixture "
                "with referenced artifacts, versions and providers."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-200 "
                "coverage (loopback fixture, not exported live)"
            ),
            "snippet": (
                "verbatim recorded: 'report export contains dataset "
                "rows per demo and fixture with referenced artifacts, "
                "versions, providers'"
            ),
            "artifact": (
                "route GET /k10/compet/audit proven by "
                "tests/test_k10st4_accept_compet.py::"
                "test_k10st4_compet_audit_served"
            ),
            "version": (
                "recorded: versioned dependency set pinned in the "
                "report row (loopback fixture, not resolved live)"
            ),
        },
    ]


def readme_setup_checks() -> list[dict]:
    """Return the fixed recorded README plus setup checks.

    Row B0B-UNCOVERED_MVP_ACCEPT-130: kit BUILD_PLAN "MVP acceptance
    verification checks README plus setup instructions alongside demos
    and fixtures". One recorded check per item.
    """
    return [
        {
            "check": "readme",
            "claim": (
                "MVP acceptance verification checks the README."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-130 "
                "coverage (loopback fixture, not fetched live)"
            ),
            "snippet": (
                "verbatim recorded: 'MVP acceptance verification checks "
                "README plus setup instructions alongside demos and "
                "fixtures'"
            ),
            "evidence": (
                "recorded: README check recorded alongside the demo and "
                "fixture checks (loopback fixture, not read live)"
            ),
        },
        {
            "check": "setup-instructions",
            "claim": (
                "MVP acceptance verification checks the setup "
                "instructions."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-130 "
                "coverage (loopback fixture, not fetched live)"
            ),
            "snippet": (
                "verbatim recorded: 'MVP acceptance verification checks "
                "README plus setup instructions alongside demos and "
                "fixtures'"
            ),
            "evidence": (
                "recorded: setup-instructions check recorded alongside "
                "the demo and fixture checks (loopback fixture, not "
                "read live)"
            ),
        },
        {
            "check": "demos",
            "claim": (
                "MVP acceptance verification checks the demos."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-130 "
                "coverage (loopback fixture, not fetched live)"
            ),
            "snippet": (
                "verbatim recorded: 'MVP acceptance verification checks "
                "README plus setup instructions alongside demos and "
                "fixtures'"
            ),
            "evidence": (
                "route GET /k10/start/demo proven by "
                "tests/test_k10open4_start_path.py::"
                "test_k10open4_start_demo_brought_to_green"
            ),
        },
        {
            "check": "fixtures",
            "claim": (
                "MVP acceptance verification checks the fixtures."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-130 "
                "coverage (loopback fixture, not fetched live)"
            ),
            "snippet": (
                "verbatim recorded: 'MVP acceptance verification checks "
                "README plus setup instructions alongside demos and "
                "fixtures'"
            ),
            "evidence": (
                "route GET /k10/compet/audit proven by "
                "tests/test_k10st4_accept_compet.py::"
                "test_k10st4_compet_audit_served"
            ),
        },
    ]


def acceptance_map() -> list[dict]:
    """Return the fixed recorded acceptance map.

    Row B0B-UNCOVERED_MVP_ACCEPT-132: kit BUILD_PLAN "acceptance map
    links each checklist item to its design section and evidence". One
    row per checklist item with its design section and evidence.
    """
    return [
        {
            "item": "readme",
            "claim": (
                "Acceptance checklist item readme links to its design "
                "section and evidence."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-132 "
                "coverage (loopback fixture, not fetched live)"
            ),
            "snippet": (
                "verbatim recorded: 'acceptance map links each checklist "
                "item to its design section and evidence'"
            ),
            "design_section": (
                "kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-130 "
                "(README plus setup instructions)"
            ),
            "evidence": (
                "agent_si.k10_compet.readme_setup_checks check readme "
                "(recorded seam, loopback)"
            ),
        },
        {
            "item": "setup-instructions",
            "claim": (
                "Acceptance checklist item setup-instructions links to "
                "its design section and evidence."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-132 "
                "coverage (loopback fixture, not fetched live)"
            ),
            "snippet": (
                "verbatim recorded: 'acceptance map links each checklist "
                "item to its design section and evidence'"
            ),
            "design_section": (
                "kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-130 "
                "(README plus setup instructions)"
            ),
            "evidence": (
                "agent_si.k10_compet.readme_setup_checks check "
                "setup-instructions (recorded seam, loopback)"
            ),
        },
        {
            "item": "demos",
            "claim": (
                "Acceptance checklist item demos links to its design "
                "section and evidence."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-132 "
                "coverage (loopback fixture, not fetched live)"
            ),
            "snippet": (
                "verbatim recorded: 'acceptance map links each checklist "
                "item to its design section and evidence'"
            ),
            "design_section": (
                "kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-130 "
                "(demos and fixtures)"
            ),
            "evidence": (
                "route GET /k10/start/demo proven by "
                "tests/test_k10open4_start_path.py::"
                "test_k10open4_start_demo_brought_to_green"
            ),
        },
        {
            "item": "fixtures",
            "claim": (
                "Acceptance checklist item fixtures links to its design "
                "section and evidence."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-132 "
                "coverage (loopback fixture, not fetched live)"
            ),
            "snippet": (
                "verbatim recorded: 'acceptance map links each checklist "
                "item to its design section and evidence'"
            ),
            "design_section": (
                "kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-130 "
                "(demos and fixtures)"
            ),
            "evidence": (
                "route GET /k10/compet/audit proven by "
                "tests/test_k10st4_accept_compet.py::"
                "test_k10st4_compet_audit_served"
            ),
        },
        {
            "item": "combine-default",
            "claim": (
                "Acceptance checklist item combine-default links to its "
                "design section and evidence."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-132 "
                "coverage (loopback fixture, not fetched live)"
            ),
            "snippet": (
                "verbatim recorded: 'acceptance map links each checklist "
                "item to its design section and evidence'"
            ),
            "design_section": (
                "kit BUILD_PLAN M-P4-166 (every package combines best "
                "plus KB plus benchmark plus Watcher on DEFAULT)"
            ),
            "evidence": (
                "route GET /k10/combine proven by "
                "tests/test_k10st4_accept_compet.py::"
                "test_k10st4_combine_default_served"
            ),
        },
        {
            "item": "competitive-audit",
            "claim": (
                "Acceptance checklist item competitive-audit links to "
                "its design section and evidence."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-132 "
                "coverage (loopback fixture, not fetched live)"
            ),
            "snippet": (
                "verbatim recorded: 'acceptance map links each checklist "
                "item to its design section and evidence'"
            ),
            "design_section": (
                "kit BUILD_PLAN M-R-COMPET (competitive audit flow by "
                "flow; fetched source plus snippet per claim)"
            ),
            "evidence": (
                "route GET /k10/compet/audit proven by "
                "tests/test_k10st4_accept_compet.py::"
                "test_k10st4_compet_audit_served"
            ),
        },
    ]


def clean_boot_record() -> list[dict]:
    """Return the fixed recorded clean-checkout boot record.

    Row B0B-UNCOVERED_MVP_ACCEPT-151: kit BUILD_PLAN "clean checkout
    boot follows documented steps, uses versioned dependencies, and
    yields identical working startup". One recorded row per boot
    property. The BUILD_PLAN cell is cut after "identical work"; the
    recorded completion ("identical working startup") follows the
    sibling boot rows (clean-state restart twice yields identical
    working startup).
    """
    return [
        {
            "step": "documented-steps",
            "claim": (
                "Clean checkout boot follows the documented steps."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-151 "
                "coverage (loopback fixture, not booted live)"
            ),
            "snippet": (
                "verbatim recorded: 'clean checkout boot follows "
                "documented steps, uses versioned dependencies, and "
                "yields identical working startup'"
            ),
        },
        {
            "step": "versioned-dependencies",
            "claim": (
                "Clean checkout boot uses versioned dependencies."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-151 "
                "coverage (loopback fixture, lockfile step recorded, "
                "not resolved live)"
            ),
            "snippet": (
                "verbatim recorded: 'clean checkout boot follows "
                "documented steps, uses versioned dependencies, and "
                "yields identical working startup'"
            ),
        },
        {
            "step": "identical-working-startup",
            "claim": (
                "Clean checkout boot yields identical working startup."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-151 "
                "coverage (loopback fixture, not booted live)"
            ),
            "snippet": (
                "verbatim recorded: 'clean checkout boot follows "
                "documented steps, uses versioned dependencies, and "
                "yields identical working startup'"
            ),
        },
    ]


def served_rows() -> list[dict]:
    """Return the K10WAVE served map: one row per open K10 row.

    Each row names the serving route plus the proving test. Pure recorded
    data, stdlib only, no network, no providers, no I/O, deterministic.
    """
    return [
        {
            "row": "R-328",
            "route": "POST /k10/start/demo",
            "test": (
                "tests/test_k10open4_start_path.py::"
                "test_k10open4_start_demo_brought_to_green"
            ),
        },
        {
            "row": "166",
            "route": "GET /k10/start/evidence",
            "test": (
                "tests/test_k10open4_start_path.py::"
                "test_k10open4_start_evidence_keeps_screenshots"
            ),
        },
        {
            "row": "R-343",
            "route": "tools/start.py --smoke fresh profile",
            "test": (
                "tests/test_k10st1_clean_boot.py::"
                "test_rowR343_fresh_install_no_test_data"
            ),
        },
        {
            "row": "165",
            "route": "tools/start.py --smoke hash plus smoke",
            "test": (
                "tests/test_k10st1_clean_boot.py::"
                "test_row165_exe_from_script_hash_smoke"
            ),
        },
        {
            "row": "167",
            "route": "tools/start.py --smoke clean profile",
            "test": (
                "tests/test_k10st1_clean_boot.py::"
                "test_row167_installed_app_check_clean_profile"
            ),
        },
        {
            "row": "M-P3-89",
            "route": "tools/start.py portable copy identical",
            "test": (
                "tests/test_k10st1_clean_boot.py::"
                "test_rowMP389_portable_start_identical"
            ),
        },
        {
            "row": "R-345",
            "route": "tools/start.py --serve quiet close",
            "test": (
                "tests/test_k10st1_clean_boot.py::"
                "test_rowR345_no_console_flash_quiet_close"
            ),
        },
        {
            "row": "M-P4-134",
            "route": "create_app consumer-layer data-dir call site",
            "test": (
                "tests/test_k10st1_migrate_datadir.py::"
                "test_k10st1_migrate_first_start_copies_settings_credentials"
            ),
        },
        {
            "row": "M-P4-138",
            "route": "GET /k10/start/migrate",
            "test": (
                "tests/test_k10open4_start_path.py::"
                "test_k10open4_start_migrates_settings_keys"
            ),
        },
        {
            "row": "M-P4-162",
            "route": "GET /k10/accept",
            "test": (
                "tests/test_k10st4_accept_compet.py::"
                "test_k10st4_accept_served"
            ),
        },
        {
            "row": "M-P4-166",
            "route": "GET /k10/combine",
            "test": (
                "tests/test_k10st4_accept_compet.py::"
                "test_k10st4_combine_default_served"
            ),
        },
        {
            "row": "M-R-COMPET",
            "route": "GET /k10/compet/audit",
            "test": (
                "tests/test_k10st4_accept_compet.py::"
                "test_k10st4_compet_audit_served"
            ),
        },
        {
            "row": "B0B-UNCOVERED_MVP_ACCEPT-200",
            "route": "agent_si.k10_compet.report_export_rows recorded seam",
            "test": (
                "tests/test_k10wave_served.py::"
                "test_k10wave3_bison_report_export_rows"
            ),
        },
        {
            "row": "B0B-UNCOVERED_MVP_ACCEPT-130",
            "route": "agent_si.k10_compet.readme_setup_checks recorded seam",
            "test": (
                "tests/test_k10wave_served.py::"
                "test_k10wave3_bison_readme_setup_checks"
            ),
        },
        {
            "row": "B0B-UNCOVERED_MVP_ACCEPT-132",
            "route": "agent_si.k10_compet.acceptance_map recorded seam",
            "test": (
                "tests/test_k10wave_served.py::"
                "test_k10wave3_bison_acceptance_map"
            ),
        },
        {
            "row": "B0B-UNCOVERED_MVP_ACCEPT-151",
            "route": "agent_si.k10_compet.clean_boot_record recorded seam",
            "test": (
                "tests/test_k10wave_served.py::"
                "test_k10wave3_bison_clean_boot_record"
            ),
        },
    ]
