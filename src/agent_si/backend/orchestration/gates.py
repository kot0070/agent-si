"""Served phase gate plus fresh audit per part (lane A, coder A).

ROW87/94 + B0B-UNCOVERED_ARCH-653/740/741 + SPEC 21C/26A/43. AuditResult is
the frozen enum {PASS,REWORK,BLOCKED,ESCALATE,FAIL}. No close without a
stored gate PASS plus a stored audit PASS (see can_close, enforced by
close_part in this module).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")

GATE_VERDICTS = frozenset({"PASS", "FAIL", "BLOCKED"})
AUDIT_RESULTS = frozenset({"PASS", "REWORK", "BLOCKED", "ESCALATE", "FAIL"})
GATE_PASS = "PASS"
AUDIT_PASS = "PASS"


class GateRefused(Exception):
    """Raised when a gate verdict cannot be served."""


class AuditRefused(Exception):
    """Raised when an audit verdict cannot be served."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class GATE_NOT_PASSED(GateRefused):
    """Refusal: part refs do not resolve to stored gate PASS + audit PASS."""


class MISSING_INTEGRATION_TASK(Exception):
    """Phase close blocked: parts PASS but the integration task is missing."""


class INVALID_HIERARCHY_CHAIN(Exception):
    """Activation refused: hierarchy chain shape invalid, nothing mutated."""


@dataclass
class GateRecord:
    gate_id: str
    part_id: str
    verdict: str
    created_at: str


@dataclass
class AuditRecord:
    audit_id: str
    part_id: str
    result: str
    auditor_session_ref: str
    producer_session_refs: list[str] = field(default_factory=list)
    scope_id: str = ""
    audit_seq: int = 0
    context_integrity: bool = False
    created_at: str = ""


def gate_id_of(part_id: str, seq: int) -> str:
    return f"{part_id}:gate-{seq:03d}"


def audit_id_of(part_id: str, seq: int) -> str:
    return f"{part_id}:audit-{seq:03d}"


def audit_scope_id_of(part_id: str) -> str:
    digest = sha256(part_id.encode("utf-8")).hexdigest()[:16]
    return f"audit-scope-{digest}"


def can_close(gate_verdict: str | None, audit_verdict: str | None) -> tuple[bool, str]:
    if gate_verdict is None:
        return False, "no gate verdict stored"
    if audit_verdict is None:
        return False, "no audit verdict stored"
    if gate_verdict != GATE_PASS:
        return False, f"gate not PASS: {gate_verdict}"
    if audit_verdict != AUDIT_PASS:
        return False, f"audit not PASS: {audit_verdict}"
    return True, "ok"


_GATE_BY_ID: dict[str, str] = {}
_AUDIT_BY_ID: dict[str, str] = {}
_GATE_BY_PART: dict[str, tuple[str, str]] = {}
_AUDIT_BY_PART: dict[str, tuple[str, str]] = {}
_INTEGRATION_SUFFIX = ":integration"
_MIN_CHAIN_LEN = 3


