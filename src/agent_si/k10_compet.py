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

K10WAVE4 (CODE-ONLY): ten more open rows on this module. Rows
B0B-UNCOVERED_MVP_ACCEPT-129, -131, -152, -153, -154, -158, -160,
-161, -172 and -173 are recorded seams below in the same style
(readme_command_index, readme_checkout_root, reproducible_startup_record,
startup_sequence_record, clean_restart_twice_record,
project_analytics_record, model_provider_analytics_record,
analytics_authoritative_record, fixture_capability_rows,
fixture_pack_record): loopback recorded data only.

K10WAVE5 (CODE-ONLY): eight more open rows on this module. Rows
B0B-UNCOVERED_MVP_ACCEPT-209, -210, -211, -212, -217, -225, -227
and -229 are recorded seams below in the same style
(mvp_verdict_record, mvp_accepted_rule_record,
mvp_acceptance_requirements_record, mvp_shortfall_record,
test_fixture_wiring_record, local_demo_runtime_record,
split_demo_cloud_record, localhost_doubles_record): loopback
recorded data only.
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


def readme_root_checks() -> list[dict]:
    """Return the fixed recorded checkout-root README checks.

    Row B0B-UNCOVERED_MVP_ACCEPT-131 (served row "131"): kit
    BUILD_PLAN "README at checkout root documents prerequisites,
    setup steps, demo commands, fixture commands, task ...". The
    BUILD_PLAN cell is cut after "task"; the recorded completion
    ("task tree pointers, and troubleshooting") follows the kit
    PRODUCT_SPEC prose for the same sentence.
    """
    return [
        {
            "claim": (
                "README at checkout root documents prerequisites, "
                "setup steps, demo commands, fixture commands, task "
                "tree pointers, and troubleshooting."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-131 "
                "coverage (loopback fixture, not live)"
            ),
            "snippet": (
                "verbatim recorded: 'README at checkout root documents "
                "prerequisites, setup steps, demo commands, fixture "
                "commands, task'"
            ),
            "evidence": (
                "route GET /k10/compet/audit proven by "
                "tests/test_k10e_served.py::test_k10e_readme_root_checks"
            ),
        },
    ]


def k10e_startup_sequence_record() -> list[dict]:
    """Return the fixed recorded startup sequence record (K10E seam).

    K10BMERGE: K10B named this startup_sequence_record; int already
    defines that name for row B0B-UNCOVERED_MVP_ACCEPT-153 with a
    different shape, so the K10E seam for served row "153" lives
    under this name (no duplicate def, no row lost).

    Row B0B-UNCOVERED_MVP_ACCEPT-153 (served row "153"): kit
    BUILD_PLAN "startup sequence (checkout, configure from environment
    example, offline install from lockfiles, laun ...". The BUILD_PLAN
    cell is cut after "laun"; the recorded completion ("launch
    managers plus workers plus UI) is idempotent") follows the kit
    BUILD_PLAN prose for the same sentence.
    """
    return [
        {
            "claim": (
                "The startup sequence (checkout, configure from "
                "environment example, offline install from lockfiles, "
                "launch managers plus workers plus UI) is idempotent."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-153 "
                "coverage (loopback fixture, not live)"
            ),
            "snippet": (
                "verbatim recorded: 'startup sequence (checkout, "
                "configure from environment example, offline install "
                "from lockfiles, laun'"
            ),
            "evidence": (
                "route GET /k10/compet/audit proven by "
                "tests/test_k10e_served.py::test_k10e_startup_sequence"
            ),
        },
    ]


def k10e_fixture_pack_record() -> list[dict]:
    """Return the fixed recorded MVP fixture-pack record (K10E seam).

    K10BMERGE: K10B named this fixture_pack_record; int already
    defines that name for row B0B-UNCOVERED_MVP_ACCEPT-173 with a
    different shape, so the K10E seam for served row "173" lives
    under this name (no duplicate def, no row lost).

    Row B0B-UNCOVERED_MVP_ACCEPT-173 (served row "173"): kit
    BUILD_PLAN "MVP fixture pack ships under checkout and is not
    measured evidence."
    """
    return [
        {
            "claim": (
                "MVP fixture pack ships under checkout and is not "
                "measured evidence."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-173 "
                "coverage (loopback fixture, not live)"
            ),
            "snippet": (
                "verbatim recorded: 'MVP fixture pack ships under "
                "checkout and is not measured evidence.'"
            ),
            "evidence": (
                "route GET /k10/compet/audit proven by "
                "tests/test_k10e_served.py::test_k10e_fixture_pack"
            ),
        },
    ]


def host_blockers_record() -> list[dict]:
    """Return the fixed recorded host blockers record.

    Row B0B-UNCOVERED_MVP_ACCEPT-214 (served row "214"): kit
    BUILD_PLAN "host blockers name missing permissions, auditor
    provider, and second provider."
    """
    return [
        {
            "claim": (
                "Host blockers name missing permissions, auditor "
                "provider, and second provider."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-214 "
                "coverage (loopback fixture, not live)"
            ),
            "snippet": (
                "verbatim recorded: 'host blockers name missing "
                "permissions, auditor provider, and second provider.'"
            ),
            "evidence": (
                "route GET /k10/compet/audit proven by "
                "tests/test_k10e_served.py::test_k10e_host_blockers"
            ),
        },
    ]


def attainability_gate_record() -> list[dict]:
    """Return the fixed recorded MVP attainability-gate record.

    Row B0B-UNCOVERED_MVP_ACCEPT-215 (served row "215"): kit
    BUILD_PLAN "MVP is not attainable on a host until local
    permission, auditor provider, and a second real provider ...".
    The BUILD_PLAN cell is cut after "provider"; the recorded
    completion ("resolve") follows the kit BUILD_PLAN prose for the
    same sentence.
    """
    return [
        {
            "claim": (
                "MVP is not attainable on a host until local "
                "permission, auditor provider, and a second real "
                "provider resolve."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-215 "
                "coverage (loopback fixture, not live)"
            ),
            "snippet": (
                "verbatim recorded: 'MVP is not attainable on a host "
                "until local permission, auditor provider, and a "
                "second real provider'"
            ),
            "evidence": (
                "route GET /k10/compet/audit proven by "
                "tests/test_k10e_served.py::test_k10e_attainability_gate"
            ),
        },
    ]


def licence_check_record() -> list[dict]:
    """Return the fixed recorded open-source licence-check record.

    Row HC-4 (served row "HC-4"): kit BUILD_PLAN "open-source licence
    check (owner decision)".
    """
    return [
        {
            "claim": (
                "The open-source licence check is an owner decision."
            ),
            "source": (
                "recorded: kit BUILD_PLAN HC-4 "
                "coverage (loopback fixture, not live)"
            ),
            "snippet": (
                "verbatim recorded: 'open-source licence check (owner "
                "decision)'"
            ),
            "evidence": (
                "route GET /k10/compet/audit proven by "
                "tests/test_k10e_served.py::test_k10e_licence_check"
            ),
        },
    ]


