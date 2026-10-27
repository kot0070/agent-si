"""K05 M3 STEP2 implementation: bench output contract v1 (csv+manifest+hardware).

Real bodies behind the frozen STEP1 signatures. Level floors are the
BUILD_PLAN staged minima (Quick ~10-15min@8B, Standard 30-60, Deep 120+),
scaled linearly by model size. Standard library only.
"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import asdict, dataclass
from enum import Enum


class BenchLevel(str, Enum):
    Quick = "Quick"
    Standard = "Standard"
    Deep = "Deep"


class ResultKind(str, Enum):
    PROXY = "PROXY"
    MEASURED = "MEASURED"


@dataclass
class HardwareProfile:
    gpu_vendor: str
    gpu_model: str | None
    vram_mb: int | None
    ram_mb: int
    cpu_only: bool


@dataclass
class BenchEstimate:
    level: BenchLevel
    model_id: str
    minutes_min: float
    minutes_max: float


@dataclass
class BenchWarning:
    code: str
    message: str


@dataclass
class BenchResultRow:
    case_id: str
    kind: ResultKind
    model_id: str
    hardware: HardwareProfile


#: BUILD_PLAN reference minima in minutes at 8B params (Quick ~10-15min@8B,
#: Standard 30-60, Deep 120+): Quick (10, 15), Standard (30, 60),
#: Deep (120, 180); Deep lower bound stays >= 120 at 8B.
_BASE_FLOORS: dict[BenchLevel, tuple[float, float]] = {
    BenchLevel.Quick: (10.0, 15.0),
    BenchLevel.Standard: (30.0, 60.0),
    BenchLevel.Deep: (120.0, 180.0),
}

#: Params reference point for size scaling.
_REFERENCE_PARAMS_B = 8.0

#: Hard minima in minutes per level, applied to BOTH bounds after scaling.
#: Floors only raise minima; they never lower a scaled bound.
_HARD_FLOORS: dict[BenchLevel, float] = {
    BenchLevel.Quick: 5.0,
    BenchLevel.Standard: 15.0,
    BenchLevel.Deep: 30.0,
}


def level_floor_minutes(level: BenchLevel, model_params_b: float) -> tuple[float, float]:
    """Floor (lo, hi) minutes for a level, scaled linearly by model size.

    Unknown/non-positive sizes fall back to the 8B reference floors
    (fail-closed: never report a zero-minute floor). Hard minima per
    level then apply to BOTH bounds: each bound is the max of its
    scaled value and the level's hard floor.
    """
    lvl = BenchLevel(level)
    try:
        params = float(model_params_b)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"model_params_b must be a number, got {model_params_b!r}") from exc
    scale = params / _REFERENCE_PARAMS_B if params > 0 else 1.0
    lo, hi = _BASE_FLOORS[lvl]
    hard = _HARD_FLOORS[lvl]
    return (max(lo * scale, hard), max(hi * scale, hard))


def build_prestart_warnings(estimate: BenchEstimate, pc_in_use: bool) -> list[BenchWarning]:
    """Duration + PC-load + do-not-use-PC pre-start warnings for an estimate."""
    warnings = [
        BenchWarning(
            code="BENCH_DURATION",
            message=(
                f"Benchmark '{estimate.model_id}' ({estimate.level.value}) takes about "
                f"{estimate.minutes_min:.0f}-{estimate.minutes_max:.0f} minutes; "
                "keep the machine powered and idle until it finishes."
            ),
        )
    ]
    if pc_in_use:
        warnings.append(
            BenchWarning(
                code="BENCH_PC_IN_USE",
                message=(
                    "The PC is currently in use; do not use the PC for other work "
                    "during the run or the measured timings are not valid evidence."
                ),
            )
        )
    return warnings


def build_result_row(
    case_id: str, kind: ResultKind, model_id: str, hardware: HardwareProfile
) -> BenchResultRow:
    """One results row carrying its hardware profile (PROXY|MEASURED)."""
    if not isinstance(case_id, str) or not case_id:
        raise ValueError(f"case_id must be a non-empty string, got {case_id!r}")
    if not isinstance(model_id, str) or not model_id:
        raise ValueError(f"model_id must be a non-empty string, got {model_id!r}")
    return BenchResultRow(
        case_id=case_id, kind=ResultKind(kind), model_id=model_id, hardware=hardware
    )


def write_manifest(run_dir: str, hardware: HardwareProfile, estimate: BenchEstimate) -> None:
    """Write the run manifest (estimate + hardware snapshot) into run_dir."""
    os.makedirs(run_dir, exist_ok=True)
    manifest = {
        "model_id": estimate.model_id,
        "level": estimate.level.value,
        "minutes_min": estimate.minutes_min,
        "minutes_max": estimate.minutes_max,
        "hardware": asdict(hardware),
    }
    with open(os.path.join(run_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")


def write_hardware_profile(run_dir: str, hardware: HardwareProfile) -> None:
    """Write the hardware profile snapshot into run_dir."""
    os.makedirs(run_dir, exist_ok=True)
    with open(os.path.join(run_dir, "hardware.json"), "w", encoding="utf-8") as fh:
        json.dump(asdict(hardware), fh, indent=2, sort_keys=True)
        fh.write("\n")


_RESULTS_CSV_COLUMNS = (
    "case_id",
    "kind",
    "model_id",
    "gpu_vendor",
    "gpu_model",
    "vram_mb",
    "ram_mb",
    "cpu_only",
)


def append_results_csv(run_dir: str, rows: list[BenchResultRow]) -> None:
    """Append result rows to run_dir/results.csv (header written once)."""
    os.makedirs(run_dir, exist_ok=True)
    path = os.path.join(run_dir, "results.csv")
    write_header = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, "a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(_RESULTS_CSV_COLUMNS))
        if write_header:
            writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "case_id": row.case_id,
                    "kind": row.kind.value,
                    "model_id": row.model_id,
                    "gpu_vendor": row.hardware.gpu_vendor,
                    "gpu_model": row.hardware.gpu_model,
                    "vram_mb": row.hardware.vram_mb,
                    "ram_mb": row.hardware.ram_mb,
                    "cpu_only": row.hardware.cpu_only,
                }
            )
