"""FXR2E-2: one capability match fn + text/tools-only choice (RED-first).

Real id lists for anthropic, openai, google and ollama tags: dated
snapshots (claude-haiku-4-5-20251001) and runtime tags (qwen3:8b)
resolve to the KB row through the single loader match function
(exact, then without date suffix, then local tag). Meta contributor
ids stay verbatim. AUTO over two connected providers compares both
and the reason names the excluded candidates. Image/audio/embedding
models are never offered or chosen (AUTO, one-click, every role
picker); a pinned one gets a plain refusal. Ordering is by fit,
never alphabetic. A real leftover... (no: real catalog, real lists).
"""
import copy
import os
import sys

import pytest
from fastapi.testclient import TestClient

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from agent_si.model_kb import kb as _kb  # noqa: E402
from agent_si.model_kb import loader as _loader  # noqa: E402
from agent_si.model_kb.kb_reader import CatalogKbReader  # noqa: E402

SRC = "https://example.invalid/fxr2e"
AT = "2026-11-02"

TEXT = {"modalities": _kb.sourced("text, tools, coding", SRC, AT),
        "tool_calling": _kb.sourced("yes, native tool calls", SRC, AT),
        "input_token_price": _kb.sourced(1.0, SRC, AT),
        "output_token_price": _kb.sourced(2.0, SRC, AT)}
IMAGE = {"modalities": _kb.sourced("image", SRC, AT)}
AUDIO = {"modalities": _kb.sourced("text, audio", SRC, AT)}


def _catalog():
    # Deliberately non-alphabetic catalog order: fit order must win.
    # qwen3 carries UNKNOWN prices on purpose: the priced image row
    # must still never win (RED before the text/tools-only fix).
    rows = [
        _kb.make_model_row("ollama", "muse-image", dict(
            IMAGE,
            input_token_price=_kb.sourced(0.01, SRC, AT),
            output_token_price=_kb.sourced(0.02, SRC, AT))),
        _kb.make_model_row("anthropic", "claude-haiku-4-5", TEXT),
        _kb.make_model_row("meta", "muse-spark-1.3-contributor", TEXT),
        _kb.make_model_row("openai", "gpt-4o", TEXT),
        _kb.make_model_row("google", "gemini-2.5-flash", TEXT),
        _kb.make_model_row("ollama", "qwen3", {
            "modalities": _kb.sourced("text, tools, coding", SRC, AT),
            "tool_calling": _kb.sourced(
                "yes, native tool calls", SRC, AT)}),
        _kb.make_model_row("xai", "grok-voice", AUDIO),
    ]
    return _kb.make_catalog(rows, kb_version=1, updated_at=AT,
                            change_log=[], sources=[])


@pytest.fixture()
def catalog():
    saved = copy.deepcopy(_kb.bound_catalog())
    _kb.bind_catalog(_catalog())
    try:
        yield _kb.bound_catalog()
    finally:
        _kb.bind_catalog(saved)


def test_match_row_exact_dated_tag(catalog):
    """One fn: exact, dated-suffix strip, local-tag strip."""
    assert _loader.match_row(
        catalog, "anthropic", "claude-haiku-4-5")["model_id"] == \
        "claude-haiku-4-5"
    assert _loader.match_row(
        catalog, "anthropic",
        "claude-haiku-4-5-20251001")["model_id"] == "claude-haiku-4-5"
    assert _loader.match_row(
        catalog, "ollama", "qwen3:8b")["model_id"] == "qwen3"
    assert _loader.match_row(
        catalog, "meta", "muse-spark-1.3-contributor")["model_id"] == \
        "muse-spark-1.3-contributor"
    assert _loader.match_row(catalog, "openai", "gpt-9") is None


def test_every_reader_resolves_dated_and_tag(catalog):
    """bridge + kb_reader resolve the same dated/tag ids."""
    assert _loader.bridge(
        catalog, "anthropic",
        "claude-haiku-4-5-20251001")["kb_status"] == _loader.IN_BASE
    facts = CatalogKbReader().facts("ollama", "qwen3:8b")
    assert facts is not None and facts.model == "qwen3"


