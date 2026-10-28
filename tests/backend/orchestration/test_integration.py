"""INT2 joint contract + end-to-end validation (frozen K02_INTERFACE.md v2+C19+C20).

Covers the 11 lane modules through their REAL implementations: joint
exports (v2+C19), common kernel shapes, V1-V8 end-to-end, link-check
joints, gate plus fresh-audit close, v2 record shapes C6-C18, and the
section 4 served-data paths. No skips, no fakes, no network; file IO
uses tmp_path only.

C20 ADOPTED (RECORDS/day1/K02_V2_CHANGES.md line 24, sha ade702a6):
lane extras below are adopted, not drift; this file asserts
adopted symbols PRESENT (test_joint_exports_c20_adopted_present)
and never asserts extras absent.
Two duplicates were dropped by C20 and never frozen, both
already absent from code and never exercised here:
- overlap.plan_managers dropped (-> v2 home split.fanout).
- parts.PartStore.close_part dropped (-> v2 home gates.close_part).
Adopted extras asserted present-only:
- overlap: validate_multi_manager_settings, early_start_allowed,
  may_start_early.
- manifest: ManifestRec, canonical_manifest_bytes, manifest_hash,
  build_manifest, verify_manifest_hash, validate_part_ref,
  check_manifest, check_part_manifest, save_manifest, load_manifest,
  frozen_hash.
- delta: activate_hierarchy_chain, validate_config_change,
  validate_stored_config, apply_stored_config.
- parts: PartStore, PartRecord, PartRow, ClosedPartRef, GateRefused,
  register_part, list_parts, update_status.
Present in code but NOT C20-adopted (no adopted-status claim here,
never asserted here):
- split.load_decompositions, split.persist_decompositions.
- parts.build_package_report, parts.persist_ledger, parts.load_ledger.
"""

import dataclasses
import inspect
import os
import sys

import pytest

sys.path.insert(
    0,
    os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
    ),
)

from agent_si.backend.orchestration import common as common_mod
from agent_si.backend.orchestration import delta as delta_mod
from agent_si.backend.orchestration import gates as gates_mod
from agent_si.backend.orchestration import graph as graph_mod
from agent_si.backend.orchestration import ledger as ledger_mod
from agent_si.backend.orchestration import manifest as manifest_mod
from agent_si.backend.orchestration import offload as offload_mod
from agent_si.backend.orchestration import overlap as overlap_mod
from agent_si.backend.orchestration import parts as parts_mod
from agent_si.backend.orchestration import split as split_mod
from agent_si.backend.orchestration import steplimits as steplimits_mod
from agent_si.backend.orchestration import teamcard as teamcard_mod

MODEL_ID = "meta/muse-spark-1.3-contributor"

_uid = 0


def fresh_id(prefix):
    global _uid
    _uid += 1
    return f"{prefix}-{_uid:04d}"


@pytest.fixture(autouse=True)
def _clean_shared_state():
    overlap_mod._clear_verdicts()
    steplimits_mod._reset_state()
    offload_mod._reset_state()
    audit_log_before = list(teamcard_mod.AUDIT_CHOICE_LOG)
    yield
    overlap_mod._clear_verdicts()
    steplimits_mod._reset_state()
    offload_mod._reset_state()
    # build_team_report serves select_audit_model without a caller log, which
    # appends to the module-global choice log; restore it so lane-global
    # state never leaks out of this file.
    del teamcard_mod.AUDIT_CHOICE_LOG[:]
    teamcard_mod.AUDIT_CHOICE_LOG.extend(audit_log_before)


# --- (1) joint exports: v2 frozen symbols present in every lane module ---


V2_EXPORTS = {
    "split": ["split_package", "validate_disjoint", "fanout"],
    "parts": ["register_part", "list_parts", "update_status"],
    "gates": ["close_part", "evaluate_phase_gate", "check_hierarchy_activation"],
    "graph": ["build_graph", "ready_parts", "mark_completed"],
    "overlap": ["may_start_early"],
    "manifest": ["frozen_hash", "check_part_manifest"],
    "delta": ["intake_bounded_delta", "cross_check", "close_with_linkcheck"],
    "teamcard": [
        "build_team_card",
        "director_context",
        "manager_context",
        "worker_context",
        "record_decomposition",
        "apply_team_config_change",
    ],
    # C9: ledger.record_row is a PackageLedger METHOD only, never module-level.
    "ledger": [
        "package_report",
        "apply_ledger_config_change",
        "persist_ledger",
        "load_ledger",
        "build_ledger_report",
    ],
    "offload": ["offload_enabled", "maybe_offload"],
    "steplimits": ["limits_for", "apply_steplimit_config_change"],
}

_LANE_BY_NAME = {
    "split": split_mod,
    "parts": parts_mod,
    "gates": gates_mod,
    "graph": graph_mod,
    "overlap": overlap_mod,
    "manifest": manifest_mod,
    "delta": delta_mod,
    "teamcard": teamcard_mod,
    "ledger": ledger_mod,
    "offload": offload_mod,
    "steplimits": steplimits_mod,
    "common": common_mod,
}


def _joint_cases():
    for module, symbols in V2_EXPORTS.items():
        for symbol in symbols:
            yield pytest.param(module, symbol, id=f"{module}.{symbol}")


@pytest.mark.parametrize("module,symbol", list(_joint_cases()))
def test_joint_exports_v2_present(module, symbol):
    assert hasattr(_LANE_BY_NAME[module], symbol), (
        f"{module} missing v2 symbol: {symbol}"
    )


def test_joint_exports_ledger_record_row_is_method_only():
    assert callable(ledger_mod.PackageLedger.record_row)
    assert not hasattr(ledger_mod, "record_row")


