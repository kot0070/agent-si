"""Per-instance health plus model readiness. Latest check wins.

A provider reporting ONLINE never marks a model READY: model readiness
comes only from adapter probes recorded here separately.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


PROVIDER_STATUSES = ("ONLINE", "DEGRADED", "OFFLINE", "UNKNOWN")

MODEL_STATUSES = ("READY", "LOADING", "DEGRADED", "ERROR", "OFFLINE", "UNKNOWN")

MEASURED = "MEASURED"
NOT_MEASURED = "UNAVAILABLE"


def _now() -> float:
    return time.time()


@dataclass
class ProviderHealth:
    provider_id: str
    instance_id: str
    status: str
    last_check: float
    latency_ms: float | None = None
    error: str | None = None
    capacity_state: str | None = None

    def view(self) -> dict:
        return {
            "provider_id": self.provider_id,
            "instance_id": self.instance_id,
            "status": self.status,
            "last_check": self.last_check,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "capacity_state": self.capacity_state,
        }


@dataclass
class ModelHealth:
    provider_id: str
    model: str
    status: str
    last_check: float
    latency_ms: float | None = None
    error: str | None = None

    def view(self) -> dict:
        return {
            "provider_id": self.provider_id,
            "model": self.model,
            "status": self.status,
            "last_check": self.last_check,
            "latency_ms": self.latency_ms,
            "error": self.error,
        }


class ProviderHealthLog:
    def __init__(self) -> None:
        self._entries: dict[tuple, ProviderHealth] = {}

    def record(
        self,
        provider_id: str,
        instance_id: str,
        status: str,
        *,
        latency_ms: float | None = None,
        error: str | None = None,
        capacity_state: str | None = None,
        checked_at: float | None = None,
    ) -> ProviderHealth:
        if status not in PROVIDER_STATUSES:
            raise ValueError("unknown provider status: %r" % (status,))
        entry = ProviderHealth(
            provider_id=provider_id,
            instance_id=instance_id,
            status=status,
            last_check=_now() if checked_at is None else checked_at,
            latency_ms=latency_ms,
            error=error,
            capacity_state=capacity_state,
        )
        self._entries[(provider_id, instance_id)] = entry
        return entry

    def latest(self, provider_id: str, instance_id: str) -> ProviderHealth | None:
        return self._entries.get((provider_id, instance_id))

    def status_of(self, provider_id: str, instance_id: str) -> str:
        entry = self.latest(provider_id, instance_id)
        return entry.status if entry is not None else "UNKNOWN"

    def snapshot(self) -> dict:
        return {
            "%s/%s" % key: entry.view() for key, entry in self._entries.items()
        }


class ModelHealthLog:
    def __init__(self) -> None:
        self._entries: dict[tuple, ModelHealth] = {}

    def record(
        self,
        provider_id: str,
        model: str,
        status: str,
        *,
        latency_ms: float | None = None,
        error: str | None = None,
        checked_at: float | None = None,
    ) -> ModelHealth:
        if status not in MODEL_STATUSES:
            raise ValueError("unknown model status: %r" % (status,))
        entry = ModelHealth(
            provider_id=provider_id,
            model=model,
            status=status,
            last_check=_now() if checked_at is None else checked_at,
            latency_ms=latency_ms,
            error=error,
        )
        self._entries[(provider_id, model)] = entry
        return entry

    def latest(self, provider_id: str, model: str) -> ModelHealth | None:
        return self._entries.get((provider_id, model))

    def status_of(self, provider_id: str, model: str) -> str:
        entry = self.latest(provider_id, model)
        return entry.status if entry is not None else "UNKNOWN"

    def snapshot(self) -> dict:
        return {
            "%s/%s" % key: entry.view() for key, entry in self._entries.items()
        }
