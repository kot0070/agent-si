"""Usage/cost telemetry: K04 builders over frozen K13 schemas (PRODUCT_SPEC 11/55).

Rules honored here: measurements travel as MetricRecords (never inline in
the TelemetryEvent envelope); value+unit+state+source are required at write;
cost arrives only via CostCalculator over a PricingSnapshot (UNAVAILABLE
without one, never zero); AI prose is never telemetry evidence; historical
cost reproduces from the original snapshot; RoutingDecision.reason carries
the cost/budget why-text inputs.
"""
from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field


class MetricState:
    MEASURED = "MEASURED"
    CALCULATED = "CALCULATED"
    ESTIMATED = "ESTIMATED"
    INFERRED = "INFERRED"
    UNAVAILABLE = "UNAVAILABLE"

    ALL = frozenset({MEASURED, CALCULATED, ESTIMATED, INFERRED, UNAVAILABLE})


# Provenance values that are AI prose, never telemetry evidence.
REJECTED_SOURCES = frozenset({"ai_prose", "ai_summary", "llm_narrative", "model_memory"})

# Frozen event-type vocabulary: unknown event_type values are rejected, never
# invented silently; new types arrive as a new vocabulary version.
EVENT_TYPES = frozenset({
    "run_started",
    "run_completed",
    "attempt_started",
    "attempt_completed",
    "routing_decided",
    "budget_reserved",
    "budget_settled",
    "budget_blocked",
    "measurement_recorded",
    "cost_calculated",
    "verification_completed",
    "audit_completed",
    "retry_scheduled",
    "fallback_taken",
    "incident_recorded",
})


def _canonical_hash(payload):
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


@dataclass
class PricingSnapshot:
    pricing_snapshot_id: str
    provider_id: str
    model_id: str
    currency: str
    effective_at: str
    source: str
    input_token_price: str | None = None
    output_token_price: str | None = None
    cached_token_price: str | None = None
    reasoning_token_price: str | None = None
    request_price: str | None = None
    other_rules: list = field(default_factory=list)
    created_at: str = ""
    hash: str = ""

    def to_dict(self):
        return {
            "pricing_snapshot_id": self.pricing_snapshot_id,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "currency": self.currency,
            "effective_at": self.effective_at,
            "source": self.source,
            "input_token_price": self.input_token_price,
            "output_token_price": self.output_token_price,
            "cached_token_price": self.cached_token_price,
            "reasoning_token_price": self.reasoning_token_price,
            "request_price": self.request_price,
            "other_rules": list(self.other_rules),
            "created_at": self.created_at,
            "hash": self.hash,
        }


def make_snapshot(pricing_snapshot_id, provider_id, model_id, currency,
                  effective_at, source, created_at, input_token_price=None,
                  output_token_price=None, cached_token_price=None,
                  reasoning_token_price=None, request_price=None,
                  other_rules=None):
    body = {
        "pricing_snapshot_id": pricing_snapshot_id,
        "provider_id": provider_id,
        "model_id": model_id,
        "currency": currency,
        "effective_at": effective_at,
        "source": source,
        "input_token_price": input_token_price,
        "output_token_price": output_token_price,
        "cached_token_price": cached_token_price,
        "reasoning_token_price": reasoning_token_price,
        "request_price": request_price,
        "other_rules": list(other_rules or []),
        "created_at": created_at,
    }
    snapshot = PricingSnapshot(hash=_canonical_hash(body), **body)
    with _REGISTRY_LOCK:
        _SNAPSHOT_REGISTRY[snapshot.pricing_snapshot_id] = snapshot
    return snapshot


@dataclass
class MetricRecord:
    metric_id: str
    project_id: str
    task_id: str
    run_id: str
    metric_name: str
    value: str | int | float | None
    unit: str
    state: str
    source: str
    recorded_at: str

    def to_dict(self):
        return {
            "metric_id": self.metric_id,
            "project_id": self.project_id,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "metric_name": self.metric_name,
            "value": self.value,
            "unit": self.unit,
            "state": self.state,
            "source": self.source,
            "recorded_at": self.recorded_at,
        }