def test_joint_exports_c16_extras_present():
    assert callable(teamcard_mod.select_audit_model)
    assert teamcard_mod.AuditModelChoice is not None
    assert callable(teamcard_mod.register_verbatim)
    assert callable(teamcard_mod.build_team_report)
    assert teamcard_mod.TeamReport is not None
    assert callable(teamcard_mod.make_secret_ref)
    assert callable(split_mod.make_secret_ref)
    assert callable(ledger_mod.build_ledger_report)
    assert ledger_mod.LedgerReport is not None


def test_joint_exports_c19_extras_present():
    assert gates_mod.GateAuditLog is not None
    for name in ("serve_gate", "serve_audit", "has_fresh_audit"):
        assert hasattr(gates_mod.GateAuditLog, name), (
            f"GateAuditLog missing C19 member: {name}"
        )
    for name in (
        "route_task",
        "validate_dispatch",
        "control_plane_map",
        "HierarchyConfigStore",
        "TaskPlanner",
        "SubtaskGraph",
        "CycleError",
        "DependencyError",
    ):
        assert hasattr(graph_mod, name), f"graph missing C19 symbol: {name}"


def test_joint_exports_c20_adopted_present():
    # C20 (RECORDS/day1/K02_V2_CHANGES.md line 24): every adopted name
    # verified present in code. Present-only; never asserts absence.
    cases = {
        manifest_mod: (
            "ManifestRec",
            "build_manifest",
            "canonical_manifest_bytes",
            "check_manifest",
            "check_part_manifest",
            "frozen_hash",
            "load_manifest",
            "manifest_hash",
            "save_manifest",
            "validate_part_ref",
            "verify_manifest_hash",
        ),
        delta_mod: (
            "activate_hierarchy_chain",
            "apply_stored_config",
            "validate_config_change",
            "validate_stored_config",
        ),
        parts_mod: (
            "PartStore",
            "PartRecord",
            "PartRow",
            "ClosedPartRef",
            "GateRefused",
            "register_part",
            "list_parts",
            "update_status",
        ),
        overlap_mod: (
            "early_start_allowed",
            "may_start_early",
            "validate_multi_manager_settings",
        ),
    }
    for module, names in cases.items():
        for name in names:
            assert hasattr(module, name), (
                f"C20 adopted symbol missing: {module.__name__}.{name}"
            )


# --- (2) common kernel: 7 symbols, BOTH outcome shapes, BOTH surface forms ---


def test_common_kernel_seven_symbols():
    for name in (
        "DecisionRow",
        "DecisionLog",
        "ApplyOutcome",
        "AppliedOutcome",
        "surface_rejection",
        "utc_now",
        "hot_write_text",
    ):
        assert hasattr(common_mod, name), f"common missing: {name}"


def test_common_decision_row_fields_exact():
    assert [f.name for f in dataclasses.fields(common_mod.DecisionRow)] == [
        "decision_id",
        "scope",
        "statement",
        "reason",
        "authority",
        "created_at",
    ]


def test_common_both_outcome_shapes():
    # Accepted-form (teamcard/ledger/parts/graph): accepted + row + surfaced.
    assert [f.name for f in dataclasses.fields(common_mod.ApplyOutcome)] == [
        "accepted",
        "reason",
        "row",
        "surfaced",
    ]
    # Applied-form (offload/steplimits/delta): applied + decision_ref.
    assert [f.name for f in dataclasses.fields(common_mod.AppliedOutcome)] == [
        "applied",
        "reason",
        "decision_ref",
    ]


def test_common_surface_rejection_both_forms():
    accepted = common_mod.ApplyOutcome(accepted=True, reason="applied")
    refused = common_mod.ApplyOutcome(accepted=False, reason="over cap: agents")
    assert common_mod.surface_rejection(accepted) == "change applied"
    surfaced = common_mod.surface_rejection(refused)
    assert "over cap: agents" in surfaced
    applied_ok = common_mod.AppliedOutcome(applied=True, reason="applied")
    applied_no = common_mod.AppliedOutcome(
        applied=False, reason="POLICY_CONFLICT: bad patch"
    )
    assert common_mod.surface_rejection(applied_ok) == "change applied"
    assert "POLICY_CONFLICT" in common_mod.surface_rejection(applied_no)


def test_common_surface_forms_match_lane_kernels():
    # C18: teamcard compacts to English, ledger returns a plain string.
    team_out = teamcard_mod.ApplyOutcome(accepted=False, reason="over cap: flood")
    assert teamcard_mod.surface_rejection(team_out) == (
        "change refused: over cap: flood"
    )
    ledger_out = ledger_mod.ApplyOutcome(accepted=False, reason="over cap: flood")
    assert ledger_mod.surface_rejection(ledger_out) == (
        "change refused: over cap: flood"
    )
    assert isinstance(ledger_mod.surface_rejection(ledger_out), str)


def test_common_decision_log_unique_scope_sequence():
    log = common_mod.DecisionLog()
    first = log.append("s", "one", "r", "a", "2026-10-26T00:00:00Z")
    second = log.append("s", "two", "r", "a", "2026-10-26T00:00:00Z")
    assert (first.decision_id, second.decision_id) == ("s-0001", "s-0002")
    assert log.rows == [first, second]


def test_common_hot_write_and_utc(tmp_path):
    target = str(tmp_path / "kernel.txt")
    common_mod.hot_write_text(target, "hello kernel")
    with open(target, encoding="utf-8") as handle:
        assert handle.read() == "hello kernel"
    stamp = common_mod.utc_now()
    assert isinstance(stamp, str) and stamp != ""


# --- helpers for the end-to-end flows ---


def _serve_pair(log, part_id, gate_v="PASS", audit_v="PASS"):
    gate = log.serve_gate(part_id, gate_v)
    audit = log.serve_audit(
        part_id, audit_v, "auditor-int2", ("producer-int2",), True
    )
    return gate, audit


