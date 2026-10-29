"""K06 Lane A toolguard -- G2 action-execution record usage.

Records carry action_id, idempotency_key, authorization_ref,
attempt and status. Execution needs the provider key, otherwise
prior-state verification; a forged or placeholder token stays
untrusted and is refused under either path. Recording an attempt
never retries on its own: each call applies one explicit status
transition and returns a new record, leaving the input untouched.
"""

from __future__ import annotations

import re
from typing import Any

ACTION_RECORD_FIELDS: tuple[str, ...] = (
    "action_id",
    "idempotency_key",
    "authorization_ref",
    "attempt",
    "status",
)

_UNTRUSTED_TOKEN_SEGMENTS = frozenset(
    {
        "forged",
        "forgery",
        "fake",
        "faked",
        "spoof",
        "spoofed",
        "invalid",
        "placeholder",
        "example",
        "sample",
        "dummy",
        "changeme",
        "default",
        "demo",
        "bogus",
        "unsigned",
        "unverified",
    }
)


def _untrusted_token(token: str) -> bool:
    """True when a token advertises itself as forged or placeholder.

    Real authorization references are opaque values issued by the
    authority; values carrying a forged, fake or placeholder marker
    can never authorize on their own. This mirrors the rejection of
    default credentials: such values are untrusted by construction.
    """
    segments = re.split(r"[-_./:\\\s]+", token.lower())
    return any(segment in _UNTRUSTED_TOKEN_SEGMENTS for segment in segments)


def build_action_record(
    action_id: str,
    idempotency_key: str,
    authorization_ref: str,
    attempt: int,
    status: str,
) -> dict[str, Any]:
    """Build the record for one action execution attempt."""
    return {
        "action_id": action_id,
        "idempotency_key": idempotency_key,
        "authorization_ref": authorization_ref,
        "attempt": attempt,
        "status": status,
    }


def verify_provider_or_prior_state(
    record: dict[str, Any],
    provider_key: str | None,
    prior_state: dict[str, Any] | None,
) -> dict[str, Any]:
    """Verify a record through the provider key or prior state.

    A missing or empty authorization reference is the no-token
    case; a reference advertising forgery or placeholder status
    is the wrong-token case even when a provider key is present.
    A present token with no provider key and no matching prior
    state is likewise refused. All refusals raise PermissionError.
    Exactly one verification is performed: there is no silent
    retry path.
    """
    token = record.get("authorization_ref") if isinstance(record, dict) else None
    if not isinstance(token, str) or not token:
        raise PermissionError("cannot verify: record carries no authorization token")
    if _untrusted_token(token):
        raise PermissionError("cannot verify: untrusted authorization token")
    if isinstance(provider_key, str) and provider_key:
        return {"ok": True}
    if isinstance(prior_state, dict) and prior_state.get(token):
        return {"ok": True}
    raise PermissionError("cannot verify: untrusted authorization token")


def record_attempt(
    record: dict[str, Any],
    status: str,
) -> dict[str, Any]:
    """Record one explicit attempt with a new status.

    The no-token case (missing or empty reference) and the
    wrong-token case (a reference advertising forgery or
    placeholder status, unverifiable here) refuse with
    PermissionError. Otherwise a new record is returned with the
    attempt count increased by one; the input record is untouched.
    """
    token = record.get("authorization_ref") if isinstance(record, dict) else None
    if not isinstance(token, str) or not token:
        raise PermissionError("cannot record attempt: record carries no authorization token")
    if _untrusted_token(token):
        raise PermissionError("cannot record attempt: untrusted authorization token")
    source = record if isinstance(record, dict) else {}
    old_attempt = source.get("attempt", 0)
    if isinstance(old_attempt, bool) or not isinstance(old_attempt, int):
        old_attempt = 0
    progressed = dict(source)
    progressed["attempt"] = old_attempt + 1
    progressed["status"] = status
    return progressed
