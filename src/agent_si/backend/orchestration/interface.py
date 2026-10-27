"""Orchestration package interface stub (v2; HD VERDICT C20 homes).

Types + signatures only; every function/method body is ``...`` (Ellipsis,
never raised). Every stub name traces to its HOME module (HD VERDICT C20):
common holds ApplyOutcome, DecisionLog, DecisionRow, utc_now,
surface_rejection, ensure_compact_english, is_compact_english,
hot_write_text (+ AppliedOutcome, the applied-form outcome shape);
ledger holds LedgerRow, PackageLedger, package_report,
build_package_report, persist_ledger, load_ledger; teamcard holds TeamCard;
graph holds HierarchyConfigStore; every other name traces to its defining
lane module among split/parts/gates/graph/overlap/manifest/delta/teamcard/
ledger/offload/steplimits/common:

- A home-canonical name is defined once under its own name carrying an
  ``ORIGIN: <home>`` comment.
- A name still defined in more than one module appears once per origin
  module as a module-qualified alias ``<module>_<name>`` carrying an
  ``ALIAS-OF: <module>.<name>`` comment (the home definition stays bare).
- Method sets, parameter names, kinds, defaults and return annotations
  mirror the home/lane code exactly. Dict-key shapes are recorded in
  docstrings.

Covers v2 (RECORDS/day1/K02_INTERFACE.md as changed by C1-C20): the C19
extras gates.serve_gate / serve_audit / GateAuditLog / has_fresh_audit
and graph.route_task / validate_dispatch / control_plane_map /
HierarchyConfigStore / TaskPlanner / SubtaskGraph / CycleError /
DependencyError; the C20 additive manifest/delta/parts/overlap names
(overlap.plan_managers and parts.PartStore.close_part EXCLUDED, v2 homes
split.fanout / gates.close_part hold).

MODEL_ID is exactly "meta/muse-spark-1.3-contributor" everywhere below.
Stdlib + typing imports only; no sibling-implementation imports; no
invented names.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, Sequence

# ---------------------------------------------------------------------------
# common.py (shared kernel; v2 home for the parts+delta duplicates)
# ---------------------------------------------------------------------------

def utc_now() -> str:  # ORIGIN: common
    ...


def is_compact_english(text: str) -> bool:  # ORIGIN: common
    ...


def ensure_compact_english(text: str) -> str:  # ORIGIN: common
    ...


def hot_write_text(path: str, text: str) -> str:  # ORIGIN: common
    ...


@dataclass
class DecisionRow:  # ORIGIN: common
    """common.DecisionRow {decision_id, scope, statement, reason, authority, created_at}."""

    decision_id: str
    scope: str
    statement: str
    reason: str
    authority: str
    created_at: str
    ...


class DecisionLog:  # ORIGIN: common
    """common.DecisionLog: UNIQUE(scope, sequence) ids (scope-%04d)."""

    rows: list[DecisionRow]

    def __init__(self, backing: list | None = None) -> None:
        ...

    def append(
        self, scope: str, statement: str, reason: str, authority: str, created_at: str
    ) -> DecisionRow:
        ...

    def __len__(self) -> int:
        ...

    def __iter__(self):  # type: ignore[no-untyped-def]
        ...

    def to_list(self) -> list:
        ...

    def next_id(self, scope: str) -> str:
        ...

    def add(self, scope: str, statement: str, reason: str, authority: str) -> dict:
        ...


@dataclass
class ApplyOutcome:  # ORIGIN: common
    """common.ApplyOutcome {accepted, reason, row, surfaced} (accepted-form)."""

    accepted: bool
    reason: str
    row: DecisionRow | None = None
    surfaced: str = ""
    ...


@dataclass
class AppliedOutcome:  # ORIGIN: common
    """common.AppliedOutcome {applied, reason, decision_ref} (applied-form)."""

    applied: bool
    reason: str
    decision_ref: str | None = None
    ...


def surface_rejection(outcome: ApplyOutcome | AppliedOutcome | str) -> str:  # ORIGIN: common
    ...


# ---------------------------------------------------------------------------
# split.py
# ---------------------------------------------------------------------------

split_MODEL_ID = "meta/muse-spark-1.3-contributor"  # ALIAS-OF: split.MODEL_ID

split_ARTIFACT_PREFIX = "artifact://"  # ALIAS-OF: split.ARTIFACT_PREFIX

split_ARTIFACT_REF_PREFIX = "ARTIFACT_REF:"  # ALIAS-OF: split.ARTIFACT_REF_PREFIX

SECRET_REF_KEY = "secret_ref"  # ORIGIN: split


class SCOPE_OVERLAP(Exception):  # ORIGIN: split
    ...


@dataclass(frozen=True)
class PartRef:  # ORIGIN: split
    """split.PartRef {package_id, contract_hash, gate_verdict_ref, audit_verdict_ref}."""

    package_id: str
    contract_hash: str
    gate_verdict_ref: str
    audit_verdict_ref: str
    ...


@dataclass
class MultiManagerSettings:  # ORIGIN: split
    """split.MultiManagerSettings; R-359 multi-manager settings shape."""

    multi_manager_mode: bool
    max_parallel_managers: int
    overlap: bool
    integration_policy: str
    model_pool_per_manager: dict = field(default_factory=dict)
    ...


def split_is_compact_english(text: str) -> bool:  # ALIAS-OF: split.is_compact_english
    ...


def split_ensure_compact_english(text: str) -> str:  # ALIAS-OF: split.ensure_compact_english
    ...


def split_make_secret_ref(name: str) -> dict[str, str]:  # ALIAS-OF: split.make_secret_ref
    ...


def is_shared_ref(value: object) -> bool:  # ORIGIN: split
    ...


def corrections_hash(corrections: Sequence[Mapping[str, Any]]) -> str:  # ORIGIN: split
    ...


def issued_corrections_hash(package_id: str) -> str | None:  # ORIGIN: split
    ...


def split_package(  # ORIGIN: split
    package_id: str,
    goal: str,
    context_refs: Sequence[str | Mapping[str, Any]],
    max_parts: int,
    corrections: Sequence[Mapping[str, Any]] = (),
    expected_corrections_hash: str | None = None,
) -> list[PartRef]:
    ...


def validate_disjoint(parts: list[PartRef]) -> None:  # ORIGIN: split
    ...


def fanout(  # ORIGIN: split
    parts: list[PartRef],
    settings: MultiManagerSettings,
) -> tuple[list[PartRef], list[PartRef]]:
    ...


@dataclass
class split_TeamCard:  # ALIAS-OF: split.TeamCard
    provider: str
    model: str
    model_kb_facts: dict[str, Any]
    budget_left: object
    limits: object
    ...


split_FACT_PART_SIZE_VS_MODEL = "part-size-vs-model"  # ALIAS-OF: split.FACT_PART_SIZE_VS_MODEL

split_FACT_LONG_CONTEXT_ROUTING = "long-context-routing"  # ALIAS-OF: split.FACT_LONG_CONTEXT_ROUTING

split_FACT_CHEAP_SMALL_PARTS = "cheap-models-for-small-parts"  # ALIAS-OF: split.FACT_CHEAP_SMALL_PARTS

split_KNOWN_FACTS = (  # ALIAS-OF: split.KNOWN_FACTS
    split_FACT_PART_SIZE_VS_MODEL,
    split_FACT_LONG_CONTEXT_ROUTING,
    split_FACT_CHEAP_SMALL_PARTS,
)

split_SMALL_PART_THRESHOLD = 8  # ALIAS-OF: split.SMALL_PART_THRESHOLD

split_LONG_CONTEXT_THRESHOLD = 64  # ALIAS-OF: split.LONG_CONTEXT_THRESHOLD


@dataclass
class split_DecompositionRecord:  # ALIAS-OF: split.DecompositionRecord
    record_id: str
    part_id: str
    facts_used: list[str]
    route: str
    reason: str
    artifact_ref: str
    ...


def split_record_decomposition(  # ALIAS-OF: split.record_decomposition
    part_id: str, size_units: int, needs_long_context: bool = False
) -> split_DecompositionRecord:
    ...


@dataclass
class QueueSlot:  # ORIGIN: split
    """split.QueueSlot {part, position, estimated_start_s}."""

    part: PartRef
    position: int
    estimated_start_s: float
    ...


def capped_queue(  # ORIGIN: split
    parts: Sequence[PartRef],
    settings: MultiManagerSettings,
    wall_time_s: float = 1.0,
) -> list[QueueSlot]:
    ...


def split_hot_write_text(path: str, text: str) -> str:  # ALIAS-OF: split.hot_write_text
    ...


def persist_decompositions(  # ORIGIN: split
    path: str, records: Sequence[split_DecompositionRecord]
) -> None:
    ...


def load_decompositions(path: str) -> list[split_DecompositionRecord]:  # ORIGIN: split
    ...


# ---------------------------------------------------------------------------
# parts.py
# ---------------------------------------------------------------------------

parts_MODEL_ID = "meta/muse-spark-1.3-contributor"  # ALIAS-OF: parts.MODEL_ID

parts_GATE_PASS = "PASS"  # ALIAS-OF: parts.GATE_PASS

parts_AUDIT_PASS = "PASS"  # ALIAS-OF: parts.AUDIT_PASS

parts_GATE_VERDICTS = frozenset({"PASS", "FAIL", "BLOCKED"})  # ALIAS-OF: parts.GATE_VERDICTS

parts_AUDIT_RESULTS = frozenset({"PASS", "REWORK", "BLOCKED", "ESCALATE", "FAIL"})  # ALIAS-OF: parts.AUDIT_RESULTS

parts_ARTIFACT_PREFIX = "artifact://"  # ALIAS-OF: parts.ARTIFACT_PREFIX

parts_ARTIFACT_REF_PREFIX = "ARTIFACT_REF:"  # ALIAS-OF: parts.ARTIFACT_REF_PREFIX


class parts_GateRefused(Exception):  # ALIAS-OF: parts.GateRefused
    ...


PartStatus = Literal[  # ORIGIN: parts
    "QUEUED", "RUNNING", "RETURNED", "ACCEPTED", "REJECTED", "BLOCKED", "HANDOFF",
]


@dataclass
class PartRow:  # ORIGIN: parts
    """parts.PartRow {agent, scope, deliverable, status}."""

    agent: str
    scope: str
    deliverable: str
    status: PartStatus = "QUEUED"  # type: ignore[assignment]
    ...


def register_part(row: PartRow) -> PartRow:  # ORIGIN: parts
    ...


def list_parts(status: PartStatus | None) -> list[PartRow]:  # ORIGIN: parts
    ...


def update_status(package_id: str, status: PartStatus) -> PartRow:  # ORIGIN: parts
    ...


@dataclass
class PartRecord:  # ORIGIN: parts
    """parts.PartRecord {part_id, package_id, contract_hash, agent, scope, deliverable_ref}."""

    part_id: str
    package_id: str
    contract_hash: str
    agent: str
    scope: str
    deliverable_ref: str
    ...


@dataclass(frozen=True)
class ClosedPartRef:  # ORIGIN: parts
    """parts.ClosedPartRef: frozen PartRef shape."""

    package_id: str
    contract_hash: str
    gate_verdict_ref: str
    audit_verdict_ref: str
    ...


class PartStore:  # ORIGIN: parts
    """parts.PartStore: served parts with GATE-RULE close."""

    def __init__(self) -> None:
        ...

    def register(self, record: PartRecord) -> PartRecord:
        ...

    def get(self, part_id: str) -> PartRecord | None:
        ...

    def record_gate_verdict(self, part_id: str, verdict: str, ref: str) -> str:
        ...

    def record_audit_verdict(self, part_id: str, result: str, ref: str) -> str:
        ...

    def gate_verdict(self, part_id: str) -> str | None:
        ...

    def audit_verdict(self, part_id: str) -> str | None:
        ...


# ---------------------------------------------------------------------------
# gates.py
# ---------------------------------------------------------------------------

def gates_utc_now() -> str:  # ALIAS-OF: gates.utc_now
    ...


gates_GATE_VERDICTS = frozenset({"PASS", "FAIL", "BLOCKED"})  # ALIAS-OF: gates.GATE_VERDICTS

gates_AUDIT_RESULTS = frozenset({"PASS", "REWORK", "BLOCKED", "ESCALATE", "FAIL"})  # ALIAS-OF: gates.AUDIT_RESULTS

gates_GATE_PASS = "PASS"  # ALIAS-OF: gates.GATE_PASS

gates_AUDIT_PASS = "PASS"  # ALIAS-OF: gates.AUDIT_PASS


class gates_GateRefused(Exception):  # ALIAS-OF: gates.GateRefused
    ...


class AuditRefused(Exception):  # ORIGIN: gates
    reason: str

    def __init__(self, reason: str) -> None:
        ...


class GATE_NOT_PASSED(gates_GateRefused):  # ORIGIN: gates
    ...


class MISSING_INTEGRATION_TASK(Exception):  # ORIGIN: gates
    ...


class INVALID_HIERARCHY_CHAIN(Exception):  # ORIGIN: gates
    ...


@dataclass
class GateRecord:  # ORIGIN: gates
    """gates.GateRecord {gate_id, part_id, verdict, created_at}."""

    gate_id: str
    part_id: str
    verdict: str
    created_at: str
    ...


@dataclass
class AuditRecord:  # ORIGIN: gates
    audit_id: str
    part_id: str
    result: str
    auditor_session_ref: str
    producer_session_refs: list[str] = field(default_factory=list)
    scope_id: str = ""
    audit_seq: int = 0
    context_integrity: bool = False
    created_at: str = ""
    ...


def gate_id_of(part_id: str, seq: int) -> str:  # ORIGIN: gates
    ...


def audit_id_of(part_id: str, seq: int) -> str:  # ORIGIN: gates
    ...


def audit_scope_id_of(part_id: str) -> str:  # ORIGIN: gates
    ...


def can_close(  # ORIGIN: gates
    gate_verdict: str | None, audit_verdict: str | None
) -> tuple[bool, str]:
    ...


class GateAuditLog:  # ORIGIN: gates
    """gates.GateAuditLog: served gate + fresh audit per part."""

    gate_history: dict[str, list[GateRecord]]
    audit_history: dict[str, list[AuditRecord]]

    def __init__(self) -> None:
        ...

    def serve_gate(self, part_id: str, verdict: str) -> GateRecord:
        ...

    def serve_audit(
        self,
        part_id: str,
        result: str,
        auditor_session_ref: str,
        producer_session_refs: list[str] | tuple[str, ...],
        context_integrity: bool,
    ) -> AuditRecord:
        ...

    def gate_verdict(self, part_id: str) -> str | None:
        ...

    def audit_verdict(self, part_id: str) -> str | None:
        ...

    def has_fresh_audit(self, part_id: str) -> bool:
        ...


def close_part(ref: object) -> dict:  # ORIGIN: gates
    """gates.close_part -> GateVerdict keys {package_id, gate, audit, decided_at, evidence_refs}."""
    ...


def evaluate_phase_gate(package_ids: list[str]) -> dict:  # ORIGIN: gates
    """gates.evaluate_phase_gate -> GateVerdict keys {package_id, gate, audit, decided_at, evidence_refs}."""
    ...


def check_hierarchy_activation(chain: list[str]) -> None:  # ORIGIN: gates
    ...


# ---------------------------------------------------------------------------
# graph.py
# ---------------------------------------------------------------------------

def graph_utc_now() -> str:  # ALIAS-OF: graph.utc_now
    ...


def graph_is_compact_english(text: str) -> bool:  # ALIAS-OF: graph.is_compact_english
    ...


def graph_ensure_compact_english(text: str) -> str:  # ALIAS-OF: graph.ensure_compact_english
    ...


@dataclass
class graph_DecisionRow:  # ALIAS-OF: graph.DecisionRow
    decision_id: str
    scope: str
    statement: str
    reason: str
    authority: str
    created_at: str
    ...


class graph_DecisionLog:  # ALIAS-OF: graph.DecisionLog
    rows: list[graph_DecisionRow]

    def __init__(self, backing: list | None = None) -> None:
        ...

    def append(
        self, scope: str, statement: str, reason: str, authority: str, created_at: str
    ) -> graph_DecisionRow:
        ...

    def __len__(self) -> int:
        ...

    def __iter__(self):  # type: ignore[no-untyped-def]
        ...

    def to_list(self) -> list:
        ...

    def next_id(self, scope: str) -> str:
        ...

    def add(self, scope: str, statement: str, reason: str, authority: str) -> dict:
        ...


@dataclass
class graph_ApplyOutcome:  # ALIAS-OF: graph.ApplyOutcome
    accepted: bool
    reason: str
    row: graph_DecisionRow | None = None
    surfaced: str = ""
    ...


RISK_LEVELS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")  # ORIGIN: graph

PLANNED = "PLANNED"  # ORIGIN: graph

graph_MODEL_ID = "meta/muse-spark-1.3-contributor"  # ALIAS-OF: graph.MODEL_ID

DIRECTOR_RUNTIME: None = None  # ORIGIN: graph

CONTROL_PLANE_MAP: dict[str, str] = {  # ORIGIN: graph
    "director.split": "split.split_package",
    "director.route": "graph.route_task",
    "director.policy": "graph.CONTROL_PLANE_MAP",
    "director.integrate": "graph.HierarchyConfigStore.close_parent",
    "director.decide": "teamcard.DecisionLog.append",
}


class CycleError(ValueError):  # ORIGIN: graph
    ...


class DependencyError(ValueError):  # ORIGIN: graph
    ...


class RoutingRefused(Exception):  # ORIGIN: graph
    reason: str

    def __init__(self, reason: str) -> None:
        ...


class DispatchRejected(Exception):  # ORIGIN: graph
    ...


class HierarchyRefused(Exception):  # ORIGIN: graph
    reason: str

    def __init__(self, reason: str) -> None:
        ...


class ParentClosureBlocked(Exception):  # ORIGIN: graph
    ...


class DirectorControlOnly(Exception):  # ORIGIN: graph
    ...


@dataclass
class PlannedSubtask:  # ORIGIN: graph
    subtask_id: str
    plan_ref: str
    goal: str
    task_class: str
    risk: str
    required_capabilities: list[str] = field(default_factory=list)
    knowledge_needs: list[str] = field(default_factory=list)
    tool_needs: list[str] = field(default_factory=list)
    acceptance_criteria_refs: list[str] = field(default_factory=list)
    dependency_ids: list[str] = field(default_factory=list)
    status: str = PLANNED
    ...


@dataclass
class RunConfig:  # ORIGIN: graph
    client_max_retries: int = 0
    retry_policy_ref: str = "retry:default"
    ...


@dataclass
class RoutingDecision:  # ORIGIN: graph
    decision_id: str
    subtask_id: str
    worker_class: str
    execution_type: str
    required_capabilities: list[str] = field(default_factory=list)
    tool_needs: list[str] = field(default_factory=list)
    knowledge_needs: list[str] = field(default_factory=list)
    constraints: str = ""
    retry_policy_ref: str = "retry:default"
    run_config: RunConfig = field(default_factory=RunConfig)
    subordinate_to: str = ""
    ...


@dataclass
class AgentTask:  # ORIGIN: graph
    agent_task_id: str
    subtask_id: str
    agent_id: str
    contract_hash: str
    status: str = "ACTIVE"
    ...


@dataclass
class HierarchyChain:  # ORIGIN: graph
    director_id: str
    manager_id: str
    tool_agent_ids: list[str] = field(default_factory=list)
    ...


@dataclass
class TeamSizing:  # ORIGIN: graph
    block_id: str
    members: int
    roles: list[str] = field(default_factory=list)
    why: str = ""
    ...


class SubtaskGraph:  # ORIGIN: graph
    """graph.SubtaskGraph: planned subtasks keyed by subtask_id."""

    nodes: dict[str, PlannedSubtask]

    def __init__(self) -> None:
        ...

    def add(self, node: PlannedSubtask) -> None:
        ...

    def validate(self) -> None:
        ...

    def order(self) -> list[str]:
        ...


class TaskPlanner:  # ORIGIN: graph
    """graph.TaskPlanner: builds the subtask graph, never picks provider/model."""

    def __init__(self) -> None:
        ...

    def plan(
        self,
        package_id: str,
        goal: str,
        specs: Sequence[Mapping[str, Any]],
    ) -> tuple[str, SubtaskGraph]:
        ...

    def clear(self) -> None:
        ...


def route_task(  # ORIGIN: graph
    subtask: PlannedSubtask,
    worker_class: str,
    execution_type: str,
    required_capabilities: Sequence[str] = (),
    tool_needs: Sequence[str] = (),
    knowledge_needs: Sequence[str] = (),
    constraints: str = "",
    retry_policy_ref: str = "retry:default",
    manager_id: str = "",
) -> RoutingDecision:
    ...


def validate_dispatch(  # ORIGIN: graph
    agent_task: Mapping[str, Any] | AgentTask, graph: SubtaskGraph
) -> AgentTask:
    ...


def build_graph(  # ORIGIN: graph
    parts: list[str], deps: list[tuple[str, str]]
) -> dict[str, list[str]]:
    ...


def ready_parts(  # ORIGIN: graph
    graph: dict[str, list[str]], completed: set[str]
) -> list[str]:
    ...


def mark_completed(  # ORIGIN: graph
    graph: dict[str, list[str]], completed: set[str], part: str
) -> set[str]:
    ...


def control_plane_map() -> dict[str, str]:  # ORIGIN: graph
    ...


def require_explicit_director(ref: str | None) -> str:  # ORIGIN: graph
    ...


def stage_rows_to_hierarchy(  # ORIGIN: graph
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    ...


class HierarchyConfigStore:  # ORIGIN: graph
    """graph.HierarchyConfigStore: stored-config gate + hierarchy chain + team sizing."""

    config: dict[str, Any]
    log: graph_DecisionLog

    def __init__(
        self, config: Mapping[str, Any] | None = None, log: graph_DecisionLog | None = None
    ) -> None:
        ...

    def activate_chain(self, chain: HierarchyChain, actor: str) -> graph_ApplyOutcome:
        ...

    def append_user_correction(self, actor: str, text: str) -> graph_ApplyOutcome:
        ...

    def grant_role_authority(
        self, role: str, binding: Mapping[str, Any], actor: str
    ) -> graph_ApplyOutcome:
        ...

    def close_parent(
        self,
        part_results: Mapping[str, str],
        integration_record: Mapping[str, Any] | None,
    ) -> dict[str, str]:
        ...

    def size_team(
        self,
        block_id: str,
        subtask_count: int,
        risk: str,
        actor: str,
    ) -> TeamSizing:
        ...


# ---------------------------------------------------------------------------
# overlap.py
# ---------------------------------------------------------------------------

overlap_MODEL_ID = "meta/muse-spark-1.3-contributor"  # ALIAS-OF: overlap.MODEL_ID


def may_start_early(ref: dict) -> bool:  # ORIGIN: overlap
    ...


def early_start_allowed(  # ORIGIN: overlap
    ref: dict, overlap: Any = True, settings: Any = None
) -> bool:
    ...


def validate_multi_manager_settings(settings: Any) -> tuple[bool, str]:  # ORIGIN: overlap
    ...


# ---------------------------------------------------------------------------
# manifest.py
# ---------------------------------------------------------------------------

def frozen_hash(manifest: dict) -> str:  # ORIGIN: manifest
    ...


def check_part_manifest(ref: dict, manifest: dict) -> bool:  # ORIGIN: manifest
    ...


class ManifestRec:  # ORIGIN: manifest
    """manifest.ManifestRec {manifest_id, version, parts, hash, hash_algorithm}."""

    def __init__(
        self,
        manifest_id: str,
        version: int,
        parts: list,
        hash: str = "",
        hash_algorithm: str = "sha256",
    ) -> None:
        ...

    def to_dict(self) -> dict:
        ...

    @classmethod
    def from_dict(cls, data: dict) -> ManifestRec:
        ...


def canonical_manifest_bytes(  # ORIGIN: manifest
    manifest_id: str, version: int, parts: list
) -> bytes:
    ...


def manifest_hash(manifest: dict) -> str:  # ORIGIN: manifest
    ...


def build_manifest(manifest_id: str, version: int, parts: list) -> dict:  # ORIGIN: manifest
    ...


def verify_manifest_hash(manifest: dict) -> bool:  # ORIGIN: manifest
    ...


def validate_part_ref(ref: dict, manifest: dict) -> bool:  # ORIGIN: manifest
    ...


def check_manifest(manifest: dict, refs: list | None = None) -> bool:  # ORIGIN: manifest
    ...


def save_manifest(manifest: dict, path: str) -> str:  # ORIGIN: manifest
    ...


def load_manifest(path: str) -> dict:  # ORIGIN: manifest
    ...


# ---------------------------------------------------------------------------
# delta.py
# ---------------------------------------------------------------------------

delta_MODEL_ID = "meta/muse-spark-1.3-contributor"  # ALIAS-OF: delta.MODEL_ID


class DELTA_OVER_BOUND(Exception):  # ORIGIN: delta
    ...


def delta_intake_bounded_delta(  # ALIAS-OF: delta.intake_bounded_delta
    scope: list[str], blocking: bool
) -> dict:
    """delta.intake_bounded_delta -> DeltaPackage keys {delta_id, scope, blocking, keep, patch, created_at}."""
    ...


def cross_check(  # ORIGIN: delta
    open_packages: list[str], gates: list[dict]
) -> list[str]:
    ...


def close_with_linkcheck(delta: dict, verdict: dict) -> dict:  # ORIGIN: delta
    """delta.close_with_linkcheck(delta: DeltaPackage, verdict: GateVerdict) -> GateVerdict."""
    ...


def validate_config_change(  # ORIGIN: delta
    patch: dict, current: dict
) -> tuple[bool, str]:
    ...


def apply_config_change(  # ORIGIN: delta
    config: dict,
    log: list,
    scope: str,
    statement: str,
    reason: str,
    authority: str,
    patch: dict,
) -> dict:
    ...


class delta_HierarchyConfigStore:  # ALIAS-OF: delta.HierarchyConfigStore
    """delta.HierarchyConfigStore: re-export of graph.HierarchyConfigStore; stored-config gate + hierarchy chain + team sizing."""

    config: dict[str, Any]
    log: graph_DecisionLog

    def __init__(
        self, config: Mapping[str, Any] | None = None, log: graph_DecisionLog | None = None
    ) -> None:
        ...

    def activate_chain(self, chain: HierarchyChain, actor: str) -> graph_ApplyOutcome:
        ...

    def append_user_correction(self, actor: str, text: str) -> graph_ApplyOutcome:
        ...

    def grant_role_authority(
        self, role: str, binding: Mapping[str, Any], actor: str
    ) -> graph_ApplyOutcome:
        ...

    def close_parent(
        self,
        part_results: Mapping[str, str],
        integration_record: Mapping[str, Any] | None,
    ) -> dict[str, str]:
        ...

    def size_team(
        self,
        block_id: str,
        subtask_count: int,
        risk: str,
        actor: str,
    ) -> TeamSizing:
        ...


def validate_stored_config(  # ORIGIN: delta
    store: delta_HierarchyConfigStore, patch: dict
) -> tuple[bool, str]:
    ...


def apply_stored_config(  # ORIGIN: delta
    store: delta_HierarchyConfigStore,
    scope: str,
    statement: str,
    reason: str,
    authority: str,
    patch: dict,
) -> dict:
    ...


def activate_hierarchy_chain(  # ORIGIN: delta
    config: dict, log: list, chain: list, authority: str = "director"
) -> dict:
    ...


# ---------------------------------------------------------------------------
# teamcard.py
# ---------------------------------------------------------------------------

teamcard_MODEL_ID = "meta/muse-spark-1.3-contributor"  # ALIAS-OF: teamcard.MODEL_ID

teamcard_FACT_PART_SIZE_VS_MODEL = "part-size-vs-model"  # ALIAS-OF: teamcard.FACT_PART_SIZE_VS_MODEL

teamcard_FACT_LONG_CONTEXT_ROUTING = "long-context-routing"  # ALIAS-OF: teamcard.FACT_LONG_CONTEXT_ROUTING

teamcard_FACT_CHEAP_SMALL_PARTS = "cheap-models-for-small-parts"  # ALIAS-OF: teamcard.FACT_CHEAP_SMALL_PARTS

teamcard_KNOWN_FACTS = (  # ALIAS-OF: teamcard.KNOWN_FACTS
    teamcard_FACT_PART_SIZE_VS_MODEL,
    teamcard_FACT_LONG_CONTEXT_ROUTING,
    teamcard_FACT_CHEAP_SMALL_PARTS,
)

teamcard_SMALL_PART_THRESHOLD = 8  # ALIAS-OF: teamcard.SMALL_PART_THRESHOLD

teamcard_LONG_CONTEXT_THRESHOLD = 64  # ALIAS-OF: teamcard.LONG_CONTEXT_THRESHOLD

teamcard_REGISTER_PRESERVED = "PRESERVED"  # ALIAS-OF: teamcard.REGISTER_PRESERVED

teamcard_REGISTER_CHANGED = "CHANGED"  # ALIAS-OF: teamcard.REGISTER_CHANGED

teamcard_REGISTER_MISSING = "MISSING"  # ALIAS-OF: teamcard.REGISTER_MISSING

teamcard_REGISTER_CONTRADICTED = "CONTRADICTED"  # ALIAS-OF: teamcard.REGISTER_CONTRADICTED


def teamcard_make_secret_ref(name: str) -> dict[str, str]:  # ALIAS-OF: teamcard.make_secret_ref
    ...


@dataclass
class TeamCard:  # ORIGIN: teamcard
    """teamcard.TeamCard {provider, model, model_kb_facts, budget_left, limits}."""

    provider: str
    model: str
    model_kb_facts: dict[str, Any]
    budget_left: dict[str, Any]
    limits: dict[str, Any]
    ...


def build_team_card(  # ORIGIN: teamcard
    provider: str,
    model_kb_facts: dict[str, Any],
    budget_left: dict[str, Any],
    limits: dict[str, Any],
    model: str = teamcard_MODEL_ID,
    budget_secret: str | None = None,
) -> TeamCard:
    ...


def director_context(  # ORIGIN: teamcard
    manager_cards: Mapping[str, TeamCard],
    worker_cards: Mapping[str, Sequence[TeamCard]],
) -> dict[str, Any]:
    ...


def manager_context(  # ORIGIN: teamcard
    own_card: TeamCard, worker_cards: Sequence[TeamCard]
) -> dict[str, Any]:
    ...


def worker_context() -> dict[str, Any]:  # ORIGIN: teamcard
    ...


@dataclass
class teamcard_DecompositionRecord:  # ALIAS-OF: teamcard.DecompositionRecord
    record_id: str
    part_id: str
    facts_used: list[str]
    route: str
    reason: str
    artifact_ref: str
    ...


def teamcard_record_decomposition(  # ALIAS-OF: teamcard.record_decomposition
    part_id: str, size_units: int, needs_long_context: bool = False
) -> teamcard_DecompositionRecord:
    ...


DEFAULT_TEAM_CONFIG: dict[str, Any] = {  # ORIGIN: teamcard
    "worker": "worker",
    "auditor": "auditor",
    "independent_audit": True,
    "model": teamcard_MODEL_ID,
    "budget_left": 100,
    "agents": 0,
    "max_agents": 8,
    "peak_concurrency": 0,
    "max_concurrency": 4,
}


class TeamConfigStore:  # ORIGIN: teamcard
    """teamcard.TeamConfigStore: validated team config + decision log."""

    config: dict[str, Any]
    log: DecisionLog

    def __init__(
        self, config: Mapping[str, Any] | None = None, log: DecisionLog | None = None
    ) -> None:
        ...


def validate_team_config_change(  # ORIGIN: teamcard
    patch: Mapping[str, Any], current: Mapping[str, Any]
) -> tuple[bool, str]:
    ...


def apply_team_config_change(  # ORIGIN: teamcard
    store: TeamConfigStore,
    statement: str,
    reason: str,
    authority: str,
    patch: Mapping[str, Any],
) -> ApplyOutcome:
    ...


@dataclass
class AuditModelChoice:  # ORIGIN: teamcard
    """teamcard.AuditModelChoice {part_id, strength, model, reason}."""

    part_id: str
    strength: str
    model: str
    reason: str
    ...


AUDIT_CHOICE_LOG: list[AuditModelChoice] = []  # ORIGIN: teamcard


def select_audit_model(  # ORIGIN: teamcard
    part_id: str, risk: str, log: list[AuditModelChoice] | None = None
) -> AuditModelChoice:
    ...


def register_verbatim(  # ORIGIN: teamcard
    entry_id: str,
    text: str,
    baseline: Mapping[str, str],
    negations: Mapping[str, str] | None = None,
) -> dict[str, str]:
    ...


@dataclass
class TeamReport:  # ORIGIN: teamcard
    director: dict[str, Any] = field(default_factory=dict)
    managers: dict[str, Any] = field(default_factory=dict)
    decompositions: list[teamcard_DecompositionRecord] = field(default_factory=list)
    audits: list[AuditModelChoice] = field(default_factory=list)
    register: list[dict[str, str]] = field(default_factory=list)
    ...


def build_team_report(  # ORIGIN: teamcard
    manager_cards: Mapping[str, TeamCard],
    worker_cards: Mapping[str, Sequence[TeamCard]],
    part_specs: Sequence[Mapping[str, Any]],
    audit_risks: Mapping[str, str] | None = None,
    register_entries: Sequence[Mapping[str, str]] | None = None,
    register_baseline: Mapping[str, str] | None = None,
    out_path: str | None = None,
) -> TeamReport:
    ...


# ---------------------------------------------------------------------------
# ledger.py
# ---------------------------------------------------------------------------

ledger_REGISTER_PRESERVED = "PRESERVED"  # ALIAS-OF: ledger.REGISTER_PRESERVED

ledger_REGISTER_CHANGED = "CHANGED"  # ALIAS-OF: ledger.REGISTER_CHANGED

ledger_REGISTER_MISSING = "MISSING"  # ALIAS-OF: ledger.REGISTER_MISSING

ledger_REGISTER_CONTRADICTED = "CONTRADICTED"  # ALIAS-OF: ledger.REGISTER_CONTRADICTED


@dataclass
class LedgerRow:  # ORIGIN: ledger
    """ledger.LedgerRow {package_id, agents, peak_concurrency, wall_time_s}."""

    package_id: str
    agents: int
    peak_concurrency: int
    wall_time_s: float
    ...


class PackageLedger:  # ORIGIN: ledger
    """ledger.PackageLedger: served per-package load rows."""

    def __init__(self) -> None:
        ...

    def record_row(
        self, package_id: str, agents: int, peak_concurrency: int, wall_time_s: float
    ) -> LedgerRow:
        ...

    def get_row(self, package_id: str) -> LedgerRow | None:
        ...

    def package_ids(self) -> list[str]:
        ...


def package_report(  # ORIGIN: ledger
    ledger: PackageLedger, package_id: str, next_package_id: str | None = None
) -> dict[str, Any]:
    """ledger.package_report -> {row: {package_id, agents, peak_concurrency, wall_time_s}, nudge, auto_push: false}."""
    ...


DEFAULT_LEDGER_CONFIG: dict[str, Any] = {  # ORIGIN: ledger
    "independent_audit": True,
    "budget_left": 100,
    "agents": 0,
    "max_agents": 8,
    "peak_concurrency": 0,
    "max_concurrency": 4,
}


class LedgerConfigStore:  # ORIGIN: ledger
    """ledger.LedgerConfigStore: validated ledger config + decision log."""

    config: dict[str, Any]
    log: DecisionLog

    def __init__(
        self, config: Mapping[str, Any] | None = None, log: DecisionLog | None = None
    ) -> None:
        ...


def validate_ledger_config_change(  # ORIGIN: ledger
    patch: Mapping[str, Any], current: Mapping[str, Any]
) -> tuple[bool, str]:
    ...


def apply_ledger_config_change(  # ORIGIN: ledger
    store: LedgerConfigStore,
    statement: str,
    reason: str,
    authority: str,
    patch: Mapping[str, Any],
) -> ApplyOutcome:
    ...


def ledger_intake_bounded_delta(  # ALIAS-OF: ledger.intake_bounded_delta
    taken: list[dict[str, Any]], delta: Mapping[str, Any], bound: int
) -> dict[str, Any]:
    """ledger.intake_bounded_delta -> {accepted, reason, delta_id} (never raises)."""
    ...


def persist_ledger(path: str, ledger: PackageLedger) -> None:  # ORIGIN: ledger
    ...


def load_ledger(path: str) -> PackageLedger:  # ORIGIN: ledger
    ...


def build_package_report(  # ORIGIN: ledger
    ledger: PackageLedger,
    ordered_ids: list[str],
    out_path: str | None = None,
) -> list[dict[str, Any]]:
    """ledger.build_package_report -> list of {row, nudge, auto_push} package reports."""
    ...


@dataclass
class LedgerReport:  # ORIGIN: ledger
    """ledger.LedgerReport {packages}."""

    packages: list[dict[str, Any]] = field(default_factory=list)
    ...


def build_ledger_report(  # ORIGIN: ledger
    ledger: PackageLedger,
    ordered_ids: Sequence[str],
    out_path: str | None = None,
) -> LedgerReport:
    ...


# ---------------------------------------------------------------------------
# offload.py
# ---------------------------------------------------------------------------

offload_AUDIT_INDEPENDENCE_REJECTED = "AUDIT_INDEPENDENCE_REJECTED"  # ALIAS-OF: offload.AUDIT_INDEPENDENCE_REJECTED

offload_BUDGET_CAPPED = "BUDGET_CAPPED"  # ALIAS-OF: offload.BUDGET_CAPPED

offload_POLICY_CONFLICT = "POLICY_CONFLICT"  # ALIAS-OF: offload.POLICY_CONFLICT

REJECTED_SCOPE_OVERLAP = "REJECTED_SCOPE_OVERLAP"  # ORIGIN: offload


@dataclass
class offload_DecisionRow:  # ALIAS-OF: offload.DecisionRow
    decision_id: str
    scope: str
    statement: str
    reason: str
    authority: str
    created_at: str
    ...


@dataclass
class HandoverRecord:  # ORIGIN: offload
    """offload.HandoverRecord {task_id, from_role, to_role, reason, created_at}."""

    task_id: str
    from_role: str
    to_role: str
    reason: str
    created_at: str
    ...


@dataclass
class offload_ApplyOutcome:  # ALIAS-OF: offload.ApplyOutcome
    applied: bool
    reason: str
    decision_ref: str | None = None
    ...


def offload_enabled(project_id: str, role: str) -> bool:  # ORIGIN: offload
    ...


def maybe_offload(  # ORIGIN: offload
    task_id: str, role: str, routine: bool
) -> HandoverRecord | None:
    ...


def apply_offload_config_change(change: dict) -> offload_ApplyOutcome:  # ORIGIN: offload
    ...


# ---------------------------------------------------------------------------
# steplimits.py
# ---------------------------------------------------------------------------

TASK_KIND = "task"  # ORIGIN: steplimits

CHAT_KIND = "chat"  # ORIGIN: steplimits

STEPLIMIT_SCOPE_PREFIX = "steplimits:"  # ORIGIN: steplimits

STEP_LIMIT_MIN = 1  # ORIGIN: steplimits

STEP_LIMIT_CAP = 10_000  # ORIGIN: steplimits

steplimits_AUDIT_INDEPENDENCE_REJECTED = "AUDIT_INDEPENDENCE_REJECTED"  # ALIAS-OF: steplimits.AUDIT_INDEPENDENCE_REJECTED

steplimits_BUDGET_CAPPED = "BUDGET_CAPPED"  # ALIAS-OF: steplimits.BUDGET_CAPPED

steplimits_POLICY_CONFLICT = "POLICY_CONFLICT"  # ALIAS-OF: steplimits.POLICY_CONFLICT


class UnknownLimitKindError(Exception):  # ORIGIN: steplimits
    reason: str

    def __init__(self, reason: str) -> None:
        ...


UNKNOWN_LIMIT_KIND = UnknownLimitKindError  # ORIGIN: steplimits


@dataclass
class StepLimits:  # ORIGIN: steplimits
    """steplimits.StepLimits {task_max_steps, chat_max_steps}."""

    task_max_steps: int
    chat_max_steps: int
    ...


@dataclass
class steplimits_ApplyOutcome:  # ALIAS-OF: steplimits.ApplyOutcome
    applied: bool
    reason: str
    decision_ref: str | None = None
    ...


def limits_for(  # ORIGIN: steplimits
    kind: str, project_id: str | None = None
) -> int:
    ...


def apply_steplimit_config_change(change: dict) -> steplimits_ApplyOutcome:  # ORIGIN: steplimits
    ...
