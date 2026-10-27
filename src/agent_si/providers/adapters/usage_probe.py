"""Usage capability probes, one per adapter (SPEC 33A).

Each provider adapter is probed for usage reporting; streaming usage is
verified separately. When a provider reports partial usage, missing
metrics stay UNAVAILABLE. The provider raw usage reference is preserved
where safe (plain scalar payloads) and useful. Probes take injected
fake transports in tests (fakes only, K06 rule) and never touch the
network. Local probing permission is the caller's duty: unpermitted
local probing is a violation, so probes never initiate it themselves.
"""
from datetime import datetime, timezone

from .base import UNAVAILABLE, TransportUnsupportedError

#: Usage metric keys reported per adapter.
METRIC_KEYS = (
    "input_tokens",
    "output_tokens",
    "cached_tokens",
    "reasoning_tokens",
)

#: Exact UsageReportingCapability fields (SPEC 33A).
USAGE_CAPABILITY_FIELDS = (
    "provider_id",
    "instance_id",
    "state",
    "input_tokens",
    "output_tokens",
    "cached_tokens",
    "reasoning_tokens",
    "raw_usage",
    "stream_usage",
    "cost_fields",
    "request_level_usage",
    "verified_at",
    "evidence_ref",
)


def _utcnow_iso():
    return datetime.now(timezone.utc).isoformat()


def _safe_raw(payload, safe):
    """Keep the raw usage reference where safe: the transport must mark
    the payload safe AND it must be a plain scalar mapping; else closed."""
    if safe is not True:
        return UNAVAILABLE
    if not isinstance(payload, dict):
        return UNAVAILABLE
    for value in payload.values():
        if not isinstance(value, (int, float, str, bool, type(None))):
            return UNAVAILABLE
    return dict(payload)


def _metrics_from(usage):
    """Split a usage payload into evidenced ints; missing stays UNAVAILABLE."""
    usage = usage if isinstance(usage, dict) else {}
    present = {}
    for key in METRIC_KEYS:
        value = usage.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            present[key] = value
    return present


def _state_for(present, answered):
    if len(present) == len(METRIC_KEYS):
        return "VERIFIED"
    if present:
        return "PARTIAL"
    if answered:
        return "UNKNOWN"
    return "UNKNOWN"


def probe_usage(provider_id, instance_id, transport, evidence_ref=None,
                verified_at=None):
    """Probe non-streaming usage reporting over an injected transport."""
    stamp = verified_at or _utcnow_iso()
    try:
        reply = transport({
            "probe": "usage",
            "provider_id": provider_id,
            "instance_id": instance_id,
            "stream": False,
        })
    except TransportUnsupportedError:
        return _capability(provider_id, instance_id, "UNSUPPORTED",
                           {}, UNAVAILABLE, UNAVAILABLE, stamp, evidence_ref)
    except Exception:
        return _capability(provider_id, instance_id, "UNKNOWN",
                           {}, UNAVAILABLE, UNAVAILABLE, stamp, evidence_ref)
    reply = reply if isinstance(reply, dict) else {}
    usage = reply.get("usage")
    present = _metrics_from(usage)
    raw = _safe_raw(reply.get("raw"), reply.get("raw_safe"))
    cost_fields = reply.get("cost_fields", UNAVAILABLE)
    request_level = reply.get("request_level_usage", UNAVAILABLE)
    state = _state_for(present, answered=True)
    return _capability(provider_id, instance_id, state, present, raw,
                       UNAVAILABLE, stamp, evidence_ref,
                       cost_fields=cost_fields,
                       request_level_usage=request_level)


def probe_stream_usage(provider_id, instance_id, transport,
                       evidence_ref=None, verified_at=None):
    """Probe streaming usage reporting separately (SPEC 33A)."""
    stamp = verified_at or _utcnow_iso()
    try:
        reply = transport({
            "probe": "usage",
            "provider_id": provider_id,
            "instance_id": instance_id,
            "stream": True,
        })
    except TransportUnsupportedError:
        return {
            "provider_id": provider_id,
            "instance_id": instance_id,
            "stream_state": "UNSUPPORTED",
            "stream_usage": UNAVAILABLE,
            "verified_at": stamp,
            "evidence_ref": evidence_ref,
        }
    except Exception:
        return {
            "provider_id": provider_id,
            "instance_id": instance_id,
            "stream_state": "UNKNOWN",
            "stream_usage": UNAVAILABLE,
            "verified_at": stamp,
            "evidence_ref": evidence_ref,
        }
    reply = reply if isinstance(reply, dict) else {}
    present = _metrics_from(reply.get("usage"))
    stream_usage = {key: present.get(key, UNAVAILABLE) for key in METRIC_KEYS}
    return {
        "provider_id": provider_id,
        "instance_id": instance_id,
        "stream_state": _state_for(present, answered=True),
        "stream_usage": stream_usage,
        "verified_at": stamp,
        "evidence_ref": evidence_ref,
    }


def probe_adapter(provider_id, instance_id, usage_transport,
                  stream_transport=None, evidence_ref=None, verified_at=None):
    """Full UsageReportingCapability: non-streaming probe plus the
    separately verified streaming probe (UNAVAILABLE when not probed)."""
    stamp = verified_at or _utcnow_iso()
    capability = probe_usage(provider_id, instance_id, usage_transport,
                             evidence_ref=evidence_ref, verified_at=stamp)
    if stream_transport is None:
        return capability
    stream = probe_stream_usage(provider_id, instance_id, stream_transport,
                                evidence_ref=evidence_ref, verified_at=stamp)
    capability["stream_usage"] = stream["stream_usage"]
    return capability


def _capability(provider_id, instance_id, state, present, raw, stream_usage,
                verified_at, evidence_ref, cost_fields=UNAVAILABLE,
                request_level_usage=UNAVAILABLE):
    capability = {
        "provider_id": provider_id,
        "instance_id": instance_id,
        "state": state,
        "raw_usage": raw,
        "stream_usage": stream_usage,
        "cost_fields": cost_fields,
        "request_level_usage": request_level_usage,
        "verified_at": verified_at,
        "evidence_ref": evidence_ref,
    }
    for key in METRIC_KEYS:
        capability[key] = present.get(key, UNAVAILABLE)
    ordered = {key: capability[key] for key in USAGE_CAPABILITY_FIELDS}
    return ordered
