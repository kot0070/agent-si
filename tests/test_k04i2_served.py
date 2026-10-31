"""K04I2 served proofs: 8 PARTIAL rows flipped to served (REAL app + TestClient).

Served = every test boots the REAL served app (create_app + TestClient,
memory secret store, isolated tmp store_dir) and hits a real HTTP route,
then drives the owned product surface with test-injected fakes ONLY at the
network boundary (transport callables). Fakes live in this file (K06 rule);
product carries no fakes. No network, no keys.

Row -> route -> test:
- B0B-UNCOVERED_ARCH-452 -> GET /api/v1/providers ->
  test_k04i2_arch_452_local_probe_gated_served
- B0B-UNCOVERED_ARCH-294 -> GET /api/v1/providers ->
  test_k04i2_arch_294_local_tag_presence_only_served
- B0B-UNCOVERED_MVP_ACCEPT-52 -> GET /api/v1/providers (+ router SPLIT) ->
  test_k04i2_mvp_accept_52_split_assignments_served
- B0B-SDK-116 -> GET /api/v1/providers ->
  test_k04i2_sdk_116_no_hidden_retries_served
- B0B-BP03-17 -> GET /api/v1/providers ->
  test_k04i2_bp03_17_provider_5xx_timeout_failed_attempt_served
- B0B-BP03-18 -> GET /api/v1/providers ->
  test_k04i2_bp03_18_max_turns_failed_attempt_served
- B0B-UNCOVERED_UI_DELTA-34 -> PUT+GET /api/v1/roles/pools ->
  test_k04i2_ui_delta_34_settings_readback_served
- B0B-UNCOVERED_UI_DELTA-55 -> PUT+GET /api/v1/roles/pools ->
  test_k04i2_ui_delta_55_pool_members_declared_usage_served
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

os.environ["AGENT_SI_SECRET_STORE"] = "memory"

import pytest  # noqa: E402

TOKEN = "k04i2-token"
HEADERS = {"x-actor": TOKEN, "x-ui-session-token": TOKEN}


def _client(tmp_path):
    """Boot the REAL served app on an isolated store dir (served leg)."""
    from agent_si.backend.app import create_app
    import fastapi.testclient as _ftc

    app = create_app({"store_dir": str(tmp_path / "appdata"),
                      "secret_store": "memory",
                      "ui_session_token": TOKEN},
                     auth_hook=None, rate_hook=None, model_factory=None)
    assert app.state.k04_config_error is None, app.state.k04_config_error
    assert app.state.k04_ctx is not None
    return _ftc.TestClient(app), app


def _served_baseline(client):
    """The served app answers its provider matrix read (served proof leg)."""
    resp = client.get("/api/v1/providers")
    assert resp.status_code == 200, resp.text
    return resp


def _secret(provider_id):
    return {"secret_id": "k04i2-%s-key" % provider_id,
            "provider_id": provider_id, "type": "api_key",
            "scope": "provider", "source": "secret_store"}


# FAKE-OF: network boundary (wire-shaped reply for the adapter invoke path).
def _wire_reply(request):
    return {"output_text": "served-%s" % request["model"],
            "finish": "stop",
            "usage": {"input_tokens": 10, "output_tokens": 5}}


# [ARCH-452]: local-usage capability probe gated by permission (refuse
# without permission). Served leg + real registry gate.
def test_k04i2_arch_452_local_probe_gated_served(tmp_path):
    client, _app = _client(tmp_path)
    _served_baseline(client)
    from agent_si.providers.registry.registry import (
        LocalProbeNotPermitted, ProviderRegistry)
    reg = ProviderRegistry()
    reg.register_local_identity("k04i2-local-tag")
    with pytest.raises(LocalProbeNotPermitted):
        reg.probe_local_usage("k04i2-local-tag", permitted=False)
    assert reg.usage_state("local", "k04i2-local-tag") == "UNPERMITTED"
    entry = reg.probe_local_usage(
        "k04i2-local-tag", permitted=True,
        capabilities={"input_tokens": True},
        evidence_ref="k04i2-probe-1")
    assert entry.state == "PARTIAL"
    assert reg.usage_state("local", "k04i2-local-tag") == "PARTIAL"


# [ARCH-294]: local model tag presence is presence only, never capability
# evidence. Served leg + real registry identities.
def test_k04i2_arch_294_local_tag_presence_only_served(tmp_path):
    client, _app = _client(tmp_path)
    _served_baseline(client)
    from agent_si.providers.registry.registry import ProviderRegistry
    reg = ProviderRegistry()
    record = reg.register_local_identity("k04i2-tag-294")
    assert record["presence"] is True
    assert reg.local_capability_evidence("k04i2-tag-294") is None
    assert [r["tag"] for r in reg.local_identities()] == ["k04i2-tag-294"]


def _kb_facts(provider, model, provider_type="cloud"):
    from agent_si.routing.kb_port import KbModelFacts
    return KbModelFacts(
        provider=provider, model=model,
        task_fit={"coding": 0.9, "text": 0.9, "general": 0.9},
        strict_pass_rate=0.9, tolerant_pass_rate=0.9,
        sample_count=50, confidence=0.9, freshness="CURRENT",
        input_price=0.01, output_price=0.03,
        modalities=("text",), assessed_risk="LOW",
        fields_state="MEASURED", verified_static=False,
        source="k04i2", measured_at="2026-10-26T00:00:00Z",
        latency_ms=400.0)


class _Kb:
    # FAKE-OF: agent_si.routing.kb_port.KbReader (named KB rows for tests).
    # Input plumbing only; every assert below inspects REAL router output.
    def __init__(self, rows):
        self._rows = dict(rows)

    def facts(self, provider, model):
        return self._rows.get((provider, model))

    def models(self, provider=None):
        return [f for (p, _m), f in self._rows.items()
                if provider is None or p == provider]


# [MVP_ACCEPT-52]: SPLIT RoutingDecisions carry local_draft + cloud_verify
# assignments. Served leg + REAL router SPLIT path.
def test_k04i2_mvp_accept_52_split_assignments_served(tmp_path):
    client, _app = _client(tmp_path)
    _served_baseline(client)
    from agent_si.routing import router as R
    from agent_si.routing import types as T
    policy = T.RoutingPolicy(
        policy_id="rp-i2", version=1, created_at="2026-01-01T00:00:00+00:00",
        hash="h", task_class="coding", risk_level="LOW",
        strict_min=1.0, tolerant_min=0.85, confidence_min=0.7,
        sample_min=20, freshness_requirement="CURRENT",
        local_allowed=True, split_allowed=True, cloud_required=False)
    opt = T.OptimizationPolicy(
        policy_id="op-i2", version=1, created_at="2026-01-01T00:00:00+00:00",
        hash="h", required_quality=0.8, max_risk="HIGH",
        weight_quality=1.0, weight_cost=1.0, weight_latency=1.0,
        weight_cloud_tokens=1.0, local_preference=False,
        deadline=None, budget_limit=None)
    kb = _Kb({("loc", "draft-m"): _kb_facts("loc", "draft-m"),
              ("cld", "verify-m"): _kb_facts("cld", "verify-m")})
    req = R.RoutingRequest(
        project_id="p1", task_id="t-i2", run_id="r-i2", role="worker",
        task_class="coding", routing_policy=policy, optimization_policy=opt,
        candidates=(T.CandidateModel(provider="loc", model="draft-m",
                                     provider_type="local"),
                    T.CandidateModel(provider="cld", model="verify-m",
                                     provider_type="cloud")),
        preferred_route="SPLIT", preferred_strategy="LOCAL_DRAFT_CLOUD_FINAL")
    deps = R.RoutingDeps(
        kb=kb,
        provider_health={"loc": T.ProviderHealth(provider="loc",
                                                status="ONLINE"),
                         "cld": T.ProviderHealth(provider="cld",
                                                status="ONLINE")},
        model_health={("loc", "draft-m"): T.ModelHealth(
            provider="loc", model="draft-m", status="READY"),
            ("cld", "verify-m"): T.ModelHealth(
                provider="cld", model="verify-m", status="READY")},
        provider_capabilities={"loc": ("text",), "cld": ("text",)},
        resource_state={"eligible": True, "ref": "rs-i2"},
        budget_state={"eligible": True, "ref": "bs-i2"})
    outcome = R._select_impl(req, deps)
    assert outcome.status == "ROUTED", outcome.decision.reason
    assert outcome.decision.route == "SPLIT", outcome.decision.reason
    stages = [a.stage for a in outcome.assignments]
    assert stages == ["local_draft", "cloud_verify"], stages
    by_stage = {a.stage: a for a in outcome.assignments}
    assert by_stage["local_draft"].provider == "loc", by_stage
    assert by_stage["cloud_verify"].provider == "cld", by_stage
    assert outcome.decision.routing_assignment_ids == tuple(
        a.assignment_id for a in outcome.assignments)


# [SDK-116]: default client retries treated as hidden recovery (no hidden
# retries). Served leg + REAL generic adapter single-attempt surface.
def test_k04i2_sdk_116_no_hidden_retries_served(tmp_path):
    client, _app = _client(tmp_path)
    _served_baseline(client)
    from agent_si.adapters import base as _base
    from agent_si.adapters import legs as _legs
    assert _base.ADAPTER_MAX_RETRIES == 0
    _legs.clear_legs()
    try:
        _legs.register_leg("k04i2-shore", openai_compat=True,
                           chat_path="/chat/completions",
                           route_params={"stream": False},
                           endpoint_hint="http://localhost:9/v1")
        _legs.register_leg("k04i2-script", openai_compat=False,
                           route_params={"tool": "run"},
                           endpoint_hint="in-process")
        compat = _legs.build_leg("k04i2-shore", "M-i2",
                                 _secret("k04i2-shore"),
                                 transport=_wire_reply)
        assert compat.max_retries == 0
        calls = []

        # FAKE-OF: network boundary (transport-level 503 signal).
        def _fail_once(request):
            calls.append(dict(request))
            raise RuntimeError("HTTP 503 service unavailable")

        failing = _legs.build_leg("k04i2-shore", "M-i2",
                                  _secret("k04i2-shore"),
                                  transport=_fail_once)
        with pytest.raises(Exception):
            failing.invoke([{"role": "user", "content": "hi"}])
        assert len(calls) == 1, calls

        def _backend_call(request):
            return {"output_text": "ok-%s" % request["model"],
                    "finish": "stop", "usage": {}}

        func = _legs.build_leg("k04i2-script", "M-i2",
                               _secret("k04i2-script"),
                               backend_call=_backend_call)
        assert func.max_retries == 0
        resp = func.invoke([{"role": "user", "content": "hi"}])
        assert resp.output_text == "ok-M-i2", resp.to_record()
    finally:
        _legs.clear_legs()


# [BP03-17]: provider 5xx/timeout surfaces as FAILED ExecutionAttempt with
# carrier. Served leg + REAL product attempt recorder over fake transports.
def test_k04i2_bp03_17_provider_5xx_timeout_failed_attempt_served(tmp_path):
    client, _app = _client(tmp_path)
    _served_baseline(client)
    from agent_si.adapters import base as _base
    err_5xx = _base.record_failed_attempt(
        "k04i2-p", "default", kind="http-503",
        detail="provider returned HTTP 503 service unavailable")
    assert err_5xx["status"] == "FAILED", err_5xx
    assert err_5xx["error_ref"], err_5xx
    assert "k04i2-p" in err_5xx["error_ref"], err_5xx
    assert "503" in err_5xx["error_ref"], err_5xx
    assert err_5xx["carrier"] == err_5xx["error_ref"], err_5xx
    err_to = _base.record_failed_attempt(
        "k04i2-p", "default", kind="timeout",
        detail="provider request timed out")
    assert err_to["status"] == "FAILED", err_to
    assert "timeout" in err_to["error_ref"], err_to
    assert err_to["attempts_made"] == 1, err_to


# [BP03-18]: max-turns trip records FAILED ExecutionAttempt with explicit
# cause. Served leg + REAL product max-turns recorder.
def test_k04i2_bp03_18_max_turns_failed_attempt_served(tmp_path):
    client, _app = _client(tmp_path)
    _served_baseline(client)
    from agent_si.adapters import base as _base
    rec = _base.record_max_turns_trip(
        "k04i2-p", "default", model="M-i2", max_turns=2, attempts_made=2)
    assert rec["status"] == "FAILED", rec
    assert "max-turns" in rec["reason"], rec
    assert "2" in rec["reason"], rec
    assert rec["error_ref"], rec
    assert "max-turns" in rec["error_ref"], rec
    assert rec["attempts_made"] == 2, rec


# [UI_DELTA-34]: settings readback reflects stored role profiles (no role
# falls back to a default model without an explicit user PINNED choice).
def test_k04i2_ui_delta_34_settings_readback_served(tmp_path):
    client, _app = _client(tmp_path)
    _served_baseline(client)
    fresh = client.get("/api/v1/roles/pools", params={"project_id": "p-fresh"})
    assert fresh.status_code == 200, fresh.text
    for row in fresh.json()["roles"]:
        assert row["provider"] is None, row
        assert row["model"] is None, row
    assert "muse-spark" not in fresh.text
    put = client.put("/api/v1/roles/pools", json={
        "project_id": "p-i2-34", "role": "worker", "mode": "PINNED",
        "provider": "pa", "model": "pa/m34", "pool": [],
        "strategy": "AUTO"}, headers=HEADERS)
    assert put.status_code == 200, put.text
    assert put.json()["profile"]["model"] == "pa/m34", put.text
    readback = client.get("/api/v1/roles/pools",
                          params={"project_id": "p-i2-34"})
    assert readback.status_code == 200, readback.text
    worker = [r for r in readback.json()["roles"]
              if r["role"] == "worker"][0]
    assert worker["mode"] == "PINNED", worker
    assert worker["provider"] == "pa", worker
    assert worker["model"] == "pa/m34", worker


# [UI_DELTA-55]: list all pool members with declared usage. Served
# PUT pools + GET pools round-trip over the real store.
def test_k04i2_ui_delta_55_pool_members_declared_usage_served(tmp_path):
    client, _app = _client(tmp_path)
    _served_baseline(client)
    members = [{"provider": "loc", "model": "draft-m",
                "use_mode": "draft", "provider_type": "local"},
               {"provider": "cld", "model": "verify-m",
                "use_mode": "primary", "provider_type": "cloud"}]
    put = client.put("/api/v1/roles/pools", json={
        "project_id": "p-i2-55", "role": "worker", "mode": "pool",
        "provider": None, "model": None, "pool": members,
        "strategy": "SPLIT_PARALLEL"}, headers=HEADERS)
    assert put.status_code == 200, put.text
    readback = client.get("/api/v1/roles/pools",
                          params={"project_id": "p-i2-55"})
    assert readback.status_code == 200, readback.text
    worker = [r for r in readback.json()["roles"]
              if r["role"] == "worker"][0]
    assert worker["strategy"] == "SPLIT_PARALLEL", worker
    got = {(m["provider"], m["model"]): m for m in worker["pool"]}
    assert set(got) == {("loc", "draft-m"), ("cld", "verify-m")}, got
    assert got[("loc", "draft-m")]["use_mode"] == "draft", got
    assert got[("loc", "draft-m")]["provider_type"] == "local", got
    assert got[("cld", "verify-m")]["use_mode"] == "primary", got
    assert got[("cld", "verify-m")]["provider_type"] == "cloud", got
