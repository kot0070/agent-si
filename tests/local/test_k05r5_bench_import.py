"""K05R5 M-BENCH import: import_route turns a results csv into a measurement.

RED before the localbench_routes conversion lands (import_route returns
None and no MEASURED row enters the store); GREEN after. The csv fixture
is written through the real bench_protocol writers and rows enter through
the real capability_store import path. Fakes live here only (FAKE-OF ids).
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))

import pytest

from agent_si.backend import localbench_routes as routes
from agent_si.capability_store import EvidenceTier, get_evidence, require_current
from agent_si.local import bench_protocol as proto
from agent_si.local import bench_runner as runner
from agent_si.local.bench_protocol import BenchLevel, ResultKind
from agent_si.local.bench_runner import BenchRefusedError, Calibration


def _hardware() -> proto.HardwareProfile:
    return proto.HardwareProfile(
        gpu_vendor="CPU-only",
        gpu_model=None,
        vram_mb=None,
        ram_mb=16384,
        cpu_only=True,
    )


def _write_bundle(
    run_dir,
    *,
    model: str,
    kinds: list,
    level: BenchLevel = BenchLevel.Quick,
    manifest: bool = True,
    manifest_level: BenchLevel | None = None,
) -> str:
    """Real results bundle: results.csv via append + optional manifest."""
    run_dir.mkdir(parents=True, exist_ok=True)
    prefix = {"Quick": "q", "Standard": "s", "Deep": "d"}[level.value]
    rows = [
        proto.build_result_row(f"{prefix}{idx + 1:02d}", kind, model, _hardware())
        for idx, kind in enumerate(kinds)
    ]
    proto.append_results_csv(str(run_dir), rows)
    if manifest:
        cal = Calibration(model_id=model, seconds_per_case=1.0)
        proto.write_manifest(
            str(run_dir),
            _hardware(),
            runner.estimate_run(model, manifest_level or level, cal),
        )
    return str(run_dir / "results.csv")


def test_import_converts_csv_to_measured_row(tmp_path) -> None:
    model = "FAKE-OF: bench import model a"
    csv_path = _write_bundle(
        tmp_path / "run-a",
        model=model,
        kinds=[ResultKind.MEASURED] * 4 + [ResultKind.PROXY] * 2,
    )
    record = routes.import_route(csv_path, True)
    assert record is not None
    assert record.tier is EvidenceTier.MEASURED
    assert record.model_id == model
    assert record.task_class == "localbench:Quick"
    assert record.sample_count == 6
    assert record.score == pytest.approx(4.0 / 6.0)
    assert 0.0 < record.confidence < record.score
    assert record.confidence == pytest.approx(routes._wilson_lower_95(4, 6))
    assert record.measured_at and record.runtime == "localbench" and record.source
    served = get_evidence(model, "localbench:Quick")
    assert served is record
    assert served.evidence_ref
    assert require_current(served.evidence_ref) is record


def test_import_without_manifest_falls_back_to_case_prefix(tmp_path) -> None:
    model = "FAKE-OF: bench import model b"
    csv_path = _write_bundle(
        tmp_path / "run-b",
        model=model,
        kinds=[ResultKind.MEASURED] * 3,
        level=BenchLevel.Standard,
        manifest=False,
    )
    record = routes.import_route(csv_path, True)
    assert record is not None
    assert record.task_class == "localbench:Standard"
    assert record.sample_count == 3
    assert record.score == pytest.approx(1.0)
    assert get_evidence(model, "localbench:Standard") is record


def test_import_manifest_level_wins_over_case_prefix(tmp_path) -> None:
    model = "FAKE-OF: bench import model c"
    csv_path = _write_bundle(
        tmp_path / "run-c",
        model=model,
        kinds=[ResultKind.MEASURED] * 2,
        level=BenchLevel.Quick,
        manifest_level=BenchLevel.Standard,
    )
    record = routes.import_route(csv_path, True)
    assert record is not None
    assert record.task_class == "localbench:Standard"
    assert get_evidence(model, "localbench:Standard") is record


def test_import_refuses_mixed_models_and_enters_nothing(tmp_path) -> None:
    run_dir = tmp_path / "run-d"
    run_dir.mkdir(parents=True, exist_ok=True)
    rows = [
        proto.build_result_row(
            "q01", ResultKind.MEASURED, "FAKE-OF: bench import model d1", _hardware()
        ),
        proto.build_result_row(
            "q02", ResultKind.MEASURED, "FAKE-OF: bench import model d2", _hardware()
        ),
    ]
    proto.append_results_csv(str(run_dir), rows)
    with pytest.raises(ValueError):
        routes.import_route(str(run_dir / "results.csv"), True)
    assert get_evidence("FAKE-OF: bench import model d1", "localbench:Quick") is None
    assert get_evidence("FAKE-OF: bench import model d2", "localbench:Quick") is None


def test_import_refuses_empty_and_unknown_kind(tmp_path) -> None:
    run_dir = tmp_path / "run-e"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "results.csv").write_text(
        "case_id,kind,model_id,gpu_vendor,gpu_model,vram_mb,ram_mb,cpu_only\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        routes.import_route(str(run_dir / "results.csv"), True)
    bad_dir = tmp_path / "run-f"
    csv_path = _write_bundle(
        bad_dir,
        model="FAKE-OF: bench import model f",
        kinds=[ResultKind.MEASURED],
    )
    text = (bad_dir / "results.csv").read_text(encoding="utf-8").replace(
        "MEASURED", "BOGUS"
    )
    (bad_dir / "results.csv").write_text(text, encoding="utf-8")
    with pytest.raises(ValueError):
        routes.import_route(csv_path, True)


def test_import_keeps_auth_and_path_contract() -> None:
    with pytest.raises(BenchRefusedError) as excinfo:
        routes.import_route("/nope/results.csv", False)
    assert runner.SESSION_TOKEN_REFUSED in str(excinfo.value)
    with pytest.raises(FileNotFoundError):
        routes.import_route("/nope/results.csv", True)
    with pytest.raises(ValueError):
        routes.import_route("", True)


def test_wilson_helper_bounds() -> None:
    assert routes._wilson_lower_95(0, 6) == 0.0
    full = routes._wilson_lower_95(6, 6)
    assert 0.0 < full < 1.0
    with pytest.raises(ValueError):
        routes._wilson_lower_95(7, 6)
    with pytest.raises(ValueError):
        routes._wilson_lower_95(0, 0)
