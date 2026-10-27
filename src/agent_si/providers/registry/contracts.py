"""Registry contracts: identity, transport, and safe public views.

Lookup plus health-view shapes only. Nothing here executes calls,
picks routes, or holds inline key material: access travels as
SecretRef values, never inline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


TRANSPORT_OPENAI_COMPATIBLE = "openai_compatible"
TRANSPORT_LITELLM_BACKED = "litellm_backed"
TRANSPORT_LOCAL = "local"

TRANSPORT_TYPES = (
    TRANSPORT_OPENAI_COMPATIBLE,
    TRANSPORT_LITELLM_BACKED,
    TRANSPORT_LOCAL,
)

STATUS_BLOCKED = "BLOCKED"
STATUS_READY = "READY"

FRESH_BLOCKED_REASON = "no provider instances configured"

RAW_INLINE_FIELD_NAMES = frozenset(
    {
        "api_key",
        "apikey",
        "api_secret",
        "secret_value",
        "client_secret",
        "access_token",
        "password",
        "authorization",
        "x-api-key",
    }
)

SECRET_REF_FIELDS = (
    "secret_id",
    "provider_id",
    "type",
    "scope",
    "source",
    "created_at",
    "last_rotated_at",
)


@dataclass(frozen=True)
class SecretRef:
    """Pointer to stored key material. Carries ids only, never the key itself."""

    secret_id: str
    provider_id: str
    type: str = "api_key"
    scope: str = ""
    source: str = ""
    created_at: str = ""
    last_rotated_at: str = ""

    def describe(self) -> dict:
        return {
            "secret_id": self.secret_id,
            "provider_id": self.provider_id,
            "type": self.type,
            "scope": self.scope,
            "source": self.source,
            "created_at": self.created_at,
            "last_rotated_at": self.last_rotated_at,
        }

    def __repr__(self) -> str:
        return (
            "SecretRef(secret_id=%r, provider_id=%r)"
            % (self.secret_id, self.provider_id)
        )


def make_secret_ref(data: Mapping[str, Any]) -> SecretRef:
    unknown = [k for k in data if k not in SECRET_REF_FIELDS]
    if unknown:
        raise ValueError("unknown SecretRef field(s): %s" % sorted(unknown))
    raw = [k for k in data if k in RAW_INLINE_FIELD_NAMES]
    if raw:
        raise ValueError("inline key material is not a ref: %s" % sorted(raw))
    for needed in ("secret_id", "provider_id"):
        if not data.get(needed):
            raise ValueError("SecretRef needs %r" % needed)
    return SecretRef(
        secret_id=str(data["secret_id"]),
        provider_id=str(data["provider_id"]),
        type=str(data.get("type", "api_key")),
        scope=str(data.get("scope", "")),
        source=str(data.get("source", "")),
        created_at=str(data.get("created_at", "")),
        last_rotated_at=str(data.get("last_rotated_at", "")),
    )


def coerce_secret_ref(value: Any) -> SecretRef:
    if isinstance(value, SecretRef):
        return value
    if isinstance(value, Mapping):
        return make_secret_ref(value)
    raise ValueError("credential_ref must be a SecretRef or a field mapping")


def reject_inline_key_material(config: Mapping[str, Any]) -> None:
    found = [k for k in config if k in RAW_INLINE_FIELD_NAMES]
    nested = config.get("credential_ref")
    if isinstance(nested, Mapping):
        found += [k for k in nested if k in RAW_INLINE_FIELD_NAMES]
    if found:
        raise ValueError("inline key material rejected: %s" % sorted(set(found)))


@dataclass
class TransportDescriptor:
    transport: str = TRANSPORT_OPENAI_COMPATIBLE
    base_url: str = ""
    limits: dict = field(default_factory=dict)
    route_params: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.transport not in TRANSPORT_TYPES:
            raise ValueError("unknown transport: %r" % (self.transport,))
        if not self.base_url:
            raise ValueError("base_url is required")
        self.limits = dict(self.limits)
        self.route_params = dict(self.route_params)

    def record_probe(
        self,
        limits: Mapping[str, Any] | None = None,
        route_params: Mapping[str, Any] | None = None,
    ) -> "TransportDescriptor":
        if limits:
            self.limits.update(dict(limits))
        if route_params:
            self.route_params.update(dict(route_params))
        return self


@dataclass
class ProviderContract:
    provider_id: str
    provider_type: str
    instance_id: str
    endpoint: str
    credential_ref: SecretRef
    transport: TransportDescriptor
    models: tuple = ()
    supports_streaming: bool = False
    supports_tools: bool = False
    supports_json_schema: bool = False
    supports_vision: bool = False
    supports_embeddings: bool = False
    supports_reasoning: bool = False
    supports_usage_reporting: bool = False
    supports_cancellation: bool = False
    max_context: int | None = None
    rate_limits: dict = field(default_factory=dict)
    auth_mode: str = "secret_ref"
    usage_reporting_state: str = "UNKNOWN"
    policy_refs: dict = field(default_factory=dict)
    catalogue: tuple = ()
    mock: bool = False
    adapter: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.credential_ref, SecretRef):
            raise ValueError("credential_ref must be a SecretRef")
        if not isinstance(self.transport, TransportDescriptor):
            raise ValueError("transport must be a TransportDescriptor")
        self.models = tuple(self.models)
        self.catalogue = tuple(self.catalogue)
        self.rate_limits = dict(self.rate_limits)
        for key, value in dict(self.policy_refs).items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise ValueError("policy_refs holds strings only")
        self.policy_refs = dict(self.policy_refs)

    def safe_summary(self) -> dict:
        return {
            "provider_id": self.provider_id,
            "provider_type": self.provider_type,
            "instance_id": self.instance_id,
            "endpoint": self.endpoint,
            "credential_ref": self.credential_ref.describe(),
            "transport": self.transport.transport,
            "base_url": self.transport.base_url,
            "models": list(self.models),
            "catalogue": list(self.catalogue),
            "flags": {
                "supports_streaming": self.supports_streaming,
                "supports_tools": self.supports_tools,
                "supports_json_schema": self.supports_json_schema,
                "supports_vision": self.supports_vision,
                "supports_embeddings": self.supports_embeddings,
                "supports_reasoning": self.supports_reasoning,
                "supports_usage_reporting": self.supports_usage_reporting,
                "supports_cancellation": self.supports_cancellation,
            },
            "max_context": self.max_context,
            "rate_limits": dict(self.rate_limits),
            "auth_mode": self.auth_mode,
            "usage_reporting_state": self.usage_reporting_state,
            "policy_refs": dict(self.policy_refs),
            "mock": self.mock,
            "adapter": self.adapter,
        }

    def __repr__(self) -> str:
        return (
            "ProviderContract(provider_id=%r, instance_id=%r, type=%r, "
            "transport=%r, models=%d, mock=%r)"
            % (
                self.provider_id,
                self.instance_id,
                self.provider_type,
                self.transport.transport,
                len(self.models),
                self.mock,
            )
        )
