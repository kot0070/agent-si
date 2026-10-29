"""K06 Lane A toolguard -- G3 permission ladder.

R0 runs only when task-authorized; R1 needs a TaskContract; R2 is
refused without a Director record; R3 is refused without a user
record; generated commands never gain privilege. Missing or
non-mapping auth is treated as empty (default-deny, never
default-allow). A structured contract claim carrying content plus
a hash is hash-verified; a mismatch refuses with
ERR_CONTRACT_CHAIN_BROKEN, keeping the R1 chain unbroken
end to end. A claim that is neither an opaque pointer string nor
a structured mapping nor a contract object (a scalar, byte string
or sequence) is no TaskContract authorization either and refuses
the same way. Passes return ok True; refusals return the exact
error code for the failed condition.
"""

from __future__ import annotations

from typing import Any

ACTION_CLASSES: tuple[str, ...] = ("R0", "R1", "R2", "R3")

ERR_R0_NOT_TASK_AUTHORIZED: str = "ERR_R0_NOT_TASK_AUTHORIZED"
ERR_R1_CONTRACT_REQUIRED: str = "ERR_R1_CONTRACT_REQUIRED"
ERR_R2_DIRECTOR_RECORD_REQUIRED: str = "ERR_R2_DIRECTOR_RECORD_REQUIRED"
ERR_R3_USER_RECORD_REQUIRED: str = "ERR_R3_USER_RECORD_REQUIRED"
ERR_GENERATED_PRIVILEGE_DENIED: str = "ERR_GENERATED_PRIVILEGE_DENIED"
ERR_CONTRACT_CHAIN_BROKEN: str = "ERR_CONTRACT_CHAIN_BROKEN"

_CHAIN_CONTENT_KEYS: tuple[str, ...] = (
    "task_id",
    "project_id",
    "contract_version",
    "contract_sequence",
    "goal",
)

_NON_CONTRACT_CLAIMS: tuple[type, ...] = (
    int,
    float,
    complex,
    bytes,
    bytearray,
    list,
    tuple,
    set,
    frozenset,
)


def _chain_digest(value: Any) -> str | None:
    """Return the claimed contract hash when the value carries one."""
    if isinstance(value, dict):
        digest = value.get("contract_hash")
    else:
        digest = getattr(value, "contract_hash", None)
    if isinstance(digest, str) and digest:
        return digest
    return None


def _chain_has_content(value: Any) -> bool:
    """True when the value carries contract content beyond a bare pointer."""
    if isinstance(value, dict):
        return any(key in value for key in _CHAIN_CONTENT_KEYS)
    return any(hasattr(value, key) for key in _CHAIN_CONTENT_KEYS)


def contract_chain_broken(contract: Any) -> bool:
    """True when a structured contract claim fails hash verification.

    Opaque pointers (plain strings, id-only mappings, claims without a
    hash) carry nothing verifiable and stay on the legacy presence
    path. A claim that carries both contract content and a contract
    hash is verified against the domain hash; a mismatch, or content
    that cannot be hashed at all, means the authorization chain is
    broken and the action must not run. Scalar and sequence claims
    (numbers, booleans, byte strings, lists, tuples, sets) are never
    TaskContract authorizations, so they are always broken.
    """
    if isinstance(contract, str) or contract is None:
        return False
    if isinstance(contract, bool):
        return True
    if isinstance(contract, _NON_CONTRACT_CLAIMS):
        return True
    if not _chain_has_content(contract):
        return False
    if _chain_digest(contract) is None:
        return False
    try:
        from agent_si.domain import contracts as domain_contracts
    except ImportError:
        return True
    try:
        if isinstance(contract, dict):
            from types import SimpleNamespace

            candidate = SimpleNamespace(**contract)
        else:
            candidate = contract
        expected = domain_contracts.compute_contract_hash(candidate)
    except Exception:
        return True
    return expected != _chain_digest(contract)


def check_permission(
    action_class: str,
    auth: dict[str, Any],
    generated: bool,
) -> dict[str, Any]:
    """Decide whether ``action_class`` may run under ``auth``.

    The generated flag is evaluated first: a generated command is
    refused whatever else it carries. Unknown action classes are
    refused with a reason naming them.
    """
    if generated:
        return {"error": ERR_GENERATED_PRIVILEGE_DENIED}
    if not isinstance(auth, dict):
        auth = {}
    if action_class == "R0":
        if auth.get("task"):
            return {"ok": True, "action_class": "R0"}
        return {"error": ERR_R0_NOT_TASK_AUTHORIZED}
    if action_class == "R1":
        if auth.get("contract"):
            if contract_chain_broken(auth.get("contract")):
                return {"error": ERR_CONTRACT_CHAIN_BROKEN}
            return {"ok": True, "action_class": "R1"}
        return {"error": ERR_R1_CONTRACT_REQUIRED}
    if action_class == "R2":
        if auth.get("contract") and auth.get("director_record"):
            if contract_chain_broken(auth.get("contract")):
                return {"error": ERR_CONTRACT_CHAIN_BROKEN}
            return {"ok": True, "action_class": "R2"}
        return {"error": ERR_R2_DIRECTOR_RECORD_REQUIRED}
    if action_class == "R3":
        if auth.get("contract") and auth.get("user_record"):
            if contract_chain_broken(auth.get("contract")):
                return {"error": ERR_CONTRACT_CHAIN_BROKEN}
            return {"ok": True, "action_class": "R3"}
        return {"error": ERR_R3_USER_RECORD_REQUIRED}
    return {"error": "ERR_UNKNOWN_ACTION_CLASS: %s" % (action_class,)}