def make_metric(metric_id, project_id, task_id, run_id, metric_name, value,
                unit, state, source, recorded_at):
    """Write-time validation: value+unit+state+source required.

    value may be None only when state is UNAVAILABLE (unknown cost is never
    recorded as zero). AI prose is never accepted as source.
    """
    if state not in MetricState.ALL:
        raise ValueError("unknown metric state %r" % (state,))
    if not unit or not state or not source:
        raise ValueError("unit, state and source are required at write time")
    if source in REJECTED_SOURCES:
        raise ValueError("AI prose is never telemetry evidence: %r" % (source,))
    if value is None and state != MetricState.UNAVAILABLE:
        raise ValueError("value is required unless state is UNAVAILABLE")
    return MetricRecord(
        metric_id=metric_id, project_id=project_id, task_id=task_id,
        run_id=run_id, metric_name=metric_name, value=value, unit=unit,
        state=state, source=source, recorded_at=recorded_at,
    )


class MetricLog:
    """Append-only metric store; duplicate metric_id returns the stored row."""

    def __init__(self):
        self._lock = threading.Lock()
        self._rows = {}

    def append(self, data):
        with self._lock:
            if data["metric_id"] in self._rows:
                return self._rows[data["metric_id"]]
            record = make_metric(**data)
            self._rows[record.metric_id] = record
            return record

    def get(self, metric_id):
        with self._lock:
            return self._rows[metric_id]


_SNAPSHOT_REGISTRY = {}
_USAGE_REGISTRY = {}
_REGISTRY_LOCK = threading.Lock()

_TOKEN_NAMES = ("input_tokens", "output_tokens", "cached_tokens",
                "reasoning_tokens", "requests")


def register_usage(usage_ref, usage=None, input_tokens=0, output_tokens=0,
                   cached_tokens=0, reasoning_tokens=0, requests=0):
    """Register token usage under a usage ref for frozen cost resolution."""
    tokens = {}
    if isinstance(usage, Mapping):
        for name in _TOKEN_NAMES:
            if name in usage:
                tokens[name] = usage[name]
    tokens.setdefault("input_tokens", input_tokens)
    tokens.setdefault("output_tokens", output_tokens)
    tokens.setdefault("cached_tokens", cached_tokens)
    tokens.setdefault("reasoning_tokens", reasoning_tokens)
    tokens.setdefault("requests", requests)
    with _REGISTRY_LOCK:
        _USAGE_REGISTRY[usage_ref] = dict(tokens)
    return usage_ref


def _is_pricing_snapshot(obj):
    return isinstance(obj, PricingSnapshot) or (
        hasattr(obj, "pricing_snapshot_id")
        and hasattr(obj, "input_token_price")
        and hasattr(obj, "currency"))


@dataclass
class CostLine:
    amount: str | None
    currency: str
    pricing_snapshot_id: str | None


def _snapshot_total(snapshot, tokens):
    from decimal import Decimal

    def priced(amount, price, name):
        if amount and price is None:
            raise ValueError("no %s in snapshot %s; cost stays unknown"
                             % (name, snapshot.pricing_snapshot_id))
        return Decimal(str(price or "0")) * Decimal(str(amount or 0))

    total = (
        priced(tokens.get("input_tokens", 0),
               snapshot.input_token_price, "input_token_price")
        + priced(tokens.get("output_tokens", 0),
                 snapshot.output_token_price, "output_token_price")
        + priced(tokens.get("cached_tokens", 0),
                 snapshot.cached_token_price, "cached_token_price")
        + priced(tokens.get("reasoning_tokens", 0),
                 snapshot.reasoning_token_price, "reasoning_token_price")
        + priced(tokens.get("requests", 0),
                 snapshot.request_price, "request_price")
    )
    return str(total.quantize(Decimal("0.000001")))


