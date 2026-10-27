"""TaskContract and ContractActivationRecord (Manifest sections 13, 15).

Frozen dataclasses: a committed instance is never rewritten. Requirement
changes, amendments, and corrections produce a NEW version with a NEW
contract_hash via replace_with_new_version(); the old instance is untouched.
The active contract derives ONLY from committed ContractActivationRecords
(highest activation_sequence per task_id), never from file order, timestamps,
or model memory. No mutation helpers are provided by this module.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Iterable, Optional, Tuple

try:
    from iface.frozen_manifest import manifest
except ImportError:  # alternate layout: the iface/ directory itself on sys.path
    from frozen_manifest import manifest


def _as_tuple(value: Any) -> Tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    return tuple(value)


@dataclass(frozen=True)
class TaskContract:
    """Manifest section 13 TaskContract. Immutable; hash-gated activation."""

    schema_version: str
    contract_version: int
    contract_sequence: int
    contract_hash: str = ""
    project_id: str = ""
    task_id: str = ""
    parent_task_id: Optional[str] = None
    supersedes_task_id: Optional[str] = None
    phase_id: Optional[str] = None
    created_at: str = ""
    created_by: str = ""
    priority: str = ""
    risk: manifest.RiskLevel = manifest.RiskLevel.MEDIUM
    goal: str = ""
    requirements: Tuple[str, ...] = ()
    acceptance_criteria: Tuple[str, ...] = ()
    inputs: Tuple[str, ...] = ()
    outputs: Tuple[str, ...] = ()
    workspace: str = ""
    permissions: str = ""
    tools: Tuple[str, ...] = ()
    verification_policy_ref: str = ""
    audit_policy_ref: str = ""
    routing_policy_ref: str = ""
    retry_policy_ref: str = ""
    fallback_policy_ref: str = ""
    optimization_policy_ref: str = ""
    override_policy_ref: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "requirements", _as_tuple(self.requirements))
        object.__setattr__(
            self, "acceptance_criteria", _as_tuple(self.acceptance_criteria)
        )
        object.__setattr__(self, "inputs", _as_tuple(self.inputs))
        object.__setattr__(self, "outputs", _as_tuple(self.outputs))
        object.__setattr__(self, "tools", _as_tuple(self.tools))
        if isinstance(self.risk, str) and not isinstance(
            self.risk, manifest.RiskLevel
        ):
            object.__setattr__(self, "risk", manifest.RiskLevel(self.risk))


@dataclass(frozen=True)
class ContractActivationRecord:
    """Manifest section 15 ContractActivationRecord. Immutable, authoritative."""

    activation_id: str = ""
    project_id: str = ""
    task_id: str = ""
    activation_sequence: int = 0
    contract_version: int = 0
    contract_sequence: int = 0
    contract_hash: str = ""
    activation_reason: str = ""
    activated_at: str = ""
    effective_from: manifest.EffectiveFrom = manifest.EffectiveFrom.IMMEDIATE
    previous_contract_hash: Optional[str] = None
    amendment_id: Optional[str] = None
    evidence_refs: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.effective_from, str) and not isinstance(
            self.effective_from, manifest.EffectiveFrom
        ):
            object.__setattr__(
                self,
                "effective_from",
                manifest.EffectiveFrom(self.effective_from),
            )
        object.__setattr__(self, "evidence_refs", _as_tuple(self.evidence_refs))


def _canonical(value: Any) -> Any:
    if isinstance(value, manifest.RiskLevel) or hasattr(value, "value"):
        enum_value = getattr(value, "value", value)
        if isinstance(enum_value, (str, int, float, bool)) or enum_value is None:
            return enum_value
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _canonical(value[key]) for key in sorted(value)}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(
        "contract_hash covers only JSON-canonical field values, got %r" % type(value)
    )


def compute_contract_hash(contract: Any) -> str:
    """sha256 over canonical field order (Manifest sections 12, 13).

    Field order is manifest.TASK_CONTRACT_FIELDS minus contract_hash itself
    (the hash covers content, never its own digest). Deterministic: same
    content always yields the same digest (one content, one hash).
    """
    payload: Dict[str, Any] = {}
    for name in manifest.TASK_CONTRACT_FIELDS:
        if name == "contract_hash":
            continue
        payload[name] = _canonical(getattr(contract, name))
    encoded = json.dumps(
        payload, sort_keys=False, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def activate(
    contract: TaskContract,
    *,
    activation_id: str,
    activation_sequence: int,
    activation_reason: str,
    effective_from: Any = manifest.EffectiveFrom.IMMEDIATE,
    amendment_id: Optional[str] = None,
    previous_contract_hash: Optional[str] = None,
    activated_at: str = "",
    evidence_refs: Iterable[str] = (),
) -> ContractActivationRecord:
    """Commit an activation binding a contract version as active (section 15)."""
    return ContractActivationRecord(
        activation_id=activation_id,
        project_id=contract.project_id,
        task_id=contract.task_id,
        activation_sequence=activation_sequence,
        contract_version=contract.contract_version,
        contract_sequence=contract.contract_sequence,
        contract_hash=contract.contract_hash,
        activation_reason=activation_reason,
        activated_at=activated_at,
        effective_from=effective_from,
        previous_contract_hash=previous_contract_hash,
        amendment_id=amendment_id,
        evidence_refs=tuple(evidence_refs or ()),
    )


def resolve_active(
    activations: Iterable[ContractActivationRecord],
) -> Optional[ContractActivationRecord]:
    """Return the active activation: highest activation_sequence (sections 13, 15).

    Returns None when there are no activations. Recovery resolves the active
    contract ONLY from committed activations.
    """
    best: Optional[ContractActivationRecord] = None
    for activation in activations:
        if best is None or activation.activation_sequence > best.activation_sequence:
            best = activation
    return best


def _bump(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(
            "%s must be supplied explicitly for non-integer versions" % field_name
        )
    return value + 1


def replace_with_new_version(old: TaskContract, **changes: Any) -> TaskContract:
    """Build a NEW contract version; *old* is never modified (sections 12, 13).

    contract_version/contract_sequence default to old+1 (or may be supplied
    explicitly in *changes*); contract_hash is always recomputed and can never
    be supplied. Returns the new frozen instance; the input keeps its original
    version, sequence, and hash.
    """
    if "contract_hash" in changes:
        raise ValueError("contract_hash is recomputed, never supplied")
    version = changes.pop(
        "contract_version", _bump(old.contract_version, "contract_version")
    )
    sequence = changes.pop(
        "contract_sequence", _bump(old.contract_sequence, "contract_sequence")
    )
    new = replace(old, contract_version=version, contract_sequence=sequence, **changes)
    return replace(new, contract_hash=compute_contract_hash(new))


__all__ = [
    "TaskContract",
    "ContractActivationRecord",
    "compute_contract_hash",
    "activate",
    "resolve_active",
    "replace_with_new_version",
]
