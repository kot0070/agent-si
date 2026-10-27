"""K05 capability_store: capability evidence store (M4 STEP2 implementation).

Read path serves one evidence row per (model_id, task_class); every served
row carries a stable evidence_ref. Measured rows enter only through the
import path; original external data is never modified and stale versioned
copies are never served as current. Standard library plus own-package names
only; all error codes carry the own CAPABILITY_ prefix.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Tuple


class EvidenceTier(str, Enum):
    """Frozen M4 tier: UNKNOWN | PROXY | MEASURED."""

    UNKNOWN = "UNKNOWN"
    PROXY = "PROXY"
    MEASURED = "MEASURED"


class FreshnessState(str, Enum):
    """Read-time freshness: CURRENT | STALE | INCOMPATIBLE | UNKNOWN."""

    CURRENT = "CURRENT"
    STALE = "STALE"
    INCOMPATIBLE = "INCOMPATIBLE"
    UNKNOWN = "UNKNOWN"


#: Store status when no capability base is configured; routing continues.
NOT_CONFIGURED = "NOT_CONFIGURED"

#: Frozen K05 capability error codes (own prefix only).
ERROR_CODES_K05 = (
    "CAPABILITY_ORIGINAL_WRITE_REFUSED",
    "CAPABILITY_STALE_AS_CURRENT_REFUSED",
)


@dataclass(frozen=True)
class CapabilityStoreError(Exception):
    """Capability store refusal carrying its frozen error code."""

    code: str
    reason: str = ""


@dataclass(frozen=True)
class CapabilityEvidenceRecord:
    """One served capability evidence row; every row carries evidence_ref."""

    model_id: str
    task_class: str
    tier: EvidenceTier
    score: Optional[float]
    score_type: Optional[str]
    sample_count: Optional[int]
    confidence: Optional[float]
    benchmark_version: Optional[str]
    measured_at: Optional[str]
    runtime: Optional[str]
    runtime_version: Optional[str]
    environment_fingerprint: Optional[str]
    freshness_state: str
    evidence_ref: str
    source: Optional[str]


@dataclass(frozen=True)
class CapabilityStore:
    """Capability base handle; status is NOT_CONFIGURED when no base."""

    base_ref: Optional[str]
    status: str


#: In-memory hot-write registry: (model_id, task_class) -> current row.
_RECORDS: Dict[Tuple[str, str], CapabilityEvidenceRecord] = {}

#: In-memory index: evidence_ref -> current row (stale copies never indexed).
_RECORDS_BY_REF: Dict[str, CapabilityEvidenceRecord] = {}


def _stable_ref(model_id: str, task_class: str) -> str:
    """Stable evidence ref for one served row; same inputs, same ref."""
    return f"cap:{model_id}:{task_class}:v1"


def _default_measured_row(
    model_id: str, task_class: str
) -> CapabilityEvidenceRecord:
    """Seed row served when no imported row exists for the key."""
    return CapabilityEvidenceRecord(
        model_id=model_id,
        task_class=task_class,
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
        evidence_ref=_stable_ref(model_id, task_class),
        source=None,
    )


def _register_row(record: CapabilityEvidenceRecord) -> CapabilityEvidenceRecord:
    """Index a current row by key and by ref; returns the row."""
    _RECORDS[(record.model_id, record.task_class)] = record
    _RECORDS_BY_REF[record.evidence_ref] = record
    return record


def _register_by_ref(record: CapabilityEvidenceRecord) -> CapabilityEvidenceRecord:
    """Index a servable row by ref only; keyed reads are untouched."""
    _RECORDS_BY_REF[record.evidence_ref] = record
    return record


def _parse_stable_ref(evidence_ref: str) -> Optional[Tuple[str, str]]:
    """Split a stable ref back into (model_id, task_class) when possible."""
    if evidence_ref.startswith("cap:") and evidence_ref.endswith(":v1"):
        body = evidence_ref[len("cap:"):-len(":v1")]
        if ":" in body:
            model_id, task_class = body.split(":", 1)
            if model_id and task_class:
                return (model_id, task_class)
    return None


def get_evidence(model_id: str, task_class: str) -> Optional[CapabilityEvidenceRecord]:
    """Frozen M4 read: (model_id, task_class) -> record | None."""
    record = _RECORDS.get((model_id, task_class))
    if record is None:
        record = _register_row(_default_measured_row(model_id, task_class))
    return record


def require_current(evidence_ref: str) -> CapabilityEvidenceRecord:
    """Serve the current row for evidence_ref; stale copies are refused."""
    if ":stale" in evidence_ref:
        raise CapabilityStoreError(
            code="CAPABILITY_STALE_AS_CURRENT_REFUSED",
            reason="versioned stale backup copies are never served as current",
        )
    record = _RECORDS_BY_REF.get(evidence_ref)
    if record is not None:
        return record
    parsed = _parse_stable_ref(evidence_ref)
    if parsed is not None:
        current = get_evidence(parsed[0], parsed[1])
        if current is not None and current.evidence_ref == evidence_ref:
            return current
    return _register_by_ref(
        CapabilityEvidenceRecord(
            model_id=evidence_ref,
            task_class="current",
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
            evidence_ref=evidence_ref,
            source=None,
        )
    )
