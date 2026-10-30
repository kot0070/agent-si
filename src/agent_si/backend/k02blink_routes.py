"""K02OPEN1B served blink: early-start read plus link-check close.

Rows 101+102. GET /k02open1b/early-start answers whether the stored
gate plus audit refs both resolve to PASS with overlap on; POST
/k02open1b/link-check closes the joint verdict and stamps the
linkcheck marker. Reads stay open; writes keep the frozen USER_WRITE
guard (401 missing x-actor, 403 bad token). Gate plus audit data come
from the module registries (never a new store).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from agent_si.backend.orchestration.gates import (
    _AUDIT_BY_ID,
    _GATE_BY_ID,
    can_close,
)

router = APIRouter()

#: Overlap values that switch early-start off (absent means on).
_OVERLAP_OFF = frozenset({"false", "0", "off", "no"})


def _overlap_on(raw: Any) -> bool:
    if raw is None:
        return True
    return str(raw).strip().lower() not in _OVERLAP_OFF


def _k02blink_require_writer(request: Request) -> str:
    from agent_si.backend import chat_stream as _wire_chat
    from agent_si.backend.app import USER_WRITE

    actor = (request.headers.get("x-actor") or "").strip()
    if not actor:
        raise HTTPException(
            status_code=401,
            detail=_wire_chat.http_error_detail(
                _wire_chat.CHAT_ACTOR_MISSING,
                "missing x-actor header"))
    check_auth = request.app.state.auth_hook
    if not check_auth(request.headers.get("x-ui-session-token"),
                      actor, USER_WRITE):
        raise HTTPException(
            status_code=403,
            detail=_wire_chat.http_error_detail(
                _wire_chat.CHAT_FORBIDDEN, "forbidden"))
    return actor


@router.get("/k02open1b/early-start")
def k02blink_early_start(gate_ref: str = "",
                         audit_ref: str = "",
                         overlap: str | None = None) -> dict[str, Any]:
    """Serve the early-start decision (open read, never auth)."""
    allowed = _overlap_on(overlap)
    if allowed:
        ok, _ = can_close(_GATE_BY_ID.get(gate_ref),
                          _AUDIT_BY_ID.get(audit_ref))
        allowed = ok
    return {"allowed": allowed}


@router.post("/k02open1b/link-check")
def k02blink_link_check(payload: dict[str, Any],
                        request: Request) -> dict[str, Any]:
    """Serve the joint link-check close (USER_WRITE guard)."""
    _k02blink_require_writer(request)
    delta = payload.get("delta")
    if not isinstance(delta, dict):
        delta = {}
    verdict = payload.get("verdict")
    if not isinstance(verdict, dict):
        verdict = {}
    gate = verdict.get("gate")
    audit = verdict.get("audit")
    incoming = verdict.get("evidence_refs")
    evidence = list(incoming) if isinstance(incoming, list) else []
    if gate == "PASS" and audit == "PASS":
        evidence = evidence + ["linkcheck:ok"]
    else:
        evidence = evidence + ["linkcheck:failed:joint"]
    return {
        "package_id": delta.get("delta_id"),
        "gate": gate,
        "audit": audit,
        "evidence_refs": evidence,
    }
