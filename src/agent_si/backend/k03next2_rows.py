"""K03NEXT2 served rows (B0B-UNCOVERED_ARCH-740/741/745/746,
B0B-UNCOVERED_MVP_ACCEPT-33/111, B0B-SDK-104/109).

Served wiring only: register_k03next2_routes(app) adds six POST routes
to the seam app (same addition-only pattern as the k03next lane mount).
Every handler drives the real assurance entries and nothing else:
AuditorRegistry select/is_eligible/register/resolve_sourcing/
sourcing_state/check_separate_model plus AuditCoordinator
classify_failure, handle_turn_cap/handle_invalid_output,
build_deliverable_schema and audit_served_turn/confirm_recovery_leg.
Only the recovery route mints an audit, and only through the real
audit_served_turn entry before confirming that same leg; the gate
itself mints no audit records. The gate answers BLOCKED while sourcing
is parked or no auditor is eligible, and SOURCED only through a
USER-resolved scope with an eligible auditor outside the implementer
set.

Mount contract (CODER-1 KNext2 owns this file; app.py mounts it):
  from agent_si.backend import k03next2_rows
  k03next2_rows.register_k03next2_routes(app)
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request

from agent_si.assurance import audit_coordinator as _chain_coordinator
from agent_si.assurance import audit_records as _chain_records
from agent_si.assurance import audit_registry as _chain_registry
from agent_si.assurance.verification import checker as _verify_checker

_GATE_ROUTE = "/api/v1/k03next2/sourcing_gate"
_CLASSIFY_ROUTE = "/api/v1/k03next2/classify_failure"
_HANDLERS_ROUTE = "/api/v1/k03next2/turn_handlers"
_SCHEMA_ROUTE = "/api/v1/k03next2/deliverable_schema"
_RECOVERY_ROUTE = "/api/v1/k03next2/recovery_confirm"
_READONLY_ROUTE = "/api/v1/k03next2/verifier_readonly"
_DEFAULT_TASK_CLASS = "served-turn"
_DEFAULT_MINIMUM_LEVEL = "L2"
_DEFAULT_SCOPE = "k03next2/sourcing/default"


class _Coordinator(_chain_coordinator.AuditCoordinator):
    """Concrete binding of the real check entries; adds no behavior."""


class _Registry(_chain_registry.AuditorRegistry):
    """Concrete binding of the real sourcing entries; adds no behavior."""


def _need_text(value: Any, what: str) -> str:
    """Return one required non-blank text field, else an honest 400."""
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(
            status_code=400,
            detail="k03next2 gate needs a non-empty %s" % what,
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
            detail="k03next2 gate needs %s as a JSON list" % name,
        )
    return list(value)


def _candidates(raw_values: list[Any]) -> list[Any]:
    """Validate candidate payloads into real AuditorCandidate entries."""
    out = []
    for position, raw in enumerate(raw_values):
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
        cap = raw.get("capability_evidence_refs")
        if cap is None:
            refs: tuple[str, ...] = ()
        elif isinstance(cap, list):
            refs = tuple(str(item) for item in cap)
        else:
            raise HTTPException(
                status_code=400,
                detail="auditor candidate capability_evidence_refs "
                "must be a JSON list",
            )
        out.append(_chain_registry.AuditorCandidate(
            provider_id=provider_id,
            provider_instance=(
                instance if isinstance(instance, str) else None
            ),
            model=model,
            capability_evidence_refs=refs,
            registered_at="",
        ))
    return out


def _eligibility(registry: _Registry,
                 entries: list[Any]) -> list[dict[str, Any]]:
    """Per-candidate eligibility from the real registry entry."""
    return [{
        "provider_id": entry.provider_id,
        "model": entry.model,
        "eligible": bool(registry.is_eligible(
            entry.provider_id, entry.model)),
    } for entry in entries]


def _resolution(body: dict[str, Any], scope: str) -> Any:
    """Apply the caller USER resolution, if one was presented."""
    raw = body.get("user_resolution")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise HTTPException(
            status_code=400,
            detail="k03next2 gate needs user_resolution as a JSON object",
        )
    decision = _chain_registry.SourcingDecision(
        decision_id=_need_text(
            raw.get("decision_id"), "user_resolution decision_id"),
        project_id=str(raw.get("project_id") or ""),
        scope=str(raw.get("scope") or scope),
        statement=str(raw.get("statement") or ""),
        reason=str(raw.get("reason") or ""),
        authority=str(raw.get("authority") or _chain_registry.USER_AUTHORITY),
        decided_by=str(raw.get("decided_by") or ""),
        visible_to_user=bool(raw.get("visible_to_user", True)),
        user_resolution_ref=raw.get("user_resolution_ref"),
        created_at="",
    )
    registry = _Registry()
    return registry.resolve_sourcing(decision)


def _resolve_options(scope: str) -> list[str]:
    """Documented options for leaving the parked BLOCKED state."""
    return [
        "record a USER sourcing decision resolving scope %r "
        "through resolve_sourcing" % scope,
        "register capability evidence refs for the chosen provider "
        "and re-run sourcing",
        "leave the task parked: sourcing stays BLOCKED until the USER "
        "resolves it",
    ]


def register_k03next2_routes(app: Any) -> Any:
    """Mount the K03NEXT2 gates plus checks; returns app."""

    @app.post(_GATE_ROUTE)
    async def k03next2_sourcing_gate(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = None
        if not isinstance(body, dict):
            raise HTTPException(
                status_code=400,
                detail="k03next2 gate needs a JSON object body",
            )
        scope = body.get("scope")
        scope = scope.strip() if isinstance(scope, str) and scope.strip() \
            else _DEFAULT_SCOPE
        run_id = body.get("run_id")
        run_id = run_id.strip() if isinstance(run_id, str) and run_id.strip() \
            else None
        entries = _candidates(_need_list(body, "auditor_candidates"))
        implementers = tuple(
            str(item) for item in _need_list(body, "implementer_model_ids")
        )
        task_class = body.get("task_class") or _DEFAULT_TASK_CLASS
        minimum_level = body.get("minimum_level") or _DEFAULT_MINIMUM_LEVEL
        if not isinstance(task_class, str) or not task_class.strip():
            raise HTTPException(
                status_code=400,
                detail="k03next2 gate needs a non-empty task_class",
            )
        if not isinstance(minimum_level, str) or not minimum_level.strip():
            raise HTTPException(
                status_code=400,
                detail="k03next2 gate needs a non-empty minimum_level",
            )
        decision = _resolution(body, scope)
        decision_id = getattr(decision, "decision_id", None)
        registry = _Registry()
        for entry in entries:
            registry.register_candidate(entry)
        eligibility = _eligibility(registry, entries)
        state = registry.sourcing_state(scope)
        if state != "RESOLVED":
            return {
                "ok": False,
                "disposition": "BLOCKED",
                "code": "SOURCING_UNRESOLVED",
                "pass_prohibited": True,
                "audit_id": None,
                "auditor": None,
                "scope": scope,
                "sourcing_state": state,
                "sourcing_decision_id": decision_id,
                "eligibility": eligibility,
                "separate_model": None,
                "options": _resolve_options(scope),
                "run_id": run_id,
            }
        try:
            selection = registry.select_auditor(
                task_class.strip(), implementers, minimum_level.strip())
        except _chain_registry.NoEligibleAuditorError as exc:
            first_model = entries[0].model if entries else None
            separate = (
                registry.check_separate_model(first_model, implementers)
                if first_model is not None else None
            )
            return {
                "ok": False,
                "disposition": "BLOCKED",
                "code": exc.code,
                "pass_prohibited": True,
                "audit_id": None,
                "auditor": None,
                "scope": scope,
                "sourcing_state": state,
                "sourcing_decision_id": decision_id,
                "eligibility": eligibility,
                "separate_model": separate,
                "options": _resolve_options(scope),
                "run_id": run_id,
            }
        return {
            "ok": True,
            "disposition": "SOURCED",
            "code": None,
            "pass_prohibited": False,
            "audit_id": None,
            "auditor": {
                "provider_id": selection.auditor.provider_id,
                "model": selection.auditor.model,
                "session_ref": selection.auditor.session_ref,
            },
            "independence_level": selection.independence_level,
            "separate_model": registry.check_separate_model(
                selection.auditor.model, implementers),
            "scope": scope,
            "sourcing_state": state,
            "sourcing_decision_id": selection.sourcing_decision_ref,
            "eligibility": eligibility,
            "options": [],
            "run_id": run_id,
        }

    @app.post(_CLASSIFY_ROUTE)
    async def k03next2_classify_failure(
            request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = None
        if not isinstance(body, dict):
            raise HTTPException(
                status_code=400,
                detail="k03next2 classify needs a JSON object body",
            )
        signal = body.get("signal")
        if not isinstance(signal, str):
            raise HTTPException(
                status_code=400,
                detail="k03next2 classify needs signal as a string",
            )
        severity = body.get("severity")
        severity = severity if isinstance(severity, str) and severity.strip() \
            else "HIGH"
        failure = _Coordinator().classify_failure(signal, severity.strip())
        return {
            "failure_class": failure.value
            if hasattr(failure, "value") else str(failure),
            "signal": signal,
            "severity": severity.strip(),
        }

    @app.post(_HANDLERS_ROUTE)
    async def k03next2_turn_handlers(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = None
        if not isinstance(body, dict):
            raise HTTPException(
                status_code=400,
                detail="k03next2 handlers need a JSON object body",
            )
        handler = body.get("handler")
        if handler == "turn_cap":
            ref = _Coordinator().handle_turn_cap(
                _need_text(body.get("turn_ref"), "turn_ref"),
                _need_text(body.get("budget_state_ref"),
                           "budget_state_ref"),
            )
            return {"handler": "turn_cap", "ref": ref}
        if handler == "invalid_output":
            ref = _Coordinator().handle_invalid_output(
                _need_text(body.get("output_ref"), "output_ref"),
                _need_text(body.get("reason"), "reason"),
            )
            return {"handler": "invalid_output", "ref": ref}
        raise HTTPException(
            status_code=400,
            detail="k03next2 handlers need handler turn_cap or "
            "invalid_output",
        )

    @app.post(_SCHEMA_ROUTE)
    async def k03next2_deliverable_schema(
            request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = None
        if not isinstance(body, dict):
            raise HTTPException(
                status_code=400,
                detail="k03next2 schema needs a JSON object body",
            )
        schema_id = _need_text(body.get("schema_id"), "schema_id")
        raw_outputs = body.get("expected_outputs")
        if not isinstance(raw_outputs, list):
            raise HTTPException(
                status_code=400,
                detail="k03next2 schema needs expected_outputs as a "
                "JSON list",
            )
        outputs = tuple(str(item) for item in raw_outputs)
        evidence_required = body.get("evidence_required")
        if not isinstance(evidence_required, bool):
            raise HTTPException(
                status_code=400,
                detail="k03next2 schema needs evidence_required as a "
                "JSON boolean",
            )
        schema = _Coordinator().build_deliverable_schema(
            schema_id, outputs, evidence_required)
        return {
            "schema_id": schema.schema_id,
            "version": schema.version,
            "expected_outputs": list(schema.expected_outputs),
            "evidence_required": schema.evidence_required,
            "hash": schema.hash,
            "created_at": schema.created_at,
        }

    register_mh4_readonly_route(app)
    _register_recovery_route(app)
    return app


def _tree_snapshot(base: str) -> tuple[list, str]:
    """Snapshot a project tree: canonical listing plus its sha256 digest."""
    import hashlib as _snapshot_hashlib
    import os as _snapshot_os

    rows: list = []
    for root, dirs, files in _snapshot_os.walk(base):
        dirs.sort()
        for name in sorted(files):
            full = _snapshot_os.path.join(root, name)
            rel = _snapshot_os.path.relpath(full, base)
            try:
                with open(full, "rb") as handle:
                    digest = _snapshot_hashlib.sha256(
                        handle.read()).hexdigest()
                stat = _snapshot_os.stat(full)
                rows.append((rel, stat.st_size, stat.st_mtime_ns, digest))
            except OSError:
                rows.append((rel, -1, -1, "unreadable"))
    canon = "\n".join("%s|%d|%d|%s" % item for item in rows)
    return rows, _snapshot_hashlib.sha256(
        canon.encode("utf-8")).hexdigest()


def _ref_list(body: dict[str, Any], name: str) -> tuple[str, ...]:
    """One body field as a tuple of strings (missing reads as empty)."""
    return tuple(str(item) for item in _need_list(body, name))


def _readonly_guard(write_set: tuple[str, ...]) -> None:
    """Reject any verifier write attempt with the named MH-4 refusal."""
    if write_set:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "VERIFIER_WRITE_REJECTED",
                "detail": "verifier/auditor runs read-only: "
                "write attempt rejected",
                "write_set": list(write_set),
            },
        )


def _readonly_audit(
    coordinator: _Coordinator,
    *,
    project_id: str,
    task_id: str,
    run_id: str,
    contract_hash: str,
    turn_ref: str,
    work_refs: tuple[str, ...],
    artifact_refs: tuple[str, ...],
    evidence_refs: tuple[str, ...],
    producer_refs: tuple[str, ...],
) -> tuple[str, str, bool]:
    """Mint one audit through the real entry; prove disjoint sessions."""
    served = _chain_coordinator.ServedTurn(
        turn_ref=turn_ref,
        project_id=project_id,
        task_id=task_id,
        run_id=run_id,
        work_refs=work_refs,
        artifact_refs=artifact_refs,
        evidence_refs=evidence_refs,
        producer_session_refs=producer_refs,
        contract_hash=contract_hash,
    )
    audit_id = coordinator.audit_served_turn(served)
    stored = _chain_records._fetch_record(audit_id)
    auditor_session = (
        str(stored.context_session_ref) if stored is not None else ""
    )
    return audit_id, auditor_session, auditor_session not in set(
        producer_refs)


def register_mh4_readonly_route(app: Any) -> Any:
    """Mount the MH-4 read-only verifier/auditor proof route.

    Served wiring only: POST /api/v1/k03next2/verifier_readonly drives
    the real verification checker entry (verify_run, which only reads
    the project dir), the real R-304 file-contract entry (judging the
    verifier write set, which must be empty) and the real audit entry
    (audit_served_turn plus the stored record proving the producer
    session set and the auditor context session are disjoint). Any
    presented verifier write attempt is refused before anything runs.
    Called by register_k03next2_routes.
    """

    @app.post(_READONLY_ROUTE)
    async def k03next2_verifier_readonly(
            request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = None
        if not isinstance(body, dict):
            raise HTTPException(
                status_code=400,
                detail="k03next2 verifier_readonly needs a JSON "
                "object body",
            )
        project_id = _need_text(body.get("project_id"), "project_id")
        task_id = _need_text(body.get("task_id"), "task_id")
        run_id = _need_text(body.get("run_id"), "run_ref")
        contract_hash = _need_text(
            body.get("contract_hash"), "contract_hash")
        project_dir = _need_text(body.get("project_dir"), "project_dir")
        _readonly_guard(tuple(_ref_list(body, "attempted_writes")))
        tool_rows = tuple(_need_list(body, "tool_rows"))
        criteria = tuple(_need_list(body, "criteria"))
        files_read = _ref_list(body, "files_read")
        producer_refs = _ref_list(body, "producer_session_refs")
        work_refs = _ref_list(body, "work_refs")
        artifact_refs = _ref_list(body, "artifact_refs")
        evidence_refs = _ref_list(body, "evidence_refs")
        if not work_refs and not artifact_refs:
            raise HTTPException(
                status_code=400,
                detail="k03next2 verifier_readonly needs work_refs "
                "or artifact_refs",
            )
        turn_ref = body.get("turn_ref")
        turn_ref = turn_ref.strip() if isinstance(
            turn_ref, str) and turn_ref.strip() else (
                "turn-mh4-%s" % run_id)
        before_rows, before_hash = _tree_snapshot(project_dir)
        record = _verify_checker.verify_run(
            project_dir=project_dir,
            tool_rows=tool_rows,
            criteria=criteria,
            project_id=project_id,
            task_id=task_id,
            run_id=run_id,
            contract_hash=contract_hash,
        )
        _after_rows, after_hash = _tree_snapshot(project_dir)
        from agent_si.backend.app import runner_contract_verdict as _contract_entry
        contract = _contract_entry(
            project_dir=project_dir,
            tool_rows=tool_rows,
            files_read=list(files_read),
            files_written=(),
        )
        audit_id, auditor_session, disjoint = _readonly_audit(
            _Coordinator(),
            project_id=project_id,
            task_id=task_id,
            run_id=run_id,
            contract_hash=contract_hash,
            turn_ref=turn_ref,
            work_refs=work_refs,
            artifact_refs=artifact_refs,
            evidence_refs=evidence_refs,
            producer_refs=producer_refs,
        )
        return {
            "verification_result": record.result.value,
            "verification_id": record.verification_id,
            "tree_hash_before": before_hash,
            "tree_hash_after": after_hash,
            "tree_files": len(before_rows),
            "read_only": before_hash == after_hash,
            "contract_verdict": contract["verdict"],
            "checked_read": contract["checked_read"],
            "checked_written": contract["checked_written"],
            "write_set": [],
            "audit_id": audit_id,
            "auditor_session_ref": auditor_session,
            "producer_session_refs": list(producer_refs),
            "producer_auditor_disjoint": disjoint,
            "run_id": run_id,
        }

    return app


def _register_recovery_route(app: Any) -> Any:
    """Bind the recovery-confirm route; called by the lane register."""

    @app.post(_RECOVERY_ROUTE)
    async def k03next2_recovery_confirm(
            request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = None
        if not isinstance(body, dict):
            raise HTTPException(
                status_code=400,
                detail="k03next2 recovery needs a JSON object body",
            )
        run_ref = _need_text(body.get("run_ref"), "run_ref")
        verification = body.get("verification_ref")
        verification_ref = verification if isinstance(verification, str) \
            else ""
        turn = body.get("turn")
        if not isinstance(turn, dict):
            raise HTTPException(
                status_code=400,
                detail="k03next2 recovery needs turn as a JSON object",
            )
        coordinator = _Coordinator()
        served = _chain_coordinator.ServedTurn(
            turn_ref=_need_text(turn.get("turn_ref"), "turn turn_ref"),
            project_id=_need_text(turn.get("project_id"),
                                  "turn project_id"),
            task_id=_need_text(turn.get("task_id"), "turn task_id"),
            run_id=str(turn.get("run_id") or run_ref),
            work_refs=tuple(
                str(item) for item in _need_list(turn, "work_refs")),
            artifact_refs=tuple(
                str(item) for item in _need_list(turn, "artifact_refs")),
            evidence_refs=tuple(
                str(item) for item in _need_list(turn, "evidence_refs")),
            producer_session_refs=tuple(
                str(item) for item in _need_list(
                    turn, "producer_session_refs")),
            contract_hash=_need_text(turn.get("contract_hash"),
                                     "turn contract_hash"),
        )
        audit_id = coordinator.audit_served_turn(served)
        confirmation = coordinator.confirm_recovery_leg(
            run_ref, verification_ref, audit_id)
        return {
            "audit_id": audit_id,
            "run_ref": confirmation.run_ref,
            "verification_ref": verification_ref,
            "check_ref": confirmation.check_ref,
            "confirmed": bool(confirmation.confirmed),
            "confirmed_by": confirmation.confirmed_by,
            "audit_ref": getattr(confirmation, "audit_ref", audit_id),
        }

    return app
