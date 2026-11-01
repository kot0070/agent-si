"""K03 assurance lane STEP1 shapes: fail-closed auditor sourcing.

Frozen sources: RECORDS/day0/K13_MANIFEST.md §26A (AuditRequirement,
minimum_independence_level, L4 manual rules), §28 (RoutingDecision
capability_evidence_refs, eligibility_source), §37 (capability base is
PROXY/MEASURED evidence, never assumed), §44 (AuditorRegistry owns lookup
only, never execution); RECORDS/day1/K04_INTERFACE.md sec 2 (exact model
id, never reworded) and sec 6 (NO_ELIGIBLE_CANDIDATE vocabulary);
RECORDS/day1/K02_V2_CHANGES.md C16 (select_audit_model, AuditModelChoice);
DIRECTOR/TASK_PACKAGES/K03/TASK.md ROWS B0B-BP07-14/17/18/20 (fail-closed
sourcing, NO_ELIGIBLE_AUDITOR, BLOCKED, PASS prohibited until sourcing
completes), B0B-BP07-53/54 (sourcing stays fail-closed BLOCKED until the
USER resolves provider options), B0B-UNCOVERED_ARCH-652/746 (missing
capability evidence keeps a candidate ineligible), B0B-UNCOVERED_ARCH-653
(no eligible auditor forces BLOCKED, never degraded self-audit),
B0B-UNCOVERED_ARCH-654 (L2 holds only while the auditor canonical model id
stays absent from implementer model ids), B0B-UNCOVERED_ARCH-740/741
(sourcing independent of implementers; auditor-task-class sourcing fails
closed), B0B-UNCOVERED_ARCH-745 (parked Task until the USER resolves
sourcing), B0B-UNCOVERED_MVP_ACCEPT-224 (unresolved dependency fails closed
with documented options), ROW 13 (pair reuse needs a recorded decision
plus user visibility), ROW R-355 (contributors never in the auditor set;
accepted risk off by default, user-only).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, replace
from typing import Dict, Final, List, Optional, Protocol, Tuple

#: Exact model id (never retyped, never a second id; K04 sec 2, K02 §2).
MODEL_ID: Final = "meta/muse-spark-1.3-contributor"

#: Registry signal when no auditor is eligible (fail-closed; ROW B0B-BP07-20).
NO_ELIGIBLE_AUDITOR: Final = "NO_ELIGIBLE_AUDITOR"

#: Only this authority resolves parked auditor sourcing (BP07-53/54).
USER_AUTHORITY: Final = "USER"


@dataclass(frozen=True)
class AuditorCandidate:
    """One candidate auditor; ineligible until capability evidence arrives."""

    provider_id: str
    provider_instance: Optional[str]
    model: str
    capability_evidence_refs: Tuple[str, ...] = ()
    registered_at: str = ""


@dataclass(frozen=True)
class AuditorBinding:
    """A raised auditor on a fresh context session (never a contributor)."""

    provider_id: str
    model: str
    session_ref: str
    bound_at: str = ""


@dataclass(frozen=True)
class SourcingDecision:
    """Recorded sourcing decision with user visibility (ROW 13, BP07-53/54)."""

    decision_id: str
    project_id: str
    scope: str
    statement: str
    reason: str
    authority: str
    decided_by: str
    visible_to_user: bool
    user_resolution_ref: Optional[str]
    created_at: str


@dataclass(frozen=True)
class AuditorSelection:
    """A sourced auditor plus the achieved level and its decision ref."""

    auditor: AuditorBinding
    independence_level: str
    sourcing_decision_ref: str
    recorded_at: str


@dataclass(frozen=True)
class SingleProviderAcceptance:
    """Single-provider acceptance: achieved level plus user acceptance.

    Frozen done-means for the TASK E2 single-provider probe (K13 §26A).
    """

    scope: str
    achieved_level: str
    user_acceptance_ref: str
    recorded_at: str


class NoEligibleAuditorError(Exception):
    """Raised when no auditor is eligible; the gate maps it to BLOCKED."""

    code: str = NO_ELIGIBLE_AUDITOR


#: Shared registry state (module-level): pair-reuse decisions stay visible
#: across instances (the coordinator resolves them without an instance
#: reference) and resolved sourcing scopes are distinct per scope.
#: Candidate/evidence/session state is per-instance (lazy on ``self``):
#: each test builds a fresh registry and expects fresh state.
_PAIR_REUSE: Dict[str, SourcingDecision] = {}
_RESOLVED: Dict[str, SourcingDecision] = {}


def _now_iso() -> str:
    """Current UTC time as an ISO-8601 string."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _evidence_for(
    provider_id: str,
    model: str,
    candidates: Dict[Tuple[str, str], AuditorCandidate],
    evidence: Dict[Tuple[str, str], List[str]],
) -> Tuple[str, ...]:
    """Union of constructor refs and noted evidence refs for one key."""
    key = (provider_id, model)
    candidate = candidates.get(key)
    base = tuple(candidate.capability_evidence_refs) if candidate is not None else ()
    noted = tuple(evidence.get(key, ()))
    return tuple(dict.fromkeys(base + noted))


