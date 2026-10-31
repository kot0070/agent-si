"""K04E served proofs A: LiteLLM-backed adapter seam (rows 39/40/41).

Served = each proof boots the served app (create_app + TestClient, memory
secret store) and reads the provider matrix route, then drives the owned
adapter surface with test-injected fake transports only. Fakes live in
tests (K06 rule); product carries no fakes. No network, no keys.

Row -> route -> test:
- B0B-UNCOVERED_UI_DELTA-39 -> GET /api/v1/providers ->
  test_k04a_ui_delta_39_litellm_backed_adapter_served
- B0B-UNCOVERED_UI_DELTA-40 -> GET /api/v1/providers ->
  test_k04a_ui_delta_40_litellm_registry_entry_served
- B0B-UNCOVERED_UI_DELTA-41 -> GET /api/v1/providers ->
  test_k04a_ui_delta_41_probe_noncompat_routes_served
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.providers.adapters.base import AdapterConfig, make_secret_ref
from agent_si.providers.adapters.legs import build_leg
from agent_si.providers.adapters.litellm_backed import LiteLLMBackedAdapter
from agent_si.providers.adapters import usage_probe as probe_mod


def _secret(provider_id):
    return make_secret_ref(
        secret_id="k04a-secret",
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


_ROUTE_PARAMS = {"request_path": "/v1/messages",
                 "auth_scheme": "secret_ref"}
_PROBED_LIMITS = {"max_context": 128000, "supports_streaming": True}
_FULL_USAGE = {"input_tokens": 10, "output_tokens": 5,
               "cached_tokens": 2, "reasoning_tokens": 0}


def _litellm_adapter(provider_id="claude", model="Claude-K04A-1"):
    return LiteLLMBackedAdapter(
        AdapterConfig(
            provider_id=provider_id,
            instance_id="k04a",
            model=model,
            secret_ref=_secret(provider_id),
            base_url="https://k04a.example/v1",
        ),
        _FakeTransport(_stop_response),
        route_params=dict(_ROUTE_PARAMS),
        probed_limits=dict(_PROBED_LIMITS),
    )


# [UI_DELTA-39]-part: LiteLLM-backed adapter for non-OpenAI-compatible
# routes, with recorded probed limits.
def test_k04a_ui_delta_39_litellm_backed_adapter_served(tmp_path):
    client = _served_client(tmp_path)
    _served_baseline(client)
    adapter = _litellm_adapter()
    assert adapter.adapter_kind == "litellm_backed"
    assert adapter.openai_compat is False
    response = adapter.invoke([{"role": "user", "content": "hi"}])
    assert response.model == "Claude-K04A-1"
    assert response.mock is False
    assert adapter.route_params == _ROUTE_PARAMS
    assert adapter.probed_limits == _PROBED_LIMITS


# [UI_DELTA-40]-part: litellm-backed entry in the adapter registry for
# routes without an OpenAI-compatible API.
def test_k04a_ui_delta_40_litellm_registry_entry_served(tmp_path):
    client = _served_client(tmp_path)
    _served_baseline(client)
    entry = _litellm_adapter().registry_entry()
    assert entry["adapter_kind"] == "litellm_backed"
    assert entry["openai_compat"] is False
    assert entry["provider_id"] == "claude"
    assert entry["route_params"] == _ROUTE_PARAMS
    assert entry["probed_limits"] == _PROBED_LIMITS
    assert entry["endpoint"] == "https://k04a.example/v1"


# [UI_DELTA-41]-part: each non-OpenAI-compatible route is probed; its
# limits and route parameters are recorded.
def test_k04a_ui_delta_41_probe_noncompat_routes_served(tmp_path):
    client = _served_client(tmp_path)
    _served_baseline(client)
    for provider_id in ("anthropic", "claude", "gemini"):
        adapter = build_leg(
            provider_id,
            model="K04A-%s" % provider_id,
            secret_ref=_secret(provider_id),
            base_url="https://k04a.example/v1",
            litellm_call=_FakeTransport(_stop_response),
            route_params=dict(_ROUTE_PARAMS),
            probed_limits=dict(_PROBED_LIMITS),
        )
        assert isinstance(adapter, LiteLLMBackedAdapter)
        assert adapter.route_params == _ROUTE_PARAMS
        assert adapter.probed_limits == _PROBED_LIMITS
        probed = probe_mod.probe_usage(
            provider_id, "k04a", _usage_transport(_FULL_USAGE))
        assert probed["state"] == "VERIFIED"
        assert probed["input_tokens"] == 10
