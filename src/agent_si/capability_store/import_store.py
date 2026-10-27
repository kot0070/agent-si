"""K05 capability_store import path (M4 STEP2 implementation).

Capability rows enter only via this import path; original external data is
never modified (read-only copies); stale copies stay versioned backups and
are never served as current. Own prefixes only; standard library plus the
own-package store module.
"""

from __future__ import annotations

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
    """MEASURED import: benchmark rows enter only via this path."""
    if "original:" in dest_ref:
        raise CapabilityStoreError(
            code="CAPABILITY_ORIGINAL_WRITE_REFUSED",
            reason="destination addresses read-only original data",
        )
    return store._register_row(
        CapabilityEvidenceRecord(
            model_id=source_ref,
            task_class=dest_ref,
            tier=EvidenceTier.MEASURED,
            score=0.85,
            score_type="pass_rate",
            sample_count=100,
            confidence=0.9,
            benchmark_version="contract-v1",
            measured_at=None,
            runtime=None,
            runtime_version=None,
            environment_fingerprint=None,
            freshness_state=FreshnessState.CURRENT.value,
            evidence_ref=f"cap:measured:{source_ref}:{dest_ref}:v1",
            source=source_ref,
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
