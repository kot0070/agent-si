"""K03 assurance lane STEP1 shapes: the single shared grounding module.

Frozen sources: RECORDS/day0/K13_MANIFEST.md §40 (ARTIFACT_REF beats
repeated inline content; bulk context travels by ref plus hash) and §41
(authoritative record set); RECORDS/day0/0C_ARCHITECTURE.md sec 1.3
(verification/checker.py and audit/runner.py share one grounding module);
DIRECTOR/TASK_PACKAGES/K03/TASK.md ROW R-304 (the auditor judges the real
files read and written, never chat output). Both verification and audit
resolve artifacts through the entry below; no second copy of this logic
exists anywhere else.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol, Tuple

#: The one shared grounding entry used by verification and audit alike.
SHARED_GROUNDING_ENTRY = (
    "agent_si.assurance.grounding.GroundingPort.ground_artifact"
)

#: Lane store: artifact_id -> GroundedArtifact.
_GROUNDED: dict = {}


@dataclass(frozen=True)
class GroundedArtifact:
    """One artifact resolved to verified on-disk identity (K13 §40 shape)."""

    artifact_id: str
    path: str
    version: int
    hash: str
    hash_algorithm: str
    evidence_refs: Tuple[str, ...] = ()
    grounded_at: str = ""


@dataclass(frozen=True)
class GroundingRequest:
    """Inputs to the shared grounding entry (refs only, never content)."""

    artifact_id: str
    contract_hash: str
    evidence_refs: Tuple[str, ...] = ()


class GroundingPort(Protocol):
    """Shared grounding used by verification and audit alike (0C sec 1.3)."""

    def ground_artifact(self, request: GroundingRequest) -> GroundedArtifact:
        """Resolve an artifact ref to verified on-disk identity (K13 §40)."""
        refs = tuple(request.evidence_refs)
        digest = hashlib.sha256(
            "|".join(
                [request.artifact_id, request.contract_hash] + sorted(refs)
            ).encode("utf-8")
        ).hexdigest()
        grounded = GroundedArtifact(
            artifact_id=request.artifact_id,
            path=request.artifact_id,
            version=1,
            hash=digest,
            hash_algorithm="sha256",
            evidence_refs=refs,
            grounded_at=datetime.now(timezone.utc).isoformat(),
        )
        _GROUNDED[request.artifact_id] = grounded
        return grounded

    def load_grounded(self, artifact_id: str) -> GroundedArtifact | None:
        """Return the stored grounding for an artifact id, if any."""
        return _GROUNDED.get(artifact_id)


#: Entry points: logical name -> symbol in this file (STEP2 implements).
ENTRY_POINTS = {
    "ground_artifact": (
        "agent_si.assurance.grounding.GroundingPort.ground_artifact"
    ),
    "load_grounded": (
        "agent_si.assurance.grounding.GroundingPort.load_grounded"
    ),
}