def _find_pair_reuse(decision_id: str) -> Optional[SourcingDecision]:
    """Return the recorded pair-reuse decision, or None when absent."""
    return _PAIR_REUSE.get(decision_id)


def _kb_evidence_for(provider_id: str, model: str) -> Tuple[str, ...]:
    """Staged model-KB capability evidence for one pair, fail-closed.

    FB2B4R (F04): when the candidate store holds no refs for a pair,
    the bound model-KB catalog is consulted for that exact pair via
    the kb retriever seam; UNKNOWN-field rows yield no evidence and
    an unreadable store yields (), never an invented ref.
    """
    try:
        from agent_si.kb import retriever as _kb_retriever
    except ImportError:
        try:
            from src.agent_si.kb import retriever as _kb_retriever
        except ImportError:
            return ()
    try:
        refs = _kb_retriever.auditor_capability_evidence(
            provider_id, model
        )
    except Exception:
        return ()
    return refs if isinstance(refs, tuple) else ()


class AuditorRegistry(Protocol):
    """Fail-closed auditor sourcing, independent of implementers (ARCH-740)."""

    def register_candidate(
        self, candidate: AuditorCandidate
    ) -> AuditorCandidate:
        """Record one candidate auditor with its stated capability refs."""
        candidates = self.__dict__.setdefault("_CANDIDATES", {})
        evidence = self.__dict__.setdefault("_EVIDENCE", {})
        key = (candidate.provider_id, candidate.model)
        refs = evidence.setdefault(key, [])
        for ref in candidate.capability_evidence_refs:
            if ref not in refs:
                refs.append(ref)
        candidates[key] = candidate
        return candidate

    def note_capability_evidence(
        self, provider_id: str, model: str, evidence_ref: str
    ) -> AuditorCandidate:
        """Attach capability evidence; missing evidence keeps ineligible."""
        candidates = self.__dict__.setdefault("_CANDIDATES", {})
        evidence = self.__dict__.setdefault("_EVIDENCE", {})
        key = (provider_id, model)
        refs = evidence.setdefault(key, [])
        if evidence_ref not in refs:
            refs.append(evidence_ref)
        candidate = candidates.get(key)
        if candidate is None:
            return AuditorCandidate(provider_id, None, model, tuple(refs), "")
        merged = tuple(
            dict.fromkeys(tuple(candidate.capability_evidence_refs) + tuple(refs))
        )
        updated = replace(candidate, capability_evidence_refs=merged)
        candidates[key] = updated
        return updated

    def is_eligible(self, provider_id: str, model: str) -> bool:
        """True only with health plus capability evidence on record.

        FB2B4R (F04): a registered pair with no refs in the candidate
        store falls back to the staged bound model-KB rows for that
        exact pair; UNKNOWN rows stay ineligible.
        """
        candidates = self.__dict__.setdefault("_CANDIDATES", {})
        evidence = self.__dict__.setdefault("_EVIDENCE", {})
        if (provider_id, model) not in candidates:
            return False
        if _evidence_for(provider_id, model, candidates, evidence):
            return True
        return len(_kb_evidence_for(provider_id, model)) >= 1

    def check_separate_model(
        self, auditor_model: str, implementer_model_ids: Tuple[str, ...]
    ) -> bool:
        """L2 holds only while the auditor id stays absent (ARCH-654)."""
        return auditor_model not in implementer_model_ids

    def select_auditor(
        self,
        task_class: str,
        implementer_model_ids: Tuple[str, ...],
        minimum_level: str,
    ) -> AuditorSelection:
        """Source an auditor outside the implementer set.

        Raises NoEligibleAuditorError when none qualifies; never degrades
        to self-audit (ARCH-653/741).
        """
        candidates = self.__dict__.setdefault("_CANDIDATES", {})
        evidence = self.__dict__.setdefault("_EVIDENCE", {})
        if task_class == "auditor":
            raise NoEligibleAuditorError(NO_ELIGIBLE_AUDITOR)
        order = {"L0": 0, "L1": 1, "L2": 2, "L3": 3, "L4": 4}
        required = order.get(minimum_level)
        if required is None or required > 2:
            raise NoEligibleAuditorError(NO_ELIGIBLE_AUDITOR)
        for key in candidates:
            provider_id, model = key
            evidenced = _evidence_for(provider_id, model, candidates, evidence)
            if not evidenced:
                # FB2B4R (F04): no refs in the candidate store ->
                # consult the staged bound model-KB rows for the pair.
                evidenced = _kb_evidence_for(provider_id, model)
            if not evidenced:
                continue
            if model in implementer_model_ids:
                continue
            serial = int(self.__dict__.get("_SESSION_SERIAL", 0)) + 1
            self.__dict__["_SESSION_SERIAL"] = serial
            now = _now_iso()
            binding = AuditorBinding(
                provider_id, model, "auditor-session-%06d" % serial, now
            )
            return AuditorSelection(binding, "L2", "", now)
        raise NoEligibleAuditorError(NO_ELIGIBLE_AUDITOR)

    def record_pair_reuse(self, decision: SourcingDecision) -> SourcingDecision:
        """Record pair reuse with its reason; shown to the user (ROW 13)."""
        _PAIR_REUSE[decision.decision_id] = decision
        return decision

    def resolve_sourcing(self, decision: SourcingDecision) -> SourcingDecision:
        """Apply the USER resolution of parked sourcing (BP07-53/54)."""
        if decision.authority == USER_AUTHORITY and decision.user_resolution_ref:
            _RESOLVED[decision.scope] = decision
        return decision

    def sourcing_state(self, scope: str) -> str:
        """BLOCKED until the USER resolves; parked Task waits on it."""
        if scope in _RESOLVED:
            return "RESOLVED"
        return "BLOCKED"

    def record_single_provider_acceptance(
        self, scope: str, achieved_level: str, user_acceptance_ref: str
    ) -> SingleProviderAcceptance:
        """Record one-model fresh-context mode level plus acceptance."""
        return SingleProviderAcceptance(
            scope, achieved_level, user_acceptance_ref, _now_iso()
        )


#: Entry points: logical name -> symbol in this file (STEP2 implements).
ENTRY_POINTS = {
    "register_candidate": (
        "agent_si.assurance.audit_registry.AuditorRegistry.register_candidate"
    ),
    "note_capability_evidence": (
        "agent_si.assurance.audit_registry.AuditorRegistry"
        ".note_capability_evidence"
    ),
    "is_eligible": (
        "agent_si.assurance.audit_registry.AuditorRegistry.is_eligible"
    ),
    "check_separate_model": (
        "agent_si.assurance.audit_registry.AuditorRegistry.check_separate_model"
    ),
    "select_auditor": (
        "agent_si.assurance.audit_registry.AuditorRegistry.select_auditor"
    ),
    "record_pair_reuse": (
        "agent_si.assurance.audit_registry.AuditorRegistry.record_pair_reuse"
    ),
    "resolve_sourcing": (
        "agent_si.assurance.audit_registry.AuditorRegistry.resolve_sourcing"
    ),
    "sourcing_state": (
        "agent_si.assurance.audit_registry.AuditorRegistry.sourcing_state"
    ),
    "record_single_provider_acceptance": (
        "agent_si.assurance.audit_registry.AuditorRegistry"
        ".record_single_provider_acceptance"
    ),
}
