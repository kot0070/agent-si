"""STEP 2 entry point for Lane B script-import commands (frozen G1).

G1 guard: evaluate(argv: list[str], action_class: str (R0|R1|R2|R3),
auth: dict) -> dict{decision: allow|ask|deny, reason: str,
evidence_ref: str}. Every import command routes argv-only through the
injected Lane A guard callable and never runs anything itself: an allow
verdict passes through, ask and deny come back as refusals. The guard is
the only policy source; this module imports no guard of its own.
"""

from __future__ import annotations

from typing import Any, Callable

# Guard wiring (STEP 2): src.agent_si.toolguard.evaluate; argv-only.
GuardEvaluate = Callable[[list[str], str, dict[str, Any]], dict[str, Any]]

ACTION_CLASSES: tuple[str, ...] = ("R0", "R1", "R2", "R3")


def list_import_commands() -> list[str]:
    return ["import list", "import approve", "import run"]


def _refusal(code: str, reason: str) -> dict[str, Any]:
    return {
        "ok": False,
        "decision": "deny",
        "error_code": code,
        "reason": reason,
        "evidence_ref": "",
    }


def run_import_command(
    argv: list[str],
    action_class: str,
    auth: dict[str, Any],
    guard_evaluate: GuardEvaluate,
) -> dict[str, Any]:
    if guard_evaluate is None or not callable(guard_evaluate):
        return _refusal("E_SCHEMA_INVALID", "guard missing")
    if (
        not isinstance(argv, list)
        or not all(isinstance(item, str) for item in argv)
    ):
        return _refusal("E_SCHEMA_INVALID", "argv must be a string list")
    if action_class not in ACTION_CLASSES:
        return _refusal("E_SCHEMA_INVALID", "unknown action class")
    verdict = guard_evaluate(list(argv), action_class, dict(auth) if isinstance(auth, dict) else {})
    if not isinstance(verdict, dict) or verdict.get("decision") not in ("allow", "ask", "deny"):
        return _refusal("E_SCHEMA_INVALID", "guard verdict malformed")
    decision = verdict["decision"]
    reason = verdict.get("reason", "")
    evidence_ref = verdict.get("evidence_ref", "")
    if decision != "allow":
        return {
            "ok": False,
            "decision": decision,
            "error_code": "E_APPROVAL_MISSING",
            "reason": reason,
            "evidence_ref": evidence_ref,
        }
    if not isinstance(auth, dict) or not auth.get("actor"):
        return _refusal("E_APPROVAL_MISSING", "approval missing")
    return {
        "ok": True,
        "decision": "allow",
        "error_code": "",
        "reason": reason,
        "evidence_ref": evidence_ref,
    }
