"""K05R3 on-demand local helper for a routed assignment (B0B-BP03-47).

Attach/start/release pass through the real gateway entry point
(agent_si.local.gateway.passive_check). Attach and start proceed only on
an idle verdict and refuse with K05R3_HELPER_GATEWAY_BUSY otherwise
(machine not idle -> skip with reason, never forced). Release always
completes and records the gateway state observed at release. Standard
library plus agent_si.local public imports only.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

from agent_si.local import gateway

#: Helper refused: the gateway passive check did not report idle.
K05R3_HELPER_GATEWAY_BUSY = "K05R3_HELPER_GATEWAY_BUSY"
#: Helper refused: unknown handle, double start, or release of a closed handle.
K05R3_HELPER_STATE_REFUSED = "K05R3_HELPER_STATE_REFUSED"
#: Helper refused: assignment ref is not a non-empty string.
K05R3_HELPER_BAD_REF = "K05R3_HELPER_BAD_REF"

#: New-module error-code set (frozen ERROR_CODES_* tuples elsewhere untouched).
ERROR_CODES_K05R3_HELPER = (
    K05R3_HELPER_GATEWAY_BUSY,
    K05R3_HELPER_STATE_REFUSED,
    K05R3_HELPER_BAD_REF,
)


class HelperError(Exception):
    """Helper failure; carries one ERROR_CODES_K05R3_HELPER code in `code`."""

    code: str

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class HelperAttachment:
    """Attached on-demand helper: assignment ref plus the idle verdict behind it."""

    helper_id: str
    assignment_ref: str
    gateway_reason: str
    started: bool = False


@dataclass(frozen=True)
class HelperRelease:
    """Closed helper: assignment ref plus the gateway state observed at release."""

    helper_id: str
    assignment_ref: str
    gateway_reason: str
    started: bool = False


#: Helper ids, unique per attach in call order.
_HELPER_SEQ = itertools.count(1)

#: Live handles by helper id (assignment ref plus started/released flags).
_HANDLES: dict[str, dict[str, object]] = {}


def _require_ref(assignment_ref: str) -> str:
    if not isinstance(assignment_ref, str) or not assignment_ref:
        raise HelperError(
            K05R3_HELPER_BAD_REF,
            "assignment_ref must be a non-empty string, got %r" % (assignment_ref,),
        )
    return assignment_ref


def _idle_or_refuse(action: str, assignment_ref: str) -> gateway.PassiveCheckResult:
    """Real gateway entry point; a refused verdict raises, never forces contact."""
    check = gateway.passive_check()
    if not check.allowed:
        raise HelperError(
            K05R3_HELPER_GATEWAY_BUSY,
            "helper %s for assignment %r refused: gateway %s; skipped, never forced"
            % (action, assignment_ref, check.reason),
        )
    return check


def _live_state(attachment: HelperAttachment) -> dict[str, object]:
    if not isinstance(attachment, HelperAttachment):
        raise HelperError(
            K05R3_HELPER_STATE_REFUSED,
            "expected a HelperAttachment, got %r" % (attachment,),
        )
    state = _HANDLES.get(attachment.helper_id)
    if (
        state is None
        or state.get("assignment_ref") != attachment.assignment_ref
        or state.get("released")
    ):
        raise HelperError(
            K05R3_HELPER_STATE_REFUSED,
            "unknown or closed helper %r" % (attachment.helper_id,),
        )
    return state


def attach_helper(assignment_ref: str) -> HelperAttachment:
    """Attach an on-demand helper for a routed assignment behind an idle verdict."""
    ref = _require_ref(assignment_ref)
    check = _idle_or_refuse("attach", ref)
    helper_id = "k05r3-helper-%06d" % next(_HELPER_SEQ)
    _HANDLES[helper_id] = {"assignment_ref": ref, "started": False, "released": False}
    return HelperAttachment(
        helper_id=helper_id, assignment_ref=ref, gateway_reason=check.reason
    )


def start_helper(attachment: HelperAttachment) -> HelperAttachment:
    """Start an attached helper after re-verifying an idle gateway verdict."""
    state = _live_state(attachment)
    if state.get("started"):
        raise HelperError(
            K05R3_HELPER_STATE_REFUSED,
            "helper %r already started" % (attachment.helper_id,),
        )
    check = _idle_or_refuse("start", attachment.assignment_ref)
    state["started"] = True
    return HelperAttachment(
        helper_id=attachment.helper_id,
        assignment_ref=attachment.assignment_ref,
        gateway_reason=check.reason,
        started=True,
    )


def release_helper(attachment: HelperAttachment) -> HelperRelease:
    """Release a helper after its task finishes; always completes."""
    state = _live_state(attachment)
    check = gateway.passive_check()
    state["released"] = True
    return HelperRelease(
        helper_id=attachment.helper_id,
        assignment_ref=attachment.assignment_ref,
        gateway_reason=check.reason,
        started=bool(state.get("started")),
    )
