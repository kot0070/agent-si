"""Per-adapter usage reporting support records.

Shape follows the frozen usage capability fields: state plus per-metric
evidence plus streaming recorded separately from the base channel. A
metric without probe evidence reads UNAVAILABLE, never assumed.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Mapping


USAGE_STATES = ("VERIFIED", "PARTIAL", "UNSUPPORTED", "UNKNOWN")

UNPERMITTED = "UNPERMITTED"

METRIC_MEASURED = "MEASURED"
METRIC_UNAVAILABLE = "UNAVAILABLE"

USAGE_METRICS = (
    "input_tokens",
    "output_tokens",
    "cached_tokens",
    "reasoning_tokens",
    "raw_usage",
    "request_level_usage",
    "cost_fields",
)


class LocalProbeNotPermitted(PermissionError):
    pass


def _now() -> float:
    return time.time()


@dataclass
class UsageSupport:
    provider_id: str
    instance_id: str
    state: str = "UNKNOWN"
    metrics: dict = field(default_factory=dict)
    stream_metrics: dict = field(default_factory=dict)
    evidence_ref: str | None = None
    verified_at: float | None = None

    def metric_state(self, metric: str, channel: str = "usage") -> str:
        table = self.stream_metrics if channel == "stream" else self.metrics
        return (
            METRIC_MEASURED if table.get(metric) is True else METRIC_UNAVAILABLE
        )

    def view(self) -> dict:
        return {
            "provider_id": self.provider_id,
            "instance_id": self.instance_id,
            "state": self.state,
            "usage": {
                metric: self.metric_state(metric) for metric in USAGE_METRICS
            },
            "stream_usage": {
                metric: self.metric_state(metric, "stream")
                for metric in USAGE_METRICS
            },
            "evidence_ref": self.evidence_ref,
            "verified_at": self.verified_at,
        }


class UsageSupportLog:
    def __init__(self) -> None:
        self._entries: dict[tuple, UsageSupport] = {}

    def record_probe(
        self,
        provider_id: str,
        instance_id: str,
        *,
        capabilities: Mapping[str, Any] | None = None,
        stream_capabilities: Mapping[str, Any] | None = None,
        evidence_ref: str | None = None,
        verified_at: float | None = None,
    ) -> UsageSupport:
        base = {
            metric: bool((capabilities or {}).get(metric, False))
            for metric in USAGE_METRICS
        }
        if stream_capabilities is None:
            stream = {metric: False for metric in USAGE_METRICS}
        else:
            stream = {
                metric: bool(stream_capabilities.get(metric, False))
                for metric in USAGE_METRICS
            }
        hits = sum(1 for value in base.values() if value)
        if hits == len(USAGE_METRICS):
            state = "VERIFIED"
        elif hits > 0:
            state = "PARTIAL"
        else:
            state = "UNSUPPORTED"
        entry = UsageSupport(
            provider_id=provider_id,
            instance_id=instance_id,
            state=state,
            metrics=base,
            stream_metrics=stream,
            evidence_ref=evidence_ref,
            verified_at=_now() if verified_at is None else verified_at,
        )
        self._entries[(provider_id, instance_id)] = entry
        return entry

    def record_local_probe_refused(
        self, provider_id: str, instance_id: str, *, evidence_ref: str | None = None
    ) -> UsageSupport:
        entry = UsageSupport(
            provider_id=provider_id,
            instance_id=instance_id,
            state=UNPERMITTED,
            metrics={metric: False for metric in USAGE_METRICS},
            stream_metrics={metric: False for metric in USAGE_METRICS},
            evidence_ref=evidence_ref,
            verified_at=_now(),
        )
        self._entries[(provider_id, instance_id)] = entry
        return entry

    def get(self, provider_id: str, instance_id: str) -> UsageSupport | None:
        return self._entries.get((provider_id, instance_id))

    def snapshot(self) -> dict:
        return {"%s/%s" % key: entry.view() for key, entry in self._entries.items()}
