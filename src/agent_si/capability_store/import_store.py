"""K05 capability_store import path (M4 STEP2 implementation).

Capability rows enter only via this import path; original external data is
never modified (read-only copies); stale copies stay versioned backups and
are never served as current. Own prefixes only; standard library plus the
own-package store module.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from agent_si.capability_store import store
from agent_si.capability_store.store import (
    CapabilityEvidenceRecord,
    CapabilityStoreError,
    EvidenceTier,
    FreshnessState,
)


def import_measured_capability(
    source_ref: str, dest_ref: str
) -> Optional[CapabilityEvidenceRecord]:
    """MEASURED import: benchmark rows enter only via this path.

    source_ref is a path to a JSON measurement document; dest_ref is the
    destination task class. Every numeric/provenance field comes from the
    document; nothing is seeded here. Malformed input raises ValueError.
    """
    if "original:" in dest_ref:
        raise CapabilityStoreError(
            code="CAPABILITY_ORIGINAL_WRITE_REFUSED",
            reason="destination addresses read-only original data",
        )
    try:
        raw_text = Path(source_ref).read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(
            "cannot read measurement document %r: %s" % (source_ref, exc)
        ) from exc
    try:
        doc = json.loads(raw_text)
    except ValueError as exc:
        raise ValueError(
            "invalid measurement JSON in %r: %s" % (source_ref, exc)
        ) from exc
    if not isinstance(doc, dict):
        raise ValueError(
            "measurement document %r must hold a JSON object" % (source_ref,)
        )
    for key in (
        "model_id",
        "score",
        "sample_count",
        "confidence",
        "measured_at",
        "runtime",
        "source",
    ):
        if key not in doc:
            raise ValueError(
                "measurement document %r misses required key %r"
                % (source_ref, key)
            )
    score = doc["score"]
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise ValueError(
            "measurement document %r holds a non-numeric score" % (source_ref,)
        )
    sample_count = doc["sample_count"]
    if isinstance(sample_count, bool) or not isinstance(sample_count, int):
        raise ValueError(
            "measurement document %r holds a non-integer sample_count"
            % (source_ref,)
        )
    confidence = doc["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ValueError(
            "measurement document %r holds a non-numeric confidence"
            % (source_ref,)
        )
    for key in ("model_id", "measured_at", "runtime", "source"):
        value = doc[key]
        if not isinstance(value, str) or not value:
            raise ValueError(
                "measurement document %r holds an empty %r" % (source_ref, key)
            )
    if doc.get("task_class", dest_ref) != dest_ref:
        raise ValueError(
            "measurement document %r addresses a different task_class"
            % (source_ref,)
        )
    evidence_ref = doc.get("evidence_ref")
    if evidence_ref is None:
        evidence_ref = "cap:measured:%s:%s:v1" % (doc["model_id"], dest_ref)
    return store._register_row(
        CapabilityEvidenceRecord(
            model_id=doc["model_id"],
            task_class=dest_ref,
            tier=EvidenceTier.MEASURED,
            score=score,
            score_type=doc.get("score_type"),
            sample_count=sample_count,
            confidence=confidence,
            benchmark_version=doc.get("benchmark_version"),
            measured_at=doc["measured_at"],
            runtime=doc["runtime"],
            runtime_version=doc.get("runtime_version"),
            environment_fingerprint=doc.get("environment_fingerprint"),
            freshness_state=FreshnessState.CURRENT.value,
            evidence_ref=evidence_ref,
            source=doc["source"],
        )
    )


def adapt_proxy_notes(
    source_ref: str, dest_ref: str
) -> Optional[CapabilityEvidenceRecord]:
    """Labelled PROXY adapter for prose notes; never numeric scores."""
    return store._register_by_ref(
        CapabilityEvidenceRecord(
            model_id=source_ref,
            task_class=dest_ref,
            tier=EvidenceTier.PROXY,
            score=None,
            score_type=None,
            sample_count=None,
            confidence=None,
            benchmark_version=None,
            measured_at=None,
            runtime=None,
            runtime_version=None,
            environment_fingerprint=None,
            freshness_state=FreshnessState.UNKNOWN.value,
            evidence_ref=f"cap:proxy:{source_ref}:{dest_ref}:v1",
            source=source_ref,
        )
    )
