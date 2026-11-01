"""K05 M3 STEP2 implementation: bench suite defs (frozen slices, seeded, fail-closed).

Case ids and prompt refs are frozen metadata; owner-original prompt
content stays read-only elsewhere and is never copied here. Standard
library only.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from agent_si.local.bench_protocol import BenchLevel


@dataclass
class BenchCase:
    case_id: str
    level: BenchLevel
    prompt_ref: str
    frozen: bool


#: Frozen seeded suite slices per level (ids + metadata refs only).
_SUITE_SLICES: dict[BenchLevel, tuple[str, ...]] = {
    BenchLevel.Quick: ("q01", "q02", "q03", "q04", "q05", "q06"),
    BenchLevel.Standard: (
        "s01",
        "s02",
        "s03",
        "s04",
        "s05",
        "s06",
        "s07",
        "s08",
        "s09",
        "s10",
        "s11",
        "s12",
    ),
    BenchLevel.Deep: (
        "d01",
        "d02",
        "d03",
        "d04",
        "d05",
        "d06",
        "d07",
        "d08",
        "d09",
        "d10",
        "d11",
        "d12",
        "d13",
        "d14",
        "d15",
        "d16",
        "d17",
        "d18",
        "d19",
        "d20",
        "d21",
        "d22",
        "d23",
        "d24",
    ),
}

#: Suite version carried by every prompt ref.
_SUITE_VERSION = "bench-suite-v1"


def _make_case(case_id: str, level: BenchLevel) -> BenchCase:
    return BenchCase(
        case_id=case_id,
        level=level,
        prompt_ref=f"{_SUITE_VERSION}:{case_id}",
        frozen=True,
    )


def list_cases(level: BenchLevel) -> list[BenchCase]:
    """Full frozen slice for a level (seeded order, all frozen)."""
    lvl = BenchLevel(level)
    return [_make_case(case_id, lvl) for case_id in _SUITE_SLICES[lvl]]


def select_cases(level: BenchLevel, model_params_b: float) -> list[BenchCase]:
    """Size-scaled subset of the frozen slice (8B+ runs the whole slice).

    Smaller models run a leading prefix of the slice; the slice order is
    seeded so the prefix is deterministic. Unknown/non-positive sizes run
    the whole slice (fail-closed: never select zero cases).
    """
    full = list_cases(level)
    try:
        params = float(model_params_b)
    except (TypeError, ValueError):
        return full
    if params <= 0:
        return full
    count = round(len(full) * min(params / 8.0, 1.0))
    return full[: max(1, count)]


def validate_case(case: BenchCase) -> None:
    """Fail-closed validation: valid frozen cases return None, else raise."""
    if not isinstance(case, BenchCase):
        raise ValueError(f"not a BenchCase: {case!r}")
    if not isinstance(case.case_id, str) or not case.case_id:
        raise ValueError(f"case_id must be a non-empty string, got {case.case_id!r}")
    if any(ch.isspace() or ch in "/\\" for ch in case.case_id):
        raise ValueError(f"case_id must be a plain id, got {case.case_id!r}")
    BenchLevel(case.level)
    if not isinstance(case.prompt_ref, str) or not case.prompt_ref:
        raise ValueError(f"prompt_ref must be a non-empty string, got {case.prompt_ref!r}")
    if case.frozen is not True:
        raise ValueError(f"only frozen suite cases validate, got frozen={case.frozen!r}")
    return None


def suite_manifest_hash(cases: list[BenchCase]) -> str:
    """Stable sha256 over the sorted suite slice (ids + level + ref + flag)."""
    lines = sorted(
        f"{case.case_id}|{BenchLevel(case.level).value}|{case.prompt_ref}|{int(case.frozen is True)}"
        for case in cases
    )
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class QuickCaseSpec:
    """Frozen F10 executor material for one Quick case (new F10 content).

    prompt is the exact text the background executor sends; rule is the
    expected-answer rule the reply is scored against; expected is the
    canonical passing reply. These prompts are new F10 material, not
    owner-original content.
    """

    case_id: str
    prompt: str
    rule: str
    expected: str


#: Frozen F10 Quick prompts + expected-answer rules (q01-q06, one category
#: each: exact arithmetic; valid JSON with given keys; one-word reply;
#: capital of a country; reversed string; sorted numbers).
_QUICK_CASE_SPECS: dict[str, QuickCaseSpec] = {
    "q01": QuickCaseSpec(
        case_id="q01",
        prompt="What is 17 + 25? Reply with only the number.",
        rule="exact:42",
        expected="42",
    ),
    "q02": QuickCaseSpec(
        case_id="q02",
        prompt="Reply with only a valid JSON object containing the keys "
        '"name" and "score".',
        rule="json-keys:name,score",
        expected='{"name": "ada", "score": 1}',
    ),
    "q03": QuickCaseSpec(
        case_id="q03",
        prompt='Reply with exactly one word: lantern',
        rule="one-word:lantern",
        expected="lantern",
    ),
    "q04": QuickCaseSpec(
        case_id="q04",
        prompt="What is the capital of France? Reply with only the city name.",
        rule="exact-ci:Paris",
        expected="Paris",
    ),
    "q05": QuickCaseSpec(
        case_id="q05",
        prompt='Reverse the string "bench" and reply with only the reversed string.',
        rule="exact:hcneb",
        expected="hcneb",
    ),
    "q06": QuickCaseSpec(
        case_id="q06",
        prompt="Sort these numbers from smallest to largest: 5, 3, 8, 1. "
        "Reply with only the sorted numbers, comma-separated.",
        rule="numbers-asc:1,3,5,8",
        expected="1, 3, 5, 8",
    ),
}


def quick_case_spec(case_id: str) -> QuickCaseSpec:
    """Frozen F10 spec for a Quick case; ValueError on anything else."""
    try:
        return _QUICK_CASE_SPECS[case_id]
    except (KeyError, TypeError):
        raise ValueError(
            f"no frozen F10 executor spec for case {case_id!r}"
        ) from None