class GateAuditLog:
    def __init__(self) -> None:
        self.gate_history: dict[str, list[GateRecord]] = {}
        self.audit_history: dict[str, list[AuditRecord]] = {}

    def serve_gate(self, part_id: str, verdict: str) -> GateRecord:
        if not part_id.strip():
            raise GateRefused("part_id must be non-empty")
        if verdict not in GATE_VERDICTS:
            raise GateRefused(f"unknown gate verdict: {verdict}")
        seq = len(self.gate_history.get(part_id, ())) + 1
        record = GateRecord(
            gate_id=gate_id_of(part_id, seq),
            part_id=part_id,
            verdict=verdict,
            created_at=utc_now(),
        )
        self.gate_history.setdefault(part_id, []).append(record)
        _GATE_BY_ID[record.gate_id] = record.verdict
        _GATE_BY_PART[part_id] = (record.gate_id, record.verdict)
        return record

    def serve_audit(
        self,
        part_id: str,
        result: str,
        auditor_session_ref: str,
        producer_session_refs: list[str] | tuple[str, ...],
        context_integrity: bool,
    ) -> AuditRecord:
        if not part_id.strip():
            raise AuditRefused("part_id must be non-empty")
        if result not in AUDIT_RESULTS:
            raise AuditRefused(f"unknown audit result: {result}")
        auditor = str(auditor_session_ref)
        if not auditor.strip():
            raise AuditRefused("auditor session ref must be non-empty")
        producers = [str(session) for session in producer_session_refs]
        if auditor in producers:
            raise AuditRefused(
                "self-audit refused: auditor session is in the producer set"
            )
        if result == AUDIT_PASS and not context_integrity:
            raise AuditRefused("PASS forbidden while context integrity not PASS")
        seq = len(self.audit_history.get(part_id, ())) + 1
        record = AuditRecord(
            audit_id=audit_id_of(part_id, seq),
            part_id=part_id,
            result=result,
            auditor_session_ref=auditor,
            producer_session_refs=producers,
            scope_id=audit_scope_id_of(part_id),
            audit_seq=seq,
            context_integrity=bool(context_integrity),
            created_at=utc_now(),
        )
        self.audit_history.setdefault(part_id, []).append(record)
        _AUDIT_BY_ID[record.audit_id] = record.result
        _AUDIT_BY_PART[part_id] = (record.audit_id, record.result)
        return record

    def gate_verdict(self, part_id: str) -> str | None:
        history = self.gate_history.get(part_id, ())
        return history[-1].verdict if history else None

    def audit_verdict(self, part_id: str) -> str | None:
        history = self.audit_history.get(part_id, ())
        return history[-1].result if history else None

    def has_fresh_audit(self, part_id: str) -> bool:
        return bool(self.audit_history.get(part_id))


def _ref_field(ref: object, name: str) -> str | None:
    try:
        if isinstance(ref, dict):  # noqa: SIM108  # frozen-cite K02
            value = ref.get(name)
        else:
            value = getattr(ref, name)
    except Exception:
        return None
    if isinstance(value, str) and value.strip():
        return value
    return None


def close_part(ref: object) -> dict:
    """Close one part: serve its GateVerdict (ROW94, frozen §3).

    Ref is the frozen PartRef shape {package_id, contract_hash,
    gate_verdict_ref, audit_verdict_ref}; attribute-style objects with the
    same four fields are accepted too. Both refs must resolve to stored
    GateAuditLog records with verdict PASS, else GATE_NOT_PASSED is raised
    (missing, gate-only, audit-only, FAIL, or malformed refs all refuse).
    Success returns the GateVerdict shape {package_id, gate, audit,
    decided_at, evidence_refs}.
    """
    try:
        package_id = _ref_field(ref, "package_id")
        contract_hash = _ref_field(ref, "contract_hash")
        gate_ref = _ref_field(ref, "gate_verdict_ref")
        audit_ref = _ref_field(ref, "audit_verdict_ref")
        if (
            package_id is None
            or contract_hash is None
            or gate_ref is None
            or audit_ref is None
        ):
            raise GATE_NOT_PASSED(
                "GATE_NOT_PASSED: malformed PartRef; need non-blank "
                "package_id, contract_hash, gate_verdict_ref, audit_verdict_ref"
            )
        gate_verdict = _GATE_BY_ID.get(gate_ref)
        audit_verdict = _AUDIT_BY_ID.get(audit_ref)
        ok, reason = can_close(gate_verdict, audit_verdict)
        if not ok:
            raise GATE_NOT_PASSED(f"GATE_NOT_PASSED: {reason}")
        return {
            "package_id": package_id,
            "gate": GATE_PASS,
            "audit": AUDIT_PASS,
            "decided_at": utc_now(),
            "evidence_refs": [gate_ref, audit_ref],
        }
    except GATE_NOT_PASSED:
        raise
    except Exception as exc:
        raise GATE_NOT_PASSED(
            f"GATE_NOT_PASSED: unreadable PartRef ({type(exc).__name__})"
        ) from exc


def _package_part_ids(package_id: str) -> list[str]:
    prefix = package_id + ":"
    integration_id = package_id + _INTEGRATION_SUFFIX
    known = set(_GATE_BY_PART) | set(_AUDIT_BY_PART)
    return sorted(
        part_id
        for part_id in known
        if (part_id == package_id or part_id.startswith(prefix))
        and part_id != integration_id
    )


