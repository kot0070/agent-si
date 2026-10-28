"""Helper-provider outage observe: read-only service map plus outage linkage.

K04 side of M-P2-68 (helper-provider outage telemetry; small audits on free
models) plus R-366 (declared services: check types, UP/DOWN/DEGRADED,
observe + notify, usage from metadata, outage linkage).

Read library: no HTTP surface, no body-carried identity. Identity arrives
as explicit query-style arguments (project_id=..., session_token=...);
this module defines no body parameter, so body-carried identity cannot
reach it. The session token travels in query-style arguments, never in a
body (same rule as the roles chat-model route).

K08 seam: two injected callables (journal_append, notify) with no watcher
import. An unwired seam reads fail-closed DOWN plus a local incident row.
"""
from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from agent_si.budget import telemetry as _telemetry
from agent_si.budget.gate import BudgetBlockedError
from agent_si.budget.telemetry import (
    CostCalculator,
    CostLine,
    MetricState,
    build_routing_reason,
    register_usage,
)


SERVICE_STATUSES = ("UP", "DEGRADED", "DOWN")

_REGISTRY_TO_SERVICE = {
    "ONLINE": "UP",
    "DEGRADED": "DEGRADED",
    "OFFLINE": "DOWN",
    "UNKNOWN": "DOWN",
}

UNKNOWN_HEALTH_REASON = "unknown-health"
SEAM_DOWN_REASON = "seam-down"
PROVIDER_OUTAGE_REASON = "provider-outage"

_TOKEN_NAMES = ("input_tokens", "output_tokens", "cached_tokens",
                "reasoning_tokens", "requests")

_PRICE_FIELDS = ("input_token_price", "output_token_price",
                 "cached_token_price", "reasoning_token_price",
                 "request_price")


def _require_query_identity(project_id, session_token):
    """Query-style identity guard: explicit non-empty project plus token."""
    if not (isinstance(project_id, str) and project_id.strip()):
        raise ValueError("observe needs project_id as a query-style argument")
    if not (isinstance(session_token, str) and session_token.strip()):
        raise ValueError("observe needs session_token as a query-style "
                         "argument (never in a body)")


def map_service_status(registry_status):
    """Map one registry health status to a service status, fail-closed.

    ONLINE -> UP, DEGRADED stays, OFFLINE -> DOWN, UNKNOWN -> DOWN with
    reason unknown-health. Anything unrecognised maps DOWN the same way.
    """
    if not isinstance(registry_status, str):
        return ("DOWN", UNKNOWN_HEALTH_REASON)
    service = _REGISTRY_TO_SERVICE.get(registry_status)
    if service is None:
        return ("DOWN", UNKNOWN_HEALTH_REASON)
    if registry_status == "UNKNOWN":
        return (service, UNKNOWN_HEALTH_REASON)
    return (service, "")


def _service_refs(services):
    """Yield (provider_id, instance_id) pairs from pairs or mappings."""
    for item in services or ():
        if isinstance(item, Mapping):
            yield (item.get("provider_id"), item.get("instance_id"))
        else:
            provider_id, instance_id = item
            yield (provider_id, instance_id)


def observe_provider(health_log, provider_id, instance_id, *,
                     project_id, session_token):
    """Read one service: registry health mapped to UP/DEGRADED/DOWN."""
    _require_query_identity(project_id, session_token)
    registry_status = health_log.status_of(provider_id, instance_id)
    service, reason = map_service_status(registry_status)
    return {
        "project_id": project_id,
        "provider_id": provider_id,
        "instance_id": instance_id,
        "registry_status": registry_status,
        "service": service,
        "reason": reason,
    }


def observe_services(health_log, services, *, project_id, session_token):
    """Read several services; each row carries its own fail-closed map."""
    _require_query_identity(project_id, session_token)
    return [
        observe_provider(
            health_log, provider_id, instance_id,
            project_id=project_id, session_token=session_token)
        for provider_id, instance_id in _service_refs(services)
    ]


