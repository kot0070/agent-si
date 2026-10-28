"""K13F1 HTTP routes: amend, finalize-read, and stop over the real entries.

register_k13f1_routes(app) wires three endpoints onto the FastAPI app
built by create_app (prefix /api/v1/k13/). Per-app in-memory K13 stores
live on app.state (bound by bind_k13f1_state, called from the K13F1
block in create_app); no secret and no path is hardcoded here.

Writes (amend, stop) keep the frozen USER_WRITE guard: a missing
x-actor header fails 401 and a bad UI session token fails 403 via
app.state.auth_hook, before any K13 entry runs. Finalize-read is a
read and stays open.
"""

from __future__ import annotations

from dataclasses import asdict
from dataclasses import fields as _dc_fields
from enum import Enum
from typing import Any, Dict

from fastapi import HTTPException, Request

from agent_si.domain import amendments, contracts
from agent_si.runtime.scheduler import cancellation
from agent_si.storage import repositories

USER_WRITE = "USER_WRITE"

AMEND_PATH = "/api/v1/k13/contracts/amend"
STOP_PATH = "/api/v1/k13/runs/stop"
FINAL_PATH = "/api/v1/k13/finalizations/{finalization_id}"

_CONTRACT_FIELD_NAMES = {f.name for f in _dc_fields(contracts.TaskContract)}
_ACTIVATION_FIELD_NAMES = {
    f.name for f in _dc_fields(contracts.ContractActivationRecord)
}

_RESERVED_AMEND_FIELDS = (
    "contract_hash",
    "contract_version",
    "contract_sequence",
)


class K13State:
    """Per-app in-memory K13 stores for the amend/stop/read routes."""

    def __init__(self) -> None:
        self.contracts = repositories.TaskContractRepository()
        self.activations = repositories.ContractActivationLog()
        self.runs = repositories.ExecutionRunRepository()
        self.amendments = repositories.AmendmentRepository()
        self.finalizations = repositories.FinalizationLog()


def bind_k13f1_state(app: Any) -> K13State:
    """Create fresh K13 stores and bind them on app.state."""
    state = K13State()
    app.state.k13f1 = state
    return state


def k13f1_state(app: Any) -> K13State:
    """Return the bound K13 state, binding it when missing."""
    state = getattr(app.state, "k13f1", None)
    if state is None:
        state = bind_k13f1_state(app)
    return state


def _plain(value: Any) -> Any:
    """Render a stored value JSON-safe (enums to values, tuples to lists)."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return repr(value)


def contract_to_record(contract: contracts.TaskContract) -> Dict[str, Any]:
    """Serialize a contract for the contract store (keyed by content hash)."""
    row = _plain(asdict(contract))
    row["record_id"] = "%s:%s:%s" % (
        contract.project_id, contract.task_id, contract.contract_hash)
    row["version"] = contract.contract_version
    return row


def activation_to_record(
    activation: contracts.ContractActivationRecord,
) -> Dict[str, Any]:
    """Serialize an activation for the activation log."""
    row = _plain(asdict(activation))
    row["record_id"] = activation.activation_id
    row["version"] = activation.activation_sequence
    return row


def amendment_to_record(amendment: amendments.Amendment) -> Dict[str, Any]:
    """Serialize an amendment aggregate for the amendment store."""
    row = _plain(asdict(amendment))
    row["record_id"] = amendment.amendment_id
    row["version"] = amendment.amendment_sequence
    return row


def _write_guard(request: Request) -> str:
    """Frozen USER_WRITE guard: 401 without actor, 403 on a bad token."""
    actor = (request.headers.get("x-actor") or "").strip()
    if not actor:
        raise HTTPException(status_code=401,
                            detail="missing x-actor header")
    token = request.headers.get("x-ui-session-token")
    hook = getattr(request.app.state, "auth_hook", None)
    allowed = False
    if callable(hook):
        try:
            allowed = bool(hook(token, actor, USER_WRITE))
        except Exception:
            allowed = False
    else:
        expected = getattr(request.app.state, "ui_session_token", None)
        allowed = bool(token) and token == expected
    if not allowed:
        raise HTTPException(status_code=403, detail="forbidden")
    return actor


async def _json_body(request: Request, what: str) -> Dict[str, Any]:
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400,
                            detail="%s needs a JSON body" % what)
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400,
                            detail="%s needs a JSON object" % what)
    return payload


def _live_contract_row(
    state: K13State, project_id: str, task_id: str
) -> Dict[str, Any]:
    """Return the stored row for the task's active contract version."""
    stored_activations = state.activations.list_by(
        {"project_id": project_id, "task_id": task_id})
    if not stored_activations:
        raise HTTPException(status_code=404,
                            detail="no contract for task")
    activation_objs = [
        contracts.ContractActivationRecord(**{
            key: row[key] for key in _ACTIVATION_FIELD_NAMES if key in row
        })
        for row in stored_activations
    ]
    live = contracts.resolve_active(activation_objs)
    if live is None:
        raise HTTPException(status_code=404,
                            detail="no active contract for task")
    for row in state.contracts.list_by(
        {"project_id": project_id, "task_id": task_id}
    ):
        if row.get("contract_hash") == live.contract_hash:
            return row
    raise HTTPException(status_code=404,
                        detail="active contract record missing")


