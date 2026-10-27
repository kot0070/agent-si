"""Decision + authorization records (Manifest sections 21B, 19A).

Permission ladder (frozen, section 19A):
  R0 auto when task-authorized
    < R1 task-contract authorization
    < R2 Director explicit record
    < R3 user explicit record.
Generated commands never gain privilege: a model (or any non Director/user
issuer) can never grant authorization; only granted_by "director" (R2) or
"user" (R3) writes a valid AuthorizationRecord, and HIGH/CRITICAL risk needs
the R3 user record. Shared names come ONLY from
iface/frozen_manifest/manifest.py; on any clash the 0C architecture wins.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from iface.frozen_manifest import manifest
except ImportError:  # alternate layout: the iface/ directory itself on sys.path
    from frozen_manifest import manifest


class ConcurrentEditError(Exception):
    """compare_and_set failed: expected_version is stale; loser re-reads."""


class AuthorizationRejectedError(Exception):
    """An authorization write was rejected (forged, model-issued, expired)."""


def _as_tuple(value: Any) -> Tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    return tuple(value)


# ---------------------------------------------------------------------------
# DecisionRecord (section 21B): nullable task/run refs, version-ordered.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DecisionRecord:
    """Manifest section 21B DecisionRecord. Immutable; version-ordered edits."""

    decision_id: str = ""
    project_id: str = ""
    task_id: Optional[str] = None
    run_id: Optional[str] = None
    phase_id: Optional[str] = None
    gate_id: Optional[str] = None
    scope: str = ""
    type: str = ""
    statement: str = ""
    reason: str = ""
    authority: str = ""
    created_at: str = ""
    evidence_refs: Tuple[str, ...] = ()
    supersedes_decision_id: Optional[str] = None
    status: str = ""
    version: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_refs", _as_tuple(self.evidence_refs))


def order_decisions(records: Iterable[DecisionRecord]) -> List[DecisionRecord]:
    """Version ordering for concurrent edits (section 21B); never silent."""
    return sorted(list(records), key=lambda item: item.version)


def resolve_latest(records: Iterable[DecisionRecord]) -> Optional[DecisionRecord]:
    """Return the highest-version decision; None when there are none."""
    best: Optional[DecisionRecord] = None
    for record in records:
        if best is None or record.version > best.version:
            best = record
    return best


def replace_decision(old: DecisionRecord, **changes: Any) -> DecisionRecord:
    """Build a NEW decision version; *old* is never rewritten (section 21B)."""
    if "version" in changes:
        raise ValueError("version is ordered, never supplied")
    return replace(old, version=old.version + 1, **changes)


def commit_decision(
    records: Iterable[DecisionRecord],
    expected_version: int,
    record: DecisionRecord,
) -> DecisionRecord:
    """compare_and_set on (decision_id, expected_version); loser re-reads."""
    latest = resolve_latest(
        item for item in records if item.decision_id == record.decision_id
    )
    current = latest.version if latest is not None else 0
    if current != expected_version:
        raise ConcurrentEditError(
            "stale commit for %r: expected version %d, current is %d"
            % (record.decision_id, expected_version, current)
        )
    return record


# ---------------------------------------------------------------------------
# AuthorizationRecord (section 19A): R2 Director, R3 user.
# ---------------------------------------------------------------------------

R2_GRANTED_BY = "director"
R3_GRANTED_BY = "user"
GRANT_TIERS = {R2_GRANTED_BY: "R2", R3_GRANTED_BY: "R3"}
"""Only Director (R2) and user (R3) explicit records grant; see ladder above."""


@dataclass(frozen=True)
class AuthorizationRecord:
    """Manifest section 19A AuthorizationRecord. Immutable, R2/R3 only."""

    authorization_id: str = ""
    project_id: str = ""
    task_id: str = ""
    run_id: Optional[str] = None
    risk_level: manifest.RiskLevel = manifest.RiskLevel.LOW
    action: str = ""
    scope: str = ""
    granted_by: str = ""
    granted_at: str = ""
    expires_at: Optional[str] = None
    evidence_ref: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.risk_level, str) and not isinstance(
            self.risk_level, manifest.RiskLevel
        ):
            object.__setattr__(
                self, "risk_level", manifest.RiskLevel(self.risk_level)
            )
        if self.granted_by not in GRANT_TIERS:
            raise AuthorizationRejectedError(
                "granted_by %r cannot grant: only 'director' (R2) or 'user' "
                "(R3) explicit records authorize; generated commands never "
                "gain privilege (Manifest section 19A)" % (self.granted_by,)
            )


def tier_of(record: AuthorizationRecord) -> str:
    """Return the ladder tier of a valid grant: R2 (Director) or R3 (user)."""
    return GRANT_TIERS[record.granted_by]


def _requires_user(risk: manifest.RiskLevel) -> bool:
    return risk in (manifest.RiskLevel.HIGH, manifest.RiskLevel.CRITICAL)


class AuthorizationStore:
    """Append-only authorization log (ports shape: append returns stored).

    append(record) verifies the grant and rejects forgeries: a duplicate
    authorization_id with different content, a non R2/R3 issuer, a HIGH or
    CRITICAL risk without an R3 user grant, or a missing evidence_ref.
    Duplicate identical appends return the stored record (idempotent).
    """

    def __init__(self) -> None:
        self._records: Dict[str, AuthorizationRecord] = {}

    def append(self, record: AuthorizationRecord) -> AuthorizationRecord:
        """Verify and append; return the stored record."""
        stored = self._records.get(record.authorization_id)
        if stored is not None:
            if stored != record:
                raise AuthorizationRejectedError(
                    "forged authorization %r: duplicate id with different "
                    "content vs the append-only store"
                    % (record.authorization_id,)
                )
            return stored
        if _requires_user(record.risk_level) and record.granted_by != R3_GRANTED_BY:
            raise AuthorizationRejectedError(
                "risk %r needs an R3 user record; granted_by %r rejected"
                % (record.risk_level.value, record.granted_by)
            )
        if not record.evidence_ref:
            raise AuthorizationRejectedError(
                "authorization %r rejected: evidence_ref required"
                % (record.authorization_id,)
            )
        self._records[record.authorization_id] = record
        return record

    def list_by(self, authorization_id: str) -> List[AuthorizationRecord]:
        """Replay/audit-friendly read: the stored record, or empty."""
        record = self._records.get(authorization_id)
        return [record] if record is not None else []


def request_high_risk_approval(
    store: AuthorizationStore, *, authorization_id: str, project_id: str,
    task_id: str, action: str, scope: str, granted_by: str,
) -> AuthorizationRecord:
    """Record a HIGH-risk approval; model-issued grants are rejected.

    Rejection stores nothing, so the action stays blocked (see check_action).
    """
    record = AuthorizationRecord(
        authorization_id=authorization_id,
        project_id=project_id,
        task_id=task_id,
        risk_level=manifest.RiskLevel.HIGH,
        action=action,
        scope=scope,
        granted_by=granted_by,
        granted_at="",
        evidence_ref="high-risk-evidence",
    )
    return store.append(record)


def check_action(
    store: AuthorizationStore, action: str, scope: str
) -> str:
    """Return AUTHORIZED when a matching grant is stored, else BLOCKED."""
    for record in store._records.values():
        if record.action == action and record.scope == scope:
            return "AUTHORIZED"
    return "BLOCKED"


__all__ = [
    "ConcurrentEditError",
    "AuthorizationRejectedError",
    "DecisionRecord",
    "order_decisions",
    "resolve_latest",
    "replace_decision",
    "commit_decision",
    "R2_GRANTED_BY",
    "R3_GRANTED_BY",
    "GRANT_TIERS",
    "AuthorizationRecord",
    "tier_of",
    "AuthorizationStore",
    "request_high_risk_approval",
    "check_action",
]