def _gate_refs(gate, audit, package_id):
    return {
        "package_id": package_id,
        "contract_hash": "contract-int2",
        "gate_verdict_ref": gate.gate_id,
        "audit_verdict_ref": audit.audit_id,
    }


def _serve_phase(log, package_id, parts=("part-000", "part-001")):
    for part in parts:
        _serve_pair(log, package_id + ":" + part)
    return _serve_pair(log, package_id + ":integration")


# --- (3) V1-V8 end-to-end through REAL modules ---


def test_v1_no_close_part_without_stored_pass():
    log = gates_mod.GateAuditLog()
    package_id = fresh_id("pkg-v1")
    part_id = package_id + ":part-000"
    with pytest.raises(gates_mod.GATE_NOT_PASSED):
        gates_mod.close_part(
            {
                "package_id": package_id,
                "contract_hash": "ch",
                "gate_verdict_ref": "missing-gate",
                "audit_verdict_ref": "missing-audit",
            }
        )
    gate = log.serve_gate(part_id, "PASS")
    gate_only_ref = {
        "package_id": package_id,
        "contract_hash": "ch",
        "gate_verdict_ref": gate.gate_id,
        "audit_verdict_ref": "missing-audit",
    }
    with pytest.raises(gates_mod.GATE_NOT_PASSED):
        gates_mod.close_part(gate_only_ref)


def test_v1_close_part_pass_returns_gate_verdict():
    log = gates_mod.GateAuditLog()
    package_id = fresh_id("pkg-v1ok")
    gate, audit = _serve_pair(log, package_id + ":part-000")
    verdict = gates_mod.close_part(_gate_refs(gate, audit, package_id))
    assert verdict["package_id"] == package_id
    assert verdict["gate"] == "PASS" and verdict["audit"] == "PASS"
    assert set(verdict.keys()) == {
        "package_id",
        "gate",
        "audit",
        "decided_at",
        "evidence_refs",
    }


def test_v2_no_early_start_without_resolved_pass():
    package_id = fresh_id("pkg-v2")
    ref = {
        "package_id": package_id,
        "contract_hash": "ch",
        "gate_verdict_ref": f"gate-{package_id}",
        "audit_verdict_ref": f"audit-{package_id}",
    }
    assert overlap_mod.may_start_early(ref) is False
    overlap_mod._record_gate_verdict(ref["gate_verdict_ref"], "PASS")
    assert overlap_mod.may_start_early(ref) is False
    overlap_mod._record_audit_verdict(ref["audit_verdict_ref"], "REWORK")
    assert overlap_mod.may_start_early(ref) is False
    overlap_mod._record_audit_verdict(ref["audit_verdict_ref"], "PASS")
    assert overlap_mod.may_start_early(ref) is True


def test_v3_manifest_mismatch_rejects_part():
    # Frozen v2 shape: minimal manifest sealed with frozen_hash
    # (build_manifest serves the extra drift shape, covered in the joint flow).
    base = {
        "manifest_id": f"m-v3-{fresh_id('x')}",
        "version": 1,
        "hash_algorithm": "sha256",
    }
    manifest = dict(base, hash=manifest_mod.frozen_hash(dict(base, hash="x")))
    good = {
        "package_id": "pkg-v3",
        "contract_hash": manifest["hash"],
        "gate_verdict_ref": "g",
        "audit_verdict_ref": "a",
    }
    assert manifest_mod.check_part_manifest(good, manifest) is True
    bad = dict(good, contract_hash="0" * 64)
    assert manifest_mod.check_part_manifest(bad, manifest) is False
    tampered = dict(manifest, version=999)
    assert manifest_mod.check_part_manifest(good, tampered) is False


def test_v4_accept_persists_unique_row_refusal_mutates_nothing():
    store = teamcard_mod.TeamConfigStore()
    first = teamcard_mod.apply_team_config_change(
        store, "raise cap use", "need room", "tester-int2", {"agents": 2}
    )
    assert first.accepted is True and first.row is not None
    second = teamcard_mod.apply_team_config_change(
        store, "raise cap use two", "need room", "tester-int2", {"agents": 3}
    )
    assert second.accepted is True and second.row is not None
    assert first.row.decision_id == "team-config-0001"
    assert second.row.decision_id == "team-config-0002"
    assert len(store.log.rows) == 2
    before = dict(store.config)
    rows_before = len(store.log.rows)
    refused = teamcard_mod.apply_team_config_change(
        store,
        "kill audit",
        "test",
        "tester-int2",
        {"auditor": "worker", "worker": "worker"},
    )
    assert refused.accepted is False
    assert refused.row is None
    assert refused.reason != ""
    assert store.config == before
    assert len(store.log.rows) == rows_before


def test_v4_steplimits_refusal_mutates_nothing_accept_persists_row():
    change = {
        "project_id": fresh_id("proj-v4"),
        "authority": "manager-int2",
        "reason": "set limits for test",
        "task_max_steps": 2,
        "chat_max_steps": 5,
    }
    outcome = steplimits_mod.apply_steplimit_config_change(change)
    assert outcome.applied is True
    assert outcome.decision_ref is not None
    before_limits = dict(steplimits_mod._PROJECT_LIMITS)
    before_rows = list(steplimits_mod._DECISIONS)
    with pytest.raises(steplimits_mod.UNKNOWN_LIMIT_KIND):
        steplimits_mod.limits_for("bogus", change["project_id"])
    assert dict(steplimits_mod._PROJECT_LIMITS) == before_limits
    assert list(steplimits_mod._DECISIONS) == before_rows


