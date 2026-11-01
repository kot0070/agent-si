"""K03WIRE served assurance entries plus their FastAPI mount.

Every entry has the frozen shape ``(payload: dict) -> dict`` and
drives only the real product entries: ``AuditCoordinator``
(served-turn, fresh-audit, pair-reuse, close-stage, risk-defaults),
``assurance_coordinator.run_assurance`` (run gate),
``checker.verify_run`` (verify-run) and ``AuditorRegistry``
(sourcing-state). The module adds no product logic of its own; it
only adapts HTTP payloads to the real entries and their results to
plain JSON dicts. Errors from the real entries keep their frozen
signal codes on the wire.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, Request

#: Frozen write guard action shared with the seam app.
USER_WRITE = "USER_WRITE"

_SERVED_TURN_ROUTE = "/api/v1/assurance/served-turn"
_RUN_ROUTE = "/api/v1/assurance/run"
_FRESH_AUDIT_ROUTE = "/api/v1/assurance/fresh-audit"
_PAIR_REUSE_ROUTE = "/api/v1/assurance/pair-reuse"
_VERIFY_RUN_ROUTE = "/api/v1/assurance/verify-run"
_RISK_DEFAULTS_ROUTE = "/api/v1/assurance/risk-defaults"
_CLOSE_STAGE_ROUTE = "/api/v1/assurance/stages/close"
_SOURCING_STATE_ROUTE = "/api/v1/assurance/sourcing-state"


class _WireError(Exception):
    """Entry-level refusal carrying its HTTP status plus signal code."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


def _utcnow() -> str:
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


def _need_text(mapping: Any, name: str, what: str) -> str:
    """Return one required non-blank text field, else a loud 400."""
    value = mapping.get(name) if isinstance(mapping, dict) else None
    if not isinstance(value, str) or not value.strip():
        raise _WireError(400, "K03WIRE_FIELD_MISSING",
                         "k03wire needs a non-empty %s" % what)
    return value.strip()


def _need_list(mapping: Any, name: str) -> list[Any]:
    """Return one optional request list (missing reads as empty)."""
    value = mapping.get(name) if isinstance(mapping, dict) else None
    if value is None:
        return []
    if not isinstance(value, list):
        raise _WireError(400, "K03WIRE_FIELD_INVALID",
                         "k03wire needs %s as a JSON list" % name)
    return list(value)


def _str_tuple(values: list[Any]) -> tuple[str, ...]:
    """Render one request list as a tuple of strings."""
    return tuple(str(item) for item in values)


def _coordinator() -> Any:
    """A concrete binding of the real audit entries; adds no behavior."""
    from agent_si.assurance import audit_coordinator as _entries

    class _WireCoordinator(_entries.AuditCoordinator):
        """Fresh binding per call; adds no behavior."""

    return _WireCoordinator()


def _registry() -> Any:
    """A concrete binding of the real sourcing entries; adds no behavior."""
    from agent_si.assurance import audit_registry as _entries

    class _WireRegistry(_entries.AuditorRegistry):
        """Fresh binding per call; adds no behavior."""

    return _WireRegistry()


def _turn_of(payload: dict[str, Any]) -> Any:
    """Build the real ServedTurn from one request payload."""
    from agent_si.assurance import audit_coordinator as _entries

    return _entries.ServedTurn(
        turn_ref=_need_text(payload, "run_id", "run_id"),
        project_id=_need_text(payload, "project_id", "project_id"),
        task_id=_need_text(payload, "task_id", "task_id"),
        run_id=_need_text(payload, "run_id", "run_id"),
        work_refs=_str_tuple(_need_list(payload, "work_refs")),
        artifact_refs=_str_tuple(_need_list(payload, "artifact_refs")),
        evidence_refs=_str_tuple(_need_list(payload, "evidence_refs")),
        producer_session_refs=_str_tuple(
            _need_list(payload, "producer_session_refs")),
        contract_hash=_need_text(payload, "contract_hash", "contract_hash"),
    )


def _candidates_of(payload: dict[str, Any],
                   registry: Any) -> list[tuple[str, str]]:
    """Register the payload auditor candidates; return provider/model pairs."""
    from agent_si.assurance import audit_registry as _entries

    pairs = []
    for position, raw in enumerate(_need_list(
            payload, "auditor_candidates")):
        if not isinstance(raw, dict):
            raise _WireError(400, "K03WIRE_FIELD_INVALID",
                             "auditor candidate %d must be a JSON object"
                             % position)
        provider_id = _need_text(
            raw, "provider_id", "auditor candidate provider_id")
        model = _need_text(raw, "model", "auditor candidate model")
        instance = raw.get("provider_instance")
        refs = raw.get("capability_evidence_refs")
        if refs is None:
            cap_refs: tuple[str, ...] = ()
        elif isinstance(refs, list):
            cap_refs = tuple(str(item) for item in refs)
        else:
            raise _WireError(400, "K03WIRE_FIELD_INVALID",
                             "auditor candidate capability_evidence_refs "
                             "must be a JSON list")
        registry.register_candidate(_entries.AuditorCandidate(
            provider_id=provider_id,
            provider_instance=(
                instance if isinstance(instance, str) else None),
            model=model,
            capability_evidence_refs=cap_refs,
            registered_at="",
        ))
        pairs.append((provider_id, model))
    return pairs


