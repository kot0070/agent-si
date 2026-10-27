"""One provider-specific leg per provider over the generic path.

A leg is a small param/route mapping (SPEC K04 block): it declares the
provider id verbatim, the transport kind, the chat path, route params and
the capability surface, then builds the matching adapter. Cloud legs take
their endpoint from configuration (base_url); the Meta leg reaches the
Meta cloud endpoint through a SecretRef. Local loopback legs (ollama,
lm_studio) default to their conventional loopback base_url values; every
other leg requires base_url from configuration and fails explicitly
without it. Further providers are added by configuration, never by a
core rewrite. No routing or selection lives here: legs only map params.
"""
from .base import (
    CAPABILITY_KEYS,
    AdapterConfig,
    AdapterConfigError,
    ProviderAdapter,
)
from .litellm_backed import LiteLLMBackedAdapter
from .openai_compat import OpenAICompatAdapter

#: Provider leg ids, verbatim (task TPL1-NEW Lane A list).
LEG_IDS = (
    "meta",
    "openai",
    "anthropic",
    "openai_compatible",
    "ollama",
    "lm_studio",
    "claude",
    "gemini",
    "mistral",
    "groq",
    "openrouter",
    "deepseek",
    "xai",
)

_NON_COMPAT = ("anthropic", "claude", "gemini")


def _capabilities():
    """Pre-evidence capability surface: nothing evidenced yet (SPEC 34A)."""
    return {key: (None if key == "max_context" else False)
            for key in CAPABILITY_KEYS}


def _leg(openai_compat, chat_path, route_params, endpoint_hint=None):
    return {
        "openai_compat": bool(openai_compat),
        "chat_path": chat_path,
        "route_params": dict(route_params),
        "endpoint_hint": endpoint_hint,
        "capabilities": _capabilities(),
    }


#: Per-leg param/route mapping over the generic path.
LEG_DEFAULTS = {
    "meta": _leg(True, "/chat/completions",
                 {"api": "chat_completions", "auth_scheme": "secret_ref"}),
    "openai": _leg(True, "/chat/completions",
                   {"api": "chat_completions", "auth_scheme": "secret_ref"}),
    "anthropic": _leg(False, "/v1/messages",
                      {"api": "messages", "auth_scheme": "secret_ref"}),
    "openai_compatible": _leg(
        True, "/chat/completions",
        {"api": "chat_completions", "auth_scheme": "secret_ref"}),
    "ollama": _leg(True, "/api/chat",
                   {"api": "chat", "auth_scheme": "secret_ref"},
                   endpoint_hint="http://localhost:11434/v1"),
    "lm_studio": _leg(True, "/v1/chat/completions",
                      {"api": "chat_completions", "auth_scheme": "secret_ref"},
                      endpoint_hint="http://localhost:1234/v1"),
    "claude": _leg(False, "/v1/messages",
                   {"api": "messages", "auth_scheme": "secret_ref"}),
    "gemini": _leg(False, "/v1beta/models",
                   {"api": "generate_content", "auth_scheme": "secret_ref"}),
    "mistral": _leg(True, "/v1/chat/completions",
                    {"api": "chat_completions", "auth_scheme": "secret_ref"}),
    "groq": _leg(True, "/openai/v1/chat/completions",
                 {"api": "chat_completions", "auth_scheme": "secret_ref"}),
    "openrouter": _leg(True, "/api/v1/chat/completions",
                       {"api": "chat_completions", "auth_scheme": "secret_ref"}),
    "deepseek": _leg(True, "/v1/chat/completions",
                     {"api": "chat_completions", "auth_scheme": "secret_ref"}),
    "xai": _leg(True, "/v1/chat/completions",
                {"api": "chat_completions", "auth_scheme": "secret_ref"}),
}


def leg_descriptor(provider_id):
    """Return a copy of the leg's transport mapping (data only)."""
    if provider_id not in LEG_DEFAULTS:
        raise AdapterConfigError(
            "unknown provider_id '%s'; expected one of: %s" % (
                provider_id, ", ".join(LEG_IDS)),
            "config:provider-id")
    defaults = LEG_DEFAULTS[provider_id]
    return {
        "provider_id": provider_id,
        "openai_compat": defaults["openai_compat"],
        "chat_path": defaults["chat_path"],
        "route_params": dict(defaults["route_params"]),
        "endpoint_hint": defaults["endpoint_hint"],
        "capabilities": dict(defaults["capabilities"]),
    }


def build_leg(provider_id, model, secret_ref, transport=None, *,
              instance_id="default", base_url=None, litellm_call=None,
              route_params=None, probed_limits=None, max_retries=0):
    """Build the provider leg's adapter. Ids pass through verbatim.

    OpenAI-compatible legs build OpenAICompatAdapter over the injected
    transport; the remaining legs build LiteLLMBackedAdapter over the
    injected litellm_call. Unknown or re-cased ids raise instead of
    being folded.
    """
    if provider_id not in LEG_DEFAULTS:
        raise AdapterConfigError(
            "unknown provider_id '%s'; expected one of: %s" % (
                provider_id, ", ".join(LEG_IDS)),
            "config:provider-id")
    defaults = LEG_DEFAULTS[provider_id]
    resolved_base_url = base_url or defaults["endpoint_hint"]
    config = AdapterConfig(
        provider_id=provider_id,
        instance_id=instance_id,
        model=model,
        secret_ref=secret_ref,
        base_url=resolved_base_url,
        max_retries=max_retries,
    )
    if defaults["openai_compat"]:
        return OpenAICompatAdapter(config, transport,
                                   chat_path=defaults["chat_path"])
    return LiteLLMBackedAdapter(
        config,
        litellm_call,
        route_params=route_params if route_params is not None
        else dict(defaults["route_params"]),
        probed_limits=dict(probed_limits) if probed_limits else {},
    )


def leg_capabilities(provider_id):
    """Expose the leg's declared provider capability surface (SPEC 34A)."""
    return leg_descriptor(provider_id)["capabilities"]


def describe_transport(adapter):
    """Transport descriptor data for a built leg adapter (SPEC 44)."""
    if not isinstance(adapter, ProviderAdapter):
        raise AdapterConfigError(
            "describe_transport needs a ProviderAdapter",
            "config:adapter")
    return adapter.transport_descriptor()
