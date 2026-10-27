"""Resource leases, reservations and restart recovery (Manifest sec 38).

Frozen record shapes live here as frozen dataclasses; all mutable registry
state is confined to LeaseStore. Imports are stdlib plus the frozen manifest
interface only. Budget and routing writers live outside this module and are
injected as callables by the scheduler layer.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Dict, List, Optional, Tuple

try:
    from iface.frozen_manifest import manifest  # noqa: F401 (frozen names)
except ImportError:  # alternate layout: the iface/ folder on sys.path
    from frozen_manifest import manifest  # type: ignore[no-redef]  # noqa: F401


class ResourceLeaseStatus(str, Enum):
    """Manifest sec 38 ENUM ResourceLeaseStatus (frozen member set)."""

    CREATED = "CREATED"
    ACTIVE = "ACTIVE"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"
    ORPHANED = "ORPHANED"


class ResourceReservationStatus(str, Enum):
    """Manifest sec 38 ENUM ResourceReservationStatus (frozen member set)."""

    CREATED = "CREATED"
    ACTIVE = "ACTIVE"
    FULFILLED = "FULFILLED"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"
    ORPHANED = "ORPHANED"


@dataclass(frozen=True)
class ResourceStateSnapshot:
    """Manifest sec 38 ResourceStateSnapshot (authoritative when referenced)."""

    resource_state_snapshot_id: str
    project_id: str
    task_id: str
    run_id: str
    created_at: float
    available_gpu_slots: int
    available_cpu_slots: int
    memory_available: int
    gpu_memory_available: int
    queue_depth: int
    provider_capacity_refs: Tuple[str, ...] = ()
    hash: str = ""


@dataclass(frozen=True)
class ResourceLease:
    """Manifest sec 38 ResourceLease (authoritative, persistent)."""

    lease_id: str
    project_id: str
    task_id: str
    run_id: str
    resource_type: str
    resource_id: str
    owner_run_id: str
    acquired_at: float
    expires_at: float
    released_at: Optional[float]
    status: ResourceLeaseStatus
    capacity_claim: int
    evidence_ref: str


@dataclass(frozen=True)
class ResourceReservation:
    """Manifest sec 38 ResourceReservation (authoritative, persistent)."""

    reservation_id: str
    project_id: str
    task_id: str
    run_id: str
    resource_type: str
    resource_id: Optional[str]
    owner_run_id: str
    requested_capacity: int
    created_at: float
    expires_at: float
    fulfilled_at: Optional[float]
    released_at: Optional[float]
    status: ResourceReservationStatus
    evidence_ref: str


@dataclass(frozen=True)
class LeaseRequest:
    """Capacity ask evaluated by precheck and consumed by reserve."""

    project_id: str
    task_id: str
    run_id: str
    resource_type: str
    requested_capacity: int = 1
    resource_id: Optional[str] = None


@dataclass(frozen=True)
class PrecheckOutcome:
    """Read-only eligibility answer; creating one changes no registry state."""

    eligible: bool
    snapshot: ResourceStateSnapshot
    queue_position: Optional[int]
    available_capacity: int


@dataclass(frozen=True)
class ReserveOutcome:
    """Reserve answer: a bound Lease, or a queue slot that is never dropped."""

    kind: str  # "LEASE" or "QUEUED"
    lease: Optional[ResourceLease]
    reservation: Optional[ResourceReservation]
    queue_position: Optional[int]
    estimated_start: Optional[float]


@dataclass(frozen=True)
class QueuedEntry:
    """FIFO queue slot; excess demand waits here, it is never discarded."""

    request: LeaseRequest
    enqueued_at: float
    queue_position: int


@dataclass(frozen=True)
class RecoveryReport:
    """Lease half of restart recovery: expired leases are never trusted."""

    trusted_lease_ids: Tuple[str, ...]
    expired_untrusted_ids: Tuple[str, ...]
    orphans_released_ids: Tuple[str, ...]
    revalidated_run_ids: Tuple[str, ...]


_ACTIVE_HOLDING = (
    ResourceLeaseStatus.CREATED,
    ResourceLeaseStatus.ACTIVE,
)


class LeaseStore:
    """Mutable registry for leases, reservations and the wait queue.

    precheck() is strictly read-only. reserve() binds a lease plus a
    reservation when capacity is free, else appends a queue slot (excess
    demand queues, never drops). recover() reconciles persisted entries
    with live runs: expired leases are never trusted, orphans are
    released/expired deterministically, live owners are revalidated.
    """

    def __init__(self, capacity_slots: int, lease_timeout: float) -> None:
        if (
            isinstance(capacity_slots, bool)
            or not isinstance(capacity_slots, int)
            or capacity_slots < 1
        ):
            raise ValueError("capacity_slots must be an int >= 1")
        if lease_timeout <= 0:
            raise ValueError("lease_timeout must be positive")
        self._capacity = capacity_slots
        self._lease_timeout = lease_timeout
        self._leases: Dict[str, ResourceLease] = {}
        self._reservations: Dict[str, ResourceReservation] = {}
        self._lease_links: Dict[str, str] = {}
        self._queue: List[QueuedEntry] = []
        self._lease_seq = 0
        self._reservation_seq = 0

    @property
    def capacity(self) -> int:
        return self._capacity

    def active_capacity(self) -> int:
        return sum(
            lease.capacity_claim
            for lease in list(self._leases.values())
            if lease.status in _ACTIVE_HOLDING
        )

    def queue_depth(self) -> int:
        return len(self._queue)

    def lease_count(self) -> int:
        return len(self._leases)

    def reservation_count(self) -> int:
        return len(self._reservations)

    def get_lease(self, lease_id: str) -> ResourceLease:
        return self._leases[lease_id]

    def get_reservation(self, reservation_id: str) -> ResourceReservation:
        return self._reservations[reservation_id]

    def _snapshot(self, request: LeaseRequest, now: float) -> ResourceStateSnapshot:
        free = self._capacity - self.active_capacity()
        return ResourceStateSnapshot(
            resource_state_snapshot_id="snap-%s-%s" % (request.run_id, int(now)),
            project_id=request.project_id,
            task_id=request.task_id,
            run_id=request.run_id,
            created_at=now,
            available_gpu_slots=max(0, free),
            available_cpu_slots=max(0, free),
            memory_available=max(0, free),
            gpu_memory_available=max(0, free),
            queue_depth=len(self._queue),
            provider_capacity_refs=(),
            hash="",
        )

    def precheck(self, request: LeaseRequest, now: float) -> PrecheckOutcome:
        """Read-only eligibility: inspects state, changes nothing."""
        free = self._capacity - self.active_capacity()
        eligible = request.requested_capacity <= free
        position: Optional[int] = None
        if not eligible:
            position = len(self._queue) + 1
        return PrecheckOutcome(
            eligible=eligible,
            snapshot=self._snapshot(request, now),
            queue_position=position,
            available_capacity=max(0, free),
        )

    def _bind(self, request: LeaseRequest, now: float) -> ReserveOutcome:
        """Bind a lease + reservation directly; never touches the queue."""
        self._lease_seq += 1
        self._reservation_seq += 1
        lease_id = "lease-%d" % self._lease_seq
        reservation_id = "resvn-%d" % self._reservation_seq
        lease = ResourceLease(
            lease_id=lease_id,
            project_id=request.project_id,
            task_id=request.task_id,
            run_id=request.run_id,
            resource_type=request.resource_type,
            resource_id=request.resource_id or "slot-%d" % self._lease_seq,
            owner_run_id=request.run_id,
            acquired_at=now,
            expires_at=now + self._lease_timeout,
            released_at=None,
            status=ResourceLeaseStatus.ACTIVE,
            capacity_claim=request.requested_capacity,
            evidence_ref="ev-%s" % lease_id,
        )
        reservation = ResourceReservation(
            reservation_id=reservation_id,
            project_id=request.project_id,
            task_id=request.task_id,
            run_id=request.run_id,
            resource_type=request.resource_type,
            resource_id=lease.resource_id,
            owner_run_id=request.run_id,
            requested_capacity=request.requested_capacity,
            created_at=now,
            expires_at=now + self._lease_timeout,
            fulfilled_at=None,
            released_at=None,
            status=ResourceReservationStatus.ACTIVE,
            evidence_ref="ev-%s" % reservation_id,
        )
        self._leases[lease_id] = lease
        self._reservations[reservation_id] = reservation
        self._lease_links[lease_id] = reservation_id
        return ReserveOutcome(
            kind="LEASE",
            lease=lease,
            reservation=reservation,
            queue_position=None,
            estimated_start=now,
        )

    def reserve(self, request: LeaseRequest, now: float) -> ReserveOutcome:
        """Bind a lease + reservation, or queue the ask (never drop it)."""
        free = self._capacity - self.active_capacity()
        if request.requested_capacity <= free and not self._queue:
            return self._bind(request, now)
        position = len(self._queue) + 1
        self._queue.append(
            QueuedEntry(request=request, enqueued_at=now,
                        queue_position=position)
        )
        return ReserveOutcome(
            kind="QUEUED",
            lease=None,
            reservation=None,
            queue_position=position,
            estimated_start=now + position * self._lease_timeout,
        )

    def promote(self, now: float) -> List[ReserveOutcome]:
        """Bind queued asks FIFO while capacity is free. Never drops."""
        granted: List[ReserveOutcome] = []
        for _ in range(len(self._queue)):
            if not self._queue:
                break
            head = self._queue[0]
            free = self._capacity - self.active_capacity()
            if head.request.requested_capacity > free:
                break
            self._queue.pop(0)
            for index, entry in enumerate(list(self._queue)):
                self._queue[index] = replace(
                    entry, queue_position=index + 1
                )
            outcome = self._bind(head.request, now)
            assert outcome.kind == "LEASE"
            granted.append(outcome)
        return granted

    def release(self, lease_id: str, now: float) -> ResourceLease:
        lease = self._leases[lease_id]
        if lease.status in _ACTIVE_HOLDING:
            lease = replace(
                lease,
                status=ResourceLeaseStatus.RELEASED,
                released_at=now,
            )
            self._leases[lease_id] = lease
            linked = self._lease_links.get(lease_id)
            if linked is not None and linked in self._reservations:
                current = self._reservations[linked]
                if current.status in (
                    ResourceReservationStatus.CREATED,
                    ResourceReservationStatus.ACTIVE,
                    ResourceReservationStatus.FULFILLED,
                ):
                    self._reservations[linked] = replace(
                        current,
                        status=ResourceReservationStatus.RELEASED,
                        released_at=now,
                    )
        return self._leases[lease_id]

    def fulfill(self, reservation_id: str, now: float) -> ResourceReservation:
        current = self._reservations[reservation_id]
        if current.status == ResourceReservationStatus.ACTIVE:
            current = replace(
                current, status=ResourceReservationStatus.FULFILLED,
                fulfilled_at=now,
            )
            self._reservations[reservation_id] = current
        return self._reservations[reservation_id]

    def expire_due(self, now: float) -> Tuple[str, ...]:
        expired: List[str] = []
        for lease_id, lease in list(self._leases.items()):
            if (
                lease.status in _ACTIVE_HOLDING
                and lease.expires_at <= now
            ):
                self._leases[lease_id] = replace(
                    lease, status=ResourceLeaseStatus.EXPIRED
                )
                expired.append(lease_id)
                linked = self._lease_links.get(lease_id)
                if linked is not None and linked in self._reservations:
                    current = self._reservations[linked]
                    if current.status in (
                        ResourceReservationStatus.CREATED,
                        ResourceReservationStatus.ACTIVE,
                    ):
                        self._reservations[linked] = replace(
                            current,
                            status=ResourceReservationStatus.EXPIRED,
                        )
        return tuple(expired)

    def recover(
        self,
        persisted_leases: Tuple[ResourceLease, ...],
        persisted_reservations: Tuple[ResourceReservation, ...],
        live_run_ids: Tuple[str, ...],
        now: float,
    ) -> RecoveryReport:
        """Reconcile persisted entries with live runs.

        Expired leases are never trusted. Orphans (owner gone) are marked
        ORPHANED and released deterministically. Live, unexpired owners
        are revalidated and trusted.
        """
        live = set(live_run_ids)
        trusted: List[str] = []
        expired_untrusted: List[str] = []
        orphans: List[str] = []
        revalidated: List[str] = []
        for lease in persisted_leases:
            if lease.expires_at <= now:
                self._leases[lease.lease_id] = replace(
                    lease, status=ResourceLeaseStatus.EXPIRED
                )
                expired_untrusted.append(lease.lease_id)
            elif lease.owner_run_id not in live:
                self._leases[lease.lease_id] = replace(
                    lease,
                    status=ResourceLeaseStatus.ORPHANED,
                    released_at=now,
                )
                orphans.append(lease.lease_id)
            else:
                self._leases[lease.lease_id] = lease
                trusted.append(lease.lease_id)
                if lease.owner_run_id not in revalidated:
                    revalidated.append(lease.owner_run_id)
        for reservation in persisted_reservations:
            if reservation.expires_at <= now:
                self._reservations[reservation.reservation_id] = replace(
                    reservation, status=ResourceReservationStatus.EXPIRED
                )
            elif reservation.owner_run_id not in live:
                self._reservations[reservation.reservation_id] = replace(
                    reservation,
                    status=ResourceReservationStatus.ORPHANED,
                    released_at=now,
                )
            else:
                self._reservations[reservation.reservation_id] = reservation
        return RecoveryReport(
            trusted_lease_ids=tuple(trusted),
            expired_untrusted_ids=tuple(expired_untrusted),
            orphans_released_ids=tuple(orphans),
            revalidated_run_ids=tuple(revalidated),
        )
