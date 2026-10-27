"""K03 STEP1 behaviour contract: audit independence.

Rows 7, 9-13, 13, R-304, R-355, M-P1-41, MVP_ACCEPT-117, MVP_ACCEPT-224,
ARCH-653, ARCH-740, ARCH-741, ARCH-745, BP07-53, BP07-54, SPEC 0A, SPEC 18,
SPEC 45A. MUST FAIL now (RED).

Entry points: real stub symbols are loaded from
``src/agent_si/assurance/{audit_coordinator,audit_registry,audit_records,
grounding}.py`` via the loader below (no copies, no mocks of the unit
under test; fakes of providers/models are plain data marked FAKE-OF with
the real module path). Stub behaviour methods live on Protocol classes, so
each test uses a thin concrete subclass defined here (inheriting the real
stub methods; STEP2 fills the base bodies). Registering the loaded module
in ``sys.modules`` under its synthetic name is required: the stubs use
``from __future__ import annotations`` with dataclasses, which resolves
string annotations through ``sys.modules``.
STEP1 RED mechanism per test: stub bodies are ``...``, so every behaviour
assertion fails (missing raise, None attribute, wrong value). STEP2 fills
real behaviour and turns these GREEN. Names below follow the stub files as
read; anything a row needs but no stub symbol provides is recorded as a
defect + NOT-DONE in the return, never added here. Each error code is
asserted in its own test.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

_ASSURANCE = (
    pathlib.Path(__file__).resolve().parents[3]
    / "src"
    / "agent_si"
    / "assurance"
)

#: Exact shipped-preset model id (never retyped, never a second id).
MODEL = "meta/muse-spark-1.3-contributor"

#: Fixture auditor model, outside the implementer set so the default path is
#: L2-clean. FAKE-OF: src/agent_si/providers/registry/provider_api.py.
AUDITOR_MODEL = "meta/muse-spark-1.3-auditor"

PROJECT = "proj-k03-audit1"
TASK = "task-k03-audit1"
RUN = "run-k03-audit1"
CONTRACT_HASH = "contract-hash-k03-1"


def _load(name):
    path = _ASSURANCE / ("%s.py" % name)
    assert path.is_file(), "STEP1 stub missing: %s" % path
    module_name = "k03_assurance_%s" % name
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_cache = {}


def _mod(name):
    if name not in _cache:
        _cache[name] = _load(name)
    return _cache[name]


def _coordinator():
    module = _mod("audit_coordinator")

    class _ConcreteCoordinator(module.AuditCoordinator):
        pass

    return _ConcreteCoordinator(), module


def _registry():
    module = _mod("audit_registry")

    class _ConcreteRegistry(module.AuditorRegistry):
        pass

    return _ConcreteRegistry(), module


def _log():
    module = _mod("audit_records")

    class _ConcreteLog(module.AuditLog):
        pass

    return _ConcreteLog(), module


def _grounding():
    module = _mod("grounding")

    class _ConcreteGrounding(module.GroundingPort):
        pass

    return _ConcreteGrounding(), module


def _turn(**overrides):
    module = _mod("audit_coordinator")
    kwargs = {
        "turn_ref": "turn-1",
        "project_id": PROJECT,
        "task_id": TASK,
        "run_id": RUN,
        "work_refs": ("work-1",),
        "artifact_refs": ("art-read-1", "art-write-1"),
        "evidence_refs": ("ev-1",),
        "producer_session_refs": ("sess-producer-1", "sess-producer-2"),
        "contract_hash": CONTRACT_HASH,
    }
    kwargs.update(overrides)
    return module.ServedTurn(**kwargs)


def _decision(**overrides):
    module = _mod("audit_registry")
    kwargs = {
        "decision_id": "dec-1",
        "project_id": PROJECT,
        "scope": "scope-1",
        "statement": "reuse auditor pair for scope-1",
        "reason": "same scope, recorded and user-visible",
        "authority": "USER",
        "decided_by": "user-1",
        "visible_to_user": True,
        "user_resolution_ref": None,
        "created_at": "2026-10-26T00:00:00Z",
    }
    kwargs.update(overrides)
    return module.SourcingDecision(**kwargs)


def _evidenced_candidate(provider_id="prov-audit", instance="i-1"):
    _, module = _registry()
    # FAKE-OF: src/agent_si/providers/registry/provider_api.py.
    return module.AuditorCandidate(
        provider_id=provider_id,
        provider_instance=instance,
        model=AUDITOR_MODEL,
        capability_evidence_refs=("ev-cap-1",),
    )


def test_assurance_runs_on_every_served_turn():  # ROW 7
    coordinator, _ = _coordinator()
    audit_id = coordinator.audit_served_turn(_turn())
    assert isinstance(audit_id, str) and audit_id


def test_empty_work_fails():  # ROW 7
    coordinator, _ = _coordinator()
    with pytest.raises(Exception) as exc_info:
        coordinator.audit_served_turn(
            _turn(turn_ref="turn-empty", work_refs=(), artifact_refs=()))
    assert exc_info.value.code == "EMPTY_WORK_REFUSED"


def test_fresh_auditor_instance_per_audit():  # ROWS 9-13
    coordinator, _ = _coordinator()
    first = coordinator.audit_with_fresh_auditor(_turn(run_id="run-a-1"))
    second = coordinator.audit_with_fresh_auditor(_turn(run_id="run-a-2"))
    assert isinstance(first, str) and first
    assert isinstance(second, str) and second
    assert first != second


def test_fresh_auditor_instance_per_reaudit():  # ROWS 9-13
    coordinator, _ = _coordinator()
    original = coordinator.audit_with_fresh_auditor(_turn(run_id="run-r-1"))
    reaudit = coordinator.reaudit(original, None)
    assert isinstance(reaudit, str) and reaudit
    assert reaudit != original


def test_reaudit_bounded_by_audit_correction_budget():  # MVP_ACCEPT-117
    # STEP2 contract: coordinator-persisted audit records are visible to
    # AuditLog.load (same lane store); the correction that exhausts the
    # per-scope budget (AUDIT_CORRECTION_MAX == 2) keeps REWORK and
    # escalates handling with REWORK_BUDGET_EXHAUSTED.
    coordinator, _ = _coordinator()
    log, records = _log()
    first = coordinator.audit_with_fresh_auditor(_turn(run_id="run-b-1"))
    second = coordinator.reaudit(first, None)
    third = coordinator.reaudit(second, None)
    assert len({first, second, third}) == 3
    budget = coordinator.remaining_correction_budget("scope-b-1")
    assert budget.limit == 2
    exhausted = log.load(third)
    assert exhausted.result == records.AuditResult.REWORK
    assert exhausted.handling_disposition == (
        records.AuditHandlingDisposition.ESCALATE)


def test_recorded_pair_reuse_returns_visible_decision():  # ROW 13
    registry, _ = _registry()
    recorded = registry.record_pair_reuse(_decision())
    assert recorded.decision_id == "dec-1"
    assert recorded.visible_to_user is True


def test_reaudit_with_recorded_pair_reuse_is_allowed():  # ROW 13
    coordinator, _ = _coordinator()
    registry, _ = _registry()
    original = coordinator.audit_with_fresh_auditor(_turn(run_id="run-p-1"))
    registry.record_pair_reuse(_decision(decision_id="dec-reuse-1"))
    reaudit = coordinator.reaudit(original, "dec-reuse-1")
    assert isinstance(reaudit, str) and reaudit
    assert reaudit != original


def test_unrecorded_pair_reuse_refused():  # ROW 13
    # No stub error vocabulary names this refusal, so only the refusal
    # itself is pinned here (no .code); STEP2 chooses the error type.
    coordinator, _ = _coordinator()
    original = coordinator.audit_with_fresh_auditor(_turn(run_id="run-p-2"))
    with pytest.raises(Exception):
        coordinator.reaudit(original, "never-recorded-ref")


def test_contributor_in_auditor_set_refused():  # R-355
    coordinator, _ = _coordinator()
    with pytest.raises(Exception) as exc_info:
        coordinator.refuse_contributor("audit-1", ("contrib-1",))
    assert exc_info.value.code == "AUDIT_INDEPENDENCE_REJECTED"


def test_self_audit_refused():  # R-355
    coordinator, _ = _coordinator()
    with pytest.raises(Exception) as exc_info:
        coordinator.refuse_contributor("audit-1", ("auditor-self-1",))
    assert exc_info.value.code == "AUDIT_INDEPENDENCE_REJECTED"


def test_accepted_risk_off_by_default():  # R-355
    coordinator, _ = _coordinator()
    gate = coordinator.accepted_risk_allowed(None)
    assert gate.allowed is False


def test_accepted_risk_needs_user_policy():  # R-355
    coordinator, _ = _coordinator()
    gate = coordinator.accepted_risk_allowed("user-policy-1")
    assert gate.allowed is True
    assert gate.policy_ref == "user-policy-1"


def test_auditor_judges_real_files_read_and_written():  # R-304
    grounding, _ = _grounding()
    for artifact_id in ("art-read-1", "art-write-1"):
        grounded = grounding.ground_artifact(
            _mod("grounding").GroundingRequest(
                artifact_id=artifact_id,
                contract_hash=CONTRACT_HASH,
                evidence_refs=("ev-1",),
            )
        )
        assert grounded.artifact_id == artifact_id
        assert grounded.path
        assert grounded.hash


def test_close_stage_leaves_queryable_row():  # M-P1-41
    coordinator, _ = _coordinator()
    log, records = _log()
    audit_id = coordinator.audit_with_fresh_auditor(_turn(run_id="run-c-1"))
    row_id = coordinator.close_stage(TASK, "scope-c-1", audit_id)
    assert isinstance(row_id, str) and row_id
    record = records.AuditRecord(
        audit_id=audit_id,
        project_id=PROJECT,
        task_id=TASK,
        run_id="run-c-1",
        audit_scope_id="scope-c-1",
        audit_sequence=1,
        supersedes_audit_id=None,
        context_session_ref="sess-audit-1",
        producer_session_refs=("sess-producer-1", "sess-producer-2"),
        implementer_model_ids=(MODEL,),
        contract_hash=CONTRACT_HASH,
        audit_policy_ref="audit-policy-1",
        artifact_refs=("art-read-1", "art-write-1"),
        evidence_refs=("ev-1",),
        requirement_verdicts=(
            records.RequirementVerdictRow(
                requirement_id="req-1",
                verdict=records.RequirementVerdict.MISSING,
                evidence_refs=(),
            ),
        ),
        context_integrity="PASS",
        result=records.AuditResult.BLOCKED,
        handling_disposition=records.AuditHandlingDisposition.BLOCK,
        failure_class=None,
        created_at="2026-10-26T00:00:00Z",
    )
    assert log.append(record) == record
    assert audit_id in [row.audit_id for row in log.list_by_task(TASK)]
    latest = log.latest_for_scope("scope-c-1")
    assert latest.audit_sequence == 1
    assert latest.requirement_verdicts[0].verdict == (
        records.RequirementVerdict.MISSING)


def test_no_eligible_auditor_raises_without_self_audit_fallback():  # ARCH-653
    # Also proves BP07-20: the registry signal carries NO_ELIGIBLE_AUDITOR.
    registry, _ = _registry()
    with pytest.raises(Exception) as exc_info:
        registry.select_auditor("worker", (MODEL,), "L2")
    assert exc_info.value.code == "NO_ELIGIBLE_AUDITOR"
    assert registry.sourcing_state("scope-fresh-653") == "BLOCKED"


def test_auditor_sourcing_independent_of_implementers():  # ARCH-740
    registry, _ = _registry()
    registry.register_candidate(_evidenced_candidate())
    first = registry.select_auditor("worker", (MODEL,), "L2")
    assert first.auditor.model not in (MODEL,)
    assert first.independence_level
    assert first.auditor.session_ref
    second = registry.select_auditor("worker", ("other/model-x",), "L2")
    assert (second.auditor.provider_id, second.auditor.model) == (
        first.auditor.provider_id, first.auditor.model)
    assert second.auditor.session_ref != first.auditor.session_ref


def test_auditor_task_class_sourcing_fail_closed():  # ARCH-741
    # The candidate registered earlier in this file carries AUDITOR_MODEL;
    # naming it in the implementer set leaves no eligible auditor for the
    # auditor task class, whatever else was registered before.
    registry, _ = _registry()
    with pytest.raises(Exception) as exc_info:
        registry.select_auditor("auditor", (MODEL, AUDITOR_MODEL), "L2")
    assert exc_info.value.code == "NO_ELIGIBLE_AUDITOR"
    assert registry.sourcing_state("scope-fresh-741") == "BLOCKED"


def test_unresolved_sourcing_stays_blocked():  # ARCH-745 + BP07-54
    registry, _ = _registry()
    assert registry.sourcing_state("scope-park-1") == "BLOCKED"


def test_user_resolution_unparks_sourcing():  # ARCH-745 + BP07-53
    registry, _ = _registry()
    resolved = registry.resolve_sourcing(_decision(
        decision_id="dec-park-1",
        scope="scope-park-1",
        user_resolution_ref="user-dec-1",
    ))
    assert resolved.user_resolution_ref == "user-dec-1"
    assert registry.sourcing_state("scope-park-1") != "BLOCKED"


def test_non_user_resolution_keeps_blocked():  # BP07-53
    registry, _ = _registry()
    registry.resolve_sourcing(_decision(
        decision_id="dec-mgr-1",
        scope="scope-mgr-1",
        authority="MANAGER",
        decided_by="manager-1",
        visible_to_user=False,
        user_resolution_ref=None,
    ))
    assert registry.sourcing_state("scope-mgr-1") == "BLOCKED"


def test_unresolved_provider_dependency_fails_closed_with_documented_options():  # MVP_ACCEPT-224
    # Unresolved auditor-provider dependency fails closed to BLOCKED with
    # documented options: select raises NO_ELIGIBLE_AUDITOR, the scope
    # reads BLOCKED, and only a USER resolution documenting
    # statement+reason unparks it.
    registry, _ = _registry()
    with pytest.raises(Exception) as exc_info:
        registry.select_auditor("worker", (MODEL,), "L2")
    assert exc_info.value.code == "NO_ELIGIBLE_AUDITOR"
    assert registry.sourcing_state("scope-dep-224") == "BLOCKED"
    resolved = registry.resolve_sourcing(_decision(
        decision_id="dec-dep-224",
        scope="scope-dep-224",
        user_resolution_ref="user-dec-224",
    ))
    assert resolved.statement
    assert resolved.reason
    assert resolved.authority == "USER"
    assert registry.sourcing_state("scope-dep-224") != "BLOCKED"


def test_single_provider_acceptance_records_level_and_acceptance():  # E2
    # The recorded level and the user's acceptance are pinned here via the
    # SingleProviderAcceptance record. That a single-provider run is not
    # provider-blocked has no verdict-producing stub symbol; see NOT-DONE
    # in the return.
    registry, module = _registry()
    recorded = registry.record_single_provider_acceptance(
        "scope-solo-1", "L1", "user-accept-solo-1")
    assert isinstance(recorded, module.SingleProviderAcceptance)
    assert recorded.scope == "scope-solo-1"
    assert recorded.achieved_level == "L1"
    assert recorded.user_acceptance_ref == "user-accept-solo-1"


def test_missing_requirement_blocks_pass():  # SPEC 0A
    coordinator, _ = _coordinator()
    outcome = coordinator.block_on_missing_requirement(
        "audit-1", "req-missing-1")
    assert outcome == "BLOCKED"


def test_pass_forbidden_unless_context_integrity_pass():  # SPEC 45A
    # Fail-closed direction only: an unknown audit reads as not-PASS.
    # The PASS-allowed path needs register state no stub writer provides.
    coordinator, _ = _coordinator()
    assert coordinator.require_context_integrity_pass("audit-unknown-1") is False


def test_every_entry_point_reaches_real_symbol():
    coordinator, cmod = _coordinator()
    registry, rmod = _registry()
    log, lmod = _log()
    grounding, gmod = _grounding()
    instances = {
        "AuditCoordinator": coordinator,
        "AuditorRegistry": registry,
        "AuditLog": log,
        "GroundingPort": grounding,
    }
    modules = {
        "agent_si.assurance.audit_coordinator": cmod,
        "agent_si.assurance.audit_registry": rmod,
        "agent_si.assurance.audit_records": lmod,
        "agent_si.assurance.grounding": gmod,
    }
    turn = _turn(run_id="run-rt-1")
    audit_id = coordinator.audit_served_turn(turn)
    registry.register_candidate(_evidenced_candidate(
        provider_id="prov-rt", instance="i-rt"))
    registry.note_capability_evidence("prov-rt", AUDITOR_MODEL, "ev-rt-1")
    record = lmod.AuditRecord(
        audit_id=audit_id,
        project_id=PROJECT,
        task_id=TASK,
        run_id="run-rt-1",
        audit_scope_id="scope-rt-1",
        audit_sequence=1,
        supersedes_audit_id=None,
        context_session_ref="sess-audit-rt",
        producer_session_refs=("sess-producer-1", "sess-producer-2"),
        implementer_model_ids=(MODEL,),
        contract_hash=CONTRACT_HASH,
        audit_policy_ref="audit-policy-rt",
        artifact_refs=("art-read-1",),
        evidence_refs=("ev-rt-1",),
        requirement_verdicts=(),
        context_integrity="PASS",
        result=lmod.AuditResult.PASS,
        handling_disposition=lmod.AuditHandlingDisposition.COMPLETE,
        failure_class=None,
        created_at="2026-10-26T00:00:00Z",
    )
    log.append(record)
    decision = _decision(decision_id="dec-rt-1", scope="scope-rt-resolve",
                         user_resolution_ref="user-dec-rt")
    # FAKE-OF: per-entry probe payloads (test-only values).
    probes = {
        "audit_served_turn": ({"turn": _turn(run_id="run-rt-2")}, "id"),
        "audit_with_fresh_auditor": ({"turn": _turn(run_id="run-rt-3")}, "id"),
        "reaudit": ({"audit_id": audit_id, "pair_reuse_ref": None}, "id"),
        "refuse_contributor": None,
        "remaining_correction_budget": ({"scope_id": "scope-rt-1"}, "limit"),
        "block_on_missing_requirement": (
            {"audit_id": audit_id, "requirement_id": "req-m-rt"}, "status"),
        "require_context_integrity_pass": (
            {"audit_id": "audit-unknown-rt"}, "flag"),
        "check_context_recovery": (
            {"run_ref": "run-rt-1",
             "expected_contract_hash": "hash-other"}, "confirmed"),
        "confirm_recovery_leg": (
            {"run_ref": "run-rt-1", "verification_ref": "ver-rt-1",
             "audit_ref": audit_id}, "confirmed"),
        "classify_failure": (
            {"signal": "verifier_timeout", "severity": "HIGH"}, "class"),
        "handle_turn_cap": (
            {"turn_ref": "turn-rt", "budget_state_ref": "budget-rt"}, "ref"),
        "handle_invalid_output": (
            {"output_ref": "out-rt", "reason": "reason-rt"}, "ref"),
        "check_semantic_and_security": (
            {"criterion_refs": ("crit-rt",),
             "evidence_refs": ("ev-rt-1",)}, "verdict"),
        "build_deliverable_schema": (
            {"schema_id": "schema-rt", "expected_outputs": ("out-1",),
             "evidence_required": True}, "schema"),
        "fail_criterion_on_missing_evidence": (
            {"criterion_id": "crit-rt", "evidence_refs": ()}, "verdict"),
        "close_stage": (
            {"task_id": TASK, "scope_id": "scope-rt-1",
             "audit_id": audit_id}, "row"),
        "accepted_risk_allowed": ({"policy_ref": None}, "gate"),
        "register_candidate": (
            {"candidate": _evidenced_candidate(
                provider_id="prov-rt-2", instance="i-rt-2")}, "candidate"),
        "note_capability_evidence": (
            {"provider_id": "prov-rt", "model": AUDITOR_MODEL,
             "evidence_ref": "ev-rt-2"}, "candidate"),
        "is_eligible": (
            {"provider_id": "prov-ghost-rt", "model": "model-ghost"},
            "eligible"),
        "check_separate_model": (
            {"auditor_model": AUDITOR_MODEL,
             "implementer_model_ids": (MODEL,)}, "separate"),
        "select_auditor": (
            {"task_class": "worker", "implementer_model_ids": (MODEL,),
             "minimum_level": "L2"}, "selection"),
        "record_pair_reuse": ({"decision": decision}, "recorded"),
        "resolve_sourcing": ({"decision": decision}, "resolved"),
        "sourcing_state": ({"scope": "scope-never-rt"}, "state"),
        "record_single_provider_acceptance": (
            {"scope": "scope-solo-rt", "achieved_level": "L1",
             "user_acceptance_ref": "user-accept-rt"}, "recorded"),
        "ground_artifact": (
            {"request": gmod.GroundingRequest(
                artifact_id="art-rt-1", contract_hash=CONTRACT_HASH,
                evidence_refs=("ev-rt-1",))}, "grounded"),
        "load_grounded": ({"artifact_id": "art-rt-1"}, "grounded"),
        "append": ({"record": record}, "stored"),
        "load": ({"audit_id": audit_id}, "stored"),
        "latest_for_scope": ({"audit_scope_id": "scope-rt-1"}, "stored"),
        "list_by_task": ({"task_id": TASK}, "stored"),
    }
    entries = {}
    for module in modules.values():
        entries.update(getattr(module, "ENTRY_POINTS", {}))
    entries.update({
        "append": "agent_si.assurance.audit_records.AuditLog.append",
        "load": "agent_si.assurance.audit_records.AuditLog.load",
        "latest_for_scope": (
            "agent_si.assurance.audit_records.AuditLog.latest_for_scope"),
        "list_by_task": (
            "agent_si.assurance.audit_records.AuditLog.list_by_task"),
    })
    for logical, dotted in entries.items():
        owner_dotted, symbol = dotted.rsplit(".", 1)
        classname = owner_dotted.rsplit(".", 1)[1]
        target = getattr(instances[classname], symbol)
        assert callable(target), logical
        probe = probes[logical]
        if probe is None:
            continue
        kwargs, _ = probe
        assert target(**kwargs) is not None, logical