def _is_zero_price(snapshot):
    """Zero-price snapshot: at least one price present, all present zero."""
    if snapshot is None:
        return False
    if isinstance(snapshot, Mapping):
        def get(name):
            return snapshot.get(name)
    else:
        def get(name):
            return getattr(snapshot, name, None)
    seen = False
    for name in _PRICE_FIELDS:
        value = get(name)
        if value is None:
            continue
        seen = True
        try:
            if Decimal(str(value)) != 0:
                return False
        except (ValueError, ArithmeticError):
            return False
    return seen


def pick_free_audit_model(candidates, *, project_id, session_token,
                          budget_remaining="0", budget_hard_limit="0",
                          currency="USD", route="AUDIT"):
    """Route a small audit to a zero-price snapshot candidate.

    Candidates arrive from the caller (each with provider_id, model and a
    pricing_snapshot); the pick is the first zero-price candidate in
    (provider_id, model) order. The reason is recorded through
    build_routing_reason. Fail-closed: no zero-price candidate raises,
    never a silent paid pick.
    """
    _require_query_identity(project_id, session_token)
    rows = [c for c in (candidates or []) if isinstance(c, Mapping)]
    free = [c for c in rows if _is_zero_price(c.get("pricing_snapshot"))]
    free = sorted(free, key=lambda c: (str(c.get("provider_id")),
                                       str(c.get("model"))))
    if not free:
        raise ValueError("no zero-price audit candidate for project %r "
                         "(fail-closed; never a silent paid pick)"
                         % (project_id,))
    pick = free[0]
    snapshot = pick.get("pricing_snapshot")
    if isinstance(snapshot, Mapping):
        snapshot_id = snapshot.get("pricing_snapshot_id")
    else:
        snapshot_id = getattr(snapshot, "pricing_snapshot_id", "")
    reason = build_routing_reason(
        "0", currency, budget_remaining, budget_hard_limit, route,
        "free audit model %s/%s (zero-price snapshot %s; %d free of %d "
        "candidates)" % (pick.get("provider_id"), pick.get("model"),
                         snapshot_id, len(free), len(rows)),
    )
    return {"pick": dict(pick), "reason": reason}


def _resolve_outage_cost(outage_id, usage, pricing_snapshot):
    """Usage from provider metadata through CostCalculator, else UNAVAILABLE.

    Unknown cost is never recorded as zero: no usage metadata or no pricing
    snapshot (or an unresolvable one) yields amount None, never "0".
    """
    tokens = {}
    if isinstance(usage, Mapping):
        for name in _TOKEN_NAMES:
            if name in usage:
                tokens[name] = usage[name]
    if not tokens or pricing_snapshot is None:
        return {"amount": None, "currency": "USD",
                "pricing_snapshot_id": None,
                "state": MetricState.UNAVAILABLE}
    usage_ref = "outage-usage-%s" % outage_id
    register_usage(usage_ref, tokens)
    try:
        if isinstance(pricing_snapshot, str):
            line = CostCalculator.calculate(usage_ref, pricing_snapshot)
        else:
            amount = CostCalculator._calculate_legacy(
                pricing_snapshot, **tokens)
            line = CostLine(
                amount=amount,
                currency=getattr(pricing_snapshot, "currency", "USD"),
                pricing_snapshot_id=getattr(
                    pricing_snapshot, "pricing_snapshot_id", ""),
            )
    except (ValueError, ArithmeticError):
        return {"amount": None, "currency": "USD",
                "pricing_snapshot_id": None,
                "state": MetricState.UNAVAILABLE}
    return {"amount": line.amount, "currency": line.currency,
            "pricing_snapshot_id": line.pricing_snapshot_id,
            "state": MetricState.CALCULATED}