class CostCalculator:
    """Cost only via a PricingSnapshot; UNAVAILABLE without one, never zero."""

    @staticmethod
    def _calculate_legacy(usage_ref, pricing_snapshot_id=None, *args, **kwargs):
        # Legacy: snapshot object + token kwargs/positionals -> str total.
        if _is_pricing_snapshot(usage_ref):
            snapshot = usage_ref
            positionals = []
            if pricing_snapshot_id is not None:
                positionals.append(pricing_snapshot_id)
            positionals.extend(args)
            numbers = [v for v in positionals
                       if isinstance(v, (int, float))
                       and not isinstance(v, bool)]
            tokens = {}
            for index, name in enumerate(_TOKEN_NAMES):
                if name in kwargs:
                    tokens[name] = kwargs[name]
                elif index < len(numbers):
                    tokens[name] = numbers[index]
                else:
                    tokens[name] = 0
            return _snapshot_total(snapshot, tokens)
        if usage_ref is None:
            alias = kwargs.get("snapshot", kwargs.get("pricing_snapshot"))
            if _is_pricing_snapshot(alias):
                tokens = {name: kwargs.get(name, 0) for name in _TOKEN_NAMES}
                return _snapshot_total(alias, tokens)
            raise ValueError(
                "no pricing snapshot; cost stays unknown "
                "(UNAVAILABLE, never zero)")
        # Direct snapshot object as second arg with a registered usage ref.
        if isinstance(usage_ref, str) \
                and _is_pricing_snapshot(pricing_snapshot_id):
            snapshot = pricing_snapshot_id
            with _REGISTRY_LOCK:
                stored = dict(_USAGE_REGISTRY.get(usage_ref) or {})
            known = usage_ref in _USAGE_REGISTRY
            for name in _TOKEN_NAMES:
                if name in kwargs:
                    stored[name] = kwargs[name]
            if not known and not any(name in kwargs
                                     for name in _TOKEN_NAMES):
                raise ValueError(
                    "no usage %r; cost stays unknown "
                    "(UNAVAILABLE, never zero)" % (usage_ref,))
            return CostLine(
                amount=_snapshot_total(snapshot, stored),
                currency=snapshot.currency,
                pricing_snapshot_id=snapshot.pricing_snapshot_id)
        # Mapping usage with a snapshot id.
        if isinstance(usage_ref, Mapping):
            pid = pricing_snapshot_id
            if not isinstance(pid, str):
                pid = kwargs.get("pricing_snapshot_id")
            if not isinstance(pid, str) or not pid:
                raise ValueError(
                    "no pricing snapshot; cost stays unknown "
                    "(UNAVAILABLE, never zero)")
            with _REGISTRY_LOCK:
                snapshot = _SNAPSHOT_REGISTRY.get(pid)
            if snapshot is None:
                raise ValueError(
                    "no pricing snapshot %r; cost stays unknown "
                    "(UNAVAILABLE, never zero)" % (pid,))
            stored = {name: usage_ref[name] for name in _TOKEN_NAMES
                      if name in usage_ref}
            for name in _TOKEN_NAMES:
                if name in kwargs:
                    stored[name] = kwargs[name]
            return CostLine(
                amount=_snapshot_total(snapshot, stored),
                currency=snapshot.currency,
                pricing_snapshot_id=snapshot.pricing_snapshot_id)
        # Frozen: str usage ref + str snapshot id via registries -> CostLine.
        if isinstance(usage_ref, str):
            pid = pricing_snapshot_id
            if not isinstance(pid, str):
                pid = kwargs.get("pricing_snapshot_id")
            if not isinstance(pid, str) or not pid:
                raise ValueError(
                    "no pricing snapshot; cost stays unknown "
                    "(UNAVAILABLE, never zero)")
            with _REGISTRY_LOCK:
                snapshot = _SNAPSHOT_REGISTRY.get(pid)
                stored = dict(_USAGE_REGISTRY.get(usage_ref) or {})
                known = usage_ref in _USAGE_REGISTRY
            if snapshot is None:
                raise ValueError(
                    "no pricing snapshot %r; cost stays unknown "
                    "(UNAVAILABLE, never zero)" % (pid,))
            for name in _TOKEN_NAMES:
                if name in kwargs:
                    stored[name] = kwargs[name]
            if not known and not any(name in kwargs
                                     for name in _TOKEN_NAMES):
                raise ValueError(
                    "no usage %r; cost stays unknown "
                    "(UNAVAILABLE, never zero)" % (usage_ref,))
            return CostLine(
                amount=_snapshot_total(snapshot, stored),
                currency=snapshot.currency,
                pricing_snapshot_id=snapshot.pricing_snapshot_id)
        raise ValueError(
            "no pricing snapshot; cost stays unknown "
            "(UNAVAILABLE, never zero)")

    @staticmethod
    def calculate(usage_ref: str, pricing_snapshot_id: str) -> CostLine:
        """Frozen facade: registry str usage ref + str snapshot id.

        Resolves both through the registries; anything else raises the
        existing UNAVAILABLE ValueErrors (never zero).
        """
        if not isinstance(pricing_snapshot_id, str) \
                or not pricing_snapshot_id:
            raise ValueError(
                "no pricing snapshot; cost stays unknown "
                "(UNAVAILABLE, never zero)")
        if not isinstance(usage_ref, str) or not usage_ref:
            raise ValueError(
                "no usage %r; cost stays unknown "
                "(UNAVAILABLE, never zero)" % (usage_ref,))
        with _REGISTRY_LOCK:
            snapshot = _SNAPSHOT_REGISTRY.get(pricing_snapshot_id)
            stored = dict(_USAGE_REGISTRY.get(usage_ref) or {})
            known = usage_ref in _USAGE_REGISTRY
        if snapshot is None:
            raise ValueError(
                "no pricing snapshot %r; cost stays unknown "
                "(UNAVAILABLE, never zero)" % (pricing_snapshot_id,))
        if not known:
            raise ValueError(
                "no usage %r; cost stays unknown "
                "(UNAVAILABLE, never zero)" % (usage_ref,))
        return CostLine(
            amount=_snapshot_total(snapshot, stored),
            currency=snapshot.currency,
            pricing_snapshot_id=snapshot.pricing_snapshot_id)

    @classmethod
    def cost_metric(cls, metric_id, project_id, task_id, run_id, metric_name,
                    snapshot, source, recorded_at, input_tokens=0,
                    output_tokens=0, cached_tokens=0, reasoning_tokens=0,
                    requests=0):
        return make_metric(
            metric_id=metric_id, project_id=project_id, task_id=task_id,
            run_id=run_id, metric_name=metric_name,
            value=cls._calculate_legacy(
                snapshot, input_tokens, output_tokens, cached_tokens,
                reasoning_tokens, requests),
            unit=snapshot.currency, state=MetricState.CALCULATED,
            source="%s+pricing_snapshot:%s" % (source, snapshot.pricing_snapshot_id),
            recorded_at=recorded_at,
        )

    @staticmethod
    def unavailable_cost(metric_id, project_id, task_id, run_id, metric_name,
                         unit, source, recorded_at):
        return make_metric(
            metric_id=metric_id, project_id=project_id, task_id=task_id,
            run_id=run_id, metric_name=metric_name, value=None, unit=unit,
            state=MetricState.UNAVAILABLE, source=source,
            recorded_at=recorded_at,
        )


