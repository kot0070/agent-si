"""Team card plus decomposition and config-decision records (lane B, coder B1).

Original code. Frozen shapes kept verbatim:
TeamCard {provider, model, model_kb_facts:dict, budget_left, limits};
DecisionRow {decision_id, scope, statement, reason, authority, created_at}.
Model id is exactly meta/muse-spark-1.3-contributor.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence  # noqa: UP035  # frozen-cite K02

try:
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
except ImportError:  # lane tests load this module by file path (no package)
    import importlib.util as _importlib_util
    import sys as _fallback_sys

    _common_name = "agent_si.backend.orchestration.common"
    _common_module = _fallback_sys.modules.get(_common_name)
    if _common_module is None:
        _common_spec: Any = _importlib_util.spec_from_file_location(
            _common_name,
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "common.py"),
        )
        _common_module = _importlib_util.module_from_spec(_common_spec)
        _fallback_sys.modules[_common_name] = _common_module
        _common_spec.loader.exec_module(_common_module)
    ApplyOutcome = _common_module.ApplyOutcome  # type: ignore[misc]
    DecisionLog = _common_module.DecisionLog  # type: ignore[misc]
    DecisionRow = _common_module.DecisionRow  # type: ignore[misc]
    ensure_compact_english = _common_module.ensure_compact_english
    hot_write_text = _common_module.hot_write_text
    is_compact_english = _common_module.is_compact_english
    surface_rejection = _common_module.surface_rejection
    utc_now = _common_module.utc_now

MODEL_ID = "meta/muse-spark-1.3-contributor"

FACT_PART_SIZE_VS_MODEL = "part-size-vs-model"
FACT_LONG_CONTEXT_ROUTING = "long-context-routing"
FACT_CHEAP_SMALL_PARTS = "cheap-models-for-small-parts"
KNOWN_FACTS = FACT_PART_SIZE_VS_MODEL, FACT_LONG_CONTEXT_ROUTING, FACT_CHEAP_SMALL_PARTS

SMALL_PART_THRESHOLD = 8
LONG_CONTEXT_THRESHOLD = 64

REGISTER_PRESERVED = "PRESERVED"
REGISTER_CHANGED = "CHANGED"
REGISTER_MISSING = "MISSING"
REGISTER_CONTRADICTED = "CONTRADICTED"


def make_secret_ref(name: str) -> dict[str, str]:
    return {"secret_ref": name}


@dataclass
class TeamCard:
    provider: str
    model: str
    model_kb_facts: dict[str, Any]
    budget_left: dict[str, Any]
    limits: dict[str, Any]

    def __post_init__(self) -> None:
        if self.model != MODEL_ID:
            raise ValueError(f"model id must stay {MODEL_ID}")
        if not isinstance(self.model_kb_facts, dict):
            raise ValueError("model_kb_facts must be a dict")


def build_team_card(
    provider: str,
    model_kb_facts: dict[str, Any],
    budget_left: dict[str, Any],
    limits: dict[str, Any],
    model: str = MODEL_ID,
    budget_secret: str | None = None,
) -> TeamCard:
    budget = dict(budget_left)
    if budget_secret is not None:
        budget["secret_ref"] = make_secret_ref("budget-store")
    return TeamCard(
        provider=provider,
        model=model,
        model_kb_facts=dict(model_kb_facts),
        budget_left=budget,
        limits=dict(limits),
    )


def director_context(
    manager_cards: Mapping[str, TeamCard],
    worker_cards: Mapping[str, Sequence[TeamCard]],
) -> dict[str, Any]:
    return {
        "managers": dict(manager_cards),
        "workers": {mid: list(cards) for mid, cards in worker_cards.items()},
    }


def manager_context(own_card: TeamCard, worker_cards: Sequence[TeamCard]) -> dict[str, Any]:  # noqa: E501  # frozen-cite K02
    return {"own": own_card, "workers": list(worker_cards)}


def worker_context() -> dict[str, Any]:
    return {}


@dataclass
class DecompositionRecord:
    record_id: str
    part_id: str
    facts_used: list[str]
    route: str
    reason: str
    artifact_ref: str


def record_decomposition(
    part_id: str, size_units: int, needs_long_context: bool = False
) -> DecompositionRecord:
    facts = [FACT_PART_SIZE_VS_MODEL]
    if needs_long_context or size_units > LONG_CONTEXT_THRESHOLD:
        facts.append(FACT_LONG_CONTEXT_ROUTING)
        route = "long-context"
        reason = ensure_compact_english(
            f"part {part_id} routes to long-context model "
            f"using facts {FACT_PART_SIZE_VS_MODEL} and {FACT_LONG_CONTEXT_ROUTING}"
        )
    elif size_units <= SMALL_PART_THRESHOLD:
        facts.append(FACT_CHEAP_SMALL_PARTS)
        route = "cheap-small-part"
        reason = ensure_compact_english(
            f"part {part_id} runs on a cheap model "
            f"using facts {FACT_PART_SIZE_VS_MODEL} and {FACT_CHEAP_SMALL_PARTS}"
        )
    else:
        route = "standard"
        reason = ensure_compact_english(
            f"part {part_id} keeps the standard model using fact {FACT_PART_SIZE_VS_MODEL}"  # noqa: E501  # frozen-cite K02
        )
    for fact in facts:
        if fact not in KNOWN_FACTS:
            raise ValueError(f"unknown model fact: {fact}")
    return DecompositionRecord(
        record_id=f"decomp-{part_id}",
        part_id=part_id,
        facts_used=facts,
        route=route,
        reason=reason,
        artifact_ref=f"ARTIFACT_REF:{part_id}/decomposition",
    )


DEFAULT_TEAM_CONFIG: dict[str, Any] = {
    "worker": "worker",
    "auditor": "auditor",
    "independent_audit": True,
    "model": MODEL_ID,
    "budget_left": 100,
    "agents": 0,
    "max_agents": 8,
    "peak_concurrency": 0,
    "max_concurrency": 4,
}


class TeamConfigStore:
    def __init__(
        self, config: Mapping[str, Any] | None = None, log: DecisionLog | None = None
    ) -> None:
        self.config: dict[str, Any] = dict(DEFAULT_TEAM_CONFIG)
        if config:
            self.config.update(config)
        self.log: DecisionLog = log if log is not None else DecisionLog()


def validate_team_config_change(patch: Mapping[str, Any], current: Mapping[str, Any]) -> tuple[bool, str]:  # noqa: E501  # frozen-cite K02
    merged = dict(current)
    cost = patch.get("cost", 0)
    try:
        cost_value = float(cost)
    except (TypeError, ValueError):
        return False, "cost must be numeric"
    if cost_value > float(merged.get("budget_left", 0)):
        return False, f"over budget: cost {cost_value} exceeds budget left"
    merged.update({key: value for key, value in patch.items() if key != "cost"})
    merged["budget_left"] = float(merged.get("budget_left", 0)) - cost_value
    if merged.get("model", MODEL_ID) != MODEL_ID:
        return False, f"model id must stay {MODEL_ID}"
    if merged.get("auditor") == merged.get("worker"):
        return False, "audit independence broken: auditor must differ from worker"
    if not merged.get("independent_audit"):
        return False, "audit independence broken: independent_audit must stay true"
    if int(merged.get("agents", 0)) > int(merged.get("max_agents", 0)):
        return False, "over cap: agents exceed max_agents"
    if int(merged.get("peak_concurrency", 0)) > int(merged.get("max_concurrency", 0)):
        return False, "over cap: peak concurrency exceeds max_concurrency"
    return True, "ok"


def apply_team_config_change(
    store: TeamConfigStore,
    statement: str,
    reason: str,
    authority: str,
    patch: Mapping[str, Any],
) -> ApplyOutcome:
    ok, check_reason = validate_team_config_change(patch, store.config)
    if not ok:
        outcome = ApplyOutcome(accepted=False, reason=check_reason)
        outcome.surfaced = surface_rejection(outcome)
        return outcome
    merged = dict(store.config)
    cost = float(patch.get("cost", 0))
    merged.update({key: value for key, value in patch.items() if key != "cost"})
    merged["budget_left"] = float(merged.get("budget_left", 0)) - cost
    store.config = merged
    row = store.log.append("team-config", statement, reason, authority, utc_now())
    outcome = ApplyOutcome(accepted=True, reason="applied", row=row)
    outcome.surfaced = surface_rejection(outcome)
    return outcome


@dataclass
class AuditModelChoice:
    part_id: str
    strength: str
    model: str
    reason: str


AUDIT_CHOICE_LOG: list[AuditModelChoice] = []


def select_audit_model(
    part_id: str, risk: str, log: list[AuditModelChoice] | None = None
) -> AuditModelChoice:
    target = log if log is not None else AUDIT_CHOICE_LOG
    if risk == "high":
        choice = AuditModelChoice(
            part_id=part_id,
            strength="strong",
            model=MODEL_ID,
            reason=ensure_compact_english(
                f"part {part_id} needs the stronger audit model for high risk"
            ),
        )
    else:
        choice = AuditModelChoice(
            part_id=part_id,
            strength="standard",
            model=MODEL_ID,
            reason=ensure_compact_english(
                f"part {part_id} keeps the standard audit model for low risk"
            ),
        )
    target.append(choice)
    return choice


def register_verbatim(
    entry_id: str,
    text: str,
    baseline: Mapping[str, str],
    negations: Mapping[str, str] | None = None,
) -> dict[str, str]:
    if entry_id not in baseline:
        return {"entry_id": entry_id, "status": REGISTER_MISSING, "detail": "no baseline entry"}  # noqa: E501  # frozen-cite K02
    if baseline[entry_id] == text:
        return {"entry_id": entry_id, "status": REGISTER_PRESERVED, "detail": "verbatim match"}  # noqa: E501  # frozen-cite K02
    if negations is not None and negations.get(entry_id) == text:
        return {"entry_id": entry_id, "status": REGISTER_CONTRADICTED, "detail": "negates baseline"}  # noqa: E501  # frozen-cite K02
    return {"entry_id": entry_id, "status": REGISTER_CHANGED, "detail": "text differs"}


@dataclass
class TeamReport:
    director: dict[str, Any] = field(default_factory=dict)
    managers: dict[str, Any] = field(default_factory=dict)
    decompositions: list[DecompositionRecord] = field(default_factory=list)
    audits: list[AuditModelChoice] = field(default_factory=list)
    register: list[dict[str, str]] = field(default_factory=list)


def build_team_report(
    manager_cards: Mapping[str, TeamCard],
    worker_cards: Mapping[str, Sequence[TeamCard]],
    part_specs: Sequence[Mapping[str, Any]],
    audit_risks: Mapping[str, str] | None = None,
    register_entries: Sequence[Mapping[str, str]] | None = None,
    register_baseline: Mapping[str, str] | None = None,
    out_path: str | None = None,
) -> TeamReport:
    risks = audit_risks or {}
    report = TeamReport()
    report.director = director_context(manager_cards, worker_cards)
    report.managers = {
        mid: manager_context(card, worker_cards.get(mid, []))
        for mid, card in manager_cards.items()
    }
    _ = worker_context()
    for spec in part_specs:
        part_id = str(spec["part_id"])
        report.decompositions.append(
            record_decomposition(
                part_id,
                int(spec.get("size_units", 0)),
                bool(spec.get("needs_long_context", False)),
            )
        )
        report.audits.append(select_audit_model(part_id, risks.get(part_id, "low")))
    baseline = register_baseline or {}
    for entry in register_entries or []:
        report.register.append(
            register_verbatim(str(entry["entry_id"]), str(entry["text"]), baseline)
        )
    if out_path is not None:
        lines = [
            f"{rec.record_id} {rec.route} {'+'.join(rec.facts_used)} {rec.artifact_ref}"
            for rec in report.decompositions
        ]
        hot_write_text(out_path, "\n".join(lines) + "\n")
    return report


# INT2 wiring: canonical kernel anchor, no behavior change
try:
    from agent_si.backend.orchestration import common as _int2_common
except ImportError:
    import importlib.util as _int2_util
    import sys as _int2_sys

    _int2_spec: Any = _int2_util.spec_from_file_location(
        "agent_si.backend.orchestration.common",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "common.py"),
    )
    _int2_common = _int2_util.module_from_spec(_int2_spec)
    _int2_sys.modules[_int2_spec.name] = _int2_common
    _int2_spec.loader.exec_module(_int2_common)
_INT2_KERNEL = (
    _int2_common.DecisionRow,
    _int2_common.DecisionLog,
    _int2_common.ApplyOutcome,
    _int2_common.AppliedOutcome,
    _int2_common.surface_rejection,
    _int2_common.utc_now,
    _int2_common.hot_write_text,
)
