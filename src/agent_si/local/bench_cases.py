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