def build_telemetry_event(event_id, project_id, timestamp, event_type,
                           task_id=None, run_id=None, attempt_id=None,
                           subtask_id=None, parent_id=None, role=None,
                           task_class=None, risk=None, state=None, route=None,
                           split_strategy=None, provider=None, model=None,
                           provider_instance=None, retry=None,
                           verification_ref=None, audit_ref=None,
                           re_execution=None, error_ref=None,
                           fallback_reason=None, capability_rule=None,
                           capability_evidence_ref=None,
                           routing_decision_ref=None, routing_snapshot_id=None,
                           resource_state_ref=None, metric_refs=None,
                           final_status=None):
    """TelemetryEvent envelope builder (NOT a multi-metric record)."""
    if not event_id or not project_id or not timestamp:
        raise ValueError("event_id, project_id and timestamp are required")
    if event_type not in EVENT_TYPES:
        raise ValueError("unknown event_type %r" % (event_type,))
    return {
        "event_id": event_id,
        "project_id": project_id,
        "timestamp": timestamp,
        "task_id": task_id,
        "run_id": run_id,
        "attempt_id": attempt_id,
        "subtask_id": subtask_id,
        "parent_id": parent_id,
        "role": role,
        "task_class": task_class,
        "risk": risk,
        "state": state,
        "route": route,
        "split_strategy": split_strategy,
        "provider": provider,
        "model": model,
        "provider_instance": provider_instance,
        "event_type": event_type,
        "retry": retry,
        "verification_ref": verification_ref,
        "audit_ref": audit_ref,
        "re-execution": re_execution,
        "error_ref": error_ref,
        "fallback_reason": fallback_reason,
        "capability_rule": capability_rule,
        "capability_evidence_ref": capability_evidence_ref,
        "routing_decision_ref": routing_decision_ref,
        "routing_snapshot_id": routing_snapshot_id,
        "resource_state_ref": resource_state_ref,
        "metric_refs": list(metric_refs or []),
        "final_status": final_status,
    }


