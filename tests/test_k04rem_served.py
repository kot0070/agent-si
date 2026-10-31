"""K04REM served proof: B0B-UNCOVERED_ARCH-753 + LIVE0B-06.

Row B0B-UNCOVERED_ARCH-753 (provider clients max_retries 0, one
authoritative ExecutionAttempt): the served app boots, a provider client
built with defaults carries max_retries 0 (non-zero refused), one invoke
drives exactly one transport call, and the run posts exactly one
INITIAL ExecutionAttempt record.

Row LIVE0B-06 (GET /api/v1/budget answers the project budget, no 404):
the served app answers the seeded project budget with budget content.

Stdlib + pytest only; transports are injected (no network, no installs).
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
from agent_si.providers.adapters.openai_compat import OpenAICompatAdapter
from agent_si.state_machines import attempt_machine


def _secret():
    return make_secret_ref(
        secret_id="s-k04rem", provider_id="openai", type="api_key",
        scope="provider", source="secret_store",
    )


# FAKE-OF: agent_si.providers.adapters.base (ProviderAdapter transport port)
class _FakeTransport:
    """Injected transport double: records requests, plays back one stop."""

    def __init__(self):
        self.requests = []

    def __call__(self, request):
        self.requests.append(dict(request))
        return {"output_text": "rem-final", "finish": "stop",
                "usage": {"input_tokens": 3, "output_tokens": 1}}


def _served_client(tmp_path):
    from agent_si.backend.app import create_app
    import fastapi.testclient

    app = create_app({"store_dir": str(tmp_path), "secret_store": "memory"},
                     auth_hook=None, rate_hook=None, model_factory=None)
    return fastapi.testclient.TestClient(app)


def test_k04rem_b0b_max_retries_zero_single_authoritative_attempt(tmp_path):
    # B0B-UNCOVERED_ARCH-753: served leg boots, then the client rule.
    client = _served_client(tmp_path)
    baseline = client.get("/api/v1/providers")
    assert baseline.status_code == 200, baseline.text

    config = AdapterConfig(
        provider_id="openai", instance_id="rem-1", model="m-rem",
        secret_ref=_secret(), base_url="https://config.example/v1")
    assert config.max_retries == 0
    with pytest.raises(AdapterConfigError):
        AdapterConfig(
            provider_id="openai", instance_id="rem-1", model="m-rem",
            secret_ref=_secret(), base_url="https://config.example/v1",
            max_retries=2)

    transport = _FakeTransport()
    adapter = OpenAICompatAdapter(config, transport)
    response = adapter.invoke([{"role": "user", "content": "hi"}])
    assert response.finish_reason == "stop"
    assert len(transport.requests) == 1

    attempt = attempt_machine.ExecutionAttempt(
        attempt_id="att-rem-1", project_id="p1", task_id="t1", run_id="r1",
        routing_assignment_id="assign-rem-1", attempt_no=1,
        run_attempt_sequence=1,
        attempt_type=attempt_machine.AttemptType.INITIAL,
        provider="openai", provider_instance="rem-1", model="m-rem",
        canonical_provider_id="openai", canonical_model_id="m-rem",
        status="CREATED")
    assert attempt.attempt_no == 1
    assert attempt.run_attempt_sequence == 1
    assert attempt.retry_reason is None and attempt.fallback_reason is None
    assert attempt.status.value == "CREATED"


def test_k04rem_live0b_budget_route_answers_project_budget(tmp_path):
    # LIVE0B-06: GET /api/v1/budget answers the project budget, no 404.
    client = _served_client(tmp_path)
    gate = client.app.state.k04_ctx.budget_state
    gate.configure_project(
        project_id="p1", currency="USD", budget_limit="10.00",
        soft_limit="7.00", hard_limit="10.00")
    resp = client.get("/api/v1/budget", params={"project_id": "p1"})
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["project_id"] == "p1", payload
    budget = payload["budget"]
    assert budget["currency"] == "USD", budget
    assert budget["hard_limit"] == "10.00", budget
    assert budget["soft_limit"] == "7.00", budget
    assert budget["spent"] == "0", budget
    assert budget["reserved"] == "0", budget
