"""Choice-point reads over the model KB.

Model ids pass through verbatim: no case folding, no trimming, no
shortening. Every choice point marks rows outside the shipped base with
the same not-in-base mark. AUTO shortlists only connected providers;
unconnected providers are listed as excluded, never read for choice.
"""

from __future__ import annotations

import copy
import json
import re
from typing import TYPE_CHECKING, List, Tuple

from agent_si.model_kb import kb
from agent_si.model_kb import updater

if TYPE_CHECKING:
    from agent_si.routing.interface import ModelContracts

IN_BASE = "in-base"
NOT_IN_BASE = "not-in-base"


def find_row(catalog, provider_id, model_id):
    """Exact match only; returns the row dict or None."""
    for row in catalog.get("models", []):
        if row.get("provider_id") == provider_id and \
                row.get("model_id") == model_id:
            return row
    return None


def lookup(catalog, provider_id, model_id):
    """Single PINNED-style read with the base-membership mark."""
    row = find_row(catalog, provider_id, model_id)
    return {"provider_id": provider_id,
            "model_id": model_id,
            "found": row is not None,
            "kb_status": IN_BASE if row is not None else NOT_IN_BASE,
            "row": row}


def _snapshot_index(snapshots):
    index = {}
    if isinstance(snapshots, dict):
        items = list(snapshots.items())
    elif isinstance(snapshots, (list, tuple)):
        items = [((snap.get("provider_id"), snap.get("model_id")), snap)
                 for snap in snapshots if isinstance(snap, dict)]
    else:
        return index
    for pair, snap in items:
        if not isinstance(snap, dict):
            continue
        known = index.get(pair)
        if known is None or str(snap.get("effective_at", "")) >= str(
                known.get("effective_at", "")):
            index[pair] = snap
    return index


def _tag_index(local_tags):
    if isinstance(local_tags, dict):
        return {(pair[0], pair[1]): list(tags)
                for pair, tags in local_tags.items()}
    return {}


def bridge(catalog, provider_id, model_id, snapshots=None, local_tags=None):
    """Bridge exact ids to the KB row plus dated snapshot plus tags."""
    row = find_row(catalog, provider_id, model_id)
    snap = _snapshot_index(snapshots).get((provider_id, model_id))
    tags = _tag_index(local_tags).get((provider_id, model_id), [])
    return {"provider_id": provider_id,
            "model_id": model_id,
            "kb_status": IN_BASE if row is not None else NOT_IN_BASE,
            "row": row,
            "pricing_snapshot": snap,
            "local_tags": list(tags)}


def candidates_for_auto(catalog, connected_provider_ids,
                        snapshots=None, local_tags=None):
    """AUTO shortlist: model data is read for connected providers only."""
    connected = list(connected_provider_ids or [])
    catalog_providers = []
    for row in catalog.get("models", []):
        provider = row.get("provider_id")
        if provider not in catalog_providers:
            catalog_providers.append(provider)
    candidates = []
    for provider_id in connected:
        for row in catalog.get("models", []):
            if row.get("provider_id") != provider_id:
                continue
            candidates.append(
                bridge(catalog, provider_id, row.get("model_id"),
                       snapshots=snapshots, local_tags=local_tags))
    excluded = [p for p in catalog_providers if p not in connected]
    if candidates:
        reason = "AUTO shortlist from connected providers only"
    elif connected:
        reason = "connected providers hold no KB rows"
    else:
        reason = "no provider connected; AUTO is blocked with this reason"
    return {"candidates": candidates,
            "excluded_unconnected": sorted(excluded),
            "reason": reason}


def resolve_pool(catalog, entries, connected_provider_ids,
                 snapshots=None, local_tags=None):
    """Resolve one pool entry per item; every entry carries the mark."""
    connected = set(connected_provider_ids or [])
    resolutions = []
    for entry in entries or []:
        provider_id = entry.get("provider_id")
        model_id = entry.get("model_id")
        item = bridge(catalog, provider_id, model_id,
                      snapshots=snapshots, local_tags=local_tags)
        item["connected"] = provider_id in connected
        resolutions.append(item)
    return {"resolutions": resolutions}


def read_back(catalog, provider_id, model_id, connected_provider_ids,
              snapshots=None, local_tags=None):
    """PINNED read-back: binding plus base mark plus connection state."""
    item = bridge(catalog, provider_id, model_id,
                  snapshots=snapshots, local_tags=local_tags)
    item["mode"] = "PINNED"
    item["connected"] = provider_id in set(connected_provider_ids or [])
    item["found"] = item["row"] is not None
    return item


# --- one-click offer (K04_INTERFACE section 3.4) -------------------------------
#
# RULE (explicit; KB row fields only; no invented numbers):
# eligibility: provider connected AND modalities value affirmatively
# includes "text" AND mentions none of image/audio/embedding. Modalities
# UNKNOWN (or empty, or without "text") is not-proven-text and is always
# excluded: a row that cannot prove it is a text model is never offered.
# strength: lexicographic tuple of (tool_calling affirmative,
# reasoning affirmative, distinct coding-keyword hits across best_for
# plus purpose, cheaper cost_tier first). No weights, no scores from
# outside the KB. Full ties keep the first row in catalog order;
# model_id is never a sort key or deciding key, so alphabetical order
# cannot decide. UNKNOWN (or unrecognized) cost_tier counts as expensive
# and never wins a cost tiebreak.

_TOKEN_SPLIT = re.compile("[^a-z0-9]+")


def _split_words(text):
    """Lowercase alphanumeric tokens of a KB text value."""
    return [tok for tok in _TOKEN_SPLIT.split(text.lower()) if tok]


_NON_TEXT_MODALITIES = ("image", "audio", "embedding")

_AFFIRMATIVE_TOKENS = frozenset([
    "yes", "true", "supported", "supports", "support", "supporting",
    "native", "full", "strong", "available", "enabled", "advanced",
    "excellent",
])

_NEGATIVE_TOKENS = frozenset([
    "no", "not", "none", "never", "without", "unsupported",
    "unavailable", "unknown", "false", "nil", "null", "limited",
    "partial", "weak", "basic", "experimental",
])

_CODING_TOKENS = frozenset([
    "code", "codes", "coding", "program", "programs", "programming",
    "software", "develop", "developer", "developers", "developing",
    "debug", "debugging", "tool", "tools", "agent", "agents", "agentic",
    "engineer", "engineers", "engineering",
])

_CHEAP_TOKENS = frozenset([
    "low", "lowest", "cheap", "cheapest", "budget", "free", "1",
])

_MID_TOKENS = frozenset([
    "medium", "mid", "moderate", "standard", "2",
])


def _field_text(row, name):
    """Raw KB field value as text; lists joined, None reads as empty."""
    try:
        value = row.get("fields", {}).get(name, {}).get("value", "")
    except AttributeError:
        return ""
    if isinstance(value, (list, tuple)):
        return " ".join(str(item) for item in value)
    if value is None:
        return ""
    return str(value)


def _modalities_eligible(row):
    """True only when the KB modalities value proves a text-only model."""
    text = _field_text(row, "modalities").strip().lower()
    if not text or text == "unknown":
        return False
    if "text" not in text:
        return False
    return not any(mark in text for mark in _NON_TEXT_MODALITIES)


def _affirmative(text):
    """True when KB text affirms a capability; negatives/UNKNOWN False."""
    tokens = _split_words(text)
    if not tokens:
        return False
    if any(tok in _NEGATIVE_TOKENS for tok in tokens):
        return False
    return any(tok in _AFFIRMATIVE_TOKENS for tok in tokens)


def _coding_hits(row):
    """Distinct coding-keyword hits across best_for plus purpose."""
    tokens = set(_split_words(
        _field_text(row, "best_for") + " " + _field_text(row, "purpose")))
    return len(tokens & _CODING_TOKENS)


def _cost_rank(row):
    """0 cheap, 1 mid, 2 costly; UNKNOWN/unrecognized counts as costly."""
    tokens = set(_split_words(_field_text(row, "cost_tier")))
    if tokens & _CHEAP_TOKENS:
        return 0
    if tokens & _MID_TOKENS:
        return 1
    return 2


def _strength_key(row):
    """Lexicographic KB-only strength; bigger tuple wins, no weights."""
    tool = 1 if _affirmative(_field_text(row, "tool_calling")) else 0
    reason = 1 if _affirmative(_field_text(row, "reasoning")) else 0
    return (tool, reason, _coding_hits(row), -_cost_rank(row))


def offer_one_click(catalog, connected_provider_ids,
                    snapshots=None, local_tags=None):
    """Offer the strongest connected text/tools/coding model (one-click).

    Reads model data for connected providers only; unconnected
    providers are listed as excluded, never read for choice. Rows whose
    modalities cannot prove text-only are skipped. Returns {"offer":
    bridged row or None, "excluded_unconnected": [...], "reason": str}.
    """
    connected = set(connected_provider_ids or [])
    catalog_providers = []
    for row in catalog.get("models", []):
        provider = row.get("provider_id")
        if provider not in catalog_providers:
            catalog_providers.append(provider)
    best_row = None
    best_key = None
    for row in catalog.get("models", []):
        if row.get("provider_id") not in connected:
            continue
        if not _modalities_eligible(row):
            continue
        key = _strength_key(row)
        if best_key is None or key > best_key:
            best_key = key
            best_row = row
    excluded = sorted(p for p in catalog_providers if p not in connected)
    if best_row is None:
        if not connected:
            reason = ("no provider connected; one-click is blocked "
                      "with this reason")
        else:
            reason = ("no eligible text/tools/coding model among "
                      "connected providers")
        return {"offer": None, "excluded_unconnected": excluded,
                "reason": reason}
    offer = bridge(catalog, best_row.get("provider_id"),
                   best_row.get("model_id"), snapshots=snapshots,
                   local_tags=local_tags)
    offer["connected"] = True
    return {"offer": offer,
            "excluded_unconnected": excluded,
            "reason": ("one-click offer: strongest connected "
                       "text/tools/coding model by tool_calling, "
                       "reasoning, coding best_for/purpose, then "
                       "cheaper cost_tier")}


__all__ = [
    "IN_BASE",
    "NOT_IN_BASE",
    "STAGED_MANIFEST_SOURCES",
    "STAGED_MODEL_COUNT",
    "STAGED_PROVIDER_COUNT",
    "STAGED_PROVIDER_ENVELOPES",
    "STAGED_SECTIONS_RETRIEVED_AT",
    "STAGED_SECTION_ENVELOPE",
    "bridge",
    "build_staged_base",
    "candidates_for_auto",
    "find_row",
    "import_staged_sections",
    "lookup",
    "offer_one_click",
    "propose_update",
    "read_back",
    "read_kb",
    "resolve_exact_id",
    "resolve_pool",
    "staged_section_rows",
]




# --- K04KBIMPORT staged section import (retrieved 2026-10-11) ---
#
# Data below is quoted verbatim from the 16 staged provider
# section files (DIRECTOR inbox MODEL_KB sections bundle): every
# value, source URL and retrieval date comes from its section
# file; a section datum with no KB field has no row home and
# stays UNKNOWN (see mapping notes in the task return). Price
# numbers are per-1M-tokens exactly as the pricing pages state
# them; no unit conversion is applied. Proposal envelopes are
# the provider docs base when that base is allowlisted, else
# STAGED_SECTION_ENVELOPE (the frozen allowlist has no entry
# for 12 of the 16 staged providers); per-field change sources
# always carry the true section-cited URL.
STAGED_SECTIONS_RETRIEVED_AT = "2026-10-11"
STAGED_SECTION_ENVELOPE = "https://platform.openai.com/docs"
STAGED_MODEL_COUNT = 132
STAGED_PROVIDER_COUNT = 16
STAGED_MANIFEST_SOURCES = [
    "https://ai.google.dev/gemini-api/docs/deprecations",
    "https://ai.google.dev/gemini-api/docs/models",
    "https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flas"
    "h",
    "https://ai.google.dev/gemini-api/docs/models/gemini-2.5-pro",
    "https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flas"
    "h-lite",
    "https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-"
    "preview",
    "https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flas"
    "h-lite",
    "https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flas"
    "h",
    "https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flas"
    "h",
    "https://ai.google.dev/gemini-api/docs/models/gemini-embeddin"
    "g-001",
    "https://ai.google.dev/gemini-api/docs/pricing",
    "https://ai.meta.com/blog/llama-4-multimodal-intelligence",
    "https://api-docs.deepseek.com/guides/thinking_mode",
    "https://api-docs.deepseek.com/guides/vision",
    "https://api-docs.deepseek.com/quick_start/pricing",
    "https://api-docs.deepseek.com/updates",
    "https://aws.amazon.com/bedrock/pricing/",
    "https://azure.microsoft.com/en-us/pricing/details/azure-open"
    "ai/",
    "https://cohere.com/pricing",
    "https://console.groq.com/docs/deprecations",
    "https://console.groq.com/docs/model/llama-3.1-8b-instant",
    "https://console.groq.com/docs/model/llama-3.3-70b-versatile",
    "https://console.groq.com/docs/model/openai/gpt-oss-120b",
    "https://console.groq.com/docs/model/openai/gpt-oss-20b",
    "https://console.groq.com/docs/model/openai/gpt-oss-safeguard"
    "-20b",
    "https://console.groq.com/docs/model/qwen/qwen3.8-27b",
    "https://console.groq.com/docs/model/whisper-large-v3-turbo",
    "https://console.groq.com/docs/models",
    "https://dev.meta.ai/docs/models",
    "https://dev.meta.ai/docs/muse-glimmer",
    "https://dev.meta.ai/docs/pricing-rate-limits",
    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
    "ard-amazon-nova-pro.html",
    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
    "ard-anthropic-claude-fable-5-1.html",
    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
    "ard-anthropic-claude-haiku-4-5.html",
    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
    "ard-anthropic-claude-haiku-5-5.html",
    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
    "ard-anthropic-claude-opus-4-8.html",
    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
    "ard-anthropic-claude-opus-5-5.html",
    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
    "ard-anthropic-claude-opus-5.html",
    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
    "ard-anthropic-claude-sonnet-5-5.html",
    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
    "ard-anthropic-claude-sonnet-5.html",
    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
    "ard-meta-llama-3-3-70b-instruct.html",
    "https://docs.cohere.com/docs/command-a",
    "https://docs.cohere.com/docs/command-a-reasoning",
    "https://docs.cohere.com/docs/command-a-vision",
    "https://docs.cohere.com/docs/how-does-cohere-pricing-work",
    "https://docs.cohere.com/docs/models",
    "https://docs.cohere.com/docs/reasoning",
    "https://docs.cohere.com/docs/structured-outputs",
    "https://docs.cohere.com/docs/tool-use",
    "https://docs.fireworks.ai/serverless/pricing",
    "https://docs.mistral.ai/getting-started/models/",
    "https://docs.mistral.ai/inference/pricing/",
    "https://docs.mistral.ai/models/codestral-25-08",
    "https://docs.mistral.ai/models/codestral-embed-25-05",
    "https://docs.mistral.ai/models/ministral-3-8b-25-12",
    "https://docs.mistral.ai/models/mistral-large-3-25-12",
    "https://docs.mistral.ai/models/mistral-large-4-0",
    "https://docs.mistral.ai/models/mistral-medium-3-5-26-04",
    "https://docs.mistral.ai/models/mistral-small-4-0-26-03",
    "https://docs.mistral.ai/models/ocr-4-1",
    "https://docs.perplexity.ai/docs/agent-api/migrate-from-sonar"
    "/overview",
    "https://docs.perplexity.ai/docs/resources/changelog",
    "https://docs.perplexity.ai/getting-started/models",
    "https://docs.perplexity.ai/getting-started/pricing",
    "https://docs.together.ai/docs/inference/chat/reasoning",
    "https://docs.together.ai/docs/serverless-models",
    "https://docs.x.ai/docs/models",
    "https://docs.x.ai/docs/models/grok-4.3",
    "https://docs.x.ai/docs/models/grok-4.5",
    "https://docs.x.ai/docs/models/grok-4.6",
    "https://docs.x.ai/docs/models/grok-4.7",
    "https://docs.x.ai/docs/models/grok-build-0.1",
    "https://docs.x.ai/docs/models/grok-imagine-image-2.0",
    "https://docs.x.ai/docs/pricing",
    "https://fireworks.ai/models",
    "https://fireworks.ai/models/deepseek-ai/deepseek-v4p1-flash",
    "https://fireworks.ai/models/fireworks/glm-5p3",
    "https://fireworks.ai/models/fireworks/glm-5p3-flash",
    "https://fireworks.ai/models/fireworks/gpt-oss-120b",
    "https://fireworks.ai/models/fireworks/kimi-k3",
    "https://fireworks.ai/models/fireworks/minimax-m3",
    "https://fireworks.ai/models/fireworks/nemotron-lightning-3p5"
    "-30b-a3b",
    "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
    "ncepts/models",
    "https://ollama.com/library/deepseek-r1",
    "https://ollama.com/library/gemma2",
    "https://ollama.com/library/gemma3",
    "https://ollama.com/library/llama3.1",
    "https://ollama.com/library/mistral",
    "https://ollama.com/library/mixtral",
    "https://ollama.com/library/phi3",
    "https://ollama.com/library/phi4",
    "https://ollama.com/library/qwen2.5",
    "https://ollama.com/library/qwen3",
    "https://openrouter.ai/api/v1/models",
    "https://openrouter.ai/deepseek/deepseek-v4-flash-0731",
    "https://openrouter.ai/google/gemma-4-12b-it",
    "https://openrouter.ai/meta/muse-spark-1.3",
    "https://openrouter.ai/microsoft/mai-code-1-flash",
    "https://openrouter.ai/mistral/mistral-medium-latest",
    "https://openrouter.ai/qwen/qwen3.8-27b",
    "https://platform.claude.com/docs/en/about-claude/model-depre"
    "cations",
    "https://platform.claude.com/docs/en/about-claude/pricing",
    "https://platform.claude.com/docs/en/models/fable-5-1/overvie"
    "w",
    "https://platform.claude.com/docs/en/models/fable-5/overview",
    "https://platform.claude.com/docs/en/models/haiku-4-5/overvie"
    "w",
    "https://platform.claude.com/docs/en/models/haiku-5-5/overvie"
    "w",
    "https://platform.claude.com/docs/en/models/opus-4-6/overview",
    "https://platform.claude.com/docs/en/models/opus-4-7/overview",
    "https://platform.claude.com/docs/en/models/opus-4-8/overview",
    "https://platform.claude.com/docs/en/models/opus-5-5/overview",
    "https://platform.claude.com/docs/en/models/opus-5/overview",
    "https://platform.claude.com/docs/en/models/overview",
    "https://platform.claude.com/docs/en/models/sonnet-4-6/overvi"
    "ew",
    "https://platform.claude.com/docs/en/models/sonnet-5-5/overvi"
    "ew",
    "https://platform.claude.com/docs/en/models/sonnet-5/overview",
    "https://platform.openai.com/docs/deprecations",
    "https://platform.openai.com/docs/guides/embeddings",
    "https://platform.openai.com/docs/models/gpt-4o",
    "https://platform.openai.com/docs/models/gpt-4o-mini",
    "https://platform.openai.com/docs/models/gpt-4o-mini-tts",
    "https://platform.openai.com/docs/models/gpt-5.4",
    "https://platform.openai.com/docs/models/gpt-5.6-sol",
    "https://platform.openai.com/docs/models/gpt-6-astra",
    "https://platform.openai.com/docs/models/gpt-6-luna",
    "https://platform.openai.com/docs/models/gpt-6.1-sol",
    "https://platform.openai.com/docs/models/gpt-transcribe",
    "https://platform.openai.com/docs/models/o3",
    "https://platform.openai.com/docs/models/o4-mini",
    "https://platform.openai.com/docs/pricing",
    "https://www.together.ai/models/deepseek-v4-pro-0813",
    "https://www.together.ai/models/glm-5-3",
    "https://www.together.ai/models/glm-5-3-flash",
    "https://www.together.ai/models/gpt-oss-120b",
    "https://www.together.ai/models/kimi-k3",
    "https://www.together.ai/models/minimax-m3",
    "https://www.together.ai/models/muse-glimmer",
    "https://www.together.ai/pricing",
    "https://x.ai/news/grok-4",
]
STAGED_PROVIDER_ENVELOPES = {
    "anthropic": "https://platform.openai.com/docs",
    "azure-openai": "https://platform.openai.com/docs",
    "bedrock": "https://platform.openai.com/docs",
    "cohere": "https://platform.openai.com/docs",
    "deepseek": "https://platform.openai.com/docs",
    "fireworks": "https://platform.openai.com/docs",
    "google": "https://platform.openai.com/docs",
    "groq": "https://console.groq.com/docs/model/openai/gpt-oss-120b",
    "local": "https://platform.openai.com/docs",
    "meta": "https://platform.openai.com/docs",
    "mistral": "https://docs.mistral.ai/models/mistral-large-4-0",
    "openai": "https://platform.openai.com/docs/models/gpt-6-astra",
    "openrouter": "https://platform.openai.com/docs",
    "perplexity": "https://platform.openai.com/docs",
    "together": "https://platform.openai.com/docs",
    "xai": "https://docs.x.ai/docs/models/grok-4.7",
}
_STAGED_SECTION_ROWS = {
    "anthropic": [
        ("claude-fable-5-1", {
            "avoid_for": (
                "less suited to latency-sensitive high-volume routing, "
                "tiny-budget classification. Task fit: agents: best; coding: "
                "best; reasoning: best; routing: avoid.",
                "https://platform.claude.com/docs/en/models/fable-5-1/overvie"
                "w"),
            "best_for": (
                "suited to long-horizon agents, ambitious coding, enterprise "
                "knowledge work. Task fit: agents: best; coding: best; "
                "reasoning: best; routing: avoid.",
                "https://platform.claude.com/docs/en/models/fable-5-1/overvie"
                "w"),
            "context_window": (
                1000000,
                "https://platform.claude.com/docs/en/models/fable-5-1/overvie"
                "w"),
            "cost_tier": (
                "strong-reasoning",
                "https://platform.claude.com/docs/en/models/fable-5-1/overvie"
                "w"),
            "currency": (
                "USD",
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "input_token_price": (
                10,
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "knowledge_cutoff": (
                "2026-06",
                "https://platform.claude.com/docs/en/models/fable-5-1/overvie"
                "w"),
            "max_output": (
                128000,
                "https://platform.claude.com/docs/en/models/fable-5-1/overvie"
                "w"),
            "modalities": (
                [
                    "text-in",
                    "image-in",
                    "text-out",
                ],
                "https://platform.claude.com/docs/en/models/fable-5-1/overvie"
                "w"),
            "output_token_price": (
                50,
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "reasoning": (
                True,
                "https://platform.claude.com/docs/en/models/fable-5-1/overvie"
                "w"),
            "role_notes": (
                "auditor role: use for deep audit of agentic plans; director "
                "role: reserve for hardest plans; manager role: decompose "
                "before delegating; worker role: overkill for simple edits.",
                "https://platform.claude.com/docs/en/models/fable-5-1/overvie"
                "w"),
            "source_links": (
                [
                    "https://platform.claude.com/docs/en/about-claude/model-depre"
                    "cations",
                    "https://platform.claude.com/docs/en/about-claude/pricing",
                    "https://platform.claude.com/docs/en/models/fable-5-1/overvie"
                    "w",
                    "https://platform.claude.com/docs/en/models/fable-5/overview",
                    "https://platform.claude.com/docs/en/models/haiku-4-5/overvie"
                    "w",
                    "https://platform.claude.com/docs/en/models/haiku-5-5/overvie"
                    "w",
                    "https://platform.claude.com/docs/en/models/opus-4-6/overview",
                    "https://platform.claude.com/docs/en/models/opus-4-7/overview",
                    "https://platform.claude.com/docs/en/models/opus-4-8/overview",
                    "https://platform.claude.com/docs/en/models/opus-5-5/overview",
                    "https://platform.claude.com/docs/en/models/opus-5/overview",
                    "https://platform.claude.com/docs/en/models/overview",
                    "https://platform.claude.com/docs/en/models/sonnet-4-6/overvi"
                    "ew",
                    "https://platform.claude.com/docs/en/models/sonnet-5-5/overvi"
                    "ew",
                    "https://platform.claude.com/docs/en/models/sonnet-5/overview",
                ],
                "https://platform.claude.com/docs/en/models/fable-5-1/overvie"
                "w"),
            "strengths": (
                "reads as strong on frontier reasoning for demanding tasks, "
                "long-horizon agentic work, 1M context window.",
                "https://platform.claude.com/docs/en/models/fable-5-1/overvie"
                "w"),
            "tool_calling": (
                True,
                "https://platform.claude.com/docs/en/models/overview"),
            "weaknesses": (
                "watch out for highest price tier, slower comparative "
                "latency, overkill for simple tasks.",
                "https://platform.claude.com/docs/en/models/fable-5-1/overvie"
                "w"),
        }),
        ("claude-opus-5-5", {
            "avoid_for": (
                "less suited to high-volume cheap routing, tiny-budget "
                "tasks. Task fit: agents: best; coding: best; reasoning: "
                "best; routing: ok.",
                "https://platform.claude.com/docs/en/models/opus-5-5/overview"),
            "best_for": (
                "suited to long-running agentic coding, knowledge work, "
                "complex reasoning at lower cost than Fable. Task fit: "
                "agents: best; coding: best; reasoning: best; routing: ok.",
                "https://platform.claude.com/docs/en/models/opus-5-5/overview"),
            "context_window": (
                1000000,
                "https://platform.claude.com/docs/en/models/opus-5-5/overview"),
            "cost_tier": (
                "strong-reasoning",
                "https://platform.claude.com/docs/en/models/opus-5-5/overview"),
            "currency": (
                "USD",
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "input_token_price": (
                4,
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "knowledge_cutoff": (
                "2026-06",
                "https://platform.claude.com/docs/en/models/opus-5-5/overview"),
            "max_output": (
                128000,
                "https://platform.claude.com/docs/en/models/opus-5-5/overview"),
            "modalities": (
                [
                    "text-in",
                    "image-in",
                    "text-out",
                ],
                "https://platform.claude.com/docs/en/models/opus-5-5/overview"),
            "output_token_price": (
                20,
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "reasoning": (
                True,
                "https://platform.claude.com/docs/en/models/opus-5-5/overview"),
            "role_notes": (
                "auditor role: strong verifier for code and plans; director "
                "role: default for most hard workloads; manager role: good "
                "planner and reviewer; worker role: fine for complex "
                "implementation.",
                "https://platform.claude.com/docs/en/models/opus-5-5/overview"),
            "source_links": (
                [
                    "https://platform.claude.com/docs/en/about-claude/model-depre"
                    "cations",
                    "https://platform.claude.com/docs/en/about-claude/pricing",
                    "https://platform.claude.com/docs/en/models/fable-5-1/overvie"
                    "w",
                    "https://platform.claude.com/docs/en/models/fable-5/overview",
                    "https://platform.claude.com/docs/en/models/haiku-4-5/overvie"
                    "w",
                    "https://platform.claude.com/docs/en/models/haiku-5-5/overvie"
                    "w",
                    "https://platform.claude.com/docs/en/models/opus-4-6/overview",
                    "https://platform.claude.com/docs/en/models/opus-4-7/overview",
                    "https://platform.claude.com/docs/en/models/opus-4-8/overview",
                    "https://platform.claude.com/docs/en/models/opus-5-5/overview",
                    "https://platform.claude.com/docs/en/models/opus-5/overview",
                    "https://platform.claude.com/docs/en/models/overview",
                    "https://platform.claude.com/docs/en/models/sonnet-4-6/overvi"
                    "ew",
                    "https://platform.claude.com/docs/en/models/sonnet-5-5/overvi"
                    "ew",
                    "https://platform.claude.com/docs/en/models/sonnet-5/overview",
                ],
                "https://platform.claude.com/docs/en/models/fable-5-1/overvie"
                "w"),
            "strengths": (
                "reads as strong on most capable Opus per model page, coding "
                "and knowledge work, 1M context at standard pricing.",
                "https://platform.claude.com/docs/en/models/opus-5-5/overview"),
            "tool_calling": (
                True,
                "https://platform.claude.com/docs/en/models/overview"),
            "weaknesses": (
                "watch out for costs 2x Sonnet 5.5, moderate latency, newer "
                "tokenizer raises token counts ~30%.",
                "https://platform.claude.com/docs/en/models/opus-5-5/overview"),
        }),
        ("claude-sonnet-5-5", {
            "avoid_for": (
                "less suited to deepest frontier reasoning, cheapest bulk "
                "classification. Task fit: agents: best; coding: best; "
                "reasoning: good; routing: good.",
                "https://platform.claude.com/docs/en/models/sonnet-5-5/overvi"
                "ew"),
            "best_for": (
                "suited to production coding, agents at scale, speed plus "
                "intelligence balance. Task fit: agents: best; coding: best; "
                "reasoning: good; routing: good.",
                "https://platform.claude.com/docs/en/models/sonnet-5-5/overvi"
                "ew"),
            "context_window": (
                1000000,
                "https://platform.claude.com/docs/en/models/sonnet-5-5/overvi"
                "ew"),
            "cost_tier": (
                "balanced",
                "https://platform.claude.com/docs/en/models/sonnet-5-5/overvi"
                "ew"),
            "currency": (
                "USD",
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "input_token_price": (
                2,
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "knowledge_cutoff": (
                "2026-06",
                "https://platform.claude.com/docs/en/models/sonnet-5-5/overvi"
                "ew"),
            "max_output": (
                128000,
                "https://platform.claude.com/docs/en/models/sonnet-5-5/overvi"
                "ew"),
            "modalities": (
                [
                    "text-in",
                    "image-in",
                    "text-out",
                ],
                "https://platform.claude.com/docs/en/models/sonnet-5-5/overvi"
                "ew"),
            "output_token_price": (
                10,
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "reasoning": (
                True,
                "https://platform.claude.com/docs/en/models/sonnet-5-5/overvi"
                "ew"),
            "role_notes": (
                "auditor role: fast second reviewer; director role: default "
                "worker fleet model; manager role: plan and delegate "
                "efficiently; worker role: best default for implementation.",
                "https://platform.claude.com/docs/en/models/sonnet-5-5/overvi"
                "ew"),
            "source_links": (
                [
                    "https://platform.claude.com/docs/en/about-claude/model-depre"
                    "cations",
                    "https://platform.claude.com/docs/en/about-claude/pricing",
                    "https://platform.claude.com/docs/en/models/fable-5-1/overvie"
                    "w",
                    "https://platform.claude.com/docs/en/models/fable-5/overview",
                    "https://platform.claude.com/docs/en/models/haiku-4-5/overvie"
                    "w",
                    "https://platform.claude.com/docs/en/models/haiku-5-5/overvie"
                    "w",
                    "https://platform.claude.com/docs/en/models/opus-4-6/overview",
                    "https://platform.claude.com/docs/en/models/opus-4-7/overview",
                    "https://platform.claude.com/docs/en/models/opus-4-8/overview",
                    "https://platform.claude.com/docs/en/models/opus-5-5/overview",
                    "https://platform.claude.com/docs/en/models/opus-5/overview",
                    "https://platform.claude.com/docs/en/models/overview",
                    "https://platform.claude.com/docs/en/models/sonnet-4-6/overvi"
                    "ew",
                    "https://platform.claude.com/docs/en/models/sonnet-5-5/overvi"
                    "ew",
                    "https://platform.claude.com/docs/en/models/sonnet-5/overview",
                ],
                "https://platform.claude.com/docs/en/models/fable-5-1/overvie"
                "w"),
            "strengths": (
                "reads as strong on best speed-intelligence combination, "
                "leap over Sonnet 5 per docs, low cost per task.",
                "https://platform.claude.com/docs/en/models/sonnet-5-5/overvi"
                "ew"),
            "tool_calling": (
                True,
                "https://platform.claude.com/docs/en/models/overview"),
            "weaknesses": (
                "watch out for below Opus/Fable on hardest reasoning, large "
                "prompts still cost, UNKNOWN benchmark deltas.",
                "https://platform.claude.com/docs/en/models/sonnet-5-5/overvi"
                "ew"),
        }),
        ("claude-haiku-5-5", {
            "avoid_for": (
                "less suited to frontier reasoning, very long outputs beyond "
                "128K sync. Task fit: agents: good; coding: good; reasoning: "
                "ok; routing: best.",
                "https://platform.claude.com/docs/en/models/haiku-5-5/overvie"
                "w"),
            "best_for": (
                "suited to classification, extraction, routing, high-volume "
                "latency-sensitive tasks. Task fit: agents: good; coding: "
                "good; reasoning: ok; routing: best.",
                "https://platform.claude.com/docs/en/models/haiku-5-5/overvie"
                "w"),
            "context_window": (
                1000000,
                "https://platform.claude.com/docs/en/models/haiku-5-5/overvie"
                "w"),
            "cost_tier": (
                "cheap-fast",
                "https://platform.claude.com/docs/en/models/haiku-5-5/overvie"
                "w"),
            "currency": (
                "USD",
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "input_token_price": (
                0.1,
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "knowledge_cutoff": (
                "2026-06",
                "https://platform.claude.com/docs/en/models/haiku-5-5/overvie"
                "w"),
            "max_output": (
                128000,
                "https://platform.claude.com/docs/en/models/haiku-5-5/overvie"
                "w"),
            "modalities": (
                [
                    "text-in",
                    "image-in",
                    "text-out",
                ],
                "https://platform.claude.com/docs/en/models/haiku-5-5/overvie"
                "w"),
            "output_token_price": (
                0.5,
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "reasoning": (
                True,
                "https://platform.claude.com/docs/en/models/haiku-5-5/overvie"
                "w"),
            "role_notes": (
                "auditor role: triage only, not final audit; director role: "
                "bulk triage and routing; manager role: fan-out cheap "
                "subtasks; worker role: fast simple edits and extracts.",
                "https://platform.claude.com/docs/en/models/haiku-5-5/overvie"
                "w"),
            "source_links": (
                [
                    "https://platform.claude.com/docs/en/about-claude/model-depre"
                    "cations",
                    "https://platform.claude.com/docs/en/about-claude/pricing",
                    "https://platform.claude.com/docs/en/models/fable-5-1/overvie"
                    "w",
                    "https://platform.claude.com/docs/en/models/fable-5/overview",
                    "https://platform.claude.com/docs/en/models/haiku-4-5/overvie"
                    "w",
                    "https://platform.claude.com/docs/en/models/haiku-5-5/overvie"
                    "w",
                    "https://platform.claude.com/docs/en/models/opus-4-6/overview",
                    "https://platform.claude.com/docs/en/models/opus-4-7/overview",
                    "https://platform.claude.com/docs/en/models/opus-4-8/overview",
                    "https://platform.claude.com/docs/en/models/opus-5-5/overview",
                    "https://platform.claude.com/docs/en/models/opus-5/overview",
                    "https://platform.claude.com/docs/en/models/overview",
                    "https://platform.claude.com/docs/en/models/sonnet-4-6/overvi"
                    "ew",
                    "https://platform.claude.com/docs/en/models/sonnet-5-5/overvi"
                    "ew",
                    "https://platform.claude.com/docs/en/models/sonnet-5/overview",
                ],
                "https://platform.claude.com/docs/en/models/fable-5-1/overvie"
                "w"),
            "strengths": (
                "reads as strong on fastest comparative latency, cheapest "
                "current Claude, step up over Haiku 4.5 on agents.",
                "https://platform.claude.com/docs/en/models/haiku-5-5/overvie"
                "w"),
            "tool_calling": (
                True,
                "https://platform.claude.com/docs/en/models/overview"),
            "weaknesses": (
                "watch out for prompt-length tiered pricing over 100K "
                "tokens, weaker on hardest reasoning, UNKNOWN benchmark "
                "figures.",
                "https://platform.claude.com/docs/en/models/haiku-5-5/overvie"
                "w"),
        }),
        ("claude-fable-5", {
            "avoid_for": (
                "less suited to cheap bulk routing, latency-critical paths. "
                "Task fit: agents: best; coding: best; reasoning: best; "
                "routing: avoid.",
                "https://platform.claude.com/docs/en/models/fable-5/overview"),
            "best_for": (
                "suited to complex knowledge work, sustained autonomous "
                "coding, multi-day agentic tasks. Task fit: agents: best; "
                "coding: best; reasoning: best; routing: avoid.",
                "https://platform.claude.com/docs/en/models/fable-5/overview"),
            "context_window": (
                1000000,
                "https://platform.claude.com/docs/en/models/fable-5/overview"),
            "cost_tier": (
                "strong-reasoning",
                "https://platform.claude.com/docs/en/models/fable-5/overview"),
            "currency": (
                "USD",
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "input_token_price": (
                10,
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "knowledge_cutoff": (
                "2026-01",
                "https://platform.claude.com/docs/en/models/fable-5/overview"),
            "max_output": (
                128000,
                "https://platform.claude.com/docs/en/models/fable-5/overview"),
            "modalities": (
                [
                    "text-in",
                    "image-in",
                    "text-out",
                ],
                "https://platform.claude.com/docs/en/models/fable-5/overview"),
            "output_token_price": (
                50,
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "reasoning": (
                True,
                "https://platform.claude.com/docs/en/models/fable-5/overview"),
            "role_notes": (
                "auditor role: deep review of long plans; director role: use "
                "when 5.1 unavailable; manager role: supervise long tasks; "
                "worker role: heavy implementation only.",
                "https://platform.claude.com/docs/en/models/fable-5/overview"),
            "source_links": (
                [
                    "https://platform.claude.com/docs/en/about-claude/model-depre"
                    "cations",
                    "https://platform.claude.com/docs/en/about-claude/pricing",
                    "https://platform.claude.com/docs/en/models/fable-5-1/overvie"
                    "w",
                    "https://platform.claude.com/docs/en/models/fable-5/overview",
                    "https://platform.claude.com/docs/en/models/haiku-4-5/overvie"
                    "w",
                    "https://platform.claude.com/docs/en/models/haiku-5-5/overvie"
                    "w",
                    "https://platform.claude.com/docs/en/models/opus-4-6/overview",
                    "https://platform.claude.com/docs/en/models/opus-4-7/overview",
                    "https://platform.claude.com/docs/en/models/opus-4-8/overview",
                    "https://platform.claude.com/docs/en/models/opus-5-5/overview",
                    "https://platform.claude.com/docs/en/models/opus-5/overview",
                    "https://platform.claude.com/docs/en/models/overview",
                    "https://platform.claude.com/docs/en/models/sonnet-4-6/overvi"
                    "ew",
                    "https://platform.claude.com/docs/en/models/sonnet-5-5/overvi"
                    "ew",
                    "https://platform.claude.com/docs/en/models/sonnet-5/overview",
                ],
                "https://platform.claude.com/docs/en/models/fable-5-1/overvie"
                "w"),
            "strengths": (
                "reads as strong on sustained autonomous operation, complex "
                "knowledge work, legacy active with 2027 retirement floor.",
                "https://platform.claude.com/docs/en/models/fable-5/overview"),
            "weaknesses": (
                "watch out for top price tier, superseded by Fable 5.1, "
                "slower latency.",
                "https://platform.claude.com/docs/en/models/fable-5/overview"),
        }),
        ("claude-opus-5", {
            "avoid_for": (
                "less suited to cheap bulk work, simplest routing. Task fit: "
                "agents: best; coding: best; reasoning: best; routing: ok.",
                "https://platform.claude.com/docs/en/models/opus-5/overview"),
            "best_for": (
                "suited to long-running agents, coding and professional "
                "work, pre-5.5 Opus workloads. Task fit: agents: best; "
                "coding: best; reasoning: best; routing: ok.",
                "https://platform.claude.com/docs/en/models/opus-5/overview"),
            "context_window": (
                1000000,
                "https://platform.claude.com/docs/en/models/opus-5/overview"),
            "cost_tier": (
                "strong-reasoning",
                "https://platform.claude.com/docs/en/models/opus-5/overview"),
            "currency": (
                "USD",
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "input_token_price": (
                5,
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "knowledge_cutoff": (
                "2026-05",
                "https://platform.claude.com/docs/en/models/opus-5/overview"),
            "max_output": (
                128000,
                "https://platform.claude.com/docs/en/models/opus-5/overview"),
            "modalities": (
                [
                    "text-in",
                    "image-in",
                    "text-out",
                ],
                "https://platform.claude.com/docs/en/models/opus-5/overview"),
            "output_token_price": (
                25,
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "reasoning": (
                True,
                "https://platform.claude.com/docs/en/models/opus-5/overview"),
            "role_notes": (
                "auditor role: solid verifier; director role: fallback when "
                "5.5 unavailable; manager role: reliable planner; worker "
                "role: complex builds.",
                "https://platform.claude.com/docs/en/models/opus-5/overview"),
            "source_links": (
                [
                    "https://platform.claude.com/docs/en/about-claude/model-depre"
                    "cations",
                    "https://platform.claude.com/docs/en/about-claude/pricing",
                    "https://platform.claude.com/docs/en/models/fable-5-1/overvie"
                    "w",
                    "https://platform.claude.com/docs/en/models/fable-5/overview",
                    "https://platform.claude.com/docs/en/models/haiku-4-5/overvie"
                    "w",
                    "https://platform.claude.com/docs/en/models/haiku-5-5/overvie"
                    "w",
                    "https://platform.claude.com/docs/en/models/opus-4-6/overview",
                    "https://platform.claude.com/docs/en/models/opus-4-7/overview",
                    "https://platform.claude.com/docs/en/models/opus-4-8/overview",
                    "https://platform.claude.com/docs/en/models/opus-5-5/overview",
                    "https://platform.claude.com/docs/en/models/opus-5/overview",
                    "https://platform.claude.com/docs/en/models/overview",
                    "https://platform.claude.com/docs/en/models/sonnet-4-6/overvi"
                    "ew",
                    "https://platform.claude.com/docs/en/models/sonnet-5-5/overvi"
                    "ew",
                    "https://platform.claude.com/docs/en/models/sonnet-5/overview",
                ],
                "https://platform.claude.com/docs/en/models/fable-5-1/overvie"
                "w"),
            "strengths": (
                "reads as strong on long-running agent support, coding "
                "improvements over 4.x, active with 2027 retirement floor.",
                "https://platform.claude.com/docs/en/models/opus-5/overview"),
            "tool_calling": (
                True,
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "weaknesses": (
                "watch out for 25% pricier than Opus 5.5, superseded by Opus "
                "5.5, UNKNOWN cutoff.",
                "https://platform.claude.com/docs/en/models/opus-5/overview"),
        }),
        ("claude-sonnet-5", {
            "avoid_for": (
                "less suited to frontier reasoning, cheapest routing. Task "
                "fit: agents: good; coding: best; reasoning: good; routing: "
                "good.",
                "https://platform.claude.com/docs/en/models/sonnet-5/overview"),
            "best_for": (
                "suited to coding and agents at scale, professional work, "
                "Sonnet 4.x upgrades. Task fit: agents: good; coding: best; "
                "reasoning: good; routing: good.",
                "https://platform.claude.com/docs/en/models/sonnet-5/overview"),
            "context_window": (
                1000000,
                "https://platform.claude.com/docs/en/models/sonnet-5/overview"),
            "cost_tier": (
                "balanced",
                "https://platform.claude.com/docs/en/models/sonnet-5/overview"),
            "currency": (
                "USD",
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "input_token_price": (
                2,
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "knowledge_cutoff": (
                "2026-01",
                "https://platform.claude.com/docs/en/models/sonnet-5/overview"),
            "max_output": (
                128000,
                "https://platform.claude.com/docs/en/models/sonnet-5/overview"),
            "modalities": (
                [
                    "text-in",
                    "image-in",
                    "text-out",
                ],
                "https://platform.claude.com/docs/en/models/sonnet-5/overview"),
            "output_token_price": (
                10,
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "reasoning": (
                True,
                "https://platform.claude.com/docs/en/models/sonnet-5/overview"),
            "role_notes": (
                "auditor role: quick review pass; director role: fleet "
                "default alternative; manager role: delegate at scale; "
                "worker role: general implementation.",
                "https://platform.claude.com/docs/en/models/sonnet-5/overview"),
            "source_links": (
                [
                    "https://platform.claude.com/docs/en/about-claude/model-depre"
                    "cations",
                    "https://platform.claude.com/docs/en/about-claude/pricing",
                    "https://platform.claude.com/docs/en/models/fable-5-1/overvie"
                    "w",
                    "https://platform.claude.com/docs/en/models/fable-5/overview",
                    "https://platform.claude.com/docs/en/models/haiku-4-5/overvie"
                    "w",
                    "https://platform.claude.com/docs/en/models/haiku-5-5/overvie"
                    "w",
                    "https://platform.claude.com/docs/en/models/opus-4-6/overview",
                    "https://platform.claude.com/docs/en/models/opus-4-7/overview",
                    "https://platform.claude.com/docs/en/models/opus-4-8/overview",
                    "https://platform.claude.com/docs/en/models/opus-5-5/overview",
                    "https://platform.claude.com/docs/en/models/opus-5/overview",
                    "https://platform.claude.com/docs/en/models/overview",
                    "https://platform.claude.com/docs/en/models/sonnet-4-6/overvi"
                    "ew",
                    "https://platform.claude.com/docs/en/models/sonnet-5-5/overvi"
                    "ew",
                    "https://platform.claude.com/docs/en/models/sonnet-5/overview",
                ],
                "https://platform.claude.com/docs/en/models/fable-5-1/overvie"
                "w"),
            "strengths": (
                "reads as strong on same $2/$10 as Sonnet 5.5, scales to "
                "production workloads, active with 2027 retirement floor.",
                "https://platform.claude.com/docs/en/models/sonnet-5/overview"),
            "tool_calling": (
                True,
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "weaknesses": (
                "watch out for superseded by Sonnet 5.5, UNKNOWN cutoff, "
                "UNKNOWN benchmark deltas.",
                "https://platform.claude.com/docs/en/models/sonnet-5/overview"),
        }),
        ("claude-opus-4-8", {
            "avoid_for": (
                "less suited to cheap bulk routing. Task fit: agents: best; "
                "coding: best; reasoning: best; routing: ok.",
                "https://platform.claude.com/docs/en/models/opus-4-8/overview"),
            "best_for": (
                "suited to coding and enterprise agents, deep reasoning on "
                "4.x line, Opus 4.7 and earlier upgrades. Task fit: agents: "
                "best; coding: best; reasoning: best; routing: ok.",
                "https://platform.claude.com/docs/en/models/opus-4-8/overview"),
            "context_window": (
                1000000,
                "https://platform.claude.com/docs/en/models/opus-4-8/overview"),
            "cost_tier": (
                "strong-reasoning",
                "https://platform.claude.com/docs/en/models/opus-4-8/overview"),
            "currency": (
                "USD",
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "input_token_price": (
                5,
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "knowledge_cutoff": (
                "2026-01",
                "https://platform.claude.com/docs/en/models/opus-4-8/overview"),
            "max_output": (
                128000,
                "https://platform.claude.com/docs/en/models/opus-4-8/overview"),
            "modalities": (
                [
                    "text-in",
                    "image-in",
                    "text-out",
                ],
                "https://platform.claude.com/docs/en/models/opus-4-8/overview"),
            "output_token_price": (
                25,
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "reasoning": (
                True,
                "https://platform.claude.com/docs/en/models/opus-4-8/overview"),
            "role_notes": (
                "auditor role: careful reviewer; director role: legacy "
                "fallback; manager role: plan complex work; worker role: "
                "deep implementation.",
                "https://platform.claude.com/docs/en/models/opus-4-8/overview"),
            "source_links": (
                [
                    "https://platform.claude.com/docs/en/about-claude/model-depre"
                    "cations",
                    "https://platform.claude.com/docs/en/about-claude/pricing",
                    "https://platform.claude.com/docs/en/models/fable-5-1/overvie"
                    "w",
                    "https://platform.claude.com/docs/en/models/fable-5/overview",
                    "https://platform.claude.com/docs/en/models/haiku-4-5/overvie"
                    "w",
                    "https://platform.claude.com/docs/en/models/haiku-5-5/overvie"
                    "w",
                    "https://platform.claude.com/docs/en/models/opus-4-6/overview",
                    "https://platform.claude.com/docs/en/models/opus-4-7/overview",
                    "https://platform.claude.com/docs/en/models/opus-4-8/overview",
                    "https://platform.claude.com/docs/en/models/opus-5-5/overview",
                    "https://platform.claude.com/docs/en/models/opus-5/overview",
                    "https://platform.claude.com/docs/en/models/overview",
                    "https://platform.claude.com/docs/en/models/sonnet-4-6/overvi"
                    "ew",
                    "https://platform.claude.com/docs/en/models/sonnet-5-5/overvi"
                    "ew",
                    "https://platform.claude.com/docs/en/models/sonnet-5/overview",
                ],
                "https://platform.claude.com/docs/en/models/fable-5-1/overvie"
                "w"),
            "strengths": (
                "reads as strong on optimised for coding and agents, deeper "
                "reasoning in workflows, fast mode eligible.",
                "https://platform.claude.com/docs/en/models/opus-4-8/overview"),
            "tool_calling": (
                True,
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "weaknesses": (
                "watch out for superseded by Opus 5 line, older tokenizer "
                "line, UNKNOWN cutoff.",
                "https://platform.claude.com/docs/en/models/opus-4-8/overview"),
        }),
        ("claude-opus-4-7", {
            "avoid_for": (
                "less suited to cheap bulk routing. Task fit: agents: best; "
                "coding: best; reasoning: good; routing: ok.",
                "https://platform.claude.com/docs/en/models/opus-4-7/overview"),
            "best_for": (
                "suited to coding and long-running agents, enterprise "
                "workflows, Opus 4.6 upgrades. Task fit: agents: best; "
                "coding: best; reasoning: good; routing: ok.",
                "https://platform.claude.com/docs/en/models/opus-4-7/overview"),
            "context_window": (
                1000000,
                "https://platform.claude.com/docs/en/models/opus-4-7/overview"),
            "cost_tier": (
                "strong-reasoning",
                "https://platform.claude.com/docs/en/models/opus-4-7/overview"),
            "currency": (
                "USD",
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "input_token_price": (
                5,
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "knowledge_cutoff": (
                "2026-01",
                "https://platform.claude.com/docs/en/models/opus-4-7/overview"),
            "max_output": (
                128000,
                "https://platform.claude.com/docs/en/models/opus-4-7/overview"),
            "modalities": (
                [
                    "text-in",
                    "image-in",
                    "text-out",
                ],
                "https://platform.claude.com/docs/en/models/opus-4-7/overview"),
            "output_token_price": (
                25,
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "reasoning": (
                True,
                "https://platform.claude.com/docs/en/models/opus-4-7/overview"),
            "role_notes": (
                "auditor role: reviewer for 4.x stacks; director role: "
                "legacy fallback; manager role: plan enterprise tasks; "
                "worker role: implement large features.",
                "https://platform.claude.com/docs/en/models/opus-4-7/overview"),
            "source_links": (
                [
                    "https://platform.claude.com/docs/en/about-claude/model-depre"
                    "cations",
                    "https://platform.claude.com/docs/en/about-claude/pricing",
                    "https://platform.claude.com/docs/en/models/fable-5-1/overvie"
                    "w",
                    "https://platform.claude.com/docs/en/models/fable-5/overview",
                    "https://platform.claude.com/docs/en/models/haiku-4-5/overvie"
                    "w",
                    "https://platform.claude.com/docs/en/models/haiku-5-5/overvie"
                    "w",
                    "https://platform.claude.com/docs/en/models/opus-4-6/overview",
                    "https://platform.claude.com/docs/en/models/opus-4-7/overview",
                    "https://platform.claude.com/docs/en/models/opus-4-8/overview",
                    "https://platform.claude.com/docs/en/models/opus-5-5/overview",
                    "https://platform.claude.com/docs/en/models/opus-5/overview",
                    "https://platform.claude.com/docs/en/models/overview",
                    "https://platform.claude.com/docs/en/models/sonnet-4-6/overvi"
                    "ew",
                    "https://platform.claude.com/docs/en/models/sonnet-5-5/overvi"
                    "ew",
                    "https://platform.claude.com/docs/en/models/sonnet-5/overview",
                ],
                "https://platform.claude.com/docs/en/models/fable-5-1/overvie"
                "w"),
            "strengths": (
                "reads as strong on built for long-running agents, newer "
                "tokenizer from 4.7 line, Bedrock Messages-API IDs.",
                "https://platform.claude.com/docs/en/models/opus-4-7/overview"),
            "tool_calling": (
                True,
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "weaknesses": (
                "watch out for superseded twice over, no fast mode, UNKNOWN "
                "cutoff.",
                "https://platform.claude.com/docs/en/models/opus-4-7/overview"),
        }),
        ("claude-opus-4-6", {
            "avoid_for": (
                "less suited to cheapest routing, simplest extracts. Task "
                "fit: agents: best; coding: best; reasoning: best; routing: "
                "avoid.",
                "https://platform.claude.com/docs/en/models/opus-4-6/overview"),
            "best_for": (
                "suited to flagship planning, massive codebases, sustained "
                "agentic tasks. Task fit: agents: best; coding: best; "
                "reasoning: best; routing: avoid.",
                "https://platform.claude.com/docs/en/models/opus-4-6/overview"),
            "context_window": (
                1000000,
                "https://platform.claude.com/docs/en/models/opus-4-6/overview"),
            "cost_tier": (
                "strong-reasoning",
                "https://platform.claude.com/docs/en/models/opus-4-6/overview"),
            "currency": (
                "USD",
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "input_token_price": (
                5,
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "knowledge_cutoff": (
                "2025-05",
                "https://platform.claude.com/docs/en/models/opus-4-6/overview"),
            "max_output": (
                128000,
                "https://platform.claude.com/docs/en/models/opus-4-6/overview"),
            "modalities": (
                [
                    "text-in",
                    "image-in",
                    "text-out",
                ],
                "https://platform.claude.com/docs/en/models/opus-4-6/overview"),
            "output_token_price": (
                25,
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "reasoning": (
                True,
                "https://platform.claude.com/docs/en/models/opus-4-6/overview"),
            "role_notes": (
                "auditor role: careful legacy audit; director role: legacy "
                "only; manager role: plan with care; worker role: heavy "
                "tasks only.",
                "https://platform.claude.com/docs/en/models/opus-4-6/overview"),
            "source_links": (
                [
                    "https://platform.claude.com/docs/en/about-claude/model-depre"
                    "cations",
                    "https://platform.claude.com/docs/en/about-claude/pricing",
                    "https://platform.claude.com/docs/en/models/fable-5-1/overvie"
                    "w",
                    "https://platform.claude.com/docs/en/models/fable-5/overview",
                    "https://platform.claude.com/docs/en/models/haiku-4-5/overvie"
                    "w",
                    "https://platform.claude.com/docs/en/models/haiku-5-5/overvie"
                    "w",
                    "https://platform.claude.com/docs/en/models/opus-4-6/overview",
                    "https://platform.claude.com/docs/en/models/opus-4-7/overview",
                    "https://platform.claude.com/docs/en/models/opus-4-8/overview",
                    "https://platform.claude.com/docs/en/models/opus-5-5/overview",
                    "https://platform.claude.com/docs/en/models/opus-5/overview",
                    "https://platform.claude.com/docs/en/models/overview",
                    "https://platform.claude.com/docs/en/models/sonnet-4-6/overvi"
                    "ew",
                    "https://platform.claude.com/docs/en/models/sonnet-5-5/overvi"
                    "ew",
                    "https://platform.claude.com/docs/en/models/sonnet-5/overview",
                ],
                "https://platform.claude.com/docs/en/models/fable-5-1/overvie"
                "w"),
            "strengths": (
                "reads as strong on flagship planning behaviour, operates in "
                "massive codebases, active per deprecation table.",
                "https://platform.claude.com/docs/en/models/opus-4-6/overview"),
            "tool_calling": (
                True,
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "weaknesses": (
                "watch out for superseded by 4.7+ and 5 line, UNKNOWN "
                "context and cutoff, older capabilities.",
                "https://platform.claude.com/docs/en/models/opus-4-6/overview"),
        }),
        ("claude-sonnet-4-6", {
            "avoid_for": (
                "less suited to frontier reasoning, cheapest routing. Task "
                "fit: agents: good; coding: good; reasoning: good; routing: "
                "good.",
                "https://platform.claude.com/docs/en/models/sonnet-4-6/overvi"
                "ew"),
            "best_for": (
                "suited to mid-tier coding upgrades, computer use, "
                "long-context agent planning. Task fit: agents: good; "
                "coding: good; reasoning: good; routing: good.",
                "https://platform.claude.com/docs/en/models/sonnet-4-6/overvi"
                "ew"),
            "context_window": (
                1000000,
                "https://platform.claude.com/docs/en/models/sonnet-4-6/overvi"
                "ew"),
            "cost_tier": (
                "balanced",
                "https://platform.claude.com/docs/en/models/sonnet-4-6/overvi"
                "ew"),
            "currency": (
                "USD",
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "input_token_price": (
                3,
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "knowledge_cutoff": (
                "2025-08",
                "https://platform.claude.com/docs/en/models/sonnet-4-6/overvi"
                "ew"),
            "max_output": (
                128000,
                "https://platform.claude.com/docs/en/models/sonnet-4-6/overvi"
                "ew"),
            "modalities": (
                [
                    "text-in",
                    "image-in",
                    "text-out",
                ],
                "https://platform.claude.com/docs/en/models/sonnet-4-6/overvi"
                "ew"),
            "output_token_price": (
                15,
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "reasoning": (
                True,
                "https://platform.claude.com/docs/en/models/sonnet-4-6/overvi"
                "ew"),
            "role_notes": (
                "auditor role: mid-tier reviewer; director role: legacy "
                "fleet; manager role: balanced delegation; worker role: "
                "general builds.",
                "https://platform.claude.com/docs/en/models/sonnet-4-6/overvi"
                "ew"),
            "source_links": (
                [
                    "https://platform.claude.com/docs/en/about-claude/model-depre"
                    "cations",
                    "https://platform.claude.com/docs/en/about-claude/pricing",
                    "https://platform.claude.com/docs/en/models/fable-5-1/overvie"
                    "w",
                    "https://platform.claude.com/docs/en/models/fable-5/overview",
                    "https://platform.claude.com/docs/en/models/haiku-4-5/overvie"
                    "w",
                    "https://platform.claude.com/docs/en/models/haiku-5-5/overvie"
                    "w",
                    "https://platform.claude.com/docs/en/models/opus-4-6/overview",
                    "https://platform.claude.com/docs/en/models/opus-4-7/overview",
                    "https://platform.claude.com/docs/en/models/opus-4-8/overview",
                    "https://platform.claude.com/docs/en/models/opus-5-5/overview",
                    "https://platform.claude.com/docs/en/models/opus-5/overview",
                    "https://platform.claude.com/docs/en/models/overview",
                    "https://platform.claude.com/docs/en/models/sonnet-4-6/overvi"
                    "ew",
                    "https://platform.claude.com/docs/en/models/sonnet-5-5/overvi"
                    "ew",
                    "https://platform.claude.com/docs/en/models/sonnet-5/overview",
                ],
                "https://platform.claude.com/docs/en/models/fable-5-1/overvie"
                "w"),
            "strengths": (
                "reads as strong on full mid-tier upgrade, computer use and "
                "long context, 1M context per Bedrock card.",
                "https://platform.claude.com/docs/en/models/sonnet-4-6/overvi"
                "ew"),
            "tool_calling": (
                True,
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "weaknesses": (
                "watch out for pricier than Sonnet 5 line, superseded by "
                "Sonnet 5+, UNKNOWN cutoff.",
                "https://platform.claude.com/docs/en/models/sonnet-4-6/overvi"
                "ew"),
        }),
        ("claude-haiku-4-5", {
            "avoid_for": (
                "less suited to frontier reasoning, huge batch where 5.5 "
                "wins. Task fit: agents: good; coding: good; reasoning: ok; "
                "routing: best.",
                "https://platform.claude.com/docs/en/models/haiku-4-5/overvie"
                "w"),
            "best_for": (
                "suited to speed and efficiency, coding and agent drafts, "
                "cheap tool-calling fleets. Task fit: agents: good; coding: "
                "good; reasoning: ok; routing: best.",
                "https://platform.claude.com/docs/en/models/haiku-4-5/overvie"
                "w"),
            "context_window": (
                200000,
                "https://platform.claude.com/docs/en/models/haiku-4-5/overvie"
                "w"),
            "cost_tier": (
                "cheap-fast",
                "https://platform.claude.com/docs/en/models/haiku-4-5/overvie"
                "w"),
            "currency": (
                "USD",
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "input_token_price": (
                1,
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "knowledge_cutoff": (
                "2025-02",
                "https://platform.claude.com/docs/en/models/haiku-4-5/overvie"
                "w"),
            "max_output": (
                64000,
                "https://platform.claude.com/docs/en/models/haiku-4-5/overvie"
                "w"),
            "modalities": (
                [
                    "text-in",
                    "image-in",
                    "text-out",
                ],
                "https://platform.claude.com/docs/en/models/haiku-4-5/overvie"
                "w"),
            "output_token_price": (
                5,
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "reasoning": (
                True,
                "https://platform.claude.com/docs/en/models/haiku-4-5/overvie"
                "w"),
            "role_notes": (
                "auditor role: triage only; director role: cheap fan-out; "
                "manager role: delegate drafts; worker role: fast drafts and "
                "extracts.",
                "https://platform.claude.com/docs/en/models/haiku-4-5/overvie"
                "w"),
            "source_links": (
                [
                    "https://platform.claude.com/docs/en/about-claude/model-depre"
                    "cations",
                    "https://platform.claude.com/docs/en/about-claude/pricing",
                    "https://platform.claude.com/docs/en/models/fable-5-1/overvie"
                    "w",
                    "https://platform.claude.com/docs/en/models/fable-5/overview",
                    "https://platform.claude.com/docs/en/models/haiku-4-5/overvie"
                    "w",
                    "https://platform.claude.com/docs/en/models/haiku-5-5/overvie"
                    "w",
                    "https://platform.claude.com/docs/en/models/opus-4-6/overview",
                    "https://platform.claude.com/docs/en/models/opus-4-7/overview",
                    "https://platform.claude.com/docs/en/models/opus-4-8/overview",
                    "https://platform.claude.com/docs/en/models/opus-5-5/overview",
                    "https://platform.claude.com/docs/en/models/opus-5/overview",
                    "https://platform.claude.com/docs/en/models/overview",
                    "https://platform.claude.com/docs/en/models/sonnet-4-6/overvi"
                    "ew",
                    "https://platform.claude.com/docs/en/models/sonnet-5-5/overvi"
                    "ew",
                    "https://platform.claude.com/docs/en/models/sonnet-5/overview",
                ],
                "https://platform.claude.com/docs/en/models/fable-5-1/overvie"
                "w"),
            "strengths": (
                "reads as strong on lightweight and efficient, strong coding "
                "for size, 10x cheaper than Sonnet 5.",
                "https://platform.claude.com/docs/en/models/haiku-4-5/overvie"
                "w"),
            "tool_calling": (
                True,
                "https://platform.claude.com/docs/en/about-claude/pricing"),
            "weaknesses": (
                "watch out for smaller context than 5.5 line, weaker hardest "
                "reasoning, superseded by Haiku 5.5.",
                "https://platform.claude.com/docs/en/models/haiku-4-5/overvie"
                "w"),
        }),
    ],
    "azure-openai": [
        ("gpt-6-astra", {
            "avoid_for": (
                "less suited to outside-Azure low-cost bulk. Task fit: "
                "code-gen: best; planning: best; math-reasoning: best; "
                "agent-loop: best; long-doc: best.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "best_for": (
                "suited to complex reasoning in Azure compliance boundary. "
                "Task fit: code-gen: best; planning: best; math-reasoning: "
                "best; agent-loop: best; long-doc: best.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "context_window": (
                1050000,
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "cost_tier": (
                "strong-reasoning",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "max_output": (
                128000,
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "modalities": (
                [
                    "text-in",
                    "image-in",
                    "text-out",
                ],
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "reasoning": (
                True,
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "role_notes": (
                "director role: Use when data must stay in Azure.; manager "
                "role: Deploy via Foundry standard/provisioned.; worker "
                "role: Same prompts as OpenAI endpoint.; auditor role: Audit "
                "with residency guarantees..",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "source_links": (
                [
                    "https://azure.microsoft.com/en-us/pricing/details/azure-open"
                    "ai/",
                    "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                    "ncepts/models",
                ],
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "strengths": (
                "reads as strong on Azure-hosted OpenAI GPT-6 flagship; same "
                "weights as OpenAI, Azure SLA, VNet/data-residency, billed "
                "via Azure subscription.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "tool_calling": (
                True,
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "weaknesses": (
                "watch out for Azure pricing separate; short/long context "
                "categories; quota tiers may need request.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
        }),
        ("gpt-6.1-sol", {
            "avoid_for": (
                "less suited to UNKNOWN. Task fit: code-gen: best; planning: "
                "best; short-chat: best; long-doc: best; agent-loop: best.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "best_for": (
                "suited to balanced Azure workloads. Task fit: code-gen: "
                "best; planning: best; short-chat: best; long-doc: best; "
                "agent-loop: best.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "context_window": (
                1050000,
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "cost_tier": (
                "balanced",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "max_output": (
                128000,
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "modalities": (
                [
                    "text-in",
                    "image-in",
                    "text-out",
                ],
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "reasoning": (
                True,
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "role_notes": (
                "director role: Default Azure reasoning.; manager role: "
                "Standard deployment.; worker role: Primary Azure worker.; "
                "auditor role: Azure audit trail..",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "source_links": (
                [
                    "https://azure.microsoft.com/en-us/pricing/details/azure-open"
                    "ai/",
                    "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                    "ncepts/models",
                ],
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "strengths": (
                "reads as strong on Azure host of OpenAI 6.1-sol; balanced "
                "cost/intelligence.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "tool_calling": (
                True,
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "weaknesses": (
                "watch out for Azure billing separate from OpenAI API.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
        }),
        ("gpt-6-luna", {
            "avoid_for": (
                "less suited to UNKNOWN. Task fit: routing: best; "
                "short-chat: best; bulk-summary: best.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "best_for": (
                "suited to high-volume Azure tasks. Task fit: routing: best; "
                "short-chat: best; bulk-summary: best.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "context_window": (
                1050000,
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "cost_tier": (
                "cheap-fast",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "max_output": (
                128000,
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "modalities": (
                [
                    "text-in",
                    "image-in",
                    "text-out",
                ],
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "reasoning": (
                True,
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "role_notes": (
                "director role: Cheap Azure triage.; manager role: Bulk "
                "fan-out.; worker role: Bulk worker.; auditor role: First "
                "pass..",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "source_links": (
                [
                    "https://azure.microsoft.com/en-us/pricing/details/azure-open"
                    "ai/",
                    "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                    "ncepts/models",
                ],
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "strengths": (
                "reads as strong on Azure host of OpenAI Luna efficient tier.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "tool_calling": (
                True,
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "weaknesses": (
                "watch out for UNKNOWN.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
        }),
        ("gpt-5.6-sol", {
            "avoid_for": (
                "less suited to UNKNOWN. Task fit: code-gen: best; planning: "
                "best; math-reasoning: best; long-doc: best.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "best_for": (
                "suited to professional Azure reasoning work. Task fit: "
                "code-gen: best; planning: best; math-reasoning: best; "
                "long-doc: best.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "context_window": (
                1050000,
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "cost_tier": (
                "strong-reasoning",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "max_output": (
                128000,
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "modalities": (
                [
                    "text-in",
                    "image-in",
                    "text-out",
                ],
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "reasoning": (
                True,
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "role_notes": (
                "director role: Fallback when GPT-6 quota limited.; manager "
                "role: Stable Azure pipeline.; worker role: Strong worker.; "
                "auditor role: Reliable audit..",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "source_links": (
                [
                    "https://azure.microsoft.com/en-us/pricing/details/azure-open"
                    "ai/",
                    "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                    "ncepts/models",
                ],
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "strengths": (
                "reads as strong on Azure host of OpenAI 5.6-sol flagship.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "tool_calling": (
                True,
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "weaknesses": (
                "watch out for UNKNOWN.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
        }),
        ("gpt-5.4", {
            "avoid_for": (
                "less suited to UNKNOWN. Task fit: short-chat: best; "
                "long-doc: good; code-gen: good.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "best_for": (
                "suited to general Azure chat and docs. Task fit: "
                "short-chat: best; long-doc: good; code-gen: good.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "context_window": (
                1050000,
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "cost_tier": (
                "balanced",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "max_output": (
                128000,
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "modalities": (
                [
                    "text-in",
                    "image-in",
                    "text-out",
                ],
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "reasoning": (
                True,
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "role_notes": (
                "director role: Legacy compat.; manager role: Existing "
                "pipelines.; worker role: General tasks.; auditor role: "
                "Routine audits..",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "source_links": (
                [
                    "https://azure.microsoft.com/en-us/pricing/details/azure-open"
                    "ai/",
                    "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                    "ncepts/models",
                ],
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "strengths": (
                "reads as strong on Azure host of OpenAI 5.4 generation.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "tool_calling": (
                True,
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "weaknesses": (
                "watch out for UNKNOWN.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
        }),
        ("gpt-4o", {
            "avoid_for": (
                "less suited to hard reasoning. Task fit: short-chat: best; "
                "vision: best; code-gen: good.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "best_for": (
                "suited to general multimodal Azure apps. Task fit: "
                "short-chat: best; vision: best; code-gen: good.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "context_window": (
                128000,
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "cost_tier": (
                "balanced",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "max_output": (
                16384,
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "modalities": (
                [
                    "text-in",
                    "image-in",
                    "text-out",
                ],
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "role_notes": (
                "director role: Legacy default.; manager role: Stable apps.; "
                "worker role: Everyday worker.; auditor role: Baseline..",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "source_links": (
                [
                    "https://azure.microsoft.com/en-us/pricing/details/azure-open"
                    "ai/",
                    "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                    "ncepts/models",
                ],
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "strengths": (
                "reads as strong on Azure host of OpenAI GPT-4o omni; mature.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "tool_calling": (
                True,
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "weaknesses": (
                "watch out for 128K context smaller than 5/6 gen.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
        }),
        ("gpt-4o-mini", {
            "avoid_for": (
                "less suited to frontier proofs. Task fit: routing: best; "
                "short-chat: best; bulk-summary: best.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "best_for": (
                "suited to high-volume cheap Azure traffic. Task fit: "
                "routing: best; short-chat: best; bulk-summary: best.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "context_window": (
                128000,
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "cost_tier": (
                "cheap-fast",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "max_output": (
                16384,
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "modalities": (
                [
                    "text-in",
                    "image-in",
                    "text-out",
                ],
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "role_notes": (
                "director role: Bulk triage.; manager role: Fan-out.; worker "
                "role: Cheap worker.; auditor role: First pass..",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "source_links": (
                [
                    "https://azure.microsoft.com/en-us/pricing/details/azure-open"
                    "ai/",
                    "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                    "ncepts/models",
                ],
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "strengths": (
                "reads as strong on Azure host of OpenAI mini cheap tier.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "tool_calling": (
                True,
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "weaknesses": (
                "watch out for UNKNOWN.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
        }),
        ("o3", {
            "avoid_for": (
                "less suited to cheap chat. Task fit: math-reasoning: best; "
                "code-gen: best; planning: best.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "best_for": (
                "suited to Azure math/science reasoning. Task fit: "
                "math-reasoning: best; code-gen: best; planning: best.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "context_window": (
                200000,
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "cost_tier": (
                "strong-reasoning",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "knowledge_cutoff": (
                "2024-05-31",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "max_output": (
                100000,
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "modalities": (
                [
                    "text-in",
                    "image-in",
                    "text-out",
                ],
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "reasoning": (
                True,
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "role_notes": (
                "director role: Deep escalation.; manager role: Multi-step.; "
                "worker role: Reasoning chains.; auditor role: Verify logic..",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "source_links": (
                [
                    "https://azure.microsoft.com/en-us/pricing/details/azure-open"
                    "ai/",
                    "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                    "ncepts/models",
                ],
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "strengths": (
                "reads as strong on Azure host of OpenAI o3 reasoning.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "tool_calling": (
                True,
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "weaknesses": (
                "watch out for migration to gpt-5.6-sol advised by OpenAI.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
        }),
        ("text-embedding-3-large", {
            "avoid_for": (
                "less suited to generation. Task fit: embeddings: best; "
                "long-doc: good; routing: good.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "best_for": (
                "suited to Azure RAG retrieval. Task fit: embeddings: best; "
                "long-doc: good; routing: good.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "context_window": (
                8192,
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "cost_tier": (
                "specialised",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "modalities": (
                [
                    "text-in",
                    "vector-out",
                ],
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "role_notes": (
                "director role: Similarity routing.; manager role: RAG "
                "backbone.; worker role: Embed first.; auditor role: "
                "Duplicate checks..",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "source_links": (
                [
                    "https://azure.microsoft.com/en-us/pricing/details/azure-open"
                    "ai/",
                    "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                    "ncepts/models",
                ],
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "strengths": (
                "reads as strong on Azure host of OpenAI embedding; same "
                "3072-dim model.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "weaknesses": (
                "watch out for must re-embed when migrating from ada.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
        }),
        ("gpt-4o-mini-tts", {
            "avoid_for": (
                "less suited to reasoning. Task fit: speech: best.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "best_for": (
                "suited to Azure voice output. Task fit: speech: best.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "cost_tier": (
                "specialised",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "modalities": (
                [
                    "text-in",
                    "audio-out",
                ],
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "role_notes": (
                "director role: Voice only.; manager role: Voice chain.; "
                "worker role: Narration.; auditor role: UNKNOWN.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "source_links": (
                [
                    "https://azure.microsoft.com/en-us/pricing/details/azure-open"
                    "ai/",
                    "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                    "ncepts/models",
                ],
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "strengths": (
                "reads as strong on Azure host of OpenAI TTS voice.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
            "weaknesses": (
                "watch out for Azure audio availability varies by region.",
                "https://learn.microsoft.com/en-us/azure/ai-foundry/openai/co"
                "ncepts/models"),
        }),
    ],
    "bedrock": [
        ("bedrock-anthropic-claude-fable-5-1", {
            "avoid_for": (
                "less suited to cheapest bulk routing. Task fit: agents: "
                "best; coding: best; reasoning: best; routing: avoid.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-fable-5-1.html"),
            "best_for": (
                "suited to long-horizon agents on AWS, private VPC "
                "inference. Task fit: agents: best; coding: best; reasoning: "
                "best; routing: avoid.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-fable-5-1.html"),
            "context_window": (
                1000000,
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-fable-5-1.html"),
            "cost_tier": (
                "strong-reasoning",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-fable-5-1.html"),
            "knowledge_cutoff": (
                "2026-06",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-fable-5-1.html"),
            "max_output": (
                128000,
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-fable-5-1.html"),
            "modalities": (
                [
                    "text",
                    "image",
                ],
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-fable-5-1.html"),
            "reasoning": (
                True,
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-fable-5-1.html"),
            "role_notes": (
                "UNKNOWN.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-fable-5-1.html"),
            "source_links": (
                [
                    "https://aws.amazon.com/bedrock/pricing/",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-amazon-nova-pro.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-fable-5-1.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-haiku-4-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-haiku-5-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-opus-4-8.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-opus-5-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-opus-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-sonnet-5-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-sonnet-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-meta-llama-3-3-70b-instruct.html",
                ],
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-fable-5-1.html"),
            "strengths": (
                "reads as strong on same frontier model inside AWS boundary, "
                "Bedrock guardrails and VPC controls.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-fable-5-1.html"),
            "tool_calling": (
                True,
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-fable-5-1.html"),
            "weaknesses": (
                "watch out for top price tier, gated availability on some "
                "endpoints.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-fable-5-1.html"),
        }),
        ("bedrock-anthropic-claude-opus-5-5", {
            "avoid_for": (
                "less suited to tiny-budget routing. Task fit: agents: best; "
                "coding: best; reasoning: best; routing: ok.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-opus-5-5.html"),
            "best_for": (
                "suited to agentic coding on AWS, knowledge work with data "
                "residency. Task fit: agents: best; coding: best; reasoning: "
                "best; routing: ok.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-opus-5-5.html"),
            "context_window": (
                1000000,
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-opus-5-5.html"),
            "cost_tier": (
                "strong-reasoning",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-opus-5-5.html"),
            "knowledge_cutoff": (
                "2026-06",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-opus-5-5.html"),
            "max_output": (
                128000,
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-opus-5-5.html"),
            "modalities": (
                [
                    "text",
                    "image",
                ],
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-opus-5-5.html"),
            "reasoning": (
                True,
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-opus-5-5.html"),
            "role_notes": (
                "UNKNOWN.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-opus-5-5.html"),
            "source_links": (
                [
                    "https://aws.amazon.com/bedrock/pricing/",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-amazon-nova-pro.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-fable-5-1.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-haiku-4-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-haiku-5-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-opus-4-8.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-opus-5-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-opus-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-sonnet-5-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-sonnet-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-meta-llama-3-3-70b-instruct.html",
                ],
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-fable-5-1.html"),
            "strengths": (
                "reads as strong on most capable Opus via Bedrock, global "
                "and regional endpoints.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-opus-5-5.html"),
            "tool_calling": (
                True,
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-opus-5-5.html"),
            "weaknesses": (
                "watch out for regional 10% premium, Bedrock sets own "
                "lifecycle dates.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-opus-5-5.html"),
        }),
        ("bedrock-anthropic-claude-sonnet-5-5", {
            "avoid_for": (
                "less suited to deepest frontier reasoning. Task fit: "
                "agents: best; coding: best; reasoning: good; routing: good.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-sonnet-5-5.html"),
            "best_for": (
                "suited to production agents on AWS, coding at scale with "
                "residency. Task fit: agents: best; coding: best; reasoning: "
                "good; routing: good.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-sonnet-5-5.html"),
            "context_window": (
                1000000,
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-sonnet-5-5.html"),
            "cost_tier": (
                "balanced",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-sonnet-5-5.html"),
            "knowledge_cutoff": (
                "2026-06",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-sonnet-5-5.html"),
            "max_output": (
                128000,
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-sonnet-5-5.html"),
            "modalities": (
                [
                    "text",
                    "image",
                ],
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-sonnet-5-5.html"),
            "reasoning": (
                True,
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-sonnet-5-5.html"),
            "role_notes": (
                "UNKNOWN.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-sonnet-5-5.html"),
            "source_links": (
                [
                    "https://aws.amazon.com/bedrock/pricing/",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-amazon-nova-pro.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-fable-5-1.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-haiku-4-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-haiku-5-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-opus-4-8.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-opus-5-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-opus-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-sonnet-5-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-sonnet-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-meta-llama-3-3-70b-instruct.html",
                ],
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-fable-5-1.html"),
            "strengths": (
                "reads as strong on balanced cost and intelligence on AWS, "
                "batch inference 50% lower per Bedrock pricing.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-sonnet-5-5.html"),
            "tool_calling": (
                True,
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-sonnet-5-5.html"),
            "weaknesses": (
                "watch out for regional premium applies, Bedrock lifecycle "
                "differs from first-party.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-sonnet-5-5.html"),
        }),
        ("bedrock-anthropic-claude-haiku-5-5", {
            "avoid_for": (
                "less suited to frontier reasoning. Task fit: agents: good; "
                "coding: good; reasoning: ok; routing: best.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-haiku-5-5.html"),
            "best_for": (
                "suited to high-volume classification on AWS, extraction and "
                "routing fleets. Task fit: agents: good; coding: good; "
                "reasoning: ok; routing: best.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-haiku-5-5.html"),
            "context_window": (
                1000000,
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-haiku-5-5.html"),
            "cost_tier": (
                "cheap-fast",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-haiku-5-5.html"),
            "knowledge_cutoff": (
                "2026-06",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-haiku-5-5.html"),
            "max_output": (
                128000,
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-haiku-5-5.html"),
            "modalities": (
                [
                    "text",
                    "image",
                ],
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-haiku-5-5.html"),
            "reasoning": (
                True,
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-haiku-5-5.html"),
            "role_notes": (
                "UNKNOWN.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-haiku-5-5.html"),
            "source_links": (
                [
                    "https://aws.amazon.com/bedrock/pricing/",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-amazon-nova-pro.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-fable-5-1.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-haiku-4-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-haiku-5-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-opus-4-8.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-opus-5-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-opus-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-sonnet-5-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-sonnet-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-meta-llama-3-3-70b-instruct.html",
                ],
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-fable-5-1.html"),
            "strengths": (
                "reads as strong on cheapest Claude on Bedrock, fastest "
                "latency class.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-haiku-5-5.html"),
            "tool_calling": (
                True,
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-haiku-5-5.html"),
            "weaknesses": (
                "watch out for length-tiered pricing, weakest reasoning of "
                "family.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-haiku-5-5.html"),
        }),
        ("bedrock-anthropic-claude-opus-5", {
            "avoid_for": (
                "less suited to cheap bulk work. Task fit: agents: best; "
                "coding: best; reasoning: best; routing: ok.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-opus-5.html"),
            "best_for": (
                "suited to legacy Opus 5 agents on AWS. Task fit: agents: "
                "best; coding: best; reasoning: best; routing: ok.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-opus-5.html"),
            "context_window": (
                1000000,
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-opus-5.html"),
            "cost_tier": (
                "strong-reasoning",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-opus-5.html"),
            "knowledge_cutoff": (
                "2026-05",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-opus-5.html"),
            "max_output": (
                128000,
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-opus-5.html"),
            "modalities": (
                [
                    "text",
                    "image",
                ],
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-opus-5.html"),
            "reasoning": (
                True,
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-opus-5.html"),
            "role_notes": (
                "UNKNOWN.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-opus-5.html"),
            "source_links": (
                [
                    "https://aws.amazon.com/bedrock/pricing/",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-amazon-nova-pro.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-fable-5-1.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-haiku-4-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-haiku-5-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-opus-4-8.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-opus-5-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-opus-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-sonnet-5-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-sonnet-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-meta-llama-3-3-70b-instruct.html",
                ],
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-fable-5-1.html"),
            "strengths": (
                "reads as strong on Bedrock-hosted Opus 5, same base price "
                "as first-party.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-opus-5.html"),
            "tool_calling": (
                True,
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-opus-5.html"),
            "weaknesses": (
                "watch out for superseded by Opus 5.5, UNKNOWN Bedrock "
                "regional table.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-opus-5.html"),
        }),
        ("bedrock-anthropic-claude-sonnet-5", {
            "avoid_for": (
                "less suited to frontier reasoning. Task fit: agents: good; "
                "coding: best; reasoning: good; routing: good.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-sonnet-5.html"),
            "best_for": (
                "suited to legacy Sonnet production fleets on AWS. Task fit: "
                "agents: good; coding: best; reasoning: good; routing: good.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-sonnet-5.html"),
            "context_window": (
                1000000,
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-sonnet-5.html"),
            "cost_tier": (
                "balanced",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-sonnet-5.html"),
            "knowledge_cutoff": (
                "2026-01",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-sonnet-5.html"),
            "max_output": (
                128000,
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-sonnet-5.html"),
            "modalities": (
                [
                    "text",
                    "image",
                ],
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-sonnet-5.html"),
            "reasoning": (
                True,
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-sonnet-5.html"),
            "role_notes": (
                "UNKNOWN.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-sonnet-5.html"),
            "source_links": (
                [
                    "https://aws.amazon.com/bedrock/pricing/",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-amazon-nova-pro.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-fable-5-1.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-haiku-4-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-haiku-5-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-opus-4-8.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-opus-5-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-opus-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-sonnet-5-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-sonnet-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-meta-llama-3-3-70b-instruct.html",
                ],
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-fable-5-1.html"),
            "strengths": (
                "reads as strong on cheap production Sonnet on AWS, batch "
                "discount eligible.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-sonnet-5.html"),
            "tool_calling": (
                True,
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-sonnet-5.html"),
            "weaknesses": (
                "watch out for superseded by Sonnet 5.5, UNKNOWN Bedrock "
                "regional table.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-sonnet-5.html"),
        }),
        ("bedrock-anthropic-claude-opus-4-8", {
            "avoid_for": (
                "less suited to cheap routing. Task fit: agents: best; "
                "coding: best; reasoning: best; routing: ok.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-opus-4-8.html"),
            "best_for": (
                "suited to legacy 4.x Opus agents on AWS. Task fit: agents: "
                "best; coding: best; reasoning: best; routing: ok.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-opus-4-8.html"),
            "context_window": (
                1000000,
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-opus-4-8.html"),
            "cost_tier": (
                "strong-reasoning",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-opus-4-8.html"),
            "knowledge_cutoff": (
                "2026-01",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-opus-4-8.html"),
            "max_output": (
                128000,
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-opus-4-8.html"),
            "modalities": (
                [
                    "text",
                    "image",
                ],
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-opus-4-8.html"),
            "reasoning": (
                True,
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-opus-4-8.html"),
            "role_notes": (
                "UNKNOWN.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-opus-4-8.html"),
            "source_links": (
                [
                    "https://aws.amazon.com/bedrock/pricing/",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-amazon-nova-pro.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-fable-5-1.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-haiku-4-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-haiku-5-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-opus-4-8.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-opus-5-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-opus-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-sonnet-5-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-sonnet-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-meta-llama-3-3-70b-instruct.html",
                ],
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-fable-5-1.html"),
            "strengths": (
                "reads as strong on stable legacy Opus on AWS, fast mode on "
                "first-party only.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-opus-4-8.html"),
            "tool_calling": (
                True,
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-opus-4-8.html"),
            "weaknesses": (
                "watch out for two generations behind, UNKNOWN Bedrock "
                "regional table.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-opus-4-8.html"),
        }),
        ("bedrock-anthropic-claude-haiku-4-5", {
            "avoid_for": (
                "less suited to frontier reasoning. Task fit: agents: good; "
                "coding: good; reasoning: ok; routing: best.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-haiku-4-5.html"),
            "best_for": (
                "suited to cheap efficient agents on AWS. Task fit: agents: "
                "good; coding: good; reasoning: ok; routing: best.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-haiku-4-5.html"),
            "context_window": (
                200000,
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-haiku-4-5.html"),
            "cost_tier": (
                "cheap-fast",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-haiku-4-5.html"),
            "knowledge_cutoff": (
                "2025-02",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-haiku-4-5.html"),
            "max_output": (
                64000,
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-haiku-4-5.html"),
            "modalities": (
                [
                    "text",
                    "image",
                ],
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-haiku-4-5.html"),
            "reasoning": (
                True,
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-haiku-4-5.html"),
            "role_notes": (
                "UNKNOWN.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-haiku-4-5.html"),
            "source_links": (
                [
                    "https://aws.amazon.com/bedrock/pricing/",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-amazon-nova-pro.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-fable-5-1.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-haiku-4-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-haiku-5-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-opus-4-8.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-opus-5-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-opus-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-sonnet-5-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-sonnet-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-meta-llama-3-3-70b-instruct.html",
                ],
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-fable-5-1.html"),
            "strengths": (
                "reads as strong on cheap Bedrock-hosted lightweight, good "
                "tool-calling for size.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-haiku-4-5.html"),
            "tool_calling": (
                True,
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-haiku-4-5.html"),
            "weaknesses": (
                "watch out for superseded by Haiku 5.5, UNKNOWN Bedrock "
                "regional table.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-haiku-4-5.html"),
        }),
        ("bedrock-meta-llama-3-3-70b", {
            "avoid_for": (
                "less suited to frontier coding precision, tasks needing "
                "Claude tooling. Task fit: agents: ok; coding: ok; "
                "reasoning: ok; routing: good.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-meta-llama-3-3-70b-instruct.html"),
            "best_for": (
                "suited to open-weight chat on AWS, cost-sensitive batch "
                "inference. Task fit: agents: ok; coding: ok; reasoning: ok; "
                "routing: good.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-meta-llama-3-3-70b-instruct.html"),
            "context_window": (
                128000,
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-meta-llama-3-3-70b-instruct.html"),
            "cost_tier": (
                "balanced",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-meta-llama-3-3-70b-instruct.html"),
            "knowledge_cutoff": (
                "2023-12",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-meta-llama-3-3-70b-instruct.html"),
            "max_output": (
                4000,
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-meta-llama-3-3-70b-instruct.html"),
            "modalities": (
                [
                    "text",
                ],
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-meta-llama-3-3-70b-instruct.html"),
            "role_notes": (
                "UNKNOWN.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-meta-llama-3-3-70b-instruct.html"),
            "source_links": (
                [
                    "https://aws.amazon.com/bedrock/pricing/",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-amazon-nova-pro.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-fable-5-1.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-haiku-4-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-haiku-5-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-opus-4-8.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-opus-5-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-opus-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-sonnet-5-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-sonnet-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-meta-llama-3-3-70b-instruct.html",
                ],
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-fable-5-1.html"),
            "strengths": (
                "reads as strong on open-weight flexibility, Bedrock VPC and "
                "guardrails apply.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-meta-llama-3-3-70b-instruct.html"),
            "tool_calling": (
                True,
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-meta-llama-3-3-70b-instruct.html"),
            "weaknesses": (
                "watch out for UNKNOWN Bedrock per-token price, weaker than "
                "Claude Opus on code.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-meta-llama-3-3-70b-instruct.html"),
        }),
        ("bedrock-amazon-nova-pro", {
            "avoid_for": (
                "less suited to frontier reasoning, Claude-specific tooling. "
                "Task fit: agents: ok; coding: ok; reasoning: ok; routing: "
                "best.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-amazon-nova-pro.html"),
            "best_for": (
                "suited to AWS-native cheap inference, summarisation and RAG "
                "on Bedrock. Task fit: agents: ok; coding: ok; reasoning: "
                "ok; routing: best.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-amazon-nova-pro.html"),
            "context_window": (
                300000,
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-amazon-nova-pro.html"),
            "cost_tier": (
                "cheap-fast",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-amazon-nova-pro.html"),
            "knowledge_cutoff": (
                "2024-10",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-amazon-nova-pro.html"),
            "max_output": (
                10000,
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-amazon-nova-pro.html"),
            "modalities": (
                [
                    "text",
                    "image",
                    "video",
                ],
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-amazon-nova-pro.html"),
            "role_notes": (
                "UNKNOWN.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-amazon-nova-pro.html"),
            "source_links": (
                [
                    "https://aws.amazon.com/bedrock/pricing/",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-amazon-nova-pro.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-fable-5-1.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-haiku-4-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-haiku-5-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-opus-4-8.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-opus-5-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-opus-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-sonnet-5-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-anthropic-claude-sonnet-5.html",
                    "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                    "ard-meta-llama-3-3-70b-instruct.html",
                ],
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-anthropic-claude-fable-5-1.html"),
            "strengths": (
                "reads as strong on AWS-native model, Bedrock batch and "
                "provisioned options.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-amazon-nova-pro.html"),
            "tool_calling": (
                True,
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-amazon-nova-pro.html"),
            "weaknesses": (
                "watch out for UNKNOWN Bedrock per-token price, UNKNOWN "
                "benchmark standing.",
                "https://docs.aws.amazon.com/bedrock/latest/userguide/model-c"
                "ard-amazon-nova-pro.html"),
        }),
    ],
    "cohere": [
        ("command-a-plus-05-2026", {
            "avoid_for": (
                "less suited to embeddings or rerank (use Embed/Rerank "
                "endpoints), speech transcription, simple bulk chat where "
                "R7B is cheaper. Task fit: agent-loop: best; code-review: "
                "good; long-doc: best; planning: best; routing: good; "
                "short-chat: good; vision: good.",
                "https://docs.cohere.com/docs/models"),
            "best_for": (
                "suited to agentic tool-use loops, RAG over long docs, "
                "multilingual enterprise chat. Task fit: agent-loop: best; "
                "code-review: good; long-doc: best; planning: best; routing: "
                "good; short-chat: good; vision: good.",
                "https://docs.cohere.com/docs/models"),
            "context_window": (
                128000,
                "https://docs.cohere.com/docs/models"),
            "cost_tier": (
                "strong-reasoning",
                "https://docs.cohere.com/docs/models"),
            "max_output": (
                64000,
                "https://docs.cohere.com/docs/models"),
            "modalities": (
                [
                    "text",
                    "image",
                ],
                "https://docs.cohere.com/docs/models"),
            "reasoning": (
                True,
                "https://docs.cohere.com/docs/models"),
            "role_notes": (
                "auditor role: Strong audit reviewer; verify citations via "
                "RAG sources.; director role: Flagship for complex "
                "delegation; watch unknown per-token cost.; manager role: "
                "Best multi-step agent manager in Cohere lineup.; worker "
                "role: Use for hard reasoning steps; R7B for cheap steps..",
                "https://docs.cohere.com/docs/models"),
            "source_links": (
                [
                    "https://cohere.com/pricing",
                    "https://docs.cohere.com/docs/command-a",
                    "https://docs.cohere.com/docs/command-a-reasoning",
                    "https://docs.cohere.com/docs/command-a-vision",
                    "https://docs.cohere.com/docs/how-does-cohere-pricing-work",
                    "https://docs.cohere.com/docs/models",
                    "https://docs.cohere.com/docs/reasoning",
                    "https://docs.cohere.com/docs/structured-outputs",
                    "https://docs.cohere.com/docs/tool-use",
                ],
                "https://docs.cohere.com/docs/models"),
            "strengths": (
                "reads as strong on First Cohere MoE combining vision, "
                "agents, reasoning, translation, Fits 1xB200 or 2xH100; "
                "higher throughput than Reasoning variant, 128K context with "
                "64K output.",
                "https://docs.cohere.com/docs/models"),
            "tool_calling": (
                True,
                "https://docs.cohere.com/docs/tool-use"),
            "weaknesses": (
                "watch out for Per-token price not published on pricing page "
                "(Model Vault instance pricing), Knowledge cutoff "
                "undisclosed, Newer model with less community benchmark "
                "coverage.",
                "https://docs.cohere.com/docs/models"),
        }),
        ("command-a-03-2025", {
            "avoid_for": (
                "less suited to vision input (use A+ or A-Vision), "
                "embeddings or rerank tasks, speech transcription. Task fit: "
                "agent-loop: best; bulk-summary: good; code-gen: good; "
                "long-doc: best; planning: good; routing: good; short-chat: "
                "good.",
                "https://docs.cohere.com/docs/models"),
            "best_for": (
                "suited to tool use and agents, RAG pipelines, multilingual "
                "chat (23 languages). Task fit: agent-loop: best; "
                "bulk-summary: good; code-gen: good; long-doc: best; "
                "planning: good; routing: good; short-chat: good.",
                "https://docs.cohere.com/docs/models"),
            "context_window": (
                256000,
                "https://docs.cohere.com/docs/models"),
            "cost_tier": (
                "balanced",
                "https://docs.cohere.com/docs/models"),
            "max_output": (
                8000,
                "https://docs.cohere.com/docs/models"),
            "modalities": (
                [
                    "text",
                ],
                "https://docs.cohere.com/docs/models"),
            "role_notes": (
                "auditor role: Solid grounded QA reviewer via RAG "
                "citations.; director role: Workhorse planner for RAG/agent "
                "fleets.; manager role: Good delegation manager; 2-GPU "
                "deployable.; worker role: Strong general worker; cap output "
                "expectations at 8K..",
                "https://docs.cohere.com/docs/models"),
            "source_links": (
                [
                    "https://cohere.com/pricing",
                    "https://docs.cohere.com/docs/command-a",
                    "https://docs.cohere.com/docs/command-a-reasoning",
                    "https://docs.cohere.com/docs/command-a-vision",
                    "https://docs.cohere.com/docs/how-does-cohere-pricing-work",
                    "https://docs.cohere.com/docs/models",
                    "https://docs.cohere.com/docs/reasoning",
                    "https://docs.cohere.com/docs/structured-outputs",
                    "https://docs.cohere.com/docs/tool-use",
                ],
                "https://docs.cohere.com/docs/models"),
            "strengths": (
                "reads as strong on 111B params, 256K context, runs on 2 "
                "GPUs, 150 percent higher throughput than Command R+ "
                "08-2024, Strong tool-use avoiding unnecessary calls.",
                "https://docs.cohere.com/docs/models"),
            "tool_calling": (
                True,
                "https://docs.cohere.com/docs/command-a"),
            "weaknesses": (
                "watch out for 8K max output limits long generations, "
                "Per-token price not published (instance pricing), Cutoff "
                "undisclosed.",
                "https://docs.cohere.com/docs/models"),
        }),
        ("command-r7b-12-2024", {
            "avoid_for": (
                "less suited to long-doc synthesis over 128K, vision or "
                "speech tasks, max-quality reasoning chains. Task fit: "
                "agent-loop: good; bulk-summary: good; code-gen: ok; "
                "long-doc: ok; routing: best; short-chat: best.",
                "https://docs.cohere.com/docs/models"),
            "best_for": (
                "suited to high-volume simple QA and classification, cheap "
                "RAG and tool-use steps, bulk routing and triage. Task fit: "
                "agent-loop: good; bulk-summary: good; code-gen: ok; "
                "long-doc: ok; routing: best; short-chat: best.",
                "https://docs.cohere.com/docs/models"),
            "context_window": (
                128000,
                "https://docs.cohere.com/docs/models"),
            "cost_tier": (
                "cheap-fast",
                "https://docs.cohere.com/docs/models"),
            "max_output": (
                4000,
                "https://docs.cohere.com/docs/models"),
            "modalities": (
                [
                    "text",
                ],
                "https://docs.cohere.com/docs/models"),
            "role_notes": (
                "auditor role: Use for cheap first-pass checks only.; "
                "director role: Cheapest routing tier for fan-out.; manager "
                "role: Bulk triage manager.; worker role: Default cheap "
                "worker for simple steps..",
                "https://docs.cohere.com/docs/models"),
            "source_links": (
                [
                    "https://cohere.com/pricing",
                    "https://docs.cohere.com/docs/command-a",
                    "https://docs.cohere.com/docs/command-a-reasoning",
                    "https://docs.cohere.com/docs/command-a-vision",
                    "https://docs.cohere.com/docs/how-does-cohere-pricing-work",
                    "https://docs.cohere.com/docs/models",
                    "https://docs.cohere.com/docs/reasoning",
                    "https://docs.cohere.com/docs/structured-outputs",
                    "https://docs.cohere.com/docs/tool-use",
                ],
                "https://docs.cohere.com/docs/models"),
            "strengths": (
                "reads as strong on Small fast model for RAG, tool use, "
                "agents, Most cost-effective Command tier per third-party "
                "pricing surveys, 128K context.",
                "https://docs.cohere.com/docs/models"),
            "tool_calling": (
                True,
                "https://docs.cohere.com/docs/models"),
            "weaknesses": (
                "watch out for 4K output cap, Weaker on nuanced reasoning, "
                "Exact per-token price not on official page.",
                "https://docs.cohere.com/docs/models"),
        }),
        ("command-a-reasoning-08-2025", {
            "avoid_for": (
                "less suited to vision tasks, embeddings or rerank, simple "
                "chat where cheaper models win. Task fit: agent-loop: best; "
                "code-review: good; long-doc: good; math-reasoning: best; "
                "planning: best; routing: ok; short-chat: ok.",
                "https://docs.cohere.com/docs/models"),
            "best_for": (
                "suited to math and nuanced problem solving, multi-step "
                "agent reasoning (23 languages), planning with "
                "think-before-answer. Task fit: agent-loop: best; "
                "code-review: good; long-doc: good; math-reasoning: best; "
                "planning: best; routing: ok; short-chat: ok.",
                "https://docs.cohere.com/docs/models"),
            "context_window": (
                256000,
                "https://docs.cohere.com/docs/models"),
            "cost_tier": (
                "strong-reasoning",
                "https://docs.cohere.com/docs/models"),
            "max_output": (
                32000,
                "https://docs.cohere.com/docs/models"),
            "modalities": (
                [
                    "text",
                ],
                "https://docs.cohere.com/docs/models"),
            "reasoning": (
                True,
                "https://docs.cohere.com/docs/command-a-reasoning"),
            "role_notes": (
                "auditor role: Best Cohere auditor for step-by-step "
                "verification.; director role: Use for hard planning nodes.; "
                "manager role: Reasoning manager for complex subgoals.; "
                "worker role: Use for math-reasoning subtasks..",
                "https://docs.cohere.com/docs/models"),
            "source_links": (
                [
                    "https://cohere.com/pricing",
                    "https://docs.cohere.com/docs/command-a",
                    "https://docs.cohere.com/docs/command-a-reasoning",
                    "https://docs.cohere.com/docs/command-a-vision",
                    "https://docs.cohere.com/docs/how-does-cohere-pricing-work",
                    "https://docs.cohere.com/docs/models",
                    "https://docs.cohere.com/docs/reasoning",
                    "https://docs.cohere.com/docs/structured-outputs",
                    "https://docs.cohere.com/docs/tool-use",
                ],
                "https://docs.cohere.com/docs/models"),
            "strengths": (
                "reads as strong on First Cohere reasoning model with "
                "explicit think step, 256K context with 32K output, "
                "23-language reasoning coverage.",
                "https://docs.cohere.com/docs/models"),
            "tool_calling": (
                True,
                "https://docs.cohere.com/docs/command-a-reasoning"),
            "weaknesses": (
                "watch out for Slower than non-reasoning siblings, Per-token "
                "price unpublished, Cutoff undisclosed.",
                "https://docs.cohere.com/docs/models"),
        }),
        ("command-a-vision-07-2025", {
            "avoid_for": (
                "less suited to text-only bulk (cheaper models win), "
                "embeddings or speech, long 256K-doc RAG (use Command A). "
                "Task fit: agent-loop: good; long-doc: good; routing: ok; "
                "short-chat: good; vision: best.",
                "https://docs.cohere.com/docs/models"),
            "best_for": (
                "suited to chart and diagram analysis, document QA with OCR "
                "and tables, object detection style QA. Task fit: "
                "agent-loop: good; long-doc: good; routing: ok; short-chat: "
                "good; vision: best.",
                "https://docs.cohere.com/docs/models"),
            "context_window": (
                128000,
                "https://docs.cohere.com/docs/models"),
            "cost_tier": (
                "specialised",
                "https://docs.cohere.com/docs/models"),
            "max_output": (
                8000,
                "https://docs.cohere.com/docs/models"),
            "modalities": (
                [
                    "text",
                    "image",
                ],
                "https://docs.cohere.com/docs/models"),
            "role_notes": (
                "auditor role: Verify visual claims against source images.; "
                "director role: Assign all image-bearing subtasks here.; "
                "manager role: Vision-capable manager for doc pipelines.; "
                "worker role: Default Cohere vision worker..",
                "https://docs.cohere.com/docs/models"),
            "source_links": (
                [
                    "https://cohere.com/pricing",
                    "https://docs.cohere.com/docs/command-a",
                    "https://docs.cohere.com/docs/command-a-reasoning",
                    "https://docs.cohere.com/docs/command-a-vision",
                    "https://docs.cohere.com/docs/how-does-cohere-pricing-work",
                    "https://docs.cohere.com/docs/models",
                    "https://docs.cohere.com/docs/reasoning",
                    "https://docs.cohere.com/docs/structured-outputs",
                    "https://docs.cohere.com/docs/tool-use",
                ],
                "https://docs.cohere.com/docs/models"),
            "strengths": (
                "reads as strong on First Cohere image-input model: charts, "
                "OCR, tables, Official EN/PT/IT/FR/DE/ES support, 128K "
                "context.",
                "https://docs.cohere.com/docs/models"),
            "tool_calling": (
                False,
                "https://docs.cohere.com/docs/command-a-vision"),
            "weaknesses": (
                "watch out for 8K output cap, Language support narrower than "
                "text models, Price unpublished.",
                "https://docs.cohere.com/docs/models"),
        }),
        ("embed-v5.0-pro", {
            "avoid_for": (
                "less suited to chat generation, translation (use Translate "
                "model), speech tasks. Task fit: embeddings: best; long-doc: "
                "good; routing: good.",
                "https://docs.cohere.com/docs/models"),
            "best_for": (
                "suited to embeddings for search and RAG, classification and "
                "clustering, multimodal (text+image) retrieval. Task fit: "
                "embeddings: best; long-doc: good; routing: good.",
                "https://docs.cohere.com/docs/models"),
            "context_window": (
                128000,
                "https://docs.cohere.com/docs/models"),
            "cost_tier": (
                "specialised",
                "https://docs.cohere.com/docs/models"),
            "modalities": (
                [
                    "text",
                    "image",
                ],
                "https://docs.cohere.com/docs/models"),
            "role_notes": (
                "auditor role: Use for semantic duplicate detection.; "
                "director role: Retrieval backbone for RAG fleets.; manager "
                "role: Pre-filter context before LLM calls.; worker role: "
                "Embed-first step for search subtasks..",
                "https://docs.cohere.com/docs/models"),
            "source_links": (
                [
                    "https://cohere.com/pricing",
                    "https://docs.cohere.com/docs/command-a",
                    "https://docs.cohere.com/docs/command-a-reasoning",
                    "https://docs.cohere.com/docs/command-a-vision",
                    "https://docs.cohere.com/docs/how-does-cohere-pricing-work",
                    "https://docs.cohere.com/docs/models",
                    "https://docs.cohere.com/docs/reasoning",
                    "https://docs.cohere.com/docs/structured-outputs",
                    "https://docs.cohere.com/docs/tool-use",
                ],
                "https://docs.cohere.com/docs/models"),
            "strengths": (
                "reads as strong on Most capable Cohere embedding model, "
                "text+images+PDFs, Flexible dims 256-2048, "
                "cosine/dot/Euclidean, 128K context.",
                "https://docs.cohere.com/docs/models"),
            "tool_calling": (
                False,
                "https://docs.cohere.com/docs/tool-use"),
            "weaknesses": (
                "watch out for Higher latency than fast variant, Priced per "
                "embedded tokens, not chat tokens, No generative output.",
                "https://docs.cohere.com/docs/models"),
        }),
        ("rerank-v4.0-pro", {
            "avoid_for": (
                "less suited to generation or chat, embeddings, "
                "transcription. Task fit: embeddings: good; long-doc: good; "
                "routing: good.",
                "https://docs.cohere.com/docs/models"),
            "best_for": (
                "suited to reranking search results, RAG precision boost, "
                "multilingual retrieval (incl. JSON data). Task fit: "
                "embeddings: good; long-doc: good; routing: good.",
                "https://docs.cohere.com/docs/models"),
            "context_window": (
                32000,
                "https://docs.cohere.com/docs/models"),
            "cost_tier": (
                "specialised",
                "https://docs.cohere.com/docs/models"),
            "modalities": (
                [
                    "text",
                ],
                "https://docs.cohere.com/docs/models"),
            "role_notes": (
                "auditor role: Re-rank evidence before final answer.; "
                "director role: Quality gate for retrieval pipelines.; "
                "manager role: Add after bulk retrieval.; worker role: "
                "Rerank-then-answer pattern..",
                "https://docs.cohere.com/docs/models"),
            "source_links": (
                [
                    "https://cohere.com/pricing",
                    "https://docs.cohere.com/docs/command-a",
                    "https://docs.cohere.com/docs/command-a-reasoning",
                    "https://docs.cohere.com/docs/command-a-vision",
                    "https://docs.cohere.com/docs/how-does-cohere-pricing-work",
                    "https://docs.cohere.com/docs/models",
                    "https://docs.cohere.com/docs/reasoning",
                    "https://docs.cohere.com/docs/structured-outputs",
                    "https://docs.cohere.com/docs/tool-use",
                ],
                "https://docs.cohere.com/docs/models"),
            "strengths": (
                "reads as strong on SOTA quality multilingual rerank incl. "
                "semi-structured JSON, 32K context vs 4K on v3.5, Pairs with "
                "Embed for search stacks.",
                "https://docs.cohere.com/docs/models"),
            "tool_calling": (
                False,
                "https://docs.cohere.com/docs/tool-use"),
            "weaknesses": (
                "watch out for Priced per search, not tokens, Slower than "
                "fast variant, No generation.",
                "https://docs.cohere.com/docs/models"),
        }),
    ],
    "deepseek": [
        ("deepseek-v4-pro", {
            "avoid_for": (
                "less suited to cutoff-sensitive factual QA, vision input "
                "tasks, simple bulk jobs where flash is cheaper. Task fit: "
                "agent-loop: best; code-gen: best; code-review: best; "
                "long-doc: good; math-reasoning: best; planning: best; "
                "routing: ok; short-chat: good.",
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "best_for": (
                "suited to agent loops, code generation and review, hard "
                "reasoning and planning. Task fit: agent-loop: best; "
                "code-gen: best; code-review: best; long-doc: good; "
                "math-reasoning: best; planning: best; routing: ok; "
                "short-chat: good.",
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "context_window": (
                1000000,
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "cost_tier": (
                "strong-reasoning",
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "currency": (
                "USD",
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "input_token_price": (
                1.32,
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "max_output": (
                384000,
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "modalities": (
                [
                    "text",
                ],
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "output_token_price": (
                3.96,
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "price_effective_at": (
                "2026-10-11",
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "reasoning": (
                True,
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "role_notes": (
                "auditor role: Use max effort for audit-grade review; "
                "preserve reasoning_content trace.; director role: Strongest "
                "DeepSeek planner; use for hard decomposition.; manager "
                "role: Good multi-step delegator; schedule off-peak to halve "
                "cost.; worker role: Best quality code-gen worker when cost "
                "is secondary..",
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "source_links": (
                [
                    "https://api-docs.deepseek.com/guides/thinking_mode",
                    "https://api-docs.deepseek.com/guides/vision",
                    "https://api-docs.deepseek.com/quick_start/pricing",
                    "https://api-docs.deepseek.com/updates",
                ],
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "strengths": (
                "reads as strong on GA agent scores: Terminal-Bench 2.1 "
                "87.9, Toolathlon-Verified 74.1, Thinking effort "
                "low/high/max, default high, Supports tools, JSON, Responses "
                "API, Anthropic API.",
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "tool_calling": (
                True,
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "weaknesses": (
                "watch out for No vision input, Peak price 2x off-peak; "
                "concurrency limit 500, Knowledge cutoff not disclosed.",
                "https://api-docs.deepseek.com/quick_start/pricing"),
        }),
        ("deepseek-flash", {
            "avoid_for": (
                "less suited to max-quality deep reasoning (use v4-pro), "
                "cutoff-sensitive QA, tasks needing disclosed cutoff. Task "
                "fit: agent-loop: good; bulk-summary: best; code-gen: good; "
                "code-review: good; long-doc: good; routing: best; "
                "short-chat: best; vision: best.",
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "best_for": (
                "suited to cheap bulk chat and coding, vision QA and chart "
                "reading, high-throughput agent loops. Task fit: agent-loop: "
                "good; bulk-summary: best; code-gen: good; code-review: "
                "good; long-doc: good; routing: best; short-chat: best; "
                "vision: best.",
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "context_window": (
                1000000,
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "cost_tier": (
                "cheap-fast",
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "currency": (
                "USD",
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "input_token_price": (
                0.3,
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "max_output": (
                384000,
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "modalities": (
                [
                    "text",
                    "image",
                ],
                "https://api-docs.deepseek.com/guides/vision"),
            "output_token_price": (
                1.2,
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "price_effective_at": (
                "2026-10-11",
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "reasoning": (
                True,
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "role_notes": (
                "auditor role: Cheap re-check pass; vision claims need "
                "second source.; director role: Default router choice for "
                "cost-aware delegation.; manager role: Good fan-out worker; "
                "batch off-peak.; worker role: Default worker for code, "
                "vision, bulk summary..",
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "source_links": (
                [
                    "https://api-docs.deepseek.com/guides/thinking_mode",
                    "https://api-docs.deepseek.com/guides/vision",
                    "https://api-docs.deepseek.com/quick_start/pricing",
                    "https://api-docs.deepseek.com/updates",
                ],
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "strengths": (
                "reads as strong on Native multimodal vision "
                "(JPEG/PNG/GIF/WebP, 600 images max), Peak input $0.30/1M, "
                "off-peak half; concurrency 2500, Benchmarks: GPQA Diamond "
                "90.9, Terminal-Bench 2.1 90.6.",
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "tool_calling": (
                True,
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "weaknesses": (
                "watch out for Weaker than pro on hard agent benchmarks, "
                "Knowledge cutoff not disclosed, Thinking mode disables "
                "temperature penalties (fixed behavior).",
                "https://api-docs.deepseek.com/quick_start/pricing"),
        }),
        ("deepseek-v4-flash", {
            "avoid_for": (
                "less suited to new integrations (use deepseek-flash), "
                "expecting original V4-Flash weights, cutoff-sensitive QA. "
                "Task fit: agent-loop: ok; bulk-summary: good; code-gen: "
                "good; routing: ok; short-chat: best.",
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "best_for": (
                "suited to legacy code still calling deepseek-v4-flash, "
                "cheap bulk chat during migration. Task fit: agent-loop: ok; "
                "bulk-summary: good; code-gen: good; routing: ok; "
                "short-chat: best.",
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "context_window": (
                1000000,
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "cost_tier": (
                "cheap-fast",
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "currency": (
                "USD",
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "input_token_price": (
                0.3,
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "max_output": (
                384000,
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "output_token_price": (
                1.2,
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "price_effective_at": (
                "2026-10-11",
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "reasoning": (
                True,
                "https://api-docs.deepseek.com/guides/thinking_mode"),
            "role_notes": (
                "auditor role: Treat as flash alias; verify backend version "
                "in responses.; director role: Do not assign; migrate "
                "callers to deepseek-flash.; manager role: Temporary alias "
                "only.; worker role: Works as flash; prefer canonical id..",
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "source_links": (
                [
                    "https://api-docs.deepseek.com/guides/thinking_mode",
                    "https://api-docs.deepseek.com/guides/vision",
                    "https://api-docs.deepseek.com/quick_start/pricing",
                    "https://api-docs.deepseek.com/updates",
                ],
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "strengths": (
                "reads as strong on Still accepted; served by V4.1-Flash and "
                "billed at Flash price, Same 1M context and 384K output "
                "envelope.",
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "tool_calling": (
                True,
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "weaknesses": (
                "watch out for Backend retired; compatibility routing may "
                "end, Vision-exp variant behavior merged into flash.",
                "https://api-docs.deepseek.com/quick_start/pricing"),
        }),
        ("deepseek-v4-flash-vision-exp", {
            "avoid_for": (
                "less suited to new integrations (use deepseek-flash), "
                "general text-only bulk (use canonical flash id), "
                "cutoff-sensitive QA. Task fit: agent-loop: ok; "
                "bulk-summary: good; routing: ok; short-chat: best; vision: "
                "best.",
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "best_for": (
                "suited to legacy vision code calling the exp name, image QA "
                "during migration. Task fit: agent-loop: ok; bulk-summary: "
                "good; routing: ok; short-chat: best; vision: best.",
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "context_window": (
                1000000,
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "cost_tier": (
                "cheap-fast",
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "currency": (
                "USD",
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "input_token_price": (
                0.3,
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "max_output": (
                384000,
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "modalities": (
                [
                    "text",
                    "image",
                ],
                "https://api-docs.deepseek.com/guides/vision"),
            "output_token_price": (
                1.2,
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "price_effective_at": (
                "2026-10-11",
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "reasoning": (
                True,
                "https://api-docs.deepseek.com/guides/thinking_mode"),
            "role_notes": (
                "auditor role: Vision claims need second source; alias may "
                "vanish.; director role: Do not assign; migrate to "
                "deepseek-flash.; manager role: Temporary alias only.; "
                "worker role: Works as flash vision; prefer canonical id..",
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "source_links": (
                [
                    "https://api-docs.deepseek.com/guides/thinking_mode",
                    "https://api-docs.deepseek.com/guides/vision",
                    "https://api-docs.deepseek.com/quick_start/pricing",
                    "https://api-docs.deepseek.com/updates",
                ],
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "strengths": (
                "reads as strong on Still accepted; served by V4.1-Flash at "
                "Flash price, Vision capability preserved via flash backend.",
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "tool_calling": (
                True,
                "https://api-docs.deepseek.com/quick_start/pricing"),
            "weaknesses": (
                "watch out for Experimental backend retired; routing "
                "temporary, No separate benchmarks for the alias itself.",
                "https://api-docs.deepseek.com/quick_start/pricing"),
        }),
    ],
    "fireworks": [
        ("accounts/fireworks/models/gpt-oss-120b", {
            "avoid_for": (
                "less suited to 1M-context single-pass analysis. Task fit: "
                "routing: good; short-chat: good; code-gen: best; "
                "code-review: good; planning: best; math-reasoning: best; "
                "agent-loop: best.",
                "https://fireworks.ai/models/fireworks/gpt-oss-120b"),
            "best_for": (
                "suited to cheap agent-loop, code-gen. Task fit: routing: "
                "good; short-chat: good; code-gen: best; code-review: good; "
                "planning: best; math-reasoning: best; agent-loop: best.",
                "https://fireworks.ai/models/fireworks/gpt-oss-120b"),
            "context_window": (
                131072,
                "https://fireworks.ai/models"),
            "cost_tier": (
                "balanced",
                "https://fireworks.ai/models/fireworks/gpt-oss-120b"),
            "currency": (
                "USD",
                "https://docs.fireworks.ai/serverless/pricing"),
            "input_token_price": (
                0.15,
                "https://docs.fireworks.ai/serverless/pricing"),
            "modalities": (
                [
                    "text",
                ],
                "https://fireworks.ai/models/fireworks/gpt-oss-120b"),
            "output_token_price": (
                0.6,
                "https://docs.fireworks.ai/serverless/pricing"),
            "reasoning": (
                True,
                "https://fireworks.ai/models/fireworks/gpt-oss-120b"),
            "role_notes": (
                "director role: budget reasoning host; manager role: "
                "orchestration; worker role: execution; auditor role: verify.",
                "https://fireworks.ai/models/fireworks/gpt-oss-120b"),
            "source_links": (
                [
                    "https://docs.fireworks.ai/serverless/pricing",
                    "https://fireworks.ai/models",
                    "https://fireworks.ai/models/deepseek-ai/deepseek-v4p1-flash",
                    "https://fireworks.ai/models/fireworks/glm-5p3",
                    "https://fireworks.ai/models/fireworks/glm-5p3-flash",
                    "https://fireworks.ai/models/fireworks/gpt-oss-120b",
                    "https://fireworks.ai/models/fireworks/kimi-k3",
                    "https://fireworks.ai/models/fireworks/minimax-m3",
                    "https://fireworks.ai/models/fireworks/nemotron-lightning-3p5"
                    "-30b-a3b",
                ],
                "https://fireworks.ai/models/fireworks/gpt-oss-120b"),
            "strengths": (
                "reads as strong on $0.15/$0.60 with $0.015 cached input, "
                "fast serverless path available, tool + structured support.",
                "https://fireworks.ai/models/fireworks/gpt-oss-120b"),
            "tool_calling": (
                True,
                "https://fireworks.ai/models/fireworks/gpt-oss-120b"),
            "weaknesses": (
                "watch out for 131K context vs 1M rivals, open-weight "
                "ceiling.",
                "https://fireworks.ai/models/fireworks/gpt-oss-120b"),
        }),
        ("accounts/fireworks/models/glm-5p3", {
            "avoid_for": (
                "less suited to cheap bulk work. Task fit: long-doc: best; "
                "planning: best; math-reasoning: best; agent-loop: best; "
                "code-gen: best; code-review: best; routing: ok.",
                "https://fireworks.ai/models/fireworks/glm-5p3"),
            "best_for": (
                "suited to long-doc, planning over big context. Task fit: "
                "long-doc: best; planning: best; math-reasoning: best; "
                "agent-loop: best; code-gen: best; code-review: best; "
                "routing: ok.",
                "https://fireworks.ai/models/fireworks/glm-5p3"),
            "context_window": (
                1048576,
                "https://fireworks.ai/models"),
            "cost_tier": (
                "strong-reasoning",
                "https://fireworks.ai/models/fireworks/glm-5p3"),
            "currency": (
                "USD",
                "https://docs.fireworks.ai/serverless/pricing"),
            "input_token_price": (
                1.4,
                "https://docs.fireworks.ai/serverless/pricing"),
            "modalities": (
                [
                    "text",
                ],
                "https://fireworks.ai/models/fireworks/glm-5p3"),
            "output_token_price": (
                4.4,
                "https://docs.fireworks.ai/serverless/pricing"),
            "role_notes": (
                "director role: long-context flagship; manager role: "
                "big-context planning; worker role: deep execution; auditor "
                "role: citation checks.",
                "https://fireworks.ai/models/fireworks/glm-5p3"),
            "source_links": (
                [
                    "https://docs.fireworks.ai/serverless/pricing",
                    "https://fireworks.ai/models",
                    "https://fireworks.ai/models/deepseek-ai/deepseek-v4p1-flash",
                    "https://fireworks.ai/models/fireworks/glm-5p3",
                    "https://fireworks.ai/models/fireworks/glm-5p3-flash",
                    "https://fireworks.ai/models/fireworks/gpt-oss-120b",
                    "https://fireworks.ai/models/fireworks/kimi-k3",
                    "https://fireworks.ai/models/fireworks/minimax-m3",
                    "https://fireworks.ai/models/fireworks/nemotron-lightning-3p5"
                    "-30b-a3b",
                ],
                "https://fireworks.ai/models/fireworks/gpt-oss-120b"),
            "strengths": (
                "reads as strong on 1M context flagship, Fast variant for "
                "higher speed, cached input $0.26.",
                "https://fireworks.ai/models/fireworks/glm-5p3"),
            "tool_calling": (
                True,
                "https://fireworks.ai/models/fireworks/glm-5p3"),
            "weaknesses": (
                "watch out for premium price, US-region variant costs more.",
                "https://fireworks.ai/models/fireworks/glm-5p3"),
        }),
        ("accounts/fireworks/models/glm-5p3-flash", {
            "avoid_for": (
                "less suited to frontier reasoning finals. Task fit: "
                "bulk-summary: best; long-doc: best; routing: good; "
                "short-chat: good; code-gen: good; agent-loop: best; vision: "
                "good.",
                "https://fireworks.ai/models/fireworks/glm-5p3-flash"),
            "best_for": (
                "suited to bulk-summary, cheap long-doc triage. Task fit: "
                "bulk-summary: best; long-doc: best; routing: good; "
                "short-chat: good; code-gen: good; agent-loop: best; vision: "
                "good.",
                "https://fireworks.ai/models/fireworks/glm-5p3-flash"),
            "context_window": (
                1048576,
                "https://fireworks.ai/models"),
            "cost_tier": (
                "cheap-fast",
                "https://fireworks.ai/models/fireworks/glm-5p3-flash"),
            "currency": (
                "USD",
                "https://docs.fireworks.ai/serverless/pricing"),
            "input_token_price": (
                0.15,
                "https://docs.fireworks.ai/serverless/pricing"),
            "modalities": (
                [
                    "text",
                    "vision",
                ],
                "https://fireworks.ai/models/fireworks/glm-5p3-flash"),
            "output_token_price": (
                0.5,
                "https://docs.fireworks.ai/serverless/pricing"),
            "role_notes": (
                "director role: cheap long-context default; manager role: "
                "triage; worker role: summarize; auditor role: sample-verify.",
                "https://fireworks.ai/models/fireworks/glm-5p3-flash"),
            "source_links": (
                [
                    "https://docs.fireworks.ai/serverless/pricing",
                    "https://fireworks.ai/models",
                    "https://fireworks.ai/models/deepseek-ai/deepseek-v4p1-flash",
                    "https://fireworks.ai/models/fireworks/glm-5p3",
                    "https://fireworks.ai/models/fireworks/glm-5p3-flash",
                    "https://fireworks.ai/models/fireworks/gpt-oss-120b",
                    "https://fireworks.ai/models/fireworks/kimi-k3",
                    "https://fireworks.ai/models/fireworks/minimax-m3",
                    "https://fireworks.ai/models/fireworks/nemotron-lightning-3p5"
                    "-30b-a3b",
                ],
                "https://fireworks.ai/models/fireworks/gpt-oss-120b"),
            "strengths": (
                "reads as strong on 1M context at $0.15/$0.50, vision tagged "
                "on model library, best value long-context.",
                "https://fireworks.ai/models/fireworks/glm-5p3-flash"),
            "tool_calling": (
                True,
                "https://fireworks.ai/models/fireworks/glm-5p3-flash"),
            "weaknesses": (
                "watch out for below full 5.3 on hardest tasks, "
                "preview-fresh snapshot.",
                "https://fireworks.ai/models/fireworks/glm-5p3-flash"),
        }),
        ("accounts/fireworks/models/kimi-k3", {
            "avoid_for": (
                "less suited to cost-sensitive work. Task fit: vision: best; "
                "long-doc: best; agent-loop: best; code-gen: best; planning: "
                "best; routing: ok; short-chat: good.",
                "https://fireworks.ai/models/fireworks/kimi-k3"),
            "best_for": (
                "suited to premium vision agent-loop. Task fit: vision: "
                "best; long-doc: best; agent-loop: best; code-gen: best; "
                "planning: best; routing: ok; short-chat: good.",
                "https://fireworks.ai/models/fireworks/kimi-k3"),
            "context_window": (
                1048576,
                "https://fireworks.ai/models"),
            "cost_tier": (
                "strong-reasoning",
                "https://fireworks.ai/models/fireworks/kimi-k3"),
            "currency": (
                "USD",
                "https://docs.fireworks.ai/serverless/pricing"),
            "input_token_price": (
                3.0,
                "https://docs.fireworks.ai/serverless/pricing"),
            "modalities": (
                [
                    "text",
                    "vision",
                ],
                "https://fireworks.ai/models/fireworks/kimi-k3"),
            "output_token_price": (
                15.0,
                "https://docs.fireworks.ai/serverless/pricing"),
            "role_notes": (
                "director role: premium vision pick; manager role: "
                "multimodal planning; worker role: vision execution; auditor "
                "role: cost and grounding checks.",
                "https://fireworks.ai/models/fireworks/kimi-k3"),
            "source_links": (
                [
                    "https://docs.fireworks.ai/serverless/pricing",
                    "https://fireworks.ai/models",
                    "https://fireworks.ai/models/deepseek-ai/deepseek-v4p1-flash",
                    "https://fireworks.ai/models/fireworks/glm-5p3",
                    "https://fireworks.ai/models/fireworks/glm-5p3-flash",
                    "https://fireworks.ai/models/fireworks/gpt-oss-120b",
                    "https://fireworks.ai/models/fireworks/kimi-k3",
                    "https://fireworks.ai/models/fireworks/minimax-m3",
                    "https://fireworks.ai/models/fireworks/nemotron-lightning-3p5"
                    "-30b-a3b",
                ],
                "https://fireworks.ai/models/fireworks/gpt-oss-120b"),
            "strengths": (
                "reads as strong on 1M vision+text flagship, Fast and "
                "US-region variants, strong agentic coding lineage.",
                "https://fireworks.ai/models/fireworks/kimi-k3"),
            "tool_calling": (
                True,
                "https://fireworks.ai/models/fireworks/kimi-k3"),
            "weaknesses": (
                "watch out for highest price ($3/$15), cost volatile across "
                "variants.",
                "https://fireworks.ai/models/fireworks/kimi-k3"),
        }),
        ("accounts/fireworks/models/deepseek-v4p1-flash", {
            "avoid_for": (
                "less suited to hardest math finals. Task fit: long-doc: "
                "best; vision: good; bulk-summary: best; code-gen: good; "
                "agent-loop: best; routing: good; short-chat: good.",
                "https://fireworks.ai/models/deepseek-ai/deepseek-v4p1-flash"),
            "best_for": (
                "suited to cheap long-doc + vision triage. Task fit: "
                "long-doc: best; vision: good; bulk-summary: best; code-gen: "
                "good; agent-loop: best; routing: good; short-chat: good.",
                "https://fireworks.ai/models/deepseek-ai/deepseek-v4p1-flash"),
            "context_window": (
                1048576,
                "https://fireworks.ai/models"),
            "cost_tier": (
                "balanced",
                "https://fireworks.ai/models/deepseek-ai/deepseek-v4p1-flash"),
            "currency": (
                "USD",
                "https://docs.fireworks.ai/serverless/pricing"),
            "input_token_price": (
                0.3,
                "https://docs.fireworks.ai/serverless/pricing"),
            "modalities": (
                [
                    "text",
                    "vision",
                ],
                "https://fireworks.ai/models/deepseek-ai/deepseek-v4p1-flash"),
            "output_token_price": (
                1.2,
                "https://docs.fireworks.ai/serverless/pricing"),
            "role_notes": (
                "director role: value reasoning-vision pick; manager role: "
                "triage and dispatch; worker role: analyze and summarize; "
                "auditor role: spot-check.",
                "https://fireworks.ai/models/deepseek-ai/deepseek-v4p1-flash"),
            "source_links": (
                [
                    "https://docs.fireworks.ai/serverless/pricing",
                    "https://fireworks.ai/models",
                    "https://fireworks.ai/models/deepseek-ai/deepseek-v4p1-flash",
                    "https://fireworks.ai/models/fireworks/glm-5p3",
                    "https://fireworks.ai/models/fireworks/glm-5p3-flash",
                    "https://fireworks.ai/models/fireworks/gpt-oss-120b",
                    "https://fireworks.ai/models/fireworks/kimi-k3",
                    "https://fireworks.ai/models/fireworks/minimax-m3",
                    "https://fireworks.ai/models/fireworks/nemotron-lightning-3p5"
                    "-30b-a3b",
                ],
                "https://fireworks.ai/models/fireworks/gpt-oss-120b"),
            "strengths": (
                "reads as strong on 1M context at $0.30/$1.20, cached input "
                "only $0.006, vision-tagged Flash.",
                "https://fireworks.ai/models/deepseek-ai/deepseek-v4p1-flash"),
            "tool_calling": (
                True,
                "https://fireworks.ai/models/deepseek-ai/deepseek-v4p1-flash"),
            "weaknesses": (
                "watch out for Flash tier below Pro on depth, very new "
                "snapshot.",
                "https://fireworks.ai/models/deepseek-ai/deepseek-v4p1-flash"),
        }),
        ("accounts/fireworks/models/minimax-m3", {
            "avoid_for": (
                "less suited to 1M single-pass repos. Task fit: long-doc: "
                "best; bulk-summary: best; short-chat: good; routing: good; "
                "code-gen: good; agent-loop: good.",
                "https://fireworks.ai/models/fireworks/minimax-m3"),
            "best_for": (
                "suited to mid-long-doc, bulk-summary. Task fit: long-doc: "
                "best; bulk-summary: best; short-chat: good; routing: good; "
                "code-gen: good; agent-loop: good.",
                "https://fireworks.ai/models/fireworks/minimax-m3"),
            "context_window": (
                512000,
                "https://fireworks.ai/models"),
            "cost_tier": (
                "balanced",
                "https://fireworks.ai/models/fireworks/minimax-m3"),
            "currency": (
                "USD",
                "https://docs.fireworks.ai/serverless/pricing"),
            "input_token_price": (
                0.3,
                "https://docs.fireworks.ai/serverless/pricing"),
            "modalities": (
                [
                    "text",
                ],
                "https://fireworks.ai/models/fireworks/minimax-m3"),
            "output_token_price": (
                1.2,
                "https://docs.fireworks.ai/serverless/pricing"),
            "role_notes": (
                "director role: mid-context value pick; manager role: doc "
                "pipelines; worker role: summarize; auditor role: fidelity "
                "checks.",
                "https://fireworks.ai/models/fireworks/minimax-m3"),
            "source_links": (
                [
                    "https://docs.fireworks.ai/serverless/pricing",
                    "https://fireworks.ai/models",
                    "https://fireworks.ai/models/deepseek-ai/deepseek-v4p1-flash",
                    "https://fireworks.ai/models/fireworks/glm-5p3",
                    "https://fireworks.ai/models/fireworks/glm-5p3-flash",
                    "https://fireworks.ai/models/fireworks/gpt-oss-120b",
                    "https://fireworks.ai/models/fireworks/kimi-k3",
                    "https://fireworks.ai/models/fireworks/minimax-m3",
                    "https://fireworks.ai/models/fireworks/nemotron-lightning-3p5"
                    "-30b-a3b",
                ],
                "https://fireworks.ai/models/fireworks/gpt-oss-120b"),
            "strengths": (
                "reads as strong on 512K context at $0.30/$1.20, cached "
                "input $0.06, efficient mid-tier.",
                "https://fireworks.ai/models/fireworks/minimax-m3"),
            "tool_calling": (
                True,
                "https://fireworks.ai/models/fireworks/minimax-m3"),
            "weaknesses": (
                "watch out for 512K below 1M rivals, narrower tooling "
                "ecosystem.",
                "https://fireworks.ai/models/fireworks/minimax-m3"),
        }),
        ("accounts/fireworks/models/nemotron-lightning-3p5-30b-a3b", {
            "avoid_for": (
                "less suited to frontier planning finals. Task fit: routing: "
                "best; short-chat: best; bulk-summary: best; code-gen: good; "
                "agent-loop: good; long-doc: good.",
                "https://fireworks.ai/models/fireworks/nemotron-lightning-3p5"
                "-30b-a3b"),
            "best_for": (
                "suited to routing, bulk short-chat, cheap agent fan-out. "
                "Task fit: routing: best; short-chat: best; bulk-summary: "
                "best; code-gen: good; agent-loop: good; long-doc: good.",
                "https://fireworks.ai/models/fireworks/nemotron-lightning-3p5"
                "-30b-a3b"),
            "context_window": (
                262144,
                "https://fireworks.ai/models"),
            "cost_tier": (
                "cheap-fast",
                "https://fireworks.ai/models/fireworks/nemotron-lightning-3p5"
                "-30b-a3b"),
            "currency": (
                "USD",
                "https://docs.fireworks.ai/serverless/pricing"),
            "input_token_price": (
                0.05,
                "https://docs.fireworks.ai/serverless/pricing"),
            "modalities": (
                [
                    "text",
                ],
                "https://fireworks.ai/models/fireworks/nemotron-lightning-3p5"
                "-30b-a3b"),
            "output_token_price": (
                0.2,
                "https://docs.fireworks.ai/serverless/pricing"),
            "reasoning": (
                True,
                "https://fireworks.ai/models/fireworks/nemotron-lightning-3p5"
                "-30b-a3b"),
            "role_notes": (
                "director role: cheapest fan-out pick; manager role: mass "
                "dispatch; worker role: short generations; auditor role: "
                "verify, low trust.",
                "https://fireworks.ai/models/fireworks/nemotron-lightning-3p5"
                "-30b-a3b"),
            "source_links": (
                [
                    "https://docs.fireworks.ai/serverless/pricing",
                    "https://fireworks.ai/models",
                    "https://fireworks.ai/models/deepseek-ai/deepseek-v4p1-flash",
                    "https://fireworks.ai/models/fireworks/glm-5p3",
                    "https://fireworks.ai/models/fireworks/glm-5p3-flash",
                    "https://fireworks.ai/models/fireworks/gpt-oss-120b",
                    "https://fireworks.ai/models/fireworks/kimi-k3",
                    "https://fireworks.ai/models/fireworks/minimax-m3",
                    "https://fireworks.ai/models/fireworks/nemotron-lightning-3p5"
                    "-30b-a3b",
                ],
                "https://fireworks.ai/models/fireworks/gpt-oss-120b"),
            "strengths": (
                "reads as strong on cheapest hosted reasoning ($0.05/$0.20), "
                "262K context, tool + structured support.",
                "https://fireworks.ai/models/fireworks/nemotron-lightning-3p5"
                "-30b-a3b"),
            "tool_calling": (
                True,
                "https://fireworks.ai/models/fireworks/nemotron-lightning-3p5"
                "-30b-a3b"),
            "weaknesses": (
                "watch out for 30B quality ceiling, narrow eval history.",
                "https://fireworks.ai/models/fireworks/nemotron-lightning-3p5"
                "-30b-a3b"),
        }),
    ],
    "google": [
        ("gemini-3.8-flash", {
            "avoid_for": (
                "less suited to real-time voice (use Live models), image "
                "generation (use Nano Banana), sub-second latency bulk work. "
                "Task fit: agent-loop: best; code-gen: best; code-review: "
                "best; long-doc: best; math-reasoning: best; planning: best; "
                "routing: best; short-chat: good; vision: good.",
                "https://ai.google.dev/gemini-api/docs/models"),
            "best_for": (
                "suited to agent loops, long-horizon software engineering, "
                "enterprise workflows, long-context reasoning. Task fit: "
                "agent-loop: best; code-gen: best; code-review: best; "
                "long-doc: best; math-reasoning: best; planning: best; "
                "routing: best; short-chat: good; vision: good.",
                "https://ai.google.dev/gemini-api/docs/models"),
            "context_window": (
                1048576,
                "https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flas"
                "h"),
            "cost_tier": (
                "balanced",
                "https://ai.google.dev/gemini-api/docs/models"),
            "currency": (
                "USD",
                "https://ai.google.dev/gemini-api/docs/pricing"),
            "input_token_price": (
                0.75,
                "https://ai.google.dev/gemini-api/docs/pricing"),
            "max_output": (
                65536,
                "https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flas"
                "h"),
            "modalities": (
                [
                    "text",
                    "image",
                    "video",
                    "audio",
                    "pdf",
                ],
                "https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flas"
                "h"),
            "output_token_price": (
                3.75,
                "https://ai.google.dev/gemini-api/docs/pricing"),
            "reasoning": (
                True,
                "https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flas"
                "h"),
            "role_notes": (
                "auditor role: good for cited long-doc audit with search "
                "grounding; director role: best default for planning + "
                "routing; manager role: best for decomposing multi-step "
                "work; worker role: best for code-gen and agent-loop "
                "execution.",
                "https://ai.google.dev/gemini-api/docs/models"),
            "source_links": (
                [
                    "https://ai.google.dev/gemini-api/docs/deprecations",
                    "https://ai.google.dev/gemini-api/docs/models",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flas"
                    "h",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-2.5-pro",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flas"
                    "h-lite",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-"
                    "preview",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flas"
                    "h-lite",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flas"
                    "h",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flas"
                    "h",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-embeddin"
                    "g-001",
                    "https://ai.google.dev/gemini-api/docs/pricing",
                ],
                "https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flas"
                "h"),
            "strengths": (
                "reads as strong on flagship Flash intelligence; thinking "
                "(low/medium/high); function calling + structured outputs; "
                "search/Maps grounding; code execution; 1M context.",
                "https://ai.google.dev/gemini-api/docs/models"),
            "tool_calling": (
                True,
                "https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flas"
                "h"),
            "weaknesses": (
                "watch out for promo pricing expires 2026-12-31 (doubles "
                "2027-01-01); 65k output cap; no native image output.",
                "https://ai.google.dev/gemini-api/docs/models"),
        }),
        ("gemini-3.6-flash", {
            "avoid_for": (
                "less suited to bleeding-edge reasoning max (use 3.1 Pro "
                "preview or 3.8 Flash). Task fit: agent-loop: good; "
                "code-gen: good; long-doc: good; planning: good; routing: "
                "good; short-chat: best; vision: good.",
                "https://ai.google.dev/gemini-api/docs/models"),
            "best_for": (
                "suited to general agentic tasks, everyday multimodal work, "
                "chat + tool use. Task fit: agent-loop: good; code-gen: "
                "good; long-doc: good; planning: good; routing: good; "
                "short-chat: best; vision: good.",
                "https://ai.google.dev/gemini-api/docs/models"),
            "context_window": (
                1048576,
                "https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flas"
                "h"),
            "cost_tier": (
                "balanced",
                "https://ai.google.dev/gemini-api/docs/models"),
            "currency": (
                "USD",
                "https://ai.google.dev/gemini-api/docs/pricing"),
            "input_token_price": (
                0.75,
                "https://ai.google.dev/gemini-api/docs/pricing"),
            "max_output": (
                65536,
                "https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flas"
                "h"),
            "modalities": (
                [
                    "text",
                    "image",
                    "video",
                    "audio",
                    "pdf",
                ],
                "https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flas"
                "h"),
            "output_token_price": (
                3.75,
                "https://ai.google.dev/gemini-api/docs/pricing"),
            "reasoning": (
                True,
                "https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flas"
                "h"),
            "role_notes": (
                "auditor role: good for review with grounding; director "
                "role: good planner fallback; manager role: good task "
                "splitter; worker role: good executor.",
                "https://ai.google.dev/gemini-api/docs/models"),
            "source_links": (
                [
                    "https://ai.google.dev/gemini-api/docs/deprecations",
                    "https://ai.google.dev/gemini-api/docs/models",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flas"
                    "h",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-2.5-pro",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flas"
                    "h-lite",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-"
                    "preview",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flas"
                    "h-lite",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flas"
                    "h",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flas"
                    "h",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-embeddin"
                    "g-001",
                    "https://ai.google.dev/gemini-api/docs/pricing",
                ],
                "https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flas"
                "h"),
            "strengths": (
                "reads as strong on previous-gen Flash balancing speed and "
                "multimodal ability; grounding + caching support.",
                "https://ai.google.dev/gemini-api/docs/models"),
            "tool_calling": (
                True,
                "https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flas"
                "h"),
            "weaknesses": (
                "watch out for superseded by 3.8 Flash; promo pricing "
                "expires end 2026.",
                "https://ai.google.dev/gemini-api/docs/models"),
        }),
        ("gemini-3.5-flash-lite", {
            "avoid_for": (
                "less suited to deep reasoning, large code refactors. Task "
                "fit: agent-loop: ok; bulk-summary: best; routing: best; "
                "short-chat: best; translation-uk-en: good.",
                "https://ai.google.dev/gemini-api/docs/models"),
            "best_for": (
                "suited to high-volume agentic tasks, translation, simple "
                "data processing, bulk summary. Task fit: agent-loop: ok; "
                "bulk-summary: best; routing: best; short-chat: best; "
                "translation-uk-en: good.",
                "https://ai.google.dev/gemini-api/docs/models"),
            "context_window": (
                1048576,
                "https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flas"
                "h-lite"),
            "cost_tier": (
                "cheap-fast",
                "https://ai.google.dev/gemini-api/docs/models"),
            "currency": (
                "USD",
                "https://ai.google.dev/gemini-api/docs/pricing"),
            "input_token_price": (
                0.3,
                "https://ai.google.dev/gemini-api/docs/pricing"),
            "max_output": (
                65536,
                "https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flas"
                "h-lite"),
            "modalities": (
                [
                    "text",
                    "image",
                    "video",
                    "audio",
                    "pdf",
                ],
                "https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flas"
                "h-lite"),
            "output_token_price": (
                2.5,
                "https://ai.google.dev/gemini-api/docs/pricing"),
            "reasoning": (
                True,
                "https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flas"
                "h-lite"),
            "role_notes": (
                "auditor role: ok for cheap first-pass triage; director "
                "role: good for routing/bulk dispatch; manager role: good "
                "for fan-out; worker role: best for bulk-summary and "
                "short-chat.",
                "https://ai.google.dev/gemini-api/docs/models"),
            "source_links": (
                [
                    "https://ai.google.dev/gemini-api/docs/deprecations",
                    "https://ai.google.dev/gemini-api/docs/models",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flas"
                    "h",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-2.5-pro",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flas"
                    "h-lite",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-"
                    "preview",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flas"
                    "h-lite",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flas"
                    "h",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flas"
                    "h",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-embeddin"
                    "g-001",
                    "https://ai.google.dev/gemini-api/docs/pricing",
                ],
                "https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flas"
                "h"),
            "strengths": (
                "reads as strong on cheapest current chat Flash; grounding "
                "support; batch/flex discounts.",
                "https://ai.google.dev/gemini-api/docs/models"),
            "tool_calling": (
                True,
                "https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flas"
                "h-lite"),
            "weaknesses": (
                "watch out for weaker reasoning vs Flash/Pro; no context "
                "caching on standard tier per pricing page.",
                "https://ai.google.dev/gemini-api/docs/models"),
        }),
        ("gemini-3.1-flash-lite", {
            "avoid_for": (
                "less suited to frontier reasoning, heavy agentic coding. "
                "Task fit: bulk-summary: best; routing: best; short-chat: "
                "best; translation-uk-en: good.",
                "https://ai.google.dev/gemini-api/docs/models"),
            "best_for": (
                "suited to high-frequency lightweight tasks, translation, "
                "cheap bulk processing. Task fit: bulk-summary: best; "
                "routing: best; short-chat: best; translation-uk-en: good.",
                "https://ai.google.dev/gemini-api/docs/models"),
            "context_window": (
                1048576,
                "https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flas"
                "h-lite"),
            "cost_tier": (
                "cheap-fast",
                "https://ai.google.dev/gemini-api/docs/models"),
            "currency": (
                "USD",
                "https://ai.google.dev/gemini-api/docs/pricing"),
            "input_token_price": (
                0.25,
                "https://ai.google.dev/gemini-api/docs/pricing"),
            "max_output": (
                65536,
                "https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flas"
                "h-lite"),
            "modalities": (
                [
                    "text",
                    "image",
                    "video",
                    "audio",
                    "pdf",
                ],
                "https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flas"
                "h-lite"),
            "output_token_price": (
                1.5,
                "https://ai.google.dev/gemini-api/docs/pricing"),
            "reasoning": (
                True,
                "https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flas"
                "h-lite"),
            "role_notes": (
                "auditor role: avoid as sole auditor; director role: good "
                "cheap router; manager role: good for splitting bulk work; "
                "worker role: best for cheap fast drafts.",
                "https://ai.google.dev/gemini-api/docs/models"),
            "source_links": (
                [
                    "https://ai.google.dev/gemini-api/docs/deprecations",
                    "https://ai.google.dev/gemini-api/docs/models",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flas"
                    "h",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-2.5-pro",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flas"
                    "h-lite",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-"
                    "preview",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flas"
                    "h-lite",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flas"
                    "h",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flas"
                    "h",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-embeddin"
                    "g-001",
                    "https://ai.google.dev/gemini-api/docs/pricing",
                ],
                "https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flas"
                "h"),
            "strengths": (
                "reads as strong on lowest text input price of Gemini chat "
                "line; audio input supported at higher rate.",
                "https://ai.google.dev/gemini-api/docs/models"),
            "tool_calling": (
                True,
                "https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flas"
                "h-lite"),
            "weaknesses": (
                "watch out for lowest capability tier; audio input costs 2x "
                "text rate.",
                "https://ai.google.dev/gemini-api/docs/models"),
        }),
        ("gemini-3.1-pro-preview", {
            "avoid_for": (
                "less suited to cheap bulk work, latency-sensitive simple "
                "chat. Task fit: agent-loop: good; code-gen: best; long-doc: "
                "best; math-reasoning: best; planning: best; vision: good.",
                "https://ai.google.dev/gemini-api/docs/models"),
            "best_for": (
                "suited to complex problem solving, multimodal "
                "understanding, vibe-coding, agentic planning. Task fit: "
                "agent-loop: good; code-gen: best; long-doc: best; "
                "math-reasoning: best; planning: best; vision: good.",
                "https://ai.google.dev/gemini-api/docs/models"),
            "context_window": (
                1048576,
                "https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-"
                "preview"),
            "cost_tier": (
                "strong-reasoning",
                "https://ai.google.dev/gemini-api/docs/models"),
            "currency": (
                "USD",
                "https://ai.google.dev/gemini-api/docs/pricing"),
            "input_token_price": (
                2.0,
                "https://ai.google.dev/gemini-api/docs/pricing"),
            "max_output": (
                65536,
                "https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-"
                "preview"),
            "modalities": (
                [
                    "text",
                    "image",
                    "video",
                    "audio",
                    "pdf",
                ],
                "https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-"
                "preview"),
            "output_token_price": (
                12.0,
                "https://ai.google.dev/gemini-api/docs/pricing"),
            "reasoning": (
                True,
                "https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-"
                "preview"),
            "role_notes": (
                "auditor role: best for deep audit; director role: best for "
                "hard planning; manager role: best for complex "
                "decomposition; worker role: best for hard code-gen.",
                "https://ai.google.dev/gemini-api/docs/models"),
            "source_links": (
                [
                    "https://ai.google.dev/gemini-api/docs/deprecations",
                    "https://ai.google.dev/gemini-api/docs/models",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flas"
                    "h",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-2.5-pro",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flas"
                    "h-lite",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-"
                    "preview",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flas"
                    "h-lite",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flas"
                    "h",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flas"
                    "h",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-embeddin"
                    "g-001",
                    "https://ai.google.dev/gemini-api/docs/pricing",
                ],
                "https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flas"
                "h"),
            "strengths": (
                "reads as strong on 3rd-gen Pro: multimodal understanding, "
                "agentic + vibe-coding focus; tiered long-prompt pricing.",
                "https://ai.google.dev/gemini-api/docs/models"),
            "tool_calling": (
                True,
                "https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-"
                "preview"),
            "weaknesses": (
                "watch out for preview status; no free tier; price jumps "
                "past 200k-token prompts ($4/$18).",
                "https://ai.google.dev/gemini-api/docs/models"),
        }),
        ("gemini-2.5-pro", {
            "avoid_for": (
                "less suited to new projects (Google advises 3.5 Flash-Lite "
                "or 3.8 Flash); real-time voice. Task fit: code-gen: best; "
                "code-review: best; long-doc: best; math-reasoning: best; "
                "planning: best.",
                "https://ai.google.dev/gemini-api/docs/models"),
            "best_for": (
                "suited to complex code/math/STEM reasoning, large codebase "
                "and dataset analysis (legacy continuity). Task fit: "
                "code-gen: best; code-review: best; long-doc: best; "
                "math-reasoning: best; planning: best.",
                "https://ai.google.dev/gemini-api/docs/models"),
            "context_window": (
                1048576,
                "https://ai.google.dev/gemini-api/docs/models/gemini-2.5-pro"),
            "cost_tier": (
                "strong-reasoning",
                "https://ai.google.dev/gemini-api/docs/models"),
            "knowledge_cutoff": (
                "2025-01-01",
                "https://ai.google.dev/gemini-api/docs/models/gemini-2.5-pro"),
            "max_output": (
                65536,
                "https://ai.google.dev/gemini-api/docs/models/gemini-2.5-pro"),
            "modalities": (
                [
                    "text",
                    "image",
                    "video",
                    "audio",
                    "pdf",
                ],
                "https://ai.google.dev/gemini-api/docs/models/gemini-2.5-pro"),
            "reasoning": (
                True,
                "https://ai.google.dev/gemini-api/docs/models/gemini-2.5-pro"),
            "role_notes": (
                "auditor role: good legacy auditor; director role: good "
                "legacy planner; manager role: good legacy decomposer; "
                "worker role: good legacy coder.",
                "https://ai.google.dev/gemini-api/docs/models"),
            "source_links": (
                [
                    "https://ai.google.dev/gemini-api/docs/deprecations",
                    "https://ai.google.dev/gemini-api/docs/models",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flas"
                    "h",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-2.5-pro",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flas"
                    "h-lite",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-"
                    "preview",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flas"
                    "h-lite",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flas"
                    "h",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flas"
                    "h",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-embeddin"
                    "g-001",
                    "https://ai.google.dev/gemini-api/docs/pricing",
                ],
                "https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flas"
                "h"),
            "strengths": (
                "reads as strong on state-of-the-art 2.5 thinking model; "
                "search grounding; file search; URL context.",
                "https://ai.google.dev/gemini-api/docs/models"),
            "tool_calling": (
                True,
                "https://ai.google.dev/gemini-api/docs/models/gemini-2.5-pro"),
            "weaknesses": (
                "watch out for access restricted to past users; capacity "
                "reserved for legacy workflows; price not re-verified this "
                "session.",
                "https://ai.google.dev/gemini-api/docs/models"),
        }),
        ("gemini-2.5-flash", {
            "avoid_for": (
                "less suited to new projects (use 3.5 Flash-Lite or 3.8 "
                "Flash per Google note). Task fit: agent-loop: good; "
                "bulk-summary: good; routing: good; short-chat: best.",
                "https://ai.google.dev/gemini-api/docs/models"),
            "best_for": (
                "suited to price-performance legacy workloads, large-scale "
                "processing, low-latency high-volume thinking tasks. Task "
                "fit: agent-loop: good; bulk-summary: good; routing: good; "
                "short-chat: best.",
                "https://ai.google.dev/gemini-api/docs/models"),
            "context_window": (
                1048576,
                "https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flas"
                "h"),
            "cost_tier": (
                "balanced",
                "https://ai.google.dev/gemini-api/docs/models"),
            "knowledge_cutoff": (
                "2025-01-01",
                "https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flas"
                "h"),
            "max_output": (
                65536,
                "https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flas"
                "h"),
            "modalities": (
                [
                    "text",
                    "image",
                    "video",
                    "audio",
                ],
                "https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flas"
                "h"),
            "reasoning": (
                True,
                "https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flas"
                "h"),
            "role_notes": (
                "auditor role: ok legacy triage; director role: good legacy "
                "router; manager role: good legacy fan-out; worker role: "
                "good legacy executor.",
                "https://ai.google.dev/gemini-api/docs/models"),
            "source_links": (
                [
                    "https://ai.google.dev/gemini-api/docs/deprecations",
                    "https://ai.google.dev/gemini-api/docs/models",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flas"
                    "h",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-2.5-pro",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flas"
                    "h-lite",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-"
                    "preview",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flas"
                    "h-lite",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flas"
                    "h",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flas"
                    "h",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-embeddin"
                    "g-001",
                    "https://ai.google.dev/gemini-api/docs/pricing",
                ],
                "https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flas"
                "h"),
            "strengths": (
                "reads as strong on best 2.5 price-performance; thinking "
                "support; agentic use cases.",
                "https://ai.google.dev/gemini-api/docs/models"),
            "tool_calling": (
                True,
                "https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flas"
                "h"),
            "weaknesses": (
                "watch out for access restricted to past users; superseded "
                "by Gemini 3 line.",
                "https://ai.google.dev/gemini-api/docs/models"),
        }),
        ("gemini-embedding-001", {
            "avoid_for": (
                "less suited to chat, code-gen, reasoning (not a generative "
                "model). Task fit: embeddings: best.",
                "https://ai.google.dev/gemini-api/docs/models"),
            "best_for": (
                "suited to semantic search, text classification, RAG "
                "embeddings. Task fit: embeddings: best.",
                "https://ai.google.dev/gemini-api/docs/models"),
            "context_window": (
                2048,
                "https://ai.google.dev/gemini-api/docs/models/gemini-embeddin"
                "g-001"),
            "cost_tier": (
                "specialised",
                "https://ai.google.dev/gemini-api/docs/models"),
            "modalities": (
                [
                    "text",
                ],
                "https://ai.google.dev/gemini-api/docs/models/gemini-embeddin"
                "g-001"),
            "role_notes": (
                "auditor role: good for retrieval-backed audit; director "
                "role: ok for memory retrieval; manager role: ok for context "
                "assembly; worker role: best for RAG lookup.",
                "https://ai.google.dev/gemini-api/docs/models"),
            "source_links": (
                [
                    "https://ai.google.dev/gemini-api/docs/deprecations",
                    "https://ai.google.dev/gemini-api/docs/models",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flas"
                    "h",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-2.5-pro",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flas"
                    "h-lite",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-"
                    "preview",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flas"
                    "h-lite",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flas"
                    "h",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flas"
                    "h",
                    "https://ai.google.dev/gemini-api/docs/models/gemini-embeddin"
                    "g-001",
                    "https://ai.google.dev/gemini-api/docs/pricing",
                ],
                "https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flas"
                "h"),
            "strengths": (
                "reads as strong on high-dimensional vectors; RAG-ready; "
                "successor gemini-embedding-2 available.",
                "https://ai.google.dev/gemini-api/docs/models"),
            "weaknesses": (
                "watch out for shutdown scheduled 2028-05-14; migrate to "
                "gemini-embedding-2.",
                "https://ai.google.dev/gemini-api/docs/models"),
        }),
    ],
    "groq": [
        ("openai/gpt-oss-120b", {
            "avoid_for": (
                "less suited to contexts over 131K, native vision, speech. "
                "Task fit: routing: good; short-chat: good; long-doc: good; "
                "code-gen: best; code-review: good; planning: best; "
                "math-reasoning: best; agent-loop: best.",
                "https://console.groq.com/docs/models"),
            "best_for": (
                "suited to agent-loop, code-gen, planning, math-reasoning at "
                "speed. Task fit: routing: good; short-chat: good; long-doc: "
                "good; code-gen: best; code-review: good; planning: best; "
                "math-reasoning: best; agent-loop: best.",
                "https://console.groq.com/docs/models"),
            "context_window": (
                131072,
                "https://console.groq.com/docs/model/openai/gpt-oss-120b"),
            "cost_tier": (
                "strong-reasoning",
                "https://console.groq.com/docs/models"),
            "currency": (
                "USD",
                "https://console.groq.com/docs/model/openai/gpt-oss-120b"),
            "input_token_price": (
                0.15,
                "https://console.groq.com/docs/model/openai/gpt-oss-120b"),
            "max_output": (
                65536,
                "https://console.groq.com/docs/model/openai/gpt-oss-120b"),
            "modalities": (
                [
                    "text",
                ],
                "https://console.groq.com/docs/model/openai/gpt-oss-120b"),
            "output_token_price": (
                0.6,
                "https://console.groq.com/docs/model/openai/gpt-oss-120b"),
            "reasoning": (
                True,
                "https://console.groq.com/docs/model/openai/gpt-oss-120b"),
            "role_notes": (
                "director role: default strong-reasoning Groq host pick; "
                "manager role: planning and orchestration; worker role: "
                "code-gen and agent execution; auditor role: re-verify "
                "chains and tool args.",
                "https://console.groq.com/docs/models"),
            "source_links": (
                [
                    "https://console.groq.com/docs/deprecations",
                    "https://console.groq.com/docs/model/llama-3.1-8b-instant",
                    "https://console.groq.com/docs/model/llama-3.3-70b-versatile",
                    "https://console.groq.com/docs/model/openai/gpt-oss-120b",
                    "https://console.groq.com/docs/model/openai/gpt-oss-20b",
                    "https://console.groq.com/docs/model/openai/gpt-oss-safeguard"
                    "-20b",
                    "https://console.groq.com/docs/model/qwen/qwen3.8-27b",
                    "https://console.groq.com/docs/model/whisper-large-v3-turbo",
                    "https://console.groq.com/docs/models",
                ],
                "https://console.groq.com/docs/model/openai/gpt-oss-120b"),
            "strengths": (
                "reads as strong on 120B open-weight reasoning at ~500 tps, "
                "built-in browser search and code execution, 131K context, "
                "65K max completion.",
                "https://console.groq.com/docs/models"),
            "tool_calling": (
                True,
                "https://console.groq.com/docs/model/openai/gpt-oss-120b"),
            "weaknesses": (
                "watch out for open-weight quality below frontier closed "
                "models, no native vision/speech on Groq.",
                "https://console.groq.com/docs/models"),
        }),
        ("openai/gpt-oss-20b", {
            "avoid_for": (
                "less suited to hard math-reasoning, complex planning. Task "
                "fit: routing: best; short-chat: best; long-doc: ok; "
                "code-gen: good; code-review: ok; planning: ok; "
                "math-reasoning: ok; agent-loop: good; bulk-summary: best.",
                "https://console.groq.com/docs/models"),
            "best_for": (
                "suited to routing, short-chat, bulk-summary drafts. Task "
                "fit: routing: best; short-chat: best; long-doc: ok; "
                "code-gen: good; code-review: ok; planning: ok; "
                "math-reasoning: ok; agent-loop: good; bulk-summary: best.",
                "https://console.groq.com/docs/models"),
            "context_window": (
                131072,
                "https://console.groq.com/docs/model/openai/gpt-oss-20b"),
            "cost_tier": (
                "cheap-fast",
                "https://console.groq.com/docs/models"),
            "currency": (
                "USD",
                "https://console.groq.com/docs/model/openai/gpt-oss-20b"),
            "input_token_price": (
                0.075,
                "https://console.groq.com/docs/model/openai/gpt-oss-20b"),
            "max_output": (
                65536,
                "https://console.groq.com/docs/model/openai/gpt-oss-20b"),
            "modalities": (
                [
                    "text",
                ],
                "https://console.groq.com/docs/model/openai/gpt-oss-20b"),
            "output_token_price": (
                0.3,
                "https://console.groq.com/docs/model/openai/gpt-oss-20b"),
            "reasoning": (
                True,
                "https://console.groq.com/docs/model/openai/gpt-oss-20b"),
            "role_notes": (
                "director role: cheap fast triage and routing; manager role: "
                "fan-out subtask dispatch; worker role: bulk short "
                "generations; auditor role: spot-check outputs, low trust "
                "for hard claims.",
                "https://console.groq.com/docs/models"),
            "source_links": (
                [
                    "https://console.groq.com/docs/deprecations",
                    "https://console.groq.com/docs/model/llama-3.1-8b-instant",
                    "https://console.groq.com/docs/model/llama-3.3-70b-versatile",
                    "https://console.groq.com/docs/model/openai/gpt-oss-120b",
                    "https://console.groq.com/docs/model/openai/gpt-oss-20b",
                    "https://console.groq.com/docs/model/openai/gpt-oss-safeguard"
                    "-20b",
                    "https://console.groq.com/docs/model/qwen/qwen3.8-27b",
                    "https://console.groq.com/docs/model/whisper-large-v3-turbo",
                    "https://console.groq.com/docs/models",
                ],
                "https://console.groq.com/docs/model/openai/gpt-oss-120b"),
            "strengths": (
                "reads as strong on cheapest Groq reasoning host, ~1000 tps "
                "ideal for routing and short chat, same 131K context as 120B.",
                "https://console.groq.com/docs/models"),
            "tool_calling": (
                True,
                "https://console.groq.com/docs/model/openai/gpt-oss-20b"),
            "weaknesses": (
                "watch out for 21B-class quality, weaker deep reasoning, not "
                "for hard math or long complex plans.",
                "https://console.groq.com/docs/models"),
        }),
        ("llama-3.3-70b-versatile", {
            "avoid_for": (
                "less suited to new builds; use gpt-oss-120b instead. Task "
                "fit: routing: good; short-chat: best; long-doc: good; "
                "code-gen: good; code-review: good; planning: good; "
                "math-reasoning: ok; agent-loop: good.",
                "https://console.groq.com/docs/models"),
            "best_for": (
                "suited to legacy production compat, general chat. Task fit: "
                "routing: good; short-chat: best; long-doc: good; code-gen: "
                "good; code-review: good; planning: good; math-reasoning: "
                "ok; agent-loop: good.",
                "https://console.groq.com/docs/models"),
            "context_window": (
                131072,
                "https://console.groq.com/docs/model/llama-3.3-70b-versatile"),
            "cost_tier": (
                "balanced",
                "https://console.groq.com/docs/models"),
            "max_output": (
                32768,
                "https://console.groq.com/docs/model/llama-3.3-70b-versatile"),
            "modalities": (
                [
                    "text",
                ],
                "https://console.groq.com/docs/model/llama-3.3-70b-versatile"),
            "reasoning": (
                False,
                "https://console.groq.com/docs/model/llama-3.3-70b-versatile"),
            "role_notes": (
                "director role: legacy only, migrate off; manager role: "
                "compat routing; worker role: general text tasks; auditor "
                "role: flag deprecated usage.",
                "https://console.groq.com/docs/models"),
            "source_links": (
                [
                    "https://console.groq.com/docs/deprecations",
                    "https://console.groq.com/docs/model/llama-3.1-8b-instant",
                    "https://console.groq.com/docs/model/llama-3.3-70b-versatile",
                    "https://console.groq.com/docs/model/openai/gpt-oss-120b",
                    "https://console.groq.com/docs/model/openai/gpt-oss-20b",
                    "https://console.groq.com/docs/model/openai/gpt-oss-safeguard"
                    "-20b",
                    "https://console.groq.com/docs/model/qwen/qwen3.8-27b",
                    "https://console.groq.com/docs/model/whisper-large-v3-turbo",
                    "https://console.groq.com/docs/models",
                ],
                "https://console.groq.com/docs/model/openai/gpt-oss-120b"),
            "strengths": (
                "reads as strong on proven 70B instruct quality, 280 tps "
                "production history, 131K context.",
                "https://console.groq.com/docs/models"),
            "tool_calling": (
                True,
                "https://console.groq.com/docs/model/llama-3.3-70b-versatile"),
            "weaknesses": (
                "watch out for deprecated for free/developer tiers "
                "2026-08-16, Contact Sales pricing, no public rate.",
                "https://console.groq.com/docs/models"),
        }),
        ("llama-3.1-8b-instant", {
            "avoid_for": (
                "less suited to new builds; use gpt-oss-20b instead. Task "
                "fit: routing: best; short-chat: best; long-doc: ok; "
                "code-gen: ok; code-review: ok; planning: ok; "
                "math-reasoning: avoid; agent-loop: good; bulk-summary: best.",
                "https://console.groq.com/docs/models"),
            "best_for": (
                "suited to ultra-cheap routing, short-chat legacy. Task fit: "
                "routing: best; short-chat: best; long-doc: ok; code-gen: "
                "ok; code-review: ok; planning: ok; math-reasoning: avoid; "
                "agent-loop: good; bulk-summary: best.",
                "https://console.groq.com/docs/models"),
            "context_window": (
                131072,
                "https://console.groq.com/docs/model/llama-3.1-8b-instant"),
            "cost_tier": (
                "cheap-fast",
                "https://console.groq.com/docs/models"),
            "max_output": (
                131072,
                "https://console.groq.com/docs/model/llama-3.1-8b-instant"),
            "modalities": (
                [
                    "text",
                ],
                "https://console.groq.com/docs/model/llama-3.1-8b-instant"),
            "reasoning": (
                False,
                "https://console.groq.com/docs/model/llama-3.1-8b-instant"),
            "role_notes": (
                "director role: legacy triage only; manager role: "
                "high-fan-out dispatch; worker role: short drafts; auditor "
                "role: low trust, verify.",
                "https://console.groq.com/docs/models"),
            "source_links": (
                [
                    "https://console.groq.com/docs/deprecations",
                    "https://console.groq.com/docs/model/llama-3.1-8b-instant",
                    "https://console.groq.com/docs/model/llama-3.3-70b-versatile",
                    "https://console.groq.com/docs/model/openai/gpt-oss-120b",
                    "https://console.groq.com/docs/model/openai/gpt-oss-20b",
                    "https://console.groq.com/docs/model/openai/gpt-oss-safeguard"
                    "-20b",
                    "https://console.groq.com/docs/model/qwen/qwen3.8-27b",
                    "https://console.groq.com/docs/model/whisper-large-v3-turbo",
                    "https://console.groq.com/docs/models",
                ],
                "https://console.groq.com/docs/model/openai/gpt-oss-120b"),
            "strengths": (
                "reads as strong on 560 tps fastest general chat host, 131K "
                "context both directions, mature tool-use.",
                "https://console.groq.com/docs/models"),
            "tool_calling": (
                True,
                "https://console.groq.com/docs/model/llama-3.1-8b-instant"),
            "weaknesses": (
                "watch out for 8B quality ceiling, deprecated for "
                "free/developer tiers 2026-08-16.",
                "https://console.groq.com/docs/models"),
        }),
        ("qwen/qwen3.8-27b", {
            "avoid_for": (
                "less suited to production without fallback; long-doc "
                "generation. Task fit: routing: good; short-chat: best; "
                "long-doc: ok; code-gen: good; code-review: good; planning: "
                "good; math-reasoning: good; agent-loop: good; vision: best.",
                "https://console.groq.com/docs/models"),
            "best_for": (
                "suited to vision short-chat, tuned-reasoning tasks. Task "
                "fit: routing: good; short-chat: best; long-doc: ok; "
                "code-gen: good; code-review: good; planning: good; "
                "math-reasoning: good; agent-loop: good; vision: best.",
                "https://console.groq.com/docs/models"),
            "context_window": (
                131072,
                "https://console.groq.com/docs/model/qwen/qwen3.8-27b"),
            "cost_tier": (
                "balanced",
                "https://console.groq.com/docs/models"),
            "currency": (
                "USD",
                "https://console.groq.com/docs/model/qwen/qwen3.8-27b"),
            "input_token_price": (
                0.8,
                "https://console.groq.com/docs/model/qwen/qwen3.8-27b"),
            "max_output": (
                16384,
                "https://console.groq.com/docs/model/qwen/qwen3.8-27b"),
            "modalities": (
                [
                    "text",
                    "vision",
                ],
                "https://console.groq.com/docs/model/qwen/qwen3.8-27b"),
            "output_token_price": (
                4.0,
                "https://console.groq.com/docs/model/qwen/qwen3.8-27b"),
            "reasoning": (
                True,
                "https://console.groq.com/docs/model/qwen/qwen3.8-27b"),
            "role_notes": (
                "director role: eval-vision pick, keep fallback; manager "
                "role: vision routing, reasoning-effort tuning; worker role: "
                "image+text tasks, OCR assist; auditor role: verify vision "
                "grounding.",
                "https://console.groq.com/docs/models"),
            "source_links": (
                [
                    "https://console.groq.com/docs/deprecations",
                    "https://console.groq.com/docs/model/llama-3.1-8b-instant",
                    "https://console.groq.com/docs/model/llama-3.3-70b-versatile",
                    "https://console.groq.com/docs/model/openai/gpt-oss-120b",
                    "https://console.groq.com/docs/model/openai/gpt-oss-20b",
                    "https://console.groq.com/docs/model/openai/gpt-oss-safeguard"
                    "-20b",
                    "https://console.groq.com/docs/model/qwen/qwen3.8-27b",
                    "https://console.groq.com/docs/model/whisper-large-v3-turbo",
                    "https://console.groq.com/docs/models",
                ],
                "https://console.groq.com/docs/model/openai/gpt-oss-120b"),
            "strengths": (
                "reads as strong on multimodal 27B with thinking/instruct "
                "modes, tunable reasoning effort, JSON mode, 450 tps preview "
                "speed.",
                "https://console.groq.com/docs/models"),
            "tool_calling": (
                True,
                "https://console.groq.com/docs/model/qwen/qwen3.8-27b"),
            "weaknesses": (
                "watch out for preview, may be discontinued at short notice, "
                "16K max completion limits long outputs.",
                "https://console.groq.com/docs/models"),
        }),
        ("whisper-large-v3-turbo", {
            "avoid_for": (
                "less suited to all text-only routing tasks. Task fit: "
                "speech: best; short-chat: avoid; long-doc: avoid; code-gen: "
                "avoid.",
                "https://console.groq.com/docs/models"),
            "best_for": (
                "suited to speech transcription. Task fit: speech: best; "
                "short-chat: avoid; long-doc: avoid; code-gen: avoid.",
                "https://console.groq.com/docs/models"),
            "cost_tier": (
                "specialised",
                "https://console.groq.com/docs/models"),
            "modalities": (
                [
                    "audio",
                ],
                "https://console.groq.com/docs/model/whisper-large-v3-turbo"),
            "reasoning": (
                False,
                "https://console.groq.com/docs/model/whisper-large-v3-turbo"),
            "role_notes": (
                "director role: speech pipeline only; manager role: "
                "transcription fan-out; worker role: transcribe then hand "
                "off text; auditor role: check transcript segments.",
                "https://console.groq.com/docs/models"),
            "source_links": (
                [
                    "https://console.groq.com/docs/deprecations",
                    "https://console.groq.com/docs/model/llama-3.1-8b-instant",
                    "https://console.groq.com/docs/model/llama-3.3-70b-versatile",
                    "https://console.groq.com/docs/model/openai/gpt-oss-120b",
                    "https://console.groq.com/docs/model/openai/gpt-oss-20b",
                    "https://console.groq.com/docs/model/openai/gpt-oss-safeguard"
                    "-20b",
                    "https://console.groq.com/docs/model/qwen/qwen3.8-27b",
                    "https://console.groq.com/docs/model/whisper-large-v3-turbo",
                    "https://console.groq.com/docs/models",
                ],
                "https://console.groq.com/docs/model/openai/gpt-oss-120b"),
            "strengths": (
                "reads as strong on fast speech-to-text host, more languages "
                "than distil-whisper.",
                "https://console.groq.com/docs/models"),
            "tool_calling": (
                False,
                "https://console.groq.com/docs/model/whisper-large-v3-turbo"),
            "weaknesses": (
                "watch out for billed per hour ($0.04/hr), not per token, "
                "100MB file cap.",
                "https://console.groq.com/docs/models"),
        }),
        ("openai/gpt-oss-safeguard-20b", {
            "avoid_for": (
                "less suited to general code-gen or planning. Task fit: "
                "routing: ok; short-chat: ok.",
                "https://console.groq.com/docs/models"),
            "best_for": (
                "suited to content moderation guardrail. Task fit: routing: "
                "ok; short-chat: ok.",
                "https://console.groq.com/docs/models"),
            "context_window": (
                131072,
                "https://console.groq.com/docs/model/openai/gpt-oss-safeguard"
                "-20b"),
            "cost_tier": (
                "specialised",
                "https://console.groq.com/docs/models"),
            "currency": (
                "USD",
                "https://console.groq.com/docs/model/openai/gpt-oss-safeguard"
                "-20b"),
            "input_token_price": (
                0.075,
                "https://console.groq.com/docs/model/openai/gpt-oss-safeguard"
                "-20b"),
            "max_output": (
                65536,
                "https://console.groq.com/docs/model/openai/gpt-oss-safeguard"
                "-20b"),
            "modalities": (
                [
                    "text",
                ],
                "https://console.groq.com/docs/model/openai/gpt-oss-safeguard"
                "-20b"),
            "output_token_price": (
                0.3,
                "https://console.groq.com/docs/model/openai/gpt-oss-safeguard"
                "-20b"),
            "reasoning": (
                True,
                "https://console.groq.com/docs/model/openai/gpt-oss-safeguard"
                "-20b"),
            "role_notes": (
                "director role: moderation gate; manager role: pre/post "
                "generation filter; worker role: policy checks; auditor "
                "role: primary moderation tool.",
                "https://console.groq.com/docs/models"),
            "source_links": (
                [
                    "https://console.groq.com/docs/deprecations",
                    "https://console.groq.com/docs/model/llama-3.1-8b-instant",
                    "https://console.groq.com/docs/model/llama-3.3-70b-versatile",
                    "https://console.groq.com/docs/model/openai/gpt-oss-120b",
                    "https://console.groq.com/docs/model/openai/gpt-oss-20b",
                    "https://console.groq.com/docs/model/openai/gpt-oss-safeguard"
                    "-20b",
                    "https://console.groq.com/docs/model/qwen/qwen3.8-27b",
                    "https://console.groq.com/docs/model/whisper-large-v3-turbo",
                    "https://console.groq.com/docs/models",
                ],
                "https://console.groq.com/docs/model/openai/gpt-oss-120b"),
            "strengths": (
                "reads as strong on policy-following reasoning for trust and "
                "safety, bring-your-own-policy moderation, same price as "
                "gpt-oss-20b.",
                "https://console.groq.com/docs/models"),
            "tool_calling": (
                True,
                "https://console.groq.com/docs/model/openai/gpt-oss-safeguard"
                "-20b"),
            "weaknesses": (
                "watch out for preview, evaluation only, not a general chat "
                "replacement.",
                "https://console.groq.com/docs/models"),
        }),
    ],
    "local": [
        ("local-llama-3.1-8b", {
            "avoid_for": (
                "less suited to 70B-plus frontier reasoning on one GPU; "
                "vision tasks. Task fit: general: good.",
                "https://ollama.com/library/llama3.1"),
            "best_for": (
                "suited to Local chat, summarisation and coding assistants "
                "on one GPU. Task fit: general: good.",
                "https://ollama.com/library/llama3.1"),
            "context_window": (
                128000,
                "https://ollama.com/library/llama3.1"),
            "cost_tier": (
                "balanced",
                "https://ollama.com/library/llama3.1"),
            "modalities": (
                [
                    "text",
                ],
                "https://ollama.com/library/llama3.1"),
            "reasoning": (
                False,
                "https://ollama.com/library/llama3.1"),
            "role_notes": (
                "auditor role: Good local auditor for short transcripts.; "
                "director role: Avoid as director; small model.; manager "
                "role: OK local manager for small splits.; worker role: Best "
                "local worker for offline subtasks..",
                "https://ollama.com/library/llama3.1"),
            "source_links": (
                [
                    "https://ollama.com/library/deepseek-r1",
                    "https://ollama.com/library/gemma2",
                    "https://ollama.com/library/gemma3",
                    "https://ollama.com/library/llama3.1",
                    "https://ollama.com/library/mistral",
                    "https://ollama.com/library/mixtral",
                    "https://ollama.com/library/phi3",
                    "https://ollama.com/library/phi4",
                    "https://ollama.com/library/qwen2.5",
                    "https://ollama.com/library/qwen3",
                ],
                "https://ollama.com/library/llama3.1"),
            "strengths": (
                "reads as strong on 128K context in 8B class, Multilingual "
                "with tool use, Small 4.9GB download.",
                "https://ollama.com/library/llama3.1"),
            "tool_calling": (
                True,
                "https://ollama.com/library/llama3.1"),
            "weaknesses": (
                "watch out for Below frontier quality, Text-only in Ollama "
                "listing.",
                "https://ollama.com/library/llama3.1"),
        }),
        ("local-llama-3.1-70b", {
            "avoid_for": (
                "less suited to Single consumer GPU; laptop inference. Task "
                "fit: general: best.",
                "https://ollama.com/library/llama3.1"),
            "best_for": (
                "suited to High-quality local reasoning and long-form "
                "summarisation. Task fit: general: best.",
                "https://ollama.com/library/llama3.1"),
            "context_window": (
                128000,
                "https://ollama.com/library/llama3.1"),
            "cost_tier": (
                "strong-reasoning",
                "https://ollama.com/library/llama3.1"),
            "modalities": (
                [
                    "text",
                ],
                "https://ollama.com/library/llama3.1"),
            "reasoning": (
                False,
                "https://ollama.com/library/llama3.1"),
            "role_notes": (
                "auditor role: Best local auditor when VRAM allows.; "
                "director role: Usable local director on big rigs.; manager "
                "role: Good local manager.; worker role: Strong worker; "
                "needs 43GB+ class hardware..",
                "https://ollama.com/library/llama3.1"),
            "source_links": (
                [
                    "https://ollama.com/library/deepseek-r1",
                    "https://ollama.com/library/gemma2",
                    "https://ollama.com/library/gemma3",
                    "https://ollama.com/library/llama3.1",
                    "https://ollama.com/library/mistral",
                    "https://ollama.com/library/mixtral",
                    "https://ollama.com/library/phi3",
                    "https://ollama.com/library/phi4",
                    "https://ollama.com/library/qwen2.5",
                    "https://ollama.com/library/qwen3",
                ],
                "https://ollama.com/library/llama3.1"),
            "strengths": (
                "reads as strong on 70B quality with 128K context, Tool use "
                "and multilingual, Near-405B class per Meta evaluations "
                "cited on page.",
                "https://ollama.com/library/llama3.1"),
            "tool_calling": (
                True,
                "https://ollama.com/library/llama3.1"),
            "weaknesses": (
                "watch out for 43GB download; multi-GPU or big RAM needed, "
                "Slower than 8B on same hardware.",
                "https://ollama.com/library/llama3.1"),
        }),
        ("local-qwen-2.5-7b", {
            "avoid_for": (
                "less suited to Frontier math and reasoning; vision input. "
                "Task fit: general: good.",
                "https://ollama.com/library/qwen2.5"),
            "best_for": (
                "suited to Fast local instruct-following and structured JSON "
                "output. Task fit: general: good.",
                "https://ollama.com/library/qwen2.5"),
            "context_window": (
                32000,
                "https://ollama.com/library/qwen2.5"),
            "cost_tier": (
                "balanced",
                "https://ollama.com/library/qwen2.5"),
            "max_output": (
                8000,
                "https://ollama.com/library/qwen2.5"),
            "modalities": (
                [
                    "text",
                ],
                "https://ollama.com/library/qwen2.5"),
            "reasoning": (
                False,
                "https://ollama.com/library/qwen2.5"),
            "role_notes": (
                "auditor role: OK local auditor for short logs.; director "
                "role: Avoid as director.; manager role: OK local manager "
                "for small splits.; worker role: Best cheap local worker..",
                "https://ollama.com/library/qwen2.5"),
            "source_links": (
                [
                    "https://ollama.com/library/deepseek-r1",
                    "https://ollama.com/library/gemma2",
                    "https://ollama.com/library/gemma3",
                    "https://ollama.com/library/llama3.1",
                    "https://ollama.com/library/mistral",
                    "https://ollama.com/library/mixtral",
                    "https://ollama.com/library/phi3",
                    "https://ollama.com/library/phi4",
                    "https://ollama.com/library/qwen2.5",
                    "https://ollama.com/library/qwen3",
                ],
                "https://ollama.com/library/llama3.1"),
            "strengths": (
                "reads as strong on Strong instruction following in 7B "
                "class, Structured JSON output support, 29+ language support.",
                "https://ollama.com/library/qwen2.5"),
            "tool_calling": (
                True,
                "https://ollama.com/library/qwen2.5"),
            "weaknesses": (
                "watch out for 32K Ollama context vs 128K upstream, Below "
                "32B+ quality.",
                "https://ollama.com/library/qwen2.5"),
        }),
        ("local-qwen-2.5-32b", {
            "avoid_for": (
                "less suited to Single 8GB GPU without offload; "
                "latency-critical chat. Task fit: general: best.",
                "https://ollama.com/library/qwen2.5"),
            "best_for": (
                "suited to Local coding, math and structured generation. "
                "Task fit: general: best.",
                "https://ollama.com/library/qwen2.5"),
            "context_window": (
                32000,
                "https://ollama.com/library/qwen2.5"),
            "cost_tier": (
                "balanced",
                "https://ollama.com/library/qwen2.5"),
            "max_output": (
                8000,
                "https://ollama.com/library/qwen2.5"),
            "modalities": (
                [
                    "text",
                ],
                "https://ollama.com/library/qwen2.5"),
            "reasoning": (
                False,
                "https://ollama.com/library/qwen2.5"),
            "role_notes": (
                "auditor role: Good local auditor for code.; director role: "
                "Usable local director on 24GB+ GPUs.; manager role: Good "
                "local manager.; worker role: Strong worker; needs 20GB+ "
                "class hardware..",
                "https://ollama.com/library/qwen2.5"),
            "source_links": (
                [
                    "https://ollama.com/library/deepseek-r1",
                    "https://ollama.com/library/gemma2",
                    "https://ollama.com/library/gemma3",
                    "https://ollama.com/library/llama3.1",
                    "https://ollama.com/library/mistral",
                    "https://ollama.com/library/mixtral",
                    "https://ollama.com/library/phi3",
                    "https://ollama.com/library/phi4",
                    "https://ollama.com/library/qwen2.5",
                    "https://ollama.com/library/qwen3",
                ],
                "https://ollama.com/library/llama3.1"),
            "strengths": (
                "reads as strong on Specialised coding and math ability, "
                "Structured outputs and long-text generation, Multilingual.",
                "https://ollama.com/library/qwen2.5"),
            "tool_calling": (
                True,
                "https://ollama.com/library/qwen2.5"),
            "weaknesses": (
                "watch out for 20GB download size, 32K Ollama context.",
                "https://ollama.com/library/qwen2.5"),
        }),
        ("local-qwen-3-8b", {
            "avoid_for": (
                "less suited to Vision tasks; largest-model quality. Task "
                "fit: general: best.",
                "https://ollama.com/library/qwen3"),
            "best_for": (
                "suited to Local agents with tool use on one GPU. Task fit: "
                "general: best.",
                "https://ollama.com/library/qwen3"),
            "context_window": (
                40000,
                "https://ollama.com/library/qwen3"),
            "cost_tier": (
                "balanced",
                "https://ollama.com/library/qwen3"),
            "modalities": (
                [
                    "text",
                ],
                "https://ollama.com/library/qwen3"),
            "reasoning": (
                True,
                "https://ollama.com/library/qwen3"),
            "role_notes": (
                "auditor role: Good local auditor for agent traces.; "
                "director role: OK local director for small plans.; manager "
                "role: Good local manager.; worker role: Best balanced local "
                "worker..",
                "https://ollama.com/library/qwen3"),
            "source_links": (
                [
                    "https://ollama.com/library/deepseek-r1",
                    "https://ollama.com/library/gemma2",
                    "https://ollama.com/library/gemma3",
                    "https://ollama.com/library/llama3.1",
                    "https://ollama.com/library/mistral",
                    "https://ollama.com/library/mixtral",
                    "https://ollama.com/library/phi3",
                    "https://ollama.com/library/phi4",
                    "https://ollama.com/library/qwen2.5",
                    "https://ollama.com/library/qwen3",
                ],
                "https://ollama.com/library/llama3.1"),
            "strengths": (
                "reads as strong on Thinking and non-thinking modes, Agent "
                "tool integration, 100+ languages and dialects.",
                "https://ollama.com/library/qwen3"),
            "tool_calling": (
                True,
                "https://ollama.com/library/qwen3"),
            "weaknesses": (
                "watch out for 40K Ollama context on 8B tag, Below 30B+ "
                "reasoning quality.",
                "https://ollama.com/library/qwen3"),
        }),
        ("local-qwen-3-30b", {
            "avoid_for": (
                "less suited to Single consumer GPU; quick chat. Task fit: "
                "general: best.",
                "https://ollama.com/library/qwen3"),
            "best_for": (
                "suited to Strong local reasoning and coding on big VRAM. "
                "Task fit: general: best.",
                "https://ollama.com/library/qwen3"),
            "context_window": (
                256000,
                "https://ollama.com/library/qwen3"),
            "cost_tier": (
                "strong-reasoning",
                "https://ollama.com/library/qwen3"),
            "modalities": (
                [
                    "text",
                ],
                "https://ollama.com/library/qwen3"),
            "reasoning": (
                True,
                "https://ollama.com/library/qwen3"),
            "role_notes": (
                "auditor role: Best local reasoning auditor on capable "
                "hardware.; director role: Best local director option.; "
                "manager role: Good local manager.; worker role: Strong "
                "worker; needs 19GB+ class hardware..",
                "https://ollama.com/library/qwen3"),
            "source_links": (
                [
                    "https://ollama.com/library/deepseek-r1",
                    "https://ollama.com/library/gemma2",
                    "https://ollama.com/library/gemma3",
                    "https://ollama.com/library/llama3.1",
                    "https://ollama.com/library/mistral",
                    "https://ollama.com/library/mixtral",
                    "https://ollama.com/library/phi3",
                    "https://ollama.com/library/phi4",
                    "https://ollama.com/library/qwen2.5",
                    "https://ollama.com/library/qwen3",
                ],
                "https://ollama.com/library/llama3.1"),
            "strengths": (
                "reads as strong on Small MoE outcompeting larger dense "
                "cited on page, 256K context on 30B tag, Thinking mode "
                "reasoning.",
                "https://ollama.com/library/qwen3"),
            "tool_calling": (
                True,
                "https://ollama.com/library/qwen3"),
            "weaknesses": (
                "watch out for 19GB download; heavy for laptops, MoE setup "
                "complexity.",
                "https://ollama.com/library/qwen3"),
        }),
        ("local-gemma-2-9b", {
            "avoid_for": (
                "less suited to Long-context RAG over 8K; tool-heavy agents. "
                "Task fit: general: good.",
                "https://ollama.com/library/gemma2"),
            "best_for": (
                "suited to Cheap local summarisation and chat. Task fit: "
                "general: good.",
                "https://ollama.com/library/gemma2"),
            "context_window": (
                8000,
                "https://ollama.com/library/gemma2"),
            "cost_tier": (
                "balanced",
                "https://ollama.com/library/gemma2"),
            "modalities": (
                [
                    "text",
                ],
                "https://ollama.com/library/gemma2"),
            "reasoning": (
                False,
                "https://ollama.com/library/gemma2"),
            "role_notes": (
                "auditor role: OK local auditor for short text.; director "
                "role: Avoid as director.; manager role: OK local manager "
                "for tiny splits.; worker role: Good cheap worker..",
                "https://ollama.com/library/gemma2"),
            "source_links": (
                [
                    "https://ollama.com/library/deepseek-r1",
                    "https://ollama.com/library/gemma2",
                    "https://ollama.com/library/gemma3",
                    "https://ollama.com/library/llama3.1",
                    "https://ollama.com/library/mistral",
                    "https://ollama.com/library/mixtral",
                    "https://ollama.com/library/phi3",
                    "https://ollama.com/library/phi4",
                    "https://ollama.com/library/qwen2.5",
                    "https://ollama.com/library/qwen3",
                ],
                "https://ollama.com/library/llama3.1"),
            "strengths": (
                "reads as strong on Efficient 9B with strong benchmarks "
                "cited, Small 5.4GB download, Good for content and chat.",
                "https://ollama.com/library/gemma2"),
            "tool_calling": (
                False,
                "https://ollama.com/library/gemma2"),
            "weaknesses": (
                "watch out for 8K Ollama context only, No tool tag in Ollama "
                "listing.",
                "https://ollama.com/library/gemma2"),
        }),
        ("local-gemma-3-12b", {
            "avoid_for": (
                "less suited to Pure-text cheapest inference; 8K-only "
                "pipelines. Task fit: general: best.",
                "https://ollama.com/library/gemma3"),
            "best_for": (
                "suited to Local multimodal chat with images on one GPU. "
                "Task fit: general: best.",
                "https://ollama.com/library/gemma3"),
            "context_window": (
                128000,
                "https://ollama.com/library/gemma3"),
            "cost_tier": (
                "balanced",
                "https://ollama.com/library/gemma3"),
            "modalities": (
                [
                    "text",
                    "image",
                ],
                "https://ollama.com/library/gemma3"),
            "reasoning": (
                False,
                "https://ollama.com/library/gemma3"),
            "role_notes": (
                "auditor role: Good auditor for multimodal transcripts.; "
                "director role: OK local director for small multimodal "
                "plans.; manager role: Good local manager.; worker role: "
                "Best local multimodal worker on 12GB+ GPUs..",
                "https://ollama.com/library/gemma3"),
            "source_links": (
                [
                    "https://ollama.com/library/deepseek-r1",
                    "https://ollama.com/library/gemma2",
                    "https://ollama.com/library/gemma3",
                    "https://ollama.com/library/llama3.1",
                    "https://ollama.com/library/mistral",
                    "https://ollama.com/library/mixtral",
                    "https://ollama.com/library/phi3",
                    "https://ollama.com/library/phi4",
                    "https://ollama.com/library/qwen2.5",
                    "https://ollama.com/library/qwen3",
                ],
                "https://ollama.com/library/llama3.1"),
            "strengths": (
                "reads as strong on Vision + text with 128K context, 140+ "
                "language support, QAT variants for lower memory.",
                "https://ollama.com/library/gemma3"),
            "tool_calling": (
                False,
                "https://ollama.com/library/gemma3"),
            "weaknesses": (
                "watch out for 8.2GB download; needs 12GB+ GPU comfort, "
                "Below 27B reasoning quality.",
                "https://ollama.com/library/gemma3"),
        }),
        ("local-mistral-7b", {
            "avoid_for": (
                "less suited to Long-context RAG; vision tasks. Task fit: "
                "general: good.",
                "https://ollama.com/library/mistral"),
            "best_for": (
                "suited to Fast local general chat and function calling. "
                "Task fit: general: good.",
                "https://ollama.com/library/mistral"),
            "context_window": (
                32000,
                "https://ollama.com/library/mistral"),
            "cost_tier": (
                "balanced",
                "https://ollama.com/library/mistral"),
            "modalities": (
                [
                    "text",
                ],
                "https://ollama.com/library/mistral"),
            "reasoning": (
                False,
                "https://ollama.com/library/mistral"),
            "role_notes": (
                "auditor role: OK local auditor for chat logs.; director "
                "role: Avoid as director.; manager role: OK local manager "
                "for tiny splits.; worker role: Best fast local worker..",
                "https://ollama.com/library/mistral"),
            "source_links": (
                [
                    "https://ollama.com/library/deepseek-r1",
                    "https://ollama.com/library/gemma2",
                    "https://ollama.com/library/gemma3",
                    "https://ollama.com/library/llama3.1",
                    "https://ollama.com/library/mistral",
                    "https://ollama.com/library/mixtral",
                    "https://ollama.com/library/phi3",
                    "https://ollama.com/library/phi4",
                    "https://ollama.com/library/qwen2.5",
                    "https://ollama.com/library/qwen3",
                ],
                "https://ollama.com/library/llama3.1"),
            "strengths": (
                "reads as strong on Apache licensed 7B, v0.3 function "
                "calling support, Small 4.4GB download.",
                "https://ollama.com/library/mistral"),
            "tool_calling": (
                True,
                "https://ollama.com/library/mistral"),
            "weaknesses": (
                "watch out for 32K context only, Below larger-model code "
                "quality.",
                "https://ollama.com/library/mistral"),
        }),
        ("local-mixtral-8x7b", {
            "avoid_for": (
                "less suited to Single 8GB GPU; simple fast chat. Task fit: "
                "general: good.",
                "https://ollama.com/library/mixtral"),
            "best_for": (
                "suited to Multilingual local work with MoE quality. Task "
                "fit: general: good.",
                "https://ollama.com/library/mixtral"),
            "context_window": (
                32000,
                "https://ollama.com/library/mixtral"),
            "cost_tier": (
                "strong-reasoning",
                "https://ollama.com/library/mixtral"),
            "modalities": (
                [
                    "text",
                ],
                "https://ollama.com/library/mixtral"),
            "reasoning": (
                False,
                "https://ollama.com/library/mixtral"),
            "role_notes": (
                "auditor role: Good local auditor for multilingual text.; "
                "director role: Usable local director on big hardware.; "
                "manager role: Good local manager.; worker role: Strong "
                "worker; needs 26GB+ class hardware..",
                "https://ollama.com/library/mixtral"),
            "source_links": (
                [
                    "https://ollama.com/library/deepseek-r1",
                    "https://ollama.com/library/gemma2",
                    "https://ollama.com/library/gemma3",
                    "https://ollama.com/library/llama3.1",
                    "https://ollama.com/library/mistral",
                    "https://ollama.com/library/mixtral",
                    "https://ollama.com/library/phi3",
                    "https://ollama.com/library/phi4",
                    "https://ollama.com/library/qwen2.5",
                    "https://ollama.com/library/qwen3",
                ],
                "https://ollama.com/library/llama3.1"),
            "strengths": (
                "reads as strong on Sparse MoE efficiency, Fluent in "
                "EN/FR/IT/DE/ES, Native function calling cited.",
                "https://ollama.com/library/mixtral"),
            "tool_calling": (
                True,
                "https://ollama.com/library/mixtral"),
            "weaknesses": (
                "watch out for 26GB download; heavy hardware, 32K context on "
                "8x7b tag.",
                "https://ollama.com/library/mixtral"),
        }),
        ("local-phi-3-mini-3.8b", {
            "avoid_for": (
                "less suited to Multilingual non-English work; vision tasks. "
                "Task fit: general: good.",
                "https://ollama.com/library/phi3"),
            "best_for": (
                "suited to Local reasoning on memory-constrained machines. "
                "Task fit: general: good.",
                "https://ollama.com/library/phi3"),
            "context_window": (
                128000,
                "https://ollama.com/library/phi3"),
            "cost_tier": (
                "cheap-fast",
                "https://ollama.com/library/phi3"),
            "knowledge_cutoff": (
                "2023-10",
                "https://ollama.com/library/phi3"),
            "modalities": (
                [
                    "text",
                ],
                "https://ollama.com/library/phi3"),
            "reasoning": (
                False,
                "https://ollama.com/library/phi3"),
            "role_notes": (
                "auditor role: OK local auditor for English logs.; director "
                "role: Avoid as director.; manager role: OK local manager "
                "for tiny splits.; worker role: Best tiny local worker..",
                "https://ollama.com/library/phi3"),
            "source_links": (
                [
                    "https://ollama.com/library/deepseek-r1",
                    "https://ollama.com/library/gemma2",
                    "https://ollama.com/library/gemma3",
                    "https://ollama.com/library/llama3.1",
                    "https://ollama.com/library/mistral",
                    "https://ollama.com/library/mixtral",
                    "https://ollama.com/library/phi3",
                    "https://ollama.com/library/phi4",
                    "https://ollama.com/library/qwen2.5",
                    "https://ollama.com/library/qwen3",
                ],
                "https://ollama.com/library/llama3.1"),
            "strengths": (
                "reads as strong on Tiny 2.2GB download, 128K context "
                "variant noted, Strong math/logic for size.",
                "https://ollama.com/library/phi3"),
            "tool_calling": (
                False,
                "https://ollama.com/library/phi3"),
            "weaknesses": (
                "watch out for English-focused; weaker other languages, "
                "Limited code scope beyond Python cited.",
                "https://ollama.com/library/phi3"),
        }),
        ("local-phi-4-14b", {
            "avoid_for": (
                "less suited to Long-context RAG over 16K; vision tasks. "
                "Task fit: general: good.",
                "https://ollama.com/library/phi4"),
            "best_for": (
                "suited to Local reasoning and logic on a single GPU. Task "
                "fit: general: good.",
                "https://ollama.com/library/phi4"),
            "context_window": (
                16000,
                "https://ollama.com/library/phi4"),
            "cost_tier": (
                "balanced",
                "https://ollama.com/library/phi4"),
            "modalities": (
                [
                    "text",
                ],
                "https://ollama.com/library/phi4"),
            "reasoning": (
                False,
                "https://ollama.com/library/phi4"),
            "role_notes": (
                "auditor role: Good local auditor for reasoning logs.; "
                "director role: OK local director for small technical "
                "plans.; manager role: Good local manager.; worker role: "
                "Strong worker on 12GB+ GPUs..",
                "https://ollama.com/library/phi4"),
            "source_links": (
                [
                    "https://ollama.com/library/deepseek-r1",
                    "https://ollama.com/library/gemma2",
                    "https://ollama.com/library/gemma3",
                    "https://ollama.com/library/llama3.1",
                    "https://ollama.com/library/mistral",
                    "https://ollama.com/library/mixtral",
                    "https://ollama.com/library/phi3",
                    "https://ollama.com/library/phi4",
                    "https://ollama.com/library/qwen2.5",
                    "https://ollama.com/library/qwen3",
                ],
                "https://ollama.com/library/llama3.1"),
            "strengths": (
                "reads as strong on Synthetic-data reasoning focus, SFT plus "
                "direct preference optimisation cited, MIT-licensed family "
                "cited on phi3 page.",
                "https://ollama.com/library/phi4"),
            "tool_calling": (
                False,
                "https://ollama.com/library/phi4"),
            "weaknesses": (
                "watch out for 16K context only, English-primary cited.",
                "https://ollama.com/library/phi4"),
        }),
        ("local-deepseek-r1-8b", {
            "avoid_for": (
                "less suited to Vision tasks; latency-critical chat; "
                "tool-heavy agents. Task fit: general: best.",
                "https://ollama.com/library/deepseek-r1"),
            "best_for": (
                "suited to Local chain-of-thought math, code and logic. Task "
                "fit: general: best.",
                "https://ollama.com/library/deepseek-r1"),
            "context_window": (
                128000,
                "https://ollama.com/library/deepseek-r1"),
            "cost_tier": (
                "balanced",
                "https://ollama.com/library/deepseek-r1"),
            "modalities": (
                [
                    "text",
                ],
                "https://ollama.com/library/deepseek-r1"),
            "reasoning": (
                True,
                "https://ollama.com/library/deepseek-r1"),
            "role_notes": (
                "auditor role: Good local auditor for reasoning traces.; "
                "director role: OK local director for technical plans.; "
                "manager role: Good local manager.; worker role: Best local "
                "reasoning worker on one GPU..",
                "https://ollama.com/library/deepseek-r1"),
            "source_links": (
                [
                    "https://ollama.com/library/deepseek-r1",
                    "https://ollama.com/library/gemma2",
                    "https://ollama.com/library/gemma3",
                    "https://ollama.com/library/llama3.1",
                    "https://ollama.com/library/mistral",
                    "https://ollama.com/library/mixtral",
                    "https://ollama.com/library/phi3",
                    "https://ollama.com/library/phi4",
                    "https://ollama.com/library/qwen2.5",
                    "https://ollama.com/library/qwen3",
                ],
                "https://ollama.com/library/llama3.1"),
            "strengths": (
                "reads as strong on Distilled R1 reasoning patterns, "
                "MIT-licensed weights cited, Small 5.2GB download.",
                "https://ollama.com/library/deepseek-r1"),
            "tool_calling": (
                True,
                "https://ollama.com/library/deepseek-r1"),
            "weaknesses": (
                "watch out for Distill weaker than full 671B, Verbose "
                "thinking traces cost tokens.",
                "https://ollama.com/library/deepseek-r1"),
        }),
        ("local-deepseek-r1-32b", {
            "avoid_for": (
                "less suited to Single consumer GPU; fast chat. Task fit: "
                "general: best.",
                "https://ollama.com/library/deepseek-r1"),
            "best_for": (
                "suited to Serious local reasoning on 24GB+ GPUs. Task fit: "
                "general: best.",
                "https://ollama.com/library/deepseek-r1"),
            "context_window": (
                128000,
                "https://ollama.com/library/deepseek-r1"),
            "cost_tier": (
                "strong-reasoning",
                "https://ollama.com/library/deepseek-r1"),
            "modalities": (
                [
                    "text",
                ],
                "https://ollama.com/library/deepseek-r1"),
            "reasoning": (
                True,
                "https://ollama.com/library/deepseek-r1"),
            "role_notes": (
                "auditor role: Best local distill auditor on big VRAM.; "
                "director role: Usable local director on 24GB+ GPUs.; "
                "manager role: Good local manager.; worker role: Strong "
                "worker; needs 20GB+ class hardware..",
                "https://ollama.com/library/deepseek-r1"),
            "source_links": (
                [
                    "https://ollama.com/library/deepseek-r1",
                    "https://ollama.com/library/gemma2",
                    "https://ollama.com/library/gemma3",
                    "https://ollama.com/library/llama3.1",
                    "https://ollama.com/library/mistral",
                    "https://ollama.com/library/mixtral",
                    "https://ollama.com/library/phi3",
                    "https://ollama.com/library/phi4",
                    "https://ollama.com/library/qwen2.5",
                    "https://ollama.com/library/qwen3",
                ],
                "https://ollama.com/library/llama3.1"),
            "strengths": (
                "reads as strong on Larger distill with stronger reasoning, "
                "128K context, Tools plus thinking tags.",
                "https://ollama.com/library/deepseek-r1"),
            "tool_calling": (
                True,
                "https://ollama.com/library/deepseek-r1"),
            "weaknesses": (
                "watch out for 20GB download size, Slower than 8B distill.",
                "https://ollama.com/library/deepseek-r1"),
        }),
    ],
    "meta": [
        ("muse-spark-1.3", {
            "avoid_for": (
                "less suited to Single-shot cheap bulk classification where "
                "contributor-tier price matters; audio-only transcription "
                "(use Voice Transcribe); image output (use Muse Image). Task "
                "fit: agent-loop: best; bulk-summary: good; code-gen: best; "
                "code-review: best; long-doc: best; math-reasoning: good; "
                "planning: best; routing: good; short-chat: good; vision: "
                "good.",
                "https://dev.meta.ai/docs/models"),
            "best_for": (
                "suited to Agentic coding loops, multi-step tool use, "
                "long-horizon planning, repo-scale code-gen and code-review. "
                "Task fit: agent-loop: best; bulk-summary: good; code-gen: "
                "best; code-review: best; long-doc: best; math-reasoning: "
                "good; planning: best; routing: good; short-chat: good; "
                "vision: good.",
                "https://dev.meta.ai/docs/models"),
            "context_window": (
                1048576,
                "https://dev.meta.ai/docs/models"),
            "cost_tier": (
                "strong-reasoning",
                "https://dev.meta.ai/docs/models"),
            "currency": (
                "USD",
                "https://dev.meta.ai/docs/pricing-rate-limits"),
            "input_token_price": (
                1.25,
                "https://dev.meta.ai/docs/pricing-rate-limits"),
            "modalities": (
                [
                    "text",
                    "image",
                    "video",
                    "pdf",
                    "audio-limited",
                ],
                "https://dev.meta.ai/docs/models"),
            "output_token_price": (
                4.25,
                "https://dev.meta.ai/docs/pricing-rate-limits"),
            "reasoning": (
                True,
                "https://dev.meta.ai/docs/models"),
            "role_notes": (
                "auditor role: Use for audit of code and agent traces; 1M "
                "context holds whole change sets.; director role: Default "
                "choice for planning and decomposition; strongest Muse Spark "
                "reasoning incl. max effort level.; manager role: Good for "
                "fan-out task packaging and merging subagent outputs.; "
                "worker role: Best worker for code-gen, tool loops, file "
                "edits in OpenCode/Muse Code harnesses..",
                "https://dev.meta.ai/docs/models"),
            "source_links": (
                [
                    "https://ai.meta.com/blog/llama-4-multimodal-intelligence",
                    "https://dev.meta.ai/docs/models",
                    "https://dev.meta.ai/docs/muse-glimmer",
                    "https://dev.meta.ai/docs/pricing-rate-limits",
                ],
                "https://dev.meta.ai/docs/models"),
            "strengths": (
                "reads as strong on Latest Muse Spark; improved agentic and "
                "coding performance over 1.2, 1M-token context with no "
                "long-context premium, Parallel tool calls, streamed "
                "tool-call args, reasoning across turns, structured output, "
                "search grounding.",
                "https://dev.meta.ai/docs/models"),
            "tool_calling": (
                True,
                "https://dev.meta.ai/docs/models"),
            "weaknesses": (
                "watch out for Audio understanding degraded in 1.3 (docs "
                "advise 1.2 or Voice Transcribe for audio), Higher price "
                "than contributor tier and many Llama self-hosted options.",
                "https://dev.meta.ai/docs/models"),
        }),
        ("muse-spark-1.2", {
            "avoid_for": (
                "less suited to Audio transcription at scale (use Voice "
                "Transcribe); image synthesis. Task fit: agent-loop: best; "
                "bulk-summary: good; code-gen: best; code-review: best; "
                "long-doc: best; math-reasoning: good; planning: good; "
                "routing: good; short-chat: good; vision: good.",
                "https://dev.meta.ai/docs/models"),
            "best_for": (
                "suited to Coding agents and tool loops where 1.3 is "
                "unavailable or audio input is required. Task fit: "
                "agent-loop: best; bulk-summary: good; code-gen: best; "
                "code-review: best; long-doc: best; math-reasoning: good; "
                "planning: good; routing: good; short-chat: good; vision: "
                "good.",
                "https://dev.meta.ai/docs/models"),
            "context_window": (
                1048576,
                "https://dev.meta.ai/docs/models"),
            "cost_tier": (
                "balanced",
                "https://dev.meta.ai/docs/models"),
            "currency": (
                "USD",
                "https://dev.meta.ai/docs/pricing-rate-limits"),
            "input_token_price": (
                1.25,
                "https://dev.meta.ai/docs/pricing-rate-limits"),
            "modalities": (
                [
                    "text",
                    "image",
                    "video",
                    "audio",
                    "pdf",
                ],
                "https://dev.meta.ai/docs/models"),
            "output_token_price": (
                4.25,
                "https://dev.meta.ai/docs/pricing-rate-limits"),
            "role_notes": (
                "auditor role: Solid auditor fallback; full audio support "
                "helps review meeting-derived specs.; director role: Capable "
                "planner; prefer 1.3 for newest work.; manager role: Good "
                "manager for dispatch and merge.; worker role: Strong "
                "worker, esp. tasks with audio attachments..",
                "https://dev.meta.ai/docs/models"),
            "source_links": (
                [
                    "https://ai.meta.com/blog/llama-4-multimodal-intelligence",
                    "https://dev.meta.ai/docs/models",
                    "https://dev.meta.ai/docs/muse-glimmer",
                    "https://dev.meta.ai/docs/pricing-rate-limits",
                ],
                "https://dev.meta.ai/docs/models"),
            "strengths": (
                "reads as strong on Full audio understanding (unlike "
                "degraded 1.3 audio), Same 1M context and agent primitives "
                "as 1.3, Contributor variant available for cheap prototyping.",
                "https://dev.meta.ai/docs/models"),
            "tool_calling": (
                True,
                "https://dev.meta.ai/docs/models"),
            "weaknesses": (
                "watch out for Previous version; coding quality below 1.3 "
                "per official docs, Same standard price as 1.3 so no cost "
                "reason to prefer it except audio.",
                "https://dev.meta.ai/docs/models"),
        }),
        ("muse-spark-1.1", {
            "avoid_for": (
                "less suited to New projects (prefer 1.3); heavy "
                "audio-transcription loads. Task fit: agent-loop: good; "
                "bulk-summary: good; code-gen: good; code-review: good; "
                "long-doc: good; math-reasoning: ok; planning: good; "
                "routing: good; short-chat: good; vision: good.",
                "https://dev.meta.ai/docs/models"),
            "best_for": (
                "suited to Legacy continuity for teams already pinned to "
                "1.1; general chat and tool calling. Task fit: agent-loop: "
                "good; bulk-summary: good; code-gen: good; code-review: "
                "good; long-doc: good; math-reasoning: ok; planning: good; "
                "routing: good; short-chat: good; vision: good.",
                "https://dev.meta.ai/docs/models"),
            "context_window": (
                1048576,
                "https://dev.meta.ai/docs/models"),
            "cost_tier": (
                "balanced",
                "https://dev.meta.ai/docs/models"),
            "currency": (
                "USD",
                "https://dev.meta.ai/docs/pricing-rate-limits"),
            "input_token_price": (
                1.25,
                "https://dev.meta.ai/docs/pricing-rate-limits"),
            "modalities": (
                [
                    "text",
                    "image",
                    "video",
                    "audio",
                    "pdf",
                ],
                "https://dev.meta.ai/docs/models"),
            "output_token_price": (
                4.25,
                "https://dev.meta.ai/docs/pricing-rate-limits"),
            "role_notes": (
                "auditor role: Acceptable auditor when pinned; otherwise "
                "migrate.; director role: Usable planner but superseded.; "
                "manager role: Usable manager.; worker role: Usable worker "
                "for short-chat and simple code tasks..",
                "https://dev.meta.ai/docs/models"),
            "source_links": (
                [
                    "https://ai.meta.com/blog/llama-4-multimodal-intelligence",
                    "https://dev.meta.ai/docs/models",
                    "https://dev.meta.ai/docs/muse-glimmer",
                    "https://dev.meta.ai/docs/pricing-rate-limits",
                ],
                "https://dev.meta.ai/docs/models"),
            "strengths": (
                "reads as strong on Original agentic Muse Spark with "
                "computer use and multimodal perception, Same 1M context and "
                "standard-tier data privacy (no training on data).",
                "https://dev.meta.ai/docs/models"),
            "tool_calling": (
                True,
                "https://dev.meta.ai/docs/models"),
            "weaknesses": (
                "watch out for Oldest version; superseded on coding by 1.2 "
                "and 1.3, No contributor-tier discount variant.",
                "https://dev.meta.ai/docs/models"),
        }),
        ("muse-spark-1.3-contributor", {
            "avoid_for": (
                "less suited to Production with sensitive prompts "
                "(training-eligible tier); audio transcription; image "
                "output. Task fit: agent-loop: good; bulk-summary: best; "
                "code-gen: good; code-review: good; long-doc: good; "
                "math-reasoning: ok; planning: ok; routing: best; "
                "short-chat: best; vision: good.",
                "https://dev.meta.ai/docs/models"),
            "best_for": (
                "suited to Cheap-fast prototyping, bulk-summary, short-chat, "
                "high-volume experiments where data may train future models. "
                "Task fit: agent-loop: good; bulk-summary: best; code-gen: "
                "good; code-review: good; long-doc: good; math-reasoning: "
                "ok; planning: ok; routing: best; short-chat: best; vision: "
                "good.",
                "https://dev.meta.ai/docs/models"),
            "context_window": (
                1048576,
                "https://dev.meta.ai/docs/models"),
            "cost_tier": (
                "cheap-fast",
                "https://dev.meta.ai/docs/models"),
            "currency": (
                "USD",
                "https://dev.meta.ai/docs/pricing-rate-limits"),
            "input_token_price": (
                0.1,
                "https://dev.meta.ai/docs/pricing-rate-limits"),
            "modalities": (
                [
                    "text",
                    "image",
                    "video",
                    "audio-limited",
                    "pdf",
                ],
                "https://dev.meta.ai/docs/models"),
            "output_token_price": (
                0.2,
                "https://dev.meta.ai/docs/pricing-rate-limits"),
            "role_notes": (
                "auditor role: Avoid for sensitive audits (data reused for "
                "training).; director role: Avoid for confidential "
                "planning.; manager role: Good for cheap fan-out trials.; "
                "worker role: Best cheap worker for bulk-summary and "
                "short-chat experiments..",
                "https://dev.meta.ai/docs/models"),
            "source_links": (
                [
                    "https://ai.meta.com/blog/llama-4-multimodal-intelligence",
                    "https://dev.meta.ai/docs/models",
                    "https://dev.meta.ai/docs/muse-glimmer",
                    "https://dev.meta.ai/docs/pricing-rate-limits",
                ],
                "https://dev.meta.ai/docs/models"),
            "strengths": (
                "reads as strong on Heavily discounted: $0.10/$0.20 per 1M "
                "vs $1.25/$4.25 standard, Same 1M context and Muse Spark 1.3 "
                "capabilities, Lowers barrier for scaling experiments.",
                "https://dev.meta.ai/docs/models"),
            "tool_calling": (
                True,
                "https://dev.meta.ai/docs/models"),
            "weaknesses": (
                "watch out for Prompts/completions may train future Meta "
                "models (privacy trade), Lower rate limits (100 RPM vs 3000 "
                "standard), Max reasoning level unavailable on contributor "
                "tier.",
                "https://dev.meta.ai/docs/models"),
        }),
        ("muse-glimmer-30b", {
            "avoid_for": (
                "less suited to 1M-context repo-scale tasks; hosted-API-only "
                "deployments; speech synthesis. Task fit: agent-loop: good; "
                "bulk-summary: good; code-gen: good; code-review: ok; "
                "long-doc: ok; math-reasoning: ok; planning: ok; routing: "
                "best; short-chat: best; vision: good.",
                "https://dev.meta.ai/docs/models"),
            "best_for": (
                "suited to Local always-on agents, on-device chat, "
                "privacy-sensitive routing and short-chat, fine-tuning base. "
                "Task fit: agent-loop: good; bulk-summary: good; code-gen: "
                "good; code-review: ok; long-doc: ok; math-reasoning: ok; "
                "planning: ok; routing: best; short-chat: best; vision: good.",
                "https://dev.meta.ai/docs/models"),
            "context_window": (
                131072,
                "https://dev.meta.ai/docs/muse-glimmer"),
            "cost_tier": (
                "cheap-fast",
                "https://dev.meta.ai/docs/models"),
            "modalities": (
                [
                    "text",
                    "image",
                ],
                "https://dev.meta.ai/docs/muse-glimmer"),
            "reasoning": (
                True,
                "https://dev.meta.ai/docs/muse-glimmer"),
            "role_notes": (
                "auditor role: Local audit without data leaving host; good "
                "for offline checks.; director role: Avoid as director "
                "(smaller than Spark).; manager role: Cheap local "
                "router/dispatcher.; worker role: Good offline worker for "
                "short-chat and simple code tasks..",
                "https://dev.meta.ai/docs/models"),
            "source_links": (
                [
                    "https://ai.meta.com/blog/llama-4-multimodal-intelligence",
                    "https://dev.meta.ai/docs/models",
                    "https://dev.meta.ai/docs/muse-glimmer",
                    "https://dev.meta.ai/docs/pricing-rate-limits",
                ],
                "https://dev.meta.ai/docs/models"),
            "strengths": (
                "reads as strong on Open-weight Apache 2.0; self-hosted via "
                "vLLM/SGLang/llama.cpp/ExecuTorch, Distilled from Muse "
                "Spark; step-by-step reasoning; 100+ languages, No per-token "
                "API cost; data stays on own hardware.",
                "https://dev.meta.ai/docs/models"),
            "weaknesses": (
                "watch out for 30B dense class below frontier Muse Spark "
                "quality, Default 128K context far below 1M Spark window.",
                "https://dev.meta.ai/docs/models"),
        }),
        ("llama-4-maverick", {
            "avoid_for": (
                "less suited to Single-H100 self-hosting (too large); "
                "cheapest bulk jobs. Task fit: agent-loop: good; "
                "bulk-summary: good; code-gen: best; code-review: best; "
                "long-doc: ok; math-reasoning: good; planning: good; "
                "routing: ok; short-chat: good; vision: best.",
                "https://dev.meta.ai/docs/models"),
            "best_for": (
                "suited to High-quality open-weight chat, coding, "
                "multilingual, image understanding where self-hosting on a "
                "single H100 host is acceptable. Task fit: agent-loop: good; "
                "bulk-summary: good; code-gen: best; code-review: best; "
                "long-doc: ok; math-reasoning: good; planning: good; "
                "routing: ok; short-chat: good; vision: best.",
                "https://dev.meta.ai/docs/models"),
            "cost_tier": (
                "balanced",
                "https://dev.meta.ai/docs/models"),
            "modalities": (
                [
                    "text",
                    "image",
                ],
                "https://ai.meta.com/blog/llama-4-multimodal-intelligence"),
            "role_notes": (
                "auditor role: Strong open auditor for code and multilingual "
                "review.; director role: Good open planner; needs hosting "
                "ops.; manager role: Good manager for merge/summarise.; "
                "worker role: Best open worker for code-gen and vision "
                "tasks..",
                "https://dev.meta.ai/docs/models"),
            "source_links": (
                [
                    "https://ai.meta.com/blog/llama-4-multimodal-intelligence",
                    "https://dev.meta.ai/docs/models",
                    "https://dev.meta.ai/docs/muse-glimmer",
                    "https://dev.meta.ai/docs/pricing-rate-limits",
                ],
                "https://dev.meta.ai/docs/models"),
            "strengths": (
                "reads as strong on 17B active / 400B total MoE; beats "
                "GPT-4o-class on multimodal per Meta, Open weights via "
                "llama.com and Hugging Face, Natively multimodal with early "
                "fusion (context window UNKNOWN per R1 spot-check "
                "2026-10-11).",
                "https://dev.meta.ai/docs/models"),
            "weaknesses": (
                "watch out for Requires single H100 host or distributed "
                "inference, Behemoth teacher (288B active) never released; "
                "frontier path moved to closed Muse Spark.",
                "https://dev.meta.ai/docs/models"),
        }),
        ("llama-4-scout", {
            "avoid_for": (
                "less suited to Absolute frontier quality (use Maverick or "
                "Muse Spark); tiny-edge deployment. Task fit: agent-loop: "
                "good; bulk-summary: best; code-gen: good; code-review: "
                "good; long-doc: best; math-reasoning: ok; planning: good; "
                "routing: ok; short-chat: good; vision: best.",
                "https://dev.meta.ai/docs/models"),
            "best_for": (
                "suited to Long-doc retrieval, multi-document summary, "
                "vast-codebase reasoning with industry-leading 10M context; "
                "single-H100 self-hosting. Task fit: agent-loop: good; "
                "bulk-summary: best; code-gen: good; code-review: good; "
                "long-doc: best; math-reasoning: ok; planning: good; "
                "routing: ok; short-chat: good; vision: best.",
                "https://dev.meta.ai/docs/models"),
            "context_window": (
                10000000,
                "https://ai.meta.com/blog/llama-4-multimodal-intelligence"),
            "cost_tier": (
                "specialised",
                "https://dev.meta.ai/docs/models"),
            "modalities": (
                [
                    "text",
                    "image",
                ],
                "https://ai.meta.com/blog/llama-4-multimodal-intelligence"),
            "role_notes": (
                "auditor role: Best open auditor for very long documents.; "
                "director role: Good planner over huge corpora.; manager "
                "role: Good for map-reduce over long inputs.; worker role: "
                "Best worker for long-doc and bulk-summary..",
                "https://dev.meta.ai/docs/models"),
            "source_links": (
                [
                    "https://ai.meta.com/blog/llama-4-multimodal-intelligence",
                    "https://dev.meta.ai/docs/models",
                    "https://dev.meta.ai/docs/muse-glimmer",
                    "https://dev.meta.ai/docs/pricing-rate-limits",
                ],
                "https://dev.meta.ai/docs/models"),
            "strengths": (
                "reads as strong on 17B active / 109B total MoE with 16 "
                "experts; fits single H100 with Int4, 10M-token context "
                "(pre/post-trained 256K with iRoPE length generalisation), "
                "Best-in-class image grounding per Meta.",
                "https://dev.meta.ai/docs/models"),
            "weaknesses": (
                "watch out for Quality below Maverick on reasoning/coding, "
                "Very long contexts need specialised serving and "
                "verification for needles.",
                "https://dev.meta.ai/docs/models"),
        }),
    ],
    "mistral": [
        ("mistral-large-4", {
            "avoid_for": (
                "less suited to cheapest bulk chat (use Small 4 / "
                "Ministral). Task fit: agent-loop: best; code-gen: best; "
                "long-doc: best; math-reasoning: best; planning: best; "
                "vision: good.",
                "https://docs.mistral.ai/getting-started/models/"),
            "best_for": (
                "suited to demanding multimodal reasoning, agents, "
                "long-context frontier work. Task fit: agent-loop: best; "
                "code-gen: best; long-doc: best; math-reasoning: best; "
                "planning: best; vision: good.",
                "https://docs.mistral.ai/getting-started/models/"),
            "context_window": (
                1048576,
                "https://docs.mistral.ai/models/mistral-large-4-0"),
            "cost_tier": (
                "strong-reasoning",
                "https://docs.mistral.ai/getting-started/models/"),
            "currency": (
                "USD",
                "https://docs.mistral.ai/inference/pricing/"),
            "input_token_price": (
                0.68,
                "https://docs.mistral.ai/inference/pricing/"),
            "modalities": (
                [
                    "text",
                    "image",
                ],
                "https://docs.mistral.ai/models/mistral-large-4-0"),
            "output_token_price": (
                2.09,
                "https://docs.mistral.ai/inference/pricing/"),
            "role_notes": (
                "auditor role: best for deep audit; director role: best for "
                "hard planning; manager role: best for complex "
                "decomposition; worker role: best for hard execution.",
                "https://docs.mistral.ai/getting-started/models/"),
            "source_links": (
                [
                    "https://docs.mistral.ai/getting-started/models/",
                    "https://docs.mistral.ai/inference/pricing/",
                    "https://docs.mistral.ai/models/codestral-25-08",
                    "https://docs.mistral.ai/models/codestral-embed-25-05",
                    "https://docs.mistral.ai/models/ministral-3-8b-25-12",
                    "https://docs.mistral.ai/models/mistral-large-3-25-12",
                    "https://docs.mistral.ai/models/mistral-large-4-0",
                    "https://docs.mistral.ai/models/mistral-medium-3-5-26-04",
                    "https://docs.mistral.ai/models/mistral-small-4-0-26-03",
                    "https://docs.mistral.ai/models/ocr-4-1",
                ],
                "https://docs.mistral.ai/models/mistral-large-4-0"),
            "strengths": (
                "reads as strong on 52B-active MoE, 1.05T total; 1.6B vision "
                "encoder; structured outputs + function calling; open-weight.",
                "https://docs.mistral.ai/getting-started/models/"),
            "tool_calling": (
                True,
                "https://docs.mistral.ai/models/mistral-large-4-0"),
            "weaknesses": (
                "watch out for public preview status; sale pricing may "
                "revert ($1.36/$4.18); heaviest/slowest Mistral.",
                "https://docs.mistral.ai/getting-started/models/"),
        }),
        ("mistral-large-3", {
            "avoid_for": (
                "less suited to 1M-context needs (use Large 4). Task fit: "
                "agent-loop: good; code-gen: good; long-doc: good; planning: "
                "good; short-chat: good; vision: good.",
                "https://docs.mistral.ai/getting-started/models/"),
            "best_for": (
                "suited to general-purpose multimodal flagship work, "
                "open-weight deployment. Task fit: agent-loop: good; "
                "code-gen: good; long-doc: good; planning: good; short-chat: "
                "good; vision: good.",
                "https://docs.mistral.ai/getting-started/models/"),
            "context_window": (
                262144,
                "https://docs.mistral.ai/models/mistral-large-3-25-12"),
            "cost_tier": (
                "balanced",
                "https://docs.mistral.ai/getting-started/models/"),
            "currency": (
                "USD",
                "https://docs.mistral.ai/inference/pricing/"),
            "input_token_price": (
                0.5,
                "https://docs.mistral.ai/inference/pricing/"),
            "modalities": (
                [
                    "text",
                    "image",
                ],
                "https://docs.mistral.ai/models/mistral-large-3-25-12"),
            "output_token_price": (
                1.5,
                "https://docs.mistral.ai/inference/pricing/"),
            "role_notes": (
                "auditor role: good auditor; director role: good planner; "
                "manager role: good decomposer; worker role: good executor.",
                "https://docs.mistral.ai/getting-started/models/"),
            "source_links": (
                [
                    "https://docs.mistral.ai/getting-started/models/",
                    "https://docs.mistral.ai/inference/pricing/",
                    "https://docs.mistral.ai/models/codestral-25-08",
                    "https://docs.mistral.ai/models/codestral-embed-25-05",
                    "https://docs.mistral.ai/models/ministral-3-8b-25-12",
                    "https://docs.mistral.ai/models/mistral-large-3-25-12",
                    "https://docs.mistral.ai/models/mistral-large-4-0",
                    "https://docs.mistral.ai/models/mistral-medium-3-5-26-04",
                    "https://docs.mistral.ai/models/mistral-small-4-0-26-03",
                    "https://docs.mistral.ai/models/ocr-4-1",
                ],
                "https://docs.mistral.ai/models/mistral-large-4-0"),
            "strengths": (
                "reads as strong on 41B-active MoE, 675B total; Apache 2.0; "
                "agents/conversations + built-in tools support.",
                "https://docs.mistral.ai/getting-started/models/"),
            "tool_calling": (
                True,
                "https://docs.mistral.ai/models/mistral-large-3-25-12"),
            "weaknesses": (
                "watch out for 256k context vs Large 4 1M; pricier than "
                "Small for bulk work.",
                "https://docs.mistral.ai/getting-started/models/"),
        }),
        ("mistral-medium-3.5", {
            "avoid_for": (
                "less suited to budget bulk chat, cheapest edge inference. "
                "Task fit: agent-loop: best; code-gen: best; code-review: "
                "best; planning: best; vision: good.",
                "https://docs.mistral.ai/getting-started/models/"),
            "best_for": (
                "suited to frontier agentic + coding, open-weights flagship "
                "tasks. Task fit: agent-loop: best; code-gen: best; "
                "code-review: best; planning: best; vision: good.",
                "https://docs.mistral.ai/getting-started/models/"),
            "context_window": (
                262144,
                "https://docs.mistral.ai/models/mistral-medium-3-5-26-04"),
            "cost_tier": (
                "strong-reasoning",
                "https://docs.mistral.ai/getting-started/models/"),
            "currency": (
                "USD",
                "https://docs.mistral.ai/inference/pricing/"),
            "input_token_price": (
                1.5,
                "https://docs.mistral.ai/inference/pricing/"),
            "modalities": (
                [
                    "text",
                    "image",
                ],
                "https://docs.mistral.ai/models/mistral-medium-3-5-26-04"),
            "output_token_price": (
                7.5,
                "https://docs.mistral.ai/inference/pricing/"),
            "role_notes": (
                "auditor role: best for code audit; director role: best for "
                "agentic planning; manager role: best for coding "
                "workstreams; worker role: best for code-gen.",
                "https://docs.mistral.ai/getting-started/models/"),
            "source_links": (
                [
                    "https://docs.mistral.ai/getting-started/models/",
                    "https://docs.mistral.ai/inference/pricing/",
                    "https://docs.mistral.ai/models/codestral-25-08",
                    "https://docs.mistral.ai/models/codestral-embed-25-05",
                    "https://docs.mistral.ai/models/ministral-3-8b-25-12",
                    "https://docs.mistral.ai/models/mistral-large-3-25-12",
                    "https://docs.mistral.ai/models/mistral-large-4-0",
                    "https://docs.mistral.ai/models/mistral-medium-3-5-26-04",
                    "https://docs.mistral.ai/models/mistral-small-4-0-26-03",
                    "https://docs.mistral.ai/models/ocr-4-1",
                ],
                "https://docs.mistral.ai/models/mistral-large-4-0"),
            "strengths": (
                "reads as strong on frontier-class multimodal for "
                "agents/coding; modified MIT open weights; predicted outputs "
                "+ prefix support.",
                "https://docs.mistral.ai/getting-started/models/"),
            "tool_calling": (
                True,
                "https://docs.mistral.ai/models/mistral-medium-3-5-26-04"),
            "weaknesses": (
                "watch out for highest per-token price in Mistral flagship "
                "list; 256k context.",
                "https://docs.mistral.ai/getting-started/models/"),
        }),
        ("mistral-small-4", {
            "avoid_for": (
                "less suited to max-reasoning frontier tasks (use Medium 3.5 "
                "/ Large 4). Task fit: agent-loop: good; bulk-summary: good; "
                "code-gen: good; routing: best; short-chat: best.",
                "https://docs.mistral.ai/getting-started/models/"),
            "best_for": (
                "suited to cost-sensitive chat, coding assist, bulk agents, "
                "tool use. Task fit: agent-loop: good; bulk-summary: good; "
                "code-gen: good; routing: best; short-chat: best.",
                "https://docs.mistral.ai/getting-started/models/"),
            "context_window": (
                262144,
                "https://docs.mistral.ai/models/mistral-small-4-0-26-03"),
            "cost_tier": (
                "cheap-fast",
                "https://docs.mistral.ai/getting-started/models/"),
            "currency": (
                "USD",
                "https://docs.mistral.ai/inference/pricing/"),
            "input_token_price": (
                0.15,
                "https://docs.mistral.ai/inference/pricing/"),
            "output_token_price": (
                0.6,
                "https://docs.mistral.ai/inference/pricing/"),
            "role_notes": (
                "auditor role: ok first-pass reviewer; director role: good "
                "cheap router; manager role: good fan-out; worker role: best "
                "cheap executor.",
                "https://docs.mistral.ai/getting-started/models/"),
            "source_links": (
                [
                    "https://docs.mistral.ai/getting-started/models/",
                    "https://docs.mistral.ai/inference/pricing/",
                    "https://docs.mistral.ai/models/codestral-25-08",
                    "https://docs.mistral.ai/models/codestral-embed-25-05",
                    "https://docs.mistral.ai/models/ministral-3-8b-25-12",
                    "https://docs.mistral.ai/models/mistral-large-3-25-12",
                    "https://docs.mistral.ai/models/mistral-large-4-0",
                    "https://docs.mistral.ai/models/mistral-medium-3-5-26-04",
                    "https://docs.mistral.ai/models/mistral-small-4-0-26-03",
                    "https://docs.mistral.ai/models/ocr-4-1",
                ],
                "https://docs.mistral.ai/models/mistral-large-4-0"),
            "strengths": (
                "reads as strong on hybrid instruct+reasoning+coding in one "
                "119B (6.5B active) model; Apache 2.0; cheapest flagship "
                "per-token.",
                "https://docs.mistral.ai/getting-started/models/"),
            "tool_calling": (
                True,
                "https://docs.mistral.ai/models/mistral-small-4-0-26-03"),
            "weaknesses": (
                "watch out for below frontier on hard reasoning/math.",
                "https://docs.mistral.ai/getting-started/models/"),
        }),
        ("ministral-3-8b", {
            "avoid_for": (
                "less suited to long-doc giant contexts, vision-heavy "
                "frontier work. Task fit: bulk-summary: good; routing: good; "
                "short-chat: best.",
                "https://docs.mistral.ai/getting-started/models/"),
            "best_for": (
                "suited to efficient edge/small-device text+vision, cheap "
                "bulk chat. Task fit: bulk-summary: good; routing: good; "
                "short-chat: best.",
                "https://docs.mistral.ai/getting-started/models/"),
            "context_window": (
                262144,
                "https://docs.mistral.ai/models/ministral-3-8b-25-12"),
            "cost_tier": (
                "cheap-fast",
                "https://docs.mistral.ai/getting-started/models/"),
            "currency": (
                "USD",
                "https://docs.mistral.ai/inference/pricing/"),
            "input_token_price": (
                0.15,
                "https://docs.mistral.ai/inference/pricing/"),
            "modalities": (
                [
                    "text",
                    "image",
                ],
                "https://docs.mistral.ai/models/ministral-3-8b-25-12"),
            "output_token_price": (
                0.15,
                "https://docs.mistral.ai/inference/pricing/"),
            "role_notes": (
                "auditor role: avoid as sole auditor; director role: ok "
                "cheap router; manager role: ok for small splits; worker "
                "role: good cheap drafter.",
                "https://docs.mistral.ai/getting-started/models/"),
            "source_links": (
                [
                    "https://docs.mistral.ai/getting-started/models/",
                    "https://docs.mistral.ai/inference/pricing/",
                    "https://docs.mistral.ai/models/codestral-25-08",
                    "https://docs.mistral.ai/models/codestral-embed-25-05",
                    "https://docs.mistral.ai/models/ministral-3-8b-25-12",
                    "https://docs.mistral.ai/models/mistral-large-3-25-12",
                    "https://docs.mistral.ai/models/mistral-large-4-0",
                    "https://docs.mistral.ai/models/mistral-medium-3-5-26-04",
                    "https://docs.mistral.ai/models/mistral-small-4-0-26-03",
                    "https://docs.mistral.ai/models/ocr-4-1",
                ],
                "https://docs.mistral.ai/models/mistral-large-4-0"),
            "strengths": (
                "reads as strong on symmetric cheap in/out pricing; Apache "
                "2.0; text+vision per model listing.",
                "https://docs.mistral.ai/getting-started/models/"),
            "tool_calling": (
                True,
                "https://docs.mistral.ai/models/ministral-3-8b-25-12"),
            "weaknesses": (
                "watch out for context/output limits not re-verified this "
                "session; weakest reasoning tier.",
                "https://docs.mistral.ai/getting-started/models/"),
        }),
        ("codestral-25-08", {
            "avoid_for": (
                "less suited to general chat, vision, long-doc reasoning. "
                "Task fit: agent-loop: ok; code-gen: best; code-review: "
                "good; short-chat: ok.",
                "https://docs.mistral.ai/getting-started/models/"),
            "best_for": (
                "suited to code completion, fill-in-the-middle, code "
                "generation, coding agents. Task fit: agent-loop: ok; "
                "code-gen: best; code-review: good; short-chat: ok.",
                "https://docs.mistral.ai/getting-started/models/"),
            "context_window": (
                131072,
                "https://docs.mistral.ai/models/codestral-25-08"),
            "cost_tier": (
                "specialised",
                "https://docs.mistral.ai/getting-started/models/"),
            "currency": (
                "USD",
                "https://docs.mistral.ai/inference/pricing/"),
            "input_token_price": (
                0.3,
                "https://docs.mistral.ai/inference/pricing/"),
            "modalities": (
                [
                    "text",
                    "code",
                ],
                "https://docs.mistral.ai/models/codestral-25-08"),
            "output_token_price": (
                0.9,
                "https://docs.mistral.ai/inference/pricing/"),
            "role_notes": (
                "auditor role: good code auditor; director role: ok for code "
                "planning; manager role: good for code workstreams; worker "
                "role: best for completion/FIM.",
                "https://docs.mistral.ai/getting-started/models/"),
            "source_links": (
                [
                    "https://docs.mistral.ai/getting-started/models/",
                    "https://docs.mistral.ai/inference/pricing/",
                    "https://docs.mistral.ai/models/codestral-25-08",
                    "https://docs.mistral.ai/models/codestral-embed-25-05",
                    "https://docs.mistral.ai/models/ministral-3-8b-25-12",
                    "https://docs.mistral.ai/models/mistral-large-3-25-12",
                    "https://docs.mistral.ai/models/mistral-large-4-0",
                    "https://docs.mistral.ai/models/mistral-medium-3-5-26-04",
                    "https://docs.mistral.ai/models/mistral-small-4-0-26-03",
                    "https://docs.mistral.ai/models/ocr-4-1",
                ],
                "https://docs.mistral.ai/models/mistral-large-4-0"),
            "strengths": (
                "reads as strong on FIM endpoint; low-latency high-frequency "
                "completion; function calling + predicted outputs.",
                "https://docs.mistral.ai/getting-started/models/"),
            "tool_calling": (
                True,
                "https://docs.mistral.ai/models/codestral-25-08"),
            "weaknesses": (
                "watch out for 128k context; not for general reasoning/chat.",
                "https://docs.mistral.ai/getting-started/models/"),
        }),
        ("codestral-embed-25-05", {
            "avoid_for": (
                "less suited to chat, generation, reasoning. Task fit: "
                "embeddings: best.",
                "https://docs.mistral.ai/getting-started/models/"),
            "best_for": (
                "suited to code retrieval, RAG over codebases, similarity "
                "search. Task fit: embeddings: best.",
                "https://docs.mistral.ai/getting-started/models/"),
            "context_window": (
                8192,
                "https://docs.mistral.ai/models/codestral-embed-25-05"),
            "cost_tier": (
                "specialised",
                "https://docs.mistral.ai/getting-started/models/"),
            "currency": (
                "USD",
                "https://docs.mistral.ai/inference/pricing/"),
            "input_token_price": (
                0.15,
                "https://docs.mistral.ai/inference/pricing/"),
            "modalities": (
                [
                    "text",
                    "code",
                ],
                "https://docs.mistral.ai/models/codestral-embed-25-05"),
            "role_notes": (
                "auditor role: good for retrieval-backed audit; director "
                "role: ok for memory; manager role: ok for context assembly; "
                "worker role: best for code lookup.",
                "https://docs.mistral.ai/getting-started/models/"),
            "source_links": (
                [
                    "https://docs.mistral.ai/getting-started/models/",
                    "https://docs.mistral.ai/inference/pricing/",
                    "https://docs.mistral.ai/models/codestral-25-08",
                    "https://docs.mistral.ai/models/codestral-embed-25-05",
                    "https://docs.mistral.ai/models/ministral-3-8b-25-12",
                    "https://docs.mistral.ai/models/mistral-large-3-25-12",
                    "https://docs.mistral.ai/models/mistral-large-4-0",
                    "https://docs.mistral.ai/models/mistral-medium-3-5-26-04",
                    "https://docs.mistral.ai/models/mistral-small-4-0-26-03",
                    "https://docs.mistral.ai/models/ocr-4-1",
                ],
                "https://docs.mistral.ai/models/mistral-large-4-0"),
            "strengths": (
                "reads as strong on state-of-the-art code representation per "
                "docs; cheap per-token embed.",
                "https://docs.mistral.ai/getting-started/models/"),
            "tool_calling": (
                False,
                "https://docs.mistral.ai/models/codestral-embed-25-05"),
            "weaknesses": (
                "watch out for no output pricing (embed-only); dims/limits "
                "not re-verified.",
                "https://docs.mistral.ai/getting-started/models/"),
        }),
        ("ocr-4-1", {
            "avoid_for": (
                "less suited to chat, code, general reasoning. Task fit: "
                "long-doc: good; vision: best.",
                "https://docs.mistral.ai/getting-started/models/"),
            "best_for": (
                "suited to document understanding, OCR extraction, Document "
                "AI pipelines. Task fit: long-doc: good; vision: best.",
                "https://docs.mistral.ai/getting-started/models/"),
            "cost_tier": (
                "specialised",
                "https://docs.mistral.ai/getting-started/models/"),
            "currency": (
                "USD",
                "https://docs.mistral.ai/inference/pricing/"),
            "role_notes": (
                "auditor role: best for doc-evidence extraction; director "
                "role: ok for doc routing; manager role: good for doc "
                "workstreams; worker role: best for OCR extraction.",
                "https://docs.mistral.ai/getting-started/models/"),
            "source_links": (
                [
                    "https://docs.mistral.ai/getting-started/models/",
                    "https://docs.mistral.ai/inference/pricing/",
                    "https://docs.mistral.ai/models/codestral-25-08",
                    "https://docs.mistral.ai/models/codestral-embed-25-05",
                    "https://docs.mistral.ai/models/ministral-3-8b-25-12",
                    "https://docs.mistral.ai/models/mistral-large-3-25-12",
                    "https://docs.mistral.ai/models/mistral-large-4-0",
                    "https://docs.mistral.ai/models/mistral-medium-3-5-26-04",
                    "https://docs.mistral.ai/models/mistral-small-4-0-26-03",
                    "https://docs.mistral.ai/models/ocr-4-1",
                ],
                "https://docs.mistral.ai/models/mistral-large-4-0"),
            "strengths": (
                "reads as strong on paragraph boxes, block labels, block "
                "confidence scores; priced per 1000 pages ($4 in, $0.4 "
                "cached).",
                "https://docs.mistral.ai/getting-started/models/"),
            "tool_calling": (
                False,
                "https://docs.mistral.ai/models/ocr-4-1"),
            "weaknesses": (
                "watch out for page-based pricing not per-token; not for "
                "generative chat.",
                "https://docs.mistral.ai/getting-started/models/"),
        }),
    ],
    "openai": [
        ("gpt-6-astra", {
            "avoid_for": (
                "less suited to bulk cheap traffic, simple classification. "
                "Task fit: routing: ok; short-chat: good; long-doc: best; "
                "code-gen: best; code-review: best; planning: best; "
                "math-reasoning: best; agent-loop: best; vision: good.",
                "https://platform.openai.com/docs/models/gpt-6-astra"),
            "best_for": (
                "suited to complex reasoning, coding, computer use, "
                "research. Task fit: routing: ok; short-chat: good; "
                "long-doc: best; code-gen: best; code-review: best; "
                "planning: best; math-reasoning: best; agent-loop: best; "
                "vision: good.",
                "https://platform.openai.com/docs/models/gpt-6-astra"),
            "context_window": (
                1050000,
                "https://platform.openai.com/docs/models/gpt-6-astra"),
            "cost_tier": (
                "strong-reasoning",
                "https://platform.openai.com/docs/models/gpt-6-astra"),
            "input_token_price": (
                10,
                "https://platform.openai.com/docs/models/gpt-6-astra"),
            "knowledge_cutoff": (
                "2026-04-30",
                "https://platform.openai.com/docs/models/gpt-6-astra"),
            "max_output": (
                128000,
                "https://platform.openai.com/docs/models/gpt-6-astra"),
            "modalities": (
                [
                    "text-in",
                    "image-in",
                    "text-out",
                ],
                "https://platform.openai.com/docs/models/gpt-6-astra"),
            "output_token_price": (
                50,
                "https://platform.openai.com/docs/models/gpt-6-astra"),
            "reasoning": (
                True,
                "https://platform.openai.com/docs/models/gpt-6-astra"),
            "role_notes": (
                "director role: Hardest routing/planning only; costliest.; "
                "manager role: Reserve for escalations; delegate routine to "
                "Sol/Luna.; worker role: Hardest code-gen and agent-loop "
                "with high effort.; auditor role: Final verification of hard "
                "cases; sample due to cost..",
                "https://platform.openai.com/docs/models/gpt-6-astra"),
            "source_links": (
                [
                    "https://platform.openai.com/docs/deprecations",
                    "https://platform.openai.com/docs/guides/embeddings",
                    "https://platform.openai.com/docs/models/gpt-4o",
                    "https://platform.openai.com/docs/models/gpt-4o-mini",
                    "https://platform.openai.com/docs/models/gpt-4o-mini-tts",
                    "https://platform.openai.com/docs/models/gpt-5.4",
                    "https://platform.openai.com/docs/models/gpt-5.6-sol",
                    "https://platform.openai.com/docs/models/gpt-6-astra",
                    "https://platform.openai.com/docs/models/gpt-6-luna",
                    "https://platform.openai.com/docs/models/gpt-6.1-sol",
                    "https://platform.openai.com/docs/models/gpt-transcribe",
                    "https://platform.openai.com/docs/models/o3",
                    "https://platform.openai.com/docs/models/o4-mini",
                    "https://platform.openai.com/docs/pricing",
                ],
                "https://platform.openai.com/docs/models/gpt-6-astra"),
            "strengths": (
                "reads as strong on most capable flagship for demanding "
                "work, 1.05M context window, 128K max output, tools incl "
                "computer use and web/file search.",
                "https://platform.openai.com/docs/models/gpt-6-astra"),
            "tool_calling": (
                True,
                "https://platform.openai.com/docs/models/gpt-6-astra"),
            "weaknesses": (
                "watch out for highest price 10/50 USD per 1M, slow, "
                "overkill for simple tasks.",
                "https://platform.openai.com/docs/models/gpt-6-astra"),
        }),
        ("gpt-6.1-sol", {
            "avoid_for": (
                "less suited to ultra-high-volume cheap traffic. Task fit: "
                "routing: good; short-chat: best; long-doc: best; code-gen: "
                "best; code-review: best; planning: best; math-reasoning: "
                "best; agent-loop: best; vision: good.",
                "https://platform.openai.com/docs/models/gpt-6.1-sol"),
            "best_for": (
                "suited to balanced complex work, coding, agent workflows. "
                "Task fit: routing: good; short-chat: best; long-doc: best; "
                "code-gen: best; code-review: best; planning: best; "
                "math-reasoning: best; agent-loop: best; vision: good.",
                "https://platform.openai.com/docs/models/gpt-6.1-sol"),
            "context_window": (
                1050000,
                "https://platform.openai.com/docs/models/gpt-6.1-sol"),
            "cost_tier": (
                "balanced",
                "https://platform.openai.com/docs/models/gpt-6.1-sol"),
            "input_token_price": (
                2,
                "https://platform.openai.com/docs/models/gpt-6.1-sol"),
            "knowledge_cutoff": (
                "2026-04-30",
                "https://platform.openai.com/docs/models/gpt-6.1-sol"),
            "max_output": (
                128000,
                "https://platform.openai.com/docs/models/gpt-6.1-sol"),
            "modalities": (
                [
                    "text-in",
                    "image-in",
                    "text-out",
                ],
                "https://platform.openai.com/docs/models/gpt-6.1-sol"),
            "output_token_price": (
                10,
                "https://platform.openai.com/docs/models/gpt-6.1-sol"),
            "reasoning": (
                True,
                "https://platform.openai.com/docs/models/gpt-6.1-sol"),
            "role_notes": (
                "director role: Default choice for director-level "
                "reasoning.; manager role: Good default for managed task "
                "decomposition.; worker role: Primary worker for code-gen "
                "and planning.; auditor role: Good cost/quality for audits..",
                "https://platform.openai.com/docs/models/gpt-6.1-sol"),
            "source_links": (
                [
                    "https://platform.openai.com/docs/deprecations",
                    "https://platform.openai.com/docs/guides/embeddings",
                    "https://platform.openai.com/docs/models/gpt-4o",
                    "https://platform.openai.com/docs/models/gpt-4o-mini",
                    "https://platform.openai.com/docs/models/gpt-4o-mini-tts",
                    "https://platform.openai.com/docs/models/gpt-5.4",
                    "https://platform.openai.com/docs/models/gpt-5.6-sol",
                    "https://platform.openai.com/docs/models/gpt-6-astra",
                    "https://platform.openai.com/docs/models/gpt-6-luna",
                    "https://platform.openai.com/docs/models/gpt-6.1-sol",
                    "https://platform.openai.com/docs/models/gpt-transcribe",
                    "https://platform.openai.com/docs/models/o3",
                    "https://platform.openai.com/docs/models/o4-mini",
                    "https://platform.openai.com/docs/pricing",
                ],
                "https://platform.openai.com/docs/models/gpt-6-astra"),
            "strengths": (
                "reads as strong on near-Astra performance at lower cost, "
                "1.05M context, reasoning effort + verbosity control.",
                "https://platform.openai.com/docs/models/gpt-6.1-sol"),
            "tool_calling": (
                True,
                "https://platform.openai.com/docs/models/gpt-6.1-sol"),
            "weaknesses": (
                "watch out for still pricier than Luna/mini, not for "
                "realtime audio.",
                "https://platform.openai.com/docs/models/gpt-6.1-sol"),
        }),
        ("gpt-6-luna", {
            "avoid_for": (
                "less suited to frontier math/proof tasks. Task fit: "
                "routing: best; short-chat: best; long-doc: good; code-gen: "
                "good; code-review: good; planning: ok; math-reasoning: ok; "
                "agent-loop: good; vision: good; bulk-summary: best.",
                "https://platform.openai.com/docs/models/gpt-6-luna"),
            "best_for": (
                "suited to focused high-volume tasks, bulk summary, routing. "
                "Task fit: routing: best; short-chat: best; long-doc: good; "
                "code-gen: good; code-review: good; planning: ok; "
                "math-reasoning: ok; agent-loop: good; vision: good; "
                "bulk-summary: best.",
                "https://platform.openai.com/docs/models/gpt-6-luna"),
            "context_window": (
                1050000,
                "https://platform.openai.com/docs/models/gpt-6-luna"),
            "cost_tier": (
                "cheap-fast",
                "https://platform.openai.com/docs/models/gpt-6-luna"),
            "input_token_price": (
                0.1,
                "https://platform.openai.com/docs/models/gpt-6-luna"),
            "knowledge_cutoff": (
                "2026-05-18",
                "https://platform.openai.com/docs/models/gpt-6-luna"),
            "max_output": (
                128000,
                "https://platform.openai.com/docs/models/gpt-6-luna"),
            "modalities": (
                [
                    "text-in",
                    "image-in",
                    "text-out",
                ],
                "https://platform.openai.com/docs/models/gpt-6-luna"),
            "output_token_price": (
                0.5,
                "https://platform.openai.com/docs/models/gpt-6-luna"),
            "reasoning": (
                True,
                "https://platform.openai.com/docs/models/gpt-6-luna"),
            "role_notes": (
                "director role: Use for cheap triage/routing.; manager role: "
                "Fan-out bulk subtasks to Luna.; worker role: Bulk summary "
                "and short-chat workhorse.; auditor role: First-pass checks "
                "before Astra audit..",
                "https://platform.openai.com/docs/models/gpt-6-luna"),
            "source_links": (
                [
                    "https://platform.openai.com/docs/deprecations",
                    "https://platform.openai.com/docs/guides/embeddings",
                    "https://platform.openai.com/docs/models/gpt-4o",
                    "https://platform.openai.com/docs/models/gpt-4o-mini",
                    "https://platform.openai.com/docs/models/gpt-4o-mini-tts",
                    "https://platform.openai.com/docs/models/gpt-5.4",
                    "https://platform.openai.com/docs/models/gpt-5.6-sol",
                    "https://platform.openai.com/docs/models/gpt-6-astra",
                    "https://platform.openai.com/docs/models/gpt-6-luna",
                    "https://platform.openai.com/docs/models/gpt-6.1-sol",
                    "https://platform.openai.com/docs/models/gpt-transcribe",
                    "https://platform.openai.com/docs/models/o3",
                    "https://platform.openai.com/docs/models/o4-mini",
                    "https://platform.openai.com/docs/pricing",
                ],
                "https://platform.openai.com/docs/models/gpt-6-astra"),
            "strengths": (
                "reads as strong on most efficient GPT-6 for high volume, "
                "1.05M context at 0.10/0.50, tool calling + structured "
                "output.",
                "https://platform.openai.com/docs/models/gpt-6-luna"),
            "tool_calling": (
                True,
                "https://platform.openai.com/docs/models/gpt-6-luna"),
            "weaknesses": (
                "watch out for weaker than Astra/Sol on hardest reasoning.",
                "https://platform.openai.com/docs/models/gpt-6-luna"),
        }),
        ("gpt-5.6-sol", {
            "avoid_for": (
                "less suited to cheapest bulk jobs (use Luna/mini). Task "
                "fit: routing: good; short-chat: best; long-doc: best; "
                "code-gen: best; code-review: best; planning: best; "
                "math-reasoning: best; agent-loop: best; vision: good; "
                "bulk-summary: good.",
                "https://platform.openai.com/docs/models/gpt-5.6-sol"),
            "best_for": (
                "suited to complex professional work, coding, reasoning. "
                "Task fit: routing: good; short-chat: best; long-doc: best; "
                "code-gen: best; code-review: best; planning: best; "
                "math-reasoning: best; agent-loop: best; vision: good; "
                "bulk-summary: good.",
                "https://platform.openai.com/docs/models/gpt-5.6-sol"),
            "context_window": (
                1050000,
                "https://platform.openai.com/docs/models/gpt-5.6-sol"),
            "cost_tier": (
                "strong-reasoning",
                "https://platform.openai.com/docs/models/gpt-5.6-sol"),
            "input_token_price": (
                4,
                "https://platform.openai.com/docs/models/gpt-5.6-sol"),
            "knowledge_cutoff": (
                "2026-02-16",
                "https://platform.openai.com/docs/models/gpt-5.6-sol"),
            "max_output": (
                128000,
                "https://platform.openai.com/docs/models/gpt-5.6-sol"),
            "modalities": (
                [
                    "text-in",
                    "image-in",
                    "text-out",
                ],
                "https://platform.openai.com/docs/models/gpt-5.6-sol"),
            "output_token_price": (
                20,
                "https://platform.openai.com/docs/models/gpt-5.6-sol"),
            "reasoning": (
                True,
                "https://platform.openai.com/docs/models/gpt-5.6-sol"),
            "role_notes": (
                "director role: Solid fallback when GPT-6 quota limited.; "
                "manager role: Stable choice for managed pipelines.; worker "
                "role: Strong code-gen and math worker.; auditor role: "
                "Reliable audit model..",
                "https://platform.openai.com/docs/models/gpt-5.6-sol"),
            "source_links": (
                [
                    "https://platform.openai.com/docs/deprecations",
                    "https://platform.openai.com/docs/guides/embeddings",
                    "https://platform.openai.com/docs/models/gpt-4o",
                    "https://platform.openai.com/docs/models/gpt-4o-mini",
                    "https://platform.openai.com/docs/models/gpt-4o-mini-tts",
                    "https://platform.openai.com/docs/models/gpt-5.4",
                    "https://platform.openai.com/docs/models/gpt-5.6-sol",
                    "https://platform.openai.com/docs/models/gpt-6-astra",
                    "https://platform.openai.com/docs/models/gpt-6-luna",
                    "https://platform.openai.com/docs/models/gpt-6.1-sol",
                    "https://platform.openai.com/docs/models/gpt-transcribe",
                    "https://platform.openai.com/docs/models/o3",
                    "https://platform.openai.com/docs/models/o4-mini",
                    "https://platform.openai.com/docs/pricing",
                ],
                "https://platform.openai.com/docs/models/gpt-6-astra"),
            "strengths": (
                "reads as strong on flagship of 5.6 family for professional "
                "work, promo pricing through 2026-11-21, reasoning "
                "none/low/medium/high/xhigh/max.",
                "https://platform.openai.com/docs/models/gpt-5.6-sol"),
            "tool_calling": (
                True,
                "https://platform.openai.com/docs/models/gpt-5.6-sol"),
            "weaknesses": (
                "watch out for superseded by GPT-6 Astra for frontier tasks, "
                "long-context requests cost 2x/1.5x.",
                "https://platform.openai.com/docs/models/gpt-5.6-sol"),
        }),
        ("gpt-5.4", {
            "avoid_for": (
                "less suited to frontier reasoning (prefer 5.6-sol/6-astra). "
                "Task fit: routing: good; short-chat: best; long-doc: good; "
                "code-gen: good; code-review: good; planning: good; "
                "math-reasoning: good; agent-loop: good; vision: good; "
                "bulk-summary: good.",
                "https://platform.openai.com/docs/models/gpt-5.4"),
            "best_for": (
                "suited to general chat, coding assistance, document work. "
                "Task fit: routing: good; short-chat: best; long-doc: good; "
                "code-gen: good; code-review: good; planning: good; "
                "math-reasoning: good; agent-loop: good; vision: good; "
                "bulk-summary: good.",
                "https://platform.openai.com/docs/models/gpt-5.4"),
            "context_window": (
                1050000,
                "https://platform.openai.com/docs/models/gpt-5.4"),
            "cost_tier": (
                "balanced",
                "https://platform.openai.com/docs/models/gpt-5.4"),
            "input_token_price": (
                2.5,
                "https://platform.openai.com/docs/models/gpt-5.4"),
            "knowledge_cutoff": (
                "2025-08-31",
                "https://platform.openai.com/docs/models/gpt-5.4"),
            "max_output": (
                128000,
                "https://platform.openai.com/docs/models/gpt-5.4"),
            "modalities": (
                [
                    "text-in",
                    "image-in",
                    "text-out",
                ],
                "https://platform.openai.com/docs/models/gpt-5.4"),
            "output_token_price": (
                15,
                "https://platform.openai.com/docs/models/gpt-5.4"),
            "reasoning": (
                True,
                "https://platform.openai.com/docs/models/gpt-5.4"),
            "role_notes": (
                "director role: Legacy-compatible choice.; manager role: "
                "Safe for existing pipelines.; worker role: General worker "
                "tasks.; auditor role: Adequate for routine audits..",
                "https://platform.openai.com/docs/models/gpt-5.4"),
            "source_links": (
                [
                    "https://platform.openai.com/docs/deprecations",
                    "https://platform.openai.com/docs/guides/embeddings",
                    "https://platform.openai.com/docs/models/gpt-4o",
                    "https://platform.openai.com/docs/models/gpt-4o-mini",
                    "https://platform.openai.com/docs/models/gpt-4o-mini-tts",
                    "https://platform.openai.com/docs/models/gpt-5.4",
                    "https://platform.openai.com/docs/models/gpt-5.6-sol",
                    "https://platform.openai.com/docs/models/gpt-6-astra",
                    "https://platform.openai.com/docs/models/gpt-6-luna",
                    "https://platform.openai.com/docs/models/gpt-6.1-sol",
                    "https://platform.openai.com/docs/models/gpt-transcribe",
                    "https://platform.openai.com/docs/models/o3",
                    "https://platform.openai.com/docs/models/o4-mini",
                    "https://platform.openai.com/docs/pricing",
                ],
                "https://platform.openai.com/docs/models/gpt-6-astra"),
            "strengths": (
                "reads as strong on mature 5.x workhorse, 1.05M context, "
                "Responses + Chat Completions APIs.",
                "https://platform.openai.com/docs/models/gpt-5.4"),
            "tool_calling": (
                True,
                "https://platform.openai.com/docs/models/gpt-5.4"),
            "weaknesses": (
                "watch out for older cutoff Aug 2025, narrower than GPT-6 "
                "tool set.",
                "https://platform.openai.com/docs/models/gpt-5.4"),
        }),
        ("gpt-4o", {
            "avoid_for": (
                "less suited to hard multi-step reasoning (use o/GPT-6). "
                "Task fit: routing: good; short-chat: best; long-doc: good; "
                "code-gen: good; code-review: good; planning: ok; "
                "math-reasoning: ok; agent-loop: good; vision: best; "
                "translation-uk-en: good; bulk-summary: good.",
                "https://platform.openai.com/docs/models/gpt-4o"),
            "best_for": (
                "suited to general chat, vision tasks, fine-tuned variants. "
                "Task fit: routing: good; short-chat: best; long-doc: good; "
                "code-gen: good; code-review: good; planning: ok; "
                "math-reasoning: ok; agent-loop: good; vision: best; "
                "translation-uk-en: good; bulk-summary: good.",
                "https://platform.openai.com/docs/models/gpt-4o"),
            "context_window": (
                128000,
                "https://platform.openai.com/docs/models/gpt-4o"),
            "cost_tier": (
                "balanced",
                "https://platform.openai.com/docs/models/gpt-4o"),
            "input_token_price": (
                2.5,
                "https://platform.openai.com/docs/models/gpt-4o"),
            "knowledge_cutoff": (
                "2023-10-01",
                "https://platform.openai.com/docs/models/gpt-4o"),
            "max_output": (
                16384,
                "https://platform.openai.com/docs/models/gpt-4o"),
            "modalities": (
                [
                    "text-in",
                    "image-in",
                    "text-out",
                ],
                "https://platform.openai.com/docs/models/gpt-4o"),
            "output_token_price": (
                10,
                "https://platform.openai.com/docs/models/gpt-4o"),
            "role_notes": (
                "director role: Legacy default; migrate new work to "
                "GPT-5.6/6.; manager role: Stable for existing apps.; worker "
                "role: Everyday chat and vision worker.; auditor role: "
                "Baseline comparison model..",
                "https://platform.openai.com/docs/models/gpt-4o"),
            "source_links": (
                [
                    "https://platform.openai.com/docs/deprecations",
                    "https://platform.openai.com/docs/guides/embeddings",
                    "https://platform.openai.com/docs/models/gpt-4o",
                    "https://platform.openai.com/docs/models/gpt-4o-mini",
                    "https://platform.openai.com/docs/models/gpt-4o-mini-tts",
                    "https://platform.openai.com/docs/models/gpt-5.4",
                    "https://platform.openai.com/docs/models/gpt-5.6-sol",
                    "https://platform.openai.com/docs/models/gpt-6-astra",
                    "https://platform.openai.com/docs/models/gpt-6-luna",
                    "https://platform.openai.com/docs/models/gpt-6.1-sol",
                    "https://platform.openai.com/docs/models/gpt-transcribe",
                    "https://platform.openai.com/docs/models/o3",
                    "https://platform.openai.com/docs/models/o4-mini",
                    "https://platform.openai.com/docs/pricing",
                ],
                "https://platform.openai.com/docs/models/gpt-6-astra"),
            "strengths": (
                "reads as strong on versatile omni model, fine-tuning "
                "support, mature ecosystem.",
                "https://platform.openai.com/docs/models/gpt-4o"),
            "tool_calling": (
                True,
                "https://platform.openai.com/docs/models/gpt-4o"),
            "weaknesses": (
                "watch out for older cutoff Oct 2023, 128K context smaller "
                "than GPT-5/6, non-reasoning.",
                "https://platform.openai.com/docs/models/gpt-4o"),
        }),
        ("gpt-4o-mini", {
            "avoid_for": (
                "less suited to frontier coding/proofs. Task fit: routing: "
                "best; short-chat: best; long-doc: ok; code-gen: ok; "
                "code-review: ok; planning: ok; math-reasoning: avoid; "
                "agent-loop: ok; vision: good; translation-uk-en: good; "
                "bulk-summary: best.",
                "https://platform.openai.com/docs/models/gpt-4o-mini"),
            "best_for": (
                "suited to high-volume chat, classification, bulk summary. "
                "Task fit: routing: best; short-chat: best; long-doc: ok; "
                "code-gen: ok; code-review: ok; planning: ok; "
                "math-reasoning: avoid; agent-loop: ok; vision: good; "
                "translation-uk-en: good; bulk-summary: best.",
                "https://platform.openai.com/docs/models/gpt-4o-mini"),
            "context_window": (
                128000,
                "https://platform.openai.com/docs/models/gpt-4o-mini"),
            "cost_tier": (
                "cheap-fast",
                "https://platform.openai.com/docs/models/gpt-4o-mini"),
            "input_token_price": (
                0.15,
                "https://platform.openai.com/docs/models/gpt-4o-mini"),
            "knowledge_cutoff": (
                "2023-10-01",
                "https://platform.openai.com/docs/models/gpt-4o-mini"),
            "max_output": (
                16384,
                "https://platform.openai.com/docs/models/gpt-4o-mini"),
            "modalities": (
                [
                    "text-in",
                    "image-in",
                    "text-out",
                ],
                "https://platform.openai.com/docs/models/gpt-4o-mini"),
            "output_token_price": (
                0.6,
                "https://platform.openai.com/docs/models/gpt-4o-mini"),
            "role_notes": (
                "director role: Triage and bulk routing.; manager role: "
                "Fan-out cheap subtasks.; worker role: Default cheap "
                "worker.; auditor role: Cheap first pass..",
                "https://platform.openai.com/docs/models/gpt-4o-mini"),
            "source_links": (
                [
                    "https://platform.openai.com/docs/deprecations",
                    "https://platform.openai.com/docs/guides/embeddings",
                    "https://platform.openai.com/docs/models/gpt-4o",
                    "https://platform.openai.com/docs/models/gpt-4o-mini",
                    "https://platform.openai.com/docs/models/gpt-4o-mini-tts",
                    "https://platform.openai.com/docs/models/gpt-5.4",
                    "https://platform.openai.com/docs/models/gpt-5.6-sol",
                    "https://platform.openai.com/docs/models/gpt-6-astra",
                    "https://platform.openai.com/docs/models/gpt-6-luna",
                    "https://platform.openai.com/docs/models/gpt-6.1-sol",
                    "https://platform.openai.com/docs/models/gpt-transcribe",
                    "https://platform.openai.com/docs/models/o3",
                    "https://platform.openai.com/docs/models/o4-mini",
                    "https://platform.openai.com/docs/pricing",
                ],
                "https://platform.openai.com/docs/models/gpt-6-astra"),
            "strengths": (
                "reads as strong on fast affordable focused tasks, "
                "fine-tuning + distillation target, 128K context at low "
                "price.",
                "https://platform.openai.com/docs/models/gpt-4o-mini"),
            "tool_calling": (
                True,
                "https://platform.openai.com/docs/models/gpt-4o-mini"),
            "weaknesses": (
                "watch out for weaker on hard reasoning, older cutoff.",
                "https://platform.openai.com/docs/models/gpt-4o-mini"),
        }),
        ("o3", {
            "avoid_for": (
                "less suited to cheap chat, realtime audio. Task fit: "
                "routing: ok; short-chat: good; long-doc: good; code-gen: "
                "best; code-review: best; planning: best; math-reasoning: "
                "best; agent-loop: good; vision: good.",
                "https://platform.openai.com/docs/models/o3"),
            "best_for": (
                "suited to math reasoning, science, technical writing. Task "
                "fit: routing: ok; short-chat: good; long-doc: good; "
                "code-gen: best; code-review: best; planning: best; "
                "math-reasoning: best; agent-loop: good; vision: good.",
                "https://platform.openai.com/docs/models/o3"),
            "context_window": (
                200000,
                "https://platform.openai.com/docs/models/o3"),
            "cost_tier": (
                "strong-reasoning",
                "https://platform.openai.com/docs/models/o3"),
            "input_token_price": (
                2,
                "https://platform.openai.com/docs/models/o3"),
            "knowledge_cutoff": (
                "2024-06-01",
                "https://platform.openai.com/docs/models/o3"),
            "max_output": (
                100000,
                "https://platform.openai.com/docs/models/o3"),
            "modalities": (
                [
                    "text-in",
                    "image-in",
                    "text-out",
                ],
                "https://platform.openai.com/docs/models/o3"),
            "output_token_price": (
                8,
                "https://platform.openai.com/docs/models/o3"),
            "reasoning": (
                True,
                "https://platform.openai.com/docs/models/o3"),
            "role_notes": (
                "director role: Deep reasoning escalation.; manager role: "
                "Multi-step problem decomposition.; worker role: Think "
                "through code/math chains.; auditor role: Verify proofs and "
                "logic..",
                "https://platform.openai.com/docs/models/o3"),
            "source_links": (
                [
                    "https://platform.openai.com/docs/deprecations",
                    "https://platform.openai.com/docs/guides/embeddings",
                    "https://platform.openai.com/docs/models/gpt-4o",
                    "https://platform.openai.com/docs/models/gpt-4o-mini",
                    "https://platform.openai.com/docs/models/gpt-4o-mini-tts",
                    "https://platform.openai.com/docs/models/gpt-5.4",
                    "https://platform.openai.com/docs/models/gpt-5.6-sol",
                    "https://platform.openai.com/docs/models/gpt-6-astra",
                    "https://platform.openai.com/docs/models/gpt-6-luna",
                    "https://platform.openai.com/docs/models/gpt-6.1-sol",
                    "https://platform.openai.com/docs/models/gpt-transcribe",
                    "https://platform.openai.com/docs/models/o3",
                    "https://platform.openai.com/docs/models/o4-mini",
                    "https://platform.openai.com/docs/pricing",
                ],
                "https://platform.openai.com/docs/models/gpt-6-astra"),
            "strengths": (
                "reads as strong on strong math/science/coding reasoning, "
                "visual reasoning, succeeded by GPT-5 but still listed.",
                "https://platform.openai.com/docs/models/o3"),
            "tool_calling": (
                True,
                "https://platform.openai.com/docs/models/o3"),
            "weaknesses": (
                "watch out for snapshot deprecation announced for "
                "o3-2025-04-16 on 2026-12-11, migrate path is gpt-5.6-sol.",
                "https://platform.openai.com/docs/models/o3"),
        }),
        ("o4-mini", {
            "avoid_for": (
                "less suited to non-reasoning bulk chat. Task fit: routing: "
                "good; short-chat: good; long-doc: good; code-gen: best; "
                "code-review: good; planning: good; math-reasoning: best; "
                "agent-loop: good; vision: good.",
                "https://platform.openai.com/docs/models/o4-mini"),
            "best_for": (
                "suited to coding with reasoning, fast math help. Task fit: "
                "routing: good; short-chat: good; long-doc: good; code-gen: "
                "best; code-review: good; planning: good; math-reasoning: "
                "best; agent-loop: good; vision: good.",
                "https://platform.openai.com/docs/models/o4-mini"),
            "context_window": (
                200000,
                "https://platform.openai.com/docs/models/o4-mini"),
            "cost_tier": (
                "balanced",
                "https://platform.openai.com/docs/models/o4-mini"),
            "input_token_price": (
                1.1,
                "https://platform.openai.com/docs/models/o4-mini"),
            "knowledge_cutoff": (
                "2024-06-01",
                "https://platform.openai.com/docs/models/o4-mini"),
            "max_output": (
                100000,
                "https://platform.openai.com/docs/models/o4-mini"),
            "modalities": (
                [
                    "text-in",
                    "image-in",
                    "text-out",
                ],
                "https://platform.openai.com/docs/models/o4-mini"),
            "output_token_price": (
                4.4,
                "https://platform.openai.com/docs/models/o4-mini"),
            "reasoning": (
                True,
                "https://platform.openai.com/docs/models/o4-mini"),
            "role_notes": (
                "director role: Cheaper reasoning option.; manager role: "
                "Mid-tier reasoning delegation.; worker role: Efficient "
                "reasoning worker.; auditor role: Quick logic checks..",
                "https://platform.openai.com/docs/models/o4-mini"),
            "source_links": (
                [
                    "https://platform.openai.com/docs/deprecations",
                    "https://platform.openai.com/docs/guides/embeddings",
                    "https://platform.openai.com/docs/models/gpt-4o",
                    "https://platform.openai.com/docs/models/gpt-4o-mini",
                    "https://platform.openai.com/docs/models/gpt-4o-mini-tts",
                    "https://platform.openai.com/docs/models/gpt-5.4",
                    "https://platform.openai.com/docs/models/gpt-5.6-sol",
                    "https://platform.openai.com/docs/models/gpt-6-astra",
                    "https://platform.openai.com/docs/models/gpt-6-luna",
                    "https://platform.openai.com/docs/models/gpt-6.1-sol",
                    "https://platform.openai.com/docs/models/gpt-transcribe",
                    "https://platform.openai.com/docs/models/o3",
                    "https://platform.openai.com/docs/models/o4-mini",
                    "https://platform.openai.com/docs/pricing",
                ],
                "https://platform.openai.com/docs/models/gpt-6-astra"),
            "strengths": (
                "reads as strong on enhanced reasoning at lower cost, Chat + "
                "Responses APIs.",
                "https://platform.openai.com/docs/models/o4-mini"),
            "tool_calling": (
                True,
                "https://platform.openai.com/docs/models/o4-mini"),
            "weaknesses": (
                "watch out for fine-tuned/base snapshot retirement "
                "2026-10-23 per Azure/OpenAI schedule.",
                "https://platform.openai.com/docs/models/o4-mini"),
        }),
        ("text-embedding-3-large", {
            "avoid_for": (
                "less suited to generation tasks. Task fit: embeddings: "
                "best; long-doc: good; routing: good.",
                "https://platform.openai.com/docs/guides/embeddings"),
            "best_for": (
                "suited to search, clustering, RAG retrieval. Task fit: "
                "embeddings: best; long-doc: good; routing: good.",
                "https://platform.openai.com/docs/guides/embeddings"),
            "context_window": (
                8192,
                "https://platform.openai.com/docs/guides/embeddings"),
            "cost_tier": (
                "specialised",
                "https://platform.openai.com/docs/guides/embeddings"),
            "input_token_price": (
                0.13,
                "https://platform.openai.com/docs/pricing"),
            "modalities": (
                [
                    "text-in",
                    "vector-out",
                ],
                "https://platform.openai.com/docs/guides/embeddings"),
            "role_notes": (
                "director role: Use for routing via similarity.; manager "
                "role: RAG retrieval backbone.; worker role: Embed docs "
                "before generation.; auditor role: Similarity checks for "
                "duplicates..",
                "https://platform.openai.com/docs/guides/embeddings"),
            "source_links": (
                [
                    "https://platform.openai.com/docs/deprecations",
                    "https://platform.openai.com/docs/guides/embeddings",
                    "https://platform.openai.com/docs/models/gpt-4o",
                    "https://platform.openai.com/docs/models/gpt-4o-mini",
                    "https://platform.openai.com/docs/models/gpt-4o-mini-tts",
                    "https://platform.openai.com/docs/models/gpt-5.4",
                    "https://platform.openai.com/docs/models/gpt-5.6-sol",
                    "https://platform.openai.com/docs/models/gpt-6-astra",
                    "https://platform.openai.com/docs/models/gpt-6-luna",
                    "https://platform.openai.com/docs/models/gpt-6.1-sol",
                    "https://platform.openai.com/docs/models/gpt-transcribe",
                    "https://platform.openai.com/docs/models/o3",
                    "https://platform.openai.com/docs/models/o4-mini",
                    "https://platform.openai.com/docs/pricing",
                ],
                "https://platform.openai.com/docs/models/gpt-6-astra"),
            "strengths": (
                "reads as strong on most capable embedding, 3072 dims, MTEB "
                "64.6 and MIRACL 54.9, dimensions parameter for cost "
                "tradeoff.",
                "https://platform.openai.com/docs/guides/embeddings"),
            "weaknesses": (
                "watch out for no upgrade path from ada; must re-embed, text "
                "only.",
                "https://platform.openai.com/docs/guides/embeddings"),
        }),
        ("gpt-4o-mini-tts", {
            "avoid_for": (
                "less suited to text reasoning tasks. Task fit: speech: "
                "best; short-chat: ok.",
                "https://platform.openai.com/docs/models/gpt-4o-mini-tts"),
            "best_for": (
                "suited to narration, voice interfaces. Task fit: speech: "
                "best; short-chat: ok.",
                "https://platform.openai.com/docs/models/gpt-4o-mini-tts"),
            "context_window": (
                2000,
                "https://platform.openai.com/docs/models/gpt-4o-mini-tts"),
            "cost_tier": (
                "specialised",
                "https://platform.openai.com/docs/models/gpt-4o-mini-tts"),
            "input_token_price": (
                0.6,
                "https://platform.openai.com/docs/models/gpt-4o-mini-tts"),
            "modalities": (
                [
                    "text-in",
                    "audio-out",
                ],
                "https://platform.openai.com/docs/models/gpt-4o-mini-tts"),
            "output_token_price": (
                12.0,
                "https://platform.openai.com/docs/models/gpt-4o-mini-tts"),
            "role_notes": (
                "director role: Voice output only.; manager role: Chained "
                "voice workflows.; worker role: Generate narration audio.; "
                "auditor role: UNKNOWN.",
                "https://platform.openai.com/docs/models/gpt-4o-mini-tts"),
            "source_links": (
                [
                    "https://platform.openai.com/docs/deprecations",
                    "https://platform.openai.com/docs/guides/embeddings",
                    "https://platform.openai.com/docs/models/gpt-4o",
                    "https://platform.openai.com/docs/models/gpt-4o-mini",
                    "https://platform.openai.com/docs/models/gpt-4o-mini-tts",
                    "https://platform.openai.com/docs/models/gpt-5.4",
                    "https://platform.openai.com/docs/models/gpt-5.6-sol",
                    "https://platform.openai.com/docs/models/gpt-6-astra",
                    "https://platform.openai.com/docs/models/gpt-6-luna",
                    "https://platform.openai.com/docs/models/gpt-6.1-sol",
                    "https://platform.openai.com/docs/models/gpt-transcribe",
                    "https://platform.openai.com/docs/models/o3",
                    "https://platform.openai.com/docs/models/o4-mini",
                    "https://platform.openai.com/docs/pricing",
                ],
                "https://platform.openai.com/docs/models/gpt-6-astra"),
            "strengths": (
                "reads as strong on natural TTS powered by GPT-4o mini, low "
                "text input price.",
                "https://platform.openai.com/docs/models/gpt-4o-mini-tts"),
            "weaknesses": (
                "watch out for dated snapshots deprecated 2027-01-06; "
                "migrate to gpt-realtime-2.1-mini.",
                "https://platform.openai.com/docs/models/gpt-4o-mini-tts"),
        }),
        ("gpt-transcribe", {
            "avoid_for": (
                "less suited to generation and reasoning. Task fit: speech: "
                "best.",
                "https://platform.openai.com/docs/models/gpt-transcribe"),
            "best_for": (
                "suited to transcription, captions. Task fit: speech: best.",
                "https://platform.openai.com/docs/models/gpt-transcribe"),
            "cost_tier": (
                "specialised",
                "https://platform.openai.com/docs/models/gpt-transcribe"),
            "modalities": (
                [
                    "audio-in",
                    "text-in",
                    "text-out",
                ],
                "https://platform.openai.com/docs/models/gpt-transcribe"),
            "role_notes": (
                "director role: Ingest audio evidence.; manager role: "
                "Transcribe meetings.; worker role: Produce transcripts.; "
                "auditor role: UNKNOWN.",
                "https://platform.openai.com/docs/models/gpt-transcribe"),
            "source_links": (
                [
                    "https://platform.openai.com/docs/deprecations",
                    "https://platform.openai.com/docs/guides/embeddings",
                    "https://platform.openai.com/docs/models/gpt-4o",
                    "https://platform.openai.com/docs/models/gpt-4o-mini",
                    "https://platform.openai.com/docs/models/gpt-4o-mini-tts",
                    "https://platform.openai.com/docs/models/gpt-5.4",
                    "https://platform.openai.com/docs/models/gpt-5.6-sol",
                    "https://platform.openai.com/docs/models/gpt-6-astra",
                    "https://platform.openai.com/docs/models/gpt-6-luna",
                    "https://platform.openai.com/docs/models/gpt-6.1-sol",
                    "https://platform.openai.com/docs/models/gpt-transcribe",
                    "https://platform.openai.com/docs/models/o3",
                    "https://platform.openai.com/docs/models/o4-mini",
                    "https://platform.openai.com/docs/pricing",
                ],
                "https://platform.openai.com/docs/models/gpt-6-astra"),
            "strengths": (
                "reads as strong on high-accuracy STT at 0.0045 USD per "
                "minute, replacement for whisper-1 and gpt-4o-transcribe.",
                "https://platform.openai.com/docs/models/gpt-transcribe"),
            "weaknesses": (
                "watch out for per-minute billing not per-token; no "
                "reasoning.",
                "https://platform.openai.com/docs/models/gpt-transcribe"),
        }),
    ],
    "openrouter": [
        ("openrouter-meta-muse-spark-1.3", {
            "avoid_for": (
                "less suited to Cheapest bulk single-turn chat; "
                "latency-critical simple tasks. Task fit: general: best.",
                "https://openrouter.ai/meta/muse-spark-1.3"),
            "best_for": (
                "suited to Long-horizon agentic, multi-agent and coding "
                "workflows. Task fit: general: best.",
                "https://openrouter.ai/meta/muse-spark-1.3"),
            "cost_tier": (
                "strong-reasoning",
                "https://openrouter.ai/meta/muse-spark-1.3"),
            "modalities": (
                [
                    "text",
                ],
                "https://openrouter.ai/meta/muse-spark-1.3"),
            "reasoning": (
                True,
                "https://openrouter.ai/meta/muse-spark-1.3"),
            "role_notes": (
                "auditor role: Fits audit of long agent traces given 131K "
                "output limit.; director role: Candidate director-level "
                "planner; verify spend caps first.; manager role: Good "
                "manager decomposer for multi-step plans.; worker role: "
                "Strong worker for coding subtasks when budget allows..",
                "https://openrouter.ai/meta/muse-spark-1.3"),
            "source_links": (
                [
                    "https://openrouter.ai/api/v1/models",
                    "https://openrouter.ai/deepseek/deepseek-v4-flash-0731",
                    "https://openrouter.ai/google/gemma-4-12b-it",
                    "https://openrouter.ai/meta/muse-spark-1.3",
                    "https://openrouter.ai/microsoft/mai-code-1-flash",
                    "https://openrouter.ai/mistral/mistral-medium-latest",
                    "https://openrouter.ai/qwen/qwen3.8-27b",
                ],
                "https://openrouter.ai/meta/muse-spark-1.3"),
            "strengths": (
                "reads as strong on 1M context with 131K output limit, Tool "
                "calling, reasoning and structured output, Built for "
                "long-running agent collaboration.",
                "https://openrouter.ai/meta/muse-spark-1.3"),
            "tool_calling": (
                True,
                "https://openrouter.ai/meta/muse-spark-1.3"),
            "weaknesses": (
                "watch out for Closed weights, Top-tier price band.",
                "https://openrouter.ai/meta/muse-spark-1.3"),
        }),
        ("openrouter-qwen-qwen3.8-27b", {
            "avoid_for": (
                "less suited to Tasks needing 1M context; unvetted "
                "data-residency setups. Task fit: general: best.",
                "https://openrouter.ai/qwen/qwen3.8-27b"),
            "best_for": (
                "suited to Coding agents, tool use and multilingual chat via "
                "aggregator. Task fit: general: best.",
                "https://openrouter.ai/qwen/qwen3.8-27b"),
            "cost_tier": (
                "balanced",
                "https://openrouter.ai/qwen/qwen3.8-27b"),
            "modalities": (
                [
                    "text",
                ],
                "https://openrouter.ai/qwen/qwen3.8-27b"),
            "reasoning": (
                True,
                "https://openrouter.ai/qwen/qwen3.8-27b"),
            "role_notes": (
                "auditor role: Good auditor for code and multilingual "
                "content.; director role: Usable director for mid-size "
                "planning.; manager role: Good manager; structured output "
                "helps task splits.; worker role: Best-value worker for "
                "coding subtasks..",
                "https://openrouter.ai/qwen/qwen3.8-27b"),
            "source_links": (
                [
                    "https://openrouter.ai/api/v1/models",
                    "https://openrouter.ai/deepseek/deepseek-v4-flash-0731",
                    "https://openrouter.ai/google/gemma-4-12b-it",
                    "https://openrouter.ai/meta/muse-spark-1.3",
                    "https://openrouter.ai/microsoft/mai-code-1-flash",
                    "https://openrouter.ai/mistral/mistral-medium-latest",
                    "https://openrouter.ai/qwen/qwen3.8-27b",
                ],
                "https://openrouter.ai/meta/muse-spark-1.3"),
            "strengths": (
                "reads as strong on Open weights with Hugging Face link, "
                "Vision-language dense 27B for coding and agents, Cheap "
                "OpenRouter input price.",
                "https://openrouter.ai/qwen/qwen3.8-27b"),
            "tool_calling": (
                True,
                "https://openrouter.ai/qwen/qwen3.8-27b"),
            "weaknesses": (
                "watch out for Output price above input price, 262K context "
                "below 1M rivals.",
                "https://openrouter.ai/qwen/qwen3.8-27b"),
        }),
        ("openrouter-google-gemma-4-12b-it", {
            "avoid_for": (
                "less suited to Primary reasoning-heavy agent loops; vision "
                "tasks. Task fit: general: good.",
                "https://openrouter.ai/google/gemma-4-12b-it"),
            "best_for": (
                "suited to Self-hosted chat and light reasoning via "
                "aggregator endpoints. Task fit: general: good.",
                "https://openrouter.ai/google/gemma-4-12b-it"),
            "cost_tier": (
                "balanced",
                "https://openrouter.ai/google/gemma-4-12b-it"),
            "role_notes": (
                "auditor role: OK auditor for short chat transcripts.; "
                "director role: Avoid as director; compact model.; manager "
                "role: OK manager for small splits.; worker role: Good "
                "worker for cheap chat subtasks..",
                "https://openrouter.ai/google/gemma-4-12b-it"),
            "source_links": (
                [
                    "https://openrouter.ai/api/v1/models",
                    "https://openrouter.ai/deepseek/deepseek-v4-flash-0731",
                    "https://openrouter.ai/google/gemma-4-12b-it",
                    "https://openrouter.ai/meta/muse-spark-1.3",
                    "https://openrouter.ai/microsoft/mai-code-1-flash",
                    "https://openrouter.ai/mistral/mistral-medium-latest",
                    "https://openrouter.ai/qwen/qwen3.8-27b",
                ],
                "https://openrouter.ai/meta/muse-spark-1.3"),
            "strengths": (
                "reads as strong on Compact 12B open-weight instruction "
                "model, Tool calling and structured output support, 262K "
                "context for its size.",
                "https://openrouter.ai/google/gemma-4-12b-it"),
            "weaknesses": (
                "watch out for No OpenRouter price row found; cost unknown, "
                "No reasoning flag.",
                "https://openrouter.ai/google/gemma-4-12b-it"),
        }),
        ("openrouter-deepseek-v4-flash-0731", {
            "avoid_for": (
                "less suited to Strict-budget high-volume simple chat. Task "
                "fit: general: best.",
                "https://openrouter.ai/deepseek/deepseek-v4-flash-0731"),
            "best_for": (
                "suited to Agentic coding, tool use and long-context "
                "reasoning via aggregator. Task fit: general: best.",
                "https://openrouter.ai/deepseek/deepseek-v4-flash-0731"),
            "cost_tier": (
                "balanced",
                "https://openrouter.ai/deepseek/deepseek-v4-flash-0731"),
            "modalities": (
                [
                    "text",
                ],
                "https://openrouter.ai/deepseek/deepseek-v4-flash-0731"),
            "reasoning": (
                True,
                "https://openrouter.ai/deepseek/deepseek-v4-flash-0731"),
            "role_notes": (
                "auditor role: Strong auditor for code and reasoning "
                "traces.; director role: Candidate director for technical "
                "planning.; manager role: Good manager for coding work "
                "breakdown.; worker role: Best worker for agentic coding at "
                "low input price..",
                "https://openrouter.ai/deepseek/deepseek-v4-flash-0731"),
            "source_links": (
                [
                    "https://openrouter.ai/api/v1/models",
                    "https://openrouter.ai/deepseek/deepseek-v4-flash-0731",
                    "https://openrouter.ai/google/gemma-4-12b-it",
                    "https://openrouter.ai/meta/muse-spark-1.3",
                    "https://openrouter.ai/microsoft/mai-code-1-flash",
                    "https://openrouter.ai/mistral/mistral-medium-latest",
                    "https://openrouter.ai/qwen/qwen3.8-27b",
                ],
                "https://openrouter.ai/meta/muse-spark-1.3"),
            "strengths": (
                "reads as strong on 1M context with 384K output limit, Open "
                "weights on Hugging Face, Low OpenRouter input price.",
                "https://openrouter.ai/deepseek/deepseek-v4-flash-0731"),
            "tool_calling": (
                True,
                "https://openrouter.ai/deepseek/deepseek-v4-flash-0731"),
            "weaknesses": (
                "watch out for Newer release; provider quality varies by "
                "endpoint, Output price above input price.",
                "https://openrouter.ai/deepseek/deepseek-v4-flash-0731"),
        }),
        ("openrouter-mistral-medium-latest", {
            "avoid_for": (
                "less suited to Cheap high-volume inference without price "
                "check. Task fit: general: good.",
                "https://openrouter.ai/mistral/mistral-medium-latest"),
            "best_for": (
                "suited to Enterprise assistants, multilingual work and tool "
                "workflows. Task fit: general: good.",
                "https://openrouter.ai/mistral/mistral-medium-latest"),
            "cost_tier": (
                "balanced",
                "https://openrouter.ai/mistral/mistral-medium-latest"),
            "role_notes": (
                "auditor role: Good auditor for assistant transcripts.; "
                "director role: Usable director for enterprise planning.; "
                "manager role: Good manager; large output window.; worker "
                "role: OK worker; confirm price before bulk use..",
                "https://openrouter.ai/mistral/mistral-medium-latest"),
            "source_links": (
                [
                    "https://openrouter.ai/api/v1/models",
                    "https://openrouter.ai/deepseek/deepseek-v4-flash-0731",
                    "https://openrouter.ai/google/gemma-4-12b-it",
                    "https://openrouter.ai/meta/muse-spark-1.3",
                    "https://openrouter.ai/microsoft/mai-code-1-flash",
                    "https://openrouter.ai/mistral/mistral-medium-latest",
                    "https://openrouter.ai/qwen/qwen3.8-27b",
                ],
                "https://openrouter.ai/meta/muse-spark-1.3"),
            "strengths": (
                "reads as strong on 262K context and 262K output limit, "
                "Tools, reasoning and structured output, Open weights "
                "reference on Hugging Face.",
                "https://openrouter.ai/mistral/mistral-medium-latest"),
            "weaknesses": (
                "watch out for No OpenRouter price row found; cost unknown, "
                "Mid-size flagship; weaker than largest rivals.",
                "https://openrouter.ai/mistral/mistral-medium-latest"),
        }),
        ("openrouter-microsoft-mai-code-1-flash", {
            "avoid_for": (
                "less suited to General chat outside coding; long-context "
                "RAG. Task fit: general: good.",
                "https://openrouter.ai/microsoft/mai-code-1-flash"),
            "best_for": (
                "suited to Fast everyday developer coding assistance. Task "
                "fit: general: good.",
                "https://openrouter.ai/microsoft/mai-code-1-flash"),
            "cost_tier": (
                "balanced",
                "https://openrouter.ai/microsoft/mai-code-1-flash"),
            "role_notes": (
                "auditor role: OK auditor for code diffs.; director role: "
                "Avoid as director; coding-specialised.; manager role: OK "
                "manager for dev task splits.; worker role: Good worker for "
                "fast code subtasks..",
                "https://openrouter.ai/microsoft/mai-code-1-flash"),
            "source_links": (
                [
                    "https://openrouter.ai/api/v1/models",
                    "https://openrouter.ai/deepseek/deepseek-v4-flash-0731",
                    "https://openrouter.ai/google/gemma-4-12b-it",
                    "https://openrouter.ai/meta/muse-spark-1.3",
                    "https://openrouter.ai/microsoft/mai-code-1-flash",
                    "https://openrouter.ai/mistral/mistral-medium-latest",
                    "https://openrouter.ai/qwen/qwen3.8-27b",
                ],
                "https://openrouter.ai/meta/muse-spark-1.3"),
            "strengths": (
                "reads as strong on Coding-specialised with tool support, "
                "256K context with 128K output, Reasoning and structured "
                "output flags.",
                "https://openrouter.ai/microsoft/mai-code-1-flash"),
            "weaknesses": (
                "watch out for Closed weights, No OpenRouter price row "
                "found; cost unknown.",
                "https://openrouter.ai/microsoft/mai-code-1-flash"),
        }),
    ],
    "perplexity": [
        ("sonar", {
            "avoid_for": (
                "less suited to deep multi-step analysis (use "
                "pro/reasoning), exhaustive research reports, complex "
                "instruction-following chains. Task fit: agent-loop: ok; "
                "bulk-summary: good; long-doc: ok; routing: best; "
                "short-chat: best.",
                "https://docs.perplexity.ai/getting-started/pricing"),
            "best_for": (
                "suited to quick factual QA with citations, topic summaries "
                "and comparisons, current-events grounding. Task fit: "
                "agent-loop: ok; bulk-summary: good; long-doc: ok; routing: "
                "best; short-chat: best.",
                "https://docs.perplexity.ai/getting-started/pricing"),
            "cost_tier": (
                "cheap-fast",
                "https://docs.perplexity.ai/getting-started/pricing"),
            "currency": (
                "USD",
                "https://docs.perplexity.ai/getting-started/pricing"),
            "input_token_price": (
                1.0,
                "https://docs.perplexity.ai/getting-started/pricing"),
            "output_token_price": (
                1.0,
                "https://docs.perplexity.ai/getting-started/pricing"),
            "role_notes": (
                "auditor role: Citations included; verify sources before "
                "sign-off.; director role: Cheapest grounded lookup tier.; "
                "manager role: Fan-out quick research.; worker role: Default "
                "fast research worker..",
                "https://docs.perplexity.ai/getting-started/pricing"),
            "source_links": (
                [
                    "https://docs.perplexity.ai/docs/agent-api/migrate-from-sonar"
                    "/overview",
                    "https://docs.perplexity.ai/docs/resources/changelog",
                    "https://docs.perplexity.ai/getting-started/models",
                    "https://docs.perplexity.ai/getting-started/pricing",
                ],
                "https://docs.perplexity.ai/getting-started/pricing"),
            "strengths": (
                "reads as strong on Lightweight cost-effective search "
                "grounding with citations, Customizable sources; request fee "
                "low $5/1K at low context, Maps to Agent API fast preset.",
                "https://docs.perplexity.ai/getting-started/pricing"),
            "weaknesses": (
                "watch out for Chat Completions support ended 2026-09-27; "
                "served via Agent reformulation, Per-request fee on top of "
                "tokens, Not for multi-step analysis.",
                "https://docs.perplexity.ai/getting-started/pricing"),
        }),
        ("sonar-pro", {
            "avoid_for": (
                "less suited to trivial lookups where sonar is cheaper, "
                "offline non-search tasks, bulk jobs ignoring request fees. "
                "Task fit: agent-loop: good; bulk-summary: best; long-doc: "
                "best; routing: good; short-chat: good.",
                "https://docs.perplexity.ai/getting-started/pricing"),
            "best_for": (
                "suited to complex research questions, comparative "
                "multi-source analysis, information synthesis and reporting. "
                "Task fit: agent-loop: good; bulk-summary: best; long-doc: "
                "best; routing: good; short-chat: good.",
                "https://docs.perplexity.ai/getting-started/pricing"),
            "cost_tier": (
                "balanced",
                "https://docs.perplexity.ai/getting-started/pricing"),
            "currency": (
                "USD",
                "https://docs.perplexity.ai/getting-started/pricing"),
            "input_token_price": (
                3.0,
                "https://docs.perplexity.ai/getting-started/pricing"),
            "output_token_price": (
                15.0,
                "https://docs.perplexity.ai/getting-started/pricing"),
            "role_notes": (
                "auditor role: Double citations per search aid "
                "verification.; director role: Mid-tier research choice.; "
                "manager role: Everyday research manager.; worker role: "
                "Research worker for synthesis..",
                "https://docs.perplexity.ai/getting-started/pricing"),
            "source_links": (
                [
                    "https://docs.perplexity.ai/docs/agent-api/migrate-from-sonar"
                    "/overview",
                    "https://docs.perplexity.ai/docs/resources/changelog",
                    "https://docs.perplexity.ai/getting-started/models",
                    "https://docs.perplexity.ai/getting-started/pricing",
                ],
                "https://docs.perplexity.ai/getting-started/pricing"),
            "strengths": (
                "reads as strong on 2x search results vs sonar; 200K "
                "context, Pro Search mode for multi-step tool use, Vision "
                "input support.",
                "https://docs.perplexity.ai/getting-started/pricing"),
            "weaknesses": (
                "watch out for High output price $15/1M, Request fee "
                "$6-14/1K by context, Chat Completions sunset; use Agent API.",
                "https://docs.perplexity.ai/getting-started/pricing"),
        }),
        ("sonar-reasoning-pro", {
            "avoid_for": (
                "less suited to simple factual queries, speed-priority "
                "lookups, image+structured-output combos (unsupported). Task "
                "fit: agent-loop: good; long-doc: good; math-reasoning: "
                "good; planning: good; routing: ok; short-chat: ok.",
                "https://docs.perplexity.ai/getting-started/pricing"),
            "best_for": (
                "suited to step-by-step reasoning over sources, multi-hop "
                "browsing and aggregation, instruction-strict synthesis. "
                "Task fit: agent-loop: good; long-doc: good; math-reasoning: "
                "good; planning: good; routing: ok; short-chat: ok.",
                "https://docs.perplexity.ai/getting-started/pricing"),
            "cost_tier": (
                "strong-reasoning",
                "https://docs.perplexity.ai/getting-started/pricing"),
            "currency": (
                "USD",
                "https://docs.perplexity.ai/getting-started/pricing"),
            "input_token_price": (
                2.0,
                "https://docs.perplexity.ai/getting-started/pricing"),
            "output_token_price": (
                8.0,
                "https://docs.perplexity.ai/getting-started/pricing"),
            "reasoning": (
                True,
                "https://docs.perplexity.ai/docs/resources/changelog"),
            "role_notes": (
                "auditor role: Chain-of-thought section aids audit trail.; "
                "director role: Reasoning-heavy research choice.; manager "
                "role: Multi-hop research manager.; worker role: Reasoning "
                "worker; handle think tags..",
                "https://docs.perplexity.ai/getting-started/pricing"),
            "source_links": (
                [
                    "https://docs.perplexity.ai/docs/agent-api/migrate-from-sonar"
                    "/overview",
                    "https://docs.perplexity.ai/docs/resources/changelog",
                    "https://docs.perplexity.ai/getting-started/models",
                    "https://docs.perplexity.ai/getting-started/pricing",
                ],
                "https://docs.perplexity.ai/getting-started/pricing"),
            "strengths": (
                "reads as strong on Chain-of-thought reasoning with search "
                "grounding, Request fee $6-14/1K; maps to Agent low preset, "
                "Good for logical problem solving.",
                "https://docs.perplexity.ai/getting-started/pricing"),
            "weaknesses": (
                "watch out for Image input with structured outputs "
                "unsupported, Slower than non-reasoning sonar, Chat "
                "Completions sunset path.",
                "https://docs.perplexity.ai/getting-started/pricing"),
        }),
        ("sonar-deep-research", {
            "avoid_for": (
                "less suited to quick cheap lookups, single-fact QA, "
                "latency-critical loops. Task fit: agent-loop: ok; "
                "bulk-summary: best; long-doc: best; planning: good; "
                "routing: ok.",
                "https://docs.perplexity.ai/getting-started/pricing"),
            "best_for": (
                "suited to exhaustive deep research reports, market and "
                "literature analysis, multi-source comprehensive synthesis. "
                "Task fit: agent-loop: ok; bulk-summary: best; long-doc: "
                "best; planning: good; routing: ok.",
                "https://docs.perplexity.ai/getting-started/pricing"),
            "cost_tier": (
                "strong-reasoning",
                "https://docs.perplexity.ai/getting-started/pricing"),
            "currency": (
                "USD",
                "https://docs.perplexity.ai/getting-started/pricing"),
            "input_token_price": (
                2.0,
                "https://docs.perplexity.ai/getting-started/pricing"),
            "output_token_price": (
                8.0,
                "https://docs.perplexity.ai/getting-started/pricing"),
            "reasoning": (
                True,
                "https://docs.perplexity.ai/docs/resources/changelog"),
            "role_notes": (
                "auditor role: Exhaustive source coverage; still verify "
                "citations.; director role: Top-tier research assignment.; "
                "manager role: Deep research orchestrator.; worker role: "
                "Long-running research worker..",
                "https://docs.perplexity.ai/getting-started/pricing"),
            "source_links": (
                [
                    "https://docs.perplexity.ai/docs/agent-api/migrate-from-sonar"
                    "/overview",
                    "https://docs.perplexity.ai/docs/resources/changelog",
                    "https://docs.perplexity.ai/getting-started/models",
                    "https://docs.perplexity.ai/getting-started/pricing",
                ],
                "https://docs.perplexity.ai/getting-started/pricing"),
            "strengths": (
                "reads as strong on Expert-level exhaustive search and "
                "reporting, Extra billing dimensions: citation $2/1M, "
                "reasoning $3/1M, Maps to Agent high preset.",
                "https://docs.perplexity.ai/getting-started/pricing"),
            "weaknesses": (
                "watch out for Search queries billed $5/1K extra, Slowest "
                "and most expensive sonar tier, Overkill for simple queries.",
                "https://docs.perplexity.ai/getting-started/pricing"),
        }),
        ("sonar-pro-search", {
            "avoid_for": (
                "less suited to simple single-search QA (overkill), cheap "
                "bulk without tool loop, non-search offline tasks. Task fit: "
                "agent-loop: best; long-doc: best; planning: good; routing: "
                "ok; short-chat: ok.",
                "https://docs.perplexity.ai/getting-started/pricing"),
            "best_for": (
                "suited to agentic multi-step research workflows, autonomous "
                "plan-and-execute search, deep analysis with tools. Task "
                "fit: agent-loop: best; long-doc: best; planning: good; "
                "routing: ok; short-chat: ok.",
                "https://docs.perplexity.ai/getting-started/pricing"),
            "cost_tier": (
                "strong-reasoning",
                "https://docs.perplexity.ai/getting-started/pricing"),
            "role_notes": (
                "auditor role: Trace autonomous tool steps in output.; "
                "director role: Agentic research flagship.; manager role: "
                "Workflow orchestrator.; worker role: Agentic search worker..",
                "https://docs.perplexity.ai/getting-started/pricing"),
            "source_links": (
                [
                    "https://docs.perplexity.ai/docs/agent-api/migrate-from-sonar"
                    "/overview",
                    "https://docs.perplexity.ai/docs/resources/changelog",
                    "https://docs.perplexity.ai/getting-started/models",
                    "https://docs.perplexity.ai/getting-started/pricing",
                ],
                "https://docs.perplexity.ai/getting-started/pricing"),
            "strengths": (
                "reads as strong on Autonomous multi-step reasoning vs "
                "single query+synthesis, 200K context with vision, web "
                "search, streaming, Extended thinking trace.",
                "https://docs.perplexity.ai/getting-started/pricing"),
            "weaknesses": (
                "watch out for Pricing per tokens plus ~$18/1K requests, "
                "Secondary-source context figures, Heaviest tier for simple "
                "needs.",
                "https://docs.perplexity.ai/getting-started/pricing"),
        }),
        ("perplexity/sonar", {
            "avoid_for": (
                "less suited to pure offline generation without search, "
                "single-shot cheap lookup (use sonar), workflows needing "
                "classic chat choices shape. Task fit: agent-loop: best; "
                "bulk-summary: good; routing: best; short-chat: best.",
                "https://docs.perplexity.ai/getting-started/pricing"),
            "best_for": (
                "suited to agent API grounded answers, tool-call search "
                "workflows, migrated sonar traffic (no code change on "
                "gateway). Task fit: agent-loop: best; bulk-summary: good; "
                "routing: best; short-chat: best.",
                "https://docs.perplexity.ai/getting-started/pricing"),
            "cost_tier": (
                "cheap-fast",
                "https://docs.perplexity.ai/getting-started/pricing"),
            "currency": (
                "USD",
                "https://docs.perplexity.ai/getting-started/models"),
            "input_token_price": (
                0.25,
                "https://docs.perplexity.ai/getting-started/models"),
            "output_token_price": (
                2.5,
                "https://docs.perplexity.ai/getting-started/models"),
            "role_notes": (
                "auditor role: Model decides search; verify when no search "
                "ran.; director role: Default Agent API grounded model.; "
                "manager role: Agentic loop with search-as-tool.; worker "
                "role: Agent worker; searches metered individually..",
                "https://docs.perplexity.ai/getting-started/pricing"),
            "source_links": (
                [
                    "https://docs.perplexity.ai/docs/agent-api/migrate-from-sonar"
                    "/overview",
                    "https://docs.perplexity.ai/docs/resources/changelog",
                    "https://docs.perplexity.ai/getting-started/models",
                    "https://docs.perplexity.ai/getting-started/pricing",
                ],
                "https://docs.perplexity.ai/getting-started/pricing"),
            "strengths": (
                "reads as strong on Agent API drops flat per-request fee; "
                "searches metered individually, Lower input price than "
                "classic sonar; cache pricing separate, Same model id keeps "
                "working on new transport.",
                "https://docs.perplexity.ai/getting-started/pricing"),
            "weaknesses": (
                "watch out for Output tokens priced higher than classic "
                "path, Behavioral change: model decides whether to search, "
                "Async sonar requests unsupported.",
                "https://docs.perplexity.ai/getting-started/pricing"),
        }),
    ],
    "together": [
        ("openai/gpt-oss-120b", {
            "avoid_for": (
                "less suited to 1M-context long-doc. Task fit: routing: "
                "good; short-chat: good; code-gen: best; code-review: good; "
                "planning: best; math-reasoning: best; agent-loop: best.",
                "https://docs.together.ai/docs/serverless-models"),
            "best_for": (
                "suited to agent-loop, code-gen on budget. Task fit: "
                "routing: good; short-chat: good; code-gen: best; "
                "code-review: good; planning: best; math-reasoning: best; "
                "agent-loop: best.",
                "https://docs.together.ai/docs/serverless-models"),
            "context_window": (
                131072,
                "https://docs.together.ai/docs/serverless-models"),
            "cost_tier": (
                "strong-reasoning",
                "https://docs.together.ai/docs/serverless-models"),
            "currency": (
                "USD",
                "https://www.together.ai/pricing"),
            "input_token_price": (
                0.15,
                "https://www.together.ai/pricing"),
            "modalities": (
                [
                    "text",
                ],
                "https://www.together.ai/models/gpt-oss-120b"),
            "output_token_price": (
                0.6,
                "https://www.together.ai/pricing"),
            "reasoning": (
                True,
                "https://docs.together.ai/docs/inference/chat/reasoning"),
            "role_notes": (
                "director role: budget reasoning default; manager role: "
                "orchestration; worker role: code execution; auditor role: "
                "verify outputs.",
                "https://docs.together.ai/docs/serverless-models"),
            "source_links": (
                [
                    "https://docs.together.ai/docs/inference/chat/reasoning",
                    "https://docs.together.ai/docs/serverless-models",
                    "https://www.together.ai/models/deepseek-v4-pro-0813",
                    "https://www.together.ai/models/glm-5-3",
                    "https://www.together.ai/models/glm-5-3-flash",
                    "https://www.together.ai/models/gpt-oss-120b",
                    "https://www.together.ai/models/kimi-k3",
                    "https://www.together.ai/models/minimax-m3",
                    "https://www.together.ai/models/muse-glimmer",
                    "https://www.together.ai/pricing",
                ],
                "https://www.together.ai/models/gpt-oss-120b"),
            "strengths": (
                "reads as strong on cheapest strong reasoning host, MXFP4 "
                "quant, function calling + structured outputs, fine-tunable "
                "on Together.",
                "https://docs.together.ai/docs/serverless-models"),
            "tool_calling": (
                True,
                "https://docs.together.ai/docs/serverless-models"),
            "weaknesses": (
                "watch out for 131K context smaller than 1M rivals, "
                "open-weight ceiling.",
                "https://docs.together.ai/docs/serverless-models"),
        }),
        ("zai-org/GLM-5.3", {
            "avoid_for": (
                "less suited to cheap bulk summarization. Task fit: "
                "long-doc: best; planning: best; math-reasoning: best; "
                "agent-loop: best; code-gen: best; code-review: best; "
                "routing: ok; short-chat: good.",
                "https://docs.together.ai/docs/serverless-models"),
            "best_for": (
                "suited to long-doc, planning, agent-loop over big repos. "
                "Task fit: long-doc: best; planning: best; math-reasoning: "
                "best; agent-loop: best; code-gen: best; code-review: best; "
                "routing: ok; short-chat: good.",
                "https://docs.together.ai/docs/serverless-models"),
            "context_window": (
                1048575,
                "https://docs.together.ai/docs/serverless-models"),
            "cost_tier": (
                "strong-reasoning",
                "https://docs.together.ai/docs/serverless-models"),
            "currency": (
                "USD",
                "https://www.together.ai/pricing"),
            "input_token_price": (
                1.4,
                "https://www.together.ai/pricing"),
            "modalities": (
                [
                    "text",
                ],
                "https://www.together.ai/models/glm-5-3"),
            "output_token_price": (
                4.4,
                "https://www.together.ai/pricing"),
            "reasoning": (
                True,
                "https://www.together.ai/models/glm-5-3"),
            "role_notes": (
                "director role: long-context flagship; manager role: "
                "big-repo planning; worker role: deep reasoning execution; "
                "auditor role: cross-check long-context citations.",
                "https://docs.together.ai/docs/serverless-models"),
            "source_links": (
                [
                    "https://docs.together.ai/docs/inference/chat/reasoning",
                    "https://docs.together.ai/docs/serverless-models",
                    "https://www.together.ai/models/deepseek-v4-pro-0813",
                    "https://www.together.ai/models/glm-5-3",
                    "https://www.together.ai/models/glm-5-3-flash",
                    "https://www.together.ai/models/gpt-oss-120b",
                    "https://www.together.ai/models/kimi-k3",
                    "https://www.together.ai/models/minimax-m3",
                    "https://www.together.ai/models/muse-glimmer",
                    "https://www.together.ai/pricing",
                ],
                "https://www.together.ai/models/gpt-oss-120b"),
            "strengths": (
                "reads as strong on 1M context flagship reasoning, function "
                "calling + structured outputs, FP4 efficient serving.",
                "https://docs.together.ai/docs/serverless-models"),
            "tool_calling": (
                True,
                "https://docs.together.ai/docs/serverless-models"),
            "weaknesses": (
                "watch out for $1.40/$4.40 premium over Flash, cached input "
                "still $0.26.",
                "https://docs.together.ai/docs/serverless-models"),
        }),
        ("zai-org/GLM-5.3-Flash", {
            "avoid_for": (
                "less suited to frontier math-reasoning finals. Task fit: "
                "routing: good; short-chat: good; long-doc: best; code-gen: "
                "good; planning: good; agent-loop: best; bulk-summary: best.",
                "https://docs.together.ai/docs/serverless-models"),
            "best_for": (
                "suited to long-doc triage, bulk-summary, cheap agent loops. "
                "Task fit: routing: good; short-chat: good; long-doc: best; "
                "code-gen: good; planning: good; agent-loop: best; "
                "bulk-summary: best.",
                "https://docs.together.ai/docs/serverless-models"),
            "context_window": (
                1048575,
                "https://docs.together.ai/docs/serverless-models"),
            "cost_tier": (
                "cheap-fast",
                "https://docs.together.ai/docs/serverless-models"),
            "currency": (
                "USD",
                "https://www.together.ai/pricing"),
            "input_token_price": (
                0.15,
                "https://www.together.ai/pricing"),
            "modalities": (
                [
                    "text",
                    "vision",
                ],
                "https://www.together.ai/models/glm-5-3-flash"),
            "output_token_price": (
                0.5,
                "https://www.together.ai/pricing"),
            "reasoning": (
                True,
                "https://www.together.ai/models/glm-5-3-flash"),
            "role_notes": (
                "director role: cheap long-context default; manager role: "
                "triage then escalate; worker role: bulk summarization; "
                "auditor role: sample-verify summaries.",
                "https://docs.together.ai/docs/serverless-models"),
            "source_links": (
                [
                    "https://docs.together.ai/docs/inference/chat/reasoning",
                    "https://docs.together.ai/docs/serverless-models",
                    "https://www.together.ai/models/deepseek-v4-pro-0813",
                    "https://www.together.ai/models/glm-5-3",
                    "https://www.together.ai/models/glm-5-3-flash",
                    "https://www.together.ai/models/gpt-oss-120b",
                    "https://www.together.ai/models/kimi-k3",
                    "https://www.together.ai/models/minimax-m3",
                    "https://www.together.ai/models/muse-glimmer",
                    "https://www.together.ai/pricing",
                ],
                "https://www.together.ai/models/gpt-oss-120b"),
            "strengths": (
                "reads as strong on 1M context at $0.15/$0.50, same tool + "
                "structured support as full 5.3, best price per long-context "
                "token.",
                "https://docs.together.ai/docs/serverless-models"),
            "tool_calling": (
                True,
                "https://docs.together.ai/docs/serverless-models"),
            "weaknesses": (
                "watch out for weaker than full GLM-5.3 on hard reasoning, "
                "quality gap on frontier code tasks.",
                "https://docs.together.ai/docs/serverless-models"),
        }),
        ("moonshotai/Kimi-K3", {
            "avoid_for": (
                "less suited to cost-sensitive bulk work. Task fit: "
                "long-doc: best; vision: best; agent-loop: best; code-gen: "
                "best; planning: best; math-reasoning: good; short-chat: "
                "good; routing: ok.",
                "https://docs.together.ai/docs/serverless-models"),
            "best_for": (
                "suited to vision long-doc, premium agent-loop. Task fit: "
                "long-doc: best; vision: best; agent-loop: best; code-gen: "
                "best; planning: best; math-reasoning: good; short-chat: "
                "good; routing: ok.",
                "https://docs.together.ai/docs/serverless-models"),
            "context_window": (
                1048576,
                "https://docs.together.ai/docs/serverless-models"),
            "cost_tier": (
                "strong-reasoning",
                "https://docs.together.ai/docs/serverless-models"),
            "currency": (
                "USD",
                "https://www.together.ai/pricing"),
            "input_token_price": (
                2.7,
                "https://www.together.ai/pricing"),
            "modalities": (
                [
                    "text",
                    "vision",
                ],
                "https://www.together.ai/models/kimi-k3"),
            "output_token_price": (
                13.5,
                "https://www.together.ai/pricing"),
            "reasoning": (
                True,
                "https://docs.together.ai/docs/inference/chat/reasoning"),
            "role_notes": (
                "director role: premium vision-reasoning pick; manager role: "
                "multimodal planning; worker role: vision+code execution; "
                "auditor role: verify vision grounding and cost.",
                "https://docs.together.ai/docs/serverless-models"),
            "source_links": (
                [
                    "https://docs.together.ai/docs/inference/chat/reasoning",
                    "https://docs.together.ai/docs/serverless-models",
                    "https://www.together.ai/models/deepseek-v4-pro-0813",
                    "https://www.together.ai/models/glm-5-3",
                    "https://www.together.ai/models/glm-5-3-flash",
                    "https://www.together.ai/models/gpt-oss-120b",
                    "https://www.together.ai/models/kimi-k3",
                    "https://www.together.ai/models/minimax-m3",
                    "https://www.together.ai/models/muse-glimmer",
                    "https://www.together.ai/pricing",
                ],
                "https://www.together.ai/models/gpt-oss-120b"),
            "strengths": (
                "reads as strong on 1M context vision+text reasoning, strong "
                "agentic coding lineage (Kimi K2 family), function calling + "
                "structured outputs.",
                "https://docs.together.ai/docs/serverless-models"),
            "tool_calling": (
                True,
                "https://docs.together.ai/docs/serverless-models"),
            "weaknesses": (
                "watch out for most expensive pick ($2.70/$13.50), promo "
                "pricing unstable.",
                "https://docs.together.ai/docs/serverless-models"),
        }),
        ("meta-models/Muse-Glimmer-30B", {
            "avoid_for": (
                "less suited to 1M-context repos. Task fit: code-gen: best; "
                "code-review: best; short-chat: best; routing: good; "
                "planning: good; math-reasoning: good; agent-loop: good.",
                "https://docs.together.ai/docs/serverless-models"),
            "best_for": (
                "suited to balanced code-gen and code-review. Task fit: "
                "code-gen: best; code-review: best; short-chat: best; "
                "routing: good; planning: good; math-reasoning: good; "
                "agent-loop: good.",
                "https://docs.together.ai/docs/serverless-models"),
            "context_window": (
                131072,
                "https://docs.together.ai/docs/serverless-models"),
            "cost_tier": (
                "balanced",
                "https://docs.together.ai/docs/serverless-models"),
            "currency": (
                "USD",
                "https://www.together.ai/pricing"),
            "input_token_price": (
                0.35,
                "https://www.together.ai/pricing"),
            "modalities": (
                [
                    "text",
                    "vision",
                ],
                "https://www.together.ai/models/muse-glimmer"),
            "output_token_price": (
                1.5,
                "https://www.together.ai/pricing"),
            "reasoning": (
                True,
                "https://www.together.ai/models/muse-glimmer"),
            "role_notes": (
                "director role: balanced mid-tier default; manager role: "
                "code-review dispatch; worker role: implement and review; "
                "auditor role: review correctness.",
                "https://docs.together.ai/docs/serverless-models"),
            "source_links": (
                [
                    "https://docs.together.ai/docs/inference/chat/reasoning",
                    "https://docs.together.ai/docs/serverless-models",
                    "https://www.together.ai/models/deepseek-v4-pro-0813",
                    "https://www.together.ai/models/glm-5-3",
                    "https://www.together.ai/models/glm-5-3-flash",
                    "https://www.together.ai/models/gpt-oss-120b",
                    "https://www.together.ai/models/kimi-k3",
                    "https://www.together.ai/models/minimax-m3",
                    "https://www.together.ai/models/muse-glimmer",
                    "https://www.together.ai/pricing",
                ],
                "https://www.together.ai/models/gpt-oss-120b"),
            "strengths": (
                "reads as strong on $0.35/$1.50 efficient reasoning, "
                "function calling + structured outputs, cached input only "
                "$0.04.",
                "https://docs.together.ai/docs/serverless-models"),
            "tool_calling": (
                True,
                "https://docs.together.ai/docs/serverless-models"),
            "weaknesses": (
                "watch out for 30B ceiling below 100B+ models, 131K context "
                "only.",
                "https://docs.together.ai/docs/serverless-models"),
        }),
        ("deepseek-ai/DeepSeek-V4-Pro-0813", {
            "avoid_for": (
                "less suited to cheap high-volume chat. Task fit: "
                "math-reasoning: best; long-doc: best; code-gen: best; "
                "code-review: best; planning: best; agent-loop: best; "
                "routing: ok; short-chat: good.",
                "https://docs.together.ai/docs/serverless-models"),
            "best_for": (
                "suited to math-reasoning, long-doc code analysis. Task fit: "
                "math-reasoning: best; long-doc: best; code-gen: best; "
                "code-review: best; planning: best; agent-loop: best; "
                "routing: ok; short-chat: good.",
                "https://docs.together.ai/docs/serverless-models"),
            "context_window": (
                1048576,
                "https://docs.together.ai/docs/serverless-models"),
            "cost_tier": (
                "strong-reasoning",
                "https://docs.together.ai/docs/serverless-models"),
            "currency": (
                "USD",
                "https://www.together.ai/pricing"),
            "input_token_price": (
                1.32,
                "https://www.together.ai/pricing"),
            "modalities": (
                [
                    "text",
                ],
                "https://www.together.ai/models/deepseek-v4-pro-0813"),
            "output_token_price": (
                3.96,
                "https://www.together.ai/pricing"),
            "reasoning": (
                True,
                "https://docs.together.ai/docs/inference/chat/reasoning"),
            "role_notes": (
                "director role: math/code flagship alternate; manager role: "
                "hard-problem routing; worker role: deep analysis; auditor "
                "role: verify proofs and code.",
                "https://docs.together.ai/docs/serverless-models"),
            "source_links": (
                [
                    "https://docs.together.ai/docs/inference/chat/reasoning",
                    "https://docs.together.ai/docs/serverless-models",
                    "https://www.together.ai/models/deepseek-v4-pro-0813",
                    "https://www.together.ai/models/glm-5-3",
                    "https://www.together.ai/models/glm-5-3-flash",
                    "https://www.together.ai/models/gpt-oss-120b",
                    "https://www.together.ai/models/kimi-k3",
                    "https://www.together.ai/models/minimax-m3",
                    "https://www.together.ai/models/muse-glimmer",
                    "https://www.together.ai/pricing",
                ],
                "https://www.together.ai/models/gpt-oss-120b"),
            "strengths": (
                "reads as strong on 1M context deep reasoning, NVFP4 "
                "serving, cached input $0.13, strong math/code lineage.",
                "https://docs.together.ai/docs/serverless-models"),
            "tool_calling": (
                True,
                "https://docs.together.ai/docs/serverless-models"),
            "weaknesses": (
                "watch out for premium output price $3.96, new 0813 "
                "snapshot, track record short.",
                "https://docs.together.ai/docs/serverless-models"),
        }),
        ("MiniMaxAI/MiniMax-M3", {
            "avoid_for": (
                "less suited to frontier math finals. Task fit: vision: "
                "best; bulk-summary: best; long-doc: best; short-chat: good; "
                "routing: good; code-gen: good; agent-loop: good.",
                "https://docs.together.ai/docs/serverless-models"),
            "best_for": (
                "suited to vision bulk-summary, cheap long-doc. Task fit: "
                "vision: best; bulk-summary: best; long-doc: best; "
                "short-chat: good; routing: good; code-gen: good; "
                "agent-loop: good.",
                "https://docs.together.ai/docs/serverless-models"),
            "context_window": (
                524288,
                "https://docs.together.ai/docs/serverless-models"),
            "cost_tier": (
                "balanced",
                "https://docs.together.ai/docs/serverless-models"),
            "currency": (
                "USD",
                "https://www.together.ai/pricing"),
            "input_token_price": (
                0.3,
                "https://www.together.ai/pricing"),
            "modalities": (
                [
                    "text",
                    "vision",
                ],
                "https://www.together.ai/models/minimax-m3"),
            "output_token_price": (
                1.2,
                "https://www.together.ai/pricing"),
            "reasoning": (
                True,
                "https://docs.together.ai/docs/inference/chat/reasoning"),
            "role_notes": (
                "director role: cheap vision-long-context pick; manager "
                "role: doc+image triage; worker role: summarize and extract; "
                "auditor role: check extraction fidelity.",
                "https://docs.together.ai/docs/serverless-models"),
            "source_links": (
                [
                    "https://docs.together.ai/docs/inference/chat/reasoning",
                    "https://docs.together.ai/docs/serverless-models",
                    "https://www.together.ai/models/deepseek-v4-pro-0813",
                    "https://www.together.ai/models/glm-5-3",
                    "https://www.together.ai/models/glm-5-3-flash",
                    "https://www.together.ai/models/gpt-oss-120b",
                    "https://www.together.ai/models/kimi-k3",
                    "https://www.together.ai/models/minimax-m3",
                    "https://www.together.ai/models/muse-glimmer",
                    "https://www.together.ai/pricing",
                ],
                "https://www.together.ai/models/gpt-oss-120b"),
            "strengths": (
                "reads as strong on 524K vision+text at $0.30/$1.20, cached "
                "input $0.06, FP4 efficient.",
                "https://docs.together.ai/docs/serverless-models"),
            "tool_calling": (
                True,
                "https://docs.together.ai/docs/serverless-models"),
            "weaknesses": (
                "watch out for narrower ecosystem than Qwen/DeepSeek, "
                "mid-tier reasoning depth.",
                "https://docs.together.ai/docs/serverless-models"),
        }),
    ],
    "xai": [
        ("grok-4.7", {
            "avoid_for": (
                "less suited to Cheapest bulk jobs (use grok-4.3 or "
                "build-0.1); tight budget long-context runs. Task fit: "
                "agent-loop: best; bulk-summary: good; code-gen: best; "
                "code-review: best; long-doc: best; math-reasoning: best; "
                "planning: best; routing: good; short-chat: good; vision: "
                "good.",
                "https://docs.x.ai/docs/models"),
            "best_for": (
                "suited to Frontier code-gen, math-reasoning, agent loops "
                "with tools, long-doc over 500k context. Task fit: "
                "agent-loop: best; bulk-summary: good; code-gen: best; "
                "code-review: best; long-doc: best; math-reasoning: best; "
                "planning: best; routing: good; short-chat: good; vision: "
                "good.",
                "https://docs.x.ai/docs/models"),
            "context_window": (
                500000,
                "https://docs.x.ai/docs/models/grok-4.7"),
            "cost_tier": (
                "strong-reasoning",
                "https://docs.x.ai/docs/models"),
            "currency": (
                "USD",
                "https://docs.x.ai/docs/pricing"),
            "input_token_price": (
                2.0,
                "https://docs.x.ai/docs/pricing"),
            "knowledge_cutoff": (
                "2026-05",
                "https://docs.x.ai/docs/models"),
            "modalities": (
                [
                    "text",
                    "image",
                ],
                "https://docs.x.ai/docs/models/grok-4.7"),
            "output_token_price": (
                6.0,
                "https://docs.x.ai/docs/pricing"),
            "reasoning": (
                True,
                "https://docs.x.ai/docs/models/grok-4.7"),
            "role_notes": (
                "auditor role: Strong auditor with encrypted reasoning trace "
                "on Responses API.; director role: Best xAI director for "
                "planning and decomposition.; manager role: Good manager for "
                "hard task splits.; worker role: Best xAI worker for code "
                "and reasoning..",
                "https://docs.x.ai/docs/models"),
            "source_links": (
                [
                    "https://docs.x.ai/docs/models",
                    "https://docs.x.ai/docs/models/grok-4.3",
                    "https://docs.x.ai/docs/models/grok-4.5",
                    "https://docs.x.ai/docs/models/grok-4.6",
                    "https://docs.x.ai/docs/models/grok-4.7",
                    "https://docs.x.ai/docs/models/grok-build-0.1",
                    "https://docs.x.ai/docs/models/grok-imagine-image-2.0",
                    "https://docs.x.ai/docs/pricing",
                    "https://x.ai/news/grok-4",
                ],
                "https://docs.x.ai/docs/models/grok-4.7"),
            "strengths": (
                "reads as strong on Most capable xAI model per official "
                "docs; dedicated code/chat pick, Native tool use, structured "
                "outputs, encrypted reasoning content, Long-context pricing "
                "only above 200k prompt tokens.",
                "https://docs.x.ai/docs/models"),
            "tool_calling": (
                True,
                "https://docs.x.ai/docs/models/grok-4.7"),
            "weaknesses": (
                "watch out for Long-context premium doubles price at/above "
                "200k prompt tokens, No logprobs/top_logprobs on 4.20+ "
                "generation models.",
                "https://docs.x.ai/docs/models"),
        }),
        ("grok-4.6", {
            "avoid_for": (
                "less suited to Cheapest high-volume routing; image "
                "synthesis (use Imagine). Task fit: agent-loop: best; "
                "bulk-summary: good; code-gen: best; code-review: best; "
                "long-doc: best; math-reasoning: best; planning: best; "
                "routing: good; short-chat: good; vision: good.",
                "https://docs.x.ai/docs/models"),
            "best_for": (
                "suited to Balanced frontier chat, code, reasoning at same "
                "price as 4.7 with wider provider availability. Task fit: "
                "agent-loop: best; bulk-summary: good; code-gen: best; "
                "code-review: best; long-doc: best; math-reasoning: best; "
                "planning: best; routing: good; short-chat: good; vision: "
                "good.",
                "https://docs.x.ai/docs/models"),
            "context_window": (
                500000,
                "https://docs.x.ai/docs/models/grok-4.6"),
            "cost_tier": (
                "strong-reasoning",
                "https://docs.x.ai/docs/models"),
            "currency": (
                "USD",
                "https://docs.x.ai/docs/pricing"),
            "input_token_price": (
                2.0,
                "https://docs.x.ai/docs/pricing"),
            "modalities": (
                [
                    "text",
                    "image",
                ],
                "https://docs.x.ai/docs/models/grok-4.6"),
            "output_token_price": (
                6.0,
                "https://docs.x.ai/docs/pricing"),
            "reasoning": (
                True,
                "https://docs.x.ai/docs/models/grok-4.6"),
            "role_notes": (
                "auditor role: Good auditor fallback to 4.7.; director role: "
                "Good director; prefer 4.7 for newest knowledge.; manager "
                "role: Good manager.; worker role: Good worker for code-gen "
                "and review..",
                "https://docs.x.ai/docs/models"),
            "source_links": (
                [
                    "https://docs.x.ai/docs/models",
                    "https://docs.x.ai/docs/models/grok-4.3",
                    "https://docs.x.ai/docs/models/grok-4.5",
                    "https://docs.x.ai/docs/models/grok-4.6",
                    "https://docs.x.ai/docs/models/grok-4.7",
                    "https://docs.x.ai/docs/models/grok-build-0.1",
                    "https://docs.x.ai/docs/models/grok-imagine-image-2.0",
                    "https://docs.x.ai/docs/pricing",
                    "https://x.ai/news/grok-4",
                ],
                "https://docs.x.ai/docs/models/grok-4.7"),
            "strengths": (
                "reads as strong on Same 500k context and $2/$6 pricing as "
                "4.7 below 200k, Function calling, structured outputs, image "
                "input, US regional endpoint availability (with 1.1x "
                "premium).",
                "https://docs.x.ai/docs/models"),
            "tool_calling": (
                True,
                "https://docs.x.ai/docs/models/grok-4.6"),
            "weaknesses": (
                "watch out for Same long-context doubling at/above 200k as "
                "4.7, Superseded by 4.7 as recommended pick.",
                "https://docs.x.ai/docs/models"),
        }),
        ("grok-4.5", {
            "avoid_for": (
                "less suited to Maximum 1M-context single requests; absolute "
                "frontier depth. Task fit: agent-loop: good; bulk-summary: "
                "good; code-gen: best; code-review: best; long-doc: good; "
                "math-reasoning: good; planning: good; routing: good; "
                "short-chat: good; vision: good.",
                "https://docs.x.ai/docs/models"),
            "best_for": (
                "suited to Slightly cheaper frontier runs with lower "
                "cached-input rate ($0.30 vs $0.50). Task fit: agent-loop: "
                "good; bulk-summary: good; code-gen: best; code-review: "
                "best; long-doc: good; math-reasoning: good; planning: good; "
                "routing: good; short-chat: good; vision: good.",
                "https://docs.x.ai/docs/models"),
            "context_window": (
                500000,
                "https://docs.x.ai/docs/models/grok-4.5"),
            "cost_tier": (
                "balanced",
                "https://docs.x.ai/docs/models"),
            "currency": (
                "USD",
                "https://docs.x.ai/docs/pricing"),
            "input_token_price": (
                2.0,
                "https://docs.x.ai/docs/pricing"),
            "modalities": (
                [
                    "text",
                    "image",
                ],
                "https://docs.x.ai/docs/models/grok-4.5"),
            "output_token_price": (
                6.0,
                "https://docs.x.ai/docs/pricing"),
            "reasoning": (
                True,
                "https://docs.x.ai/docs/models/grok-4.5"),
            "role_notes": (
                "auditor role: Good auditor.; director role: Good director "
                "for mid-complexity plans.; manager role: Good manager.; "
                "worker role: Good worker..",
                "https://docs.x.ai/docs/models"),
            "source_links": (
                [
                    "https://docs.x.ai/docs/models",
                    "https://docs.x.ai/docs/models/grok-4.3",
                    "https://docs.x.ai/docs/models/grok-4.5",
                    "https://docs.x.ai/docs/models/grok-4.6",
                    "https://docs.x.ai/docs/models/grok-4.7",
                    "https://docs.x.ai/docs/models/grok-build-0.1",
                    "https://docs.x.ai/docs/models/grok-imagine-image-2.0",
                    "https://docs.x.ai/docs/pricing",
                    "https://x.ai/news/grok-4",
                ],
                "https://docs.x.ai/docs/models/grok-4.7"),
            "strengths": (
                "reads as strong on Same $2/$6 base as newer 4.x with "
                "cheaper cache ($0.30/1M), 500k context with tools and "
                "structured outputs.",
                "https://docs.x.ai/docs/models"),
            "tool_calling": (
                True,
                "https://docs.x.ai/docs/models/grok-4.5"),
            "weaknesses": (
                "watch out for Superseded by 4.6/4.7 per official chooser, "
                "Same 200k-threshold doubling.",
                "https://docs.x.ai/docs/models"),
        }),
        ("grok-4.3", {
            "avoid_for": (
                "less suited to Absolute peak reasoning depth (use 4.7); "
                "speech/image generation. Task fit: agent-loop: good; "
                "bulk-summary: best; code-gen: good; code-review: good; "
                "long-doc: best; math-reasoning: good; planning: ok; "
                "routing: best; short-chat: best; vision: good.",
                "https://docs.x.ai/docs/models"),
            "best_for": (
                "suited to Cheap-fast long-context (1M) bulk-summary, "
                "long-doc, high-volume code with batch discount. Task fit: "
                "agent-loop: good; bulk-summary: best; code-gen: good; "
                "code-review: good; long-doc: best; math-reasoning: good; "
                "planning: ok; routing: best; short-chat: best; vision: good.",
                "https://docs.x.ai/docs/models"),
            "context_window": (
                1000000,
                "https://docs.x.ai/docs/models/grok-4.3"),
            "cost_tier": (
                "cheap-fast",
                "https://docs.x.ai/docs/models"),
            "currency": (
                "USD",
                "https://docs.x.ai/docs/pricing"),
            "input_token_price": (
                1.25,
                "https://docs.x.ai/docs/pricing"),
            "modalities": (
                [
                    "text",
                    "image",
                ],
                "https://docs.x.ai/docs/models/grok-4.3"),
            "output_token_price": (
                2.5,
                "https://docs.x.ai/docs/pricing"),
            "reasoning": (
                True,
                "https://docs.x.ai/docs/models/grok-4.3"),
            "role_notes": (
                "auditor role: Cheap auditor for large diff sets.; director "
                "role: Avoid as director for hardest plans.; manager role: "
                "Good cheap manager for fan-out.; worker role: Best "
                "cheap-fast xAI worker for bulk jobs..",
                "https://docs.x.ai/docs/models"),
            "source_links": (
                [
                    "https://docs.x.ai/docs/models",
                    "https://docs.x.ai/docs/models/grok-4.3",
                    "https://docs.x.ai/docs/models/grok-4.5",
                    "https://docs.x.ai/docs/models/grok-4.6",
                    "https://docs.x.ai/docs/models/grok-4.7",
                    "https://docs.x.ai/docs/models/grok-build-0.1",
                    "https://docs.x.ai/docs/models/grok-imagine-image-2.0",
                    "https://docs.x.ai/docs/pricing",
                    "https://x.ai/news/grok-4",
                ],
                "https://docs.x.ai/docs/models/grok-4.7"),
            "strengths": (
                "reads as strong on 1M context at $1.25/$2.50 - cheapest "
                "Grok 4 reasoning tier, 20% batch API discount; low $0.20 "
                "cached input, Good for scaling experiments.",
                "https://docs.x.ai/docs/models"),
            "tool_calling": (
                True,
                "https://docs.x.ai/docs/models/grok-4.3"),
            "weaknesses": (
                "watch out for Below 4.5/4.6/4.7 on frontier benchmarks per "
                "official chooser, Long-context doubling still applies "
                "at/above 200k.",
                "https://docs.x.ai/docs/models"),
        }),
        ("grok-build-0.1", {
            "avoid_for": (
                "less suited to General chat without agentic scaffolding; "
                "image/video generation. Task fit: agent-loop: best; "
                "bulk-summary: good; code-gen: best; code-review: best; "
                "long-doc: good; math-reasoning: good; planning: ok; "
                "routing: good; short-chat: good; vision: ok.",
                "https://docs.x.ai/docs/models"),
            "best_for": (
                "suited to Agentic coding workflows (Grok Build), code-gen, "
                "code-review, agent-loop with tools. Task fit: agent-loop: "
                "best; bulk-summary: good; code-gen: best; code-review: "
                "best; long-doc: good; math-reasoning: good; planning: ok; "
                "routing: good; short-chat: good; vision: ok.",
                "https://docs.x.ai/docs/models"),
            "context_window": (
                256000,
                "https://docs.x.ai/docs/models/grok-build-0.1"),
            "cost_tier": (
                "cheap-fast",
                "https://docs.x.ai/docs/models"),
            "currency": (
                "USD",
                "https://docs.x.ai/docs/pricing"),
            "input_token_price": (
                1.0,
                "https://docs.x.ai/docs/pricing"),
            "modalities": (
                [
                    "text",
                    "image",
                ],
                "https://docs.x.ai/docs/models/grok-build-0.1"),
            "output_token_price": (
                2.0,
                "https://docs.x.ai/docs/pricing"),
            "reasoning": (
                True,
                "https://docs.x.ai/docs/models/grok-build-0.1"),
            "role_notes": (
                "auditor role: Good code auditor inside Build/CLI loop.; "
                "director role: Avoid as general director.; manager role: "
                "Good for code-task dispatch.; worker role: Best xAI coding "
                "worker on budget..",
                "https://docs.x.ai/docs/models"),
            "source_links": (
                [
                    "https://docs.x.ai/docs/models",
                    "https://docs.x.ai/docs/models/grok-4.3",
                    "https://docs.x.ai/docs/models/grok-4.5",
                    "https://docs.x.ai/docs/models/grok-4.6",
                    "https://docs.x.ai/docs/models/grok-4.7",
                    "https://docs.x.ai/docs/models/grok-build-0.1",
                    "https://docs.x.ai/docs/models/grok-imagine-image-2.0",
                    "https://docs.x.ai/docs/pricing",
                    "https://x.ai/news/grok-4",
                ],
                "https://docs.x.ai/docs/models/grok-4.7"),
            "strengths": (
                "reads as strong on Cheapest text model in lineup ($1/$2), "
                "Purpose-built for agentic coding on API and CLI, 256k "
                "context covers large repos.",
                "https://docs.x.ai/docs/models"),
            "tool_calling": (
                True,
                "https://docs.x.ai/docs/models/grok-build-0.1"),
            "weaknesses": (
                "watch out for Narrower general-knowledge positioning than "
                "Grok 4.7, Doubles at/above 200k like other xAI models.",
                "https://docs.x.ai/docs/models"),
        }),
        ("grok-imagine-image-2.0", {
            "avoid_for": (
                "less suited to Text chat, code, reasoning (not a text "
                "model); strict per-token budgeting. Task fit: agent-loop: "
                "avoid; bulk-summary: avoid; code-gen: avoid; code-review: "
                "avoid; long-doc: avoid; math-reasoning: avoid; planning: "
                "avoid; routing: avoid; short-chat: avoid; vision: best.",
                "https://docs.x.ai/docs/models"),
            "best_for": (
                "suited to Image generation and editing from text; "
                "vision-adjacent creative tasks. Task fit: agent-loop: "
                "avoid; bulk-summary: avoid; code-gen: avoid; code-review: "
                "avoid; long-doc: avoid; math-reasoning: avoid; planning: "
                "avoid; routing: avoid; short-chat: avoid; vision: best.",
                "https://docs.x.ai/docs/models"),
            "cost_tier": (
                "specialised",
                "https://docs.x.ai/docs/models"),
            "currency": (
                "USD",
                "https://docs.x.ai/docs/pricing"),
            "modalities": (
                [
                    "text",
                    "image",
                ],
                "https://docs.x.ai/docs/models/grok-imagine-image-2.0"),
            "role_notes": (
                "auditor role: Avoid for audit.; director role: Avoid as "
                "director.; manager role: Avoid for management.; worker "
                "role: Specialised image worker only..",
                "https://docs.x.ai/docs/models"),
            "source_links": (
                [
                    "https://docs.x.ai/docs/models",
                    "https://docs.x.ai/docs/models/grok-4.3",
                    "https://docs.x.ai/docs/models/grok-4.5",
                    "https://docs.x.ai/docs/models/grok-4.6",
                    "https://docs.x.ai/docs/models/grok-4.7",
                    "https://docs.x.ai/docs/models/grok-build-0.1",
                    "https://docs.x.ai/docs/models/grok-imagine-image-2.0",
                    "https://docs.x.ai/docs/pricing",
                    "https://x.ai/news/grok-4",
                ],
                "https://docs.x.ai/docs/models/grok-4.7"),
            "strengths": (
                "reads as strong on Dedicated image model at $0.04/image, "
                "Listed in official Imagine pricing, Part of Imagine "
                "image/video/voice stack.",
                "https://docs.x.ai/docs/models"),
            "weaknesses": (
                "watch out for No text reasoning/tool-calling role, "
                "Per-image billing separate from token budgets.",
                "https://docs.x.ai/docs/models"),
        }),
        ("grok-4", {
            "avoid_for": (
                "less suited to New builds (prefer 4.7); 500k+ context "
                "needs. Task fit: agent-loop: good; bulk-summary: good; "
                "code-gen: good; code-review: good; long-doc: good; "
                "math-reasoning: good; planning: good; routing: good; "
                "short-chat: good; vision: good.",
                "https://docs.x.ai/docs/models"),
            "best_for": (
                "suited to Baseline frontier reference; multimodal "
                "text+vision with native tool use and live search. Task fit: "
                "agent-loop: good; bulk-summary: good; code-gen: good; "
                "code-review: good; long-doc: good; math-reasoning: good; "
                "planning: good; routing: good; short-chat: good; vision: "
                "good.",
                "https://docs.x.ai/docs/models"),
            "context_window": (
                256000,
                "https://x.ai/news/grok-4"),
            "cost_tier": (
                "balanced",
                "https://docs.x.ai/docs/models"),
            "modalities": (
                [
                    "text",
                    "image",
                ],
                "https://x.ai/news/grok-4"),
            "reasoning": (
                True,
                "https://x.ai/news/grok-4"),
            "role_notes": (
                "auditor role: Usable auditor; prefer 4.7.; director role: "
                "Usable director; prefer 4.7.; manager role: Usable "
                "manager.; worker role: Usable worker..",
                "https://docs.x.ai/docs/models"),
            "source_links": (
                [
                    "https://docs.x.ai/docs/models",
                    "https://docs.x.ai/docs/models/grok-4.3",
                    "https://docs.x.ai/docs/models/grok-4.5",
                    "https://docs.x.ai/docs/models/grok-4.6",
                    "https://docs.x.ai/docs/models/grok-4.7",
                    "https://docs.x.ai/docs/models/grok-build-0.1",
                    "https://docs.x.ai/docs/models/grok-imagine-image-2.0",
                    "https://docs.x.ai/docs/pricing",
                    "https://x.ai/news/grok-4",
                ],
                "https://docs.x.ai/docs/models/grok-4.7"),
            "strengths": (
                "reads as strong on Native tool use and realtime search "
                "integration, Multimodal text+vision API with voice mode "
                "lineage, Heavy variant lineage for parallel test-time "
                "compute.",
                "https://docs.x.ai/docs/models"),
            "tool_calling": (
                True,
                "https://x.ai/news/grok-4"),
            "weaknesses": (
                "watch out for Superseded by 4.3/4.5/4.6/4.7 with larger "
                "contexts, Per-model API pricing now listed under newer "
                "point releases.",
                "https://docs.x.ai/docs/models"),
        }),
    ],
}


def staged_section_rows():
    """Deep copy of the staged (provider, model, fields) table."""
    return copy.deepcopy(_STAGED_SECTION_ROWS)


def build_staged_base():
    """UNKNOWN-seed base catalog holding every staged model id."""
    rows = []
    for provider in sorted(_STAGED_SECTION_ROWS):
        for model_id, _fields in _STAGED_SECTION_ROWS[provider]:
            rows.append(kb.make_model_row(provider, model_id))
    return kb.make_catalog(
        rows, kb_version=1,
        updated_at=STAGED_SECTIONS_RETRIEVED_AT,
        sources=STAGED_MANIFEST_SOURCES)


def import_staged_sections(base=None, user_confirmed=False):
    """Import staged sections as sourced rows via the updater apply path.

    One proposal per provider, built with the same schema rules
    as updater.propose_update (known rows, known fields, no-op
    skips) and applied ONLY through updater.apply_proposal on
    explicit user_confirmed=True. Per-field change sources carry
    the true section-cited URL plus retrieval date; the proposal
    envelope is the provider docs base when allowlisted, else
    STAGED_SECTION_ENVELOPE. Returns the final catalog dict.
    """
    catalog = base if base is not None else build_staged_base()
    for provider in sorted(_STAGED_SECTION_ROWS):
        entries = _STAGED_SECTION_ROWS[provider]
        draft = {"source_url": STAGED_PROVIDER_ENVELOPES[provider],
                 "retrieved_at": STAGED_SECTIONS_RETRIEVED_AT,
                 "changes": []}
        for model_id, fields in entries:
            for name in sorted(fields):
                value, source = fields[name]
                draft["changes"].append({
                    "provider_id": provider,
                    "model_id": model_id,
                    "field": name,
                    "new": value,
                    "source": source,
                    "retrieved_at": STAGED_SECTIONS_RETRIEVED_AT})
        proposal = _proposal_from_change_drafts(catalog, draft)
        errors = updater.validate_proposal(catalog, proposal)
        if errors:
            raise updater.KBUpdateError(
                "staged import proposal for " + repr(provider) +
                " rejected: " + "; ".join(errors))
        result = updater.apply_proposal(
            catalog, proposal, user_confirmed=user_confirmed)
        catalog = result["catalog"]
    return catalog

# --- frozen D8 facades (server-side catalog binding) --------------------------
#
# Exact frozen signatures from routing/interface.py; verified with
# inspect against the frozen interface. They read the bound catalog
# (kb.bind_catalog / kb.bound_catalog, SEED_CATALOG until bound) and
# delegate every KB rule to the choice-point functions above, so the
# 35 owned tests keep passing unchanged. updater.propose_update keeps
# its legacy 4-arg shape; the frozen 2-arg propose_update lives here
# because updater already owns that name.


def read_kb(provider_ids: List[str]) -> List[ModelContracts]:
    """Frozen 3.4: AUTO reads only connected providers.

    Delegates to candidates_for_auto over the bound catalog, then
    projects each candidate to the ModelContracts envelope
    (provider_id, model_id, fields). Model ids pass through verbatim.
    """
    catalog = kb.bound_catalog()
    auto = candidates_for_auto(catalog, provider_ids)
    contracts = []
    for candidate in auto["candidates"]:
        row = candidate.get("row") or {}
        contracts.append({"provider_id": candidate.get("provider_id"),
                          "model_id": candidate.get("model_id"),
                          "fields": row.get("fields", {})})
    return contracts


def resolve_exact_id(model: str) -> Tuple[ModelContracts, str]:
    """Frozen 3.4: contract plus dated snapshot ref for one exact id.

    model is the exact model id; the provider is resolved by searching
    bound-catalog rows for that model id, verbatim and case-sensitive.
    The first catalog-order row wins when several providers ship the
    same model id. Delegates the row read to bridge. Returns
    (contract, snapshot_ref) where snapshot_ref is
    "provider_id/model_id@stamp" and stamp is the row's
    price_effective_at value, else the catalog version updated_at, else
    UNKNOWN. Raises LookupError for an id outside the bound catalog.
    """
    catalog = kb.bound_catalog()
    provider_id = None
    bridged = None
    for row in catalog.get("models", []):
        if isinstance(row, dict) and row.get("model_id") == model:
            provider_id = row.get("provider_id")
            bridged = bridge(catalog, provider_id, model)
            break
    if bridged is None or bridged.get("row") is None:
        raise LookupError("unknown model id %r" % (model,))
    fields = bridged["row"].get("fields", {})
    stamp = fields.get("price_effective_at", {}).get("value", "")
    if not isinstance(stamp, str) or not stamp:
        stamp = catalog.get("version", {}).get("updated_at", "")
    if not isinstance(stamp, str) or not stamp:
        stamp = kb.UNKNOWN
    contract = {"provider_id": provider_id, "model_id": model,
                "fields": fields}
    return contract, "%s/%s@%s" % (provider_id, model, stamp)


def _proposal_from_change_drafts(catalog, draft):
    """Build a proposal from explicit draft change entries (data only)."""
    source_url = draft.get("source_url")
    retrieved_at = draft.get("retrieved_at")
    known = {(row.get("provider_id"), row.get("model_id")): row
             for row in catalog.get("models", [])
             if isinstance(row, dict)}
    changes = []
    rejected = []
    for entry in draft.get("changes", []) or []:
        if not isinstance(entry, dict):
            rejected.append({"entry": entry,
                             "reason": "entry is not a dict"})
            continue
        provider_id = entry.get("provider_id")
        model_id = entry.get("model_id")
        field = entry.get("field")
        pair = (provider_id, model_id)
        if pair not in known:
            rejected.append({"entry": entry,
                             "reason": "row %s/%s is not in the base" % pair})
            continue
        if field not in kb.ROW_FIELD_NAMES:
            rejected.append({"entry": entry,
                             "reason": "unknown field %r" % (field,)})
            continue
        old = known[pair]["fields"][field]["value"]
        new = entry.get("new")
        if old == new:
            continue
        changes.append({"provider_id": provider_id,
                        "model_id": model_id,
                        "field": field,
                        "old": old,
                        "new": new,
                        "source": entry.get("source") or source_url,
                        "retrieved_at": (entry.get("retrieved_at")
                                         or retrieved_at)})
    reasons = []
    if not changes:
        reasons.append("no schema-valid field changes in draft data")
    for item in rejected:
        reasons.append(str(item))
    return {"source_url": source_url, "retrieved_at": retrieved_at,
            "changes": changes, "rejected": rejected, "reasons": reasons}


def propose_update(draft: dict, updated_by_model: str) -> dict:
    """Frozen 3.4: schema-validated proposal from draft data, never applied.

    draft carries source_url plus retrieved_at plus either "models" (a
    fetched-document style entry list, parsed exactly like fetched page
    text through updater.propose_update) or "changes" (explicit change
    entries with provider_id, model_id, field and new). The bound
    catalog is read, never written. Returns the proposal stamped with
    updated_by_model plus validation_errors ([] means appliable).
    """
    catalog = kb.bound_catalog()
    if "changes" in draft:
        proposal = _proposal_from_change_drafts(catalog, draft)
    else:
        document = {"models": draft.get("models", [])}
        proposal = updater.propose_update(
            catalog, draft.get("source_url"), json.dumps(document),
            draft.get("retrieved_at"))
    proposal = dict(proposal)
    proposal["updated_by_model"] = updated_by_model
    proposal["validation_errors"] = updater.validate_proposal(
        catalog, proposal)
    return proposal


# --- K04NEXT4 AUTO fit-price-quality (M-P3-124, additive) --------------------
def _auto_price_for_rank(row, usage):
    """Numeric price for one usage block, or None when UNKNOWN."""
    block = dict(usage or {"input_tokens": 1000, "output_tokens": 500})
    pairs = (("input_tokens", "input_token_price"),
             ("output_tokens", "output_token_price"),
             ("cached_tokens", "cached_token_price"),
             ("reasoning_tokens", "reasoning_token_price"),
             ("requests", "request_price"))
    total = 0.0
    seen = False
    fields = row.get("fields", {}) if isinstance(row, dict) else {}
    for tok, pname in pairs:
        try:
            price = fields.get(pname, {}).get("value", None)
        except AttributeError:
            continue
        if isinstance(price, bool) or not isinstance(price, (int, float)):
            continue
        amount = block.get(tok, 0)
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            continue
        seen = True
        total += float(price) * float(amount)
    if not seen:
        return None
    return total


def auto_fit_price_quality(catalog, connected_provider_ids, *,
                           task_type="coding", usage=None):
    """AUTO fit-price-quality rank over the shipped KB (M-P3-124).

    Reads only connected providers (candidates_for_auto); modalities
    that cannot prove text-only are rejected, never offered; KB price
    UNKNOWN stays UNAVAILABLE, never zero, never picked. Ranks by
    KB-only strength (tool_calling, reasoning, coding best_for/purpose
    hits, cheaper cost_tier) then by numeric block price; full ties keep
    catalog order, model_id never decides. Returns the shipped format id,
    the pick, a reason naming task type plus fit plus price plus quality,
    and the rejected plus excluded rows.
    """
    connected = list(connected_provider_ids or [])
    auto = candidates_for_auto(catalog, connected)
    block = dict(usage or {"input_tokens": 1000, "output_tokens": 500})
    ranked = []
    excluded = []
    rejected = []
    for cand in auto["candidates"]:
        provider_id = cand.get("provider_id")
        model_id = cand.get("model_id")
        row = cand.get("row")
        base = {"provider_id": provider_id, "model_id": model_id,
                "kb_status": cand.get("kb_status"), "connected": True}
        if row is None:
            excluded.append(dict(
                base, amount=None, pricing_snapshot_id=None,
                reason="not in KB base (%s); never picked"
                % (cand.get("kb_status"),)))
            continue
        if not _modalities_eligible(row):
            rejected.append(dict(
                base,
                reason="modalities cannot prove text-only; never offered"))
            continue
        price = _auto_price_for_rank(row, block)
        if price is None:
            excluded.append(dict(
                base, amount=None, pricing_snapshot_id=None,
                reason="KB price UNKNOWN for this block (UNAVAILABLE, "
                       "never zero); never picked"))
            continue
        tool, reason_flag, hits, neg_cost = _strength_key(row)
        ranked.append(dict(
            base, amount=price, pricing_snapshot_id=None,
            tool_calling=tool, reasoning=reason_flag,
            coding_hits=hits, cost_rank=-neg_cost,
            order=len(ranked)))
    for row in catalog.get("models", []):
        if not isinstance(row, dict):
            continue
        if row.get("provider_id") in set(connected):
            continue
        rejected.append({
            "provider_id": row.get("provider_id"),
            "model_id": row.get("model_id"),
            "kb_status": IN_BASE,
            "connected": False,
            "reason": "provider not connected; excluded, never read "
                      "for choice"})
    ranked.sort(key=lambda r: (-r["tool_calling"], -r["reasoning"],
                               -r["coding_hits"], r["cost_rank"],
                               r["amount"], r["order"]))
    for r in ranked:
        del r["order"]
    if ranked:
        pick = dict(ranked[0])
        reason = (
            "AUTO %s: fit-price-quality pick %s/%s (fit %d coding hits, "
            "tool %s, reasoning %s; price %s USD for one block; quality "
            "tool %s reasoning %s; %d priced of %d candidates; "
            "rejected %d, unconnected %d)"
            % (task_type, pick["provider_id"], pick["model_id"],
               pick["coding_hits"],
               "yes" if pick["tool_calling"] else "no",
               "yes" if pick["reasoning"] else "no",
               pick["amount"],
               "yes" if pick["tool_calling"] else "no",
               "yes" if pick["reasoning"] else "no",
               len(ranked),
               len(auto["candidates"]),
               len(rejected),
               len(auto.get("excluded_unconnected", []))))
    else:
        pick = None
        reason = (
            "AUTO %s: BLOCKED no priced fit-price-quality candidate for "
            "this block (unknown cost is never a pick, never zero; %d "
            "rejected, %d excluded)"
            % (task_type, len(rejected), len(excluded)))
    return {"format": kb.KB_FORMAT_ID, "task_type": task_type,
            "candidates": auto["candidates"],
            "ranked": ranked, "excluded": excluded,
            "rejected": rejected + list(excluded),
            "excluded_unconnected": sorted(auto.get(
                "excluded_unconnected", [])),
            "pick": pick, "reason": reason}