class TelemetryEventLog:
    """Append-only envelope store; duplicate event_id returns the stored row."""

    def __init__(self):
        self._lock = threading.Lock()
        self._rows = {}

    def append(self, event):
        with self._lock:
            if event["event_id"] in self._rows:
                return self._rows[event["event_id"]]
            if event["event_type"] not in EVENT_TYPES:
                raise ValueError("unknown event_type %r" % (event["event_type"],))
            self._rows[event["event_id"]] = event
            return event

    def get(self, event_id):
        with self._lock:
            return self._rows[event_id]


def build_routing_reason(estimated_cost, currency, budget_remaining,
                         budget_hard_limit, route, extra_text=""):
    """RoutingDecision.reason why-text carrying the cost/budget inputs."""
    return (
        "route %s selected; estimated_cost %s %s; budget_remaining %s %s; "
        "budget_hard_limit %s %s%s"
        % (route, estimated_cost, currency, budget_remaining, currency,
           budget_hard_limit, currency,
           ("; " + extra_text) if extra_text else "")
    )


ROLE_MODES = frozenset({"PINNED", "pool", "AUTO"})


@dataclass
class RoleModelProfile:
    role: str
    project_id: str
    mode: str
    provider: str
    model: str
    binding: str
    version: int
    hash: str

    def __post_init__(self):
        if self.mode not in ROLE_MODES:
            raise ValueError("unknown role mode %r" % (self.mode,))


MANAGER_BINDINGS = frozenset({"DEFAULT", "HARD_LOCK"})


@dataclass
class DefaultManagerProfile:
    profile_id: str
    version: int
    provider: str
    model: str
    binding: str
    hash: str

    def __post_init__(self):
        if self.binding not in MANAGER_BINDINGS:
            raise ValueError("unknown manager binding %r" % (self.binding,))

    def with_change(self, reason, **changes):
        if not reason:
            raise ValueError("profile change needs a recorded reason")
        body = {
            "profile_id": self.profile_id,
            "version": self.version + 1,
            "provider": changes.get("provider", self.provider),
            "model": changes.get("model", self.model),
            "binding": changes.get("binding", self.binding),
        }
        if body["binding"] not in MANAGER_BINDINGS:
            raise ValueError("unknown manager binding %r" % (body["binding"],))
        return DefaultManagerProfile(hash=_canonical_hash(body), **body)


@dataclass
class SecretRef:
    secret_id: str
    provider_id: str
    type: str
    scope: str
    source: str
    created_at: str
    last_rotated_at: str


class SecretStore:
    """OS-store stand-in: refs never carry raw secrets; deletion removes the
    store entry; the audit log records entry names only, never values."""

    def __init__(self):
        self._lock = threading.Lock()
        self._values = {}
        self._refs = {}
        self._audit = []

    def put(self, secret_id, provider_id, type, scope, source, created_at,
            last_rotated_at, secret_value):
        with self._lock:
            self._values[secret_id] = secret_value
            self._refs[secret_id] = SecretRef(
                secret_id=secret_id, provider_id=provider_id, type=type,
                scope=scope, source=source, created_at=created_at,
                last_rotated_at=last_rotated_at,
            )
            self._audit.append("put:%s" % secret_id)
            return self._refs[secret_id]

    def ref(self, secret_id):
        with self._lock:
            return self._refs[secret_id]

    def delete(self, secret_id):
        with self._lock:
            del self._values[secret_id]
            del self._refs[secret_id]
            self._audit.append("delete:%s" % secret_id)

    def audit_log(self):
        with self._lock:
            return list(self._audit)