def link_outage(*, outage_id, provider_id, instance_id, project_id, task_id,
                run_id, timestamp, telemetry_log, gate, usage=None,
                pricing_snapshot=None, journal_append=None, notify=None,
                session_token):
    """Record one outage linkage: telemetry event plus budget incident row.

    Writes one incident_recorded telemetry event plus one budget incident
    row sharing the outage id (event_id == incident_id == outage_id), with
    usage taken from provider metadata and resolved through CostCalculator
    (or UNAVAILABLE, never zero). Then calls the K08 seam (journal_append
    plus notify, injected; no watcher import). An unwired seam reads
    fail-closed DOWN plus the local incident row; the return always carries
    service DOWN.
    """
    _require_query_identity(project_id, session_token)
    if not (isinstance(outage_id, str) and outage_id):
        raise ValueError("link_outage needs a non-empty outage_id")
    seam_ok = callable(journal_append) and callable(notify)
    reason = PROVIDER_OUTAGE_REASON if seam_ok else SEAM_DOWN_REASON
    cost = _resolve_outage_cost(outage_id, usage, pricing_snapshot)
    event = _telemetry.build_incident_event(
        outage_id=outage_id, project_id=project_id, timestamp=timestamp,
        task_id=task_id, run_id=run_id, provider=provider_id,
        detail="helper-provider outage: %s/%s service DOWN "
               "(usage snapshot %s)"
               % (provider_id, instance_id,
                  cost["pricing_snapshot_id"] or "UNAVAILABLE"),
    )
    telemetry_log.append(event)
    incident = gate.record_provider_incident(
        project_id=project_id, task_id=task_id, run_id=run_id,
        timestamp=timestamp, incident_id=outage_id,
        description="helper-provider outage %s: %s/%s service DOWN "
                    "(telemetry %s shares this outage id)"
                    % (outage_id, provider_id, instance_id, outage_id),
        root_cause="helper-provider outage linkage",
    )
    notified = False
    if seam_ok:
        journal_append({
            "kind": "provider_outage", "outage_id": outage_id,
            "project_id": project_id, "provider_id": provider_id,
            "instance_id": instance_id, "service": "DOWN",
        })
        notify({
            "outage_id": outage_id, "project_id": project_id,
            "provider_id": provider_id, "instance_id": instance_id,
            "service": "DOWN", "reason": reason,
        })
        notified = True
    return {
        "outage_id": outage_id, "project_id": project_id,
        "provider_id": provider_id, "instance_id": instance_id,
        "service": "DOWN", "reason": reason,
        "telemetry_event": event, "incident": incident.to_dict(),
        "cost": cost, "notified": notified,
    }


def reserve_checked(gate, request, service, *, override_ref=None,
                    timestamp=""):
    """Refuse billable reservations against a DOWN provider, fail-closed.

    Raises BudgetBlockedError plus one gate incident row, except under an
    explicitly authorized override (override_ref here or on the request).
    Non-billable (LOCAL route or is_billable False) requests pass through
    to the gate, which applies its own local policy. Returns the
    ReserveResult.
    """
    if not isinstance(request, Mapping):
        raise ValueError("reserve_checked needs the request as a mapping")
    effective_override = override_ref
    if effective_override is None:
        effective_override = request.get("override_ref")
    route = request.get("route", "CLOUD")
    billable = bool(request.get("is_billable", True)) and route != "LOCAL"
    if service == "DOWN" and billable and not effective_override:
        incident = gate.record_provider_incident(
            project_id=request.get("project_id"),
            task_id=request.get("task_id"), run_id=request.get("run_id"),
            timestamp=timestamp,
            description="billable reservation refused: provider %s service "
                        "DOWN (fail-closed; no authorized override)"
                        % (request.get("provider_id") or "unknown",),
            root_cause="provider-outage admission refused",
        )
        raise BudgetBlockedError(
            incident.description + " [PROVIDER_OUTAGE_BLOCKED]")
    if effective_override is not None:
        request = dict(request)
        request["override_ref"] = effective_override
    return gate.compare_and_reserve(request)
