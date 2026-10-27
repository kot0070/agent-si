"""K13 ExecutionAttempt state machine tests (Manifest sections 14A, 14B, 16, 17A).

RED -> GREEN: this module imports src/agent_si/state_machines/attempt_machine,
which does not exist until the M1C implementation lands, so the suite FAILS
at collection before the fix and PASSES after it. Tests are frozen as-is:
the implementation must satisfy them, never the reverse.

Covers: immutability, UNIQUEs, linear transitions, retry vs new-run,
client max_retries=0. Full-tree suite still FAILs after (other lanes pending).
"""

from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest

from agent_si.state_machines import attempt_machine
from iface.frozen_manifest import manifest


def _make_attempt(**overrides):
    base = dict(
        attempt_id="att-1",
        project_id="P1",
        task_id="T1",
        run_id="run-1",
        routing_assignment_id="assign-1",
        attempt_no=1,
        run_attempt_sequence=1,
        attempt_type=attempt_machine.AttemptType.INITIAL,
        provider="prov-a",
        provider_instance="inst-1",
        model="model-a",
        canonical_provider_id="prov-a",
        canonical_model_id="model-a",
        status=manifest.ExecutionAttemptStatus.CREATED,
    )
    base.update(overrides)
    return attempt_machine.ExecutionAttempt(**base)


def test_manifest_sha_pins_file():
    assert (
        manifest.MANIFEST_SHA256
        == "f256bab4d31be3cd9e86c22a1bdcef90b08ad62500a8eca2051705cc0a9b0690"
    )
    assert (
        manifest.verify_manifest(ROOT / "RECORDS" / "day0" / "K13_MANIFEST.md")
        is True
    )
    assert manifest.is_attempt_transition_allowed("CREATED", "RUNNING") is True
    assert manifest.is_attempt_transition_allowed("RUNNING", "CREATED") is False


def test_attempt_immutable():
    attempt = _make_attempt()
    with pytest.raises(FrozenInstanceError):
        attempt.status = manifest.ExecutionAttemptStatus.RUNNING
    with pytest.raises(FrozenInstanceError):
        attempt.run_id = "run-2"
    with pytest.raises(FrozenInstanceError):
        attempt.output_artifact_refs = ("art-9",)
    moved = replace(
        attempt, status=manifest.ExecutionAttemptStatus.RUNNING, version=1
    )
    assert moved.status == manifest.ExecutionAttemptStatus.RUNNING
    assert attempt.status == manifest.ExecutionAttemptStatus.CREATED
    assert attempt.version == 0


def test_unique_attempt_no_per_routing_assignment():
    log = attempt_machine.AttemptLog()
    log.append(_make_attempt(attempt_id="att-1"))
    with pytest.raises(attempt_machine.AttemptConflictError):
        log.append(
            _make_attempt(
                attempt_id="att-2",
                run_attempt_sequence=2,
            )
        )
    # Same attempt_no under a different assignment does not collide.
    log.append(
        _make_attempt(
            attempt_id="att-3",
            routing_assignment_id="assign-2",
            run_attempt_sequence=3,
        )
    )
    assert log.current("att-3").routing_assignment_id == "assign-2"


def test_unique_run_attempt_sequence_per_run():
    log = attempt_machine.AttemptLog()
    log.append(_make_attempt(attempt_id="att-1"))
    with pytest.raises(attempt_machine.AttemptConflictError):
        log.append(
            _make_attempt(
                attempt_id="att-2",
                attempt_no=2,
            )
        )
    # Same sequence under a different run does not collide.
    log.append(
        _make_attempt(
            attempt_id="att-4",
            run_id="run-2",
            routing_assignment_id="assign-9",
            attempt_no=1,
        )
    )
    assert log.current("att-4").run_id == "run-2"


def test_unassigned_attempts_skip_assignment_unique():
    log = attempt_machine.AttemptLog()
    log.append(
        _make_attempt(
            attempt_id="att-1",
            routing_assignment_id=None,
            attempt_no=None,
            run_attempt_sequence=1,
        )
    )
    log.append(
        _make_attempt(
            attempt_id="att-2",
            routing_assignment_id=None,
            attempt_no=None,
            run_attempt_sequence=2,
        )
    )
    assert log.current("att-2").attempt_no is None


