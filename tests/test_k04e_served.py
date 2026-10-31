"""K04E served proofs E: Meta endpoint/contract + credential gating (SDK-123/124, ARCH-303).

Served = each proof boots the served app (create_app + TestClient, memory
secret store) and reads the provider matrix route, then drives the owned
adapter surface with test-injected fake transports only. Fakes live in
tests (K06 rule); product carries no fakes. No network, no keys.

Row -> route -> test:
- B0B-SDK-123 -> GET /api/v1/providers ->
  test_k04e_sdk_123_meta_secret_ref_served
- B0B-SDK-124 -> GET /api/v1/providers ->
  test_k04e_sdk_124_meta_contract_served
- B0B-UNCOVERED_ARCH-303 -> GET /api/v1/providers ->
  test_k04e_arch_303_no_credential_ineligible_served
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import pytest

from agent_si.providers.adapters.base import (
    AdapterConfig,
    AdapterConfigError,
    make_secret_ref,
)
from agent_si.providers.adapters.legs import build_leg, leg_descriptor
from agent_si.providers.adapters import facades as facades_mod


META_BASE_URL = "https://meta-config.example/v1"


def _secret(provider_id):
    return make_secret_ref(
        secret_id="k04e-secret",
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


def _stop_response(request):
    # FAKE-OF: agent_si.providers.adapters.openai_compat (canned reply)
    return {
        "output_text": "canned final",
        "finish": "stop",
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


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


# [SDK-123]-part: the Meta leg reaches the Meta cloud endpoint through a
# secret reference (id-only; never raw key material).
def test_k04e_sdk_123_meta_secret_ref_served(tmp_path):
    client = _served_client(tmp_path)
    _served_baseline(client)
    assert leg_descriptor("meta")["openai_compat"] is True
    adapter = build_leg(
        "meta",
        model="Meta-K04E-1",
        secret_ref=_secret("meta"),
        base_url=META_BASE_URL,
        transport=_FakeTransport(_stop_response),
    )
    response = adapter.invoke([{"role": "user", "content": "hi"}])
    assert response.model == "Meta-K04E-1"
    descriptor = adapter.transport_descriptor()
    assert descriptor["endpoint"] == META_BASE_URL
    assert adapter.config.secret_ref["secret_id"] == "k04e-secret"
    assert "value" not in adapter.config.secret_ref


# [SDK-124]-part: the provider contract records the Meta endpoint and the
# model catalogue surface.
def test_k04e_sdk_124_meta_contract_served(tmp_path):
    client = _served_client(tmp_path)
    _served_baseline(client)
    facades_mod.clear_adapter_transports()
    facades_mod.clear_provider_bindings()
    try:
        transport = _FakeTransport(_stop_response)
        facades_mod.bind_provider(
            "meta",
            {"secret_id": "k04e-secret", "provider_id": "meta"},
            transport,
            META_BASE_URL,
        )
        resolved = facades_mod.resolve_model("meta", "Meta-K04E-2")
        assert resolved["provider_id"] == "meta"
        assert resolved["model_id"] == "Meta-K04E-2"
        fields = resolved["fields"]
        assert fields["endpoint"] == META_BASE_URL
        assert fields["secret_id"] == "k04e-secret"
        assert "value" not in fields
        assert fields["evidence_ref"] == "binding:meta/default"
        assert set(fields["capabilities"]) >= {
            "supports_streaming", "supports_tools", "max_context"}
    finally:
        facades_mod.clear_adapter_transports()
        facades_mod.clear_provider_bindings()


# [ARCH-303]-part: a provider without an evidenced credential is
# ineligible for routing; nothing routes on an absent credential.
def test_k04e_arch_303_no_credential_ineligible_served(tmp_path):
    client = _served_client(tmp_path)
    _served_baseline(client)
    facades_mod.clear_adapter_transports()
    facades_mod.clear_provider_bindings()
    try:
        with pytest.raises(ValueError, match="unbound provider"):
            facades_mod.resolve_model("openai", "Absent-K04E-1")
        with pytest.raises(ValueError, match="unbound provider"):
            facades_mod.check_provider_health("openai", "Absent-K04E-1")
        empty_secret = dict(_secret("openai"))
        empty_secret["secret_id"] = ""
        with pytest.raises(AdapterConfigError):
            AdapterConfig(
                provider_id="openai", model="m",
                secret_ref=empty_secret,
                base_url="https://k04e.example/v1")
    finally:
        facades_mod.clear_adapter_transports()
        facades_mod.clear_provider_bindings()
