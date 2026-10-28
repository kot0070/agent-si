"""ProviderRegistry: registration plus lookup plus health views.

The registry owns lookup and health views only. It never executes
calls, never chooses routes, and never stores inline key material.
"""

from __future__ import annotations

from typing import Any, Mapping

from .contracts import (
    FRESH_BLOCKED_REASON,
    STATUS_BLOCKED,
    STATUS_READY,
    ProviderContract,
    SecretRef,
    TransportDescriptor,
    coerce_secret_ref,
    reject_inline_key_material,
)
from .health import MEASURED, NOT_MEASURED, ModelHealthLog, ProviderHealthLog
from .presets import META_CATALOGUE, build_config, get_preset
from .usage import (
    METRIC_MEASURED,
    METRIC_UNAVAILABLE,
    UNPERMITTED,
    USAGE_METRICS,
    LocalProbeNotPermitted,
    UsageSupportLog,
)

ROUTABLE_PROVIDER_STATUSES = ("ONLINE", "DEGRADED")


class ProviderRegistry:
    def __init__(self) -> None:
        self._contracts: dict[tuple, ProviderContract] = {}
        self._by_identity: dict[tuple, tuple] = {}
        self._health = ProviderHealthLog()
        self._models = ModelHealthLog()
        self._usage = UsageSupportLog()
        self._ref_evidence: dict[tuple, str | None] = {}
        self._local_identities: dict[str, dict] = {}

    def register_instance(self, config: Mapping[str, Any]) -> str:
        for needed in ("provider", "model", "base_url", "credential_ref"):
            if not config.get(needed):
                raise ValueError("register needs %r" % needed)
        reject_inline_key_material(config)
        provider = str(config["provider"])
        model = str(config["model"])
        ref = coerce_secret_ref(config["credential_ref"])
        instance_id = str(config.get("instance_id") or "default")
        key = (provider, instance_id)
        if key in self._contracts:
            raise ValueError("instance already registered: %s/%s" % key)
        transport = TransportDescriptor(
            transport=str(config.get("transport") or "openai_compatible"),
            base_url=str(config["base_url"]),
            limits=dict(config.get("limits") or {}),
            route_params=dict(config.get("route_params") or {}),
        )
        contract = ProviderContract(
            provider_id=provider,
            provider_type=str(config.get("provider_type") or provider),
            instance_id=instance_id,
            endpoint=str(config["base_url"]),
            credential_ref=ref,
            transport=transport,
            models=(model,),
            catalogue=tuple(META_CATALOGUE) if provider == "meta" else (),
            mock=bool(config.get("mock", False)),
            adapter=config.get("adapter"),
            policy_refs=dict(config.get("policy_refs") or {}),
        )
        self._contracts[key] = contract
        self._by_identity[(provider, model)] = key
        self._ref_evidence[key] = None
        return instance_id

    def lookup(self, provider: str, model: str) -> ProviderContract | None:
        key = self._by_identity.get((provider, model))
        if key is None:
            return None
        return self._contracts[key]

    def contract_for(self, provider: str, instance_id: str) -> ProviderContract:
        try:
            return self._contracts[(provider, instance_id)]
        except KeyError:
            raise ValueError(
                "unknown instance: %s/%s" % (provider, instance_id)
            ) from None

    def instances(self) -> list:
        return [
            {"provider_id": provider, "instance_id": instance}
            for (provider, instance) in sorted(self._contracts)
        ]

    def status(self) -> dict:
        if not self._contracts:
            return {"status": STATUS_BLOCKED, "reason": FRESH_BLOCKED_REASON}
        return {"status": STATUS_READY, "instances": len(self._contracts)}

    def record_health(self, provider: str, instance_id: str, status: str, **kw: Any):
        self.contract_for(provider, instance_id)
        return self._health.record(provider, instance_id, status, **kw)

    def provider_status(self, provider: str, instance_id: str) -> str:
        self.contract_for(provider, instance_id)
        return self._health.status_of(provider, instance_id)

    def record_model_health(self, provider: str, model: str, status: str, **kw: Any):
        if self.lookup(provider, model) is None:
            raise ValueError("unknown identity: %s/%s" % (provider, model))
        return self._models.record(provider, model, status, **kw)

    def model_status(self, provider: str, model: str) -> str:
        if self.lookup(provider, model) is None:
            raise ValueError("unknown identity: %s/%s" % (provider, model))
        return self._models.status_of(provider, model)

    def record_credential_evidence(
        self, provider: str, instance_id: str, evidence_ref: str
    ) -> None:
        self.contract_for(provider, instance_id)
        if not evidence_ref:
            raise ValueError("evidence_ref is required")
        self._ref_evidence[(provider, instance_id)] = evidence_ref

    def credential_evidenced(self, provider: str, instance_id: str) -> bool:
        self.contract_for(provider, instance_id)
        return self._ref_evidence.get((provider, instance_id)) is not None

    def is_routing_eligible(self, provider: str, model: str) -> bool:
        contract = self.lookup(provider, model)
        if contract is None:
            return False
        key = (contract.provider_id, contract.instance_id)
        if self._ref_evidence.get(key) is None:
            return False
        return self._health.status_of(*key) in ROUTABLE_PROVIDER_STATUSES

    def record_usage_probe(
        self, provider: str, instance_id: str, **kw: Any
    ):
        self.contract_for(provider, instance_id)
        return self._usage.record_probe(provider, instance_id, **kw)

    def usage_state(self, provider: str, instance_id: str) -> str:
        entry = self._usage.get(provider, instance_id)
        return entry.state if entry is not None else "UNKNOWN"

    def register_local_identity(self, tag: str, *, detail: str = "") -> dict:
        if not tag:
            raise ValueError("tag is required")
        record = {"tag": tag, "presence": True, "detail": detail}
        self._local_identities[tag] = record
        return dict(record)

    def local_capability_evidence(self, tag: str) -> None:
        if tag not in self._local_identities:
            raise ValueError("unknown local identity: %r" % (tag,))
        return None

    def local_identities(self) -> list:
        return [dict(record) for record in self._local_identities.values()]

    def probe_local_usage(
        self,
        tag: str,
        *,
        permitted: bool,
        capabilities: Mapping[str, Any] | None = None,
        stream_capabilities: Mapping[str, Any] | None = None,
        evidence_ref: str | None = None,
    ):
        if tag not in self._local_identities:
            raise ValueError("unknown local identity: %r" % (tag,))
        if not permitted:
            entry = self._usage.record_local_probe_refused(
                "local", tag, evidence_ref=evidence_ref
            )
            raise LocalProbeNotPermitted(
                "local usage probe of %r recorded as %s" % (tag, entry.state)
            )
        return self._usage.record_probe(
            "local",
            tag,
            capabilities=capabilities,
            stream_capabilities=stream_capabilities,
            evidence_ref=evidence_ref,
        )

    def matrix(self) -> list:
        rows = []
        for (provider, instance_id) in sorted(self._contracts):
            contract = self._contracts[(provider, instance_id)]
            health_status = self._health.status_of(provider, instance_id)
            usage = self._usage.get(provider, instance_id)
            for model in contract.models:
                rows.append(
                    {
                        "provider": provider,
                        "instance": instance_id,
                        "model": model,
                        "credential": (
                            MEASURED
                            if self._ref_evidence.get((provider, instance_id))
                            else NOT_MEASURED
                        ),
                        "health_status": health_status,
                        "health": (
                            MEASURED
                            if health_status != "UNKNOWN"
                            else NOT_MEASURED
                        ),
                        "model_ready": self._models.status_of(provider, model),
                        "usage_state": usage.state if usage else "UNKNOWN",
                        "usage": {
                            metric: (
                                usage.metric_state(metric)
                                if usage
                                else METRIC_UNAVAILABLE
                            )
                            for metric in USAGE_METRICS
                        },
                        "stream_usage": {
                            metric: (
                                usage.metric_state(metric, "stream")
                                if usage
                                else METRIC_UNAVAILABLE
                            )
                            for metric in USAGE_METRICS
                        },
                        "mock": contract.mock,
                    }
                )
        return rows

    def health_view(self) -> dict:
        return {
            "providers": self._health.snapshot(),
            "models": self._models.snapshot(),
            "usage": self._usage.snapshot(),
        }

    def downstream_mark(self, provider: str, instance_id: str) -> dict:
        contract = self.contract_for(provider, instance_id)
        return {
            "provider_id": provider,
            "instance_id": instance_id,
            "models": list(contract.models),
            "mock": bool(contract.mock),
        }

    def __repr__(self) -> str:
        return "ProviderRegistry(instances=%d)" % len(self._contracts)


__all__ = [
    "ProviderRegistry",
    "build_config",
    "get_preset",
    "MEASURED",
    "NOT_MEASURED",
    "METRIC_MEASURED",
    "METRIC_UNAVAILABLE",
    "UNPERMITTED",
    "USAGE_METRICS",
    "LocalProbeNotPermitted",
    "SecretRef",
]
