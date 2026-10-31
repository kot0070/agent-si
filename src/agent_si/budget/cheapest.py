"""Cheapest-optimal model per usage block from the model KB (K04NEXT M1).

Reads the model KB read-only through agent_si.model_kb.loader choice-point
functions; never writes the KB. Every candidate row in the result carries
the same kb_status mark (in-base / not-in-base) the loader uses, at every
choice point of this path. Cost for one usage block goes only through
CostCalculator.calculate over a PricingSnapshot bridged from the KB row;
unknown prices stay UNAVAILABLE and are never picked, never zero.
"""
from __future__ import annotations

import hashlib
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal

from agent_si.budget import telemetry as _telemetry
from agent_si.model_kb import kb as _kb
from agent_si.model_kb import loader as _loader

TOKEN_NAMES = ("input_tokens", "output_tokens", "cached_tokens",
               "reasoning_tokens", "requests")

SNAPSHOT_SOURCE = "budget-cheapest"


def _utcnow_z():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _entry_ids(entry):
    """Verbatim (provider_id, model_id) for one candidate entry."""
    if not isinstance(entry, Mapping):
        raise ValueError(
            "select_cheapest_optimal entries must be mappings with "
            "provider_id/model_id (got %s)" % type(entry).__name__)
    provider_id = entry.get("provider_id")
    model_id = entry.get("model_id")
    if not isinstance(provider_id, str) or not provider_id:
        raise ValueError(
            "select_cheapest_optimal entry needs a provider_id")
    if not isinstance(model_id, str) or not model_id:
        raise ValueError(
            "select_cheapest_optimal entry needs a model_id")
    return provider_id, model_id


def _usage_tokens(usage):
    """Token counts for one block; garbage is refused, never summed."""
    if not isinstance(usage, Mapping):
        raise ValueError(
            "select_cheapest_optimal usage must be a mapping of "
            "token counts for one block")
    tokens = {name: usage[name] for name in TOKEN_NAMES if name in usage}
    if not tokens:
        raise ValueError(
            "select_cheapest_optimal usage needs at least one of %s"
            % (", ".join(TOKEN_NAMES),))
    for name, value in tokens.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(
                "select_cheapest_optimal usage %r must be a number" % (name,))
        if value < 0:
            raise ValueError(
                "select_cheapest_optimal usage %r must not be negative"
                % (name,))
    return tokens


def _snapshot_id(provider_id, model_id, snapshot, created_at):
    """Deterministic snapshot id for one provider/model/price/created triple."""
    raw = "|".join((
        str(provider_id), str(model_id),
        str(snapshot.get("input_token_price")),
        str(snapshot.get("output_token_price")),
        str(snapshot.get("cached_token_price")),
        str(snapshot.get("reasoning_token_price")),
        str(snapshot.get("request_price")), str(created_at)))
    return "bch-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def select_cheapest_optimal(catalog, entries, usage, *,
                            connected_provider_ids=None,
                            snapshot_source=SNAPSHOT_SOURCE,
                            created_at=None):
    """Pick the cheapest priced in-base model for one usage block.

    `catalog` is a model_kb catalog dict, read read-only and never
    mutated. `entries` are the caller-eligible candidates (verbatim
    provider_id/model_id mappings); `usage` maps token counts for one
    block. Providers outside `connected_provider_ids` (when given) are
    marked but excluded, never read for choice. Cost is computed only
    via CostCalculator.calculate; rows without KB prices stay
    UNAVAILABLE (never zero, never picked). Ties keep entry order;
    model_id never decides. Fail-closed: no priced in-base candidate
    returns pick None with a BLOCKED reason, never a silent pick.
    """
    stamped = created_at or _utcnow_z()
    tokens = _usage_tokens(usage)
    items = list(entries or [])
    connected = None if connected_provider_ids is None else set(
        connected_provider_ids)
    usage_ref = "bch-" + uuid.uuid4().hex[:12]
    _telemetry.register_usage(usage_ref, dict(tokens))
    ranked = []
    excluded = []
    for index, entry in enumerate(items):
        provider_id, model_id = _entry_ids(entry)
        bridged = _loader.bridge(catalog, provider_id, model_id)
        kb_status = bridged["kb_status"]
        is_connected = connected is None or provider_id in connected
        base = {"provider_id": provider_id, "model_id": model_id,
                "kb_status": kb_status, "connected": bool(is_connected)}
        if bridged["row"] is None:
            excluded.append(dict(
                base, amount=None, pricing_snapshot_id=None,
                reason="not in KB base (%s); never picked" % (kb_status,)))
            continue
        if not is_connected:
            excluded.append(dict(
                base, amount=None, pricing_snapshot_id=None,
                reason="provider not connected; excluded, never read "
                       "for choice"))
            continue
        snapshot = _kb.to_pricing_snapshot(
            bridged["row"], "bch-pending", snapshot_source, stamped)
        snapshot["pricing_snapshot_id"] = _snapshot_id(
            provider_id, model_id, snapshot, stamped)
        try:
            registered = _telemetry.make_snapshot(
                snapshot["pricing_snapshot_id"], provider_id, model_id,
                snapshot["currency"], snapshot["effective_at"],
                snapshot_source, stamped,
                input_token_price=snapshot["input_token_price"],
                output_token_price=snapshot["output_token_price"],
                cached_token_price=snapshot["cached_token_price"],
                reasoning_token_price=snapshot["reasoning_token_price"],
                request_price=snapshot["request_price"])
            line = _telemetry.CostCalculator.calculate(
                usage_ref, registered.pricing_snapshot_id)
        except ValueError:
            excluded.append(dict(
                base, amount=None, pricing_snapshot_id=None,
                reason="KB price UNKNOWN for this block (UNAVAILABLE, "
                       "never zero); never picked"))
            continue
        ranked.append(dict(
            base, amount=line.amount, currency=line.currency,
            pricing_snapshot_id=line.pricing_snapshot_id, order=index))
    ranked.sort(key=lambda row: (Decimal(str(row["amount"])), row["order"]))
    for row in ranked:
        del row["order"]
    if not ranked:
        return {"pick": None, "ranked": [], "excluded": excluded,
                "usage_ref": usage_ref,
                "reason": "BLOCKED: no priced in-base candidate for this "
                          "block (unknown cost is never a pick, never "
                          "zero; %d excluded)" % (len(excluded),)}
    pick = dict(ranked[0])
    return {"pick": pick, "ranked": ranked, "excluded": excluded,
            "usage_ref": usage_ref,
            "reason": "cheapest-optimal for one usage block: %s/%s at "
                      "%s %s (CostCalculator over KB snapshot %s; %d "
                      "priced of %d candidates)"
                      % (pick["provider_id"], pick["model_id"],
                         pick["amount"], pick["currency"],
                         pick["pricing_snapshot_id"], len(ranked),
                         len(items))}