def k03wire_served_turn(payload: dict[str, Any]) -> dict[str, Any]:
    """Assure one served turn; empty work fails through the real entry."""
    turn = _turn_of(payload)
    audit_id = _coordinator().audit_served_turn(turn)
    return {"served": True, "audit_id": audit_id}


def k03wire_run(payload: dict[str, Any]) -> dict[str, Any]:
    """Run the real verify-then-audit-then-finalize gate; return one outcome."""
    from agent_si.assurance import coordinator as _gate

    outcome = _gate.run_assurance(
        project_id=_need_text(payload, "project_id", "project_id"),
        task_id=_need_text(payload, "task_id", "task_id"),
        run_id=_need_text(payload, "run_id", "run_id"),
        contract_hash=_need_text(payload, "contract_hash", "contract_hash"),
        artifact_refs=_str_tuple(_need_list(payload, "artifact_refs")),
        evidence_refs=_str_tuple(_need_list(payload, "evidence_refs")),
        work_refs=_str_tuple(_need_list(payload, "work_refs")),
        producer_session_refs=_str_tuple(
            _need_list(payload, "producer_session_refs")),
        tool_rows=tuple(_need_list(payload, "tool_rows")),
        criteria=tuple(_need_list(payload, "criteria")),
        project_dir=str(payload.get("project_dir") or ""),
        output_refs=_str_tuple(_need_list(payload, "output_refs")),
        metric_refs=_str_tuple(_need_list(payload, "metric_refs")),
        accounting_complete=bool(payload.get("accounting_complete", False)),
        budget_settled=bool(payload.get("budget_settled", False)),
        resources_released=bool(payload.get("resources_released", False)),
    )
    return {
        "ok": bool(outcome.ok),
        "phase": str(outcome.phase),
        "verification_id": outcome.verification_id,
        "audit_id": outcome.audit_id,
        "finalization_id": outcome.finalization_id,
        "status_trail": list(outcome.status_trail),
    }


def _record_pins_for_run(run_id: str) -> tuple[str, ...]:
    """Distinct product-recorded contract_hash pins for one run, oldest first."""
    from agent_si.assurance import audit_records as _records

    try:
        rows = _records._records_for_run(run_id)
    except Exception:
        return ()
    pins: list[str] = []
    for row in rows or ():
        pinned = getattr(row, "contract_hash", "")
        if isinstance(pinned, str) and pinned and pinned not in pins:
            pins.append(pinned)
    return tuple(pins)


def k03wire_fresh_audit(payload: dict[str, Any]) -> dict[str, Any]:
    """Audit through a fresh auditor; contributors in the set are refused."""
    turn = _turn_of(payload)
    implementers = _str_tuple(_need_list(payload, "implementer_model_ids"))
    registry = _registry()
    pairs = _candidates_of(payload, registry)
    models = {model for _provider, model in pairs}
    overlap = sorted(
        {name for name in implementers if name and name in models})
    coordinator = _coordinator()
    if overlap:
        coordinator.refuse_contributor("", tuple(overlap))
    pins = _record_pins_for_run(turn.run_id)
    if not pins:
        raise _WireError(404, "K03WIRE_FRESH_AUDIT_UNKNOWN_HASH",
                         "fresh-audit needs a product-recorded "
                         "contract_hash pin for this run: unknown-hash")
    if turn.contract_hash not in pins:
        raise _WireError(409, "K03WIRE_FRESH_AUDIT_STALE_HASH",
                         "fresh-audit contract_hash differs from the "
                         "product-recorded pin for this run: stale-hash")
    audit_id = coordinator.audit_with_fresh_auditor(turn)
    from agent_si.assurance import audit_records as _records

    stored = _records._fetch_record(audit_id)
    session_ref = getattr(stored, "context_session_ref", "") or ""
    return {"audit_id": audit_id, "audit_session_ref": session_ref}


