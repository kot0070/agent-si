# K04 Lane A2 — telemetry event port for routing choices.
# The event store itself is owned by K13 later; this port only emits
# event-shaped dicts through caller-provided callbacks. No secrets ever
# travel in an event payload (manifest section 20A).
"""Emit every routing choice with its reason."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping, Optional

from .types import utcnow


def new_event_id(prefix: str = "ev") -> str:
    import uuid
    return "%s-%s" % (prefix, uuid.uuid4().hex[:12])


def routing_event(*, project_id: str, task_id: str, run_id: str,
                  role: Optional[str] = None,
                  route: Optional[str] = None,
                  provider: Optional[str] = None,
                  model: Optional[str] = None,
                  event_type: str = "routing_decision",
                  reason: str = "",
                  routing_decision_ref: Optional[str] = None,
                  routing_snapshot_id: Optional[str] = None,
                  mock: bool = False,
                  fallback_reason: Optional[str] = None,
                  capability_rule: Optional[str] = None) -> Dict[str, Any]:
    """Build a routing telemetry envelope (never carries secrets)."""
    return {
        "event_id": new_event_id("ev"),
        "project_id": project_id,
        "task_id": task_id,
        "run_id": run_id,
        "timestamp": utcnow(),
        "role": role,
        "route": route,
        "provider": provider,
        "model": model,
        "event_type": event_type,
        "reason": reason,
        "routing_decision_ref": routing_decision_ref,
        "routing_snapshot_id": routing_snapshot_id,
        "mock": bool(mock),
        "fallback_reason": fallback_reason,
        "capability_rule": capability_rule,
    }


class TelemetryEmitter:
    """Fan-out emitter; sinks are plain callables taking one event dict."""

    def __init__(self) -> None:
        self._sinks: List[Callable[[Dict[str, Any]], None]] = []

    def add_sink(self, sink: Callable[[Dict[str, Any]], None]) -> None:
        self._sinks.append(sink)

    def emit(self, event: Mapping[str, Any]) -> Dict[str, Any]:
        envelope = dict(event)
        envelope.setdefault("event_id", new_event_id("ev"))
        envelope.setdefault("timestamp", utcnow())
        for sink in self._sinks:
            sink(dict(envelope))
        return envelope
