"""K03 assurance lane STEP1 shapes: the narrow cross-package interface.

Frozen sources: RECORDS/day0/K13_MANIFEST.md §17B (canonical AuditResult
and separate handling disposition), §0A-adjacent SPEC 0A in
DIRECTOR/TASK_PACKAGES/K03/TASK.md (requirement verdicts PRESERVED /
CHANGED / MISSING / CONTRADICTED), §1 authority order USER > DIRECTOR >
MANAGER > AGENTS; RECORDS/day1/K04_INTERFACE.md sec 2 (exact model id);
other packages code against this module only and never import lane
internals. Every value below repeats a frozen spelling; canonical record
shapes live in audit_records.py, sourcing in audit_registry.py,
coordination in audit_coordinator.py and grounding in grounding.py.
"""

from __future__ import annotations

from typing import Final, Protocol

#: Exact model id (never retyped, never a second id; K04 sec 2, K02 §2).
MODEL_ID: Final = "meta/muse-spark-1.3-contributor"

#: Registry signal when no auditor is eligible (fail-closed).
NO_ELIGIBLE_AUDITOR: Final = "NO_ELIGIBLE_AUDITOR"

#: Context-integrity value that alone permits PASS (K13 §45A).
CONTEXT_INTEGRITY_PASS: Final = "PASS"

#: Reason recorded when the audit budget is exhausted (K13 §17B).
REWORK_BUDGET_EXHAUSTED: Final = "REWORK_BUDGET_EXHAUSTED"

#: Canonical audit verdicts; immutable evidence (K13 §17B).
AUDIT_RESULTS = ("PASS", "REWORK", "BLOCKED", "ESCALATE", "FAIL")

#: Separate runtime decision; never rewrites the result (K13 §17B).
AUDIT_HANDLING = ("COMPLETE", "REWORK", "BLOCK", "ESCALATE", "FAIL")

#: Per-requirement verdicts; non-PRESERVED blocks PASS (SPEC 0A).
REQUIREMENT_VERDICTS = ("PRESERVED", "CHANGED", "MISSING", "CONTRADICTED")

#: One deterministic path per failure class (K13 §17C).
FAILURE_CLASSES = (
    "VERIFICATION_INFRA_FAILURE",
    "OUTPUT_FORMAT_FAILURE",
    "PROVIDER_OR_MODEL_CAPABILITY_FAILURE",
    "IMPLEMENTATION_AC_DEFECT",
    "SECURITY_OR_POLICY_FAILURE",
    "UNKNOWN_FAILURE",
)

#: Runtime authority order; the auditor commands nothing (SPEC 1).
AUTHORITY_ORDER = ("USER", "DIRECTOR", "MANAGER", "AGENTS")


class AssuranceQuery(Protocol):
    """Read-only assurance view for other packages (no PASS grants here)."""

    def latest_audit_result(self, task_id: str, scope_id: str) -> str:
        """Latest AuditResult spelling for a scope; no audit means no PASS."""
        ...

    def audit_exists_for_scope(self, task_id: str, scope_id: str) -> bool:
        """True only when a stored audit record covers the scope."""
        ...


#: Entry points: logical name -> owning symbol (STEP2 implements).
ENTRY_POINTS = {
    "latest_audit_result": (
        "agent_si.assurance.assurance_iface.AssuranceQuery.latest_audit_result"
    ),
    "audit_exists_for_scope": (
        "agent_si.assurance.assurance_iface.AssuranceQuery"
        ".audit_exists_for_scope"
    ),
    "ground_artifact": (
        "agent_si.assurance.grounding.GroundingPort.ground_artifact"
    ),
    "select_auditor": (
        "agent_si.assurance.audit_registry.AuditorRegistry.select_auditor"
    ),
    "audit_served_turn": (
        "agent_si.assurance.audit_coordinator.AuditCoordinator.audit_served_turn"
    ),
    "append": "agent_si.assurance.audit_records.AuditLog.append",
}