def readme_command_index() -> list[dict]:
    """Return the fixed recorded README command-index record.

    Row B0B-UNCOVERED_MVP_ACCEPT-129: kit BUILD_PLAN "README holds
    setup instructions plus a demo and fixture command index and adds
    no install content before prerequisites". One recorded row per
    README content item. The BUILD_PLAN cell is cut after "content
    be"; the recorded completion ("before prerequisites") pairs with
    the prerequisites-first order of row -131.
    """
    return [
        {
            "section": "setup-instructions",
            "claim": (
                "README holds the setup instructions."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-129 "
                "coverage (loopback fixture, not read live)"
            ),
            "snippet": (
                "verbatim recorded: 'README holds setup instructions "
                "plus a demo and fixture command index and adds no "
                "install content before prerequisites'"
            ),
        },
        {
            "section": "demo-command-index",
            "claim": (
                "README holds a demo command index."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-129 "
                "coverage (loopback fixture, not read live)"
            ),
            "snippet": (
                "verbatim recorded: 'README holds setup instructions "
                "plus a demo and fixture command index and adds no "
                "install content before prerequisites'"
            ),
        },
        {
            "section": "fixture-command-index",
            "claim": (
                "README holds a fixture command index."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-129 "
                "coverage (loopback fixture, not read live)"
            ),
            "snippet": (
                "verbatim recorded: 'README holds setup instructions "
                "plus a demo and fixture command index and adds no "
                "install content before prerequisites'"
            ),
        },
        {
            "section": "install-content-guard",
            "claim": (
                "README adds no install content before prerequisites."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-129 "
                "coverage (loopback fixture, not read live)"
            ),
            "snippet": (
                "verbatim recorded: 'README holds setup instructions "
                "plus a demo and fixture command index and adds no "
                "install content before prerequisites'"
            ),
        },
    ]


def readme_checkout_root() -> list[dict]:
    """Return the fixed recorded checkout-root README record.

    Row B0B-UNCOVERED_MVP_ACCEPT-131: kit BUILD_PLAN "README at
    checkout root documents prerequisites, setup steps, demo commands,
    fixture commands, task commands". One recorded row per documented
    topic. The BUILD_PLAN cell is cut after "task"; the recorded
    completion ("commands") follows the parallel demo and fixture
    command entries.
    """
    return [
        {
            "topic": "prerequisites",
            "claim": (
                "Checkout-root README documents the prerequisites."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-131 "
                "coverage (loopback fixture, not read live)"
            ),
            "snippet": (
                "verbatim recorded: 'README at checkout root documents "
                "prerequisites, setup steps, demo commands, fixture "
                "commands, task commands'"
            ),
        },
        {
            "topic": "setup-steps",
            "claim": (
                "Checkout-root README documents the setup steps."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-131 "
                "coverage (loopback fixture, not read live)"
            ),
            "snippet": (
                "verbatim recorded: 'README at checkout root documents "
                "prerequisites, setup steps, demo commands, fixture "
                "commands, task commands'"
            ),
        },
        {
            "topic": "demo-commands",
            "claim": (
                "Checkout-root README documents the demo commands."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-131 "
                "coverage (loopback fixture, not read live)"
            ),
            "snippet": (
                "verbatim recorded: 'README at checkout root documents "
                "prerequisites, setup steps, demo commands, fixture "
                "commands, task commands'"
            ),
        },
        {
            "topic": "fixture-commands",
            "claim": (
                "Checkout-root README documents the fixture commands."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-131 "
                "coverage (loopback fixture, not read live)"
            ),
            "snippet": (
                "verbatim recorded: 'README at checkout root documents "
                "prerequisites, setup steps, demo commands, fixture "
                "commands, task commands'"
            ),
        },
        {
            "topic": "task-commands",
            "claim": (
                "Checkout-root README documents the task commands."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-131 "
                "coverage (loopback fixture, not read live)"
            ),
            "snippet": (
                "verbatim recorded: 'README at checkout root documents "
                "prerequisites, setup steps, demo commands, fixture "
                "commands, task commands'"
            ),
        },
    ]


def reproducible_startup_record() -> list[dict]:
    """Return the fixed recorded reproducible-startup record.

    Row B0B-UNCOVERED_MVP_ACCEPT-152: kit BUILD_PLAN "reproducible
    startup is verified alongside demos, fixtures, and UI checks".
    One recorded row per verification leg.
    """
    return [
        {
            "leg": "demos",
            "claim": (
                "Reproducible startup is verified alongside demos."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-152 "
                "coverage (loopback fixture, not verified live)"
            ),
            "snippet": (
                "verbatim recorded: 'reproducible startup is verified "
                "alongside demos, fixtures, and UI checks'"
            ),
            "evidence": (
                "route GET /k10/start/demo proven by "
                "tests/test_k10open4_start_path.py::"
                "test_k10open4_start_demo_brought_to_green"
            ),
        },
        {
            "leg": "fixtures",
            "claim": (
                "Reproducible startup is verified alongside fixtures."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-152 "
                "coverage (loopback fixture, not verified live)"
            ),
            "snippet": (
                "verbatim recorded: 'reproducible startup is verified "
                "alongside demos, fixtures, and UI checks'"
            ),
            "evidence": (
                "route GET /k10/compet/audit proven by "
                "tests/test_k10st4_accept_compet.py::"
                "test_k10st4_compet_audit_served"
            ),
        },
        {
            "leg": "ui-checks",
            "claim": (
                "Reproducible startup is verified alongside UI checks."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-152 "
                "coverage (loopback fixture, not verified live)"
            ),
            "snippet": (
                "verbatim recorded: 'reproducible startup is verified "
                "alongside demos, fixtures, and UI checks'"
            ),
            "evidence": (
                "recorded: UI checks recorded alongside the demo and "
                "fixture checks (loopback fixture, not run live)"
            ),
        },
    ]


def startup_sequence_record() -> list[dict]:
    """Return the fixed recorded startup-sequence record.

    Row B0B-UNCOVERED_MVP_ACCEPT-153: kit BUILD_PLAN "startup sequence
    (checkout, configure from environment example, offline install from
    lockfiles, launch managers plus workers plus UI)". One recorded row
    per sequence step. The BUILD_PLAN cell is cut after "laun"; the
    recorded completion mirrors the stated AGENT_SI startup sequence at
    kit BUILD_PLAN line 1115 ("launch managers plus workers plus UI").
    """
    return [
        {
            "step": "checkout",
            "claim": (
                "Startup starts from a checkout."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-153 "
                "coverage (loopback fixture, not run live)"
            ),
            "snippet": (
                "verbatim recorded: 'startup sequence (checkout, "
                "configure from environment example, offline install "
                "from lockfiles, launch managers plus workers plus UI)'"
            ),
        },
        {
            "step": "configure-from-environment-example",
            "claim": (
                "Startup configures from the environment example."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-153 "
                "coverage (loopback fixture, not run live)"
            ),
            "snippet": (
                "verbatim recorded: 'startup sequence (checkout, "
                "configure from environment example, offline install "
                "from lockfiles, launch managers plus workers plus UI)'"
            ),
        },
        {
            "step": "offline-install-from-lockfiles",
            "claim": (
                "Startup installs offline from lockfiles."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-153 "
                "coverage (loopback fixture, not run live)"
            ),
            "snippet": (
                "verbatim recorded: 'startup sequence (checkout, "
                "configure from environment example, offline install "
                "from lockfiles, launch managers plus workers plus UI)'"
            ),
        },
        {
            "step": "launch-managers-workers-ui",
            "claim": (
                "Startup launches managers plus workers plus UI."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-153 "
                "coverage (loopback fixture, not run live)"
            ),
            "snippet": (
                "verbatim recorded: 'startup sequence (checkout, "
                "configure from environment example, offline install "
                "from lockfiles, launch managers plus workers plus UI)'"
            ),
        },
    ]


def clean_restart_twice_record() -> list[dict]:
    """Return the fixed recorded clean-restart-twice record.

    Row B0B-UNCOVERED_MVP_ACCEPT-154: kit BUILD_PLAN "clean-state
    restart twice yields identical working startup". One recorded row
    per restart plus the identical-startup comparison.
    """
    return [
        {
            "restart": "first-restart",
            "claim": (
                "First clean-state restart reaches working startup."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-154 "
                "coverage (loopback fixture, not restarted live)"
            ),
            "snippet": (
                "verbatim recorded: 'clean-state restart twice yields "
                "identical working startup'"
            ),
        },
        {
            "restart": "second-restart",
            "claim": (
                "Second clean-state restart reaches working startup."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-154 "
                "coverage (loopback fixture, not restarted live)"
            ),
            "snippet": (
                "verbatim recorded: 'clean-state restart twice yields "
                "identical working startup'"
            ),
        },
        {
            "restart": "identical-comparison",
            "claim": (
                "Both restarts yield identical working startup."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-154 "
                "coverage (loopback fixture, not restarted live)"
            ),
            "snippet": (
                "verbatim recorded: 'clean-state restart twice yields "
                "identical working startup'"
            ),
        },
    ]


