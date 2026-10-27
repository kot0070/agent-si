"""Run cancellation finalization (Manifest section 45B).

Cancellation is not rollback: history (telemetry, completed calls,
committed side effects, partial outputs) is never deleted; partial
usage/time/cost is finalized where measurable and otherwise recorded as
unmeasurable (never invented); RUNNING attempts move to CANCELLED while
CREATED attempts have no manifest edge to CANCELLED and terminal attempts
never reopen; the run reason is a canonical RunTerminationReason member
(user -> CANCELLED_BY_USER, amendment -> CANCELLED_BY_AMENDMENT; a generic
CANCELLED is prohibited as a reason, as are failure reasons such as
POLICY_BLOCK/RESOURCE_FAILURE, which terminate as FAILED instead);
budget reservations are settled/released and leases/reservations released;
audit/verification history passes through immutable.

Pure helpers returning NEW frozen records; inputs are never mutated.
Shared names (states, statuses, reasons) come ONLY from the frozen
manifest; run/attempt edges are checked with its transition predicates.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any, FrozenSet, Iterable, Mapping, Optional, Tuple

try:
    from iface.frozen_manifest import manifest
except ImportError:  # alternate layout: the iface/ directory itself on sys.path
    from frozen_manifest import manifest

CANCELLATION_REASONS: FrozenSet[manifest.RunTerminationReason] = frozenset(
    {
        manifest.RunTerminationReason.CANCELLED_BY_USER,
        manifest.RunTerminationReason.CANCELLED_BY_AMENDMENT,
    }
)
"""Canonical cancellation reasons (Manifest section 45B).

