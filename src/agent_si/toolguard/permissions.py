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

import contextlib
import json
import os
import tempfile
from datetime import UTC, datetime
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


#: Frozen F13 route: install-permission ask-once decision.
PERMISSIONS_CHECK_ROUTE = "/api/v1/permissions/check"

#: Longest accepted tool id; longer values are refused, never truncated.
TOOL_ID_MAX_LEN = 256

#: File in the app store dir holding the persisted once-flag id list.
ASKED_ONCE_FILENAME = "demof13w_asked_once.json"


class PermissionCheckError(Exception):
    """Refusal carrying its HTTP status plus signal code."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


def check_install_permission(tool_id: str) -> bool:
    """Decide whether ``tool_id`` is granted install permission.

    Grants any well-formed id (a string with non-blank content inside
    the length cap); refuses non-strings, blank ids and oversize ids.
    """
    if not isinstance(tool_id, str):
        return False
    text = tool_id.strip()
    if not text or len(text) > TOOL_ID_MAX_LEN:
        return False
    return True


def require_tool_id(payload: Any) -> str:
    """Return the required non-blank tool_id, else a loud 400."""
    value = payload.get("tool_id") if isinstance(payload, dict) else None
    if not isinstance(value, str) or not value.strip():
        raise PermissionCheckError(
            400, "DEMOF13F1_TOOL_ID_MISSING",
            "permissions check needs a non-empty tool_id string")
    return value.strip()


def _asked_once_path(store_dir: str) -> str:
    """Path of the persisted once-flag id list inside the store dir."""
    return os.path.join(store_dir, ASKED_ONCE_FILENAME)


def load_asked_once(store_dir: Any) -> set[str]:
    """Read the persisted once-flag id set; unknown state reads empty."""
    if not store_dir:
        return set()
    try:
        with open(_asked_once_path(store_dir),
                  "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return set()
    if not isinstance(data, list):
        return set()
    return {entry for entry in data if isinstance(entry, str)}


def save_asked_once(store_dir: Any, asked: set[str]) -> None:
    """Persist the once-flag id set with a temp file plus os.replace."""
    if not store_dir:
        return
    os.makedirs(store_dir, exist_ok=True)
    path = _asked_once_path(store_dir)
    fd, tmp = tempfile.mkstemp(
        dir=store_dir, prefix="asked_once_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(sorted(asked), handle)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def record_install_ask(store_dir: Any, memory: set[str],
                       tool_id: str) -> bool:
    """Record one install ask; True when the id was already recorded.

    The file in the store dir is the durable record (a rebuild over the
    same store dir still answers True); ``memory`` keeps the answer
    right when no store dir is configured.
    """
    asked = set(memory)
    if store_dir:
        asked |= load_asked_once(store_dir)
    seen = tool_id in asked
    asked.add(tool_id)
    memory.add(tool_id)
    if store_dir:
        save_asked_once(store_dir, asked)
    return seen


#: Frozen FXASKA route recording one install decision.
PERMISSIONS_DECIDE_ROUTE = "/api/v1/permissions/decide"

#: Frozen FXASKA route listing recorded install decisions.
PERMISSIONS_DECISIONS_ROUTE = "/api/v1/permissions/decisions"

#: File in the app store dir holding the persisted decision ledger.
DECISIONS_FILENAME = "demof13w_decisions.json"

#: Accepted ledger decisions.
DECISION_ALLOW = "allow"
DECISION_DENY = "deny"
DECISION_VALUES = (DECISION_ALLOW, DECISION_DENY)


def _decision_now() -> str:
    """Current UTC time rendered like the frozen journal timestamps."""
    return (
        datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def require_decision(payload: Any) -> str:
    """Return the required allow|deny decision, else a loud 400."""
    value = payload.get("decision") if isinstance(payload, dict) else None
    if value not in DECISION_VALUES:
        raise PermissionCheckError(
            400, "DEMOF13W_DECISION_INVALID",
            "permissions decide needs decision allow or deny")
    return str(value)


def require_project_id(payload: Any) -> str:
    """Return the required non-blank project_id, else a loud 400."""
    value = payload.get("project_id") if isinstance(payload, dict) else None
    if not isinstance(value, str) or not value.strip():
        raise PermissionCheckError(
            400, "DEMOF13W_PROJECT_ID_MISSING",
            "permissions decide needs a non-empty project_id string")
    return value.strip()


def install_tool_id(project_id: str, argv0: str) -> str:
    """Tool id for one install-class ask: install:<project>:<argv0>."""
    return f"install:{project_id}:{argv0}"


def _decisions_path(store_dir: str) -> str:
    """Path of the persisted decision ledger inside the store dir."""
    return os.path.join(store_dir, DECISIONS_FILENAME)


def load_decisions(store_dir: Any) -> dict[str, dict[str, str]]:
    """Read the persisted decision ledger; unknown state reads empty."""
    if not store_dir:
        return {}
    try:
        with open(_decisions_path(store_dir),
                  encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    ledger: dict[str, dict[str, str]] = {}
    for key, value in data.items():
        if isinstance(key, str) and isinstance(value, dict):
            ledger[key] = {
                str(field): str(item)
                for field, item in value.items()
            }
    return ledger


def save_decisions(
        store_dir: Any,
        decisions: dict[str, dict[str, str]]) -> None:
    """Persist the decision ledger with a temp file plus os.replace."""
    if not store_dir:
        return
    os.makedirs(store_dir, exist_ok=True)
    path = _decisions_path(store_dir)
    fd, tmp = tempfile.mkstemp(
        dir=store_dir, prefix="decisions_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(
                {key: decisions[key] for key in sorted(decisions)},
                handle)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


#: Store dir bound by the app composition root (create_app); the spawn
#: path reads decisions through this binding, never the environment.
_BOUND_STORE_DIR: str | None = None

#: In-process decision memory shared by the served decide route and the
#: spawn path; the file stays the durable record.
_BOUND_DECISIONS: dict[str, dict[str, str]] = {}


def bind_decision_store(store_dir: Any) -> dict[str, dict[str, str]]:
    """Bind the ledger store dir; reseed shared memory from the file."""
    global _BOUND_STORE_DIR
    _BOUND_STORE_DIR = str(store_dir) if store_dir else None
    _BOUND_DECISIONS.clear()
    _BOUND_DECISIONS.update(load_decisions(store_dir))
    return _BOUND_DECISIONS


def _resolve_ledger(store_dir: Any,
                    memory: Any) -> tuple[Any, dict]:
    """Fill unset ledger call sites from the bound store and memory."""
    if store_dir is None:
        store_dir = _BOUND_STORE_DIR
    if memory is None:
        memory = _BOUND_DECISIONS
    return store_dir, memory


def get_decision(store_dir: Any = None, memory: Any = None,
                 tool_id: str = "") -> str | None:
    """Read one ledger decision; unknown ids read as none."""
    store_dir, memory = _resolve_ledger(store_dir, memory)
    key = str(tool_id)
    entry = None
    if isinstance(memory, dict):
        entry = memory.get(key)
    if entry is None and store_dir:
        entry = load_decisions(store_dir).get(key)
    if isinstance(entry, dict):
        decision = entry.get("decision")
        if decision in DECISION_VALUES:
            return str(decision)
    return None


def record_decision(store_dir: Any = None, memory: Any = None,
                    tool_id: str = "", decision: str = "",
                    project_id: str = "",
                    decided_at: str | None = None) -> dict[str, str]:
    """Record one install decision; the file is the durable record.

    Raises PermissionCheckError (400) for a bad decision; unknown ids
    stay unreadable as none until recorded.
    """
    if decision not in DECISION_VALUES:
        raise PermissionCheckError(
            400, "DEMOF13W_DECISION_INVALID",
            "permissions decide needs decision allow or deny")
    store_dir, memory = _resolve_ledger(store_dir, memory)
    key = str(tool_id)
    record = {
        "decision": str(decision),
        "time": decided_at or _decision_now(),
        "project": str(project_id),
    }
    merged = load_decisions(store_dir)
    if isinstance(memory, dict):
        for known_key, known in memory.items():
            if isinstance(known, dict):
                merged[known_key] = known
        memory[key] = record
    merged[key] = record
    save_decisions(store_dir, merged)
    return record


def list_decisions(store_dir: Any = None, memory: Any = None,
                   project_id: str = "") -> list[dict[str, str]]:
    """List ledger rows for one project, ordered by tool id."""
    store_dir, memory = _resolve_ledger(store_dir, memory)
    merged = load_decisions(store_dir)
    if isinstance(memory, dict):
        for key, value in memory.items():
            if isinstance(value, dict):
                merged[key] = value
    rows: list[dict[str, str]] = []
    for key in sorted(merged):
        entry = merged[key]
        if not isinstance(entry, dict):
            continue
        if str(entry.get("project", "")) != str(project_id):
            continue
        decision = entry.get("decision")
        if decision not in DECISION_VALUES:
            continue
        rows.append({
            "tool_id": key,
            "decision": str(decision),
            "project": str(entry.get("project", "")),
            "time": str(entry.get("time", "")),
        })
    return rows
