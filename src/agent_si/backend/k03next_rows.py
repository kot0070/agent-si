"""K03NEXT served sourcing rows (B0B-BP07-18/20/53/54, B0B-SDK-107,
B0B-UNCOVERED_ARCH-652/653/654).

Served wiring only: register_k03next_routes(app) adds two POST routes
to the seam app (same addition-only pattern as the kb_routes and
assurance mounts). Both handlers drive the real assurance entries and
nothing else: AuditorRegistry select/is_eligible/register/note/
check_separate_model plus resolve_sourcing/sourcing_state for the
sourcing gate, and AuditCoordinator.check_semantic_and_security for
the semantic/security verdict. The gate mints no audit records; it
answers BLOCKED while sourcing is parked or no auditor is eligible,
and SOURCED only through a USER-resolved scope with an eligible
auditor outside the implementer set.

Mount contract (CODER-1 KNext owns this file; app.py mounts it):
  from agent_si.backend import k03next_rows
  k03next_rows.register_k03next_routes(app)
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request

from agent_si.assurance import audit_coordinator as _chain_coordinator
from agent_si.assurance import audit_registry as _chain_registry

_GATE_ROUTE = "/api/v1/k03next/sourcing_gate"
_SEMANTIC_ROUTE = "/api/v1/k03next/semantic_security"
_DEFAULT_TASK_CLASS = "served-turn"
_DEFAULT_MINIMUM_LEVEL = "L2"
_DEFAULT_SCOPE = "k03next/sourcing/default"


class _Coordinator(_chain_coordinator.AuditCoordinator):
    """Concrete binding of the real check entries; adds no behavior."""


class _Registry(_chain_registry.AuditorRegistry):
    """Concrete binding of the real sourcing entries; adds no behavior."""


def _need_text(value: Any, what: str) -> str:
    """Return one required non-blank text field, else an honest 400."""
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(
            status_code=400,
            detail="k03next gate needs a non-empty %s" % what,
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
            detail="k03next gate needs %s as a JSON list" % name,
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
            detail="k03next gate needs user_resolution as a JSON object",
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


def register_k03next_routes(app: Any) -> Any:
    """Mount the K03NEXT sourcing gate plus semantic check; returns app."""

    @app.post(_GATE_ROUTE)
    async def k03next_sourcing_gate(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = None
        if not isinstance(body, dict):
            raise HTTPException(
                status_code=400,
                detail="k03next gate needs a JSON object body",
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
                detail="k03next gate needs a non-empty task_class",
            )
        if not isinstance(minimum_level, str) or not minimum_level.strip():
            raise HTTPException(
                status_code=400,
                detail="k03next gate needs a non-empty minimum_level",
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

    @app.post(_SEMANTIC_ROUTE)
    async def k03next_semantic_security(
            request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = None
        if not isinstance(body, dict):
            raise HTTPException(
                status_code=400,
                detail="k03next semantic check needs a JSON object body",
            )
        criterion_refs = tuple(
            str(item) for item in _need_list(body, "criterion_refs")
        )
        evidence_refs = tuple(
            str(item) for item in _need_list(body, "evidence_refs")
        )
        verdict = _Coordinator().check_semantic_and_security(
            criterion_refs, evidence_refs)
        return {
            "verdict": verdict,
            "checked_criteria": len(criterion_refs),
            "checked_evidence": len(evidence_refs),
        }

    return app
