"""Project budget gate: K04 code over frozen K13 schemas (PRODUCT_SPEC 27A).

Frozen flow order (never reordered here):
    ModelRouter -> ResourceScheduler (precheck, read-only) -> BudgetGate
    -> AttemptExecutionGate -> execution.
Reservations are taken before parallel cloud runs; measured or calculated
cost settles them afterwards; failed gates compensate idempotently.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from agent_si.routing.interface import ReservationRequest


BUDGET_BREACH_WORDS = "hard budget limit blocks new billable cloud work"


class BudgetError(Exception):
    """Base error for budget-gate failures."""


class BudgetBlockedError(BudgetError):
    """Raised when the hard limit blocks a billable reservation."""


class DuplicateSettlementError(BudgetError):
    """Raised when a settlement dedupe key is already settled."""

    def __init__(self, message, existing=None):
        super().__init__(message)
        self.existing = existing


def _dec(value):
    from decimal import Decimal

    return Decimal(str(value))


@dataclass
class BudgetState:
    """Mutable ledger aggregate. remaining_derived is CALCULATED, never stored."""

    project_id: str
    currency: str
    budget_limit: str
    soft_limit: str
    hard_limit: str
    spent: str = "0"
    reserved: str = "0"
    updated_at: str = ""
    provider_spend_caps: dict = field(default_factory=dict)

    @property
    def remaining_derived(self):
        return str(_dec(self.hard_limit) - _dec(self.spent) - _dec(self.reserved))

    def to_dict(self):
        return {
            "project_id": self.project_id,
            "currency": self.currency,
            "budget_limit": self.budget_limit,
            "soft_limit": self.soft_limit,
            "hard_limit": self.hard_limit,
            "spent": self.spent,
            "reserved": self.reserved,
            "updated_at": self.updated_at,
            "provider_spend_caps": dict(self.provider_spend_caps),
        }

    @classmethod
    def from_dict(cls, data):
        kwargs = {k: data[k] for k in (
            "project_id", "currency", "budget_limit", "soft_limit",
            "hard_limit", "spent", "reserved", "updated_at",
        ) if k in data}
        kwargs["provider_spend_caps"] = dict(data.get("provider_spend_caps") or {})
        return cls(**kwargs)


@dataclass
class BudgetReservation:
    reservation_id: str
    project_id: str
    task_id: str
    run_id: str
    estimated_amount: str
    reserved_at: str
    expires_at: str
    status: str = "ACTIVE"
    provider_request_ref: str = ""
    provider_id: str = ""

    def to_dict(self):
        return {
            "reservation_id": self.reservation_id,
            "project_id": self.project_id,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "estimated_amount": self.estimated_amount,
            "reserved_at": self.reserved_at,
            "expires_at": self.expires_at,
            "status": self.status,
            "provider_request_ref": self.provider_request_ref,
            "provider_id": self.provider_id,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(**data)


@dataclass
class BudgetSettlement:
    settlement_id: str
    reservation_id: str
    provider_usage_evidence_ref: str | None
    provider_request_ref: str
    dedupe_key: str
    actual_amount: str | None
    difference: str | None
    status: str
    settled_at: str | None
    source: str

    def to_dict(self):
        return {
            "settlement_id": self.settlement_id,
            "reservation_id": self.reservation_id,
            "provider_usage_evidence_ref": self.provider_usage_evidence_ref,
            "provider_request_ref": self.provider_request_ref,
            "dedupe_key": self.dedupe_key,
            "actual_amount": self.actual_amount,
            "difference": self.difference,
            "status": self.status,
            "settled_at": self.settled_at,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(**data)


@dataclass
class IncidentRecord:
    incident_id: str
    project_id: str
    timestamp: str
    task_id: str
    run_id: str
    actor: str
    detected_by: str
    severity: str
    type: str
    description: str
    root_cause: str
    impact: str
    action: str
    regression_test: str
    status: str

    def to_dict(self):
        return {
            "incident_id": self.incident_id,
            "project_id": self.project_id,
            "timestamp": self.timestamp,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "actor": self.actor,
            "detected_by": self.detected_by,
            "severity": self.severity,
            "type": self.type,
            "description": self.description,
            "root_cause": self.root_cause,
            "impact": self.impact,
            "action": self.action,
            "regression_test": self.regression_test,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(**data)


@dataclass
class ReserveResult:
    ok: bool
    reservation: BudgetReservation | None
    warning: str | None
    message: str


def dedupe_key_for(reservation_id, provider_usage_evidence_ref, provider_request_ref):
    """Deterministic settlement dedupe identity (settlement_id NEVER part of it)."""
    if provider_usage_evidence_ref is not None:
        return reservation_id + "|" + provider_usage_evidence_ref
    return reservation_id + "|" + provider_request_ref + "|PENDING_RECONCILIATION"


_RESERVE_POSITIONAL = (
    "project_id", "task_id", "run_id", "reservation_id",
    "estimated_amount", "reserved_at", "expires_at", "route",
    "is_billable", "allow_local_zero_cost", "override_ref",
    "provider_request_ref", "provider_id",
)

_SETTLE_POSITIONAL = (
    "reservation_id", "provider_request_ref", "source", "settled_at",
    "actual_amount", "provider_usage_evidence_ref",
)

_RESERVE_FROZEN_FIELDS = _RESERVE_POSITIONAL

_SETTLE_FROZEN_FIELDS = _SETTLE_POSITIONAL


def _utcnow_z():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _default_expires_z(reserved_at):
    try:
        base = datetime.fromisoformat(str(reserved_at).replace("Z", "+00:00"))
    except ValueError:
        base = datetime.now(timezone.utc)
    return (base + timedelta(days=1)).isoformat().replace("+00:00", "Z")


def _frozen_reservation_id(project_id, task_id, run_id, estimated_amount,
                           provider_request_ref):
    raw = "|".join((str(project_id), str(task_id), str(run_id),
                    str(estimated_amount), str(provider_request_ref or "")))
    return "res-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class BudgetGate:
    """Atomic compare-and-reserve hard-budget gate with deterministic settlement."""

    def __init__(self, store_dir=None):
        self._lock = threading.Lock()
        self._store_dir = store_dir
        self._states = {}
        self._reservations = {}
        self._settlements = {}
        self._incidents = []
        self._settlement_seq = 0
        if store_dir is not None:
            os.makedirs(store_dir, exist_ok=True)
            self._load()

    # -- persistence -----------------------------------------------------
    def _path(self, name):
        return os.path.join(str(self._store_dir), name)

    def _write_json(self, name, payload):
        if self._store_dir is None:
            return
        tmp = self._path(name + ".tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, self._path(name))

    def _load(self):
        try:
            with open(self._path("budget_states.json"), encoding="utf-8") as fh:
                for row in json.load(fh):
                    state = BudgetState.from_dict(row)
                    self._states[state.project_id] = state
        except FileNotFoundError:
            pass
        try:
            with open(self._path("reservations.json"), encoding="utf-8") as fh:
                for row in json.load(fh):
                    res = BudgetReservation.from_dict(row)
                    self._reservations[res.reservation_id] = res
        except FileNotFoundError:
            pass
        try:
            with open(self._path("settlements.json"), encoding="utf-8") as fh:
                for row in json.load(fh):
                    stl = BudgetSettlement.from_dict(row)
                    self._settlements[stl.dedupe_key] = stl
                    self._settlement_seq += 1
        except FileNotFoundError:
            pass
        if os.path.isdir(str(self._store_dir)):
            for name in sorted(os.listdir(str(self._store_dir))):
                if name.startswith("incident-") and name.endswith(".json"):
                    with open(self._path(name), encoding="utf-8") as fh:
                        self._incidents.append(IncidentRecord.from_dict(json.load(fh)))

    def _persist(self):
        self._write_json(
            "budget_states.json", [s.to_dict() for s in self._states.values()])
        self._write_json(
            "reservations.json", [r.to_dict() for r in self._reservations.values()])
        self._write_json(
            "settlements.json", [s.to_dict() for s in self._settlements.values()])

    def _persist_incident(self, incident):
        self._write_json(
            "incident-%s.json" % incident.incident_id, incident.to_dict())

    # -- budget configuration (editable limits, real usage in currency) --
    def configure_project(self, project_id, currency, budget_limit, soft_limit,
                          hard_limit, updated_at="",
                          provider_spend_caps=None):
        with self._lock:
            state = BudgetState(
                project_id=project_id, currency=currency,
                budget_limit=str(budget_limit), soft_limit=str(soft_limit),
                hard_limit=str(hard_limit), updated_at=updated_at,
                provider_spend_caps={
                    str(k): str(v)
                    for k, v in dict(provider_spend_caps or {}).items()
                },
            )
            self._states[project_id] = state
            self._persist()
            return state

    def update_limits(self, project_id, budget_limit=None, soft_limit=None,
                      hard_limit=None, updated_at="",
                      provider_spend_caps=None):
        with self._lock:
            state = self._states[project_id]
            if budget_limit is not None:
                state.budget_limit = str(budget_limit)
            if soft_limit is not None:
                state.soft_limit = str(soft_limit)
            if hard_limit is not None:
                state.hard_limit = str(hard_limit)
            if provider_spend_caps is not None:
                state.provider_spend_caps = {
                    str(k): str(v)
                    for k, v in dict(provider_spend_caps).items()
                }
            state.updated_at = updated_at
            self._persist()
            return state

    def get_state(self, project_id: str) -> BudgetState:
        with self._lock:
            return self._states[project_id]

    def _provider_committed_locked(self, project_id, provider_id):
        """Provider settled spend + live reserved estimates (lock held)."""
        total = _dec("0")
        for res in self._reservations.values():
            if res.project_id == project_id \
                    and res.provider_id == provider_id \
                    and res.status in ("ACTIVE", "CREATED"):
                total += _dec(res.estimated_amount)
        for stl in self._settlements.values():
            if stl.status != "SETTLED" or stl.actual_amount is None:
                continue
            res = self._reservations.get(stl.reservation_id)
            if res is not None and res.project_id == project_id \
                    and res.provider_id == provider_id:
                total += _dec(stl.actual_amount)
        return total

    def provider_committed(self, project_id, provider_id):
        """Settled spend + live reserved estimates for one provider."""
        with self._lock:
            return str(self._provider_committed_locked(
                project_id, provider_id))

    def _record_incident_locked(self, state, task_id, run_id, timestamp,
                                description,
                                root_cause="budget admission refused"):
        """Append + persist one budget_breach incident (lock held)."""
        incident = IncidentRecord(
            incident_id="inc-%s-%d" % (state.project_id,
                                       len(self._incidents) + 1),
            project_id=state.project_id, timestamp=timestamp,
            task_id=task_id, run_id=run_id,
            actor="budget_gate", detected_by="budget_gate",
            severity="HIGH", type="budget_breach",
            description=description,
            root_cause=root_cause,
            impact="billable cloud execution not started",
            action="BLOCKED",
            regression_test=(
                "tests/test_k04b_budget_telemetry.py::"
                "test_every_budget_breach_recorded_as_persistent_incident"
            ),
            status="OPEN",
        )
        self._incidents.append(incident)
        self._persist_incident(incident)
        return incident

    def record_provider_incident(self, project_id, task_id, run_id,
                                 timestamp, description,
                                 incident_id=None,
                                 root_cause="helper-provider outage"):
        """Append + persist one provider-outage incident row (public path).

        Outage linkage (M-P2-68/R-366): incident_id carries the shared
        outage id when given, else the next inc-<project>-<n> identity.
        """
        with self._lock:
            state = self._states[project_id]
            if incident_id is None:
                incident_id = "inc-%s-%d" % (project_id,
                                             len(self._incidents) + 1)
            incident = IncidentRecord(
                incident_id=incident_id,
                project_id=project_id, timestamp=timestamp,
                task_id=task_id, run_id=run_id,
                actor="budget_observe", detected_by="budget_observe",
                severity="HIGH", type="provider_outage",
                description=description,
                root_cause=root_cause,
                impact="helper-provider service DOWN; "
                       "billable work refused fail-closed",
                action="LINKED",
                regression_test=(
                    "tests/test_outage_r366_m268.py::"
                    "test_outage_round_trip_links_telemetry_and_budget"
                ),
                status="OPEN",
            )
            self._incidents.append(incident)
            self._persist_incident(incident)
            return incident

    # -- admission --------------------------------------------------------
    def compare_and_reserve(self, request: ReservationRequest) -> BudgetReservation:
        """Frozen facade: ReservationRequest (Mapping/None tolerated positionally).

        Frozen `request` carries project_id/task_id/run_id/estimated_amount/
        provider_request_ref; reservation_id/reserved_at/expires_at fall back
        to deterministic derivations. Delegates to _compare_and_reserve_impl.
        Runtime returns the ReserveResult.
        """
        if request is None:
            raise ValueError(
                "compare_and_reserve needs a ReservationRequest")
        if isinstance(request, Mapping):
            data = dict(request)
        elif hasattr(request, "project_id") and hasattr(request, "task_id"):
            data = {}
            for key in _RESERVE_FROZEN_FIELDS:
                if hasattr(request, key):
                    data[key] = getattr(request, key)
        else:
            raise ValueError(
                "compare_and_reserve request must be a ReservationRequest, "
                "a mapping, or None (got %s)" % type(request).__name__)
        for key in ("project_id", "task_id", "run_id", "estimated_amount"):
            if key not in data or data[key] is None \
                    or (isinstance(data[key], str) and not data[key]):
                raise ValueError(
                    "compare_and_reserve request is missing %r" % (key,))
        if not data.get("reservation_id"):
            data["reservation_id"] = _frozen_reservation_id(
                data["project_id"], data["task_id"], data["run_id"],
                data["estimated_amount"],
                data.get("provider_request_ref", ""))
        if not data.get("reserved_at"):
            data["reserved_at"] = _utcnow_z()
        if not data.get("expires_at"):
            data["expires_at"] = _default_expires_z(data["reserved_at"])
        return self._compare_and_reserve_impl(
            project_id=data["project_id"], task_id=data["task_id"],
            run_id=data["run_id"], reservation_id=data["reservation_id"],
            estimated_amount=data["estimated_amount"],
            reserved_at=data["reserved_at"], expires_at=data["expires_at"],
            route=data.get("route", "CLOUD"),
            is_billable=data.get("is_billable", True),
            allow_local_zero_cost=data.get("allow_local_zero_cost", True),
            override_ref=data.get("override_ref"),
            provider_request_ref=data.get("provider_request_ref", ""),
            provider_id=data.get("provider_id"),
        )

    def _compare_and_reserve_impl(self, project_id, task_id, run_id,
                                  reservation_id, estimated_amount,
                                  reserved_at, expires_at, route="CLOUD",
                                  is_billable=True,
                                  allow_local_zero_cost=True,
                                  override_ref=None, provider_request_ref="",
                                  provider_id=None):
        """Atomic spent + reserved + requested <= hard else block.

        Soft limit warns; hard limit blocks billable cloud work unless an
        explicitly authorized override exists. Local zero-marginal-cost work
        may continue when policy allows.
        """
        with self._lock:
            state = self._states[project_id]
            if reservation_id in self._reservations:
                held = self._reservations[reservation_id]
                held_committed = _dec(state.spent) + _dec(state.reserved)
                held_warning = None
                if held_committed > _dec(state.soft_limit):
                    held_warning = (
                        "soft budget limit reached [BUDGET_SOFT_WARN]: "
                        "committed %s of soft %s %s"
                        % (held_committed, state.soft_limit, state.currency)
                    )
                return ReserveResult(
                    ok=True, reservation=held, warning=held_warning,
                    message="reservation already held",
                )
            requested = _dec(estimated_amount)
            committed = _dec(state.spent) + _dec(state.reserved)
            warning = None
            if committed + requested > _dec(state.soft_limit):
                warning = (
                    "soft budget limit reached [BUDGET_SOFT_WARN]: "
                    "committed %s of soft %s %s"
                    % (committed + requested, state.soft_limit, state.currency)
                )
            cap = None
            if provider_id:
                cap = (state.provider_spend_caps or {}).get(provider_id)
            if cap is not None and (
                    self._provider_committed_locked(project_id, provider_id)
                    + requested > _dec(cap)):
                incident = self._record_incident_locked(
                    state, task_id, run_id, reserved_at,
                    "provider budget spend cap blocks new billable cloud work"
                    ": project %s provider %s requested %s %s would exceed "
                    "cap %s %s (provider committed %s)"
                    % (project_id, provider_id, estimated_amount,
                       state.currency, cap, state.currency,
                       self._provider_committed_locked(
                           project_id, provider_id) + requested),
                    root_cause="provider-cap admission refused",
                )
                raise BudgetBlockedError(incident.description)
            if committed + requested <= _dec(state.hard_limit):
                return self._take(
                    state, project_id, task_id, run_id, reservation_id,
                    str(estimated_amount), reserved_at, expires_at,
                    provider_request_ref, warning,
                    "reserved %s %s against hard %s %s"
                    % (estimated_amount, state.currency,
                       state.hard_limit, state.currency),
                    provider_id or "",
                )
            if override_ref:
                return self._take(
                    state, project_id, task_id, run_id, reservation_id,
                    str(estimated_amount), reserved_at, expires_at,
                    provider_request_ref, warning,
                    "reserved under explicitly authorized override %s"
                    % override_ref,
                    provider_id or "",
                )
            if route == "LOCAL" and (not is_billable or requested == 0) \
                    and allow_local_zero_cost:
                return self._take(
                    state, project_id, task_id, run_id, reservation_id,
                    str(estimated_amount), reserved_at, expires_at,
                    provider_request_ref, warning,
                    "local zero-marginal-cost work continues per policy",
                    provider_id or "",
                )
            incident = self._record_incident_locked(
                state, task_id, run_id, reserved_at,
                "%s: project %s task %s run %s requested %s %s "
                "would exceed hard %s %s (spent %s, reserved %s)"
                % (BUDGET_BREACH_WORDS, project_id, task_id, run_id,
                   estimated_amount, state.currency, state.hard_limit,
                   state.currency, state.spent, state.reserved),
                root_cause="hard-limit admission refused",
            )
            raise BudgetBlockedError(
                incident.description + " [BUDGET_HARD_BLOCKED]")

    def _take(self, state, project_id, task_id, run_id, reservation_id,
              estimated_amount, reserved_at, expires_at,
              provider_request_ref, warning, message, provider_id=""):
        if reservation_id in self._reservations:
            return ReserveResult(
                ok=True, reservation=self._reservations[reservation_id],
                warning=warning, message="reservation already held",
            )
        reservation = BudgetReservation(
            reservation_id=reservation_id, project_id=project_id,
            task_id=task_id, run_id=run_id,
            estimated_amount=estimated_amount, reserved_at=reserved_at,
            expires_at=expires_at, status="ACTIVE",
            provider_request_ref=provider_request_ref,
            provider_id=provider_id or "",
        )
        self._reservations[reservation_id] = reservation
        state.reserved = str(_dec(state.reserved) + _dec(estimated_amount))
        self._persist()
        return ReserveResult(
            ok=True, reservation=reservation, warning=warning, message=message)

    # -- settlement --------------------------------------------------------
    def settle(self, settlement: BudgetSettlement) -> BudgetSettlement:
        """Frozen facade: BudgetSettlement (Mapping/None tolerated positionally).

        Frozen `settlement` carries reservation_id/provider_request_ref/
        source/settled_at/actual_amount/provider_usage_evidence_ref;
        missing settled_at falls back to utc now. Delegates to _settle_impl.
        """
        if settlement is None:
            raise ValueError(
                "settle needs a BudgetSettlement")
        if isinstance(settlement, Mapping):
            data = dict(settlement)
        elif hasattr(settlement, "reservation_id"):
            data = {}
            for key in _SETTLE_FROZEN_FIELDS:
                if hasattr(settlement, key):
                    data[key] = getattr(settlement, key)
        else:
            raise ValueError(
                "settle settlement must be a BudgetSettlement, "
                "a mapping, or None (got %s)" % type(settlement).__name__)
        if not data.get("reservation_id"):
            raise ValueError("settle settlement is missing 'reservation_id'")
        if not data.get("source"):
            raise ValueError("settle settlement is missing 'source'")
        if not data.get("settled_at"):
            data["settled_at"] = _utcnow_z()
        return self._settle_impl(
            reservation_id=data["reservation_id"],
            provider_request_ref=data.get("provider_request_ref", ""),
            source=data["source"], settled_at=data["settled_at"],
            actual_amount=data.get("actual_amount"),
            provider_usage_evidence_ref=data.get(
                "provider_usage_evidence_ref"),
        )

    def _settle_impl(self, reservation_id, provider_request_ref, source,
                     settled_at, actual_amount=None,
                     provider_usage_evidence_ref=None):
        """Settle a reservation; duplicates by dedupe key are refused."""
        with self._lock:
            key = dedupe_key_for(
                reservation_id, provider_usage_evidence_ref,
                provider_request_ref)
            existing = self._settlements.get(key)
            if existing is not None:
                raise DuplicateSettlementError(
                    "duplicate settlement refused for dedupe key %s "
                    "[DUPLICATE_SETTLEMENT_REFUSED]" % key,
                    existing=existing,
                )
            reservation = self._reservations[reservation_id]
            if reservation.status == "SETTLED":
                prior = None
                for stl in self._settlements.values():
                    if stl.reservation_id == reservation_id \
                            and stl.status == "SETTLED":
                        prior = stl
                        break
                raise DuplicateSettlementError(
                    "duplicate settlement refused for reservation %s "
                    "(already settled) [DUPLICATE_SETTLEMENT_REFUSED]"
                    % reservation_id,
                    existing=prior,
                )
            state = self._states[reservation.project_id]
            self._settlement_seq += 1
            settlement_id = "stl-%s-%d" % (reservation_id, self._settlement_seq)
            if provider_usage_evidence_ref is None:
                settlement = BudgetSettlement(
                    settlement_id=settlement_id,
                    reservation_id=reservation_id,
                    provider_usage_evidence_ref=None,
                    provider_request_ref=provider_request_ref,
                    dedupe_key=key, actual_amount=None, difference=None,
                    status="PENDING_RECONCILIATION", settled_at=None,
                    source=source,
                )
                self._settlements[key] = settlement
                self._persist()
                return settlement
            actual = str(actual_amount)
            difference = str(_dec(reservation.estimated_amount) - _dec(actual))
            settlement = BudgetSettlement(
                settlement_id=settlement_id, reservation_id=reservation_id,
                provider_usage_evidence_ref=provider_usage_evidence_ref,
                provider_request_ref=provider_request_ref,
                dedupe_key=key, actual_amount=actual, difference=difference,
                status="SETTLED", settled_at=settled_at, source=source,
            )
            self._settlements[key] = settlement
            reservation.status = "SETTLED"
            state.spent = str(_dec(state.spent) + _dec(actual))
            state.reserved = str(
                _dec(state.reserved) - _dec(reservation.estimated_amount))
            self._persist()
            return settlement

    def release(self, reservation_id, reason, now=""):
        with self._lock:
            reservation = self._reservations[reservation_id]
            if reservation.status in ("SETTLED", "RELEASED", "EXPIRED"):
                return reservation
            state = self._states[reservation.project_id]
            reservation.status = "RELEASED"
            state.reserved = str(
                _dec(state.reserved) - _dec(reservation.estimated_amount))
            self._persist()
            return reservation

    # -- restart recovery ---------------------------------------------------
    def reconcile_on_restart(self, project_id: str) -> List[BudgetSettlement]:
        """Frozen facade: no-new-evidence reconcile scoped to one project.

        Releases expired reservations and never double-settles; returns
        the List[BudgetSettlement] settled for that project. Evidence-driven
        recovery lives in _reconcile_impl.
        """
        _summary, settled = self._reconcile_impl(
            {}, _utcnow_z(), project_scope=project_id)
        return settled

    def _reconcile_impl(self, evidence_by_reservation, now,
                        project_scope=None):
        """Settle with evidence, release expired unused, never double-settle."""
        summary = {"settled": [], "released": [], "held": []}
        settled = []
        with self._lock:
            actives = [
                r for r in self._reservations.values()
                if r.status in ("ACTIVE", "CREATED")
            ]
        for reservation in sorted(actives, key=lambda r: r.reservation_id):
            if project_scope is not None \
                    and reservation.project_id != project_scope:
                continue
            evidence = evidence_by_reservation.get(reservation.reservation_id)
            if evidence is not None:
                if not evidence.get("provider_request_ref") \
                        or not evidence.get("source"):
                    raise ValueError(
                        "recovery evidence for reservation %s needs "
                        "provider_request_ref and source"
                        % reservation.reservation_id)
                try:
                    record = self._settle_impl(
                        reservation_id=reservation.reservation_id,
                        provider_request_ref=evidence["provider_request_ref"],
                        source=evidence["source"],
                        settled_at=now,
                        actual_amount=evidence.get("actual_amount"),
                        provider_usage_evidence_ref=evidence.get(
                            "provider_usage_evidence_ref"),
                    )
                except DuplicateSettlementError:
                    record = None
                status = self._reservations[reservation.reservation_id].status
                if status == "SETTLED":
                    summary["settled"].append(reservation.reservation_id)
                    if record is not None and record.status == "SETTLED":
                        settled.append(record)
                else:
                    summary["held"].append(reservation.reservation_id)
            elif reservation.expires_at <= now:
                self.release(reservation.reservation_id, "expired unused", now)
                summary["released"].append(reservation.reservation_id)
            else:
                summary["held"].append(reservation.reservation_id)
        return summary, settled

    def list_incidents(self, project_id):
        with self._lock:
            return [i for i in self._incidents if i.project_id == project_id]

    def get_reservation(self, reservation_id):
        with self._lock:
            return self._reservations[reservation_id]
