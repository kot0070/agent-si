"""K04E served proofs B: LiteLLM limits/params/probes + mock seam (BP05-81, BP06-72).

Served = each proof boots the served app (create_app + TestClient, memory
secret store) and reads the provider matrix route, then drives the owned
adapter surface with test-injected fake transports only. Fakes live in
tests (K06 rule); product carries no fakes. No network, no keys.

Row -> route -> test:
- B0B-UNCOVERED_BP05-81 -> GET /api/v1/providers ->
  test_k04b_bp05_81_litellm_limits_params_usage_probes_served
- B0B-UNCOVERED_BP06-72 -> GET /api/v1/providers ->
  test_k04b_bp06_72_mock_until_key_served
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.providers.adapters.base import (
    UNAVAILABLE,
    AdapterConfig,
    make_secret_ref,
)
from agent_si.providers.adapters.legs import build_leg
from agent_si.providers.adapters.litellm_backed import LiteLLMBackedAdapter
from agent_si.providers.adapters.mock_provider import MockProviderAdapter
from agent_si.providers.adapters import usage_probe as probe_mod


def _secret(provider_id):
    return make_secret_ref(
        secret_id="k04b-secret",
        provider_id=provider_id,
        type="api_key",
        scope="provider",
        source="secret_store",
    )


class _FakeTransport:
    # FAKE-OF: agent_si.providers.adapters.base (transport port)
    """Injected fake transport: records requests, plays back replies."""

    def __init__(self, respond):
        self.respond = respond
        self.requests = []

    def __call__(self, request):
        self.requests.append(dict(request))
        return self.respond(request)


def _stop_response(request, usage=None):
    # FAKE-OF: agent_si.providers.adapters.litellm_backed (canned reply)
    return {
        "output_text": "canned final",
        "finish": "stop",
        "usage": dict(usage) if usage is not None else {
            "input_tokens": 10,
            "output_tokens": 5,
        },
    }


def _usage_transport(usage):
    # FAKE-OF: agent_si.providers.adapters.usage_probe (usage port)
    def respond(request):
        return {"usage": dict(usage), "raw": dict(usage),
                "raw_safe": True}

    return _FakeTransport(respond)


def _served_client(tmp_path):
    """Boot the served app for a K04E adapter proof (served leg)."""
    os.environ["AGENT_SI_SECRET_STORE"] = "memory"
    from agent_si.backend.app import create_app
    import fastapi.testclient as _ftc

    app = create_app({"store_dir": str(tmp_path),
                      "secret_store": "memory"},
                     auth_hook=None, rate_hook=None, model_factory=None)
    return _ftc.TestClient(app)


def _served_baseline(client):
    """The served app answers its provider matrix read (served proof leg)."""
    resp = client.get("/api/v1/providers")
    assert resp.status_code == 200, resp.text
    return resp


# [BP05-81]-part: a LiteLLM-backed adapter with recorded limits, route
# params and usage probes.
def test_k04b_bp05_81_litellm_limits_params_usage_probes_served(tmp_path):
    client = _served_client(tmp_path)
    _served_baseline(client)
    route_params = {"request_path": "/v1beta/models",
                    "auth_scheme": "secret_ref"}
    probed_limits = {"max_context": 32000, "supports_streaming": False}
    adapter = build_leg(
        "gemini",
        model="Gemini-K04B-1",
        secret_ref=_secret("gemini"),
        base_url="https://k04b.example/v1",
        litellm_call=_FakeTransport(_stop_response),
        route_params=dict(route_params),
        probed_limits=dict(probed_limits),
    )
    assert isinstance(adapter, LiteLLMBackedAdapter)
    assert adapter.openai_compat is False
    response = adapter.invoke([{"role": "user", "content": "hi"}])
    assert response.model == "Gemini-K04B-1"
    entry = adapter.registry_entry()
    assert entry["route_params"] == route_params
    assert entry["probed_limits"] == probed_limits
    full = {"input_tokens": 10, "output_tokens": 5,
            "cached_tokens": 2, "reasoning_tokens": 0}
    probed = probe_mod.probe_usage("gemini", "k04b",
                                   _usage_transport(full))
    assert probed["state"] == "VERIFIED"
    assert probed["cached_tokens"] == 2
    stream = probe_mod.probe_stream_usage("gemini", "k04b",
                                          _usage_transport(full))
    assert stream["stream_state"] == "VERIFIED"
    assert stream["stream_usage"]["output_tokens"] == 5


# [BP06-72]-part: mock provider routes served until the user supplies a
# key; mocked traffic is marked mock.
def test_k04b_bp06_72_mock_until_key_served(tmp_path):
    client = _served_client(tmp_path)
    _served_baseline(client)
    adapter = MockProviderAdapter(
        AdapterConfig(
            provider_id="mock",
            instance_id="k04b",
            model="Mock-K04B-1",
            secret_ref=_secret("mock"),
        )
    )
    assert adapter.serves(key_supplied=False) is True
    assert adapter.serves(key_supplied=True) is False
    first = adapter.invoke([{"role": "user", "content": "hi"}])
    assert first.mock is True
    assert first.to_record()["mock"] is True
    assert first.output_text
    probed = probe_mod.probe_usage(
        "mock", "k04b", adapter.fake_usage_transport())
    assert probed["state"] == "VERIFIED"
    assert probed["input_tokens"] == 0
    assert probed["stream_usage"] == UNAVAILABLE
