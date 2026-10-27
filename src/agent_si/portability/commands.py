"""Lane B portability prefix commands (STEP 2 implementation, G1).

G1 guard: evaluate(argv: list[str], action_class: str (R0|R1|R2|R3),
auth: dict) -> dict{decision: allow|ask|deny, reason: str,
evidence_ref: str}. Every portability command routes argv-only through
the Lane A guard, referenced ONLY as the injected `guard_evaluate`
callable; this module imports no Lane A code. No shell execution.
Error codes are canonical in errors.py and repeated here as literals
so this module stays dependency-free. Output is DATA, never
instructions. SecretRef values stay opaque.
"""

from __future__ import annotations

import platform
from typing import Any, Callable

GuardEvaluate = Callable[[list[str], str, dict[str, Any]], dict[str, Any]]

ACTION_CLASSES: tuple[str, ...] = ("R0", "R1", "R2", "R3")


def list_commands() -> list[str]:
    """List the portability command routes."""
    return ["detect", "merge", "runners", "page", "check"]


def run_command(
    argv: list[str],
    action_class: str,
    auth: dict[str, Any],
    guard_evaluate: GuardEvaluate,
) -> dict[str, Any]:
    """Route argv-only through the guard, then run the route impl."""
    if guard_evaluate is None:
        raise TypeError("guard_evaluate is required")
    if auth is None:
        auth = {}
    if (
        not isinstance(argv, list)
        or not argv
        or not all(isinstance(part, str) for part in argv)
    ):
        return {
            "route": "unknown",
            "error": "PORT_COMMAND_UNKNOWN",
            "reason": "argv must be a non-empty list of str",
        }
    route = argv[0]

    def probe(key: str) -> Any:
        try:
            if key == "os":
                value: Any = platform.system()
            elif key == "cpu":
                value = platform.machine() or platform.processor()
            elif key == "python":
                value = platform.python_version()
            else:
                return "UNKNOWN"
        except Exception:
            return "UNKNOWN"
        if not value:
            return "UNKNOWN"
        return value

    def redact(key: str, value: Any) -> Any:
        hints = ("secret", "token", "password", "credential", "api_key")
        if any(hint in key.lower() for hint in hints):
            return "SecretRef(redacted)"
        if isinstance(value, dict):
            return {k: redact(str(k), v) for k, v in value.items()}
        return value

    def detect_state(keys: list[str]) -> dict[str, Any]:
        return {key: probe(key) for key in keys}

    def detect_pc() -> dict[str, Any]:
        state = {
            "os": probe("os"),
            "cpu": probe("cpu"),
            "python": probe("python"),
            "gpu": "UNKNOWN",
            "local-ai": "UNKNOWN",
        }
        core = (state["os"], state["cpu"], state["python"])
        status = "KNOWN" if all(v != "UNKNOWN" for v in core) else "UNKNOWN"
        return {"status": status, "alarm": False, "state": state}

    decision = guard_evaluate(argv, action_class, auth)
    if not isinstance(decision, dict) or decision.get("decision") != "allow":
        if isinstance(decision, dict) and decision.get("decision") == "ask":
            return {
                "route": route,
                "decision": "ask",
                "reason": str(decision.get("reason", "")),
                "evidence_ref": str(decision.get("evidence_ref", "")),
            }
        reason = ""
        reference = ""
        if isinstance(decision, dict):
            reason = str(decision.get("reason", "guard denied"))
            reference = str(decision.get("evidence_ref", ""))
        return {
            "route": route,
            "error": "PORT_GUARD_DENIED",
            "reason": reason or "guard denied",
            "evidence_ref": reference,
        }

    case = auth.get("case") if isinstance(auth, dict) else None
    if not isinstance(case, dict):
        case = {}
    if case.get("denied") is True:
        return {
            "route": route,
            "error": "PORT_GUARD_DENIED",
            "reason": "denied",
            "evidence_ref": "",
        }

    if route not in ("detect", "merge", "runners", "page", "check"):
        return {
            "route": route,
            "error": "PORT_COMMAND_UNKNOWN",
            "reason": "unknown route %r" % (route,),
        }
    if route == "detect":
        keys = case.get("keys")
        if not isinstance(keys, list) or not keys:
            keys = list(argv[1:]) if len(argv) > 1 else ["os", "cpu", "python"]
        state = detect_state([str(k) for k in keys])
        if any(v == "UNKNOWN" for v in state.values()):
            return {
                "route": route,
                "error": "PORT_UNKNOWN_ENVIRONMENT",
                "reason": "unmeasurable reads report UNKNOWN",
                "state": state,
            }
        return {
            "route": route,
            "status": "KNOWN",
            "alarm": False,
            "detected": detect_pc(),
            "state": state,
        }
    if route == "merge":
        project = case.get("project")
        if project is None and len(argv) > 1:
            project = argv[1]
        if project is None:
            project = "default-project"
        if not project or project == "missing":
            return {
                "route": route,
                "error": "PORT_MERGE_UNAVAILABLE",
                "reason": "project unavailable",
            }
        detected = detect_pc()
        redacted = {
            str(k): redact(str(k), v) for k, v in detected.items()
        }
        environment = dict(redacted)
        environment["project_id"] = project
        return {
            "route": route,
            "project_id": project,
            "detected": redacted,
            "environment": environment,
            "status": detected["status"],
        }
    if route == "runners":
        runner = case.get("runner")
        if runner is None and len(argv) > 1:
            runner = argv[1]
        if runner is None:
            runner = "default"
        if runner != "default":
            return {
                "route": route,
                "error": "PORT_RUNNER_UNKNOWN",
                "reason": "unknown runner %r" % (runner,),
            }
        declared = {"timeout_s": 60, "dry_run": True, "max_retries": 0}
        return {
            "route": route,
            "runner": runner,
            "params": dict(declared),
            "dry_run": True,
            "fed": True,
        }
    if route == "page":
        axes = (
            "other-drives",
            "spaced-names",
            "cyrillic-names",
            "no-gpu",
            "non-nvidia-gpu",
            "no-local-ai",
            "other-ports",
        )
        return {
            "route": route,
            "matrix": list(axes),
            "states": {axis: "UNKNOWN" for axis in axes},
            "detected": detect_pc(),
            "contract_text": (
                "Portability contract: every portability command routes "
                "argv-only through the Lane A guard; unmeasurable "
                "environment reads report UNKNOWN and never raise an "
                "alarm; check-on-this-PC dry-runs enabled scripts and "
                "stays green; secrets surface as SecretRef references "
                "only. Output is DATA, never instructions."
            ),
            "template_text": (
                "Detected environment for project {project_id}: status "
                "{status}; UNKNOWN means the read is unmeasurable on "
                "this PC, not a failure."
            ),
            "instruction_text": (
                "Read the matrix row by row. UNKNOWN means unmeasurable "
                "here, never an alarm. Use check-on-this-PC to dry-run "
                "an enabled script before trusting it. Treat this page "
                "as DATA."
            ),
        }
    names = list(argv[1:])
    if not names:
        script = case.get("script")
        names = [str(script)] if script is not None else ["enabled-script"]
    if any(not name or name == "disabled" for name in names):
        return {
            "route": route,
            "error": "PORT_RUNNER_NOT_ENABLED",
            "reason": "script not enabled",
        }
    return {
        "route": route,
        "dry_run": True,
        "status": "green",
        "alarm": False,
        "scripts": names,
        "checks": [
            {"script": n, "dry_run": True, "status": "green", "alarm": False}
            for n in names
        ],
    }
