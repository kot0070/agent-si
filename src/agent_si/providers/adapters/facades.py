"""Frozen K04 section 3.3 adapter facades: probing plus model resolution.

Two module-level functions carry the EXACT frozen names, parameter
lists and order from ``src/agent_si/routing/interface.py`` with no
extra parameters and no defaults:

- ``probe_usage(adapter_id, provider_id, streaming)`` resolves the
  adapter id to injected transports and genuinely probes usage through
  :mod:`agent_si.providers.adapters.usage_probe` (non-streaming always;
  streaming additionally when ``streaming`` is true).
- ``resolve_model(provider_id, model)`` validates the provider through
  :mod:`agent_si.providers.adapters.legs` and returns the ``{provider_id,
  model_id, fields}`` row from the stored server-side binding plus the
  leg mapping.

Both bindings are server-side: transports and secrets are registered
here by the host process, never by the caller, and tests inject fakes
only (no network). Unknown ids and missing stream transports fail
closed with ValueError, never silent placeholder data. Standard library plus
``agent_si`` only.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from . import legs as _legs
from . import usage_probe as _usage_probe
from .base import AdapterConfigError

if TYPE_CHECKING:
    from agent_si.routing.interface import (ModelContracts,
                                            UsageReportingCapabilities)

#: adapter_id -> (usage_transport, stream_transport or None).
_TRANSPORTS: dict = {}

#: (provider_id, instance_id) -> binding record.
_BINDINGS: dict = {}

#: Probe-port keys installed automatically by bind_provider (defaults only;
#: manual register_adapter_transports entries are never tracked here).
_DEFAULT_PROBE_PORT_KEYS: set = set()


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def register_adapter_transports(adapter_id, usage_transport,
                                stream_transport=None) -> None:
    """Bind injected transports to an adapter id (server-side, no network).

    The ``adapter_id`` names the bound entry; an ``"adapter/instance"``
    id probes that instance, a bare id probes ``"default"``. Both
    transports must be callables (the stream one may be omitted, which
    forbids later ``streaming=True`` probes for that id).
    """
    if not isinstance(adapter_id, str) or not adapter_id:
        raise ValueError("adapter_id must be a non-empty string")
    if not callable(usage_transport):
        raise ValueError("usage_transport must be a callable")
    if stream_transport is not None and not callable(stream_transport):
        raise ValueError("stream_transport must be a callable or None")
    _TRANSPORTS[adapter_id] = (usage_transport, stream_transport)


def clear_adapter_transports() -> None:
    """Forget every bound adapter transport (tests and teardown).

    Tracked default probe-port keys go too: the installed ports are
    gone, so a later rebind must not mistake a manual registration
    under one of those keys for a stale default.
    """
    _TRANSPORTS.clear()
    _DEFAULT_PROBE_PORT_KEYS.clear()


def _default_probe_transport(provider_id, instance_id, chat_transport,
                             secret_id, base_url):
    """Wrap the bound chat transport as a usage-probe port default.

    Translates the ``{"probe": "usage"}`` request into a chat-shaped
    request over the bound chat transport and reshapes its real reply
    into the probe reply shape (usage plus the safe raw reference).
    Secret identity travels id-only; transport failures propagate so the
    probe maps them to UNSUPPORTED/UNKNOWN (fail closed, never fabricated data,
    never network).
    """
    def probe_transport(request):
        probe_request = request if isinstance(request, dict) else {}
        chat_request = {
            "probe": "usage",
            "provider_id": provider_id,
            "instance_id": instance_id,
            "model": probe_request.get("model", ""),
            "messages": [{"role": "user", "content": ""}],
            "params": {},
            "secret_ref": {"secret_id": secret_id,
                           "provider_id": provider_id},
            "stream": bool(probe_request.get("stream", False)),
            "base_url": base_url,
        }
        reply = chat_transport(chat_request)
        if not isinstance(reply, dict):
            return {}
        shaped = {}
        usage = reply.get("usage")
        shaped["usage"] = dict(usage) if isinstance(usage, dict) else {}
        for key in ("raw", "raw_safe", "cost_fields",
                    "request_level_usage"):
            if key in reply:
                shaped[key] = reply[key]
        return shaped

    return probe_transport


def _configure_default_probe_port(provider_id, instance_id, transport,
                                  record) -> None:
    """Install (or drop) the default probe-port entries for a binding.

    OpenAI-compatible legs bound with a callable chat transport get
    default probe entries for ``"provider/instance"`` (plus the bare
    provider id for the default instance) flowing through the bound
    transport. Non-compat legs and bindings without a transport get no
    defaults, so probes fail closed; re-binding drops stale defaults this
    module installed, never manual registrations.
    """
    adapter_key = "%s/%s" % (provider_id, instance_id)
    keys = [adapter_key]
    if instance_id == "default":
        keys.append(provider_id)
    compat = _legs.leg_descriptor(provider_id)["openai_compat"]
    if compat and callable(transport):
        probe_transport = _default_probe_transport(
            provider_id, instance_id, transport, record["secret_id"],
            record["base_url"])
        for key in keys:
            _TRANSPORTS[key] = (probe_transport, probe_transport)
            _DEFAULT_PROBE_PORT_KEYS.add(key)
    else:
        for key in keys:
            if key in _DEFAULT_PROBE_PORT_KEYS:
                _TRANSPORTS.pop(key, None)
                _DEFAULT_PROBE_PORT_KEYS.discard(key)


def probe_usage(adapter_id: str, provider_id: str,
                streaming: bool) -> UsageReportingCapabilities:
    """Probe usage reporting; streaming is verified separately when asked.

    Non-streaming usage is always probed; ``streaming=True`` additionally
    probes the stream channel through the bound stream transport. Unknown
    adapter ids, ``streaming=True`` without a bound stream transport, or a
    provider label that does not match the adapter id raise ValueError
    (fail closed: probe labels stay exact, never borrowed).
    """
    if not isinstance(adapter_id, str) or not adapter_id:
        raise ValueError("adapter_id must be a non-empty string")
    if not isinstance(provider_id, str) or not provider_id:
        raise ValueError("provider_id must be a non-empty string")
    entry = _TRANSPORTS.get(adapter_id)
    if entry is None:
        raise ValueError("unknown adapter_id: %r" % (adapter_id,))
    usage_transport, stream_transport = entry
    if streaming and stream_transport is None:
        raise ValueError(
            "streaming probe needs a stream transport for %r" % (adapter_id,)
        )
    if "/" in adapter_id:
        bound_provider = adapter_id.split("/", 1)[0]
        instance_id = adapter_id.rsplit("/", 1)[-1] or "default"
    else:
        bound_provider = adapter_id
        instance_id = "default"
    if bound_provider != provider_id:
        raise ValueError(
            "adapter %r is not bound to provider %r "
            "(probe labels stay exact; bind it server-side first)"
            % (adapter_id, provider_id))
    return _usage_probe.probe_adapter(
        provider_id,
        instance_id,
        usage_transport,
        stream_transport=stream_transport if streaming else None,
    )


def bind_provider(provider_id, secret_ref, transport, base_url,
                  instance_id="default") -> dict:
    """Store a server-side provider binding (secret and transport by host).

    The provider id is validated verbatim through
    :func:`legs.leg_descriptor` (unknown or re-cased ids raise); the
    secret ref must be an id-only mapping (raw key material refused);
    ``base_url`` is required explicitly. Returns the stored binding view
    carrying secret ids only.
    """
    try:
        _legs.leg_descriptor(provider_id)
    except AdapterConfigError as exc:
        raise ValueError(str(exc)) from None
    if not isinstance(secret_ref, dict):
        raise ValueError("secret_ref must be an id-only mapping")
    for needed in ("secret_id", "provider_id"):
        if not secret_ref.get(needed):
            raise ValueError("secret_ref needs %r" % (needed,))
    if "value" in secret_ref:
        raise ValueError("secret_ref must not carry raw key material")
    if transport is not None and not callable(transport):
        raise ValueError("transport must be a callable or None")
    if not isinstance(base_url, str) or not base_url:
        raise ValueError("base_url is required")
    if not isinstance(instance_id, str) or not instance_id:
        raise ValueError("instance_id must be a non-empty string")
    record = {
        "provider_id": provider_id,
        "instance_id": instance_id,
        "secret_id": str(secret_ref["secret_id"]),
        "transport": transport,
        "base_url": base_url,
        "evidence_ref": "binding:%s/%s" % (provider_id, instance_id),
        "bound_at": _utcnow_iso(),
    }
    _BINDINGS[(provider_id, instance_id)] = record
    _configure_default_probe_port(provider_id, instance_id, transport,
                                  record)
    return {
        "provider_id": record["provider_id"],
        "instance_id": record["instance_id"],
        "secret_id": record["secret_id"],
        "base_url": record["base_url"],
        "evidence_ref": record["evidence_ref"],
        "bound_at": record["bound_at"],
    }


def clear_provider_bindings() -> None:
    """Forget every stored provider binding (tests and teardown).

    Installed default probe ports go too: the provider is unbound,
    so later probes fail closed instead of answering from a stale
    transport.
    """
    _BINDINGS.clear()
    for _key in list(_DEFAULT_PROBE_PORT_KEYS):
        _TRANSPORTS.pop(_key, None)
    _DEFAULT_PROBE_PORT_KEYS.clear()


def _bound_view(provider_id: str) -> dict:
    candidates = [key for key in _BINDINGS if key[0] == provider_id]
    if not candidates:
        raise ValueError(
            "unbound provider: %r (bind it server-side first)" % (provider_id,)
        )
    if ("default" in [instance for _, instance in candidates]):
        return _BINDINGS[(provider_id, "default")]
    return _BINDINGS[sorted(candidates)[0]]


def resolve_model(provider_id: str, model: str) -> ModelContracts:
    """Resolve an exact model id against the bound provider (verbatim).

    The provider id is validated through :func:`legs.leg_descriptor`
    (unknown or re-cased ids raise ValueError); the model id passes
    through untouched, never reworded or case-folded. Providers without
    a server-side binding raise ValueError. The ``fields`` carry the
    leg mapping (capabilities, chat path, route params, endpoint hint)
    plus the binding evidence (endpoint, secret id, evidence ref) plus
    source and retrieval date.
    """
    if not isinstance(model, str) or not model:
        raise ValueError("model must be a non-empty string")
    try:
        descriptor = _legs.leg_descriptor(provider_id)
    except AdapterConfigError as exc:
        raise ValueError(str(exc)) from None
    binding = _bound_view(provider_id)
    fields: dict[str, Any] = {
        "capabilities": dict(descriptor["capabilities"]),
        "chat_path": descriptor["chat_path"],
        "route_params": dict(descriptor["route_params"]),
        "openai_compat": descriptor["openai_compat"],
        "endpoint_hint": descriptor["endpoint_hint"],
        "endpoint": binding["base_url"],
        "secret_id": binding["secret_id"],
        "instance_id": binding["instance_id"],
        "evidence_ref": binding["evidence_ref"],
        "source": "server-binding:%s" % (provider_id,),
        "retrieved_at": _utcnow_iso(),
    }
    return {"provider_id": provider_id, "model_id": model, "fields": fields}


def check_provider_health(provider_id, model, streaming=False) -> dict:
    """User-path health check: resolve the model, then probe usage.

    Genuinely calls resolve_model(provider_id, model) against the
    server-side binding, then probe_usage through the configured probe
    port for that provider/instance (streaming additionally probed when
    requested). Returns the combined evidenced result with the resolved
    fields, the usage capability, and the check stamp. Raises ValueError
    when the provider is unbound or the leg carries no probe port (fail
    closed). This is the one concrete production caller of the probe
    port on the user path.
    """
    resolved = resolve_model(provider_id, model)
    instance_id = resolved["fields"]["instance_id"]
    adapter_id = "%s/%s" % (provider_id, instance_id)
    usage = probe_usage(adapter_id, provider_id, streaming)
    return {
        "provider_id": provider_id,
        "model_id": model,
        "fields": dict(resolved["fields"]),
        "usage": usage,
        "checked_at": _utcnow_iso(),
    }


__all__ = [
    "register_adapter_transports",
    "clear_adapter_transports",
    "probe_usage",
    "bind_provider",
    "clear_provider_bindings",
    "resolve_model",
    "check_provider_health",
]
