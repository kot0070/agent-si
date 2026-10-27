"""Generic OpenAI-compatible Chat Completions adapter.

Configured per provider instance by base_url + model + SecretRef (SPEC 43).
Only the Chat Completions path is used; the Responses API is never assumed.
Client retries stay at max_retries=0: one invocation is one authoritative
attempt, runner retries come from RoutingDecision-bound RunConfig.
Standard library only at import time; the transport is injected.
"""
from .base import AdapterConfigError, ProviderAdapter

CHAT_COMPLETIONS_PATH = "/chat/completions"


class OpenAICompatAdapter(ProviderAdapter):
    """Generic adapter over an injected Chat Completions transport."""

    adapter_kind = "openai_compat"
    openai_compat = True

    def __init__(self, config, transport,
                 chat_path=CHAT_COMPLETIONS_PATH):
        super().__init__(config, transport)
        if transport is None:
            raise AdapterConfigError(
                "openai_compat adapter needs an injected transport callable",
                config.ref_base() + ":config")
        self.chat_path = chat_path

    def invoke(self, messages, params=None, max_turns=8):
        """Run one Chat Completions invocation with per-run overrides."""
        self._check_messages(messages)
        request = self._resolve_request(messages, params)
        self._require_endpoint(request)
        request["chat_path"] = self.chat_path
        return self._run_turns(request, max_turns)
