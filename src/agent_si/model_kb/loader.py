"""Choice-point reads over the model KB.

Model ids pass through verbatim: no case folding, no trimming, no
shortening. Every choice point marks rows outside the shipped base with
the same not-in-base mark. AUTO shortlists only connected providers;
unconnected providers are listed as excluded, never read for choice.
"""

from __future__ import annotations

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


__all__ = ["IN_BASE", "NOT_IN_BASE", "find_row", "lookup", "bridge",
           "candidates_for_auto", "resolve_pool", "read_back",
           "offer_one_click", "read_kb", "resolve_exact_id",
           "propose_update"]


# --- frozen D8 facades (server-side catalog binding) --------------------------
#
# Exact frozen signatures from routing/interface.py; verified with
# inspect against the stub. They read the bound catalog
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
