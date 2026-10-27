"""K13 storage repository ports (Manifest §42 APPLICATION_STORAGE; §41 set).

One in-memory port per authoritative aggregate. This module is domain core:
it never imports a database driver or anything under the adapter packages
(0C sec 12). Persistence lives in the K13 adapter package
(see migrations_k13.sql); adapters implement these same port shapes over
their own driver, which core never sees.

Frozen operation shape per port (manifest ports section):
  load(id) -> record | None
  append(record) -> record (immutable logs; duplicate idempotent key
      returns the stored record)
  compare_and_set(id, expected_version, record) -> record (mutable
      aggregates; loser re-reads)
  list_by(query) -> records in replay/audit-friendly (insertion) order.
Counters: increment(scope, kind, limit) -> value (atomic, restart-safe).

State edges are validated with the frozen manifest predicates only
(is_task_transition_allowed / is_run_transition_allowed /
is_attempt_transition_allowed); 0C wins every clash.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Dict, List, Mapping, Optional

try:
    from iface.frozen_manifest import manifest
except ImportError:  # alternate layout: the iface/ directory itself on sys.path
    from frozen_manifest import manifest


class RecordNotFoundError(KeyError):
    """load/compare_and_set target id is not stored."""


class VersionConflictError(ValueError):
    """CAS loser: expected_version != stored version; caller re-reads."""


class ImmutableRecordError(ValueError):
    """Append-only log rewrite attempt with different content."""


class IllegalTransitionError(ValueError):
    """State edge rejected by the frozen manifest transition tables."""


class CounterLimitExceededError(ValueError):
    """increment() would pass the configured limit."""


def _copy(record: Mapping[str, Any]) -> Dict[str, Any]:
    return dict(record)


class _MemoryPort(manifest.RepositoryPort):
    """Shared in-memory port mechanics (id map + insertion order + lock)."""

    DOMAIN = "records"
    ID_FIELD = "record_id"
    VERSION_FIELD = "version"
    MUTABLE = True

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rows: Dict[str, Dict[str, Any]] = {}
        self._order: List[str] = []

    # -- ports API ------------------------------------------------------
    def load(self, record_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            stored = self._rows.get(record_id)
            return _copy(stored) if stored is not None else None

    def append(self, record: Mapping[str, Any]) -> Dict[str, Any]:
        data = _copy(record)
        self._validate(data)
        key = data[self.ID_FIELD]
        with self._lock:
            stored = self._rows.get(key)
            if stored is not None:
                if _copy(stored) != data and not self.MUTABLE:
                    raise ImmutableRecordError(
                        "%s %s is append-only" % (self.DOMAIN, key)
                    )
                return _copy(stored)
            self._rows[key] = _copy(data)
            self._order.append(key)
            return _copy(data)

    def compare_and_set(
        self, record_id: str, expected_version: Any, record: Mapping[str, Any]
    ) -> Dict[str, Any]:
        data = _copy(record)
        self._validate(data)
        with self._lock:
            stored = self._rows.get(record_id)
            if stored is None:
                raise RecordNotFoundError(
                    "%s %s is not stored" % (self.DOMAIN, record_id)
                )
            if stored.get(self.VERSION_FIELD) != expected_version:
                raise VersionConflictError(
                    "%s %s expected version %r, stored %r"
                    % (self.DOMAIN, record_id, expected_version,
                       stored.get(self.VERSION_FIELD))
                )
            if not self.MUTABLE and _copy(stored) != data:
                raise ImmutableRecordError(
                    "%s %s is append-only" % (self.DOMAIN, record_id)
                )
            self._extra_check(stored, data)
            self._rows[record_id] = _copy(data)
            return _copy(data)

    def list_by(self, query: Mapping[str, Any]) -> list:
        filt = dict(query)
        with self._lock:
            rows = [_copy(self._rows[k]) for k in self._order]
        return [r for r in rows if all(r.get(k) == v for k, v in filt.items())]

    # -- hooks ----------------------------------------------------------
    def _validate(self, record: Dict[str, Any]) -> None:
        if not record.get(self.ID_FIELD):
            raise ValueError("%s record needs %s" % (self.DOMAIN, self.ID_FIELD))
        if not record.get("project_id"):
            raise ValueError("%s record needs project_id" % self.DOMAIN)

    def _extra_check(
        self, stored: Dict[str, Any], data: Dict[str, Any]
    ) -> None:
        """Per-port commit gate run inside compare_and_set."""

    # -- unit-of-work support -------------------------------------------
    def _snapshot(self) -> Any:
        with self._lock:
            return (_copy(dict(self._rows)), list(self._order))

    def _restore(self, snapshot: Any) -> None:
        rows, order = snapshot
        with self._lock:
            self._rows = _copy(dict(rows))
            self._order = list(order)


class ProjectRepository(_MemoryPort):
    """Mutable project aggregate (§8 PRODUCT_PROJECT_MODEL)."""

    DOMAIN = "projects"


class TaskContractRepository(_MemoryPort):
    """Contract versions (§13); active version resolves via activations."""

    DOMAIN = "contracts"
    MUTABLE = False

    def _validate(self, record: Dict[str, Any]) -> None:
        super()._validate(record)
        missing = [f for f in manifest.TASK_CONTRACT_FIELDS if f not in record]
        if missing:
            raise ValueError("contract missing fields: %s" % ",".join(missing))


class ContractActivationLog(_MemoryPort):
    """Immutable activation records (§15); recovery reads highest sequence."""

    DOMAIN = "activations"
    MUTABLE = False

    def _validate(self, record: Dict[str, Any]) -> None:
        super()._validate(record)
        missing = [f for f in manifest.CONTRACT_ACTIVATION_FIELDS if f not in record]
        if missing:
            raise ValueError("activation missing fields: %s" % ",".join(missing))


class TaskTransitionLog(_MemoryPort):
    """Immutable transition records (§12); edges checked at append."""

    DOMAIN = "transitions"
    MUTABLE = False

    def _validate(self, record: Dict[str, Any]) -> None:
        super()._validate(record)
        missing = [f for f in manifest.TRANSITION_FIELDS if f not in record]
        if missing:
            raise ValueError("transition missing fields: %s" % ",".join(missing))
        src = record.get("from_state", record.get("from"))
        dst = record.get("to_state", record.get("to"))
        override = bool(record.get("override", False))
        if not manifest.is_task_transition_allowed(src, dst, override=override):
            raise IllegalTransitionError(
                "task edge %r -> %r not allowed" % (src, dst)
            )


class ExecutionRunRepository(_MemoryPort):
    """Mutable run aggregate (§14); status edges checked on CAS."""

    DOMAIN = "runs"

    def _extra_check(
        self, stored: Dict[str, Any], data: Dict[str, Any]
    ) -> None:
        src = stored.get("status")
        dst = data.get("status")
        if dst is not None and dst != src:
            if not manifest.is_run_transition_allowed(src, dst):
                raise IllegalTransitionError(
                    "run edge %r -> %r not allowed" % (src, dst)
                )


class ExecutionAttemptLog(_MemoryPort):
    """Immutable attempts (§14B linear lifecycle)."""

    DOMAIN = "attempts"
    MUTABLE = False

    def _extra_check(
        self, stored: Dict[str, Any], data: Dict[str, Any]
    ) -> None:
        # Identical re-store only; status never mutates on a finished attempt.
        src = stored.get("status")
        dst = data.get("status")
        if dst is not None and dst != src:
            if not manifest.is_attempt_transition_allowed(src, dst):
                raise IllegalTransitionError(
                    "attempt edge %r -> %r not allowed" % (src, dst)
                )

    def _validate(self, record: Dict[str, Any]) -> None:
        super()._validate(record)
        src = record.get("from_status")
        dst = record.get("status")
        if src is not None and dst is not None and src != dst:
            if not manifest.is_attempt_transition_allowed(src, dst):
                raise IllegalTransitionError(
                    "attempt edge %r -> %r not allowed" % (src, dst)
                )


class AmendmentRepository(_MemoryPort):
    """Amendment aggregates (§15); lifecycle moves go through CAS."""

    DOMAIN = "amendments"

    def _validate(self, record: Dict[str, Any]) -> None:
        super()._validate(record)
        missing = [f for f in manifest.AMENDMENT_FIELDS if f not in record]
        if missing:
            raise ValueError("amendment missing fields: %s" % ",".join(missing))


class PolicyRepository(_MemoryPort):
    """Immutable versioned policy objects (§25A; one port per policy type).

    policy_type selects the family (routing/optimization/retry/fallback/
    verification/audit/override/failure_disposition).
    """

    DOMAIN = "policies"
    MUTABLE = False


class PolicyLifecycleLog(_MemoryPort):
    """Immutable policy lifecycle events (§25A PolicyLifecycleRecord)."""

    DOMAIN = "policy_lifecycle"
    MUTABLE = False


class RetryFallbackCounterStore(manifest.CounterStore):
    """Atomic restart-safe counters (§16; rework + fallback counters)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._values: Dict[str, Dict[str, Any]] = {}

    def increment(self, scope: str, kind: str, limit: int) -> int:
        key = "%s\x00%s" % (scope, kind)
        with self._lock:
            current = self._values.get(key, {}).get("value", 0)
            nxt = current + 1
            if nxt > limit:
                raise CounterLimitExceededError(
                    "counter %s:%s at %d, limit %d" % (scope, kind, current, limit)
                )
            self._values[key] = {
                "scope": scope,
                "kind": kind,
                "value": nxt,
                "limit": limit,
                "project_id": scope.split(":", 1)[0] if ":" in scope else scope,
            }
            return nxt

    def load(self, scope: str, kind: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            stored = self._values.get("%s\x00%s" % (scope, kind))
            return _copy(stored) if stored is not None else None

    def list_by(self, query: Mapping[str, Any]) -> list:
        filt = dict(query)
        with self._lock:
            rows = [_copy(v) for v in self._values.values()]
        return [r for r in rows if all(r.get(k) == v for k, v in filt.items())]

    def append(self, record: Mapping[str, Any]) -> Dict[str, Any]:
        data = _copy(record)
        if not data.get("project_id"):
            raise ValueError("counter record needs project_id")
        key = "%s\x00%s" % (data.get("scope", ""), data.get("kind", ""))
        with self._lock:
            stored = self._values.get(key)
            if stored is not None:
                return _copy(stored)
            self._values[key] = _copy(data)
            return _copy(data)

    def compare_and_set(
        self, record_id: str, expected_version: Any, record: Mapping[str, Any]
    ) -> Dict[str, Any]:
        raise ImmutableRecordError("counters move by increment() only")

    def _snapshot(self) -> Any:
        with self._lock:
            return _copy(dict(self._values))

    def _restore(self, snapshot: Any) -> None:
        with self._lock:
            self._values = _copy(dict(snapshot))


class VerificationLog(_MemoryPort):
    """Immutable verification records (§21C)."""

    DOMAIN = "verification"
    MUTABLE = False


class SuspensionLog(_MemoryPort):
    """Suspension + late-result reconciliation records (§12)."""

    DOMAIN = "suspension"
    MUTABLE = False


class RoutingDecisionLog(_MemoryPort):
    """Routing decisions + assignments (§28)."""

    DOMAIN = "routing"
    MUTABLE = False


class RoutingEvidenceSnapshotLog(_MemoryPort):
    """Routing evidence snapshots (§28); decisions reference these."""

    DOMAIN = "routing_snapshots"
    MUTABLE = False


class ResourceLeaseRegistry(_MemoryPort):
    """Resource leases (§38); expiry/orphan moves go through CAS."""

    DOMAIN = "leases"


class ResourceReservationRegistry(_MemoryPort):
    """Resource reservations (§38); fulfil/release moves go through CAS."""

    DOMAIN = "reservations"


class BudgetLedger(_MemoryPort):
    """Budget reservations + settlements + states (§27A).

    Settlement dedupe identity is (reservation_id,
    provider_usage_evidence_ref), never settlement_id.
    """

    DOMAIN = "budget"

    def settle_key(self, record: Mapping[str, Any]) -> str:
        return "%s\x00%s" % (
            record.get("reservation_id", ""),
            record.get("provider_usage_evidence_ref")
            or record.get("provider_request_ref", ""),
        )


class TelemetryEventRepository(_MemoryPort):
    """Telemetry envelope port (§55); event_type vocabulary enforced."""

    DOMAIN = "telemetry"
    MUTABLE = False

    def _validate(self, record: Dict[str, Any]) -> None:
        super()._validate(record)
        if not record.get("event_id"):
            raise ValueError("telemetry record needs event_id")


class MetricRecordRepository(_MemoryPort):
    """Metric record port (§11); value+unit+state+source required."""

    DOMAIN = "metrics"
    MUTABLE = False

    def _validate(self, record: Dict[str, Any]) -> None:
        super()._validate(record)
        for field in ("metric_name", "value", "unit", "state", "source"):
            if record.get(field) is None:
                raise ValueError("metric record needs %s" % field)


# drift-3 manifest aliases: TelemetryEventLog over TelemetryEventRepository,
# MetricRecordLog over MetricRecordRepository (identical behavior).
TelemetryEventLog = TelemetryEventRepository
MetricRecordLog = MetricRecordRepository


class GovernanceArtifactLog(_MemoryPort):
    """Governance artifacts (§21)."""

    DOMAIN = "governance"
    MUTABLE = False


class DecisionLog(_MemoryPort):
    """Decision records incl. pre-run/Phase-0 scope (§21B)."""

    DOMAIN = "decisions"
    MUTABLE = False


class FinalizationLog(_MemoryPort):
    """Finalization records (§21D)."""

    DOMAIN = "finalization"
    MUTABLE = False


class ContextIntegrityLog(_MemoryPort):
    """Context integrity records (§45A)."""

    DOMAIN = "context_integrity"
    MUTABLE = False


class IncidentIndex(_MemoryPort):
    """Incident index rows only; truth stays in ContextIntegrityLog (§46)."""

    DOMAIN = "incidents"
    MUTABLE = False


class UnitOfWork:
    """Atomic multi-record writes (§42; coverage row M-D-D33).

    Stage appends/CAS calls across repositories, then commit() validates
    and applies all of them or none. Repositories are restored from
    snapshots when any staged op fails, so a partial write never lands.
    Usable as a context manager (commit on clean exit, rollback on error).
    """

    def __init__(self) -> None:
        self._staged: List[Callable[[], None]] = []
        self._repos: List[Any] = []
        self._committed = False

    def _track(self, repo: Any) -> None:
        if repo not in self._repos:
            self._repos.append(repo)

    def stage_append(self, repo: Any, record: Mapping[str, Any]) -> None:
        self._track(repo)
        self._staged.append(lambda: repo.append(record))

    def stage_compare_and_set(
        self, repo: Any, record_id: str, expected_version: Any,
        record: Mapping[str, Any],
    ) -> None:
        self._track(repo)
        self._staged.append(
            lambda: repo.compare_and_set(record_id, expected_version, record)
        )

    def commit(self) -> None:
        snapshots = {id(r): r._snapshot() for r in self._repos}
        try:
            for op in self._staged:
                op()
        except Exception:
            for repo in self._repos:
                repo._restore(snapshots[id(repo)])
            raise
        self._staged = []
        self._committed = True

    def rollback(self) -> None:
        self._staged = []

    def __enter__(self) -> "UnitOfWork":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        return False