def test_linear_lifecycle_allowed():
    attempt = _make_attempt()
    running = attempt_machine.transition(
        attempt,
        manifest.ExecutionAttemptStatus.RUNNING,
        expected_from=manifest.ExecutionAttemptStatus.CREATED,
        expected_version=0,
        started_at="t0",
    )
    assert running.status == manifest.ExecutionAttemptStatus.RUNNING
    assert running.version == 1
    assert running.started_at == "t0"
    assert attempt.status == manifest.ExecutionAttemptStatus.CREATED
    done = attempt_machine.transition(
        running,
        manifest.ExecutionAttemptStatus.SUCCEEDED,
        expected_from=manifest.ExecutionAttemptStatus.RUNNING,
        expected_version=1,
        ended_at="t1",
    )
    assert done.status == manifest.ExecutionAttemptStatus.SUCCEEDED
    assert done.version == 2
    assert done.ended_at == "t1"


@pytest.mark.parametrize(
    "from_status,to_status",
    [
        ("CREATED", "SUCCEEDED"),
        ("CREATED", "FAILED"),
        ("CREATED", "CANCELLED"),
        ("RUNNING", "CREATED"),
        ("SUCCEEDED", "RUNNING"),
        ("SUCCEEDED", "FAILED"),
        ("FAILED", "RUNNING"),
        ("FAILED", "CANCELLED"),
        ("CANCELLED", "RUNNING"),
        ("CANCELLED", "CREATED"),
    ],
)
def test_linear_lifecycle_forbidden_edges(from_status, to_status):
    attempt = _make_attempt(
        status=manifest.ExecutionAttemptStatus(from_status)
    )
    with pytest.raises(attempt_machine.IllegalAttemptTransitionError):
        attempt_machine.transition(
            attempt,
            manifest.ExecutionAttemptStatus(to_status),
            expected_from=manifest.ExecutionAttemptStatus(from_status),
            expected_version=attempt.version,
        )


def test_finished_attempt_never_reopens_via_log():
    log = attempt_machine.AttemptLog()
    log.append(_make_attempt(attempt_id="att-1"))
    log.commit(
        "att-1",
        manifest.ExecutionAttemptStatus.RUNNING,
        expected_from=manifest.ExecutionAttemptStatus.CREATED,
        expected_version=0,
    )
    log.commit(
        "att-1",
        manifest.ExecutionAttemptStatus.FAILED,
        expected_from=manifest.ExecutionAttemptStatus.RUNNING,
        expected_version=1,
    )
    with pytest.raises(attempt_machine.IllegalAttemptTransitionError):
        log.commit(
            "att-1",
            manifest.ExecutionAttemptStatus.RUNNING,
            expected_from=manifest.ExecutionAttemptStatus.FAILED,
            expected_version=2,
        )
    assert (
        log.current("att-1").status == manifest.ExecutionAttemptStatus.FAILED
    )


def test_cas_stale_commit_fails_loser_rereads():
    log = attempt_machine.AttemptLog()
    log.append(_make_attempt(attempt_id="att-1"))
    with pytest.raises(attempt_machine.StaleAttemptCommitError):
        log.commit(
            "att-1",
            manifest.ExecutionAttemptStatus.RUNNING,
            expected_from=manifest.ExecutionAttemptStatus.CREATED,
            expected_version=99,
        )
    with pytest.raises(attempt_machine.StaleAttemptCommitError):
        log.commit(
            "att-1",
            manifest.ExecutionAttemptStatus.RUNNING,
            expected_from=manifest.ExecutionAttemptStatus.RUNNING,
            expected_version=0,
        )
    committed = log.commit(
        "att-1",
        manifest.ExecutionAttemptStatus.RUNNING,
        expected_from=manifest.ExecutionAttemptStatus.CREATED,
        expected_version=0,
    )
    assert committed.version == 1
    assert (
        log.current("att-1").status == manifest.ExecutionAttemptStatus.RUNNING
    )