def k03wire_pair_reuse(payload: dict[str, Any]) -> dict[str, Any]:
    """Record pair reuse, then re-audit; unrecorded reuse is refused."""
    from agent_si.assurance import audit_registry as _entries

    registry = _registry()
    decision_id: str | None = None
    raw = payload.get("decision")
    if raw is not None:
        if not isinstance(raw, dict):
            raise _WireError(400, "K03WIRE_FIELD_INVALID",
                             "pair_reuse decision must be a JSON object")
        decision_id = _need_text(raw, "decision_id", "decision decision_id")
        registry.record_pair_reuse(_entries.SourcingDecision(
            decision_id=decision_id,
            project_id=str(raw.get("project_id") or ""),
            scope=str(raw.get("scope") or ""),
            statement=str(raw.get("statement") or ""),
            reason=str(raw.get("reason") or ""),
            authority=str(raw.get("authority") or "USER"),
            decided_by=str(raw.get("decided_by") or ""),
            visible_to_user=bool(raw.get("visible_to_user", True)),
            user_resolution_ref=raw.get("user_resolution_ref"),
            created_at=_utcnow(),
        ))
    turn = _turn_of(payload)
    coordinator = _coordinator()
    audit_id = coordinator.audit_served_turn(turn)
    reused_id: str | None = None
    reuse_ref = payload.get("reuse_ref")
    if isinstance(reuse_ref, str) and reuse_ref.strip():
        reused_id = coordinator.reaudit(audit_id, reuse_ref.strip())
    return {
        "audit_id": audit_id,
        "reused_audit_id": reused_id,
        "pair_reuse_decision_id": decision_id,
    }


def k03wire_verify_run(payload: dict[str, Any]) -> dict[str, Any]:
    """Judge real tool rows and real files through the real checker."""
    from agent_si.assurance.verification import checker as _checker

    record = _checker.verify_run(
        project_dir=_need_text(payload, "project_dir", "project_dir"),
        tool_rows=list(_need_list(payload, "tool_rows")),
        criteria=list(_need_list(payload, "criteria")),
        project_id=_need_text(payload, "project_id", "project_id"),
        task_id=_need_text(payload, "task_id", "task_id"),
        run_id=_need_text(payload, "run_id", "run_id"),
        contract_hash=_need_text(payload, "contract_hash", "contract_hash"),
    )
    return {
        "verification_id": record.verification_id,
        "result": getattr(record.result, "value", str(record.result)),
    }


def k03wire_risk_defaults(payload: dict[str, Any]) -> dict[str, Any]:
    """Report the accepted-risk gate; off unless a user policy enables it."""
    raw = payload.get("policy_ref")
    policy_ref = raw.strip() if isinstance(raw, str) and raw.strip() else None
    gate = _coordinator().accepted_risk_allowed(policy_ref)
    return {"allowed": bool(gate.allowed), "policy_ref": gate.policy_ref}


def k03wire_close_stage(payload: dict[str, Any]) -> dict[str, Any]:
    """Close a stage with its audit; every close leaves a queryable row."""
    task_id = _need_text(payload, "task_id", "task_id")
    scope_id = _need_text(payload, "scope_id", "scope_id")
    audit_id = _need_text(payload, "audit_id", "audit_id")
    row_id = _coordinator().close_stage(task_id, scope_id, audit_id)
    return {
        "row_id": row_id,
        "task_id": task_id,
        "scope_id": scope_id,
        "audit_id": audit_id,
    }


def k03wire_sourcing_state(payload: dict[str, Any]) -> dict[str, Any]:
    """Report fail-closed sourcing; auditor-task-class selection is refused."""
    scope = _need_text(payload, "scope", "sourcing scope")
    registry = _registry()
    state = registry.sourcing_state(scope)
    raw_class = payload.get("task_class")
    task_class = (
        raw_class.strip() if isinstance(raw_class, str) and raw_class.strip()
        else "")
    implementers = _str_tuple(_need_list(payload, "implementer_model_ids"))
    pairs = _candidates_of(payload, registry)
    if not task_class and not pairs and not implementers:
        return {"scope": scope, "state": state}
    from agent_si.assurance import audit_registry as _entries

    try:
        selection = registry.select_auditor(
            task_class or "served-turn",
            implementers,
            str(payload.get("minimum_level") or "L2"),
        )
    except _entries.NoEligibleAuditorError as exc:
        return {
            "scope": scope,
            "state": "BLOCKED",
            "code": exc.code,
            "refused": ("auditor-task-class"
                        if (task_class or "") == "auditor"
                        else "no-eligible-auditor"),
        }
    return {
        "scope": scope,
        "state": "SOURCED",
        "auditor": {
            "provider_id": selection.auditor.provider_id,
            "model": selection.auditor.model,
            "session_ref": selection.auditor.session_ref,
        },
    }


def _refused(status: int, code: str, message: str) -> HTTPException:
    """Build one machine-readable refusal carrying its signal code."""
    return HTTPException(
        status_code=status, detail={"code": code, "message": message})