async def amend_contract(request: Request) -> Dict[str, Any]:
    """Apply an amendment: new contract version + activation record.

    Both amendment classes flow through the real entries (classify,
    terminal-task rule, immediate-effect descriptors, replace_with_new_version,
    activate, resolve_active). Running runs are never rewritten, so a
    RUNNING run keeps referencing the old contract hash.
    """
    _write_guard(request)
    payload = await _json_body(request, "amend")
    project_id = payload.get("project_id")
    task_id = payload.get("task_id")
    changed = payload.get("fields", {})
    if not project_id or not task_id:
        raise HTTPException(status_code=400,
                            detail="amend needs project_id and task_id")
    if not isinstance(changed, dict):
        raise HTTPException(status_code=400,
                            detail="amend fields must be an object")
    for reserved in _RESERVED_AMEND_FIELDS:
        if reserved in changed:
            raise HTTPException(
                status_code=400,
                detail="amend must not set %s" % reserved)
    effective_from = payload.get("effective_from", "IMMEDIATE")
    task_state = payload.get("task_state", "EXECUTING")
    reason = payload.get("reason", "") or ""
    state = k13f1_state(request.app)
    old_row = _live_contract_row(state, project_id, task_id)
    try:
        old_contract = contracts.TaskContract(**{
            key: old_row[key] for key in _CONTRACT_FIELD_NAMES
            if key in old_row
        })
    except Exception as exc:
        raise HTTPException(status_code=500,
                            detail="stored contract unreadable: %s" % exc)
    amendment_class = amendments.classify(
        amendments.AmendmentChange(fields=tuple(sorted(changed))))
    try:
        gate = amendments.apply_terminal_task_rule(task_state, effective_from)
        stored_amends = state.amendments.list_by({"project_id": project_id})
        amend_seq = 1 + max(
            [row.get("amendment_sequence", 0) for row in stored_amends] + [0])
        amendment = amendments.Amendment(
            amendment_id=payload.get("amendment_id") or "amend-%s-%d" % (
                task_id, amend_seq),
            project_id=project_id,
            amendment_sequence=amend_seq,
            scope=payload.get("scope", "TASK"),
            effective_from=effective_from,
            target=amendments.AmendmentTarget(task_id=task_id),
            change=amendments.AmendmentChange(
                fields=tuple(sorted(changed)), summary=reason),
            reason=reason,
            created_at=payload.get("created_at", ""),
            source=payload.get("source", ""),
            status="APPLIED",
        )
        descriptors = amendments.apply_immediate_effect(
            amendment,
            task_state,
            payload.get("active_run_id"),
            payload.get("active_run_status"),
        )
    except amendments.TerminalTaskAmendmentError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if gate != amendments.APPLY:
        raise HTTPException(status_code=409, detail=gate)
    try:
        new_contract = contracts.replace_with_new_version(
            old_contract, **changed)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    stored_task_activations = state.activations.list_by(
        {"project_id": project_id, "task_id": task_id})
    act_seq = 1 + max(
        [row.get("activation_sequence", 0)
         for row in stored_task_activations] + [0])
    new_activation = contracts.activate(
        new_contract,
        activation_id=payload.get("activation_id") or "act-%s-%d" % (
            task_id, act_seq),
        activation_sequence=act_seq,
        activation_reason=reason or "amendment",
        effective_from=effective_from,
        amendment_id=amendment.amendment_id,
        previous_contract_hash=old_contract.contract_hash,
        activated_at=payload.get("activated_at", ""),
    )
    unit = repositories.UnitOfWork()
    unit.stage_append(state.contracts, contract_to_record(new_contract))
    unit.stage_append(state.activations, activation_to_record(new_activation))
    unit.stage_append(state.amendments, amendment_to_record(amendment))
    try:
        unit.commit()
    except Exception as exc:
        raise HTTPException(status_code=500,
                            detail="amend store write failed: %s" % exc)
    return {
        "amendment_id": amendment.amendment_id,
        "amendment_class": amendment_class,
        "project_id": project_id,
        "task_id": task_id,
        "contract_version": new_contract.contract_version,
        "contract_sequence": new_contract.contract_sequence,
        "contract_hash": new_contract.contract_hash,
        "previous_contract_hash": old_contract.contract_hash,
        "activation_id": new_activation.activation_id,
        "activation_sequence": new_activation.activation_sequence,
        "effective_from": _plain(new_activation.effective_from),
        "effects": [
            {"action": item.action, "target": item.target,
             "reason": item.reason, "detail": item.detail}
            for item in descriptors
        ],
    }


