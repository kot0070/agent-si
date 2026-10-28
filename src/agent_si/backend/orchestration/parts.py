"""Served part register, GATE-RULE close, and per-package load ledger (lane A).

ROW33 + M-P1-15 + ROW87/94 + M-P1-17. V2 ONE-HOME: the shared kernel
(ApplyOutcome, DecisionLog, DecisionRow, utc_now, surface_rejection,
ensure_compact_english, is_compact_english, hot_write_text) lives in
common.py, the load-ledger shapes in ledger.py, and TeamCard in
teamcard.py; all are re-exported here and keep their frozen shapes:
TeamCard {provider, model, model_kb_facts:dict, budget_left, limits};
LedgerRow {package_id, agents:int, peak_concurrency:int, wall_time_s:float};
DecisionRow {decision_id, scope, statement, reason, authority, created_at};
PartRef {package_id, contract_hash, gate_verdict_ref, audit_verdict_ref}.
Model id is exactly meta/muse-spark-1.3-contributor.
GATE-RULE: gates.close_part refuses unless the served gate verdict is
PASS and the served audit verdict is PASS.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from .common import (
    ApplyOutcome,
    DecisionLog,
    DecisionRow,
    ensure_compact_english,
    hot_write_text,
    is_compact_english,
    surface_rejection,
    utc_now,
)
from .ledger import (
    LedgerRow,
    PackageLedger,
    build_package_report,
    load_ledger,
    package_report,
    persist_ledger,
)
from .teamcard import TeamCard

MODEL_ID = "meta/muse-spark-1.3-contributor"

GATE_PASS = "PASS"
AUDIT_PASS = "PASS"

GATE_VERDICTS = frozenset({"PASS", "FAIL", "BLOCKED"})
AUDIT_RESULTS = frozenset({"PASS", "REWORK", "BLOCKED", "ESCALATE", "FAIL"})

ARTIFACT_PREFIX = "artifact://"
ARTIFACT_REF_PREFIX = "ARTIFACT_REF:"


class GateRefused(Exception):
    """Refusal: a part cannot close under GATE-RULE."""


PartStatus = Literal[
    "QUEUED", "RUNNING", "RETURNED", "ACCEPTED", "REJECTED", "BLOCKED", "HANDOFF",
]

_STATUSES: tuple[str, ...] = (
    "QUEUED",
    "RUNNING",
    "RETURNED",
    "ACCEPTED",
    "REJECTED",
    "BLOCKED",
    "HANDOFF",
)


@dataclass
class PartRow:
    agent: str
    scope: str
    deliverable: str
    status: PartStatus = "QUEUED"

    def __post_init__(self) -> None:
        if not self.agent.strip():
            raise ValueError("PartRow.agent must be non-empty")
        if not self.scope.strip():
            raise ValueError("PartRow.scope must be non-empty")
        if not self.deliverable.strip():
            raise ValueError("PartRow.deliverable must be non-empty")
        if not self.deliverable.startswith("artifact://"):
            raise ValueError("deliverable must be an ARTIFACT_REF, not inline content")
        if self.status not in _STATUSES:
            raise ValueError(f"unknown status: {self.status}")


_store: dict[str, PartRow] = {}


def register_part(row: PartRow) -> PartRow:
    stored = replace(row)
    if stored.scope in _store:
        raise ValueError(f"duplicate scope: {stored.scope}")
    _store[stored.scope] = stored
    return replace(stored)


def list_parts(status: PartStatus | None) -> list[PartRow]:
    if status is not None and status not in _STATUSES:
        raise ValueError(f"unknown status: {status}")
    rows = [row for row in _store.values() if status is None or row.status == status]
    rows.sort(key=lambda row: row.scope)
    return [replace(row) for row in rows]


def update_status(package_id: str, status: PartStatus) -> PartRow:
    if status not in _STATUSES:
        raise ValueError(f"unknown status: {status}")
    try:
        stored = _store[package_id]
    except KeyError:
        raise KeyError(f"no registered part {package_id}") from None
    stored.status = status
    return replace(stored)


@dataclass
class PartRecord:
    part_id: str
    package_id: str
    contract_hash: str
    agent: str
    scope: str
    deliverable_ref: str

    def __post_init__(self) -> None:
        for name in ("part_id", "package_id", "contract_hash", "agent", "scope"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"PartRecord.{name} must be a non-blank string")
        if not isinstance(d := self.deliverable_ref, str) or not d.strip():
            raise ValueError("PartRecord.deliverable_ref must be non-empty")
        if not (
            self.deliverable_ref.startswith(ARTIFACT_PREFIX)
            or self.deliverable_ref.startswith(ARTIFACT_REF_PREFIX)
        ):
            raise ValueError(
                "deliverable_ref must be an ARTIFACT_REF, not inline content"
            )


@dataclass(frozen=True)
class ClosedPartRef:
    package_id: str
    contract_hash: str
    gate_verdict_ref: str
    audit_verdict_ref: str


class PartStore:
    """Served parts with recorded gate and audit verdicts.

    Gate and audit verdicts are recorded per part (as served by the gate and
    audit lanes). Closing is served by gates.close_part over the recorded
    refs, which refuses with GATE_NOT_PASSED unless the served gate verdict
    is PASS and the served audit verdict is PASS.
    """

    def __init__(self) -> None:
        self._records: dict[str, PartRecord] = {}
        self._gate: dict[str, tuple[str, str]] = {}
        self._audit: dict[str, tuple[str, str]] = {}

    def register(self, record: PartRecord) -> PartRecord:
        if not isinstance(record, PartRecord):
            raise ValueError("only PartRecord rows register")
        if record.part_id in self._records:
            raise ValueError(f"duplicate part_id: {record.part_id}")
        stored = replace(record)
        self._records[stored.part_id] = stored
        return replace(stored)

    def get(self, part_id: str) -> PartRecord | None:
        found = self._records.get(part_id)
        return replace(found) if found is not None else None

    def record_gate_verdict(self, part_id: str, verdict: str, ref: str) -> str:
        if part_id not in self._records:
            raise KeyError(f"no registered part {part_id}")
        if verdict not in GATE_VERDICTS:
            raise ValueError(f"unknown gate verdict: {verdict}")
        if not isinstance(ref, str) or not ref.strip():
            raise ValueError("gate verdict ref must be non-empty")
        self._gate[part_id] = (ref, verdict)
        return ref

    def record_audit_verdict(self, part_id: str, result: str, ref: str) -> str:
        if part_id not in self._records:
            raise KeyError(f"no registered part {part_id}")
        if result not in AUDIT_RESULTS:
            raise ValueError(f"unknown audit result: {result}")
        if not isinstance(ref, str) or not ref.strip():
            raise ValueError("audit verdict ref must be non-empty")
        self._audit[part_id] = (ref, result)
        return ref

    def gate_verdict(self, part_id: str) -> str | None:
        entry = self._gate.get(part_id)
        return entry[1] if entry is not None else None

    def audit_verdict(self, part_id: str) -> str | None:
        entry = self._audit.get(part_id)
        return entry[1] if entry is not None else None


__all__ = [
    "AUDIT_PASS",
    "AUDIT_RESULTS",
    "GATE_PASS",
    "GATE_VERDICTS",
    "MODEL_ID",
    "ApplyOutcome",
    "ClosedPartRef",
    "DecisionLog",
    "DecisionRow",
    "GateRefused",
    "LedgerRow",
    "PackageLedger",
    "PartRecord",
    "PartRow",
    "PartStatus",
    "PartStore",
    "TeamCard",
    "build_package_report",
    "ensure_compact_english",
    "hot_write_text",
    "is_compact_english",
    "list_parts",
    "load_ledger",
    "package_report",
    "persist_ledger",
    "register_part",
    "surface_rejection",
    "update_status",
    "utc_now",
]