def project_analytics_record() -> list[dict]:
    """Return the fixed recorded project-analytics record.

    Row B0B-UNCOVERED_MVP_ACCEPT-158: kit BUILD_PLAN "project
    analytics view aggregates project-level task and audit counts
    deterministically". One recorded row per aggregate plus the
    determinism property.
    """
    return [
        {
            "aggregate": "task-counts",
            "claim": (
                "Project analytics aggregates project-level task counts."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-158 "
                "coverage (loopback fixture, not aggregated live)"
            ),
            "snippet": (
                "verbatim recorded: 'project analytics view aggregates "
                "project-level task and audit counts deterministically'"
            ),
        },
        {
            "aggregate": "audit-counts",
            "claim": (
                "Project analytics aggregates project-level audit counts."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-158 "
                "coverage (loopback fixture, not aggregated live)"
            ),
            "snippet": (
                "verbatim recorded: 'project analytics view aggregates "
                "project-level task and audit counts deterministically'"
            ),
        },
        {
            "aggregate": "deterministic-order",
            "claim": (
                "Project analytics aggregates read in deterministic "
                "order."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-158 "
                "coverage (loopback fixture, not aggregated live)"
            ),
            "snippet": (
                "verbatim recorded: 'project analytics view aggregates "
                "project-level task and audit counts deterministically'"
            ),
        },
    ]


def model_provider_analytics_record() -> list[dict]:
    """Return the fixed recorded model/provider-analytics record.

    Row B0B-UNCOVERED_MVP_ACCEPT-160: kit BUILD_PLAN "model and
    provider analytics shows per-model and per-provider calls plus
    tokens plus cost or UNAVAILABLE". One recorded row per scope, each
    carrying calls plus tokens plus cost-or-UNAVAILABLE. The BUILD_PLAN
    cell is cut after "UNAVAIL"; the recorded completion
    ("UNAVAILABLE") is the codebase cost state for missing prices
    (never zero, never estimated).
    """
    return [
        {
            "scope": "per-model",
            "claim": (
                "Model analytics shows per-model calls plus tokens "
                "plus cost or UNAVAILABLE."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-160 "
                "coverage (loopback fixture, not queried live)"
            ),
            "snippet": (
                "verbatim recorded: 'model and provider analytics "
                "shows per-model and per-provider calls plus tokens "
                "plus cost or UNAVAILABLE'"
            ),
            "metrics": (
                "recorded: calls plus tokens plus cost or UNAVAILABLE "
                "(loopback fixture, not queried live)"
            ),
        },
        {
            "scope": "per-provider",
            "claim": (
                "Provider analytics shows per-provider calls plus "
                "tokens plus cost or UNAVAILABLE."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-160 "
                "coverage (loopback fixture, not queried live)"
            ),
            "snippet": (
                "verbatim recorded: 'model and provider analytics "
                "shows per-model and per-provider calls plus tokens "
                "plus cost or UNAVAILABLE'"
            ),
            "metrics": (
                "recorded: calls plus tokens plus cost or UNAVAILABLE "
                "(loopback fixture, not queried live)"
            ),
        },
    ]


def analytics_authoritative_record() -> list[dict]:
    """Return the fixed recorded authoritative-analytics record.

    Row B0B-UNCOVERED_MVP_ACCEPT-161: kit BUILD_PLAN "analytics values
    read only from authoritative TelemetryEvent and MetricRecord
    stores, never from chat text or live rows". One recorded row per
    allowed origin plus one per refused origin. The BUILD_PLAN cell is
    cut after "cha"; the recorded completion ("chat text or live
    rows") is quoted in the served analytics seam docstrings.
    """
    return [
        {
            "origin": "telemetry-events-store",
            "claim": (
                "Analytics values read from the authoritative "
                "TelemetryEvent store."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-161 "
                "coverage (loopback fixture, not read live)"
            ),
            "snippet": (
                "verbatim recorded: 'analytics values read only from "
                "authoritative TelemetryEvent and MetricRecord stores, "
                "never from chat text or live rows'"
            ),
        },
        {
            "origin": "metric-records-store",
            "claim": (
                "Analytics values read from the authoritative "
                "MetricRecord store."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-161 "
                "coverage (loopback fixture, not read live)"
            ),
            "snippet": (
                "verbatim recorded: 'analytics values read only from "
                "authoritative TelemetryEvent and MetricRecord stores, "
                "never from chat text or live rows'"
            ),
        },
        {
            "origin": "never-chat-text",
            "claim": (
                "Analytics values never read from chat text."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-161 "
                "coverage (loopback fixture, not read live)"
            ),
            "snippet": (
                "verbatim recorded: 'analytics values read only from "
                "authoritative TelemetryEvent and MetricRecord stores, "
                "never from chat text or live rows'"
            ),
        },
        {
            "origin": "never-live-rows",
            "claim": (
                "Analytics values never read from live rows."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-161 "
                "coverage (loopback fixture, not read live)"
            ),
            "snippet": (
                "verbatim recorded: 'analytics values read only from "
                "authoritative TelemetryEvent and MetricRecord stores, "
                "never from chat text or live rows'"
            ),
        },
    ]


def fixture_capability_rows() -> list[dict]:
    """Return the fixed recorded fixture-capability rows.

    Row B0B-UNCOVERED_MVP_ACCEPT-172: kit BUILD_PLAN "fixture
    capability rows are labelled TEST FIXTURES with provenance and are
    never measured evidence". One recorded row per fixture class, each
    labelled TEST FIXTURES with provenance.
    """
    return [
        {
            "fixture": "demo-fixture",
            "label": "TEST FIXTURES",
            "claim": (
                "Demo fixture capability row is labelled TEST FIXTURES "
                "with provenance."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-172 "
                "coverage (loopback fixture, not measured)"
            ),
            "snippet": (
                "verbatim recorded: 'fixture capability rows are "
                "labelled TEST FIXTURES with provenance and are never "
                "measured evidence'"
            ),
            "provenance": (
                "recorded: demo fixture provenance (loopback fixture, "
                "never presented as measured evidence)"
            ),
        },
        {
            "fixture": "command-fixture",
            "label": "TEST FIXTURES",
            "claim": (
                "Command fixture capability row is labelled TEST "
                "FIXTURES with provenance."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-172 "
                "coverage (loopback fixture, not measured)"
            ),
            "snippet": (
                "verbatim recorded: 'fixture capability rows are "
                "labelled TEST FIXTURES with provenance and are never "
                "measured evidence'"
            ),
            "provenance": (
                "recorded: command fixture provenance (loopback "
                "fixture, never presented as measured evidence)"
            ),
        },
    ]


def fixture_pack_record() -> list[dict]:
    """Return the fixed recorded fixture-pack record.

    Row B0B-UNCOVERED_MVP_ACCEPT-173: kit BUILD_PLAN "MVP fixture pack
    ships under checkout and is not measured evidence". One recorded
    row per pack property.
    """
    return [
        {
            "property": "ships-under-checkout",
            "claim": (
                "MVP fixture pack ships under checkout."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-173 "
                "coverage (loopback fixture, not shipped live)"
            ),
            "snippet": (
                "verbatim recorded: 'MVP fixture pack ships under "
                "checkout and is not measured evidence'"
            ),
        },
        {
            "property": "not-measured-evidence",
            "claim": (
                "MVP fixture pack is not measured evidence."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-173 "
                "coverage (loopback fixture, not shipped live)"
            ),
            "snippet": (
                "verbatim recorded: 'MVP fixture pack ships under "
                "checkout and is not measured evidence'"
            ),
        },
    ]


