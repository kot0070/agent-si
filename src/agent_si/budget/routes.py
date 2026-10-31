"""Budget HTTP surface (Lane B2): GET /api/v1/budget over ctx.budget_state."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Dict, Tuple

from agent_si.budget import gate as _budget_gate

#: Stable machine codes for the budget error bodies (M-WIRE L0B-08/11).
BUDGET_PROJECT_ID_REQUIRED = "BUDGET_PROJECT_ID_REQUIRED"
BUDGET_NOT_CONFIGURED = "BUDGET_NOT_CONFIGURED"
BUDGET_SESSION_TOKEN_REQUIRED = "BUDGET_SESSION_TOKEN_REQUIRED"
COMPENSATION_RESERVATION_ID_REQUIRED = "COMPENSATION_RESERVATION_ID_REQUIRED"


def _query_value(query, name, default=None):
    value = (query or {}).get(name, default)
    if isinstance(value, list):
        return value[0] if value else default
    return value


def _state_payload(state):
    if hasattr(state, "to_dict"):
        payload = dict(state.to_dict())
    elif isinstance(state, Mapping):
        payload = dict(state)
    else:
        payload = {key: value for key, value in vars(state).items()
                   if not key.startswith("_")}
    remaining = getattr(state, "remaining_derived", None)
    if remaining is not None and "remaining_derived" not in payload:
        payload["remaining_derived"] = remaining
    return payload


def get_budget(ctx, query, body) -> Tuple[int, Dict[str, Any]]:
    """Return (status, payload) for GET /api/v1/budget.

    Reads ctx.budget_state, which may be a BudgetGate (has get_state), a
    BudgetState-like object, or a mapping. Missing state is a 404.
    """
    query = query or {}
    params = body if isinstance(body, Mapping) else {}
    project_id = _query_value(query, "project_id", None)
    if project_id is None:
        project_id = params.get("project_id", "p1")
    if not isinstance(project_id, str) or not project_id:
        return 400, {"code": BUDGET_PROJECT_ID_REQUIRED,
                         "message": "project_id required"}
    budget_state = getattr(ctx, "budget_state", None)
    if budget_state is None:
        return 404, {"code": BUDGET_NOT_CONFIGURED, "message": "no budget state on file for %r" % (project_id,)}
    get_state = getattr(budget_state, "get_state", None)
    if callable(get_state):
        try:
            state = get_state(project_id)
        except (KeyError, LookupError):
            return 404, {"code": BUDGET_NOT_CONFIGURED, "message": "no budget state on file for %r"
                         % (project_id,)}
        return 200, {"project_id": project_id,
                     "budget": _state_payload(state)}
    if isinstance(budget_state, Mapping):
        node = dict(budget_state)
        if project_id in node and isinstance(node[project_id], Mapping):
            return 200, {"project_id": project_id,
                         "budget": dict(node[project_id])}
        if "project_id" in node:
            if node.get("project_id") != project_id:
                return 404, {"code": BUDGET_NOT_CONFIGURED, "message": "no budget state on file for %r"
                             % (project_id,)}
            return 200, {"project_id": project_id, "budget": node}
        return 404, {"code": BUDGET_NOT_CONFIGURED, "message": "no budget state on file for %r" % (project_id,)}
    state_project = getattr(budget_state, "project_id", None)
    if state_project is not None and state_project != project_id:
        return 404, {"code": BUDGET_NOT_CONFIGURED, "message": "no budget state on file for %r" % (project_id,)}
    return 200, {"project_id": project_id,
                 "budget": _state_payload(budget_state)}


def post_compensations(ctx, query, body) -> tuple[int, dict[str, Any]]:
    """Return (status, payload) for POST /api/v1/budget/compensations.

    ARCH-441 served entry: failed-gate compensation to terminal
    RELEASED with a persisted compensation_ref. Body carries
    reservation_id, reason and compensation_ref. Repeat of the same
    ref is idempotent; empty-ref, unknown-id and terminal
    (settled/expired, or a different ref on a released row) answers
    carry named error codes only. Drives the real BudgetGate on
    ctx.budget_state through the frozen keyword shape
    compensate(reservation_id, *, compensation_ref, reason).
    """
    _ = query
    token = getattr(ctx, "session_token", None)
    if isinstance(token, list):
        token = token[0] if token else None
    if not (isinstance(token, str) and token.strip()):
        return 401, {"code": BUDGET_SESSION_TOKEN_REQUIRED,
                     "message": "compensate refused: session token missing"}
    params = body if isinstance(body, Mapping) else {}
    reservation_id = params.get("reservation_id")
    if not isinstance(reservation_id, str) or not reservation_id:
        return 400, {"code": COMPENSATION_RESERVATION_ID_REQUIRED,
                     "message": "reservation_id required"}
    compensation_ref = params.get("compensation_ref")
    reason = params.get("reason") or ""
    gate = getattr(ctx, "budget_state", None)
    if gate is None:
        return 404, {"code": BUDGET_NOT_CONFIGURED,
                     "message": "no compensating budget gate on file"}
    compensate = getattr(gate, "compensate", None)
    if not callable(compensate):
        return 404, {"code": BUDGET_NOT_CONFIGURED,
                     "message": "no compensating budget gate on file"}
    if compensation_ref is None or str(compensation_ref) == "":
        return 400, {"code": _budget_gate.COMPENSATION_REF_REQUIRED,
                     "message": "compensate needs a non-empty "
                                "compensation_ref"}
    try:
        current = gate.get_reservation(reservation_id)
    except (KeyError, LookupError):
        return 404, {"code": _budget_gate.BUDGET_RESERVATION_NOT_FOUND,
                     "message": "no reservation on file for "
                                f"{reservation_id!r}"}
    if current.status in ("SETTLED", "EXPIRED") or (
            current.status == "RELEASED"
            and current.compensation_ref != str(compensation_ref)):
        return 409, {"code": _budget_gate.COMPENSATION_TERMINAL_REFUSED,
                     "message": f"reservation {reservation_id!r} is terminal "
                                f"({current.status}); compensation refused"}
    record = compensate(
        reservation_id, compensation_ref=compensation_ref, reason=reason)
    return 200, {"reservation_id": record.reservation_id,
                 "status": record.status,
                 "compensation_ref": record.compensation_ref,
                 "project_id": record.project_id}


BUDGET_ROUTES = (
    ("get", "/api/v1/budget", "get_budget", get_budget),
    ("post", "/api/v1/budget/compensations", "post_compensations",
     post_compensations),
)


def post_compensate(ctx, query, body) -> Tuple[int, Dict[str, Any]]:
    """Compensate a failed gate to RELEASED (ARCH-441, served entry).

    Body carries reservation_id, reason and compensation_ref. Reads
    ctx.budget_state, which must be a BudgetGate (has compensate); any
    other shape is a 404. Gate error codes decide the status.
    """
    from agent_si.budget.gate import CompensationError
    from agent_si.budget.gate import CompensationRefConflictError
    from agent_si.budget.gate import CompensationAlreadySettledError
    from agent_si.budget.gate import CompensationUnknownReservationError

    body = body if isinstance(body, Mapping) else {}
    reservation_id = body.get("reservation_id", "")
    if not isinstance(reservation_id, str) or not reservation_id:
        return 400, {"code": COMPENSATION_RESERVATION_ID_REQUIRED,
                     "message": "reservation_id required"}
    gate = getattr(ctx, "budget_state", None)
    compensate = getattr(gate, "compensate", None)
    if not callable(compensate):
        return 404, {"code": BUDGET_NOT_CONFIGURED,
                     "message": "no compensating budget gate on file"}
    try:
        record = compensate(
            reservation_id, compensation_ref=body.get("compensation_ref", ""),
            reason=body.get("reason", ""))
    except CompensationUnknownReservationError as exc:
        return 404, {"code": exc.code, "message": str(exc)}
    except CompensationRefConflictError as exc:
        return 409, {"code": exc.code, "message": str(exc),
                     "existing_compensation_ref": exc.existing}
    except CompensationAlreadySettledError as exc:
        return 409, {"code": exc.code, "message": str(exc)}
    except CompensationError as exc:
        return 400, {"code": exc.code, "message": str(exc)}
    return 200, {"reservation_id": record.reservation_id,
                 "status": record.status,
                 "compensation_ref": record.compensation_ref,
                 "project_id": record.project_id}


def _k04f_enum_value(value):
    """Plain value of a frozen enum, or the value itself."""
    return getattr(value, "value", value)


def _k04f_gate(ctx):
    """The served BudgetGate, or None when K04 is unconfigured."""
    gate = getattr(ctx, "budget_state", None)
    if gate is None or not hasattr(gate, "compare_and_reserve"):
        return None
    return gate


def _k04f_ensure_project(gate, project_id, currency, hard_limit):
    """Configured project state; explicit limits only, never guessed."""
    try:
        return gate.get_state(project_id)
    except (KeyError, LookupError):
        return gate.configure_project(
            project_id, currency, hard_limit, hard_limit, hard_limit)


def k04f_breach(ctx, query, body):
    """Prove a breach lands as a persistent incident (BP04-8, served).

    Fills the hard limit through the real gate, then attempts one more
    billable reserve: the refusal carries BUDGET_HARD_BLOCKED plus the
    persisted incident id (the incident row survives a fresh gate over
    the same store).
    """
    from agent_si.budget.gate import BudgetBlockedError

    body = body if isinstance(body, Mapping) else {}
    project_id = body.get("project_id") or "k04f-breach"
    if not isinstance(project_id, str) or not project_id:
        return 400, {"code": BUDGET_PROJECT_ID_REQUIRED,
                     "message": "project_id required"}
    gate = _k04f_gate(ctx)
    if gate is None:
        return 404, {"code": BUDGET_NOT_CONFIGURED,
                     "message": "no budget gate on file"}
    currency = body.get("currency") or "USD"
    hard = body.get("hard_limit") or "1.00"
    _k04f_ensure_project(gate, project_id, currency, hard)
    task_id = body.get("task_id") or "t1"
    run_id = body.get("run_id") or "r1"
    fill = body.get("fill_amount") or hard
    over = body.get("over_amount") or "0.01"
    stamp = "2026-10-26T00:00:00Z"
    gate.compare_and_reserve(
        {"project_id": project_id, "task_id": task_id, "run_id": run_id,
         "reservation_id": "k04f-fill-%s" % project_id,
         "estimated_amount": fill, "reserved_at": stamp,
         "expires_at": "2026-10-27T00:00:00Z"})
    try:
        gate.compare_and_reserve(
            {"project_id": project_id, "task_id": task_id,
             "run_id": run_id,
             "reservation_id": "k04f-over-%s" % project_id,
             "estimated_amount": over, "reserved_at": stamp,
             "expires_at": "2026-10-27T00:00:00Z"})
    except BudgetBlockedError as exc:
        incidents = gate.list_incidents(project_id)
        current = incidents[-1] if incidents else None
        return 409, {"code": "BUDGET_HARD_BLOCKED",
                     "message": str(exc),
                     "incident_id": current.incident_id
                     if current is not None else None,
                     "incidents": len(incidents)}
    return 500, {"code": "K04F_BREACH_NOT_BLOCKED",
                 "message": "over-limit reserve was not blocked"}


def k04f_blocked_terminate(ctx, query, body):
    """Terminalize a BUDGET_BLOCKED run with started work (BP04-34).

    Starts one billable reserve, then applies the real pre-run
    disposition for a BUDGET_BLOCKED cause: the run terminalizes as
    FAILED/BUDGET_BLOCKED and the started reservation is released.
    """
    from agent_si.state_machines import run_machine as _run_machine

    body = body if isinstance(body, Mapping) else {}
    project_id = body.get("project_id") or "k04f-b34"
    task_id = body.get("task_id") or "t1"
    run_id = body.get("run_id") or "r1"
    gate = _k04f_gate(ctx)
    if gate is None:
        return 404, {"code": BUDGET_NOT_CONFIGURED,
                     "message": "no budget gate on file"}
    _k04f_ensure_project(gate, project_id, "USD", "10.00")
    stamp = "2026-10-26T00:00:00Z"
    started = gate.compare_and_reserve(
        {"project_id": project_id, "task_id": task_id, "run_id": run_id,
         "reservation_id": "k04f-started-%s" % run_id,
         "estimated_amount": body.get("start_amount") or "1.00",
         "reserved_at": stamp, "expires_at": "2026-10-27T00:00:00Z"})
    run = _run_machine.create_run(
        run_id=run_id, project_id=project_id, task_id=task_id,
        contract_hash=body.get("contract_hash") or "k04f-hash",
        run_sequence=1)
    disp = _run_machine.apply_pre_run_disposition(run, "BUDGET_BLOCKED")
    released = gate.release(started.reservation.reservation_id,
                            "BUDGET_BLOCKED pre-run terminalization")
    return 200, {
        "run_to_status": _k04f_enum_value(disp.run_to_status),
        "run_to_reason": _k04f_enum_value(disp.run_to_reason),
        "task_to_state": _k04f_enum_value(disp.task_to_state),
        "release_reservations": disp.release_reservations,
        "reservation_id": released.reservation_id,
        "reservation_status": released.status}


def k04f_estimate(ctx, query, body):
    """Serve the estimated_tokens derivation (ARCH-412, served read).

    Builds a real RoutingRequest from the served context defaults and
    returns the real max_tokens-plus-overhead derivation; negatives
    are refused, never summed.
    """
    import dataclasses as _dataclasses

    from agent_si.routing import router as _router

    query = query or {}
    raw_max = _query_value(query, "max_tokens", None)
    raw_over = _query_value(query, "token_overhead", "0")
    try:
        max_tokens = None if raw_max in (None, "") else int(raw_max)
        overhead = 0 if raw_over in (None, "") else int(raw_over)
    except (TypeError, ValueError):
        return 400, {"code": "K04F_ESTIMATE_REJECTED",
                     "message": "max_tokens and token_overhead "
                                "must be integers"}
    opt = _dataclasses.replace(ctx.default_opt(), token_overhead=overhead)
    request = _router.RoutingRequest(
        project_id="k04f", task_id="t1", run_id="r1", role="worker",
        task_class="coding", routing_policy=ctx.default_policy("coding"),
        optimization_policy=opt, max_tokens=max_tokens)
    try:
        value = _router._estimated_tokens(request)
    except ValueError as exc:
        return 400, {"code": "K04F_ESTIMATE_REJECTED",
                     "message": str(exc)}
    return 200, {"estimated_tokens": value, "max_tokens": max_tokens,
                 "token_overhead": overhead}


def k04f_reserve_tokens(ctx, query, body):
    """Reserve only through reserveTokens (ARCH-416, served write).

    Explicit amount plus explicit currency; a denomination that is
    not the project currency and a missing amount are refused, so
    currency is never invented.
    """
    from agent_si.budget.gate import BudgetBlockedError
    from agent_si.budget.gate import ReserveTokensError
    from agent_si.budget.gate import reserveTokens as _reserve_tokens

    body = body if isinstance(body, Mapping) else {}
    project_id = body.get("project_id")
    if not isinstance(project_id, str) or not project_id:
        return 400, {"code": BUDGET_PROJECT_ID_REQUIRED,
                     "message": "project_id required"}
    gate = _k04f_gate(ctx)
    if gate is None:
        return 404, {"code": BUDGET_NOT_CONFIGURED,
                     "message": "no budget gate on file"}
    currency = body.get("currency")
    try:
        gate.get_state(project_id)
    except (KeyError, LookupError):
        gate.configure_project(
            project_id, currency or "USD",
            body.get("hard_limit") or "10.00",
            body.get("hard_limit") or "10.00",
            body.get("hard_limit") or "10.00")
    stamp = "2026-10-26T00:00:00Z"
    request = {"project_id": project_id,
               "task_id": body.get("task_id") or "t1",
               "run_id": body.get("run_id") or "r1",
               "reservation_id": body.get("reservation_id") or
               "k04f-rt-%s" % project_id,
               "estimated_amount": body.get("estimated_amount"),
               "reserved_at": stamp, "expires_at": "2026-10-27T00:00:00Z"}
    try:
        result = _reserve_tokens(gate, request, currency=currency)
    except ReserveTokensError as exc:
        status = 409 if exc.code == "CURRENCY_MISMATCH" else 400
        return status, {"code": exc.code, "message": str(exc)}
    except (KeyError, LookupError):
        return 404, {"code": BUDGET_NOT_CONFIGURED,
                     "message": "no budget state on file for %r"
                                % (project_id,)}
    except BudgetBlockedError as exc:
        return 409, {"code": "BUDGET_HARD_BLOCKED",
                     "message": str(exc)}
    kept = gate.get_state(project_id)
    return 200, {"reservation_id": result.reservation.reservation_id,
                 "estimated_amount": result.reservation.estimated_amount,
                 "currency": kept.currency,
                 "status": result.reservation.status}


def k04f_route_block(ctx, query, body):
    """Route a budget block by recoverability (ARCH-427, served write).

    Drives the real AttemptExecutionGate with budget_coverage failed:
    recoverable blocks route to BLOCKED (a top-up restores) and the
    rest to ESCALATED.
    """
    from agent_si.policies.verification import AttemptExecutionGate
    from agent_si.policies.verification import GATE_CHECK_ORDER

    _ = query
    body = body if isinstance(body, Mapping) else {}
    recoverable = bool(body.get("recoverable", False))
    fallback = bool(body.get("fallback_available", False))
    checks = {name: True for name in GATE_CHECK_ORDER}
    checks["budget_coverage"] = False
    decision = AttemptExecutionGate.check(
        checks, run_status="CREATED", recoverable=recoverable,
        fallback_available=fallback)
    return 200, {"allowed": decision.allowed,
                 "failed_check": decision.failed_check,
                 "failure_class": _k04f_enum_value(
                     decision.failure_class),
                 "phase": decision.phase,
                 "task_effect": decision.task_effect,
                 "run_effect": decision.run_effect,
                 "detail": decision.detail}


def k04f_attach(ctx, query, body):
    """Attach a re-collection to its usage ref (BP04-5, served write).

    Collects the same usage reference twice through the real updater:
    the first call creates, the second attaches to the existing row
    without duplicating.
    """
    from agent_si.model_kb.updater import attach_metric_by_usage_ref

    _ = ctx
    body = body if isinstance(body, Mapping) else {}
    usage_ref = body.get("usage_ref")
    metric = body.get("metric")
    if not isinstance(usage_ref, str) or not usage_ref:
        return 400, {"code": "K04F_ATTACH_REF_REQUIRED",
                     "message": "usage_ref required"}
    if not isinstance(metric, Mapping):
        return 400, {"code": "K04F_ATTACH_REF_REQUIRED",
                     "message": "metric mapping required"}
    store = {}
    first, created = attach_metric_by_usage_ref(
        store, usage_ref, dict(metric))
    retry = dict(metric)
    retry["metric_id"] = "%s-retry" % metric.get("metric_id")
    second, created_again = attach_metric_by_usage_ref(
        store, usage_ref, retry)
    kept = second.get("metric_id") if isinstance(second, Mapping) \
        else getattr(second, "metric_id", None)
    return 200, {"created_first": created,
                 "created_second": created_again,
                 "same_row": second == first,
                 "kept_metric_id": kept,
                 "store_size": len(store)}


def k04f_snapshot(ctx, query, body):
    """Prove snapshot immutability once referenced (BP04-14, served).

    Costs one usage block against a fresh snapshot, refuses a
    same-id re-register with new prices (SNAPSHOT_ID_REUSE), mints
    the correction as a new version and shows the original row
    unchanged.
    """
    from agent_si.budget import telemetry as _telemetry

    _ = ctx
    body = body if isinstance(body, Mapping) else {}
    sid = body.get("pricing_snapshot_id") or "k04f-ps-1"
    provider_id = body.get("provider_id")
    model_id = body.get("model_id")
    if not provider_id or not model_id:
        return 400, {"code": "K04F_SNAPSHOT_REF_REQUIRED",
                     "message": "provider_id and model_id required"}
    currency = body.get("currency") or "USD"
    input_price = body.get("input_token_price") or "0.001"
    output_price = body.get("output_token_price") or "0.002"
    stamp = "2026-10-26T00:00:00Z"
    _telemetry.make_snapshot(
        sid, provider_id, model_id, currency, stamp, "k04f-proof",
        stamp, input_token_price=input_price,
        output_token_price=output_price)
    usage_ref = "k04f-usage-%s" % sid
    _telemetry.register_usage(
        usage_ref, {"input_tokens": 1000, "output_tokens": 500})
    cost = _telemetry.CostCalculator.calculate(usage_ref, sid).amount
    try:
        _telemetry.make_snapshot(
            sid, provider_id, model_id, currency, stamp, "k04f-proof",
            stamp,
            input_token_price=body.get("new_input_token_price")
            or "0.0015",
            output_token_price=output_price)
        refused = None
    except _telemetry.SnapshotIdReuseError as exc:
        refused = exc.code
    if refused is None:
        return 500, {"code": "K04F_SNAPSHOT_MUTABLE",
                     "message": "same-id price change was accepted"}
    new_id = "%s-v2" % sid
    _telemetry.make_snapshot(
        new_id, provider_id, model_id, currency, stamp, "k04f-proof",
        stamp,
        input_token_price=body.get("new_input_token_price")
        or "0.0015",
        output_token_price=output_price)
    new_cost = _telemetry.CostCalculator.calculate(
        usage_ref, new_id).amount
    again = _telemetry.make_snapshot(
        sid, provider_id, model_id, currency, stamp, "k04f-proof",
        stamp, input_token_price=input_price,
        output_token_price=output_price)
    return 200, {"cost": cost, "refused_code": refused,
                 "new_snapshot_id": new_id, "new_cost": new_cost,
                 "original_input_price": again.input_token_price}


K04F_ROUTES = (
    ("post", "/api/v1/budget/k04f/breach", "k04f_breach", k04f_breach),
    ("post", "/api/v1/budget/k04f/blocked-terminate",
     "k04f_blocked_terminate", k04f_blocked_terminate),
    ("get", "/api/v1/budget/k04f/estimate", "k04f_estimate",
     k04f_estimate),
    ("post", "/api/v1/budget/k04f/reserve-tokens",
     "k04f_reserve_tokens", k04f_reserve_tokens),
    ("post", "/api/v1/budget/k04f/route-block", "k04f_route_block",
     k04f_route_block),
    ("post", "/api/v1/budget/k04f/attach", "k04f_attach", k04f_attach),
    ("post", "/api/v1/budget/k04f/snapshot-proof", "k04f_snapshot",
     k04f_snapshot),
)

BUDGET_ROUTES = BUDGET_ROUTES + K04F_ROUTES
