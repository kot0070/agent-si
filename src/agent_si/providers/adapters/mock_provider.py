"""Mock provider: canned routes served until the user supplies a key.

Mock traffic is always tagged mock=true on every record and response, so
telemetry can never mistake it for billed provider traffic. The mock
serves only while no user key is present; once a key is supplied the
mock route retires. Standard library only at import time.
"""
from .base import AdapterResponse, ProviderAdapter

MOCK_CANNED = (
    "Mock reply: canned output served until a user key is supplied.",
    "Mock reply: second canned turn; still mock traffic.",
)

MOCK_USAGE = {
    "input_tokens": 0,
    "output_tokens": 0,
    "cached_tokens": 0,
    "reasoning_tokens": 0,
}


class MockProviderAdapter(ProviderAdapter):
    """Canned-response adapter; every record carries mock=true."""

    adapter_kind = "mock"
    openai_compat = True

    def __init__(self, config, transport=None, canned=None):
        super().__init__(config, transport)
        self.canned = tuple(canned) if canned else MOCK_CANNED
        self.turns_served = 0

    def serves(self, key_supplied):
        """True while no user key is present; retires once one is."""
        return not bool(key_supplied)

    def invoke(self, messages, params=None, max_turns=8):
        """Serve the next canned response, tagged mock=true."""
        self._check_messages(messages)
        request = self._resolve_request(messages, params)
        text = self.canned[self.turns_served % len(self.canned)]
        self.turns_served += 1
        return AdapterResponse(
            provider_id=self.config.provider_id,
            instance_id=self.config.instance_id,
            model=request["model"],
            output_text=text,
            finish_reason="stop",
            usage=dict(MOCK_USAGE),
            mock=True,
            error_ref=None,
        )

    def fake_usage_transport(self):
        """Injected fake usage transport for probe tests (fakes only)."""

        def respond(request):
            return {
                "usage": dict(MOCK_USAGE),
                "raw": dict(MOCK_USAGE),
                "raw_safe": True,
            }

        return respond
