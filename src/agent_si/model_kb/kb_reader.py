"""KB-to-router adapter over the real bound catalog (K04 lane B owned).

Implements the router's KbReader port (routing.kb_port) by reading the
live bound catalog (model_kb.kb.bound_catalog, SEED_CATALOG until a
choice-point test binds its own). No invented numbers: every field
without sourced evidence stays None/UNKNOWN, so unknown prices stay
expensive and unknown capabilities stay ineligible downstream.
"""

from __future__ import annotations

import re
from typing import Dict, List, Mapping, Optional, Tuple

from agent_si.model_kb import kb as _kb
from agent_si.routing.kb_port import KbModelFacts

_TOKEN_SPLIT = re.compile("[^a-z0-9]+")


def _field_value(row: Mapping, name: str):
    """Raw value of one sourced KB field; UNKNOWN/None read as missing."""
    try:
        value = row.get("fields", {}).get(name, {}).get("value", None)
    except AttributeError:
        return None
    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() in ("", "unknown"):
        return None
    return value


def _modalities(value) -> Tuple[str, ...]:
    """Token tuple for the modalities field; () when not proven."""
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        tokens = [str(item).strip().lower() for item in value]
    elif isinstance(value, str):
        tokens = [tok for tok in _TOKEN_SPLIT.split(value.lower()) if tok]
    else:
        return ()
    return tuple(tok for tok in tokens if tok)


def _price(value) -> Optional[float]:
    """Numeric price or None (unknown stays expensive downstream)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def row_to_facts(row: Mapping) -> KbModelFacts:
    """Convert one bound-catalog row to router facts (honest, no guesses)."""
    fields = row.get("fields", {}) if isinstance(row, Mapping) else {}
    try:
        source = fields.get("purpose", {}).get("source", None) or "agent-si-kb"
    except AttributeError:
        source = "agent-si-kb"
    try:
        measured_at = fields.get("purpose", {}).get("retrieved_at", None)
    except AttributeError:
        measured_at = None
    return KbModelFacts(
        provider=row.get("provider_id"),
        model=row.get("model_id"),
        task_fit={},
        strict_pass_rate=None,
        tolerant_pass_rate=None,
        sample_count=None,
        confidence=None,
        freshness="UNKNOWN",
        input_price=_price(_field_value(row, "input_token_price")),
        output_price=_price(_field_value(row, "output_token_price")),
        modalities=_modalities(_field_value(row, "modalities")),
        assessed_risk="UNKNOWN",
        fields_state="UNKNOWN",
        verified_static=False,
        source=str(source),
        measured_at=measured_at if isinstance(measured_at, str) else None,
        latency_ms=None,
    )


class CatalogKbReader:
    """KbReader over the live bound catalog (the real KB, never a copy)."""

    def facts(self, provider: str, model: str) -> Optional[KbModelFacts]:
        """KB facts for one exact pair, or None (NO-DATA)."""
        from agent_si.model_kb import loader as _loader

        row = _loader.find_row(_kb.bound_catalog(), provider, model)
        if row is None:
            return None
        return row_to_facts(row)

    def models(self, provider: Optional[str] = None) -> List[KbModelFacts]:
        """All bound-catalog rows, optionally restricted to one provider."""
        rows = _kb.bound_catalog().get("models", [])
        facts = [row_to_facts(row) for row in rows if isinstance(row, Mapping)]
        if provider is None:
            return facts
        return [fact for fact in facts if fact.provider == provider]


__all__ = ["CatalogKbReader", "row_to_facts"]