def test_retry_is_same_run_new_attempt():
    decision = attempt_machine.plan_followup(
        _make_attempt(), correction=False, material_route_change=False
    )
    assert decision.action == attempt_machine.SAME_RUN_NEW_ATTEMPT
    followup = _make_attempt(
        attempt_id="att-2",
        attempt_no=2,
        run_attempt_sequence=2,
        attempt_type=attempt_machine.AttemptType.RETRY,
        retry_reason="provider_fail",
    )
    assert followup.run_id == "run-1"
    assert followup.attempt_type == attempt_machine.AttemptType.RETRY
    assert followup.retry_reason == "provider_fail"


def test_material_fallback_requires_new_run():
    decision = attempt_machine.plan_followup(
        _make_attempt(), correction=False, material_route_change=True
    )
    assert decision.action == attempt_machine.NEW_RUN_REQUIRED


def test_correction_requires_new_run():
    decision = attempt_machine.plan_followup(
        _make_attempt(), correction=True, material_route_change=False
    )
    assert decision.action == attempt_machine.NEW_RUN_REQUIRED


def test_client_max_retries_is_zero_no_hidden_recovery():
    assert attempt_machine.CLIENT_MAX_RETRIES == 0
    doc = attempt_machine.__doc__ or ""
    assert "max_retries" in doc
    assert "0" in doc


def test_compatibility_initial_carries_no_reasons():
    with pytest.raises(attempt_machine.AttemptCompatibilityError):
        _make_attempt(retry_reason="provider_fail")
    with pytest.raises(attempt_machine.AttemptCompatibilityError):
        _make_attempt(fallback_reason="model_fail")


def test_compatibility_non_initial_needs_a_reason():
    with pytest.raises(attempt_machine.AttemptCompatibilityError):
        _make_attempt(attempt_type=attempt_machine.AttemptType.RETRY)
    ok = _make_attempt(
        attempt_id="att-2",
        attempt_no=2,
        run_attempt_sequence=2,
        attempt_type=attempt_machine.AttemptType.PROVIDER_RETRY,
        retry_reason="model_fail",
        fallback_reason="model_fail",
    )
    assert ok.fallback_reason == "model_fail"


def test_compatibility_assignment_and_attempt_no_agree():
    with pytest.raises(attempt_machine.AttemptCompatibilityError):
        _make_attempt(routing_assignment_id=None, attempt_no=1)
    with pytest.raises(attempt_machine.AttemptCompatibilityError):
        _make_attempt(routing_assignment_id="assign-1", attempt_no=None)
    with pytest.raises(attempt_machine.AttemptCompatibilityError):
        _make_attempt(attempt_no=0)
    with pytest.raises(attempt_machine.AttemptCompatibilityError):
        _make_attempt(run_attempt_sequence=0)


RUN_SELECTION_FIELDS = (
    "routing_decision_refs",
    "split_strategy",
    "primary_provider",
    "primary_provider_instance",
    "primary_model",
    "implementer_provider_ids",
    "implementer_model_ids",
)
"""Manifest section 14 ExecutionRun selection-field set (FULL).

Run-level routing/selection state lives on the run, never on the attempt:
the attempt carries only its own section 14B provider/model binding
(provider, provider_instance, model, canonical_provider_id,
canonical_model_id). Drift-4 guard: these run-level names must never
become ExecutionAttempt fields (strict: GREEN by implementation only,
never by weakening these asserts).
"""


def test_drift4_attempt_carries_no_run_selection_fields():
    fields = attempt_machine.ExecutionAttempt.__dataclass_fields__
    probe = _make_attempt()
    for name in RUN_SELECTION_FIELDS:
        assert name not in fields
        assert not hasattr(probe, name)


def test_drift4_attempt_keeps_own_provider_model_binding():
    fields = attempt_machine.ExecutionAttempt.__dataclass_fields__
    for name in (
        "provider",
        "provider_instance",
        "model",
        "canonical_provider_id",
        "canonical_model_id",
    ):
        assert name in fields


def test_drift4_no_state_version_on_attempt():
    assert (
        "state_version"
        not in attempt_machine.ExecutionAttempt.__dataclass_fields__
    )
    assert not hasattr(_make_attempt(), "state_version")
    source = Path(attempt_machine.__file__).read_text(encoding="utf-8")
    assert "state_version" not in source
