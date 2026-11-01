"""Model-choice recording with reason (K04NEXT3 C2).

Budget-side seam for R-357: every model choice is recorded with its
reason. record_model_choice appends a routing_decided telemetry event
carrying the provider, the model and the why-text, and refuses an empty
reason instead of recording a choiceless row. choice_summary_plain
renders the same row as one plain-language line for the picker.
"""
from __future__ import annotations

from agent_si.budget import telemetry as _telemetry


def record_model_choice(log, *, event_id, project_id, timestamp, task_id,
                        run_id, role, provider, model, reason, route="AUTO",
                        pricing_snapshot_id=None, usage_ref=None):
    """Append the choice event; an empty reason is refused, never stored."""
    if not (isinstance(reason, str) and reason.strip()):
        raise ValueError(
            "record_model_choice needs a non-empty reason "
            "(every model choice carries its reason)")
    event = _telemetry.build_telemetry_event(
        event_id=event_id, project_id=project_id, timestamp=timestamp,
        task_id=task_id, run_id=run_id, role=role, route=route,
        provider=provider, model=model, event_type="routing_decided",
        routing_snapshot_id=pricing_snapshot_id,
        metric_refs=[usage_ref] if usage_ref else [])
    event["reason"] = reason
    return log.append(event)


def choice_summary_plain(event):
    """One plain-language line for a recorded choice event."""
    return "role %s uses %s model %s: %s" % (
        event.get("role"), event.get("provider"), event.get("model"),
        event.get("reason"))