Policy violations and resource/system failures are NOT here: they terminate
as FAILED with POLICY_BLOCK / RESOURCE_FAILURE, never as cancellations.
"""

RELEASE_RESERVATION = "reservation"
RELEASE_LEASE = "lease"


class NonCanonicalCancellationReasonError(ValueError):
    """Cancellation reason is not a canonical section 45B reason."""


class IllegalCancellationTransitionError(ValueError):
    """Run status has no manifest edge to CANCELLED (terminal runs stay)."""


class AttemptRunMismatchError(ValueError):
    """Attempt does not belong to the run being cancelled."""


class InvalidPartialUsageError(ValueError):
    """Partial usage invents numbers or double-counts measurable metrics."""


class InvalidReleaseError(ValueError):
    """Release directive has an unknown kind or an empty ref."""


def is_cancellation_reason(reason: Any) -> bool:
    """Return True iff *reason* is a canonical section 45B reason."""
    try:
        return _coerce_reason(reason) in CANCELLATION_REASONS
    except NonCanonicalCancellationReasonError:
        return False


def _coerce_reason(reason: Any) -> manifest.RunTerminationReason:
    if isinstance(reason, manifest.RunTerminationReason):
        coerced = reason
    else:
        try:
            coerced = manifest.RunTerminationReason(str(reason))
        except (ValueError, TypeError, AttributeError):
            raise NonCanonicalCancellationReasonError(
                "cancellation reason must be a RunTerminationReason member, "
                "got %r; generic CANCELLED is prohibited" % (reason,)
            ) from None
    if coerced not in CANCELLATION_REASONS:
        raise NonCanonicalCancellationReasonError(
            "non-canonical cancellation reason %r; canonical reasons: %s"
            % (
                coerced.value,
                sorted(r.value for r in CANCELLATION_REASONS),
            )
        )
    return coerced


def validate_cancellation_reason(reason: Any) -> manifest.RunTerminationReason:
    """Return the canonical reason or raise NonCanonicalCancellationReasonError.

    Rejects the generic string "CANCELLED", NONE, unknown values, and
    termination reasons that belong to other dispositions (COMPLETED,
    EXECUTION_FAILED, POLICY_BLOCK, RESOURCE_FAILURE, ...).
    """
    return _coerce_reason(reason)


def _coerce_attempt_status(value: Any) -> manifest.ExecutionAttemptStatus:
    if isinstance(value, manifest.ExecutionAttemptStatus):
        return value
    try:
        return manifest.ExecutionAttemptStatus(str(value))
    except ValueError:
        raise ValueError("unknown attempt status %r" % (value,)) from None


@dataclass(frozen=True)
class CancellableAttempt:
    """Minimal attempt view for cancellation finalization."""

    attempt_id: str = ""
    run_id: str = ""
    status: manifest.ExecutionAttemptStatus = (
        manifest.ExecutionAttemptStatus.CREATED
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "status", _coerce_attempt_status(self.status)
        )


def cancel_attempt(
    attempt: CancellableAttempt, reason: Any
) -> CancellableAttempt:
    """Return the attempt after cancellation; the input is untouched.

    RUNNING attempts move to CANCELLED (the only manifest edge into
    CANCELLED). CREATED attempts have no manifest edge to CANCELLED and stay
    as-is; terminal attempts (SUCCEEDED/FAILED/CANCELLED) never reopen.
    """
    validate_cancellation_reason(reason)
    if manifest.is_attempt_transition_allowed(attempt.status, "CANCELLED"):
        return replace(
            attempt, status=manifest.ExecutionAttemptStatus.CANCELLED
        )
    return attempt


def cancel_attempts(
    attempts: Iterable[CancellableAttempt], run_id: str, reason: Any
) -> Tuple[CancellableAttempt, ...]:
    """Cancel every attempt of *run_id*; attempts of other runs raise."""
    canonical = validate_cancellation_reason(reason)
    finalised = []
    for attempt in attempts or ():
        if attempt.run_id != run_id:
            raise AttemptRunMismatchError(
                "attempt %r belongs to run %r, not %r"
                % (attempt.attempt_id, attempt.run_id, run_id)
            )
        finalised.append(cancel_attempt(attempt, canonical))
    return tuple(finalised)


@dataclass(frozen=True)
class FinalizedPartialUsage:
    """Partial usage/time/cost finalized where measurable (section 45B).

    *measured* holds metric -> value pairs for measurable quantities only;
    *unmeasurable* names metrics with no measured value (kept without
    inventing numbers). The two sets are always disjoint.
    """

    run_id: str = ""
    measured: Tuple[Tuple[str, float], ...] = ()
    unmeasurable: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        measured = tuple(self.measured) if self.measured is not None else ()
        unmeasurable = (
            tuple(self.unmeasurable) if self.unmeasurable is not None else ()
        )
        object.__setattr__(self, "measured", measured)
        object.__setattr__(self, "unmeasurable", unmeasurable)
        names = [name for name, _ in measured]
        if len(set(names)) != len(names):
            raise InvalidPartialUsageError(
                "duplicate measured metrics: %s" % sorted(names)
            )
        overlap = set(names) & set(unmeasurable)
        if overlap:
            raise InvalidPartialUsageError(
                "metrics both measured and unmeasurable: %s"
                % sorted(overlap)
            )


def finalize_partial_usage(
    run_id: str,
    measured: Optional[Mapping[str, Any]] = None,
    unmeasurable: Iterable[str] = (),
) -> FinalizedPartialUsage:
    """Finalize partial usage/time/cost for a cancelled run.

    Values must be finite real numbers; NaN/inf/non-numeric values raise
    (no invented numbers). Metrics with no measured value belong in
    *unmeasurable*, never in *measured* with a placeholder.
    """
    pairs = []
    for name, value in (dict(measured) if measured else {}).items():
        if not name or not isinstance(name, str):
            raise InvalidPartialUsageError(
                "measured metric names must be non-empty strings, got %r"
                % (name,)
            )
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise InvalidPartialUsageError(
                "measured metric %r must be a real number, got %r"
                % (name, value)
            )
        if not math.isfinite(value):
            raise InvalidPartialUsageError(
                "measured metric %r must be finite, got %r" % (name, value)
            )
        pairs.append((name, float(value)))
    return FinalizedPartialUsage(
        run_id=run_id,
        measured=tuple(pairs),
        unmeasurable=tuple(unmeasurable or ()),
    )


@dataclass(frozen=True)
class ReleaseDirective:
    """Release exactly one budget reservation or scheduler lease."""

    kind: str = ""
    ref: str = ""
    action: str = "release"

    def __post_init__(self) -> None:
        if self.kind not in (RELEASE_RESERVATION, RELEASE_LEASE):
            raise InvalidReleaseError(
                "release kind must be %r or %r, got %r"
                % (RELEASE_RESERVATION, RELEASE_LEASE, self.kind)
            )
        if not self.ref:
            raise InvalidReleaseError("release directive requires a ref")
        if self.action != "release":
            raise InvalidReleaseError(
                "release action is always 'release', got %r" % (self.action,)
            )


def release_all(
    reservation_ids: Iterable[str] = (),
    lease_ids: Iterable[str] = (),
) -> Tuple[ReleaseDirective, ...]:
    """Issue release directives for every reservation and lease id."""
    directives = [
        ReleaseDirective(kind=RELEASE_RESERVATION, ref=ref)
        for ref in (reservation_ids or ())
    ]
    directives.extend(
        ReleaseDirective(kind=RELEASE_LEASE, ref=ref)
        for ref in (lease_ids or ())
    )
    return tuple(directives)


def _as_tuple(value: Any) -> Tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    return tuple(value)


def _coerce_run_status(value: Any) -> manifest.ExecutionRunStatus:
    if isinstance(value, manifest.ExecutionRunStatus):
        return value
    try:
        return manifest.ExecutionRunStatus(str(value))
    except ValueError:
        raise IllegalCancellationTransitionError(
            "unknown run status %r" % (value,)
        ) from None


@dataclass(frozen=True)
class RunCancellation:
    """Finalized cancellation of one run (Manifest section 45B).

    *attempts* holds post-cancellation attempt rows (history kept: terminal
    rows untouched); *usage* finalizes measurable partial usage/time/cost;
    *releases* frees every reservation/lease; *audit_refs* and
    *verification_refs* pass through immutable; *history_kept* is always
    True (finalizing with history dropped is refused).
    """

    run_id: str = ""
    reason: manifest.RunTerminationReason = (
        manifest.RunTerminationReason.CANCELLED_BY_USER
    )
    from_status: manifest.ExecutionRunStatus = (
        manifest.ExecutionRunStatus.RUNNING
    )
    to_status: manifest.ExecutionRunStatus = (
        manifest.ExecutionRunStatus.CANCELLED
    )
    attempts: Tuple[CancellableAttempt, ...] = ()
    usage: Optional[FinalizedPartialUsage] = None
    releases: Tuple[ReleaseDirective, ...] = ()
    audit_refs: Tuple[str, ...] = ()
    verification_refs: Tuple[str, ...] = ()
    history_kept: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "reason", _coerce_reason(self.reason))
        object.__setattr__(self, "from_status", _coerce_run_status(self.from_status))
        object.__setattr__(self, "to_status", _coerce_run_status(self.to_status))
        object.__setattr__(self, "attempts", _as_tuple(self.attempts))
        object.__setattr__(self, "releases", _as_tuple(self.releases))
        object.__setattr__(self, "audit_refs", _as_tuple(self.audit_refs))
        object.__setattr__(
            self, "verification_refs", _as_tuple(self.verification_refs)
        )
        if self.to_status != manifest.ExecutionRunStatus.CANCELLED:
            raise IllegalCancellationTransitionError(
                "cancellation finalizes to CANCELLED, got %r"
                % (self.to_status.value,)
            )
        if self.history_kept is not True:
            raise IllegalCancellationTransitionError(
                "cancellation never drops history (history_kept must be True)"
            )
        if not manifest.is_run_transition_allowed(self.from_status, "CANCELLED"):
            raise IllegalCancellationTransitionError(
                "run status %r has no manifest edge to CANCELLED"
                % (self.from_status.value,)
            )


def finalize_cancellation(
    *,
    run_id: str,
    reason: Any,
    from_status: Any = manifest.ExecutionRunStatus.RUNNING,
    attempts: Iterable[CancellableAttempt] = (),
    measured_usage: Optional[Mapping[str, Any]] = None,
    unmeasurable_usage: Iterable[str] = (),
    reservation_ids: Iterable[str] = (),
    lease_ids: Iterable[str] = (),
    audit_refs: Iterable[str] = (),
    verification_refs: Iterable[str] = (),
) -> RunCancellation:
    """Finalize cancellation of one run per section 45B.

    Validates the canonical reason and the manifest run edge, cancels the
    run's attempts (history kept), finalizes measurable partial usage (None
    when there is nothing to finalize), issues release directives for every
    reservation/lease, and passes audit/verification refs through unchanged.
    """
    canonical = validate_cancellation_reason(reason)
    source = _coerce_run_status(from_status)
    if not manifest.is_run_transition_allowed(source, "CANCELLED"):
        raise IllegalCancellationTransitionError(
            "run status %r has no manifest edge to CANCELLED"
            % (source.value,)
        )
    finalised_attempts = cancel_attempts(attempts or (), run_id, canonical)
    unmeasurable = _as_tuple(unmeasurable_usage)
    if measured_usage or unmeasurable:
        usage: Optional[FinalizedPartialUsage] = finalize_partial_usage(
            run_id, measured_usage, unmeasurable
        )
    else:
        usage = None
    return RunCancellation(
        run_id=run_id,
        reason=canonical,
        from_status=source,
        attempts=finalised_attempts,
        usage=usage,
        releases=release_all(reservation_ids, lease_ids),
        audit_refs=_as_tuple(audit_refs),
        verification_refs=_as_tuple(verification_refs),
    )


__all__ = [
    "CANCELLATION_REASONS",
    "RELEASE_RESERVATION",
    "RELEASE_LEASE",
    "NonCanonicalCancellationReasonError",
    "IllegalCancellationTransitionError",
    "AttemptRunMismatchError",
    "InvalidPartialUsageError",
    "InvalidReleaseError",
    "is_cancellation_reason",
    "validate_cancellation_reason",
    "CancellableAttempt",
    "cancel_attempt",
    "cancel_attempts",
    "FinalizedPartialUsage",
    "finalize_partial_usage",
    "ReleaseDirective",
    "release_all",
    "RunCancellation",
    "finalize_cancellation",
]