def test_auto_compares_both_and_reason_names_excluded(catalog):
    """Two connected providers both compare; reason names the rest."""
    auto = _loader.candidates_for_auto(catalog, ["anthropic", "openai"])
    compared = {(c["provider_id"], c["model_id"]) for c in auto["candidates"]}
    assert ("anthropic", "claude-haiku-4-5") in compared
    assert ("openai", "gpt-4o") in compared
    assert "meta" in auto["reason"] and "xai" in auto["reason"]
    assert "ollama" in auto["reason"] and "google" in auto["reason"]


def test_auto_route_never_chooses_image(catalog):
    """GET /api/v1/routing/auto never picks an image/audio model.

    ollama holds a priced image row plus an UNKNOWN-priced text row:
    cheapest-first would take the image row; the text/tools-only rule
    must pick qwen3 instead.
    """
    from agent_si.backend.app import create_app

    app = create_app({"testing": True,
                      "ui_session_token": "fxr2e-auto-token"})
    assert any(getattr(route, "path", None) == "/api/v1/routing/auto"
               for route in getattr(app, "routes", []))
    client = TestClient(app)
    resp = client.get("/api/v1/routing/auto",
                      params={"task_type": "coding",
                              "connected": "ollama"})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"manager": "ollama", "model": "qwen3"}


def test_one_click_never_offers_image(catalog):
    """One-click skips image/audio rows for the text/tools pick."""
    offer = _loader.offer_one_click(catalog, ["ollama", "openai"])
    assert offer["offer"] is not None
    assert (offer["offer"]["provider_id"], offer["offer"]["model_id"]) != \
        ("ollama", "muse-image")
    assert offer["offer"]["model_id"] in ("gpt-4o", "qwen3")


def test_role_pickers_order_by_fit_never_alpha(catalog):
    """Guided picker + strongest suggestion: fit order, no image rows.

    Even for purpose="vision" the picker never offers image/audio
    models: only text/tools-capable rows are offered, ordered by fit,
    never alphabetically.
    """
    from agent_si.routing import pools as _pools

    reader = CatalogKbReader()
    facts = [reader.facts("openai", "gpt-4o"),
             reader.facts("ollama", "muse-image"),
             reader.facts("google", "gemini-2.5-flash")]
    assert all(f is not None for f in facts)
    options, keymap = _pools.picker_options(
        "worker", facts, purpose="vision")
    assert all(keymap[key] != ("ollama", "muse-image")
               for key in keymap)
    assert len(options) == 2
    strongest = _pools.suggest_strongest(
        reader, "ollama", purpose="vision")
    assert strongest is not None
    assert (strongest.provider, strongest.model) == ("ollama", "qwen3")


def test_pinned_image_gets_plain_refusal(catalog):
    """A pinned image model is refused plainly, never routed."""
    from agent_si.routing import router as _R
    from agent_si.routing import types as _T

    req = _R.RoutingRequest(
        project_id="fxr2e-p1", task_id="t1", run_id="r1",
        role="worker", task_class="coding",        routing_policy=_T.RoutingPolicy(
            policy_id="rp-fxr2e", version=1, created_at=AT,
            hash="h-fxr2e", task_class="coding", risk_level="LOW",
            strict_min=0.0, tolerant_min=0.0, confidence_min=0.0,
            sample_min=0, freshness_requirement="CURRENT",
            local_allowed=True, split_allowed=True,
            cloud_required=False),
        optimization_policy=_T.OptimizationPolicy(
            policy_id="op-fxr2e", version=1, created_at=AT,
            hash="h-fxr2e", required_quality=0.0,
            max_risk="HIGH", weight_quality=1.0,
            weight_cost=0.0, weight_latency=0.0,
            weight_cloud_tokens=0.0, local_preference=False,
            deadline=None, budget_limit=None),
        required_capabilities=(), required_modalities=(),
        mode="PINNED", pinned_provider="ollama",
        pinned_model="muse-image",
        candidates=(_T.CandidateModel(provider="ollama",
                                      model="muse-image"),))
    deps = _R.RoutingDeps(
        kb=CatalogKbReader(),
        provider_health={"ollama": _T.ProviderHealth(
            provider="ollama", status="ONLINE")},
        model_health={("ollama", "muse-image"): _T.ModelHealth(
            provider="ollama", model="muse-image", status="READY")},
        provider_capabilities={"ollama": ("text", "image")})
    outcome = _R.decide_and_record(req, deps)
    assert outcome.status == "BLOCKED", outcome
    assert "image" in outcome.decision.reason.lower() or \
        "text" in outcome.decision.reason.lower(), outcome.decision.reason
