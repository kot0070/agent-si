# K04 Lane A2 — minimal KB-read port for the model router.
# Lane B implements the real knowledge base later; the router only ever
# consumes this port, so it must never import Lane B code.
"""KB-read interface: fit / quality / price / modality / fields-or-UNKNOWN.

Every field a model lacks is None (UNKNOWN), never guessed. The router
treats unknown prices as expensive and unknown capability as ineligible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Protocol, Tuple


@dataclass(frozen=True)
class KbModelFacts:
    """One model's KB facts, or nothing (None) when the KB has no row."""
    provider: str
    model: str  # exact model id, verbatim
    task_fit: Mapping[str, float]  # task_class -> fit score in [0, 1]
    strict_pass_rate: Optional[float]
    tolerant_pass_rate: Optional[float]
    sample_count: Optional[int]
    confidence: Optional[float]
    freshness: Optional[str]  # CURRENT | STALE | INCOMPATIBLE | UNKNOWN | None
    input_price: Optional[float]  # per 1k input tokens, currency units
    output_price: Optional[float]  # per 1k output tokens, currency units
    modalities: Tuple[str, ...]  # capability tokens, e.g. text/tools/coding
    assessed_risk: str  # RiskLevel token
    fields_state: str  # MEASURED | PROXY | UNVERIFIED | UNKNOWN
    verified_static: bool  # verified contract + probe (branch B evidence)
    source: str
    measured_at: Optional[str]
    latency_ms: Optional[float] = None

    def fit_for(self, task_class: str) -> Optional[float]:
        """Task fit for a class, or None when the KB holds no data."""
        if not self.task_fit:
            return None
        value = self.task_fit.get(task_class, self.task_fit.get("*"))
        return float(value) if value is not None else None

    def has_known_price(self) -> bool:
        return self.input_price is not None and self.output_price is not None


class KbReader(Protocol):
    """Minimal read surface the router needs. Fakes implement this in tests."""

    def facts(self, provider: str, model: str) -> Optional[KbModelFacts]:
        """KB row for an exact (provider, model) pair, or None (NO-DATA)."""
        ...  # pragma: no cover

    def models(self, provider: Optional[str] = None) -> List[KbModelFacts]:
        """All known rows, optionally restricted to one provider."""
        ...  # pragma: no cover


TEXT_CODE_MODALITIES = ("text", "tools", "coding")
NON_TEXT_CODE_MODALITIES = ("image", "audio", "embedding")


def is_text_code_candidate(facts: KbModelFacts) -> bool:
    """True for text/tools/coding models; never image/audio/embedding ones."""
    modalities = set(facts.modalities or ())
    if "text" not in modalities:
        return False
    return not (modalities & set(NON_TEXT_CODE_MODALITIES))


def facts_prove_non_text(facts: Optional[KbModelFacts]) -> bool:
    """True when facts prove a pure non-text model (no text token).

    No facts (None) or empty/unknown modalities prove nothing and read
    False, so unproven models keep their legacy path. Multimodal rows
    (text plus image/audio) stay eligible: only a proven image, audio
    or embedding set without text is never offered or chosen; a pinned
    one gets a plain refusal.
    """
    if facts is None:
        return False
    modalities = set(facts.modalities or ())
    if not modalities:
        return False
    if not (modalities & set(NON_TEXT_CODE_MODALITIES)):
        return False
    return "text" not in modalities
