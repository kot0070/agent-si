"""ExecutionAttempt state machine (Manifest sections 14A, 14B; spec sec 14B).

ExecutionAttempt is the immutable subordinate of one ExecutionRun: a committed
instance is never rewritten. Retry is a NEW attempt on the same run; a
finished attempt never reopens; verification/audit correction is a NEW run.
Fallback keeps the same run (new attempt carrying fallback_reason) only while
the logical route/strategy is unchanged -- a material route/strategy change
is a NEW run, decided deterministically from the FallbackPolicy.

Client rule (spec sec 14B, manifest section 14B): provider clients use
max_retries=0 (no hidden recovery inside the client); the runner retries only
from the RoutingDecision-bound RunConfig, and each result is posted as an
SdkRunResult carrying output_ref. CLIENT_MAX_RETRIES pins that client-side
budget at 0: any retry you see here is an explicit new attempt record, never
a silent client re-call.

Shared names (ExecutionAttemptStatus, ATTEMPT_ALLOWED, ATTEMPT_TERMINAL,
is_attempt_transition_allowed, MANIFEST_SHA256, verify_manifest) are imported
from iface.frozen_manifest.manifest, which is M1a-owned and read-only here.
AttemptType is module-local: the manifest defines no shared AttemptType, so
these values are transcribed verbatim from spec sec 14B / manifest section
14B and owned by this module, not the frozen interface.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Dict, List, Optional, Tuple

try:
    from iface.frozen_manifest import manifest
except ImportError:  # alternate layout: the iface/ directory itself on sys.path
    from frozen_manifest import manifest

CLIENT_MAX_RETRIES = 0
"""Client-side retry budget (spec sec 14B): provider clients use max_retries=0.

