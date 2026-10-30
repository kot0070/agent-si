"""K06 declared-services acceptance runs (row 253).

An acceptance run executes one declared service through the real tool
belt (agent_si.worker_tools.guarded_dispatch over a registry carrying
the real read-only ``status`` tool below) and files the run with its
decision plus evidence refs. The store is owned by the caller (per-app
state on the served path); this module holds no globals.
"""

from __future__ import annotations

from typing import Any


def _status_impl(argv: list[str], action_class: str, auth: dict[str, Any]) -> dict[str, Any]:
    """Real read-only status tool: service state as DATA, no side effect."""
    return {
        "ok": True,
        "argv": list(argv),
        "action_class": action_class,
        "output": {"service": argv[0] if argv else "status", "state": "available"},
    }


class StatusEntryPoint:
    """Real entry point behind the declared ``status`` service route."""

    name = "status"
    action_class = "R0"

    def load(self):  # type: ignore[no-untyped-def]
        """Resolve and return the real status tool implementation."""
        return _status_impl


def build_acceptance_registry():  # type: ignore[no-untyped-def]
    """Build a belt registry carrying the real declared-service tools."""
    from agent_si.worker_tools.registry import ToolRegistry

    registry = ToolRegistry()
    registry.register(StatusEntryPoint())
    return registry


def file_acceptance_run(
    store: list[dict[str, Any]],
    *,
    service: str,
    argv: list[str],
    action_class: str,
    auth: dict[str, Any],
    registry: Any = None,
    task_authorized: list[str] | None = None,
    guard_store: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run one declared service through the real belt and file the run.

    Validation failures return ``{"error": <code>}`` without touching
    the belt. A valid call executes via guarded_dispatch, so the Lane A
    guard stays on the production path, then files the run with its
    decision plus evidence refs.
    """
    from agent_si.services.commands import list_commands
    from agent_si.worker_tools.dispatcher import guarded_dispatch

    if service not in list_commands():
        return {"error": "E_UNKNOWN_SERVICE"}
    target = registry if registry is not None else build_acceptance_registry()
    allowed = task_authorized if task_authorized is not None else [service]
    try:
        result = guarded_dispatch(
            list(argv),
            action_class,
            dict(auth),
            tool=service,
            registry=target,
            task_authorized=allowed,
            guard_store=guard_store if guard_store is not None else [],
        )
    except Exception as exc:
        return {"error": type(exc).__name__, "detail": str(exc)}
    run = {
        "run_id": "acceptance-%d" % (len(store) + 1),
        "service": service,
        "argv": list(argv),
        "action_class": action_class,
        "ok": bool(result.get("ok", False)),
        "evidence_refs": ["belt:acceptance:%s" % (service,)],
        "output": result.get("output"),
    }
    store.append(dict(run))
    return run


def list_acceptance_runs(store: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a copy of every filed acceptance run, oldest first."""
    return [dict(run) for run in store]