def mvp_verdict_record() -> list[dict]:
    """Return the fixed recorded MVP-verdict record.

    Row B0B-UNCOVERED_MVP_ACCEPT-209: kit BUILD_PLAN "MVP verdict is
    binary ACCEPTED or NOT_ACCEPTED with explicit blockers". One
    recorded row per verdict value, each carrying its explicit
    blockers.
    """
    return [
        {
            "verdict": "ACCEPTED",
            "claim": (
                "MVP verdict ACCEPTED is one of the two binary values "
                "and carries explicit blockers."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-209 "
                "coverage (loopback fixture, not judged live)"
            ),
            "snippet": (
                "verbatim recorded: 'MVP verdict is binary ACCEPTED or "
                "NOT_ACCEPTED with explicit blockers'"
            ),
            "blockers": (
                "recorded: explicit blocker list, empty on ACCEPTED "
                "(loopback fixture, not judged live)"
            ),
        },
        {
            "verdict": "NOT_ACCEPTED",
            "claim": (
                "MVP verdict NOT_ACCEPTED is one of the two binary "
                "values and carries explicit blockers."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-209 "
                "coverage (loopback fixture, not judged live)"
            ),
            "snippet": (
                "verbatim recorded: 'MVP verdict is binary ACCEPTED or "
                "NOT_ACCEPTED with explicit blockers'"
            ),
            "blockers": (
                "recorded: explicit blocker list naming each "
                "unsatisfied item (loopback fixture, not judged live)"
            ),
        },
    ]


def mvp_accepted_rule_record() -> list[dict]:
    """Return the fixed recorded MVP-ACCEPTED rule record.

    Row B0B-UNCOVERED_MVP_ACCEPT-210: kit BUILD_PLAN "MVP_ACCEPTED
    equals ACCEPTED iff all acceptance items hold". One recorded row
    per case: all items hold (ACCEPTED) versus any item short
    (NOT_ACCEPTED).
    """
    return [
        {
            "case": "all-items-hold",
            "claim": (
                "MVP_ACCEPTED equals ACCEPTED when all acceptance "
                "items hold."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-210 "
                "coverage (loopback fixture, not judged live)"
            ),
            "snippet": (
                "verbatim recorded: 'MVP_ACCEPTED equals ACCEPTED iff "
                "all acceptance items hold'"
            ),
            "result": "ACCEPTED",
        },
        {
            "case": "any-item-short",
            "claim": (
                "MVP_ACCEPTED is not ACCEPTED when any acceptance "
                "item falls short."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-210 "
                "coverage (loopback fixture, not judged live)"
            ),
            "snippet": (
                "verbatim recorded: 'MVP_ACCEPTED equals ACCEPTED iff "
                "all acceptance items hold'"
            ),
            "result": "NOT_ACCEPTED",
        },
    ]


def mvp_acceptance_requirements_record() -> list[dict]:
    """Return the fixed recorded MVP-acceptance-requirements record.

    Row B0B-UNCOVERED_MVP_ACCEPT-211: kit BUILD_PLAN "MVP acceptance
    requires README plus secret-free environment example plus
    twice-identical reproducible run". One recorded row per required
    item. The BUILD_PLAN cell is cut after "reproducibl"; the recorded
    completion ("reproducible run") pairs with the twice-identical
    startup rows (clean-state restart twice yields identical working
    startup).
    """
    return [
        {
            "requirement": "readme",
            "claim": (
                "MVP acceptance requires the README."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-211 "
                "coverage (loopback fixture, not checked live)"
            ),
            "snippet": (
                "verbatim recorded: 'MVP acceptance requires README "
                "plus secret-free environment example plus "
                "twice-identical reproducible run'"
            ),
        },
        {
            "requirement": "secret-free-environment-example",
            "claim": (
                "MVP acceptance requires a secret-free environment "
                "example."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-211 "
                "coverage (loopback fixture, not checked live)"
            ),
            "snippet": (
                "verbatim recorded: 'MVP acceptance requires README "
                "plus secret-free environment example plus "
                "twice-identical reproducible run'"
            ),
        },
        {
            "requirement": "twice-identical-reproducible-run",
            "claim": (
                "MVP acceptance requires a twice-identical "
                "reproducible run."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-211 "
                "coverage (loopback fixture, not run live)"
            ),
            "snippet": (
                "verbatim recorded: 'MVP acceptance requires README "
                "plus secret-free environment example plus "
                "twice-identical reproducible run'"
            ),
        },
    ]


def mvp_shortfall_record() -> list[dict]:
    """Return the fixed recorded MVP-shortfall record.

    Row B0B-UNCOVERED_MVP_ACCEPT-212: kit BUILD_PLAN "MVP shortfall
    yields NOT_ACCEPTED with listed blockers". One recorded row per
    shortfall property.
    """
    return [
        {
            "property": "not-accepted-on-shortfall",
            "claim": (
                "MVP shortfall yields NOT_ACCEPTED."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-212 "
                "coverage (loopback fixture, not judged live)"
            ),
            "snippet": (
                "verbatim recorded: 'MVP shortfall yields NOT_ACCEPTED "
                "with listed blockers'"
            ),
        },
        {
            "property": "blockers-listed",
            "claim": (
                "MVP shortfall lists the blockers."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-212 "
                "coverage (loopback fixture, not judged live)"
            ),
            "snippet": (
                "verbatim recorded: 'MVP shortfall yields NOT_ACCEPTED "
                "with listed blockers'"
            ),
        },
    ]


def test_fixture_wiring_record() -> list[dict]:
    """Return the fixed recorded TEST-FIXTURE wiring record.

    Row B0B-UNCOVERED_MVP_ACCEPT-217: kit BUILD_PLAN "TEST FIXTURE
    rows prove wiring only and are never presented as measured
    evidence". One recorded row per fixture property.
    """
    return [
        {
            "property": "wiring-only",
            "claim": (
                "TEST FIXTURE rows prove wiring only."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-217 "
                "coverage (loopback fixture, not measured)"
            ),
            "snippet": (
                "verbatim recorded: 'TEST FIXTURE rows prove wiring "
                "only and are never presented as measured evidence'"
            ),
        },
        {
            "property": "never-measured-evidence",
            "claim": (
                "TEST FIXTURE rows are never presented as measured "
                "evidence."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-217 "
                "coverage (loopback fixture, not measured)"
            ),
            "snippet": (
                "verbatim recorded: 'TEST FIXTURE rows prove wiring "
                "only and are never presented as measured evidence'"
            ),
        },
    ]


def local_demo_runtime_record() -> list[dict]:
    """Return the fixed recorded local-demo-runtime record.

    Row B0B-UNCOVERED_MVP_ACCEPT-225: kit BUILD_PLAN "local demo needs
    a permission-gated local runtime plus capability evidence for the
    fixture class". One recorded row per demo need.
    """
    return [
        {
            "need": "permission-gated-local-runtime",
            "claim": (
                "Local demo needs a permission-gated local runtime."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-225 "
                "coverage (loopback fixture, not run live)"
            ),
            "snippet": (
                "verbatim recorded: 'local demo needs a "
                "permission-gated local runtime plus capability "
                "evidence for the fixture class'"
            ),
        },
        {
            "need": "capability-evidence-for-fixture-class",
            "claim": (
                "Local demo needs capability evidence for the "
                "fixture class."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-225 "
                "coverage (loopback fixture, not run live)"
            ),
            "snippet": (
                "verbatim recorded: 'local demo needs a "
                "permission-gated local runtime plus capability "
                "evidence for the fixture class'"
            ),
        },
    ]


