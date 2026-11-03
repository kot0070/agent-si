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

#: FXR1B routes: per-project installer grants plus the pending ask argv
#: the permission dialog displays instead of the raw tool id.
PERMISSIONS_PROJECT_GRANT_ROUTE = "/api/v1/permissions/project-grant"
PERMISSIONS_PROJECT_GRANTS_ROUTE = "/api/v1/permissions/project-grants"
PERMISSIONS_INSTALL_REQUEST_ROUTE = "/api/v1/permissions/install-request"

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


def load_decisions(store_dir: Any) -> dict[str, dict[str, Any]]:
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
    ledger: dict[str, dict[str, Any]] = {}
    for key, value in data.items():
        if isinstance(key, str) and isinstance(value, dict):
            row: dict[str, Any] = {}
            for field, item in value.items():
                if str(field) == "argv" and isinstance(item, list):
                    row["argv"] = [str(word) for word in item]
                else:
                    row[str(field)] = str(item)
            ledger[key] = row
    return ledger


def save_decisions(
        store_dir: Any,
        decisions: dict[str, dict[str, Any]]) -> None:
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
_BOUND_DECISIONS: dict[str, dict[str, Any]] = {}

#: In-process project-grant memory shared by the grant routes and the
#: spawn path; the file stays the durable record.
_BOUND_GRANTS: dict[str, dict[str, Any]] = {}


def bind_decision_store(store_dir: Any) -> dict[str, dict[str, Any]]:
    """Bind the ledger store dir; reseed shared memory from the file."""
    global _BOUND_STORE_DIR
    _BOUND_STORE_DIR = str(store_dir) if store_dir else None
    _BOUND_DECISIONS.clear()
    _BOUND_DECISIONS.update(load_decisions(store_dir))
    _BOUND_GRANTS.clear()
    _BOUND_GRANTS.update(load_project_grants(store_dir))
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


def decision_allows_run(store_dir: Any = None, memory: Any = None,
                        tool_id: str = "",
                        run_id: Any = None) -> bool:
    """True when a recorded allow covers this run (FXR4A D4).

    An allow is single-run: unconsumed allows cover any run, an allow
    consumed by another run reads as spent (ask again), an allow
    consumed by this run still covers it (same-run retries never
    re-ask). Deny and unknown never allow.
    """
    store_dir, memory = _resolve_ledger(store_dir, memory)
    key = str(tool_id)
    entry = None
    if isinstance(memory, dict):
        entry = memory.get(key)
    if entry is None and store_dir:
        entry = load_decisions(store_dir).get(key)
    if not isinstance(entry, dict):
        return False
    if entry.get("decision") != DECISION_ALLOW:
        return False
    spent = entry.get("consumed_by_run")
    if spent and run_id is not None and str(spent) != str(run_id):
        return False
    return True


def note_decision_consumed(store_dir: Any = None, memory: Any = None,
                           tool_id: str = "",
                           run_id: Any = "") -> dict[str, Any] | None:
    """Mark one allow spent by a run; the next run asks again (FXR4A D4).

    Only an unconsumed allow is stamped; a deny, an unknown id, or an
    allow already spent by another run is left untouched (None).
    """
    if not str(run_id):
        return None
    store_dir, memory = _resolve_ledger(store_dir, memory)
    key = str(tool_id)
    merged = load_decisions(store_dir)
    if isinstance(memory, dict):
        for known_key, known in memory.items():
            if isinstance(known, dict):
                merged[known_key] = known
    entry = merged.get(key)
    if not isinstance(entry, dict):
        return None
    if entry.get("decision") != DECISION_ALLOW:
        return None
    spent = entry.get("consumed_by_run")
    if spent and str(spent) != str(run_id):
        return None
    record = dict(entry)
    record["consumed_by_run"] = str(run_id)
    if isinstance(memory, dict):
        memory[key] = record
    merged[key] = record
    save_decisions(store_dir, merged)
    return dict(record)


def repin_install_request(store_dir: Any = None, memory: Any = None,
                          tool_id: str = "", argv: Any = None,
                          project_id: str = "") -> dict[str, Any] | None:
    """Point the pending ask pin at genuinely new words (FXR4A D5).

    A recorded deny is never touched. Otherwise the pin moves to the
    words the user is now asked about, so a later allow covers exactly
    those words instead of looping on a stale pin. Same-word re-asks
    keep first-ask-wins (record_install_request) semantics.
    """
    argv_words = _valid_decision_argv(argv)
    if argv_words is None:
        return None
    store_dir, memory = _resolve_ledger(store_dir, memory)
    key = str(tool_id)
    if not key:
        return None
    merged = load_decisions(store_dir)
    if isinstance(memory, dict):
        for known_key, known in memory.items():
            if isinstance(known, dict):
                merged[known_key] = known
    prior = merged.get(key)
    if isinstance(prior, dict):
        if prior.get("decision") == DECISION_DENY:
            return dict(prior)
        record = dict(prior)
        record["argv"] = argv_words
        record.setdefault("project", str(project_id))
    else:
        record = {
            "time": _decision_now(),
            "project": str(project_id),
            "argv": argv_words,
        }
    if isinstance(memory, dict):
        memory[key] = record
    merged[key] = record
    save_decisions(store_dir, merged)
    return dict(record)


