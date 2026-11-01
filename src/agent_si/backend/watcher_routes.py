"""Watcher HTTP surface: real router over the frozen watcher contract.

Row R-323 plus row Q3, lane m_entry, author CODER-2 Sable. Every entry of
``ROUTE_ENTRY_POINTS`` maps to the owning lane module (automation_routes
pattern): reads serve the watcher lane, the stop-all entry serves
``agent_si.backend.stop_all``. POST routes need a live session token
(``SESSION_TOKEN_MISSING`` -> 401, ``SESSION_TOKEN_INVALID`` -> 403,
checked before any stop is recorded); GET routes are open. The token is
read from the ``x-ui-session-token`` header or the ``session_token`` body
field. ``configure`` accepts the composition-root hooks, mirroring the
automation router.

K08NEXT additive entries (owned lane modules, same error mapping via
``_serve_owned``; the frozen five-entry drift table is untouched):
run cancel (B0B-SDK-94/95/96/99), keeper save-restore benchmark
(M-P4-160) and record-bound finalize-write (ARCH-641/642).
"""

from __future__ import annotations

import dataclasses
import datetime
import sys
from enum import Enum
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, HTTPException, Request

from agent_si.assurance import audit_records as _audit_home
from agent_si.automation import runner as _auto_runner_home
from agent_si.backend import stop_all as _stop_home
from agent_si.context_keeper import checkpoints as _checkpoints_home
from agent_si.context_keeper import register as _keeper_register_home
from agent_si.finalization import finalizer as _finalizer_home
from agent_si.policies import verification as _verify_home
from agent_si.watcher import alerts as _alerts_home
from agent_si.watcher import integrity as _integrity_home
from agent_si.watcher import journal as _journal_home
from agent_si.watcher import rules as _rules_home
from agent_si.watcher import status as _status_home

#: Dotted name of the frozen watcher contract module. Product code keeps
#: no static import of it; the module object is resolved late at call
#: time, so raised errors and returned rows are the same objects the
#: contract tests use.
_IFACE_MODULE = "agent_si.watcher.interface"


def _watcher_iface():
    """Return the frozen watcher contract module object."""
    try:
        return sys.modules[_IFACE_MODULE]
    except KeyError:
        import importlib

        return importlib.import_module(_IFACE_MODULE)


#: Dotted name of the frozen context-keeper contract module. Product code
#: keeps no static import of it; rows are built from the same class
#: objects the keeper tests use, resolved late at call time.
_CK_MODULE = "agent_si.context_keeper.interface"


def _ck_contract():
    """Return the frozen context-keeper contract module object."""
    try:
        return sys.modules[_CK_MODULE]
    except KeyError:
        import importlib

        return importlib.import_module(_CK_MODULE)


__all__ = ("router", "configure", "token_live")

router = APIRouter()

_auth_hook: Optional[Callable[[str], bool]] = None
_rate_hook: Optional[Callable[[str], bool]] = None


def configure(
    auth_hook: Optional[Callable[[str], bool]] = None,
    rate_hook: Optional[Callable[[str], bool]] = None,
    model_factory: Optional[Callable[[str], Any]] = None,
) -> Dict[str, Any]:
    """Install composition-root hooks (K02 owns auth/rate/model policy)."""
    global _auth_hook, _rate_hook
    _auth_hook = auth_hook
    _rate_hook = rate_hook
    return {
        "auth_hook": _auth_hook is not None,
        "rate_hook": _rate_hook is not None,
        "model_factory": model_factory is not None,
    }


def token_live(token: Optional[str]) -> bool:
    """True only when the configured auth hook accepts the token."""
    return (
        _auth_hook is not None
        and isinstance(token, str)
        and bool(token)
        and bool(_auth_hook(token))
    )


_STATUS_BY_CODE: Dict[str, int] = {
    "SESSION_TOKEN_MISSING": 401,
    "SESSION_TOKEN_INVALID": 403,
    "RULE_NOT_FOUND": 404,
    "PRESET_NOT_FOUND": 404,
    "JOURNAL_KIND_UNKNOWN": 404,
    "AUTOMATION_RUN_NOT_FOUND": 404,
    "STOP_REASON_MISSING": 400,
    "CANCEL_MODE_UNKNOWN": 400,
    "FINALIZATION_REFUSED": 400,
    "FINALIZATION_CONFLICT": 409,
    "CHECKPOINT_WRITE_REFUSED": 400,
    "GOVERNANCE_MISMATCH": 409,
    "PAUSE_REASON_MISSING": 400,
    "AUTOMATION_PAUSED": 409,
    "AUTOMATION_RUN_ACTIVE": 409,
}