async def stop_run(request: Request) -> Dict[str, Any]:
    """Finalize cancellation of one run and persist its CANCELLED status."""
    _write_guard(request)
    payload = await _json_body(request, "stop")
    project_id = payload.get("project_id")
    run_id = payload.get("run_id")
    if not project_id or not run_id:
        raise HTTPException(status_code=400,
                            detail="stop needs project_id and run_id")
    state = k13f1_state(request.app)
    stored = state.runs.load(run_id)
    if stored is None or stored.get("project_id") != project_id:
        raise HTTPException(status_code=404, detail="no such run")
    reason = payload.get("reason", "CANCELLED_BY_USER") or "CANCELLED_BY_USER"
    from_status = stored.get("status", "RUNNING")
    try:
        attempts = tuple(
            cancellation.CancellableAttempt(
                attempt_id=item.get("attempt_id", ""),
                run_id=item.get("run_id", run_id),
                status=item.get("status", "RUNNING"),
            )
            for item in (stored.get("attempts") or ())
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        result = cancellation.finalize_cancellation(
            run_id=run_id,
            reason=reason,
            from_status=from_status,
            attempts=attempts,
            measured_usage=payload.get("measured_usage"),
            unmeasurable_usage=payload.get("unmeasurable_usage") or (),
            reservation_ids=payload.get("reservation_ids") or (),
            lease_ids=payload.get("lease_ids") or (),
            audit_refs=payload.get("audit_refs") or (),
            verification_refs=payload.get("verification_refs") or (),
        )
    except cancellation.NonCanonicalCancellationReasonError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except cancellation.AttemptRunMismatchError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except cancellation.IllegalCancellationTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    current_version = stored.get("version", 1)
    if isinstance(current_version, int):
        next_version = current_version + 1
    else:
        next_version = 1
    updated = dict(stored)
    updated["status"] = result.to_status.value
    updated["version"] = next_version
    try:
        state.runs.compare_and_set(run_id, current_version, updated)
    except Exception as exc:
        raise HTTPException(status_code=409,
                            detail="run write conflict: %s" % exc)
    usage = None
    if result.usage is not None:
        usage = {
            "run_id": result.usage.run_id,
            "measured": [[name, number]
                         for name, number in result.usage.measured],
            "unmeasurable": list(result.usage.unmeasurable),
        }
    return {
        "run_id": result.run_id,
        "from_status": _plain(result.from_status),
        "to_status": _plain(result.to_status),
        "reason": _plain(result.reason),
        "attempts": [
            {"attempt_id": item.attempt_id, "run_id": item.run_id,
             "status": _plain(item.status)}
            for item in result.attempts
        ],
        "usage": usage,
        "releases": [
            {"kind": item.kind, "ref": item.ref, "action": item.action}
            for item in result.releases
        ],
    }


async def read_finalization(
    finalization_id: str, request: Request
) -> Dict[str, Any]:
    """Read one finalization record from the real finalization store."""
    state = k13f1_state(request.app)
    stored = state.finalizations.load(finalization_id)
    if stored is None:
        raise HTTPException(status_code=404,
                            detail="no such finalization")
    project_id = request.query_params.get("project_id")
    if project_id is not None and stored.get("project_id") != project_id:
        raise HTTPException(status_code=404,
                            detail="no such finalization")
    return _plain(dict(stored))


def register_k13f1_routes(app: Any) -> Any:
    """Bind K13 state when missing and wire the three K13 endpoints."""
    k13f1_state(app)
    app.post(AMEND_PATH)(amend_contract)
    app.get(FINAL_PATH)(read_finalization)
    app.post(STOP_PATH)(stop_run)
    return app
