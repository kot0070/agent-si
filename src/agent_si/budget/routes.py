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