def record_decision(store_dir: Any = None, memory: Any = None,
                    tool_id: str = "", decision: str = "",
                    project_id: str = "",
                    decided_at: str | None = None,
                    argv: Any = None) -> dict[str, Any]:
    """Record one install decision; the file is the durable record.

    Raises PermissionCheckError (400) for a bad decision; unknown ids
    stay unreadable as none until recorded. ``argv`` optionally pins
    the exact approved words; when absent, an argv pinned by an earlier
    install ask is preserved, so a later allow never widens it. A fresh
    decision resets once-consumption (FXR4A D4): the next run that uses
    the allow consumes it anew.
    """
    if decision not in DECISION_VALUES:
        raise PermissionCheckError(
            400, "DEMOF13W_DECISION_INVALID",
            "permissions decide needs decision allow or deny")
    argv_words = _valid_decision_argv(argv)
    store_dir, memory = _resolve_ledger(store_dir, memory)
    key = str(tool_id)
    merged = load_decisions(store_dir)
    if isinstance(memory, dict):
        for known_key, known in memory.items():
            if isinstance(known, dict):
                merged[known_key] = known
    record: dict[str, Any] = {
        "decision": str(decision),
        "time": decided_at or _decision_now(),
        "project": str(project_id),
    }
    # A fresh decision is a fresh once-allow: drop any spent marker so
    # the next run that uses it consumes it anew (FXR4A D4).
    if argv_words is not None:
        record["argv"] = argv_words
    else:
        prior = merged.get(key)
        if (isinstance(prior, dict)
                and isinstance(prior.get("argv"), list)
                and prior["argv"]):
            record["argv"] = [str(word) for word in prior["argv"]]
    if isinstance(memory, dict):
        memory[key] = record
    merged[key] = record
    save_decisions(store_dir, merged)
    return record


def _valid_decision_argv(argv: Any) -> list[str] | None:
    """Coerced install-decision argv words, or None when absent.

    Raises PermissionCheckError (400) for a malformed argv; an empty
    word list is malformed, never an approval.
    """
    if argv is None:
        return None
    if not isinstance(argv, (list, tuple)) or not argv:
        raise PermissionCheckError(
            400, "DEMOF13W_ARGV_INVALID",
            "permissions decision argv must be a non-empty list of words")
    words = [str(word) for word in argv]
    if any(not word for word in words):
        raise PermissionCheckError(
            400, "DEMOF13W_ARGV_INVALID",
            "permissions decision argv must be a non-empty list of words")
    return words


def get_install_argv(store_dir: Any = None, memory: Any = None,
                     tool_id: str = "") -> list[str] | None:
    """Exact argv pinned for one install tool id, else None.

    The ledger is the only source: a recorded decision argv, or an argv
    pinned by the install ask that led to it. No fallback to caller
    words happens here; the spawn path decides what a missing pin means.
    """
    store_dir, memory = _resolve_ledger(store_dir, memory)
    key = str(tool_id)
    entry = None
    if isinstance(memory, dict):
        entry = memory.get(key)
    if entry is None and store_dir:
        entry = load_decisions(store_dir).get(key)
    if isinstance(entry, dict):
        pinned = entry.get("argv")
        if (isinstance(pinned, list) and pinned
                and all(isinstance(word, str) and word
                        for word in pinned)):
            return list(pinned)
    return None


def record_install_request(store_dir: Any = None, memory: Any = None,
                           tool_id: str = "", argv: Any = None,
                           project_id: str = "") -> dict[str, Any] | None:
    """Pin the exact argv that triggered one install ask.

    First ask wins: a recorded allow/deny is never touched and an
    already pinned argv is never re-pinned, so the words the user is
    asked about are the words a later allow covers. Entries carry no
    decision, so they keep reading as none until decided.
    """
    argv_words = _valid_decision_argv(argv)
    if argv_words is None:
        return None
    store_dir, memory = _resolve_ledger(store_dir, memory)
    key = str(tool_id)
    if not key:
        return None
    merged = load_decisions(store_dir)
    if isinstance(memory, dict):
        for known_key, known in memory.items():
            if isinstance(known, dict):
                merged[known_key] = known
    prior = merged.get(key)
    if isinstance(prior, dict):
        if prior.get("decision") in DECISION_VALUES:
            return dict(prior)
        if (isinstance(prior.get("argv"), list)
                and prior["argv"]):
            return dict(prior)
    record: dict[str, Any] = {
        "time": _decision_now(),
        "project": str(project_id),
        "argv": argv_words,
    }
    if isinstance(memory, dict):
        memory[key] = record
    merged[key] = record
    save_decisions(store_dir, merged)
    return dict(record)


