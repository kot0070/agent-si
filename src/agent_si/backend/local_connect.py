"""K05 local runtime connect (HTTP surface plus entry points; shapes only, no logic).

Frozen sources (read-only; 0C wins every clash):
RECORDS/day0/0C_ARCHITECTURE.md sec 12 (K05 owns
src/agent_si/backend/local_connect.py) and the K13 frozen
router-guard contract (USER writes check the UI session token first;
reads need no token). Local routes use the /api/v1/local/ prefix and
never clash with the frozen K04 provider/role/KB/budget routes. Every
route reaches its real implementation through exactly one entry-point
function named in ROUTE_ENTRY_POINTS. Every function body is `...`
(no logic): real behavior lives in the owning lane module named
in REALIZATION_MAP. Standard library only.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Dict, Tuple

from agent_si.local import bench_runner as _discovery
from agent_si.local.adapter import EvidenceTier, STATUS_NOT_CONFIGURED


#: Frozen HTTP surface: (method, path) pairs.
HTTP_ROUTES = (
    ("GET", "/api/v1/local/status"),
    ("POST", "/api/v1/local/connect"),
    ("POST", "/api/v1/local/disconnect"),
    ("GET", "/api/v1/local/models"),
)


@dataclass(frozen=True)
class LocalStatus:
    status: str
    reason: str


@dataclass(frozen=True)
class LocalModelRow:
    model: str
    evidence_tier: str
    status: str


#: Env override for the bound UI session token (K02 seam x-ui-session-token).
_SESSION_TOKEN_ENV = "AGENT_SI_UI_SESSION_TOKEN"

#: Session token bound to this process: the first well-formed USER write
#: binds it (single-user desktop default); env config wins when set.
#: Refused writes never touch this or the runtime attachment.
_PAIRED_SESSION_TOKEN: str | None = None

#: Currently attached local runtime ref (None while detached).
_ATTACHED_RUNTIME: str | None = None

_STATE_LOCK = threading.Lock()

#: Status reported when an attached runtime is discovered reachable.
_STATUS_READY = "READY"


def _require_session_token(session_token: str) -> str:
    """USER-write gate: UI session token first; None/empty/mismatch refuses."""
    if not isinstance(session_token, str) or not session_token:
        raise Exception(
            "SESSION_TOKEN_REFUSED: USER write needs a bound UI session token "
            "(x-actor + x-ui-session-token); state unchanged"
        )
    configured = os.environ.get(_SESSION_TOKEN_ENV, "")
    global _PAIRED_SESSION_TOKEN
    with _STATE_LOCK:
        expected = configured or _PAIRED_SESSION_TOKEN
        if expected is None:
            _PAIRED_SESSION_TOKEN = session_token
            return session_token
        if session_token != expected:
            raise Exception(
                "SESSION_TOKEN_REFUSED: UI session token mismatch; state unchanged"
            )
        return expected


def get_status() -> LocalStatus:
    """Read the local runtime status; capability base absent yields NOT_CONFIGURED."""
    with _STATE_LOCK:
        attached = _ATTACHED_RUNTIME
    if attached is None:
        return LocalStatus(
            status=STATUS_NOT_CONFIGURED,
            reason="capability base absent; routing continues normally",
        )
    probe = _discovery.passive_gateway_check(attached)
    if probe.reachable:
        return LocalStatus(
            status=_STATUS_READY,
            reason=f"runtime {attached!r} discovered ({probe.reason}); routing continues",
        )
    return LocalStatus(
        status=STATUS_NOT_CONFIGURED,
        reason=f"runtime {attached!r} undiscovered ({probe.reason}); routing continues normally",
    )


def connect(runtime_ref: str, session_token: str) -> LocalStatus:
    """USER write: attach a local runtime; checks the UI session token first."""
    _require_session_token(session_token)
    if not isinstance(runtime_ref, str) or not runtime_ref:
        raise ValueError(f"runtime_ref must be a non-empty string, got {runtime_ref!r}")
    global _ATTACHED_RUNTIME
    with _STATE_LOCK:
        _ATTACHED_RUNTIME = runtime_ref
    return LocalStatus(
        status="NOT_CONFIGURED",
        reason=f"runtime {runtime_ref!r} attached; capability base absent, routing continues",
    )


def disconnect(session_token: str) -> LocalStatus:
    """USER write: detach the local runtime; checks the UI session token first."""
    _require_session_token(session_token)
    global _ATTACHED_RUNTIME
    with _STATE_LOCK:
        _ATTACHED_RUNTIME = None
    return LocalStatus(
        status="NOT_CONFIGURED",
        reason="runtime detached; capability base absent, routing continues",
    )


def list_models() -> Tuple[LocalModelRow, ...]:
    """Read the known local models with their evidence tier and status."""
    with _STATE_LOCK:
        attached = _ATTACHED_RUNTIME
    if attached is None:
        return ()
    probe = _discovery.passive_gateway_check(attached)
    if not probe.reachable:
        return ()
    return (
        LocalModelRow(
            model=attached,
            evidence_tier=EvidenceTier.PROXY.value,
            status=_STATUS_READY,
        ),
    )


#: Every route reaches its real implementation through one entry point.
ROUTE_ENTRY_POINTS: Dict[Tuple[str, str], str] = {
    ("GET", "/api/v1/local/status"): "get_status",
    ("POST", "/api/v1/local/connect"): "connect",
    ("POST", "/api/v1/local/disconnect"): "disconnect",
    ("GET", "/api/v1/local/models"): "list_models",
}

#: Frozen function name to owning lane implementation (dotted path).
REALIZATION_MAP = {
    "get_status": "agent_si.local.service.LocalRuntimeService.get_status",
    "connect": "agent_si.local.service.LocalRuntimeService.connect",
    "disconnect": "agent_si.local.service.LocalRuntimeService.disconnect",
    "list_models": "agent_si.local.service.LocalRuntimeService.list_models",
}
