"""LiteLLM-backed adapter path for routes without an OpenAI-compatible API.

The litellm SDK is never imported (stdlib only at import time): the caller
injects a litellm_call callable. The adapter records probed limits and
route params in its registry entry and never claims OpenAI-compat.
Usage probes are recorded via usage_probe over injected fake transports.
"""
from .base import UNAVAILABLE, AdapterConfigError, ProviderAdapter


class LiteLLMBackedAdapter(ProviderAdapter):
    """Adapter for non-OpenAI-compatible routes via an injected call."""

    adapter_kind = "litellm_backed"
    openai_compat = False

    def __init__(self, config, litellm_call, route_params=None,
                 probed_limits=None):
        super().__init__(config, litellm_call)
        if litellm_call is None:
            raise AdapterConfigError(
                "litellm_backed adapter needs an injected litellm_call",
                config.ref_base() + ":config")
        self.litellm_call = litellm_call
        self.route_params = dict(route_params) if route_params else {}
        self.probed_limits = dict(probed_limits) if probed_limits else {}

    def invoke(self, messages, params=None, max_turns=8):
        """Run one LiteLLM-route invocation with per-run overrides."""
        self._check_messages(messages)
        request = self._resolve_request(messages, params)
        self._require_endpoint(request)
        request["route_params"] = dict(self.route_params)
        saved_transport = self.transport
        self.transport = self.litellm_call
        try:
            return self._run_turns(request, max_turns)
        finally:
            self.transport = saved_transport

    def registry_entry(self):
        """Adapter registry entry: probed limits + route params (SPEC 34)."""
        return {
            "provider_id": self.config.provider_id,
            "instance_id": self.config.instance_id,
            "adapter_kind": self.adapter_kind,
            "openai_compat": False,
            "endpoint": self.config.base_url or UNAVAILABLE,
            "model": self.config.model,
            "route_params": dict(self.route_params),
            "probed_limits": dict(self.probed_limits),
        }