def _fail(code: str, detail: str = "") -> None:
    raise HTTPException(
        status_code=_STATUS_BY_CODE.get(code, 400),
        detail={"code": code, "detail": detail},
    )


def _dump(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Enum):
        return value.value
    if dataclasses.is_dataclass(value):
        return {
            field.name: _dump(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, (tuple, list)):
        return [_dump(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _dump(item) for key, item in value.items()}
    return value


def _verify_integrity(project_id: str, session_token: str = ""):
    """Entry wrapper: integrity verify tolerates the route kwarg."""
    return _integrity_home.verify(project_id)


def _evaluate_rule(project_id: str, rule_id: str, session_token: str = ""):
    """Entry wrapper: rule evaluate tolerates the route kwarg."""
    return _rules_home.evaluate(project_id, rule_id)


def _stop_all(actor: str, project_id: str, grant_ref: str = "",
              session_token: str = ""):
    """Entry wrapper: stop-all tolerates the route kwarg."""
    return _stop_home.request_stop(actor, project_id, grant_ref)


def _list_alerts(project_id: str, session_token: str = ""):
    """Entry wrapper: alerts list tolerates the route kwarg."""
    return _alerts_home.list_alerts(project_id)


def _fire_timer(project_id: str, timer_id: str, session_token: str = ""):
    """Entry wrapper: timer fire tolerates the route kwarg."""
    return _rules_home.fire_timer(project_id, timer_id)


def _pause_timer(project_id: str, timer_id: str, paused: bool,
                 reason: str = "", session_token: str = ""):
    """Entry wrapper: timer pause tolerates the route kwarg."""
    return _rules_home.pause_timer(project_id, timer_id, paused, reason)


def _utc_now_iso() -> str:
    """Call-time UTC stamp in ISO form for served record fields."""
    return datetime.datetime.now(
        datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _cancel_run(project_id: str, run_id: str, reason: str = "",
                mode: str = "immediate", session_token: str = ""):
    """Entry wrapper: run cancel tolerates the route kwarg.

    B0B-SDK-94/95/96/99: immediate (the default) stops at once, after-turn
    waits for the open turn; any other mode refuses with
    CANCEL_MODE_UNKNOWN, never a silent pass.
    """
    try:
        return _auto_runner_home.cancel_run(
            project_id, run_id, reason, mode=mode or "immediate")
    except HTTPException:
        raise
    except ValueError as err:
        _fail("CANCEL_MODE_UNKNOWN", str(err))
    return None


def _seed_keeper_provenance(register: Any, project_id: str, task_id: str,
                            run_id: Any, contract_hash: str,
                            sourced_refs: Any) -> None:
    """Pin one keeper record per sourced ref (real register append)."""
    contract = _ck_contract()
    for index, ref in enumerate(tuple(sourced_refs)):
        register.append(contract.ContextIntegrityRecord(
            context_event_id="evt-bm-served-%d" % index,
            incident_ref=None,
            project_id=project_id,
            task_id=task_id,
            run_id=run_id,
            actor="watcher",
            detected_by="watcher",
            type="CONTEXT_MISSING",
            severity=contract.IncidentSeverity.LOW,
            expected_context_refs=(ref,),
            actual_context_refs=(ref,),
            missing_refs=(),
            conflicting_refs=(),
            contract_hash=contract_hash,
            detected_at=_utc_now_iso(),
            impact="served benchmark seed",
            resolution="",
            resolved_at=None,
            evidence_refs=(),
        ))


def _benchmark_checkpoints(project_id: str, task_id: str, run_id: Any,
                           contract_hash: str, context_refs: Any = (),
                           sourced_refs: Any = (),
                           session_token: str = ""):
    """Entry wrapper: keeper save-restore benchmark (M-P4-160).

    Seeded refs benchmark SOURCED, every other ref UNKNOWN; the save is
    restored back and compared, never assumed.
    """
    try:
        register = _keeper_register_home.Register()
        _seed_keeper_provenance(register, project_id, task_id, run_id,
                                contract_hash, sourced_refs)
        store = _checkpoints_home.Checkpoints()
        return store.benchmark_save_restore(
            project_id=project_id,
            task_id=task_id,
            run_id=run_id,
            contract_hash=contract_hash,
            context_refs=tuple(context_refs),
            provenance_fn=lambda ref: register.provenance(
                project_id, ref),
        )
    except HTTPException:
        raise
    except ValueError as err:
        _fail("CHECKPOINT_WRITE_REFUSED", str(err))
    return None


def _finalize_bound(data: Dict[str, Any], session_token: str = ""):
    """Entry wrapper: strict record-bound finalization (ARCH-641/642).

    Both records are built through the real entries from the served body
    and finalized through the real ``Finalizer.finalize_with_records``.
    A missing or mismatched record refuses with FINALIZATION_REFUSED
    (an error-code body, never a silent pass).
    """
    try:
        raw_run = data.get("run_id")
        run_id = raw_run if isinstance(raw_run, str) else None
        record_run = raw_run if isinstance(raw_run, str) else ""
        verification_payload = data.get("verification")
        audit_payload = data.get("audit")
        verification_ref = data.get("verification_ref")
        if (verification_ref is None
                and isinstance(verification_payload, dict)):
            verification_ref = verification_payload.get("verification_id")
        verification_record = (
            None if not isinstance(verification_payload, dict)
            else _verify_home.VerificationRecord(
                verification_id=str(
                    verification_payload.get("verification_id", "")),
                project_id=str(data.get("project_id", "")),
                task_id=str(data.get("task_id", "")),
                run_id=record_run,
                contract_hash=str(
                    verification_payload.get("contract_hash", "")),
            )
        )
        audit_record = (
            None if not isinstance(audit_payload, dict)
            else _audit_home.AuditRecord(
                audit_id=str(audit_payload.get("audit_id", "")),
                project_id=str(data.get("project_id", "")),
                task_id=str(data.get("task_id", "")),
                run_id=record_run,
                audit_scope_id="scope-%s" % (
                    str(audit_payload.get("audit_id", "")) or "served"),
                audit_sequence=1,
                supersedes_audit_id=None,
                context_session_ref="sess-%s" % (
                    str(audit_payload.get("audit_id", "")) or "served"),
                producer_session_refs=("sess-prod-served",),
                implementer_model_ids=("impl-model-served",),
                contract_hash=str(
                    audit_payload.get("contract_hash", "")),
                audit_policy_ref="pol-served",
                artifact_refs=tuple(data.get("output_refs") or ()),
                evidence_refs=("ev-served",),
                requirement_verdicts=(),
                context_integrity="PASS",
                result=_audit_home.AuditResult(
                    str(audit_payload.get("result", "") or "FAIL")),
                handling_disposition=(
                    _audit_home.AuditHandlingDisposition.COMPLETE),
                failure_class=None,
                created_at=_utc_now_iso(),
                decided_at=None,
            )
        )
        return _finalizer_home.Finalizer.finalize_with_records(
            verification_record=verification_record,
            audit_record=audit_record,
            finalization_id=str(data.get("finalization_id", "")),
            project_id=str(data.get("project_id", "")),
            task_id=str(data.get("task_id", "")),
            run_id=run_id,
            task_state=str(data.get("task_state", "")),
            audit_ref=audit_record,
            verification_ref=verification_ref,
            output_refs=tuple(data.get("output_refs") or ()),
            accounting_complete=bool(data.get(
                "accounting_complete", False)),
            budget_settled=bool(data.get("budget_settled", False)),
            resources_released=bool(data.get(
                "resources_released", False)),
        )
    except HTTPException:
        raise
    except _finalizer_home.FinalizationError as err:
        _fail("FINALIZATION_REFUSED", str(err))
    except (ValueError, TypeError, KeyError) as err:
        _fail("FINALIZATION_REFUSED", str(err))
    return None


def _call(entry_name: str, *args: Any, **kwargs: Any) -> Any:
    _check_drift()
    try:
        return _dump(_DISPATCH[entry_name](*args, **kwargs))
    except HTTPException:
        raise
    except Exception as err:
        # Lane errors travel as (code, detail) on either WatcherError
        # class (frozen contract or lane home); anything else is a bug.
        code = getattr(err, "code", "")
        if not code:
            raise
        _fail(code, getattr(err, "detail", "") or str(err))
    return None


def _serve_owned(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Serve one owned lane entry bound after the frozen five-entry table.

    New R-324/R-335 bindings call their owning lane modules directly with
    the same error mapping as _call; the frozen drift table (_HANDLED vs
    ROUTE_ENTRY_POINTS) is untouched, so _check_drift keeps guarding the
    declared routes.
    """
    try:
        return _dump(func(*args, **kwargs))
    except HTTPException:
        raise
    except Exception as err:
        code = getattr(err, "code", "")
        if not code:
            raise
        _fail(code, getattr(err, "detail", "") or str(err))
    return None


async def _body(request: Request) -> Dict[str, Any]:
    try:
        data = await request.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _token_of(request: Request, data: Dict[str, Any]) -> Optional[str]:
    header = request.headers.get("x-ui-session-token")
    if isinstance(header, str) and header:
        return header
    value = data.get("session_token")
    if isinstance(value, str) and value:
        return value
    return None


def _guard_post(request: Request, data: Dict[str, Any]) -> str:
    token = _token_of(request, data)
    if token is None:
        _fail("SESSION_TOKEN_MISSING", "POST needs a live session token")
        raise AssertionError("unreachable")
    if not token_live(token):
        _fail("SESSION_TOKEN_INVALID", "unknown session token")
        raise AssertionError("unreachable")
    if _rate_hook is not None:
        key = token
        try:
            allowed = bool(_rate_hook(key))
        except Exception:
            allowed = False
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail={"code": "RATE_LIMITED", "detail": "rate hook refused"},
            )
    return token


#: Entry-name dispatch: every entry calls its 0C-named owning module.
_DISPATCH: Dict[str, Callable[..., Any]] = {
    "get_status": _status_home.get,
    "list_events": _journal_home.list_events,
    "verify_integrity": _verify_integrity,
    "evaluate_rule": _evaluate_rule,
    "stop_all_request_stop": _stop_all,
}

#: Route key to entry name; must equal ROUTE_ENTRY_POINTS exactly.
_HANDLED: Dict[str, str] = {
    "GET /api/v1/watcher/status": "get_status",
    "GET /api/v1/watcher/journal": "list_events",
    "POST /api/v1/watcher/integrity-check": "verify_integrity",
    "POST /api/v1/watcher/rules/{id}/evaluate": "evaluate_rule",
    "POST /api/v1/stop-all": "stop_all_request_stop",
}

_drift_checked = False


def _check_drift():
    """Verify the route table against the frozen contract once, on first use."""
    global _drift_checked
    if _drift_checked:
        return
    if dict(_HANDLED) != dict(_watcher_iface().ROUTE_ENTRY_POINTS):
        raise RuntimeError("watcher routes drifted from ROUTE_ENTRY_POINTS")
    _drift_checked = True


if set(_HANDLED.values()) != set(_DISPATCH):
    raise RuntimeError("watcher routes dispatch is incomplete")


@router.get("/api/v1/watcher/status")
def route_get_status(project_id: str) -> Any:
    """GET /api/v1/watcher/status -> get_status (open)."""
    return _call("get_status", project_id)


@router.get("/api/v1/watcher/journal")
def route_get_journal(project_id: str, kind: str = "") -> Any:
    """GET /api/v1/watcher/journal -> list_events (open)."""
    return _call("list_events", project_id, kind)


@router.post("/api/v1/watcher/integrity-check")
async def route_post_integrity(request: Request) -> Any:
    """POST /api/v1/watcher/integrity-check -> verify_integrity (token)."""
    data = await _body(request)
    token = _guard_post(request, data)
    return _call(
        "verify_integrity", str(data.get("project_id", "")),
        session_token=token,
    )


@router.post("/api/v1/watcher/rules/{id}/evaluate")
async def route_post_evaluate(id: str, request: Request) -> Any:
    """POST /api/v1/watcher/rules/{id}/evaluate -> evaluate_rule (token)."""
    data = await _body(request)
    token = _guard_post(request, data)
    return _call(
        "evaluate_rule", str(data.get("project_id", "")), id,
        session_token=token,
    )


@router.post("/api/v1/stop-all")
async def route_post_stop_all(request: Request) -> Any:
    """POST /api/v1/stop-all -> stop_all_request_stop (token).

    A body carrying ``project_id`` stops only that project; an empty
    body stops every project's work.
    """
    data = await _body(request)
    token = _guard_post(request, data)
    project_id = str(data.get("project_id", "") or data.get("project", ""))
    if not project_id:
        return _serve_owned(
            _stop_home.request_stop_all,
            str(data.get("actor", "")),
            grant_ref=str(data.get("grant_ref", "")),
            session_token=token,
        )
    return _call(
        "stop_all_request_stop",
        str(data.get("actor", "")),
        project_id,
        grant_ref=str(data.get("grant_ref", "")),
        session_token=token,
    )


@router.get("/api/v1/watcher/alerts")
def route_get_alerts(project_id: str) -> Any:
    """GET /api/v1/watcher/alerts -> list_alerts (open)."""
    return {"alerts": _serve_owned(_list_alerts, project_id)}


@router.post("/api/v1/watcher/timers/{id}/fire")
async def route_post_timer_fire(id: str, request: Request) -> Any:
    """POST /api/v1/watcher/timers/{id}/fire -> fire_timer (token)."""
    data = await _body(request)
    token = _guard_post(request, data)
    return _serve_owned(
        _fire_timer, str(data.get("project_id", "")), id,
        session_token=token,
    )


@router.post("/api/v1/watcher/timers/{id}/pause")
async def route_post_timer_pause(id: str, request: Request) -> Any:
    """POST /api/v1/watcher/timers/{id}/pause -> pause_timer (token)."""
    data = await _body(request)
    token = _guard_post(request, data)
    return _serve_owned(
        _pause_timer, str(data.get("project_id", "")), id,
        bool(data.get("paused", False)), str(data.get("reason", "")),
        session_token=token,
    )


@router.post("/api/v1/automations/runs/{id}/cancel")
async def route_post_run_cancel(id: str, request: Request) -> Any:
    """POST /api/v1/automations/runs/{id}/cancel -> cancel_run (token)."""
    data = await _body(request)
    token = _guard_post(request, data)
    return _serve_owned(
        _cancel_run, str(data.get("project_id", "")), id,
        str(data.get("reason", "")), str(data.get("mode", "immediate")),
        session_token=token,
    )


@router.post("/api/v1/watcher/checkpoints/benchmark")
async def route_post_benchmark(request: Request) -> Any:
    """POST /api/v1/watcher/checkpoints/benchmark -> benchmark (token)."""
    data = await _body(request)
    token = _guard_post(request, data)
    return _serve_owned(
        _benchmark_checkpoints, str(data.get("project_id", "")),
        str(data.get("task_id", "")), data.get("run_id"),
        str(data.get("contract_hash", "")),
        tuple(data.get("context_refs") or ()),
        tuple(data.get("sourced_refs") or ()),
        session_token=token,
    )


def _persist_finalization(app: Any, record: Any) -> None:
    """Append the served finalization to the real finalization log.

    The K13 finalize-read route serves this store, so a served write is
    readable back; a re-write of one id with different content refuses
    with FINALIZATION_CONFLICT (the log is append-only).
    """
    state = getattr(app.state, "k13f1", None)
    if state is None:
        return
    stored = dict(record) if isinstance(record, dict) else {}
    stored["record_id"] = stored.get("finalization_id", "")
    try:
        state.finalizations.append(stored)
    except HTTPException:
        raise
    except Exception as err:
        _fail("FINALIZATION_CONFLICT", str(err))


@router.post("/api/v1/core/finalizations")
async def route_post_finalize(request: Request) -> Any:
    """POST /api/v1/core/finalizations -> finalize_with_records (token)."""
    data = await _body(request)
    token = _guard_post(request, data)
    record = _serve_owned(_finalize_bound, data, session_token=token)
    _persist_finalization(request.app, record)
    return record
