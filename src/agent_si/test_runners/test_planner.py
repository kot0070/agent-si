"""K03 stage lane STEP2: test-plan derivation from catalog ids.

A plan records the catalog ids selected for one project run, with
per-kind counts that sum to the plan total, a priority order (CODE first,
then AI, HUMAN last since HUMAN steps need the permission ladder), and one
oracle ref per test. Empty selections are refused; ids outside the
catalog-id vocabulary are refused as unknown. Exact membership of a plan
in a caller-supplied catalog list is enforced by validate_plan_ids; the
catalog and overlay lanes own the id registry itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

#: Exact shipped-preset model id (never retyped, never a second id).
MODEL_ID = "meta/muse-spark-1.3-contributor"

#: Execution kinds; per-kind counts must sum to the plan total (catalog lane).
EXECUTION_KINDS = ("CODE", "AI", "HUMAN")

#: OC-K03 M-P3-120: the four built-in test bases shipped with the catalog,
#: plus their CODE/AI/HUMAN kinds in the same order. Mirrors
#: agent_si.test_runners.test_bases.BUILTIN_TEST_BASES so the planner can
#: construct kind-correct plans from bases without a second registry.
BUILTIN_TEST_BASES = (
    "base-code-fast",
    "base-code-full",
    "base-ai-judge",
    "base-human-operated",
)

#: Kind per built-in base, in the same order as BUILTIN_TEST_BASES.
BUILTIN_BASE_KINDS = ("CODE", "CODE", "AI", "HUMAN")

#: Frozen error-code names for this module (each pinned in its own test).
ERROR_CODES_PLANNER = (
    "UNKNOWN_TEST_ID",
    "EMPTY_TEST_PLAN",
)

#: Catalog-id vocabulary: the ``t-`` prefixed slug form owned by the
#: catalog lane (frozen catalog ids and user-overlay ids share it).
_CATALOG_ID_RE = re.compile(r"^t-[a-z0-9]+(?:-[a-z0-9]+)*$")

#: Priority rank per execution kind: automated first, HUMAN last.
_KIND_RANK = {"CODE": 0, "AI": 1, "HUMAN": 2}


class PlannerError(Exception):
    """Plan-derivation failure carrying the frozen ``.code`` name."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class TestPlan:
    plan_id: str
    project_id: str
    run_id: str
    test_ids: Tuple[str, ...]
    kind_counts: Dict[str, int]
    priority: Tuple[str, ...]
    oracle_refs: Tuple[str, ...]


@dataclass(frozen=True)
class PlanDerivation:
    plan_id: str
    project_id: str
    run_id: str
    catalog_ref: str
    derived_by_model: str


def _catalog_kinds() -> Dict[str, str]:
    """test_id -> kind from the frozen catalog; {} when unreachable."""
    try:
        from agent_si.qa_catalog.qa_catalog import get_catalog

        catalog = get_catalog("catalog-frozen-v1")
        return {test.test_id: test.kind for test in catalog.tests}
    except Exception:
        return {}


def _kind_for(test_id: str) -> str:
    """Execution kind for one catalog id from the catalog, not the id."""
    kind = _catalog_kinds().get(test_id)
    if kind in EXECUTION_KINDS:
        return kind
    lowered = test_id.lower()
    if "human" in lowered or "manual" in lowered:
        return "HUMAN"
    if "ai" in lowered or "judge" in lowered or "vision" in lowered:
        return "AI"
    return "CODE"


def derive_plan(
    catalog_ids: List[str],
    project_id: str,
    run_id: str,
    catalog_ref: str,
    derived_by_model: str,
) -> TestPlan:
    """Derive a plan from catalog ids only; raises UNKNOWN_TEST_ID otherwise."""
    if not catalog_ids:
        raise PlannerError(
            "EMPTY_TEST_PLAN",
            "no catalog ids selected for project %r" % project_id,
        )
    unknown = [
        test_id
        for test_id in catalog_ids
        if not isinstance(test_id, str) or not _CATALOG_ID_RE.match(test_id)
    ]
    if unknown:
        raise PlannerError(
            "UNKNOWN_TEST_ID",
            "test ids %r are not catalog ids" % (unknown,),
        )
    test_ids = tuple(catalog_ids)
    counts: Dict[str, int] = {}
    for test_id in test_ids:
        kind = _kind_for(test_id)
        counts[kind] = counts.get(kind, 0) + 1
    priority = tuple(
        sorted(test_ids, key=lambda test_id: _KIND_RANK[_kind_for(test_id)])
    )
    oracle_refs = tuple(
        "oracle://%s/%s" % (catalog_ref, test_id) for test_id in test_ids
    )
    return TestPlan(
        plan_id="plan-%s-%s" % (project_id, run_id),
        project_id=project_id,
        run_id=run_id,
        test_ids=test_ids,
        kind_counts=counts,
        priority=priority,
        oracle_refs=oracle_refs,
    )


def validate_plan_ids(plan: TestPlan, catalog_ids: List[str]) -> None:
    """Accept only plans whose ids all exist in the catalog; else raises."""
    known = set(catalog_ids)
    outside = [test_id for test_id in plan.test_ids if test_id not in known]
    if outside:
        raise PlannerError(
            "UNKNOWN_TEST_ID",
            "plan %r carries ids outside the catalog: %r"
            % (plan.plan_id, outside),
        )


def kind_total(plan: TestPlan) -> int:
    """Sum of per-kind counts; must equal len(plan.test_ids)."""
    return sum(plan.kind_counts.values())


def planner_bases() -> Tuple[Tuple[str, str], ...]:
    """Four built-in test bases with their CODE/AI/HUMAN kinds, in order."""
    return tuple(zip(BUILTIN_TEST_BASES, BUILTIN_BASE_KINDS))


def kind_for_base(base_id: str) -> str:
    """Kind for one built-in base id; unknown ids are refused."""
    for known_id, kind in zip(BUILTIN_TEST_BASES, BUILTIN_BASE_KINDS):
        if base_id == known_id:
            return kind
    raise PlannerError(
        "UNKNOWN_TEST_ID",
        "test base %r is not a built-in test base" % (base_id,),
    )


#: Entry points: logical name -> symbol in this module.
ENTRY_POINTS = {
    "derive_plan": "derive_plan",
    "validate_plan_ids": "validate_plan_ids",
    "kind_total": "kind_total",
    "planner_bases": "planner_bases",
    "kind_for_base": "kind_for_base",
}