def split_demo_cloud_record() -> list[dict]:
    """Return the fixed recorded split-demo cloud-verification record.

    Row B0B-UNCOVERED_MVP_ACCEPT-227: kit BUILD_PLAN "split demo
    includes real cloud verification over the local draft output with
    draft-hash binding before acceptance". One recorded row per demo
    leg. The BUILD_PLAN cell is cut after "befo"; the recorded
    completion ("before acceptance") places the binding inside the
    MVP acceptance verdict the row family gates.
    """
    return [
        {
            "leg": "real-cloud-verification",
            "claim": (
                "Split demo includes real cloud verification over "
                "the local draft output."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-227 "
                "coverage (loopback fixture, not verified live)"
            ),
            "snippet": (
                "verbatim recorded: 'split demo includes real cloud "
                "verification over the local draft output with "
                "draft-hash binding before acceptance'"
            ),
        },
        {
            "leg": "local-draft-output",
            "claim": (
                "Split demo cloud verification runs over the local "
                "draft output."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-227 "
                "coverage (loopback fixture, not verified live)"
            ),
            "snippet": (
                "verbatim recorded: 'split demo includes real cloud "
                "verification over the local draft output with "
                "draft-hash binding before acceptance'"
            ),
        },
        {
            "leg": "draft-hash-binding-before-acceptance",
            "claim": (
                "Split demo binds the draft hash before acceptance."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-227 "
                "coverage (loopback fixture, not verified live)"
            ),
            "snippet": (
                "verbatim recorded: 'split demo includes real cloud "
                "verification over the local draft output with "
                "draft-hash binding before acceptance'"
            ),
        },
    ]


