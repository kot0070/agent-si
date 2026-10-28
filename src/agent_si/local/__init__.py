"""K05 local-AI lane package interface (shapes only, no logic).

Re-exports the frozen M1 call surface; see adapter.py and gateway.py
for the owning contracts. Standard library only.
"""

from __future__ import annotations

from agent_si.local.adapter import (
    ERROR_CODES_LOCAL,
    ROUTE_EXPLICIT_PIN,
    ROUTE_SPLIT,
    STATUS_NOT_CONFIGURED,
    CapabilityEvidence,
    EligibilityVerdict,
    EvidenceTier,
    LifecycleStage,
    LocalDecision,
    SplitAssignment,
    advance_lifecycle,
    check_eligibility,
    lifecycle_position,
    record_explicit_pin,
    record_split_decision,
    routing_continues,
)
from agent_si.local.gateway import (
    GATEWAY_IDLE_REASON,
    GATEWAY_SKIP_REASONS,
    PassiveCheckResult,
    passive_check,
)

__all__ = [
    "ERROR_CODES_LOCAL",
    "GATEWAY_IDLE_REASON",
    "GATEWAY_SKIP_REASONS",
    "ROUTE_EXPLICIT_PIN",
    "ROUTE_SPLIT",
    "STATUS_NOT_CONFIGURED",
    "CapabilityEvidence",
    "EligibilityVerdict",
    "EvidenceTier",
    "LifecycleStage",
    "LocalDecision",
    "PassiveCheckResult",
    "SplitAssignment",
    "advance_lifecycle",
    "check_eligibility",
    "lifecycle_position",
    "passive_check",
    "record_explicit_pin",
    "record_split_decision",
    "routing_continues",
]
