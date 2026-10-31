"""K04 Lane A adapter tests (CODER-A-ADP owned).

Covers: generic OpenAI-compatible adapter + one leg per provider
[M-P1-23]; LiteLLM path + probes [M-R-ANY-API]; litellm registry entry
with probed limits + route params [UI_DELTA-39/40/41][BP05-81];
mock-until-key [BP06-72]; usage probes incl. separate streaming probe and
partial-UNAVAILABLE [SPEC 33A]; no routing API on adapters [BP02-8/9];
max_retries=0 default [BP03-9/SDK-32/114/116/ARCH-753]; typed 5xx/timeout
and max-turns errors with error_ref [BP03-17/18]; verbatim ids [R-305].

Self-sufficient: bootstraps <workspace>/src on sys.path; stdlib + pytest
only; every transport is an injected fake (no network, K06 rule).
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import pytest

from agent_si.providers.adapters import base as base_mod
from agent_si.providers.adapters import legs as legs_mod
from agent_si.providers.adapters import litellm_backed as litellm_mod
from agent_si.providers.adapters import mock_provider as mock_mod
from agent_si.providers.adapters import openai_compat as compat_mod
from agent_si.providers.adapters import usage_probe as probe_mod
from agent_si.providers.adapters.base import (
    UNAVAILABLE,
    AdapterConfig,
    AdapterConfigError,
    AdapterResponse,
    MaxTurnsTrippedError,
    ProviderHttpError,
    ProviderTimeoutError,
    TransportHttpError,
    TransportTimeoutError,
    TransportUnsupportedError,
    make_secret_ref,
)
from agent_si.providers.adapters.legs import LEG_IDS, build_leg, leg_descriptor
from agent_si.providers.adapters.litellm_backed import LiteLLMBackedAdapter
from agent_si.providers.adapters.mock_provider import MockProviderAdapter
from agent_si.providers.adapters.openai_compat import OpenAICompatAdapter


def _secret(provider_id="openai"):
    return make_secret_ref(
        secret_id="test-secret-1",
        provider_id=provider_id,
        type="api_key",
        scope="provider",
        source="secret_store",
    )


def _config(provider_id="openai", model="Exact-Model_Id-7",
            base_url="https://config.example/v1"):
    return AdapterConfig(
        provider_id=provider_id,
        instance_id="test-instance",
        model=model,
        secret_ref=_secret(provider_id),
        base_url=base_url,
    )


# FAKE-OF: agent_si.providers.adapters.base (ProviderAdapter transport port)
class FakeTransport:
    """Injected fake transport: records requests, plays back canned replies."""

    def __init__(self, respond):
        self.respond = respond
        self.requests = []

    def __call__(self, request):
        self.requests.append(dict(request))
        return self.respond(request)


# FAKE-OF: agent_si.providers.adapters.openai_compat (canned transport reply)
def _stop_response(request, usage=None):
    return {
        "output_text": "canned final",
        "finish": "stop",
        "usage": dict(usage) if usage is not None else {
            "input_tokens": 10,
            "output_tokens": 5,
        },
        "raw": {"id": "fake-1"},
        "raw_safe": True,
    }


# [R-305]-part: SecretRef field shape; ids verbatim; no raw secret material.

def test_secret_ref_fields_exact():
    ref = _secret("openai")
    assert set(ref) == {
        "secret_id", "provider_id", "type", "scope", "source",
        "created_at", "last_rotated_at",
    }
    assert ref["provider_id"] == "openai"
    assert "value" not in ref


# [M-P1-23]-part: generic adapter success path, verbatim ids, no raw secret.

def test_generic_adapter_invoke_success_verbatim():
    transport = FakeTransport(_stop_response)
    adapter = OpenAICompatAdapter(_config(), transport)
    response = adapter.invoke([{"role": "user", "content": "hi"}])
    assert isinstance(response, AdapterResponse)
    assert response.model == "Exact-Model_Id-7"
    assert response.finish_reason == "stop"
    assert response.mock is False
    assert response.error_ref is None
    request = transport.requests[0]
    assert request["model"] == "Exact-Model_Id-7"
    assert request["secret_ref"]["secret_id"] == "test-secret-1"
    assert "value" not in request["secret_ref"]
    record = response.to_record()
    assert record["model"] == "Exact-Model_Id-7"
    assert record["mock"] is False


# [R-305]-part: mixed-case ids pass through verbatim, never case-folded.

def test_mixed_case_ids_verbatim_end_to_end():
    transport = FakeTransport(_stop_response)
    config = _config(model="MiXeD-CaSe_Model-9Z")
    adapter = OpenAICompatAdapter(config, transport)
    response = adapter.invoke([{"role": "user", "content": "hi"}])
    assert response.model == "MiXeD-CaSe_Model-9Z"
    assert transport.requests[0]["model"] == "MiXeD-CaSe_Model-9Z"
    assert response.to_record()["model"] == "MiXeD-CaSe_Model-9Z"


# Per-run provider override through passed-through params; config untouched.

def test_per_run_override_params_passthrough():
    transport = FakeTransport(_stop_response)
    adapter = OpenAICompatAdapter(_config(), transport)
    response = adapter.invoke(
        [{"role": "user", "content": "hi"}],
        params={"model": "Override-Model-2",
                "base_url": "https://override.example/v1"},
    )
    assert response.model == "Override-Model-2"
    assert transport.requests[0]["model"] == "Override-Model-2"
    assert transport.requests[0]["base_url"] == "https://override.example/v1"
    assert adapter.config.model == "Exact-Model_Id-7"
    assert adapter.config.base_url == "https://config.example/v1"


# [BP03-9/SDK-32/114/116/ARCH-753]-part: max_retries defaults to 0, no retry.

def test_max_retries_defaults_to_zero():
    assert AdapterConfig(
        provider_id="openai", model="m",
        secret_ref=_secret()).max_retries == 0


def test_no_hidden_retry_on_5xx():
    calls = []

    # FAKE-OF: agent_si.providers.adapters.base (TransportHttpError signal)
    def respond(request):
        calls.append(request)
        raise TransportHttpError(503, "service unavailable")

    adapter = OpenAICompatAdapter(_config(), FakeTransport(respond))
    assert adapter.config.max_retries == 0
    with pytest.raises(ProviderHttpError):
        adapter.invoke([{"role": "user", "content": "hi"}])
    assert len(calls) == 1


# [BP03-17/18]-part: typed 5xx/timeout/max-turns failures carry error_ref.

def test_5xx_typed_error_carries_error_ref():
    # FAKE-OF: agent_si.providers.adapters.base (TransportHttpError signal)
    def respond(request):
        raise TransportHttpError(503, "service unavailable")

    adapter = OpenAICompatAdapter(_config(), FakeTransport(respond))
    with pytest.raises(ProviderHttpError) as excinfo:
        adapter.invoke([{"role": "user", "content": "hi"}])
    assert excinfo.value.status == 503
    assert isinstance(excinfo.value.error_ref, str)
    assert "openai" in excinfo.value.error_ref
    assert excinfo.value.error_ref


def test_timeout_typed_error_carries_error_ref():
    # FAKE-OF: agent_si.providers.adapters.base (TransportTimeoutError signal)
    def respond(request):
        raise TransportTimeoutError("timed out")

    adapter = OpenAICompatAdapter(_config(), FakeTransport(respond))
    with pytest.raises(ProviderTimeoutError) as excinfo:
        adapter.invoke([{"role": "user", "content": "hi"}])
    assert isinstance(excinfo.value.error_ref, str)
    assert excinfo.value.error_ref


def test_max_turns_trip_explicit_reason_and_ref():
    # FAKE-OF: agent_si.providers.adapters.openai_compat (canned transport reply) (multi-turn)
    transport = FakeTransport(
        lambda request: {"output_text": "more", "finish": "continue",
                         "usage": {}, "raw": {}, "raw_safe": True})
    adapter = OpenAICompatAdapter(_config(), transport)
    with pytest.raises(MaxTurnsTrippedError) as excinfo:
        adapter.invoke([{"role": "user", "content": "hi"}], max_turns=2)
    assert "max-turns" in excinfo.value.reason
    assert isinstance(excinfo.value.error_ref, str)
    assert excinfo.value.error_ref
    assert len(transport.requests) == 2


def test_missing_base_url_is_config_error():
    adapter = OpenAICompatAdapter(_config(base_url=None),
                                  FakeTransport(_stop_response))
    with pytest.raises(AdapterConfigError):
        adapter.invoke([{"role": "user", "content": "hi"}])


# [M-P1-23]-part: one provider-specific leg per provider over the generic path.

EXPECTED_LEG_IDS = (
    "meta", "openai", "anthropic", "openai_compatible", "ollama",
    "lm_studio", "claude", "gemini", "mistral", "groq", "openrouter",
    "deepseek", "xai",
)


def test_leg_id_set_complete():
    assert tuple(LEG_IDS) == EXPECTED_LEG_IDS


# FAKE-OF: agent_si.providers.adapters.legs (litellm_call and transport ports)
def _leg_transport_kwargs(provider_id):
    if leg_descriptor(provider_id)["openai_compat"]:
        return {"transport": FakeTransport(_stop_response)}
    calls = []

    # FAKE-OF: agent_si.providers.adapters.legs (injected litellm_call port)
    def litellm_call(request):
        calls.append(dict(request))
        return _stop_response(request)

    return {"litellm_call": litellm_call}


@pytest.mark.parametrize("provider_id", EXPECTED_LEG_IDS)
def test_leg_per_provider_invoke_verbatim(provider_id):
    kwargs = _leg_transport_kwargs(provider_id)
    adapter = build_leg(
        provider_id,
        model="Leg-Model-A",
        secret_ref=_secret(provider_id),
        base_url="https://leg.example/v1",
        **kwargs)
    response = adapter.invoke([{"role": "user", "content": "hi"}])
    assert response.model == "Leg-Model-A"
    assert response.to_record()["model"] == "Leg-Model-A"
    descriptor = leg_descriptor(provider_id)
    assert descriptor["provider_id"] == provider_id
    assert adapter.transport_descriptor()["provider_id"] == provider_id
    assert adapter.transport_descriptor()["model"] == "Leg-Model-A"


def test_leg_ids_not_case_folded():
    with pytest.raises(AdapterConfigError):
        build_leg("OPENAI", model="m", secret_ref=_secret("openai"),
                  base_url="https://leg.example/v1",
                  transport=FakeTransport(_stop_response))


def test_meta_leg_reaches_cloud_through_secret_ref():
    descriptor = leg_descriptor("meta")
    assert descriptor["openai_compat"] is True
    adapter = build_leg(
        "meta", model="Meta-Model-1", secret_ref=_secret("meta"),
        base_url="https://meta-config.example/v1",
        transport=FakeTransport(_stop_response))
    response = adapter.invoke([{"role": "user", "content": "hi"}])
    assert response.model == "Meta-Model-1"


def test_meta_leg_without_base_url_is_config_error():
    adapter = build_leg(
        "meta", model="Meta-Model-1", secret_ref=_secret("meta"),
        transport=FakeTransport(_stop_response))
    with pytest.raises(AdapterConfigError) as excinfo:
        adapter.invoke([{"role": "user", "content": "hi"}])
    assert "base_url" in str(excinfo.value)


# [BP02-8/9]-part: adapters expose transport + probes, never a routing API.

ROUTING_NAMES = (
    "route", "select", "select_model", "pick", "pick_model", "choose",
    "decide", "effective", "effective_capability", "routing", "router",
    "intersect",
)


def _adapter_instances():
    instances = [OpenAICompatAdapter(_config(), FakeTransport(_stop_response))]
    for provider_id in EXPECTED_LEG_IDS:
        instances.append(build_leg(
            provider_id, model="m", secret_ref=_secret(provider_id),
            base_url="https://leg.example/v1",
            **_leg_transport_kwargs(provider_id)))
    instances.append(LiteLLMBackedAdapter(
        _config(), lambda request: _stop_response(request),
        route_params={}, probed_limits={}))
    instances.append(MockProviderAdapter(_config(provider_id="mock")))
    return instances


def test_adapters_expose_no_routing_api():
    for adapter in _adapter_instances():
        for name in ROUTING_NAMES:
            assert not hasattr(adapter, name), name


def test_adapter_modules_define_no_routing_functions():
    banned = ("rout", "select", "pick_", "choose", "decid", "effective",
              "intersect")
    for module in (base_mod, compat_mod, litellm_mod, legs_mod,
                   mock_mod, probe_mod):
        for name in vars(module):
            lowered = name.lower()
            for token in banned:
                assert token not in lowered, name


# Provider capability surface is exposed for the router; never intersected.

def test_capabilities_exposed_router_computes_effective():
    for adapter in _adapter_instances():
        capabilities = adapter.capabilities()
        assert isinstance(capabilities, dict)
        for key in ("supports_streaming", "supports_tools",
                    "supports_json_schema", "supports_vision",
                    "supports_embeddings", "supports_reasoning",
                    "supports_usage_reporting", "supports_cancellation",
                    "max_context"):
            assert key in capabilities, key


# [M-R-ANY-API]/[UI_DELTA-39/40/41]/[BP05-81]-part: LiteLLM-backed path.

def _litellm_adapter(**kwargs):
    params = {"route_params": {"request_path": "/v1/messages",
                               "auth_scheme": "secret_ref"},
              "probed_limits": {"max_context": 128000,
                                "supports_streaming": True}}
    params.update(kwargs)
    return LiteLLMBackedAdapter(
        _config(provider_id="claude", model="Claude-Model-3"),
        FakeTransport(_stop_response),
        **params)


def test_litellm_path_invoke_and_entry():
    seen = []

    # FAKE-OF: agent_si.providers.adapters.legs (injected litellm_call port)
    def litellm_call(request):
        seen.append(dict(request))
        return _stop_response(request)

    adapter = LiteLLMBackedAdapter(
        _config(provider_id="claude", model="Claude-Model-3"),
        litellm_call,
        route_params={"request_path": "/v1/messages",
                      "auth_scheme": "secret_ref"},
        probed_limits={"max_context": 128000,
                       "supports_streaming": True})
    response = adapter.invoke([{"role": "user", "content": "hi"}])
    assert response.model == "Claude-Model-3"
    assert seen[0]["route_params"]["request_path"] == "/v1/messages"
    entry = adapter.registry_entry()
    assert entry["adapter_kind"] == "litellm_backed"
    assert entry["openai_compat"] is False
    assert entry["provider_id"] == "claude"
    assert entry["route_params"] == {"request_path": "/v1/messages",
                                     "auth_scheme": "secret_ref"}
    assert entry["probed_limits"] == {"max_context": 128000,
                                      "supports_streaming": True}


def test_litellm_never_claims_openai_compat():
    adapter = _litellm_adapter()
    assert adapter.openai_compat is False
    assert adapter.adapter_kind == "litellm_backed"
    assert adapter.registry_entry()["openai_compat"] is False


def test_litellm_requires_injected_callable():
    with pytest.raises(AdapterConfigError):
        LiteLLMBackedAdapter(_config(provider_id="claude"), None)


def test_litellm_per_run_override_and_errors():
    adapter = _litellm_adapter()
    response = adapter.invoke([{"role": "user", "content": "hi"}],
                              params={"model": "Claude-Override-1"})
    assert response.model == "Claude-Override-1"

    # FAKE-OF: agent_si.providers.adapters.base (TransportTimeoutError signal)
    def failing(request):
        raise TransportTimeoutError("timed out")

    slow = LiteLLMBackedAdapter(_config(provider_id="claude"),
                                FakeTransport(failing))
    with pytest.raises(ProviderTimeoutError) as excinfo:
        slow.invoke([{"role": "user", "content": "hi"}])
    assert excinfo.value.error_ref


# [SPEC 33A]-part: usage probes; streaming separate; partial -> UNAVAILABLE.

# FAKE-OF: agent_si.providers.adapters.usage_probe (usage transport port)
def _usage_transport(usage, raw_safe=True, extra=None):
    def respond(request):
        reply = {"usage": dict(usage), "raw": dict(usage),
                 "raw_safe": raw_safe}
        if extra:
            reply.update(extra)
        return reply

    return FakeTransport(respond)


def test_usage_probe_verified_full():
    adapter_probe = probe_mod.probe_usage(
        "openai", "test-instance",
        _usage_transport({"input_tokens": 10, "output_tokens": 5,
                          "cached_tokens": 2, "reasoning_tokens": 0}),
        evidence_ref="ev-1")
    assert adapter_probe["state"] == "VERIFIED"
    assert adapter_probe["input_tokens"] == 10
    assert adapter_probe["output_tokens"] == 5
    assert adapter_probe["cached_tokens"] == 2
    assert adapter_probe["reasoning_tokens"] == 0
    assert adapter_probe["raw_usage"] == {"input_tokens": 10,
                                          "output_tokens": 5,
                                          "cached_tokens": 2,
                                          "reasoning_tokens": 0}
    assert adapter_probe["stream_usage"] == UNAVAILABLE
    assert adapter_probe["evidence_ref"] == "ev-1"
    assert adapter_probe["verified_at"]


def test_usage_probe_partial_missing_unavailable():
    adapter_probe = probe_mod.probe_usage(
        "openai", "test-instance",
        _usage_transport({"input_tokens": 12}))
    assert adapter_probe["state"] == "PARTIAL"
    assert adapter_probe["input_tokens"] == 12
    assert adapter_probe["output_tokens"] == UNAVAILABLE
    assert adapter_probe["cached_tokens"] == UNAVAILABLE
    assert adapter_probe["reasoning_tokens"] == UNAVAILABLE


def test_usage_probe_keeps_raw_only_where_safe():
    adapter_probe = probe_mod.probe_usage(
        "openai", "test-instance",
        _usage_transport({"input_tokens": 1, "output_tokens": 1},
                         raw_safe=False))
    assert adapter_probe["raw_usage"] == UNAVAILABLE


def test_usage_probe_unsupported_and_unknown():
    # FAKE-OF: agent_si.providers.adapters.usage_probe (unsupported-path transport signal)
    def unsupported(request):
        raise TransportUnsupportedError("no usage")

    adapter_probe = probe_mod.probe_usage("openai", "test-instance",
                                          FakeTransport(unsupported))
    assert adapter_probe["state"] == "UNSUPPORTED"
    assert adapter_probe["input_tokens"] == UNAVAILABLE

    # FAKE-OF: agent_si.providers.adapters.usage_probe (unknown-path transport signal)
    def broken(request):
        raise RuntimeError("boom")

    adapter_probe = probe_mod.probe_usage("openai", "test-instance",
                                          FakeTransport(broken))
    assert adapter_probe["state"] == "UNKNOWN"
    assert adapter_probe["output_tokens"] == UNAVAILABLE


def test_streaming_usage_verified_separately():
    combined = probe_mod.probe_adapter(
        "openai", "test-instance",
        _usage_transport({"input_tokens": 10, "output_tokens": 5,
                          "cached_tokens": 0, "reasoning_tokens": 0}))
    assert combined["stream_usage"] == UNAVAILABLE

    combined = probe_mod.probe_adapter(
        "openai", "test-instance",
        _usage_transport({"input_tokens": 10, "output_tokens": 5}),
        stream_transport=_usage_transport({"input_tokens": 10,
                                            "output_tokens": 5}))
    assert combined["state"] == "PARTIAL"
    assert combined["stream_usage"] != UNAVAILABLE
    assert combined["stream_usage"]["output_tokens"] == 5

    stream = probe_mod.probe_stream_usage(
        "openai", "test-instance",
        _usage_transport({"input_tokens": 3}))
    assert stream["stream_state"] == "PARTIAL"
    assert stream["stream_usage"]["input_tokens"] == 3
    assert stream["stream_usage"]["output_tokens"] == UNAVAILABLE


# [BP06-72]-part: mock routes served until the user supplies a key.

def test_mock_until_key_and_marked():
    adapter = MockProviderAdapter(_config(provider_id="mock",
                                          model="Mock-Model-1"))
    assert adapter.serves(key_supplied=False) is True
    assert adapter.serves(key_supplied=True) is False
    first = adapter.invoke([{"role": "user", "content": "hi"}])
    second = adapter.invoke([{"role": "user", "content": "again"}])
    assert first.mock is True
    assert first.to_record()["mock"] is True
    assert second.to_record()["mock"] is True
    assert first.output_text


def test_mock_usage_probe_transport():
    adapter = MockProviderAdapter(_config(provider_id="mock"))
    probed = probe_mod.probe_usage("mock", "test-instance",
                                   adapter.fake_usage_transport())
    assert probed["state"] == "VERIFIED"
    assert probed["input_tokens"] == 0


# Adapters import with stdlib only: no third-party SDK import required.

def test_no_third_party_sdk_imported():
    import subprocess

    child = (
        "import sys\n"
        "sys.path.insert(0, %r)\n"
        "for name in (\"litellm\", \"openai\", \"anthropic\", \"google\", \"mistralai\",\n"
        "             \"groq\", \"httpx\", \"requests\", \"aiohttp\"):\n"
        "    assert name not in sys.modules, name\n"
        "from agent_si.providers.adapters.litellm_backed import LiteLLMBackedAdapter\n"
        "assert LiteLLMBackedAdapter.openai_compat is False\n"
    ) % (_SRC,)
    proc = subprocess.run([sys.executable, "-c", child],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


# K04 W04 A1W04-pins (additive only): default usage-probe port configured
# by bind_provider for openai_compat legs, plus the production caller
# check_provider_health genuinely reaching usage_probe.probe_adapter.

from agent_si.providers.adapters import facades as facades_mod


# FAKE-OF: agent_si.providers.adapters.facades (bound chat transport port)
class _RecordingChatTransport:
    """Injected bound chat transport: records requests, plays back a real
    chat-shaped reply carrying usage (no network)."""

    def __init__(self, usage):
        self.usage = dict(usage)
        self.requests = []

    def __call__(self, request):
        self.requests.append(dict(request))
        return {
            "output_text": "canned final",
            "finish": "stop",
            "usage": dict(self.usage),
            "raw": {"input_tokens": self.usage.get("input_tokens", 0)},
            "raw_safe": True,
        }


_FULL_CHAT_USAGE = {
    "input_tokens": 10,
    "output_tokens": 5,
    "cached_tokens": 2,
    "reasoning_tokens": 0,
}


def _bind_openai_w04(instance_id="default", usage=None):
    facades_mod.clear_adapter_transports()
    facades_mod.clear_provider_bindings()
    transport = _RecordingChatTransport(
        _FULL_CHAT_USAGE if usage is None else usage)
    facades_mod.bind_provider(
        "openai",
        {"secret_id": "s-health", "provider_id": "openai"},
        transport,
        "https://api.example/v1",
        instance_id=instance_id,
    )
    return transport


def test_w04_default_probe_port_on_bind_openai_compat():
    transport = _bind_openai_w04()
    try:
        assert transport.requests == []
        capability = facades_mod.probe_usage("openai/default", "openai",
                                             False)
        assert capability["state"] == "VERIFIED"
        assert capability["input_tokens"] == 10
        assert capability["output_tokens"] == 5
        # Genuinely flowed through the bound chat transport: one
        # translated chat-shaped request carrying the probe marker and
        # id-only secret identity (never raw key material).
        assert len(transport.requests) == 1
        sent = transport.requests[0]
        assert sent["probe"] == "usage"
        assert sent["provider_id"] == "openai"
        assert sent["instance_id"] == "default"
        assert "value" not in sent["secret_ref"]
        # The bare provider id resolves too for the default instance.
        bare = facades_mod.probe_usage("openai", "openai", False)
        assert bare["state"] == "VERIFIED"
        assert bare["input_tokens"] == 10
    finally:
        facades_mod.clear_adapter_transports()
        facades_mod.clear_provider_bindings()


def test_w04_production_caller_reaches_real_probe_port():
    transport = _bind_openai_w04()
    try:
        result = facades_mod.check_provider_health("openai",
                                                   "Exact-Model-7")
        assert set(result) == {"provider_id", "model_id", "fields",
                               "usage", "checked_at"}
        assert result["provider_id"] == "openai"
        assert result["model_id"] == "Exact-Model-7"
        assert result["fields"]["secret_id"] == "s-health"
        assert result["fields"]["instance_id"] == "default"
        assert result["fields"]["endpoint"] == "https://api.example/v1"
        assert "value" not in result["fields"]
        assert result["checked_at"]
        usage = result["usage"]
        assert usage["state"] == "VERIFIED"
        assert usage["input_tokens"] == 10
        assert usage["stream_usage"] == "UNAVAILABLE"
        # The real bound transport was invoked exactly once by the
        # non-streaming health check: genuine wiring, no fake in product.
        assert len(transport.requests) == 1
        streamed = facades_mod.check_provider_health("openai",
                                                     "Exact-Model-7", True)
        assert streamed["usage"]["stream_usage"] != "UNAVAILABLE"
        assert streamed["usage"]["stream_usage"]["output_tokens"] == 5
        assert len(transport.requests) == 3
    finally:
        facades_mod.clear_adapter_transports()
        facades_mod.clear_provider_bindings()


def test_w04_default_probe_port_non_default_instance():
    transport = _bind_openai_w04(instance_id="n1")
    try:
        capability = facades_mod.probe_usage("openai/n1", "openai", False)
        assert capability["state"] == "VERIFIED"
        assert capability["instance_id"] == "n1"
        assert capability["input_tokens"] == 10
        assert len(transport.requests) == 1
        with pytest.raises(ValueError):
            facades_mod.probe_usage("openai", "openai", False)
    finally:
        facades_mod.clear_adapter_transports()
        facades_mod.clear_provider_bindings()


@pytest.mark.parametrize("provider_id", ["anthropic", "claude", "gemini"])
def test_w04_non_compat_legs_fail_closed(provider_id):
    facades_mod.clear_adapter_transports()
    facades_mod.clear_provider_bindings()
    try:
        transport = _RecordingChatTransport(_FULL_CHAT_USAGE)
        facades_mod.bind_provider(
            provider_id,
            {"secret_id": "s-nc", "provider_id": provider_id},
            transport,
            "https://api.example/v1",
        )
        with pytest.raises(ValueError):
            facades_mod.probe_usage("%s/default" % provider_id,
                                    provider_id, False)
        with pytest.raises(ValueError):
            facades_mod.check_provider_health(provider_id, "m-1")
        assert transport.requests == []
    finally:
        facades_mod.clear_adapter_transports()
        facades_mod.clear_provider_bindings()


def test_w04_bind_without_transport_fails_closed():
    facades_mod.clear_adapter_transports()
    facades_mod.clear_provider_bindings()
    try:
        facades_mod.bind_provider(
            "openai",
            {"secret_id": "s-none", "provider_id": "openai"},
            None,
            "https://api.example/v1",
        )
        with pytest.raises(ValueError):
            facades_mod.probe_usage("openai/default", "openai", False)
        with pytest.raises(ValueError):
            facades_mod.check_provider_health("openai", "m-1")
    finally:
        facades_mod.clear_adapter_transports()
        facades_mod.clear_provider_bindings()


# K04REST served proofs (CODER-1 Adapters): one served test per row
# UI_DELTA-33/4/17/30/31/228 over the owned adapter surface (base.py,
# usage_probe.py). Each proof boots the served app (create_app +
# TestClient, memory secret store) for the served leg, then drives the
# owned surface with test-injected fake transports. Fakes live only in
# these tests (K06 rule); product code carries no fakes.

def _served_client(tmp_path):
    """Boot the served app for a K04REST adapter proof (served leg)."""
    import os as _os

    _os.environ["AGENT_SI_SECRET_STORE"] = "memory"
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


# [UI_DELTA-33]-part: SecretRef exactness + verbatim ids, served.
def test_k04rest_adapt_33(tmp_path):
    client = _served_client(tmp_path)
    _served_baseline(client)
    ref = make_secret_ref(secret_id="K04R-33", provider_id="OpenAI")
    assert set(ref) == set(base_mod.SECRET_REF_FIELDS)
    over = dict(ref)
    over["nickname"] = "not-a-20A-field"
    with pytest.raises(AdapterConfigError):
        AdapterConfig(
            provider_id="OpenAI", instance_id="I-33", model="MiXeD-33",
            secret_ref=over, base_url="https://s33.example/v1")
    config = AdapterConfig(
        provider_id="OpenAI", instance_id="I-33", model="MiXeD-33",
        secret_ref=ref, base_url="https://s33.example/v1")
    seen = []

    # FAKE-OF: agent_si.providers.adapters.base (transport port)
    def respond(request):
        seen.append(dict(request))
        return _stop_response(request)

    response = OpenAICompatAdapter(config, FakeTransport(respond)).invoke(
        [{"role": "user", "content": "hi"}])
    assert response.model == "MiXeD-33"
    assert seen[0]["model"] == "MiXeD-33"
    assert seen[0]["secret_ref"] == ref
    assert "value" not in seen[0]["secret_ref"]


# [UI_DELTA-4]-part: typed 5xx/timeout failures carry error_ref, served.
def test_k04rest_adapt_4(tmp_path):
    client = _served_client(tmp_path)
    _served_baseline(client)

    # FAKE-OF: agent_si.providers.adapters.base (TransportHttpError signal)
    def http_5xx(request):
        raise TransportHttpError(503, "service unavailable")

    with pytest.raises(ProviderHttpError) as http_exc:
        OpenAICompatAdapter(_config(), FakeTransport(http_5xx)).invoke(
            [{"role": "user", "content": "hi"}])
    assert http_exc.value.status == 503
    assert isinstance(http_exc.value.error_ref, str)
    assert "openai" in http_exc.value.error_ref

    # FAKE-OF: agent_si.providers.adapters.base (builtin timeout signal)
    def net_timeout(request):
        raise TimeoutError("timed out")

    with pytest.raises(ProviderTimeoutError) as timeout_exc:
        OpenAICompatAdapter(_config(), FakeTransport(net_timeout)).invoke(
            [{"role": "user", "content": "hi"}])
    assert isinstance(timeout_exc.value.error_ref, str)
    assert "openai" in timeout_exc.value.error_ref


# [UI_DELTA-17]-part: max_retries=0 single-attempt, served.
def test_k04rest_adapt_17(tmp_path):
    client = _served_client(tmp_path)
    _served_baseline(client)
    assert AdapterConfig(
        provider_id="openai", model="m",
        secret_ref=_secret()).max_retries == 0
    with pytest.raises(AdapterConfigError):
        AdapterConfig(
            provider_id="openai", model="m", secret_ref=_secret(),
            max_retries=2)
    calls = []

    # FAKE-OF: agent_si.providers.adapters.base (TransportHttpError signal)
    def http_5xx(request):
        calls.append(dict(request))
        raise TransportHttpError(503, "service unavailable")

    adapter = OpenAICompatAdapter(_config(), FakeTransport(http_5xx))
    assert adapter.config.max_retries == 0
    with pytest.raises(ProviderHttpError):
        adapter.invoke([{"role": "user", "content": "hi"}])
    assert len(calls) == 1


# [UI_DELTA-30]-part: full usage probe reports VERIFIED, served.
def test_k04rest_adapt_30(tmp_path):
    client = _served_client(tmp_path)
    _served_baseline(client)
    full = {"input_tokens": 10, "output_tokens": 5,
            "cached_tokens": 2, "reasoning_tokens": 0}
    capability = probe_mod.probe_adapter(
        "openai", "test-instance",
        _usage_transport(full),
        stream_transport=_usage_transport(full),
        evidence_ref="ev-30")
    assert capability["state"] == "VERIFIED"
    assert capability["input_tokens"] == 10
    assert capability["output_tokens"] == 5
    assert capability["cached_tokens"] == 2
    assert capability["reasoning_tokens"] == 0
    assert capability["raw_usage"] == full
    assert capability["stream_usage"] == full
    assert capability["evidence_ref"] == "ev-30"
    assert capability["verified_at"]
    assert set(capability) == set(probe_mod.USAGE_CAPABILITY_FIELDS)


# [UI_DELTA-31]-part: partial usage reports PARTIAL + UNAVAILABLE, served.
def test_k04rest_adapt_31(tmp_path):
    client = _served_client(tmp_path)
    _served_baseline(client)
    capability = probe_mod.probe_usage(
        "openai", "test-instance", _usage_transport({"input_tokens": 12}))
    assert capability["state"] == "PARTIAL"
    assert capability["input_tokens"] == 12
    assert capability["output_tokens"] == UNAVAILABLE
    assert capability["cached_tokens"] == UNAVAILABLE
    assert capability["reasoning_tokens"] == UNAVAILABLE
    stream = probe_mod.probe_stream_usage(
        "openai", "test-instance", _usage_transport({"output_tokens": 5}))
    assert stream["stream_state"] == "PARTIAL"
    assert stream["stream_usage"]["output_tokens"] == 5
    assert stream["stream_usage"]["input_tokens"] == UNAVAILABLE


# [UI_DELTA-228]-part: streaming usage probed separately, served.
def test_k04rest_adapt_228(tmp_path):
    client = _served_client(tmp_path)
    _served_baseline(client)
    full = {"input_tokens": 10, "output_tokens": 5,
            "cached_tokens": 0, "reasoning_tokens": 0}
    usage_calls = []

    # FAKE-OF: agent_si.providers.adapters.usage_probe (usage transport port)
    def usage_reply(request):
        usage_calls.append(dict(request))
        return {"usage": dict(full), "raw": dict(full), "raw_safe": True}

    stream_calls = []

    # FAKE-OF: agent_si.providers.adapters.usage_probe (stream transport port)
    def stream_reply(request):
        stream_calls.append(dict(request))
        return {"usage": dict(full), "raw": dict(full), "raw_safe": True}

    combined = probe_mod.probe_adapter(
        "openai", "test-instance", usage_reply,
        stream_transport=stream_reply)
    assert combined["state"] == "VERIFIED"
    assert combined["stream_usage"] == full
    assert len(usage_calls) == 1 and usage_calls[0]["stream"] is False
    assert len(stream_calls) == 1 and stream_calls[0]["stream"] is True
    unstreamed = probe_mod.probe_adapter(
        "openai", "test-instance", usage_reply)
    assert unstreamed["stream_usage"] == UNAVAILABLE


# K04NEXT M2 CODER-1 Adapters: served proofs for rows 42, 43, R-305, R-306,
# R-307 over the owned adapter surface. Each boots the served app (served
# leg) then drives the owned surface with test-injected fakes only (K06
# rule); product carries no fakes.

# [row-42]-part: no baked-in vendor default; fresh install blocks w/ reason.
def test_row42_fresh_install_no_default_vendor_blocks_with_reason(tmp_path):
    client = _served_client(tmp_path)
    resp = client.get("/api/v1/providers")
    assert resp.status_code == 200, resp.text
    rows = resp.json().get("providers", [])
    assert rows == []
    models = client.get("/api/v1/providers/openai/models")
    assert models.status_code == 404, models.text
    assert "unknown provider" in models.json()["error"]
    facades_mod.clear_adapter_transports()
    facades_mod.clear_provider_bindings()
    try:
        with pytest.raises(ValueError, match="unbound provider"):
            facades_mod.resolve_model("openai", "Fresh-Model-1")
        with pytest.raises(ValueError, match="unbound provider"):
            facades_mod.check_provider_health("openai", "Fresh-Model-1")
        empty_secret = dict(_secret("openai"))
        empty_secret["secret_id"] = ""
        with pytest.raises(AdapterConfigError):
            AdapterConfig(
                provider_id="openai", model="m", secret_ref=empty_secret,
                base_url="https://row42.example/v1")
        with pytest.raises(AdapterConfigError):
            AdapterConfig(
                provider_id="openai", model="m",
                secret_ref=_secret("openai"),
                base_url="https://row42.example/v1", instance_id="")
    finally:
        facades_mod.clear_adapter_transports()
        facades_mod.clear_provider_bindings()


# [row-43]-part: pinned config frozen; swaps only via the recorded path.
def test_row43_pinned_swap_only_through_recorded_path(tmp_path):
    import dataclasses

    client = _served_client(tmp_path)
    _served_baseline(client)
    config = _config()
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.model = "Swapped-Model-9"
    transport = FakeTransport(_stop_response)
    adapter = OpenAICompatAdapter(config, transport)
    response = adapter.invoke([{"role": "user", "content": "hi"}],
                              params={"model": "Override-Model-2"})
    assert response.model == "Override-Model-2"
    assert response.to_record()["model"] == "Override-Model-2"
    assert transport.requests[0]["model"] == "Override-Model-2"
    assert config.model == "Exact-Model_Id-7"
    facades_mod.clear_adapter_transports()
    facades_mod.clear_provider_bindings()
    try:
        first = facades_mod.bind_provider(
            "openai", {"secret_id": "s-43", "provider_id": "openai"},
            transport, "https://one.example/v1")
        assert first["evidence_ref"] == "binding:openai/default"
        assert first["bound_at"]
        second = facades_mod.bind_provider(
            "openai", {"secret_id": "s-43", "provider_id": "openai"},
            transport, "https://two.example/v1")
        assert second["evidence_ref"] == "binding:openai/default"
        assert second["bound_at"]
        resolved = facades_mod.resolve_model("openai", "Pinned-43")
        assert resolved["provider_id"] == "openai"
        assert resolved["model_id"] == "Pinned-43"
        assert resolved["fields"]["endpoint"] == "https://two.example/v1"
        assert resolved["fields"]["evidence_ref"] == "binding:openai/default"
        assert "value" not in resolved["fields"]
    finally:
        facades_mod.clear_adapter_transports()
        facades_mod.clear_provider_bindings()


# [R-305]-part: exact assigned model id; visible allow-list; labels exact.
def test_r305_exact_model_visible_allowlist_exact_labels(tmp_path):
    client = _served_client(tmp_path)
    _served_baseline(client)
    with pytest.raises(AdapterConfigError) as excinfo:
        leg_descriptor("OPENAI")
    message = str(excinfo.value)
    for allowed in ("openai", "anthropic", "ollama", "lm_studio"):
        assert allowed in message
    facades_mod.clear_adapter_transports()
    facades_mod.clear_provider_bindings()
    try:
        facades_mod.bind_provider(
            "openai", {"secret_id": "s-305", "provider_id": "openai"},
            _RecordingChatTransport(_FULL_CHAT_USAGE),
            "https://api.example/v1")
        resolved = facades_mod.resolve_model("openai", "MiXeD-305_Model")
        assert resolved["provider_id"] == "openai"
        assert resolved["model_id"] == "MiXeD-305_Model"
        assert resolved["fields"]["instance_id"] == "default"
        capability = facades_mod.probe_usage("openai/default", "openai",
                                             False)
        assert capability["provider_id"] == "openai"
        assert capability["instance_id"] == "default"
        assert capability["state"] == "VERIFIED"
        assert capability["input_tokens"] == 10
        with pytest.raises(ValueError, match="not bound to provider"):
            facades_mod.probe_usage("openai/default", "anthropic", False)
    finally:
        facades_mod.clear_adapter_transports()
        facades_mod.clear_provider_bindings()


# [R-306]-part: mixed-provider hierarchy acceptance mini-drive.
def test_r306_mixed_provider_hierarchy_minidrive(tmp_path):
    import dataclasses

    client = _served_client(tmp_path)
    _served_baseline(client)
    facades_mod.clear_adapter_transports()
    facades_mod.clear_provider_bindings()
    try:
        plan = (("openai", True), ("anthropic", False), ("ollama", True))
        records = []
        for provider_id, compat in plan:
            secret = _secret(provider_id)
            assert secret["secret_id"]
            kwargs = {}
            base_url = "https://r306.example/v1"
            if provider_id == "ollama":
                base_url = None
            if compat:
                kwargs["transport"] = FakeTransport(_stop_response)
            else:
                kwargs["litellm_call"] = FakeTransport(_stop_response)
            adapter = build_leg(provider_id, model="R306-%s" % provider_id,
                                secret_ref=secret, base_url=base_url,
                                **kwargs)
            with pytest.raises(dataclasses.FrozenInstanceError):
                adapter.config.model = "Swapped"
            response = adapter.invoke([{"role": "user", "content": "hi"}])
            record = response.to_record()
            assert record["provider_id"] == provider_id
            assert record["model"] == "R306-%s" % provider_id
            assert record["mock"] is False
            records.append(record)
        mock_adapter = MockProviderAdapter(
            AdapterConfig(provider_id="mock", instance_id="r306",
                          model="R306-mock", secret_ref=_secret("mock")))
        assert mock_adapter.serves(key_supplied=False) is True
        assert mock_adapter.serves(key_supplied=True) is False
        mock_record = mock_adapter.invoke(
            [{"role": "user", "content": "hi"}]).to_record()
        assert mock_record["provider_id"] == "mock"
        assert mock_record["mock"] is True
        records.append(mock_record)
        assert [item["provider_id"] for item in records] == [
            "openai", "anthropic", "ollama", "mock"]
        assert [item["model"] for item in records] == [
            "R306-openai", "R306-anthropic", "R306-ollama", "R306-mock"]
        for provider_id in ("openai", "anthropic", "ollama"):
            facades_mod.bind_provider(
                provider_id,
                {"secret_id": "s-306", "provider_id": provider_id},
                FakeTransport(_stop_response),
                "https://r306.example/v1")
        resolved = facades_mod.resolve_model("ollama", "R306-ollama")
        assert resolved["model_id"] == "R306-ollama"
        assert resolved["fields"]["instance_id"] == "default"
        assert resolved["fields"]["secret_id"] == "s-306"
        health = facades_mod.check_provider_health("openai", "R306-openai")
        assert health["model_id"] == "R306-openai"
        assert health["usage"]["state"] == "PARTIAL"
        with pytest.raises(ValueError):
            facades_mod.check_provider_health("anthropic", "R306-anthropic")
    finally:
        facades_mod.clear_adapter_transports()
        facades_mod.clear_provider_bindings()


# [R-307]-part: providers verified on distinct levels, never conflated.
def test_r307_providers_verified_on_distinct_levels(tmp_path):
    client = _served_client(tmp_path)
    _served_baseline(client)
    facades_mod.clear_adapter_transports()
    facades_mod.clear_provider_bindings()
    try:
        full = {"input_tokens": 10, "output_tokens": 5,
                "cached_tokens": 2, "reasoning_tokens": 0}
        facades_mod.bind_provider(
            "openai", {"secret_id": "s-307", "provider_id": "openai"},
            _RecordingChatTransport(full), "https://api.example/v1")
        verified = facades_mod.probe_usage("openai/default", "openai",
                                           False)
        assert verified["provider_id"] == "openai"
        assert verified["instance_id"] == "default"
        assert verified["state"] == "VERIFIED"
        assert verified["input_tokens"] == 10
        assert verified["stream_usage"] == UNAVAILABLE
        with pytest.raises(ValueError, match="not bound to provider"):
            facades_mod.probe_usage("openai/default", "groq", False)

        # FAKE-OF: agent_si.providers.adapters.facades (unsupported port)
        def unsupported(request):
            raise TransportUnsupportedError("no usage")

        facades_mod.register_adapter_transports(
            "groq", FakeTransport(unsupported))
        groq = facades_mod.probe_usage("groq", "groq", False)
        assert groq["provider_id"] == "groq"
        assert groq["state"] == "UNSUPPORTED"
        assert groq["input_tokens"] == UNAVAILABLE
        with pytest.raises(ValueError):
            facades_mod.probe_usage("no-such-adapter", "groq", False)
    finally:
        facades_mod.clear_adapter_transports()
        facades_mod.clear_provider_bindings()