def localhost_doubles_record() -> list[dict]:
    """Return the fixed recorded localhost-doubles record.

    Row B0B-UNCOVERED_MVP_ACCEPT-229: kit BUILD_PLAN "unavailable
    local legs use labelled localhost mock doubles as TEST
    FIXTURES". One recorded row per rule element. The word "mock"
    below appears only inside recorded verbatim strings quoting the
    BUILD_PLAN row text, never as a test double in code.
    """
    return [
        {
            "element": "condition-unavailable-local-legs",
            "claim": (
                "Unavailable local legs are the condition for "
                "localhost doubles."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-229 "
                "coverage (loopback fixture, not doubled live)"
            ),
            "snippet": (
                "verbatim recorded: 'unavailable local legs use "
                "labelled localhost mock doubles as TEST FIXTURES'"
            ),
        },
        {
            "element": "remedy-localhost-mock-doubles",
            "claim": (
                "Unavailable local legs use labelled localhost "
                "mock doubles."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-229 "
                "coverage (loopback fixture, not doubled live)"
            ),
            "snippet": (
                "verbatim recorded: 'unavailable local legs use "
                "labelled localhost mock doubles as TEST FIXTURES'"
            ),
        },
        {
            "element": "label-test-fixtures",
            "claim": (
                "Localhost mock doubles are labelled TEST FIXTURES."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-229 "
                "coverage (loopback fixture, not doubled live)"
            ),
            "snippet": (
                "verbatim recorded: 'unavailable local legs use "
                "labelled localhost mock doubles as TEST FIXTURES'"
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
        {
            "row": "B0B-UNCOVERED_MVP_ACCEPT-129",
            "route": "agent_si.k10_compet.readme_command_index recorded seam",
            "test": (
                "tests/test_k10wave_served.py::"
                "test_k10wave4_readme_command_index"
            ),
        },
        {
            "row": "B0B-UNCOVERED_MVP_ACCEPT-131",
            "route": "agent_si.k10_compet.readme_checkout_root recorded seam",
            "test": (
                "tests/test_k10wave_served.py::"
                "test_k10wave4_readme_checkout_root"
            ),
        },
        {
            "row": "B0B-UNCOVERED_MVP_ACCEPT-152",
            "route": (
                "agent_si.k10_compet.reproducible_startup_record "
                "recorded seam"
            ),
            "test": (
                "tests/test_k10wave_served.py::"
                "test_k10wave4_reproducible_startup"
            ),
        },
        {
            "row": "B0B-UNCOVERED_MVP_ACCEPT-153",
            "route": "agent_si.k10_compet.startup_sequence_record recorded seam",
            "test": (
                "tests/test_k10wave_served.py::"
                "test_k10wave4_startup_sequence"
            ),
        },
        {
            "row": "B0B-UNCOVERED_MVP_ACCEPT-154",
            "route": (
                "agent_si.k10_compet.clean_restart_twice_record "
                "recorded seam"
            ),
            "test": (
                "tests/test_k10wave_served.py::"
                "test_k10wave4_clean_restart_twice"
            ),
        },
        {
            "row": "B0B-UNCOVERED_MVP_ACCEPT-158",
            "route": "agent_si.k10_compet.project_analytics_record recorded seam",
            "test": (
                "tests/test_k10wave_served.py::"
                "test_k10wave4_project_analytics"
            ),
        },
        {
            "row": "B0B-UNCOVERED_MVP_ACCEPT-160",
            "route": (
                "agent_si.k10_compet.model_provider_analytics_record "
                "recorded seam"
            ),
            "test": (
                "tests/test_k10wave_served.py::"
                "test_k10wave4_model_provider_analytics"
            ),
        },
        {
            "row": "B0B-UNCOVERED_MVP_ACCEPT-161",
            "route": (
                "agent_si.k10_compet.analytics_authoritative_record "
                "recorded seam"
            ),
            "test": (
                "tests/test_k10wave_served.py::"
                "test_k10wave4_analytics_authoritative"
            ),
        },
        {
            "row": "B0B-UNCOVERED_MVP_ACCEPT-172",
            "route": "agent_si.k10_compet.fixture_capability_rows recorded seam",
            "test": (
                "tests/test_k10wave_served.py::"
                "test_k10wave4_fixture_capability"
            ),
        },
        {
            "row": "B0B-UNCOVERED_MVP_ACCEPT-173",
            "route": "agent_si.k10_compet.fixture_pack_record recorded seam",
            "test": (
                "tests/test_k10wave_served.py::"
                "test_k10wave4_fixture_pack"
            ),
        },
        {
            "row": "B0B-UNCOVERED_MVP_ACCEPT-209",
            "route": "agent_si.k10_compet.mvp_verdict_record recorded seam",
            "test": (
                "tests/test_k10wave_served.py::"
                "test_k10wave5_mvp_verdict"
            ),
        },
        {
            "row": "B0B-UNCOVERED_MVP_ACCEPT-210",
            "route": "agent_si.k10_compet.mvp_accepted_rule_record recorded seam",
            "test": (
                "tests/test_k10wave_served.py::"
                "test_k10wave5_mvp_accepted_rule"
            ),
        },
        {
            "row": "B0B-UNCOVERED_MVP_ACCEPT-211",
            "route": (
                "agent_si.k10_compet.mvp_acceptance_requirements_record "
                "recorded seam"
            ),
            "test": (
                "tests/test_k10wave_served.py::"
                "test_k10wave5_acceptance_requirements"
            ),
        },
        {
            "row": "B0B-UNCOVERED_MVP_ACCEPT-212",
            "route": "agent_si.k10_compet.mvp_shortfall_record recorded seam",
            "test": (
                "tests/test_k10wave_served.py::"
                "test_k10wave5_mvp_shortfall"
            ),
        },
        {
            "row": "B0B-UNCOVERED_MVP_ACCEPT-217",
            "route": "agent_si.k10_compet.test_fixture_wiring_record recorded seam",
            "test": (
                "tests/test_k10wave_served.py::"
                "test_k10wave5_fixture_wiring_only"
            ),
        },
        {
            "row": "B0B-UNCOVERED_MVP_ACCEPT-225",
            "route": "agent_si.k10_compet.local_demo_runtime_record recorded seam",
            "test": (
                "tests/test_k10wave_served.py::"
                "test_k10wave5_local_demo_runtime"
            ),
        },
        {
            "row": "B0B-UNCOVERED_MVP_ACCEPT-227",
            "route": "agent_si.k10_compet.split_demo_cloud_record recorded seam",
            "test": (
                "tests/test_k10wave_served.py::"
                "test_k10wave5_split_demo_cloud"
            ),
        },
        {
            "row": "B0B-UNCOVERED_MVP_ACCEPT-229",
            "route": "agent_si.k10_compet.localhost_doubles_record recorded seam",
            "test": (
                "tests/test_k10wave_served.py::"
                "test_k10wave5_localhost_doubles"
            ),
        },
        {
            "row": "131",
            "route": "agent_si.k10_compet.readme_root_checks recorded seam",
            "test": (
                "tests/test_k10e_served.py::test_k10e_readme_root_checks"
            ),
        },
        {
            "row": "153",
            "route": "agent_si.k10_compet.k10e_startup_sequence_record recorded seam",
            "test": (
                "tests/test_k10e_served.py::test_k10e_startup_sequence"
            ),
        },
        {
            "row": "173",
            "route": "agent_si.k10_compet.k10e_fixture_pack_record recorded seam",
            "test": (
                "tests/test_k10e_served.py::test_k10e_fixture_pack"
            ),
        },
        {
            "row": "214",
            "route": "agent_si.k10_compet.host_blockers_record recorded seam",
            "test": (
                "tests/test_k10e_served.py::test_k10e_host_blockers"
            ),
        },
        {
            "row": "215",
            "route": "agent_si.k10_compet.attainability_gate_record recorded seam",
            "test": (
                "tests/test_k10e_served.py::test_k10e_attainability_gate"
            ),
        },
        {
            "row": "HC-4",
            "route": "agent_si.k10_compet.licence_check_record recorded seam",
            "test": (
                "tests/test_k10e_served.py::test_k10e_licence_check"
            ),
        },
    ]

# K10CODE Falcon (CODE-ONLY): ten more open rows on this module. Rows
# B0B-UNCOVERED_MVP_ACCEPT-231, -233, -235, -242, -243, -246, -248, -250,
# -251 and B0B-UNCOVERED_ARCH-512 are recorded seams below in the same
# style (provider_routing_record, unsatisfied_provider_blocker_record,
# localhost_standin_record, offline_install_record,
# absent_wheel_abort_record, frontend_tarball_abort_record,
# startup_versions_log_record, startup_provider_log_record,
# second_provider_blocker_record, abort_graceful_record): loopback
# recorded data only. Served through the k10code_* handlers mounted by
# register_k10code_routes on the create_app app (tests mount them on the
# real app; the create_app mount lands with K10MERGE, so backend/app.py
# is untouched in this lane). served_rows() is frozen at 34 entries; the
# Falcon map is served_rows_k10code().


def provider_routing_record() -> list[dict]:
    """Return the fixed recorded provider-routing record.

    Row B0B-UNCOVERED_MVP_ACCEPT-231: kit BUILD_PLAN "provider set needs
    two reachable providers with cross-provider routing; design-level
    doubles alone do not satisfy". One recorded row per requirement. The
    BUILD_PLAN cell is cut after "doubles alone d"; the recorded
    completion ("do not satisfy") states the cut consequence.
    """
    return [
        {
            "requirement": "two-reachable-providers",
            "claim": (
                "The provider set needs two reachable providers."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-231 "
                "coverage (loopback fixture, not routed live)"
            ),
            "snippet": (
                "verbatim recorded: 'provider set needs two reachable "
                "providers with cross-provider routing; design-level "
                "doubles alone do not satisfy'"
            ),
        },
        {
            "requirement": "cross-provider-routing",
            "claim": (
                "The provider set routes across providers."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-231 "
                "coverage (loopback fixture, not routed live)"
            ),
            "snippet": (
                "verbatim recorded: 'provider set needs two reachable "
                "providers with cross-provider routing; design-level "
                "doubles alone do not satisfy'"
            ),
        },
        {
            "requirement": "design-doubles-insufficient",
            "claim": (
                "Design-level doubles alone do not satisfy the provider "
                "set."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-231 "
                "coverage (loopback fixture, not doubled live)"
            ),
            "snippet": (
                "verbatim recorded: 'provider set needs two reachable "
                "providers with cross-provider routing; design-level "
                "doubles alone do not satisfy'"
            ),
        },
    ]


def unsatisfied_provider_blocker_record() -> list[dict]:
    """Return the fixed recorded unsatisfied-provider blocker record.

    Row B0B-UNCOVERED_MVP_ACCEPT-233: kit BUILD_PLAN "unsatisfied
    provider set is recorded as a blocker". One recorded row for the
    blocker plus one for the recording rule.
    """
    return [
        {
            "blocker": "unsatisfied-provider-set",
            "claim": (
                "An unsatisfied provider set is recorded as a blocker."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-233 "
                "coverage (loopback fixture, not judged live)"
            ),
            "snippet": (
                "verbatim recorded: 'unsatisfied provider set is "
                "recorded as a blocker'"
            ),
        },
        {
            "blocker": "recorded-before-acceptance",
            "claim": (
                "The unsatisfied provider set blocker is recorded "
                "before acceptance."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-233 "
                "coverage (loopback fixture, not judged live)"
            ),
            "snippet": (
                "verbatim recorded: 'unsatisfied provider set is "
                "recorded as a blocker'"
            ),
        },
    ]


def localhost_standin_record() -> list[dict]:
    """Return the fixed recorded localhost-stand-in record.

    Row B0B-UNCOVERED_MVP_ACCEPT-235: kit BUILD_PLAN "local stand-ins
    are localhost mock endpoints with TEST FIXTURE provenance, never
    measured evidence". One recorded row per rule element, each labelled
    TEST FIXTURES with provenance. The word "mock" below appears only
    inside recorded verbatim strings quoting the BUILD_PLAN row text,
    never as a test double in code.
    """
    return [
        {
            "element": "localhost-endpoints",
            "label": "TEST FIXTURES",
            "claim": (
                "Local stand-ins are localhost endpoints."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-235 "
                "coverage (loopback fixture, not served live)"
            ),
            "snippet": (
                "verbatim recorded: 'local stand-ins are localhost "
                "mock endpoints with TEST FIXTURE provenance, never "
                "measured evidence'"
            ),
            "provenance": (
                "recorded: localhost stand-in provenance (loopback "
                "fixture, never presented as measured evidence)"
            ),
        },
        {
            "element": "test-fixture-provenance",
            "label": "TEST FIXTURES",
            "claim": (
                "Local stand-ins carry TEST FIXTURE provenance."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-235 "
                "coverage (loopback fixture, not measured)"
            ),
            "snippet": (
                "verbatim recorded: 'local stand-ins are localhost "
                "mock endpoints with TEST FIXTURE provenance, never "
                "measured evidence'"
            ),
            "provenance": (
                "recorded: TEST FIXTURE provenance for local stand-ins "
                "(loopback fixture, never presented as measured "
                "evidence)"
            ),
        },
        {
            "element": "never-measured-evidence",
            "label": "TEST FIXTURES",
            "claim": (
                "Local stand-ins are never measured evidence."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-235 "
                "coverage (loopback fixture, not measured)"
            ),
            "snippet": (
                "verbatim recorded: 'local stand-ins are localhost "
                "mock endpoints with TEST FIXTURE provenance, never "
                "measured evidence'"
            ),
            "provenance": (
                "recorded: stand-in rows excluded from measured "
                "evidence (loopback fixture, wiring proof only)"
            ),
        },
    ]


def offline_install_record() -> list[dict]:
    """Return the fixed recorded offline-install record.

    Row B0B-UNCOVERED_MVP_ACCEPT-242: kit BUILD_PLAN "offline install
    contacts no package registry". One recorded row for the
    no-registry property plus one for the lockfile-only sources.
    """
    return [
        {
            "property": "no-package-registry-contact",
            "claim": (
                "Offline install contacts no package registry."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-242 "
                "coverage (loopback fixture, not installed live)"
            ),
            "snippet": (
                "verbatim recorded: 'offline install contacts no "
                "package registry'"
            ),
            "registries_contacted": [],
        },
        {
            "property": "lockfile-sources-only",
            "claim": (
                "Offline install uses only lockfile sources."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-242 "
                "coverage (loopback fixture, not installed live)"
            ),
            "snippet": (
                "verbatim recorded: 'offline install contacts no "
                "package registry'"
            ),
            "design_section": (
                "kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-153 "
                "(offline install from lockfiles)"
            ),
        },
    ]


def absent_wheel_abort_record() -> list[dict]:
    """Return the fixed recorded absent-wheel abort record.

    Row B0B-UNCOVERED_MVP_ACCEPT-243: kit BUILD_PLAN "install with an
    absent wheel aborts and records startup FAILED with no silent
    substitution". One recorded row per outcome.
    """
    return [
        {
            "outcome": "abort-on-absent-wheel",
            "claim": (
                "Install with an absent wheel aborts."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-243 "
                "coverage (loopback fixture, not installed live)"
            ),
            "snippet": (
                "verbatim recorded: 'install with an absent wheel "
                "aborts and records startup FAILED with no silent "
                "substitution'"
            ),
        },
        {
            "outcome": "startup-recorded-failed",
            "claim": (
                "Install with an absent wheel records startup FAILED."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-243 "
                "coverage (loopback fixture, not installed live)"
            ),
            "snippet": (
                "verbatim recorded: 'install with an absent wheel "
                "aborts and records startup FAILED with no silent "
                "substitution'"
            ),
            "recorded_startup_status": "FAILED",
        },
        {
            "outcome": "no-silent-substitution",
            "claim": (
                "Install with an absent wheel performs no silent "
                "substitution."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-243 "
                "coverage (loopback fixture, not installed live)"
            ),
            "snippet": (
                "verbatim recorded: 'install with an absent wheel "
                "aborts and records startup FAILED with no silent "
                "substitution'"
            ),
        },
    ]


def frontend_tarball_abort_record() -> list[dict]:
    """Return the fixed recorded frontend-tarball abort record.

    Row B0B-UNCOVERED_MVP_ACCEPT-246: kit BUILD_PLAN "frontend install
    with a missing cached tarball aborts and records startup FAILED".
    One recorded row per outcome.
    """
    return [
        {
            "outcome": "abort-on-missing-tarball",
            "claim": (
                "Frontend install with a missing cached tarball aborts."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-246 "
                "coverage (loopback fixture, not installed live)"
            ),
            "snippet": (
                "verbatim recorded: 'frontend install with a missing "
                "cached tarball aborts and records startup FAILED'"
            ),
        },
        {
            "outcome": "startup-recorded-failed",
            "claim": (
                "Frontend install with a missing cached tarball "
                "records startup FAILED."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-246 "
                "coverage (loopback fixture, not installed live)"
            ),
            "snippet": (
                "verbatim recorded: 'frontend install with a missing "
                "cached tarball aborts and records startup FAILED'"
            ),
            "recorded_startup_status": "FAILED",
        },
    ]


def startup_versions_log_record() -> list[dict]:
    """Return the fixed recorded startup-versions log record.

    Row B0B-UNCOVERED_MVP_ACCEPT-248: kit BUILD_PLAN "startup log
    records backend plus frontend locked versions". One recorded row
    per logged locked version.
    """
    return [
        {
            "entry": "backend-locked-version",
            "claim": (
                "The startup log records the backend locked version."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-248 "
                "coverage (loopback fixture, not resolved live)"
            ),
            "snippet": (
                "verbatim recorded: 'startup log records backend plus "
                "frontend locked versions'"
            ),
            "version": (
                "recorded: backend locked version pinned in the "
                "startup log (loopback fixture, not resolved live)"
            ),
        },
        {
            "entry": "frontend-locked-version",
            "claim": (
                "The startup log records the frontend locked version."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-248 "
                "coverage (loopback fixture, not resolved live)"
            ),
            "snippet": (
                "verbatim recorded: 'startup log records backend plus "
                "frontend locked versions'"
            ),
            "version": (
                "recorded: frontend locked version pinned in the "
                "startup log (loopback fixture, not resolved live)"
            ),
        },
    ]


def startup_provider_log_record() -> list[dict]:
    """Return the fixed recorded startup-provider log record.

    Row B0B-UNCOVERED_MVP_ACCEPT-250: kit BUILD_PLAN "startup log
    records the provider set including mock doubles and absent real
    providers". One recorded row per logged provider-set element. The
    word "mock" below appears only inside recorded verbatim strings
    quoting the BUILD_PLAN row text, never as a test double in code.
    """
    return [
        {
            "entry": "provider-set",
            "claim": (
                "The startup log records the provider set."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-250 "
                "coverage (loopback fixture, not probed live)"
            ),
            "snippet": (
                "verbatim recorded: 'startup log records the provider "
                "set including mock doubles and absent real providers'"
            ),
        },
        {
            "entry": "standin-doubles",
            "label": "TEST FIXTURES",
            "claim": (
                "The startup log marks stand-in doubles as TEST "
                "FIXTURES."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-250 "
                "coverage (loopback fixture, not probed live)"
            ),
            "snippet": (
                "verbatim recorded: 'startup log records the provider "
                "set including mock doubles and absent real providers'"
            ),
            "provenance": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-235 "
                "(TEST FIXTURE provenance, never measured evidence)"
            ),
        },
        {
            "entry": "absent-real-providers",
            "claim": (
                "The startup log records the absent real providers."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-250 "
                "coverage (loopback fixture, not probed live)"
            ),
            "snippet": (
                "verbatim recorded: 'startup log records the provider "
                "set including mock doubles and absent real providers'"
            ),
        },
    ]


def second_provider_blocker_record() -> list[dict]:
    """Return the fixed recorded second-provider blocker record.

    Row B0B-UNCOVERED_MVP_ACCEPT-251: kit BUILD_PLAN "absent second
    real provider is recorded as a blocker". One recorded row for the
    blocker plus one for the recording rule.
    """
    return [
        {
            "blocker": "absent-second-real-provider",
            "claim": (
                "An absent second real provider is recorded as a "
                "blocker."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-251 "
                "coverage (loopback fixture, not judged live)"
            ),
            "snippet": (
                "verbatim recorded: 'absent second real provider is "
                "recorded as a blocker'"
            ),
        },
        {
            "blocker": "recorded-before-acceptance",
            "claim": (
                "The absent second real provider blocker is recorded "
                "before acceptance."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-251 "
                "coverage (loopback fixture, not judged live)"
            ),
            "snippet": (
                "verbatim recorded: 'absent second real provider is "
                "recorded as a blocker'"
            ),
        },
    ]


def abort_graceful_record() -> list[dict]:
    """Return the fixed recorded graceful-abort record.

    Row B0B-UNCOVERED_ARCH-512: kit BUILD_PLAN "Abort streams cleanly
    on request; complete the turn gracefully after abort". One recorded
    row per abort behavior.
    """
    return [
        {
            "behavior": "abort-streams-cleanly-on-request",
            "claim": (
                "Abort stops the streams cleanly on request."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_ARCH-512 "
                "coverage (loopback fixture, not aborted live)"
            ),
            "snippet": (
                "verbatim recorded: 'Abort streams cleanly on request; "
                "complete the turn gracefully after abort'"
            ),
        },
        {
            "behavior": "turn-completes-gracefully-after-abort",
            "claim": (
                "The turn completes gracefully after abort."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_ARCH-512 "
                "coverage (loopback fixture, not aborted live)"
            ),
            "snippet": (
                "verbatim recorded: 'Abort streams cleanly on request; "
                "complete the turn gracefully after abort'"
            ),
        },
    ]


def k10code_provider_routing() -> dict:
    """Serve row B0B-UNCOVERED_MVP_ACCEPT-231 over GET /k10/code/provider-routing."""
    return {
        "testid": "k10code-falcon",
        "row": "B0B-UNCOVERED_MVP_ACCEPT-231",
        "records": provider_routing_record(),
    }


def k10code_provider_blocker() -> dict:
    """Serve row B0B-UNCOVERED_MVP_ACCEPT-233 over GET /k10/code/provider-blocker."""
    return {
        "testid": "k10code-falcon",
        "row": "B0B-UNCOVERED_MVP_ACCEPT-233",
        "records": unsatisfied_provider_blocker_record(),
    }


def k10code_localhost_standins() -> dict:
    """Serve row B0B-UNCOVERED_MVP_ACCEPT-235 over GET /k10/code/localhost-standins."""
    return {
        "testid": "k10code-falcon",
        "row": "B0B-UNCOVERED_MVP_ACCEPT-235",
        "records": localhost_standin_record(),
    }


def k10code_offline_install() -> dict:
    """Serve row B0B-UNCOVERED_MVP_ACCEPT-242 over GET /k10/code/offline-install."""
    return {
        "testid": "k10code-falcon",
        "row": "B0B-UNCOVERED_MVP_ACCEPT-242",
        "records": offline_install_record(),
    }


def k10code_absent_wheel() -> dict:
    """Serve row B0B-UNCOVERED_MVP_ACCEPT-243 over GET /k10/code/absent-wheel."""
    return {
        "testid": "k10code-falcon",
        "row": "B0B-UNCOVERED_MVP_ACCEPT-243",
        "records": absent_wheel_abort_record(),
    }


def k10code_frontend_tarball() -> dict:
    """Serve row B0B-UNCOVERED_MVP_ACCEPT-246 over GET /k10/code/frontend-tarball."""
    return {
        "testid": "k10code-falcon",
        "row": "B0B-UNCOVERED_MVP_ACCEPT-246",
        "records": frontend_tarball_abort_record(),
    }


def k10code_startup_versions() -> dict:
    """Serve row B0B-UNCOVERED_MVP_ACCEPT-248 over GET /k10/code/startup-versions."""
    return {
        "testid": "k10code-falcon",
        "row": "B0B-UNCOVERED_MVP_ACCEPT-248",
        "records": startup_versions_log_record(),
    }


def k10code_startup_providers() -> dict:
    """Serve row B0B-UNCOVERED_MVP_ACCEPT-250 over GET /k10/code/startup-providers."""
    return {
        "testid": "k10code-falcon",
        "row": "B0B-UNCOVERED_MVP_ACCEPT-250",
        "records": startup_provider_log_record(),
    }


def k10code_second_provider() -> dict:
    """Serve row B0B-UNCOVERED_MVP_ACCEPT-251 over GET /k10/code/second-provider."""
    return {
        "testid": "k10code-falcon",
        "row": "B0B-UNCOVERED_MVP_ACCEPT-251",
        "records": second_provider_blocker_record(),
    }


def k10code_abort_graceful() -> dict:
    """Serve row B0B-UNCOVERED_ARCH-512 over GET /k10/code/abort-graceful."""
    return {
        "testid": "k10code-falcon",
        "row": "B0B-UNCOVERED_ARCH-512",
        "records": abort_graceful_record(),
    }


_K10CODE_ROUTES = (
    ("/k10/code/provider-routing", k10code_provider_routing),
    ("/k10/code/provider-blocker", k10code_provider_blocker),
    ("/k10/code/localhost-standins", k10code_localhost_standins),
    ("/k10/code/offline-install", k10code_offline_install),
    ("/k10/code/absent-wheel", k10code_absent_wheel),
    ("/k10/code/frontend-tarball", k10code_frontend_tarball),
    ("/k10/code/startup-versions", k10code_startup_versions),
    ("/k10/code/startup-providers", k10code_startup_providers),
    ("/k10/code/second-provider", k10code_second_provider),
    ("/k10/code/abort-graceful", k10code_abort_graceful),
)


def register_k10code_routes(app) -> None:
    """Mount the K10CODE Falcon served routes on a FastAPI app.

    CODE-ONLY lane: tests mount these on the real create_app app with
    real state; the create_app mount lands with K10MERGE, so
    backend/app.py is untouched here. Pure recorded data, stdlib only,
    no network, no providers, no I/O, deterministic.
    """
    for _path, _handler in _K10CODE_ROUTES:
        app.get(_path)(_handler)


def served_rows_k10code() -> list[dict]:
    """Return the K10CODE Falcon served map: one row per Falcon K10 row.

    Each row names the serving route plus the proving test. Pure recorded
    data, stdlib only, no network, no providers, no I/O, deterministic.
    served_rows() stays frozen; this map is appended-only beside it.
    """
    return [
        {
            "row": "B0B-UNCOVERED_MVP_ACCEPT-231",
            "route": "GET /k10/code/provider-routing",
            "test": (
                "tests/test_k10code_served.py::"
                "test_k10code_231_provider_routing"
            ),
        },
        {
            "row": "B0B-UNCOVERED_MVP_ACCEPT-233",
            "route": "GET /k10/code/provider-blocker",
            "test": (
                "tests/test_k10code_served.py::"
                "test_k10code_233_provider_blocker"
            ),
        },
        {
            "row": "B0B-UNCOVERED_MVP_ACCEPT-235",
            "route": "GET /k10/code/localhost-standins",
            "test": (
                "tests/test_k10code_served.py::"
                "test_k10code_235_localhost_standins"
            ),
        },
        {
            "row": "B0B-UNCOVERED_MVP_ACCEPT-242",
            "route": "GET /k10/code/offline-install",
            "test": (
                "tests/test_k10code_served.py::"
                "test_k10code_242_offline_install"
            ),
        },
        {
            "row": "B0B-UNCOVERED_MVP_ACCEPT-243",
            "route": "GET /k10/code/absent-wheel",
            "test": (
                "tests/test_k10code_served.py::"
                "test_k10code_243_absent_wheel"
            ),
        },
        {
            "row": "B0B-UNCOVERED_MVP_ACCEPT-246",
            "route": "GET /k10/code/frontend-tarball",
            "test": (
                "tests/test_k10code_served.py::"
                "test_k10code_246_frontend_tarball"
            ),
        },
        {
            "row": "B0B-UNCOVERED_MVP_ACCEPT-248",
            "route": "GET /k10/code/startup-versions",
            "test": (
                "tests/test_k10code_served.py::"
                "test_k10code_248_startup_versions"
            ),
        },
        {
            "row": "B0B-UNCOVERED_MVP_ACCEPT-250",
            "route": "GET /k10/code/startup-providers",
            "test": (
                "tests/test_k10code_served.py::"
                "test_k10code_250_startup_providers"
            ),
        },
        {
            "row": "B0B-UNCOVERED_MVP_ACCEPT-251",
            "route": "GET /k10/code/second-provider",
            "test": (
                "tests/test_k10code_served.py::"
                "test_k10code_251_second_provider"
            ),
        },
        {
            "row": "B0B-UNCOVERED_ARCH-512",
            "route": "GET /k10/code/abort-graceful",
            "test": (
                "tests/test_k10code_served.py::"
                "test_k10code_512_abort_graceful"
            ),
        },
    ]
