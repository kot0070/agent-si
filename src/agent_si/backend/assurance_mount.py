"""K03MNT1 served assurance mount: verify, fresh audit, close over HTTP.

register_assurance_routes(app) adds POST /api/v1/assurance/finalize to
the seam app (same addition-only pattern as the kb_routes and
stage_runner mounts). The handler drives the real assurance chain and
nothing else: agent_si.assurance.verification.checker.verify_run for
the verify leg, AuditCoordinator.audit_with_fresh_auditor for the
audit leg with a fresh auditor session per call,
AuditorRegistry.select_auditor plus record_pair_reuse for sourcing,
and AuditCoordinator.close_stage for the close row. Failed
verification never audits, a contributor found in the auditor set is
refused through the real refuse_contributor entry, no eligible
auditor maps to BLOCKED, and persisted audit verdicts are reported
unchanged. The audit id, verdict and close row are recorded onto the
task turns so the existing task read route exposes them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, Request

from agent_si.assurance import audit_coordinator as _chain_coordinator
from agent_si.assurance import audit_records as _chain_records
from agent_si.assurance import audit_registry as _chain_registry
from agent_si.assurance.verification import checker as _chain_checker
from agent_si.backend import task_turns as _turns
from agent_si.backend.read_routes import repos_for as _repos_for

#: Frozen write guard action shared with the seam app.
USER_WRITE = "USER_WRITE"

_MOUNT_ROUTE = "/api/v1/assurance/finalize"
_TURN_PLAN = "assurance-finalize"
_NO_AUDIT_ACTION = "no-audit"
_DEFAULT_TASK_CLASS = "served-turn"
_DEFAULT_MINIMUM_LEVEL = "L2"


class _Coordinator(_chain_coordinator.AuditCoordinator):
    """Concrete binding of the real audit entries; adds no behavior."""


class _Registry(_chain_registry.AuditorRegistry):
    """Concrete binding of the real sourcing entries; adds no behavior."""


def _utcnow() -> str:
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


def _refused_detail(code: str, message: str) -> dict[str, str]:
    """Machine-readable refusal body carrying the frozen signal code."""
    return {"code": code, "message": message}


def _need_id(body: dict[str, Any], name: str) -> str:
    """Return one required non-blank request id, else an honest 400."""
    value = body.get(name)
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(
            status_code=400,
            detail="finalize needs a non-empty %s" % name,
        )
    return value.strip()


def _need_list(body: dict[str, Any], name: str) -> list[Any]:
    """Return one optional request list (missing reads as empty)."""
    value = body.get(name)
    if value is None:
        return []
    if not isinstance(value, list):
        raise HTTPException(
            status_code=400,
            detail="finalize needs %s as a JSON list" % name,
        )
    return list(value)


def _need_text(value: Any, what: str) -> str:
    """Return one required non-blank text field, else an honest 400."""
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(
            status_code=400,
            detail="finalize needs a non-empty %s" % what,
        )
    return value.strip()


def register_assurance_routes(app: Any) -> Any:
    """Mount the served assurance finalize route; returns the app."""

    @app.post(_MOUNT_ROUTE)
    async def assurance_finalize(request: Request) -> dict[str, Any]:
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
        try:
            body = await request.json()
        except Exception:
            body = None
        if not isinstance(body, dict):
            raise HTTPException(
                status_code=400,
                detail="finalize needs a JSON object body",
            )
        project_id = _need_id(body, "project_id")
        task_id = _need_id(body, "task_id")
        run_id = _need_id(body, "run_id")
        contract_hash = _need_id(body, "contract_hash")
        _projects, tasks = _repos_for(request.app)
        if tasks.load(task_id) is None:
            raise HTTPException(
                status_code=404,
                detail="unknown task %r" % (task_id,),
            )
        project_dir = body.get("project_dir")
        if not isinstance(project_dir, str) or not project_dir.strip():
            fallback = getattr(request.app.state, "k02r3_store_dir", None)
            project_dir = fallback if isinstance(fallback, str) else ""
        if not project_dir.strip():
            raise HTTPException(
                status_code=400,
                detail="finalize needs a project_dir or a bound store dir",
            )
        project_dir = project_dir.strip()
        work_refs = [str(item) for item in _need_list(body, "work_refs")]
        artifact_refs = [
            str(item) for item in _need_list(body, "artifact_refs")
        ]
        evidence_refs = [
            str(item) for item in _need_list(body, "evidence_refs")
        ]
        producer_refs = [
            str(item) for item in _need_list(body, "producer_session_refs")
        ]
        tool_rows = _need_list(body, "tool_rows")
        criteria = _need_list(body, "criteria")
        for position, criterion in enumerate(criteria):
            if not isinstance(criterion, dict):
                raise HTTPException(
                    status_code=400,
                    detail="criterion %d must be a JSON object" % position,
                )
            _need_text(criterion.get("ac_id"), "criterion ac_id")
        if not work_refs and not artifact_refs:
            raise HTTPException(
                status_code=400,
                detail=_refused_detail(
                    _chain_coordinator.EmptyWorkError.code,
                    "served finalize carries no work; empty work fails",
                ),
            )
        registry = _Registry()
        pair_decision_id: str | None = None
        reuse = body.get("pair_reuse")
        if reuse is not None:
            if not isinstance(reuse, dict):
                raise HTTPException(
                    status_code=400,
                    detail="pair_reuse must be a JSON object",
                )
            pair_decision_id = _need_text(
                reuse.get("decision_id"), "pair_reuse decision_id")
            registry.record_pair_reuse(
                _chain_registry.SourcingDecision(
                    decision_id=pair_decision_id,
                    project_id=project_id,
                    scope=str(reuse.get("scope") or ""),
                    statement=str(reuse.get("statement") or ""),
                    reason=str(reuse.get("reason") or ""),
                    authority=str(reuse.get("authority") or "USER"),
                    decided_by=str(reuse.get("decided_by") or actor),
                    visible_to_user=bool(
                        reuse.get("visible_to_user", True)),
                    user_resolution_ref=reuse.get("user_resolution_ref"),
                    created_at=_utcnow(),
                )
            )
        try:
            verification = _chain_checker.verify_run(
                project_dir=project_dir,
                tool_rows=list(tool_rows),
                criteria=list(criteria),
                project_id=project_id,
                task_id=task_id,
                run_id=run_id,
                contract_hash=contract_hash,
            )
        except Exception as exc:
            _turns.record_turn(
                task_id,
                _TURN_PLAN,
                _NO_AUDIT_ACTION,
                "phase=VERIFY_REFUSED verification=none result=ERROR "
                "note=%s: %s" % (type(exc).__name__, exc),
            )
            return {
                "ok": False,
                "phase": "VERIFY_REFUSED",
                "verification_id": None,
                "verification_result": "ERROR",
                "audit_id": None,
                "verdict": None,
                "close_row_id": None,
                "pair_reuse_decision_id": pair_decision_id,
            }
        verification_id = verification.verification_id
        verification_result = getattr(
            verification.result, "value", str(verification.result))
        if verification_result != "PASS":
            _turns.record_turn(
                task_id,
                _TURN_PLAN,
                _NO_AUDIT_ACTION,
                "phase=VERIFY_REFUSED verification=%s result=%s"
                % (verification_id, verification_result),
            )
            return {
                "ok": False,
                "phase": "VERIFY_REFUSED",
                "verification_id": verification_id,
                "verification_result": verification_result,
                "audit_id": None,
                "verdict": None,
                "close_row_id": None,
                "pair_reuse_decision_id": pair_decision_id,
            }
        implementers = [
            str(item)
            for item in _need_list(body, "implementer_model_ids")
        ]
        raw_candidates = _need_list(body, "auditor_candidates")
        coordinator = _Coordinator()
        for position, raw in enumerate(raw_candidates):
            if not isinstance(raw, dict):
                raise HTTPException(
                    status_code=400,
                    detail="auditor candidate %d must be a JSON object"
                    % position,
                )
            provider_id = _need_text(
                raw.get("provider_id"), "auditor candidate provider_id")
            model = _need_text(raw.get("model"), "auditor candidate model")
            instance = raw.get("provider_instance")
            cap_refs = tuple(
                str(item)
                for item in _need_list(raw, "capability_evidence_refs")
            )
            registry.register_candidate(
                _chain_registry.AuditorCandidate(
                    provider_id=provider_id,
                    provider_instance=(
                        instance if isinstance(instance, str) else None
                    ),
                    model=model,
                    capability_evidence_refs=cap_refs,
                    registered_at="",
                )
            )
        auditor_models = {
            str(raw.get("model", "")).strip()
            for raw in raw_candidates
            if isinstance(raw, dict)
        }

        def _refuse(refs: tuple[str, ...]) -> None:
            """Refuse through the real entry, record it, answer 409."""
            try:
                coordinator.refuse_contributor("", tuple(refs))
            except (
                _chain_coordinator.ContributorInAuditorSetError
            ) as exc:
                _turns.record_turn(
                    task_id,
                    _TURN_PLAN,
                    _NO_AUDIT_ACTION,
                    "phase=REFUSED code=%s contributors=%s"
                    % (exc.code, ",".join(tuple(refs))),
                )
                raise HTTPException(
                    status_code=409,
                    detail=_refused_detail(exc.code, str(exc)),
                ) from None

        overlap = sorted(
            {name for name in implementers if name and name in auditor_models}
        )
        if overlap:
            _refuse(tuple(overlap))
        task_class = body.get("task_class") or _DEFAULT_TASK_CLASS
        minimum_level = body.get("minimum_level") or _DEFAULT_MINIMUM_LEVEL
        if not isinstance(task_class, str) or not task_class.strip():
            raise HTTPException(
                status_code=400,
                detail="finalize needs a non-empty task_class",
            )
        if not isinstance(minimum_level, str) or not minimum_level.strip():
            raise HTTPException(
                status_code=400,
                detail="finalize needs a non-empty minimum_level",
            )
        try:
            selection = registry.select_auditor(
                task_class.strip(),
                tuple(implementers),
                minimum_level.strip(),
            )
        except _chain_registry.NoEligibleAuditorError as exc:
            _turns.record_turn(
                task_id,
                _TURN_PLAN,
                _NO_AUDIT_ACTION,
                "phase=BLOCKED code=%s verification=%s"
                % (exc.code, verification_id),
            )
            return {
                "ok": False,
                "phase": "BLOCKED",
                "code": exc.code,
                "verification_id": verification_id,
                "verification_result": verification_result,
                "audit_id": None,
                "verdict": None,
                "close_row_id": None,
                "pair_reuse_decision_id": pair_decision_id,
            }
        if not registry.check_separate_model(
            selection.auditor.model, tuple(implementers)
        ):
            _refuse((selection.auditor.model,))
        turn = _chain_coordinator.ServedTurn(
            turn_ref=run_id,
            project_id=project_id,
            task_id=task_id,
            run_id=run_id,
            work_refs=tuple(work_refs),
            artifact_refs=tuple(artifact_refs),
            evidence_refs=tuple(evidence_refs),
            producer_session_refs=tuple(producer_refs),
            contract_hash=contract_hash,
        )
        audit_id = coordinator.audit_with_fresh_auditor(turn)
        scope = body.get("scope_id")
        if not isinstance(scope, str) or not scope.strip():
            scope = "%s/%s/%s" % (project_id, task_id, contract_hash)
        else:
            scope = scope.strip()
        row_id = coordinator.close_stage(task_id, scope, audit_id)
        stored = _chain_records._fetch_record(audit_id)
        verdict = getattr(
            getattr(stored, "result", None), "value", None) or "UNKNOWN"
        audit_session = getattr(stored, "context_session_ref", "") or ""
        _turns.record_turn(
            task_id,
            _TURN_PLAN,
            audit_id,
            "phase=AUDIT_REFUSED verification=%s verdict=%s close=%s "
            "auditor=%s session=%s"
            % (
                verification_id,
                verdict,
                row_id,
                selection.auditor.model,
                audit_session,
            ),
        )
        return {
            "ok": False,
            "phase": "AUDIT_REFUSED",
            "verification_id": verification_id,
            "verification_result": verification_result,
            "audit_id": audit_id,
            "auditor": {
                "provider_id": selection.auditor.provider_id,
                "model": selection.auditor.model,
                "session_ref": selection.auditor.session_ref,
            },
            "audit_session_ref": audit_session,
            "verdict": verdict,
            "close_row_id": row_id,
            "implementer_model_ids": implementers,
            "pair_reuse_decision_id": pair_decision_id,
        }

    return app