def pin_install_argv(store_dir: Any = None, memory: Any = None,
                     tool_id: str = "", argv: Any = None,
                     project_id: str = "") -> list[str] | None:
    """Pin the first allowed spawn for an allow that carries no argv.

    Only fills a missing pin under an existing allow (route-decided
    before any ask); first pin wins, the decision and time are kept.
    Returns the pinned words, or None when there is nothing to pin.
    """
    argv_words = _valid_decision_argv(argv)
    if argv_words is None:
        return None
    store_dir, memory = _resolve_ledger(store_dir, memory)
    key = str(tool_id)
    if not key:
        return None
    merged = load_decisions(store_dir)
    if isinstance(memory, dict):
        for known_key, known in memory.items():
            if isinstance(known, dict):
                merged[known_key] = known
    prior = merged.get(key)
    if not isinstance(prior, dict):
        return None
    if prior.get("decision") != DECISION_ALLOW:
        return None
    if (isinstance(prior.get("argv"), list)
            and prior["argv"]
            and all(isinstance(word, str) and word
                    for word in prior["argv"])):
        return [str(word) for word in prior["argv"]]
    record = dict(prior)
    record["argv"] = argv_words
    record.setdefault("project", str(project_id))
    if isinstance(memory, dict):
        memory[key] = record
    merged[key] = record
    save_decisions(store_dir, merged)
    return list(argv_words)


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


#: File in the app store dir holding the per-project installer grants.
PROJECT_GRANTS_FILENAME = "demof13w_project_grants.json"

#: Flags that widen an install beyond installer+subcommand: a project
#: grant never covers them (the spawn path asks again).
WIDENING_FLAGS = frozenset(
    {"--force", "-g", "--global", "--unsafe-perm", "--registry"})

#: Longest accepted installer/subcommand word; longer values are refused.
_GRANT_WORD_MAX_LEN = 128


def _grant_key(project_id: str, installer: str, subcommand: str) -> str:
    """Ledger key for one project grant (NUL-joined, never ambiguous)."""
    return "\x00".join([project_id, installer, subcommand])


def _valid_grant_word(value: Any, field: str) -> str:
    """Coerced grant word, or a loud 400 for a bad one."""
    if not isinstance(value, str) or not value.strip():
        raise PermissionCheckError(
            400, "DEMOF13W_GRANT_WORD_INVALID",
            "permissions grant needs a non-empty %s string" % (field,))
    word = value.strip()
    if len(word) > _GRANT_WORD_MAX_LEN or "\x00" in word:
        raise PermissionCheckError(
            400, "DEMOF13W_GRANT_WORD_INVALID",
            "permissions grant needs a short %s string" % (field,))
    return word


def require_grant_word(value: Any, field: str) -> str:
    """Return the required grant word, else a loud 400."""
    return _valid_grant_word(value, field)


def _install_subcommand(words: list[str]) -> str:
    """Subcommand word of one install argv, or empty when flag-led.

    Manager path flags (`--prefix`, `--cwd`, `--dir`, `-C`) plus their
    values are skipped first, so a flag-led install still resolves its
    verb and a project grant covers it; a flag-led run resolves no
    verb and stays empty.
    """
    if len(words) < 2:
        return ""
    from agent_si.toolguard import guard as _guard

    rest = _guard._skip_manager_path_flags([str(word) for word in words[1:]])
    if not rest:
        return ""
    second = rest[0]
    if not second or second.startswith("-"):
        return ""
    return second


def _resolve_grants(store_dir: Any,
                    memory: Any) -> tuple[Any, dict]:
    """Fill unset grant call sites from the bound store and memory."""
    if store_dir is None:
        store_dir = _BOUND_STORE_DIR
    if memory is None:
        memory = _BOUND_GRANTS
    return store_dir, memory


def _grants_path(store_dir: str) -> str:
    """Path of the persisted project-grant ledger inside the store dir."""
    return os.path.join(store_dir, PROJECT_GRANTS_FILENAME)