def evaluate_phase_gate(package_ids: list[str]) -> dict:
    """Serve the phase-gate verdict (ROW87/95, frozen §3).

    The integration/link-check Manager serves its gate plus fresh audit under
    the part id "<package_id>:integration" via GateAuditLog; regular parts
    are the other served part ids for the package. The phase closes only
    after integration PASS: GATE_NOT_PASSED is raised for empty/bad input,
    for packages with no stored verdicts, for any non-PASS part, and for a
    non-PASS integration verdict; MISSING_INTEGRATION_TASK is raised when
    every regular part is PASS but no integration record is stored.
    Success returns the GateVerdict shape {package_id, gate, audit,
    decided_at, evidence_refs} with the integration refs as evidence (for
    several packages package_id is the sorted "+"-join).
    """
    try:
        ids = list(package_ids)
    except TypeError:
        raise GATE_NOT_PASSED(
            "GATE_NOT_PASSED: package_ids must be a non-empty list of ids"
        ) from None
    if not ids or any(
        not isinstance(item, str) or not item.strip() for item in ids
    ):
        raise GATE_NOT_PASSED(
            "GATE_NOT_PASSED: package_ids must be a non-empty list of ids"
        )
    evidence: list[str] = []
    for package_id in ids:
        integration_id = package_id + _INTEGRATION_SUFFIX
        parts = _package_part_ids(package_id)
        gate_entry = _GATE_BY_PART.get(integration_id)
        audit_entry = _AUDIT_BY_PART.get(integration_id)
        has_integration = gate_entry is not None or audit_entry is not None
        if not parts and not has_integration:
            raise GATE_NOT_PASSED(
                f"GATE_NOT_PASSED: no stored verdicts for package {package_id!r}"
            )
        for part_id in parts:
            gate_verdict = _GATE_BY_PART.get(part_id, (None, None))[1]
            audit_verdict = _AUDIT_BY_PART.get(part_id, (None, None))[1]
            ok, reason = can_close(gate_verdict, audit_verdict)
            if not ok:
                raise GATE_NOT_PASSED(
                    f"GATE_NOT_PASSED: part {part_id!r}: {reason}"
                )
        if not has_integration:
            raise MISSING_INTEGRATION_TASK(
                f"MISSING_INTEGRATION_TASK: parts of {package_id!r} are PASS "
                f"but no integration task {integration_id!r} is stored"
            )
        ok, reason = can_close(
            gate_entry[1] if gate_entry else None,
            audit_entry[1] if audit_entry else None,
        )
        if not ok:
            raise GATE_NOT_PASSED(
                f"GATE_NOT_PASSED: integration {integration_id!r}: {reason}"
            )
        evidence.append(gate_entry[0] if gate_entry else integration_id)
        evidence.append(audit_entry[0] if audit_entry else integration_id)
    return {
        "package_id": ids[0] if len(ids) == 1 else "+".join(sorted(ids)),
        "gate": GATE_PASS,
        "audit": AUDIT_PASS,
        "decided_at": utc_now(),
        "evidence_refs": evidence,
    }


def check_hierarchy_activation(chain: list[str]) -> None:
    """Validate a hierarchy activation chain without mutating anything.

    Valid shape: a list of at least three non-blank unique role/node ids
    ordered director -> manager -> tool agent(s), e.g. ["director-1",
    "manager-1", "tool-1"]. Anything else (non-list, empty, fewer than
    three entries, blank or non-string entries, duplicates) raises
    INVALID_HIERARCHY_CHAIN. The input list and every stored record are
    left untouched.
    """
    valid = (
        isinstance(chain, list)
        and len(chain) >= _MIN_CHAIN_LEN
        and all(isinstance(node, str) and node.strip() for node in chain)
        and len(set(chain)) == len(chain)
    )
    if not valid:
        raise INVALID_HIERARCHY_CHAIN(
            "INVALID_HIERARCHY_CHAIN: chain must be a list of >=3 non-blank "
            "unique ids (director + manager + tool)"
        )
    return