No hidden recovery: runner retries come only from the RoutingDecision-bound
RunConfig as new ExecutionAttempt records; each result posts as an
SdkRunResult carrying output_ref.
"""

SAME_RUN_NEW_ATTEMPT = "SAME_RUN_NEW_ATTEMPT"
NEW_RUN_REQUIRED = "NEW_RUN_REQUIRED"


class AttemptType(str, Enum):
    """Manifest section 14B attempt kinds (module-local transcription)."""

    INITIAL = "INITIAL"
    RETRY = "RETRY"
    FORMAT_RETRY = "FORMAT_RETRY"
    PROVIDER_RETRY = "PROVIDER_RETRY"
    VERIFICATION_RETRY = "VERIFICATION_RETRY"
    TOOL_RETRY = "TOOL_RETRY"


class AttemptConflictError(Exception):
    """UNIQUE violation: duplicate attempt_id, (run_id, run_attempt_sequence),
    or (routing_assignment_id, attempt_no) (Manifest section 14B)."""


class IllegalAttemptTransitionError(Exception):
    """Edge outside the linear lifecycle (Manifest sections 14A, 14B)."""


class StaleAttemptCommitError(Exception):
    """CAS loser: expected version or from-state missed (conventions section)."""


class AttemptCompatibilityError(Exception):
    """Record fields incompatible with section 14B (assignment/sequence scope
    or attempt_type/reason pairing)."""


@dataclass(frozen=True)
class ExecutionAttempt:
    """Manifest section 14B ExecutionAttempt. Immutable subordinate of one run.

    version is CAS bookkeeping per the conventions section (0 at creation,
    +1 per committed transition); it is derived commit state, never part of
    the record identity. Timestamps are caller-supplied and never arbitrate.
    """

    attempt_id: str = ""
    project_id: str = ""
    task_id: str = ""
    run_id: str = ""
    routing_assignment_id: Optional[str] = None
    attempt_no: Optional[int] = None
    run_attempt_sequence: int = 0
    attempt_type: AttemptType = AttemptType.INITIAL
    provider: str = ""
    provider_instance: Optional[str] = None
    model: str = ""
    canonical_provider_id: str = ""
    canonical_model_id: str = ""
    output_artifact_refs: Tuple[str, ...] = ()
    material_contribution: bool = False
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    status: manifest.ExecutionAttemptStatus = (
        manifest.ExecutionAttemptStatus.CREATED
    )
    version: int = 0
    error_ref: Optional[str] = None
    usage_ref: Optional[str] = None
    input_ref: Optional[str] = None
    output_ref: Optional[str] = None
    retry_reason: Optional[str] = None
    fallback_reason: Optional[str] = None

    def __post_init__(self) -> None:
        if isinstance(self.attempt_type, str) and not isinstance(
            self.attempt_type, AttemptType
        ):
            object.__setattr__(
                self, "attempt_type", AttemptType(self.attempt_type)
            )
        if isinstance(self.status, str) and not isinstance(
            self.status, manifest.ExecutionAttemptStatus
        ):
            object.__setattr__(
                self,
                "status",
                manifest.ExecutionAttemptStatus(self.status),
            )
        if self.output_artifact_refs is None:
            object.__setattr__(self, "output_artifact_refs", ())
        elif not isinstance(self.output_artifact_refs, tuple):
            object.__setattr__(
                self, "output_artifact_refs", tuple(self.output_artifact_refs)
            )
        check_compatible(self)


def check_compatible(attempt: ExecutionAttempt) -> None:
    """Enforce section 14B field compatibility; raise AttemptCompatibilityError.

    Assignment/sequence scope: attempt_no is scoped to routing_assignment_id,
    so one is present iff the other is (UNIQUE(routing_assignment_id,
    attempt_no) applies when non-null); run_attempt_sequence is always a
    positive per-run ordinal. Type/reason pairing: INITIAL carries neither
    reason; any later attempt records why it exists (retry_reason, with
    fallback_reason allowed in place for same-run fallback attempts, which
    carry fallback_reason per section 14B).
    """
    aid = attempt.routing_assignment_id
    ano = attempt.attempt_no
    if (aid is None) != (ano is None):
        raise AttemptCompatibilityError(
            "routing_assignment_id and attempt_no agree: both set or both "
            "null (UNIQUE(routing_assignment_id, attempt_no) applies when "
            "non-null, Manifest section 14B); got %r and %r" % (aid, ano)
        )
    if ano is not None and (isinstance(ano, bool) or not isinstance(ano, int) or ano < 1):
        raise AttemptCompatibilityError(
            "attempt_no is monotonic per routing_assignment_id, got %r" % (ano,)
        )
    seq = attempt.run_attempt_sequence
    if isinstance(seq, bool) or not isinstance(seq, int) or seq < 1:
        raise AttemptCompatibilityError(
            "run_attempt_sequence is monotonic per run "
            "(UNIQUE(run_id, run_attempt_sequence)), got %r" % (seq,)
        )
    if attempt.attempt_type == AttemptType.INITIAL:
        if attempt.retry_reason is not None or attempt.fallback_reason is not None:
            raise AttemptCompatibilityError(
                "INITIAL attempt carries no retry_reason/fallback_reason "
                "(Manifest section 14B)"
            )
    elif attempt.retry_reason is None and attempt.fallback_reason is None:
        raise AttemptCompatibilityError(
            "non-INITIAL attempt %r records retry_reason (fallback attempts "
            "may carry fallback_reason instead) (sections 14B, 16)" % attempt.attempt_type.value
        )


def is_transition_allowed(fr: object, to: object) -> bool:
    """Delegate to the frozen table (Manifest section 14B linear lifecycle)."""
    return manifest.is_attempt_transition_allowed(fr, to)


def transition(
    attempt: ExecutionAttempt,
    to_status: manifest.ExecutionAttemptStatus,
    *,
    expected_from: manifest.ExecutionAttemptStatus,
    expected_version: int,
    started_at: Optional[str] = None,
    ended_at: Optional[str] = None,
) -> ExecutionAttempt:
    """Commit one edge; return the NEW instance, leaving *attempt* untouched.

    Enforces, in order: the frozen transition table (a finished attempt never
    reopens: terminal states have no outgoing edges), then CAS (current status
    == expected_from and current version == expected_version; losers raise
    StaleAttemptCommitError and must re-read), then field compatibility of the
    result. Timestamps supplied by the caller are recorded, never arbitrated.
    """
    if isinstance(to_status, str):
        to_status = manifest.ExecutionAttemptStatus(to_status)
    if isinstance(expected_from, str):
        expected_from = manifest.ExecutionAttemptStatus(expected_from)
    if not manifest.is_attempt_transition_allowed(attempt.status, to_status):
        raise IllegalAttemptTransitionError(
            "illegal attempt edge %s -> %s (linear lifecycle CREATED -> "
            "RUNNING -> SUCCEEDED|FAILED|CANCELLED, Manifest section 14B)"
            % (attempt.status.value, to_status.value)
        )
    if attempt.status != expected_from or attempt.version != expected_version:
        raise StaleAttemptCommitError(
            "CAS failed for %s: current (%s, v%s) != expected (%s, v%s); "
            "re-read and retry" % (
                attempt.attempt_id,
                attempt.status.value,
                attempt.version,
                expected_from.value,
                expected_version,
            )
        )
    return replace(
        attempt,
        status=to_status,
        version=attempt.version + 1,
        started_at=started_at if started_at is not None else attempt.started_at,
        ended_at=ended_at if ended_at is not None else attempt.ended_at,
    )


@dataclass(frozen=True)
class FollowupDecision:
    """Where the next attempt after a terminal attempt belongs (section 14B).

    SAME_RUN_NEW_ATTEMPT: same run, new attempt carrying retry_reason (plain
    retry) or fallback_reason (same logical route/strategy fallback).
    NEW_RUN_REQUIRED: verification/audit correction, or a material
    route/strategy change (deterministic from the FallbackPolicy); the caller
    allocates the new run, this module creates no runs.
    """

    action: str
    reason: str
    detail: str = ""


def plan_followup(
    attempt: ExecutionAttempt,
    *,
    correction: bool,
    material_route_change: bool,
) -> FollowupDecision:
    """Decide retry-in-run vs new-run after a terminal attempt (section 14B).

    correction (verification/audit loop) always needs a new run; so does a
    material route/strategy change. Anything else is a new attempt on the
    same run, with history immutable. Pure function: mutates nothing.
    """
    if correction:
        return FollowupDecision(
            action=NEW_RUN_REQUIRED,
            reason="CORRECTION_NEW_RUN",
            detail=(
                "verification/audit correction = new run (attempt %s stays "
                "immutable, Manifest section 14B)" % attempt.attempt_id
            ),
        )
    if material_route_change:
        return FollowupDecision(
            action=NEW_RUN_REQUIRED,
            reason="MATERIAL_FALLBACK_NEW_RUN",
            detail=(
                "material route/strategy change = new run (same logical "
                "route/strategy would stay in-run, Manifest section 14B)"
            ),
        )
    return FollowupDecision(
        action=SAME_RUN_NEW_ATTEMPT,
        reason="RETRY_SAME_RUN",
        detail=(
            "retry = new attempt on run %s; prior attempts immutable "
            "(Manifest section 14B)" % attempt.run_id
        ),
    )


class AttemptLog:
    """In-memory attempt store enforcing UNIQUEs + CAS (sections 14B, 42).

    append() records a CREATED attempt, rejecting duplicate attempt_id,
    duplicate (run_id, run_attempt_sequence), and duplicate
    (routing_assignment_id, attempt_no) when the assignment is non-null.
    commit() applies one transition to the CURRENT instance only (CAS on
    (status, version)); history is kept append-only for replay/audit order.
    """

    def __init__(self) -> None:
        self._current: Dict[str, ExecutionAttempt] = {}
        self._history: Dict[str, List[ExecutionAttempt]] = {}
        self._by_run_sequence: Dict[Tuple[str, int], str] = {}
        self._by_assignment_no: Dict[Tuple[str, int], str] = {}

    def append(self, attempt: ExecutionAttempt) -> ExecutionAttempt:
        check_compatible(attempt)
        if attempt.attempt_id in self._current:
            raise AttemptConflictError(
                "duplicate attempt_id %r" % (attempt.attempt_id,)
            )
        run_key = (attempt.run_id, attempt.run_attempt_sequence)
        if run_key in self._by_run_sequence:
            raise AttemptConflictError(
                "duplicate UNIQUE(run_id, run_attempt_sequence) %r "
                "(held by %r)" % (run_key, self._by_run_sequence[run_key])
            )
        if attempt.routing_assignment_id is not None:
            assign_key = (attempt.routing_assignment_id, attempt.attempt_no)
            if assign_key in self._by_assignment_no:
                raise AttemptConflictError(
                    "duplicate UNIQUE(routing_assignment_id, attempt_no) %r "
                    "(held by %r)"
                    % (assign_key, self._by_assignment_no[assign_key])
                )
            self._by_assignment_no[assign_key] = attempt.attempt_id
        self._by_run_sequence[run_key] = attempt.attempt_id
        self._current[attempt.attempt_id] = attempt
        self._history.setdefault(attempt.attempt_id, []).append(attempt)
        return attempt

    def current(self, attempt_id: str) -> ExecutionAttempt:
        return self._current[attempt_id]

    def history(self, attempt_id: str) -> Tuple[ExecutionAttempt, ...]:
        return tuple(self._history.get(attempt_id, ()))

    def commit(
        self,
        attempt_id: str,
        to_status: manifest.ExecutionAttemptStatus,
        *,
        expected_from: manifest.ExecutionAttemptStatus,
        expected_version: int,
        started_at: Optional[str] = None,
        ended_at: Optional[str] = None,
    ) -> ExecutionAttempt:
        current = self._current[attempt_id]
        moved = transition(
            current,
            to_status,
            expected_from=expected_from,
            expected_version=expected_version,
            started_at=started_at,
            ended_at=ended_at,
        )
        self._current[attempt_id] = moved
        self._history[attempt_id].append(moved)
        return moved


__all__ = [
    "CLIENT_MAX_RETRIES",
    "SAME_RUN_NEW_ATTEMPT",
    "NEW_RUN_REQUIRED",
    "AttemptType",
    "AttemptConflictError",
    "IllegalAttemptTransitionError",
    "StaleAttemptCommitError",
    "AttemptCompatibilityError",
    "ExecutionAttempt",
    "FollowupDecision",
    "check_compatible",
    "is_transition_allowed",
    "transition",
    "plan_followup",
    "AttemptLog",
]