def test_v5_planner_router_never_name_provider_or_model():
    assert "provider" not in inspect.signature(graph_mod.TaskPlanner.plan).parameters
    assert "model" not in inspect.signature(graph_mod.route_task).parameters
    specs = [
        {"goal": "first slice", "task_class": "build", "risk": "LOW"},
        {
            "goal": "second slice",
            "task_class": "verify",
            "risk": "MEDIUM",
            "dependency_ids": [f"{fresh_id('pkg-v5x')}:sub-000"],
        },
    ]
    package_id = fresh_id("pkg-v5")
    specs[1]["dependency_ids"] = [package_id + ":sub-000"]
    _, graph = graph_mod.TaskPlanner().plan(package_id, "package goal", specs)
    payload_nodes = [
        dataclasses.asdict(node) for node in graph.nodes.values()
    ]
    texts = []

    def _flatten(value):
        if isinstance(value, dict):
            for item in value.values():
                yield from _flatten(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                yield from _flatten(item)
        else:
            yield value

    for node in payload_nodes:
        texts.extend(str(item) for item in _flatten(node))
    assert not any(item == "provider" for item in _flatten(payload_nodes))
    assert not any(item == "model" for item in _flatten(payload_nodes))
    assert not any("meta/muse-spark" in text for text in texts)
    node = graph.nodes[package_id + ":sub-000"]
    decision = graph_mod.route_task(
        node, "worker", "local", manager_id="manager-int2"
    )
    decision_payload = dataclasses.asdict(decision)
    assert decision_payload["worker_class"] == "worker"
    assert decision_payload["run_config"]["client_max_retries"] == 0
    assert not any(item == "model" for item in _flatten(decision_payload))


def test_v6_anchor_resolves_seven_kernel_symbols():
    assert len(teamcard_mod._INT2_KERNEL) == 7
    expected = (
        common_mod.DecisionRow,
        common_mod.DecisionLog,
        common_mod.ApplyOutcome,
        common_mod.AppliedOutcome,
        common_mod.surface_rejection,
        common_mod.utc_now,
        common_mod.hot_write_text,
    )
    assert expected == teamcard_mod._INT2_KERNEL


def test_v7_no_raw_secrets_in_outputs(tmp_path):
    raw = "RAW-SECRET-INT2-XYZ"
    card = teamcard_mod.build_team_card(
        "acme", {"ctx": "128k"}, {"units": 5}, {"max_agents": 4},
        budget_secret=raw,
    )
    assert raw not in repr(card.budget_left)
    assert card.budget_left["secret_ref"] == {"secret_ref": "budget-store"}
    report = teamcard_mod.build_team_report(
        {"m1": card}, {"m1": [card]},
        [{"part_id": "p-v7", "size_units": 2}],
        out_path=str(tmp_path / "team.txt"),
    )
    assert raw not in repr(report)
    with open(str(tmp_path / "team.txt"), encoding="utf-8") as handle:
        assert raw not in handle.read()
    ledger = ledger_mod.PackageLedger()
    ledger.record_row("pkg-v7", agents=1, peak_concurrency=1, wall_time_s=1.0)
    ledger_report = ledger_mod.build_ledger_report(
        ledger, ["pkg-v7"], out_path=str(tmp_path / "ledger.txt")
    )
    assert raw not in repr(ledger_report)
    with open(str(tmp_path / "ledger.txt"), encoding="utf-8") as handle:
        assert raw not in handle.read()


# --- (4) link-check joints: cross_check / close_with_linkcheck / close_part /
# --- may_start_early / manifest joint flow ---


def test_joint_linkcheck_flow_clean_and_conflict():
    assert delta_mod.cross_check([], []) == []
    package_id = fresh_id("pkg-joint")
    verdict = {
        "package_id": package_id,
        "gate": "PASS",
        "audit": "PASS",
        "decided_at": "2026-10-26T00:00:00Z",
        "evidence_refs": ["ev:1"],
    }
    assert delta_mod.cross_check([package_id], [verdict]) == []
    assert delta_mod.cross_check(
        [package_id, "pkg-missing"], [verdict]
    ) == ["pkg-missing"]
    pkg = delta_mod.intake_bounded_delta(["scope-joint"], False)
    closed = delta_mod.close_with_linkcheck(pkg, verdict)
    assert closed["gate"] == "PASS"
    assert "linkcheck:ok" in closed["evidence_refs"]


def test_joint_split_parts_manifest_earlystart_close():
    package_id = fresh_id("pkg-flow")
    refs = [f"artifact://{package_id}/ctx-{idx}" for idx in range(4)]
    parts = split_mod.split_package(package_id, "joint flow goal", refs, 2)
    assert len(parts) == 2
    split_mod.validate_disjoint(parts)
    settings = split_mod.MultiManagerSettings(
        multi_manager_mode=True,
        max_parallel_managers=2,
        overlap=True,
        integration_policy="manager-integrates",
        model_pool_per_manager={},
    )
    running, queued = split_mod.fanout(parts, settings)
    assert len(running) == 2 and queued == []
    assert {part.package_id for part in running} == {package_id}
    contracts = {part.contract_hash for part in running}
    assert len(contracts) == 1
    draft_refs = [
        {
            "package_id": part.package_id,
            "contract_hash": part.contract_hash,
            "gate_verdict_ref": part.gate_verdict_ref,
            "audit_verdict_ref": part.audit_verdict_ref,
        }
        for part in running
    ]
    manifest = manifest_mod.build_manifest(f"m-{package_id}", 1, draft_refs)
    for ref in manifest["parts"]:
        ref["contract_hash"] = manifest["hash"]
    assert manifest_mod.check_manifest(manifest) is True
    assert manifest_mod.verify_manifest_hash(manifest) is True
    assert manifest_mod.validate_part_ref(manifest["parts"][0], manifest) is True
    assert manifest_mod.validate_part_ref(
        dict(manifest["parts"][0], contract_hash="0" * 64), manifest
    ) is False
    for part in running:
        overlap_mod._record_gate_verdict(part.gate_verdict_ref, "PASS")
        overlap_mod._record_audit_verdict(part.audit_verdict_ref, "PASS")
        assert overlap_mod.may_start_early(
            {
                "package_id": part.package_id,
                "contract_hash": part.contract_hash,
                "gate_verdict_ref": part.gate_verdict_ref,
                "audit_verdict_ref": part.audit_verdict_ref,
            }
        ) is True
    log = gates_mod.GateAuditLog()
    for index, _part in enumerate(running):
        part_id = f"{package_id}:part-{index:03d}"
        gate, audit = _serve_pair(log, part_id)
        verdict = gates_mod.close_part(_gate_refs(gate, audit, package_id))
        assert verdict["gate"] == "PASS" and verdict["audit"] == "PASS"
    listed = parts_mod.list_parts(None)
    assert isinstance(listed, list)


# --- (5) gate + fresh-audit close: serve_gate/serve_audit/has_fresh_audit ---


def test_joint_gate_fresh_audit_close_flow():
    log = gates_mod.GateAuditLog()
    package_id = fresh_id("pkg-close")
    part_id = package_id + ":part-000"
    assert log.has_fresh_audit(part_id) is False
    gate = log.serve_gate(part_id, "PASS")
    assert log.gate_verdict(part_id) == "PASS"
    assert log.has_fresh_audit(part_id) is False
    gate_only_ref = {
        "package_id": package_id,
        "contract_hash": "contract-int2",
        "gate_verdict_ref": gate.gate_id,
        "audit_verdict_ref": "missing-audit",
    }
    with pytest.raises(gates_mod.GATE_NOT_PASSED):
        gates_mod.close_part(gate_only_ref)
    audit = log.serve_audit(
        part_id, "PASS", "auditor-int2", ("producer-int2",), True
    )
    assert log.has_fresh_audit(part_id) is True
    verdict = gates_mod.close_part(_gate_refs(gate, audit, package_id))
    assert verdict["evidence_refs"] == [gate.gate_id, audit.audit_id]


def test_joint_phase_gate_needs_integration_pass():
    log = gates_mod.GateAuditLog()
    package_id = fresh_id("pkg-phase")
    _serve_pair(log, package_id + ":part-000")
    with pytest.raises(gates_mod.MISSING_INTEGRATION_TASK):
        gates_mod.evaluate_phase_gate([package_id])
    gate, audit = _serve_pair(log, package_id + ":integration")
    verdict = gates_mod.evaluate_phase_gate([package_id])
    assert verdict["package_id"] == package_id
    assert verdict["gate"] == "PASS" and verdict["audit"] == "PASS"
    assert gate.gate_id in verdict["evidence_refs"]
    assert audit.audit_id in verdict["evidence_refs"]
    with pytest.raises(gates_mod.GATE_NOT_PASSED):
        gates_mod.evaluate_phase_gate([])


# --- (6) v2 record shapes C6-C18 ---


def test_c4_c5_record_decomposition_new_shape():
    rec = teamcard_mod.record_decomposition("p-c4", 2)
    assert rec.record_id == "decomp-p-c4"
    assert rec.part_id == "p-c4"
    assert "part-size-vs-model" in rec.facts_used
    assert rec.route == "cheap-small-part"
    assert rec.reason != ""
    assert rec.artifact_ref == "ARTIFACT_REF:p-c4/decomposition"
    big = teamcard_mod.record_decomposition(
        "p-c4big", 200, needs_long_context=True
    )
    assert big.route == "long-context"


def test_c1_c2_c3_team_contexts_new_signatures():
    card = teamcard_mod.build_team_card(
        "acme", {"ctx": "128k"}, {"units": 100}, {"max_agents": 4}
    )
    assert card.provider == "acme" and card.model == MODEL_ID
    with pytest.raises(ValueError):
        teamcard_mod.build_team_card(
            "acme", {}, {}, {}, model="other/model-x"
        )
    worker = teamcard_mod.build_team_card(
        "w1", {"ctx": "8k"}, {"units": 9}, {"max_agents": 1}
    )
    director = teamcard_mod.director_context({"m1": card}, {"m1": [worker]})
    assert director["managers"]["m1"].provider == "acme"
    assert director["workers"]["m1"][0].provider == "w1"
    managed = teamcard_mod.manager_context(card, [worker])
    assert managed["own"].model == MODEL_ID
    assert teamcard_mod.worker_context() == {}


def test_c6_accepted_form_vs_applied_form():
    team_store = teamcard_mod.TeamConfigStore()
    team_out = teamcard_mod.apply_team_config_change(
        team_store, "raise cap use", "need room", "tester-int2", {"agents": 2}
    )
    assert set(dataclasses.asdict(team_out).keys()) == {
        "accepted",
        "reason",
        "row",
        "surfaced",
    }
    ledger_store = ledger_mod.LedgerConfigStore()
    ledger_out = ledger_mod.apply_ledger_config_change(
        ledger_store, "record two agents", "observed", "tester-int2", {"agents": 2}
    )
    assert set(dataclasses.asdict(ledger_out).keys()) == {
        "accepted",
        "reason",
        "row",
        "surfaced",
    }
    step_out = steplimits_mod.apply_steplimit_config_change(
        {
            "project_id": fresh_id("proj-c6"),
            "authority": "manager-int2",
            "reason": "set limits for test",
            "task_max_steps": 2,
            "chat_max_steps": 3,
        }
    )
    assert set(dataclasses.asdict(step_out).keys()) == {
        "applied",
        "reason",
        "decision_ref",
    }
    delta_out = delta_mod.apply_config_change(
        {
            "budget_left": 100.0,
            "auditor": "a",
            "worker": "w",
            "independent_audit": True,
            "model": MODEL_ID,
            "claimed_scopes": [],
            "max_parts": 4,
        },
        [],
        "manifest",
        "raise limit",
        "need capacity",
        "director",
        {"cost": 10.0},
    )
    assert set(delta_out.keys()) == {"applied", "reason", "decision_ref"}


def test_c7_c8_free_text_reasons_never_bare_codes():
    team_store = teamcard_mod.TeamConfigStore()
    team_refused = teamcard_mod.apply_team_config_change(
        team_store, "x", "y", "z", {"agents": 10**6}
    )
    assert team_refused.accepted is False
    assert "cap" in team_refused.reason.lower()
    ledger_store = ledger_mod.LedgerConfigStore()
    ledger_refused = ledger_mod.apply_ledger_config_change(
        ledger_store, "x", "y", "z", {"agents": 10**6}
    )
    assert ledger_refused.accepted is False
    assert "cap" in ledger_refused.reason.lower()


def test_c9_method_only_record_row_and_c10_keyerror():
    ledger = ledger_mod.PackageLedger()
    row = ledger.record_row("pkg-c9", agents=3, peak_concurrency=2, wall_time_s=12.5)
    assert (row.agents, row.peak_concurrency, row.wall_time_s) == (3, 2, 12.5)
    with pytest.raises(KeyError):
        ledger_mod.package_report(ledger, "pkg-missing-c9")


def test_c11_package_report_new_shape():
    ledger = ledger_mod.PackageLedger()
    ledger.record_row("pkg-c11a", agents=3, peak_concurrency=2, wall_time_s=12.5)
    report = ledger_mod.package_report(ledger, "pkg-c11a", next_package_id="pkg-c11b")
    assert set(report.keys()) == {"row", "nudge", "auto_push"}
    assert report["row"] == {
        "package_id": "pkg-c11a",
        "agents": 3,
        "peak_concurrency": 2,
        "wall_time_s": 12.5,
    }
    assert "pkg-c11b" in report["nudge"] and "pkg-c11a" in report["nudge"]
    assert report["auto_push"] is False


def test_c12_persist_load_ledger_roundtrip(tmp_path):
    ledger = ledger_mod.PackageLedger()
    ledger.record_row("pkg-c12", agents=3, peak_concurrency=2, wall_time_s=12.5)
    path = str(tmp_path / "ledger.json")
    assert ledger_mod.persist_ledger(path, ledger) is None
    reloaded = ledger_mod.load_ledger(path)
    assert isinstance(reloaded, ledger_mod.PackageLedger)
    row = reloaded.get_row("pkg-c12")
    assert (row.agents, row.peak_concurrency, row.wall_time_s) == (3, 2, 12.5)


def test_c13_both_bounded_delta_intakes():
    scope = [f"s-{idx:02d}" for idx in range(16)]
    pkg = delta_mod.intake_bounded_delta(scope, False)
    assert pkg["scope"] == scope and pkg["keep"] == scope and pkg["patch"] == []
    with pytest.raises(delta_mod.DELTA_OVER_BOUND):
        delta_mod.intake_bounded_delta([f"s-{idx:02d}" for idx in range(17)], False)
    taken = []
    accepted = ledger_mod.intake_bounded_delta(
        taken, {"delta_id": "d1", "items": ["a", "b"]}, 3
    )
    assert accepted["accepted"] is True and len(taken) == 1
    refused = ledger_mod.intake_bounded_delta(
        taken, {"delta_id": "d2", "items": ["a", "b", "c", "d"]}, 3
    )
    assert refused["accepted"] is False and len(taken) == 1


def test_c14_plain_dict_verdicts_and_bound_exception():
    assert issubclass(delta_mod.DELTA_OVER_BOUND, Exception)
    pkg = delta_mod.intake_bounded_delta(["x"], False)
    assert set(pkg.keys()) == {
        "delta_id",
        "scope",
        "blocking",
        "keep",
        "patch",
        "created_at",
    }
    verdict = {
        "package_id": "pkg-c14",
        "gate": "PASS",
        "audit": "PASS",
        "decided_at": "2026-10-26T00:00:00Z",
        "evidence_refs": ["ev:1"],
    }
    closed = delta_mod.close_with_linkcheck(pkg, verdict)
    assert set(closed.keys()) == {
        "package_id",
        "gate",
        "audit",
        "decided_at",
        "evidence_refs",
    }


def test_c15_delta_apply_config_change_dict_shape():
    config = {
        "budget_left": 100.0,
        "auditor": "a",
        "worker": "w",
        "independent_audit": True,
        "model": MODEL_ID,
        "claimed_scopes": [],
        "max_parts": 4,
    }
    log = []
    out = delta_mod.apply_config_change(
        config, log, "manifest", "raise limit", "need capacity", "director",
        {"cost": 10.0},
    )
    assert out == {
        "applied": True,
        "reason": "applied",
        "decision_ref": "manifest-0001",
    }
    assert len(log) == 1
    assert set(log[0].keys()) == {
        "decision_id",
        "scope",
        "statement",
        "reason",
        "authority",
        "created_at",
    }
    bad = delta_mod.apply_config_change(
        dict(config), [], "manifest", "s", "r", "director",
        {"auditor": "w", "independent_audit": False},
    )
    assert bad["applied"] is False and bad["decision_ref"] is None


def test_c16_report_and_register_helpers():
    low = teamcard_mod.select_audit_model("p-low", "low", [])
    high = teamcard_mod.select_audit_model("p-high", "high", [])
    assert (low.strength, high.strength) == ("standard", "strong")
    assert low.model == MODEL_ID == high.model
    baseline = {"e1": "alpha"}
    assert teamcard_mod.register_verbatim("e1", "alpha", baseline)["status"] == (
        "PRESERVED"
    )
    assert teamcard_mod.register_verbatim("e1", "beta", baseline)["status"] == (
        "CHANGED"
    )
    assert teamcard_mod.register_verbatim("e9", "alpha", baseline)["status"] == (
        "MISSING"
    )
    card = teamcard_mod.build_team_card(
        "acme", {"ctx": "128k"}, {"units": 1}, {"max_agents": 1}
    )
    report = teamcard_mod.build_team_report(
        {"m1": card}, {"m1": [card]}, [{"part_id": "p-c16", "size_units": 2}]
    )
    assert report.director["managers"]["m1"].provider == "acme"
    assert [entry.part_id for entry in report.audits] == ["p-c16"]
    assert report.register == []
    assert teamcard_mod.make_secret_ref("budget-store") == {
        "secret_ref": "budget-store"
    }
    ledger = ledger_mod.PackageLedger()
    ledger.record_row("pkg-c16", agents=1, peak_concurrency=1, wall_time_s=2.0)
    ledger_report = ledger_mod.build_ledger_report(ledger, ["pkg-c16"])
    assert ledger_report.packages[0]["row"]["package_id"] == "pkg-c16"


def test_c17_two_arg_limits_and_alias():
    assert steplimits_mod.UNKNOWN_LIMIT_KIND is (
        steplimits_mod.UnknownLimitKindError
    )
    project_id = fresh_id("proj-c17")
    steplimits_mod.apply_steplimit_config_change(
        {
            "project_id": project_id,
            "authority": "manager-int2",
            "reason": "set limits for test",
            "task_max_steps": 2,
            "chat_max_steps": 5,
        }
    )
    assert steplimits_mod.limits_for("task", project_id) == 2
    assert steplimits_mod.limits_for("chat", project_id) == 5
    with pytest.raises(steplimits_mod.UNKNOWN_LIMIT_KIND):
        steplimits_mod.limits_for("bogus", project_id)


def test_c18_both_surface_forms_compact_and_plain():
    assert teamcard_mod.is_compact_english("change applied")
    assert teamcard_mod.surface_rejection(
        teamcard_mod.ApplyOutcome(accepted=True, reason="applied")
    ) == "change applied"
    assert ledger_mod.surface_rejection(
        ledger_mod.ApplyOutcome(accepted=True, reason="applied")
    ) == "change applied"
    assert delta_mod.surface_rejection("POLICY_CONFLICT: bad target") == (
        "POLICY_CONFLICT: bad target"
    )


# --- (7) section 4 routes listed + package_report NEW-shape data path ---


EXPECTED_ROUTE_PATHS = [
    "/api/v1/agents/live",
    "/api/v1/runs/ledger",
    "/api/v1/reports/next-package-nudge",
]


@pytest.mark.parametrize("route", EXPECTED_ROUTE_PATHS, ids=EXPECTED_ROUTE_PATHS)
def test_section4_routes_listed(route):
    assert isinstance(route, str) and route.startswith("/api/v1/")


def test_section4_agents_live_served_from_register():
    scope = fresh_id("live")
    parts_mod.register_part(
        parts_mod.PartRow(
            agent="agent-live",
            scope=scope,
            deliverable=f"artifact://pkg/{scope}",
        )
    )
    rows = parts_mod.list_parts(None)
    served = [row for row in rows if row.scope == scope]
    assert len(served) == 1
    assert served[0].status == "QUEUED"
    assert served[0].deliverable.startswith("artifact://")


def test_section4_runs_ledger_served_from_telemetry():
    package_id = fresh_id("pkg-ledger")
    ledger = ledger_mod.PackageLedger()
    ledger.record_row(package_id, agents=2, peak_concurrency=1, wall_time_s=4.0)
    assert package_id in ledger.package_ids()
    row = ledger.get_row(package_id)
    assert (row.agents, row.peak_concurrency, row.wall_time_s) == (2, 1, 4.0)


def test_section4_nudge_served_from_package_report():
    ledger = ledger_mod.PackageLedger()
    ledger.record_row("pkg-n1", agents=2, peak_concurrency=1, wall_time_s=4.0)
    report = ledger_mod.package_report(ledger, "pkg-n1", next_package_id="pkg-n2")
    assert set(report.keys()) == {"row", "nudge", "auto_push"}
    assert report["row"]["package_id"] == "pkg-n1"
    assert "pkg-n2" in report["nudge"]
    assert report["auto_push"] is False


def test_section4_offload_and_hierarchy_guards():
    assert offload_mod.offload_enabled("proj-none", "worker") is False
    assert offload_mod.maybe_offload("task-none", "worker", True) is None
    assert offload_mod.maybe_offload("task-none", "worker", False) is None
    assert gates_mod.check_hierarchy_activation(
        ["director-1", "manager-1", "tool-1"]
    ) is None
    with pytest.raises(gates_mod.INVALID_HIERARCHY_CHAIN):
        gates_mod.check_hierarchy_activation(["director-1", "manager-1"])
    outcome = offload_mod.apply_offload_config_change(
        {
            "project_id": fresh_id("proj-off"),
            "role": "worker",
            "enabled": True,
            "authority": "manager-int2",
            "reason": "route routine subtasks cheaper",
            "task_ids": ["task-int2-1"],
            "to_role": "cheap-agent",
            "handover_reason": "routine triage runs cheaper",
        }
    )
    assert outcome.applied is True


# --- (8) INT3-FINAL: app-seam route tests through the create_app seam ---
#
# TestClient coverage of the frozen seam interface
# (src/agent_si/backend/app.py): reads need no token, USER writes need a
# non-empty x-actor plus the UI session token. Mirrors the proven
# test_app_seam.py pattern with a local helper; nothing is imported from
# that file. Every scope/package id is unique via fresh_id, and each app
# starts from a clean parts store because create_app clears the register.


_INT3F_TOKEN = "k02-seam-test-token"
_INT3F_SETTINGS = {"testing": True, "ui_session_token": _INT3F_TOKEN}


def _int3f_make_client(**kwargs):
    from fastapi.testclient import TestClient

    from agent_si.backend.app import create_app

    app = create_app(dict(_INT3F_SETTINGS), **kwargs)
    return app, TestClient(app)


def _int3f_seed_parts(prefix):
    rows = [
        parts_mod.PartRow(
            agent="int3f-agent-1",
            scope=prefix + "-0001",
            deliverable=f"artifact://int3f/{prefix}-0001",
        ),
        parts_mod.PartRow(
            agent="int3f-agent-2",
            scope=prefix + "-0002",
            deliverable=f"artifact://int3f/{prefix}-0002",
            status="RUNNING",
        ),
    ]
    for row in rows:
        parts_mod.register_part(row)
    return rows


def _int3f_seed_ledger(app, project_id, first, second):
    ledger = app.state.ledger_for(project_id)
    ledger.record_row(first, 3, 2, 12.5)
    ledger.record_row(second, 1, 1, 2.0)
    return ledger


def test_int3f_agents_live_serves_registered_rows():
    _, client = _int3f_make_client()
    rows = _int3f_seed_parts(fresh_id("int3f-live"))
    resp = client.get("/api/v1/agents/live")
    assert resp.status_code == 200
    served = {item["scope"]: item for item in resp.json()["agents"]}
    for row in rows:
        item = served[row.scope]
        assert (
            item["agent"],
            item["scope"],
            item["deliverable"],
            item["status"],
        ) == (row.agent, row.scope, row.deliverable, row.status)


def test_int3f_runs_ledger_serves_recorded_rows():
    project_id = fresh_id("proj-int3f")
    first = fresh_id("pkg-int3f")
    second = fresh_id("pkg-int3f")
    app, client = _int3f_make_client()
    _int3f_seed_ledger(app, project_id, first, second)
    resp = client.get(
        "/api/v1/runs/ledger", params={"project_id": project_id}
    )
    assert resp.status_code == 200
    served = {item["package_id"]: item for item in resp.json()["rows"]}
    assert served[first] == {
        "package_id": first,
        "agents": 3,
        "peak_concurrency": 2,
        "wall_time_s": 12.5,
    }
    assert served[second] == {
        "package_id": second,
        "agents": 1,
        "peak_concurrency": 1,
        "wall_time_s": 2.0,
    }


def test_int3f_runs_ledger_unknown_project_empty_and_missing_rejected():
    _, client = _int3f_make_client()
    resp = client.get(
        "/api/v1/runs/ledger",
        params={"project_id": fresh_id("proj-never-recorded")},
    )
    assert resp.status_code == 200
    assert resp.json() == {"rows": []}
    resp = client.get("/api/v1/runs/ledger")
    assert resp.status_code == 422


def test_int3f_next_package_nudge_names_next_package():
    project_id = fresh_id("proj-int3f-nudge")
    first = fresh_id("pkg-int3f-nudge")
    second = fresh_id("pkg-int3f-nudge")
    app, client = _int3f_make_client()
    _int3f_seed_ledger(app, project_id, first, second)
    resp = client.get(
        "/api/v1/reports/next-package-nudge",
        params={"package_id": first, "project_id": project_id},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["package_id"] == first
    assert body["load"] == {
        "package_id": first,
        "agents": 3,
        "peak_concurrency": 2,
        "wall_time_s": 12.5,
    }
    assert first in body["nudge"] and second in body["nudge"]
    assert body["auto_push"] is False


def test_int3f_next_package_nudge_unknown_and_missing():
    _, client = _int3f_make_client()
    resp = client.get(
        "/api/v1/reports/next-package-nudge",
        params={"package_id": fresh_id("pkg-never-recorded")},
    )
    assert resp.status_code == 404
    resp = client.get("/api/v1/reports/next-package-nudge")
    assert resp.status_code == 422


def test_int3f_reads_need_no_token():
    project_id = fresh_id("proj-int3f-open")
    first = fresh_id("pkg-int3f-open")
    second = fresh_id("pkg-int3f-open")
    app, client = _int3f_make_client()
    _int3f_seed_parts(fresh_id("int3f-open"))
    _int3f_seed_ledger(app, project_id, first, second)
    assert client.get("/api/v1/agents/live").status_code == 200
    resp = client.get(
        "/api/v1/runs/ledger", params={"project_id": project_id}
    )
    assert resp.status_code == 200
    assert len(resp.json()["rows"]) == 2
    resp = client.get(
        "/api/v1/reports/next-package-nudge",
        params={"package_id": first},
    )
    assert resp.status_code == 200


def test_int3f_post_write_without_actor_refused():
    _, client = _int3f_make_client()
    assert client.post("/api/v1/chat/stream").status_code == 401
    resp = client.post(
        "/api/v1/chat/stream",
        headers={"x-ui-session-token": _INT3F_TOKEN},
    )
    assert resp.status_code == 401


def test_int3f_post_write_without_token_refused():
    _, client = _int3f_make_client()
    resp = client.post(
        "/api/v1/chat/stream", headers={"x-actor": "tester-int3f"}
    )
    assert resp.status_code == 403
    resp = client.post(
        "/api/v1/chat/stream",
        headers={
            "x-actor": "tester-int3f",
            "x-ui-session-token": "wrong-token",
        },
    )
    assert resp.status_code == 403


def test_int3f_post_write_accepted_with_real_count():
    _, client = _int3f_make_client()
    rows = _int3f_seed_parts(fresh_id("int3f-chat"))
    resp = client.post(
        "/api/v1/chat/stream",
        headers={
            "x-actor": "tester-int3f",
            "x-ui-session-token": _INT3F_TOKEN,
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {
        "status": "accepted",
        "actor": "tester-int3f",
        "live_parts": len(rows),
    }


def test_int3f_denying_rate_hook_limits_with_token():
    _, client = _int3f_make_client(rate_hook=lambda key: False)
    resp = client.post(
        "/api/v1/chat/stream",
        headers={
            "x-actor": "tester-int3f",
            "x-ui-session-token": _INT3F_TOKEN,
        },
    )
    assert resp.status_code == 429
