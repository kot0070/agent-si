"""K05 M3 STEP1 contract test (RED until impl; fakes live here only, marked FAKE-OF)."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))

import pytest

from agent_si.backend import localbench_routes as routes
from agent_si.local import bench_cases as cases
from agent_si.local import bench_protocol as proto
from agent_si.local import bench_runner as runner
from agent_si.local.bench_protocol import BenchLevel, ResultKind
from agent_si.local.bench_runner import BenchBusyError, BenchRefusedError, RunSkip


class FakeRuntime:  # FAKE-OF bench_runner chat seam (injected chat callable)
    def chat(self, model_id: str, prompt: str) -> dict[str, str]:
        return {"model": model_id, "text": "fake-ok"}


class FakeGateway:  # FAKE-OF gateway passive-check (canned unreachable status)
    def status(self) -> runner.GatewayStatus:
        return runner.GatewayStatus(reachable=False, reason="fake-unreachable")


def _hw() -> proto.HardwareProfile:
    return proto.HardwareProfile(gpu_vendor="CPU-only", gpu_model=None, vram_mb=None, ram_mb=16384, cpu_only=True)


def test_level_floors_scaled() -> None:
    assert proto.level_floor_minutes(BenchLevel.Quick, 8.0) == (10.0, 15.0)
    assert proto.level_floor_minutes(BenchLevel.Standard, 8.0) == (30.0, 60.0)
    lo, _ = proto.level_floor_minutes(BenchLevel.Deep, 8.0)
    assert lo >= 120.0


def test_calibration_drives_estimates() -> None:
    cal = runner.calibrate("fake-8b", FakeRuntime())
    est = runner.estimate_run("fake-8b", BenchLevel.Quick, cal)
    assert est.minutes_min >= 5.0 and est.minutes_max >= est.minutes_min


def test_busy_machine_raises() -> None:
    runner.start_run("m-one", BenchLevel.Quick, True)
    with pytest.raises(BenchBusyError):
        runner.start_run("m-two", BenchLevel.Quick, True)


def test_skip_with_reason() -> None:
    gw = FakeGateway().status()
    assert gw.reachable is False and gw.reason != ""
    got = runner.start_run("m-offline", BenchLevel.Quick, True)
    assert isinstance(got, RunSkip) and got.reason != ""


def test_forbidden_path_refused() -> None:
    with pytest.raises(BenchRefusedError):
        runner.scan_models(["C:/allowed"], "C:/creds/secret.key")


def test_unauthorized_pull_refused() -> None:
    with pytest.raises(BenchRefusedError):
        runner.pull_model("some-model", False)


def test_pause_stop_progress() -> None:
    handle = runner.start_run("m-pause", BenchLevel.Quick, True)
    assert not isinstance(handle, RunSkip)
    runner.pause_run(handle.run_id)
    assert runner.run_progress(handle.run_id).paused is True
    runner.stop_run(handle.run_id)
    assert runner.run_progress(handle.run_id).stopped is True


def test_rows_carry_hw_profile() -> None:
    hw = _hw()
    row = proto.build_result_row("q01", ResultKind.MEASURED, "m", hw)
    assert row.kind == ResultKind.MEASURED and row.hardware == hw


def test_routes_reach_impl_via_entry() -> None:
    assert callable(routes.register_localbench_routes)
    est = routes.estimate_route("m", BenchLevel.Quick)
    assert est.minutes_min >= 5.0
    with pytest.raises(BenchRefusedError):
        routes.scan_route(["C:/allowed"], "C:/Windows/System32/config/sam")
    assert cases.validate_case(cases.list_cases(BenchLevel.Quick)[0]) is None


# ---- K05 M3 STEP1e B1+B2: token refusal on the 4 write routes via the frozen app seam ----
# Named error code (frozen K13 router-guard / 0C sec 10-11: every USER write handler
# checks the UI session token first, reads need no token; FREEZE.md: writes need
# x-actor + x-ui-session-token match else 401/403). M1 pins the same name in
# adapter.ERROR_CODES_LOCAL; M3 writes must refuse with it too.
EXPECTED_M3_AUTH_CODE = "SESSION_TOKEN_REFUSED"

# (method, path, json-payload) for the 4 write routes (runs start, pause, resume,
# stop). Paths live under the frozen /api/v1/local/ prefix (local_connect.HTTP_ROUTES).
M3_WRITE_ROUTES = (
    ("POST", "/api/v1/local/bench/runs", {"model_id": "m", "level": "Quick"}),
    ("POST", "/api/v1/local/bench/runs/pause", {"run_id": "run-no-token-1"}),
    ("POST", "/api/v1/local/bench/runs/resume", {"run_id": "run-no-token-1"}),
    ("POST", "/api/v1/local/bench/runs/stop", {"run_id": "run-no-token-1"}),
)

# Read routes: served with no token.
M3_READ_ROUTES = (
    ("GET", "/api/v1/local/bench/scan", None),
    ("GET", "/api/v1/local/bench/estimate?model_id=m&level=Quick", None),
    ("GET", "/api/v1/local/bench/results?run_id=run-no-token-1", None),
)

_WRONG_TOKEN_HEADERS = {"x-actor": "user", "x-ui-session-token": "wrong-token-1"}


def _m3_seam_client():
    """Frozen K02 seam: TestClient(create_app(test settings)) + register_localbench_routes."""
    try:
        from agent_si.backend.app import create_app
    except ImportError as exc:
        pytest.fail(f"K05-M3: create_app missing (K02 composition root): {exc}")
    try:
        from fastapi.testclient import TestClient
    except ImportError as exc:
        pytest.fail(f"K05-M3: TestClient missing: {exc}")
    app = create_app({"env": "test"})
    routes.register_localbench_routes(app)
    return TestClient(app)


def _refused_with_named_code(resp) -> None:
    assert resp.status_code in (401, 403), f"expected 401/403, got {resp.status_code}: {resp.text}"
    assert EXPECTED_M3_AUTH_CODE in resp.text, f"named code missing: {resp.text}"


def _drive(client, method, path, payload, headers=None):
    if payload is not None:
        return client.request(method, path, json=payload, headers=headers)
    return client.request(method, path, headers=headers)


def test_m3_write_routes_refuse_missing_token_named_code() -> None:
    client = _m3_seam_client()
    for method, path, payload in M3_WRITE_ROUTES:
        _refused_with_named_code(_drive(client, method, path, payload))


def test_m3_write_routes_refuse_wrong_token_named_code() -> None:
    client = _m3_seam_client()
    for method, path, payload in M3_WRITE_ROUTES:
        _refused_with_named_code(_drive(client, method, path, payload, _WRONG_TOKEN_HEADERS))


def test_m3_refused_writes_change_nothing() -> None:
    client = _m3_seam_client()
    before = [m + " " + p + " " + _drive(client, m, p, None).text for m, p, _ in M3_READ_ROUTES]
    for method, path, payload in M3_WRITE_ROUTES:
        _drive(client, method, path, payload)
        _drive(client, method, path, payload, _WRONG_TOKEN_HEADERS)
    after = [m + " " + p + " " + _drive(client, m, p, None).text for m, p, _ in M3_READ_ROUTES]
    assert before == after


def test_m3_read_routes_need_no_token() -> None:
    client = _m3_seam_client()
    for method, path, _ in M3_READ_ROUTES:
        resp = _drive(client, method, path, None)
        assert 200 <= resp.status_code < 300, f"{method} {path} -> {resp.status_code}: {resp.text}"


def test_m3_start_entry_refuses_unauthorized_with_named_code() -> None:
    with pytest.raises(BenchRefusedError) as excinfo:
        routes.runs_route("m", BenchLevel.Quick, False)
    assert EXPECTED_M3_AUTH_CODE in str(excinfo.value)
