"""Provider adapter base: config, SecretRef, typed errors, transport port.

Frozen shapes referenced (read-only): PRODUCT_SPEC sections 20A (SecretRef
fields), 33A (usage states), 34 (provider contract fields), 43 (runner
retries only from RoutingDecision-bound RunConfig; client max_retries=0),
44 (registries own no execution/routing/secret values).

Adapters expose transport + probes only. They never route, never select
models, never hold secret values (SecretRef metadata only), and never
import the provider registry: callables are injected (ports).
Standard library only at import time.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

#: Sentinel for a metric the provider did not evidence (SPEC 33A).
UNAVAILABLE = "UNAVAILABLE"

#: Usage reporting states (SPEC 33A UsageReportingState).
USAGE_STATES = ("VERIFIED", "PARTIAL", "UNSUPPORTED", "UNKNOWN")

#: Adapter kinds surfaced in transport descriptors and registry entries.
ADAPTER_KINDS = ("openai_compat", "litellm_backed", "mock")

#: Exact SecretRef fields (SPEC 20A). No raw secret value field exists here.
SECRET_REF_FIELDS = (
    "secret_id",
    "provider_id",
    "type",
    "scope",
    "source",
    "created_at",
    "last_rotated_at",
)

REQUIRED_SECRET_REF_FIELDS = (
    "secret_id",
    "provider_id",
    "type",
    "scope",
    "source",
)

#: Identity fields of a SecretRef that must carry non-empty values: the
#: pointer itself. Metadata fields (scope, source) default to "" in the
#: served SecretRef shape, so an empty metadata value is a valid ref,
#: never a misconfiguration or raw key material.
NONEMPTY_SECRET_REF_FIELDS = (
    "secret_id",
    "provider_id",
    "type",
)

#: Provider capability surface an adapter exposes for the router (SPEC 34).
CAPABILITY_KEYS = (
    "supports_streaming",
    "supports_tools",
    "supports_json_schema",
    "supports_vision",
    "supports_embeddings",
    "supports_reasoning",
    "supports_usage_reporting",
    "supports_cancellation",
    "max_context",
)


def make_secret_ref(secret_id, provider_id, type="api_key",
                    scope="provider", source="secret_store",
                    created_at=None, last_rotated_at=None):
    """Build a SecretRef mapping with exactly the SPEC 20A fields."""
    return {
        "secret_id": secret_id,
        "provider_id": provider_id,
        "type": type,
        "scope": scope,
        "source": source,
        "created_at": created_at,
        "last_rotated_at": last_rotated_at,
    }


class AdapterError(Exception):
    """Base adapter failure. Always carries an error_ref, never silent."""

    def __init__(self, message, error_ref):
        super().__init__(message)
        self.error_ref = error_ref


class AdapterConfigError(AdapterError):
    """Adapter misconfiguration (missing endpoint, bad params, no callable)."""


class ProviderHttpError(AdapterError):
    """Provider answered with an HTTP error status (e.g. 5xx)."""

    def __init__(self, message, error_ref, status):
        super().__init__(message, error_ref)
        self.status = status


class ProviderTimeoutError(AdapterError):
    """Provider request timed out."""


class MaxTurnsTrippedError(AdapterError):
    """Max-turns budget exhausted without a final response."""

    def __init__(self, message, error_ref, reason):
        super().__init__(message, error_ref)
        self.reason = reason


class TransportHttpError(Exception):
    """Transport-level signal: provider answered with an HTTP status."""

    def __init__(self, status, message=""):
        super().__init__(message)
        self.status = status
        self.message = message


class TransportTimeoutError(Exception):
    """Transport-level signal: provider request timed out."""


class TransportUnsupportedError(Exception):
    """Transport-level signal: this capability is not supported."""


@dataclass(frozen=True)
class AdapterConfig:
    """Transport configuration: base_url + model + SecretRef.

    Model/provider/instance ids pass through verbatim (never reworded,
    shortened or case-folded). max_retries defaults to 0: every invocation
    is one authoritative attempt; retries live in the runner (SPEC 43).
    """

    provider_id: str
    instance_id: str = "default"
    model: str = ""
    secret_ref: Optional[Dict[str, Any]] = None
    base_url: Optional[str] = None
    max_retries: int = 0

    def __post_init__(self):
        if not isinstance(self.provider_id, str) or not self.provider_id:
            raise AdapterConfigError(
                "provider_id must be a non-empty string",
                "config:provider-id")
        if not isinstance(self.instance_id, str) or not self.instance_id:
            raise AdapterConfigError(
                "instance_id must be a non-empty string",
                "%s/config" % self.provider_id)
        if not isinstance(self.model, str) or not self.model:
            raise AdapterConfigError(
                "model must be a non-empty string",
                "%s/config" % self.provider_id)
        if not isinstance(self.secret_ref, dict):
            raise AdapterConfigError(
                "secret_ref must be a SecretRef mapping, not a raw secret",
                "%s/%s:config" % (self.provider_id, self.instance_id))
        missing = [key for key in REQUIRED_SECRET_REF_FIELDS
                   if key not in self.secret_ref]
        if missing:
            raise AdapterConfigError(
                "secret_ref is missing fields: %s" % ",".join(missing),
                "%s/%s:config" % (self.provider_id, self.instance_id))
        empty = [key for key in NONEMPTY_SECRET_REF_FIELDS
                 if not self.secret_ref.get(key)]
        if empty:
            raise AdapterConfigError(
                "secret_ref has empty values for fields: %s" % ",".join(
                    sorted(empty)),
                "%s/%s:config" % (self.provider_id, self.instance_id))
        if "value" in self.secret_ref:
            raise AdapterConfigError(
                "secret_ref must not carry raw secret material",
                "%s/%s:config" % (self.provider_id, self.instance_id))
        unknown = [key for key in self.secret_ref
                   if key not in SECRET_REF_FIELDS]
        if unknown:
            raise AdapterConfigError(
                "secret_ref carries unknown fields: %s" % ",".join(
                    sorted(unknown)),
                "%s/%s:config" % (self.provider_id, self.instance_id))
        if not isinstance(self.max_retries, int) or self.max_retries != 0:
            raise AdapterConfigError(
                "provider clients use max_retries 0: one invocation is one "
                "authoritative attempt; retries live in the runner; got %r"
                % (self.max_retries,),
                "%s/%s:config" % (self.provider_id, self.instance_id))

    def ref_base(self):
        """Stable error_ref stem: provider_id/instance_id, verbatim."""
        return "%s/%s" % (self.provider_id, self.instance_id)


@dataclass
class AdapterResponse:
    """One authoritative adapter invocation result."""

    provider_id: str
    instance_id: str
    model: str
    output_text: str
    finish_reason: str
    usage: Dict[str, Any] = field(default_factory=dict)
    mock: bool = False
    error_ref: Optional[str] = None

    def to_record(self):
        """Telemetry-ready record; always carries the mock flag."""
        return {
            "provider_id": self.provider_id,
            "instance_id": self.instance_id,
            "model": self.model,
            "output_text": self.output_text,
            "finish_reason": self.finish_reason,
            "usage": dict(self.usage),
            "error_ref": self.error_ref,
            "mock": bool(self.mock),
        }


class ProviderAdapter:
    """Transport port. Subclasses implement invoke over an injected callable."""

    adapter_kind = "base"
    openai_compat = False

    def __init__(self, config, transport):
        if not isinstance(config, AdapterConfig):
            raise AdapterConfigError(
                "config must be an AdapterConfig",
                "config:adapter-config")
        if transport is not None and not callable(transport):
            raise AdapterConfigError(
                "transport must be an injected callable",
                config.ref_base() + ":config")
        self.config = config
        self.transport = transport

    def capabilities(self):
        """Provider-level capability surface for the router (SPEC 34A)."""
        return {key: (None if key == "max_context" else False)
                for key in CAPABILITY_KEYS}

    def transport_descriptor(self):
        """Transport descriptor data (SPEC 44: registration views only)."""
        return {
            "provider_id": self.config.provider_id,
            "instance_id": self.config.instance_id,
            "adapter_kind": self.adapter_kind,
            "openai_compat": bool(self.openai_compat),
            "endpoint": self.config.base_url or UNAVAILABLE,
            "model": self.config.model,
        }

    def invoke(self, messages, params=None, max_turns=8):
        """Run one invocation. Subclasses implement the transport loop."""
        raise AdapterConfigError(
            "invoke is implemented by provider subclasses",
            "config:adapter")

    def _resolve_request(self, messages, params, stream=False):
        """Merge config with per-run param overrides (SPEC: override via
        routing params). Overrides never mutate the stored config."""
        overrides = dict(params) if params else {}
        request = {
            "provider_id": self.config.provider_id,
            "instance_id": self.config.instance_id,
            "model": overrides.pop("model", self.config.model),
            "base_url": overrides.pop("base_url", self.config.base_url),
            "provider_instance": overrides.pop(
                "provider_instance", self.config.instance_id),
            "messages": [dict(message) for message in messages],
            "params": overrides,
            "secret_ref": dict(self.config.secret_ref),
            "stream": bool(stream),
            "attempt": 1,
        }
        return request

    def _require_endpoint(self, request):
        if not request.get("base_url"):
            raise AdapterConfigError(
                "base_url is not configured for provider '%s' "
                "instance '%s'; set base_url in configuration" % (
                    self.config.provider_id, self.config.instance_id),
                self.config.ref_base() + ":config")

    def _call_once(self, request):
        """Single transport attempt. No hidden retries (max_retries=0)."""
        try:
            return self.transport(request)
        except TransportHttpError as exc:
            raise ProviderHttpError(
                "provider returned HTTP %s" % exc.status,
                "%s:http-%s" % (self.config.ref_base(), exc.status),
                exc.status)
        except TransportTimeoutError as exc:
            raise ProviderTimeoutError(
                "provider request timed out: %s" % exc,
                self.config.ref_base() + ":timeout")
        except OSError as exc:
            raise ProviderTimeoutError(
                "provider request timed out: %s" % exc,
                self.config.ref_base() + ":timeout")

    def _finalize(self, request, reply):
        return AdapterResponse(
            provider_id=self.config.provider_id,
            instance_id=self.config.instance_id,
            model=request["model"],
            output_text=reply.get("output_text", ""),
            finish_reason=reply.get("finish", "stop"),
            usage=dict(reply.get("usage") or {}),
            mock=False,
            error_ref=None,
        )

    def _run_turns(self, request, max_turns):
        """Drive continue/stop turns; a max-turns trip is an explicit error."""
        turns = 0
        current = request
        while True:
            turns += 1
            reply = self._call_once(current)
            finish = reply.get("finish", "stop")
            if finish != "continue":
                return self._finalize(current, reply)
            if turns >= max_turns:
                raise MaxTurnsTrippedError(
                    "max-turns budget of %d exhausted without a final "
                    "response" % max_turns,
                    "%s:max-turns-%d" % (self.config.ref_base(), max_turns),
                    "max-turns budget of %d exhausted without a final "
                    "response" % max_turns)
            continued = dict(current)
            continued["messages"] = list(current["messages"]) + [
                {"role": "assistant", "content": reply.get("output_text", "")}
            ]
            continued["attempt"] = turns + 1
            current = continued

    def _check_messages(self, messages):
        if not isinstance(messages, list) or not messages:
            raise AdapterConfigError(
                "messages must be a non-empty list",
                self.config.ref_base() + ":config")