def _call(entry: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Run one entry; map the real errors to their HTTP refusals."""
    from agent_si.assurance import audit_coordinator as _coordinator_entries
    from agent_si.assurance import audit_registry as _registry_entries

    try:
        return entry(payload)
    except _WireError as exc:
        raise _refused(exc.status, exc.code, str(exc)) from None
    except _coordinator_entries.EmptyWorkError as exc:
        raise _refused(400, exc.code, str(exc)) from None
    except _coordinator_entries.ContributorInAuditorSetError as exc:
        raise _refused(409, exc.code, str(exc)) from None
    except PermissionError as exc:
        raise _refused(409, "PAIR_REUSE_REFUSED", str(exc)) from None
    except _registry_entries.NoEligibleAuditorError as exc:
        raise _refused(409, exc.code, str(exc)) from None
    except (ValueError, KeyError, TypeError) as exc:
        raise _refused(
            400, "K03WIRE_BAD_REQUEST", "%s: %s"
            % (type(exc).__name__, exc)) from None


def _bind(app: Any, method: str, path: str) -> Any:
    """Duck-type binder (same shape as the stage_runner mount)."""
    binder = None
    try:
        binder = app.get if method == "GET" else app.post
    except AttributeError:
        binder = None
    if binder is None:
        return app.route(path, methods=[method])
    return binder(path)


async def _post_body(request: Request) -> dict[str, Any]:
    """Read one JSON object POST body, tolerating missing/bad payloads."""
    try:
        data = await request.json()
    except Exception:
        data = None
    if not isinstance(data, dict):
        raise HTTPException(
            status_code=400,
            detail="k03wire needs a JSON object body",
        )
    return data


def _guard(request: Request) -> None:
    """Enforce the frozen USER_WRITE guard on POST lanes."""
    actor = (request.headers.get("x-actor") or "").strip()
    if not actor:
        raise HTTPException(
            status_code=401, detail="missing x-actor header")
    allowed = False
    try:
        allowed = bool(request.app.state.auth_hook(
            request.headers.get("x-ui-session-token"),
            actor,
            USER_WRITE,
        ))
    except Exception:
        allowed = False
    if not allowed:
        raise HTTPException(status_code=403, detail="forbidden")


def register_k03wire_assurance_routes(app: Any) -> Any:
    """Mount the eight K03WIRE assurance routes; returns the app."""

    @_bind(app, "POST", _SERVED_TURN_ROUTE)
    async def _k03wire_served_turn(request: Request) -> dict[str, Any]:
        _guard(request)
        return _call(k03wire_served_turn, await _post_body(request))

    _k03wire_served_turn.__annotations__ = {"request": Request}

    @_bind(app, "POST", _RUN_ROUTE)
    async def _k03wire_run(request: Request) -> dict[str, Any]:
        _guard(request)
        return _call(k03wire_run, await _post_body(request))

    _k03wire_run.__annotations__ = {"request": Request}

    @_bind(app, "POST", _FRESH_AUDIT_ROUTE)
    async def _k03wire_fresh_audit(request: Request) -> dict[str, Any]:
        _guard(request)
        return _call(k03wire_fresh_audit, await _post_body(request))

    _k03wire_fresh_audit.__annotations__ = {"request": Request}

    @_bind(app, "POST", _PAIR_REUSE_ROUTE)
    async def _k03wire_pair_reuse(request: Request) -> dict[str, Any]:
        _guard(request)
        return _call(k03wire_pair_reuse, await _post_body(request))

    _k03wire_pair_reuse.__annotations__ = {"request": Request}

    @_bind(app, "POST", _VERIFY_RUN_ROUTE)
    async def _k03wire_verify_run(request: Request) -> dict[str, Any]:
        _guard(request)
        return _call(k03wire_verify_run, await _post_body(request))

    _k03wire_verify_run.__annotations__ = {"request": Request}

    @_bind(app, "GET", _RISK_DEFAULTS_ROUTE)
    async def _k03wire_risk_defaults(request: Request) -> dict[str, Any]:
        return _call(k03wire_risk_defaults, dict(request.query_params))

    _k03wire_risk_defaults.__annotations__ = {"request": Request}

    @_bind(app, "POST", _CLOSE_STAGE_ROUTE)
    async def _k03wire_close_stage(request: Request) -> dict[str, Any]:
        _guard(request)
        return _call(k03wire_close_stage, await _post_body(request))

    _k03wire_close_stage.__annotations__ = {"request": Request}

    @_bind(app, "GET", _SOURCING_STATE_ROUTE)
    async def _k03wire_sourcing_state(request: Request) -> dict[str, Any]:
        return _call(k03wire_sourcing_state, dict(request.query_params))

    _k03wire_sourcing_state.__annotations__ = {"request": Request}

    return app
