"""K03 STEP1 behaviour contract: audit records, grounding, sourcing.

Rows BP07-14, BP07-17, BP07-18, BP07-20, ARCH-652, ARCH-654, ARCH-746,
SDK-104, SDK-107, SDK-109, ARCH-622, MVP_ACCEPT-33, MVP_ACCEPT-111.
MUST FAIL now (RED).

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
defect + NOT-DONE in the return, never added here. Each error code and
each failure class is asserted in its own test.
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

PROJECT = "proj-k03-records1"
TASK = "task-k03-records1"
RUN = "run-k03-records1"
CONTRACT_HASH = "contract-hash-k03-rec1"


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


def test_fail_closed_sourcing_raises_no_eligible_auditor():  # BP07-14 + BP07-20
    # Fail-closed emission plus the frozen registry signal in its own
    # condition; the gate state reads BLOCKED. The config/options payload
    # has no stub symbol; see NOT-DONE in the return.
    registry, _ = _registry()
    with pytest.raises(Exception) as exc_info:
        registry.select_auditor("worker", (MODEL,), "L2")
    assert exc_info.value.code == "NO_ELIGIBLE_AUDITOR"
    assert registry.sourcing_state("scope-fresh-r14") == "BLOCKED"


def test_sourcing_cannot_complete_stays_blocked():  # BP07-17
    # No stub symbol reports a mid-sourcing provider failure, so the
    # fail-closed default is pinned: an unsourced scope reads BLOCKED.
    registry, _ = _registry()
    assert registry.sourcing_state("scope-nc-17") == "BLOCKED"


def test_blocked_prohibits_pass_until_sourcing_succeeds():  # BP07-18
    # The prohibition half is the raise; the success half is a sourced
    # selection outside the implementer set. A PASS verdict has no
    # verdict-producing stub symbol; see NOT-DONE in the return.
    registry, _ = _registry()
    with pytest.raises(Exception) as exc_info:
        registry.select_auditor("worker", (MODEL,), "L2")
    assert exc_info.value.code == "NO_ELIGIBLE_AUDITOR"
    registry.register_candidate(_candidate(provider_id="prov-r18"))
    registry.note_capability_evidence("prov-r18", AUDITOR_MODEL, "ev-r18")
    selection = registry.select_auditor("worker", (MODEL,), "L2")
    assert selection.auditor.model not in (MODEL,)


def _candidate(provider_id="prov-audit", instance="i-1", model=AUDITOR_MODEL,
               evidence=()):
    _, module = _registry()
    # FAKE-OF: src/agent_si/providers/registry/provider_api.py.
    return module.AuditorCandidate(
        provider_id=provider_id,
        provider_instance=instance,
        model=model,
        capability_evidence_refs=tuple(evidence),
    )


def test_missing_capability_evidence_stays_ineligible_until_evidence():  # ARCH-652
    registry, _ = _registry()
    registry.register_candidate(_candidate(provider_id="prov-r652"))
    assert registry.is_eligible("prov-r652", AUDITOR_MODEL) is False
    registry.note_capability_evidence("prov-r652", AUDITOR_MODEL, "ev-r652")
    assert registry.is_eligible("prov-r652", AUDITOR_MODEL) is True


def test_l2_holds_only_when_model_outside_implementer_set():  # ARCH-654
    registry, _ = _registry()
    assert registry.check_separate_model(
        AUDITOR_MODEL, (MODEL, AUDITOR_MODEL)) is False
    assert registry.check_separate_model(
        AUDITOR_MODEL, (MODEL,)) is True


def test_missing_evidence_marks_candidate_ineligible():  # ARCH-746
    registry, _ = _registry()
    registry.register_candidate(_candidate(
        provider_id="prov-r746", instance="i-bare",
        model="model-bare-746"))
    registry.register_candidate(_candidate(
        provider_id="prov-r746", instance="i-ready",
        model=AUDITOR_MODEL, evidence=("ev-r746",)))
    selection = registry.select_auditor("worker", (MODEL,), "L2")
    assert selection.auditor.model == AUDITOR_MODEL


def test_semantic_arch_security_criteria_beyond_schema():  # SDK-107
    # Vocabulary plus evidence-gating are pinned here. Discriminating
    # schema-valid-but-violating content needs artifact-reading inputs the
    # stub signature has no room for; see NOT-DONE in the return.
    coordinator, _ = _coordinator()
    verdict = coordinator.check_semantic_and_security(
        ("crit-sem-1", "crit-arch-1", "crit-sec-1"), ("ev-r107",))
    assert verdict in ("PASS", "FAIL", "BLOCKED")
    assert coordinator.check_semantic_and_security(("crit-sem-1",), ()) == (
        "FAIL")


def test_machine_verifiable_deliverable_schema():  # SDK-104
    # Shape and content echoes are pinned here. A schema validator has no
    # stub symbol; see NOT-DONE in the return.
    coordinator, _ = _coordinator()
    schema = coordinator.build_deliverable_schema(
        "schema-rec-1", ("out-1", "out-2"), True)
    assert schema.schema_id == "schema-rec-1"
    assert tuple(schema.expected_outputs) == ("out-1", "out-2")
    assert schema.evidence_required is True
    assert schema.hash


def test_failure_class_verification_infra():  # MVP_ACCEPT-33
    coordinator, _ = _coordinator()
    assert coordinator.classify_failure(
        "verifier_timeout", "HIGH") == (
            coordinator.VerificationFailureClass.VERIFICATION_INFRA_FAILURE)


def test_failure_class_output_format():  # MVP_ACCEPT-33
    coordinator, _ = _coordinator()
    assert coordinator.classify_failure(
        "malformed_json_output", "HIGH") == (
            coordinator.VerificationFailureClass.OUTPUT_FORMAT_FAILURE)


def test_failure_class_capability():  # MVP_ACCEPT-33
    coordinator, _ = _coordinator()
    assert coordinator.classify_failure(
        "model_lacks_capability", "HIGH") == (
            coordinator.VerificationFailureClass
            .PROVIDER_OR_MODEL_CAPABILITY_FAILURE)


def test_failure_class_implementation_defect():  # MVP_ACCEPT-33
    coordinator, _ = _coordinator()
    assert coordinator.classify_failure(
        "wrong_implementation", "HIGH") == (
            coordinator.VerificationFailureClass.IMPLEMENTATION_AC_DEFECT)


def test_failure_class_security_or_policy():  # MVP_ACCEPT-33
    coordinator, _ = _coordinator()
    assert coordinator.classify_failure(
        "policy_violation", "HIGH") == (
            coordinator.VerificationFailureClass.SECURITY_OR_POLICY_FAILURE)


def test_failure_class_unknown():  # MVP_ACCEPT-33
    coordinator, _ = _coordinator()
    assert coordinator.classify_failure(
        "unrecognized_signal_xyz", "HIGH") == (
            coordinator.VerificationFailureClass.UNKNOWN_FAILURE)


def test_turn_cap_refusal_named_handler():  # SDK-109
    # The named entry and its refusal ref are pinned here. Refusal content
    # (reason, risk, ids) has no stub symbol; see NOT-DONE in the return.
    coordinator, _ = _coordinator()
    assert callable(coordinator.handle_turn_cap)
    refusal_ref = coordinator.handle_turn_cap("turn-cap-1", "budget-1")
    assert isinstance(refusal_ref, str) and refusal_ref


def test_invalid_output_named_handler():  # SDK-109
    coordinator, _ = _coordinator()
    assert callable(coordinator.handle_invalid_output)
    outcome_ref = coordinator.handle_invalid_output("out-bad-1", "bad json")
    assert isinstance(outcome_ref, str) and outcome_ref


def test_missing_evidence_ref_fails_criterion():  # ARCH-622
    coordinator, _ = _coordinator()
    assert coordinator.fail_criterion_on_missing_evidence(
        "crit-r622", ()) == "FAIL"


def test_recovery_leg_confirmed_before_recovered():  # MVP_ACCEPT-111
    # STEP2 contract: coordinator-persisted audits are visible to the
    # recovery check (same lane store). The accepted-as-recovered path
    # beyond the confirmation flag has no stub symbol; see NOT-DONE.
    coordinator, _ = _coordinator()
    pending = coordinator.confirm_recovery_leg("run-r111", "", "")
    assert pending.confirmed is False
    audit_id = coordinator.audit_served_turn(_turn())
    done = coordinator.confirm_recovery_leg("run-r111", "ver-r111", audit_id)
    assert done.confirmed is True
    assert done.audit_ref == audit_id
    assert coordinator.check_context_recovery(
        "run-r111", "hash-other").confirmed is False


def _turn(**overrides):
    module = _mod("audit_coordinator")
    kwargs = {
        "turn_ref": "turn-r111-1",
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


def test_blocked_audit_record_round_trips():
    # A BLOCKED verdict with a MISSING requirement round-trips through the
    # log. Options/parked/resume fields for the BLOCKED shape have no stub
    # symbol; see NOT-DONE in the return.
    log, records = _log()
    record = records.AuditRecord(
        audit_id="audit-rshape-1",
        project_id=PROJECT,
        task_id=TASK,
        run_id="run-rshape-1",
        audit_scope_id="scope-rshape-1",
        audit_sequence=1,
        supersedes_audit_id=None,
        context_session_ref="sess-audit-rshape",
        producer_session_refs=("sess-producer-1", "sess-producer-2"),
        implementer_model_ids=(MODEL,),
        contract_hash=CONTRACT_HASH,
        audit_policy_ref="audit-policy-rshape",
        artifact_refs=("art-read-1",),
        evidence_refs=("ev-rshape",),
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
    stored = log.load("audit-rshape-1")
    assert stored.result == records.AuditResult.BLOCKED
    assert stored.requirement_verdicts[0].verdict == (
        records.RequirementVerdict.MISSING)
    assert log.latest_for_scope("scope-rshape-1").audit_sequence == 1
    assert "audit-rshape-1" in [
        row.audit_id for row in log.list_by_task(TASK)]