def load_project_grants(store_dir: Any) -> dict[str, dict[str, Any]]:
    """Read the persisted project grants; unknown state reads empty."""
    if not store_dir:
        return {}
    try:
        with open(_grants_path(store_dir), encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    grants: dict[str, dict[str, Any]] = {}
    for key, value in data.items():
        if isinstance(key, str) and isinstance(value, dict):
            grants[key] = {
                "project": str(value.get("project", "")),
                "installer": str(value.get("installer", "")),
                "subcommand": str(value.get("subcommand", "")),
                "time": str(value.get("time", "")),
            }
    return grants


def save_project_grants(
        store_dir: Any,
        grants: dict[str, dict[str, Any]]) -> None:
    """Persist the project grants with a temp file plus os.replace."""
    if not store_dir:
        return
    os.makedirs(store_dir, exist_ok=True)
    path = _grants_path(store_dir)
    fd, tmp = tempfile.mkstemp(
        dir=store_dir, prefix="projgrants_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(
                {key: grants[key] for key in sorted(grants)},
                handle)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def record_project_grant(store_dir: Any = None, memory: Any = None,
                          project_id: str = "", installer: str = "",
                          subcommand: str = "") -> dict[str, str]:
    """Record one per-project installer grant; the file is durable.

    Later installs by the same installer head and subcommand in this
    project do not ask; anything else (flags, registries, heads,
    projects) still asks through the normal path.
    """
    project = _valid_grant_word(project_id, "project_id")
    head = _valid_grant_word(installer, "installer")
    sub = _valid_grant_word(subcommand, "subcommand")
    store_dir, memory = _resolve_grants(store_dir, memory)
    key = _grant_key(project, head, sub)
    merged = load_project_grants(store_dir)
    if isinstance(memory, dict):
        for known_key, known in memory.items():
            if isinstance(known, dict):
                merged[known_key] = known
    record = {
        "project": project,
        "installer": head,
        "subcommand": sub,
        "time": _decision_now(),
    }
    if isinstance(memory, dict):
        memory[key] = dict(record)
    merged[key] = dict(record)
    save_project_grants(store_dir, merged)
    return dict(record)


def remove_project_grant(store_dir: Any = None, memory: Any = None,
                          project_id: str = "", installer: str = "",
                          subcommand: str = "") -> bool:
    """Remove one project grant; True when a row was present."""
    store_dir, memory = _resolve_grants(store_dir, memory)
    key = _grant_key(str(project_id), str(installer), str(subcommand))
    merged = load_project_grants(store_dir)
    if isinstance(memory, dict):
        for known_key, known in memory.items():
            if isinstance(known, dict) and known_key not in merged:
                merged[known_key] = known
    if key not in merged:
        return False
    del merged[key]
    if isinstance(memory, dict):
        memory.pop(key, None)
    save_project_grants(store_dir, merged)
    return True


def get_project_grant(store_dir: Any = None, memory: Any = None,
                       project_id: str = "", installer: str = "",
                       subcommand: str = "") -> dict[str, str] | None:
    """Read one project grant row; unknown grants read as none."""
    store_dir, memory = _resolve_grants(store_dir, memory)
    key = _grant_key(str(project_id), str(installer), str(subcommand))
    entry = None
    if isinstance(memory, dict):
        entry = memory.get(key)
    if entry is None and store_dir:
        entry = load_project_grants(store_dir).get(key)
    if isinstance(entry, dict):
        return {
            "project": str(entry.get("project", "")),
            "installer": str(entry.get("installer", "")),
            "subcommand": str(entry.get("subcommand", "")),
            "time": str(entry.get("time", "")),
        }
    return None


def list_project_grants(store_dir: Any = None, memory: Any = None,
                         project_id: str = "") -> list[dict[str, str]]:
    """List grant rows for one project, ordered by installer."""
    store_dir, memory = _resolve_grants(store_dir, memory)
    merged = load_project_grants(store_dir)
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
        rows.append({
            "project_id": str(entry.get("project", "")),
            "installer": str(entry.get("installer", "")),
            "subcommand": str(entry.get("subcommand", "")),
            "time": str(entry.get("time", "")),
        })
    rows.sort(key=lambda row: (row["installer"], row["subcommand"]))
    return rows


def install_grant_allows(project_id: Any, words: Any) -> bool:
    """True when a project grant covers these exact install words.

    Cover means the same installer head and subcommand in the same
    project with no widening flag (--force, -g, --global,
    --unsafe-perm, --registry) anywhere in the words.
    """
    if not isinstance(words, (list, tuple)) or len(words) < 2:
        return False
    argv = [str(word) for word in words]
    if any(not word for word in argv):
        return False
    subcommand = _install_subcommand(argv)
    if not argv[0] or not subcommand:
        return False
    for word in argv[1:]:
        if word in WIDENING_FLAGS or word.startswith("--registry="):
            return False
    return get_project_grant(
        None, None, str(project_id), argv[0], subcommand) is not None
