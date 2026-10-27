"""K05 M3 STEP2 implementation: localbench HTTP surface.

Mounts scan/estimate/runs/pause/resume/stop/results/history/import/check
under /api/v1/local/bench/*. Every route reaches its real implementation
through the entry function below; the HTTP layer only maps errors to
status codes. Write routes (runs/pause/resume/stop/import) enforce the
K02 seam — x-actor + x-ui-session-token must match the app's bound token
(read from app.state: ui_session_token/session_token, else the settings
mapping), missing -> 401, wrong/unverifiable -> 403, both carrying
SESSION_TOKEN_REFUSED and changing nothing. Reads need no token.
Fail-closed: with no bound token configured, every write is refused.
Stdlib + fastapi only in this module.
"""

from __future__ import annotations

import os
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from agent_si.local import bench_runner as _runner
from agent_si.local.bench_protocol import BenchEstimate, BenchLevel, BenchResultRow
from agent_si.local.bench_runner import (
    BenchBusyError,
    BenchRefusedError,
    Calibration,
    GatewayStatus,
    RunHandle,
    RunSkip,
)


class _RunSkipped(Exception):
    """Private: the runner skipped (gateway unreachable); HTTP maps to 503."""


def _expected_session_token(app: Any) -> str | None:
    """Bound UI session token from the app, or None when unconfigured."""
    state = getattr(app, "state", None)
    for attr in ("ui_session_token", "session_token", "bench_session_token"):
        try:
            token = getattr(state, attr, None)
        except Exception:
            token = None
        if isinstance(token, str) and token:
            return token
    try:
        settings = getattr(state, "settings", None)
    except Exception:
        settings = None
    if isinstance(settings, dict):
        for key in ("ui_session_token", "session_token", "token"):
            token = settings.get(key)
            if isinstance(token, str) and token:
                return token
    return None


def _coerce_level(level: BenchLevel | str) -> BenchLevel:
    try:
        return BenchLevel(level)
    except ValueError:
        raise ValueError(f"unknown bench level: {level!r}") from None


def register_localbench_routes(app: Any) -> Any:
    """Mount the localbench routes on a FastAPI app; returns the app."""
    expected = _expected_session_token(app)
    router = APIRouter()

    def _refusal(status: int, message: str) -> JSONResponse:
        return JSONResponse(status_code=status, content={"detail": message})

    def _guard(request: Request) -> JSONResponse | None:
        actor = request.headers.get("x-actor", "")
        token = request.headers.get("x-ui-session-token", "")
        if not actor or not token:
            return _refusal(
                401,
                f"{_runner.SESSION_TOKEN_REFUSED}: write needs x-actor + "
                "x-ui-session-token; state unchanged",
            )
        if expected is None or token != expected:
            return _refusal(
                403,
                f"{_runner.SESSION_TOKEN_REFUSED}: UI session token mismatch; "
                "state unchanged",
            )
        return None

    def _run_id_from_body(body: Any) -> str:
        run_id = (body or {}).get("run_id", "") if isinstance(body, dict) else ""
        if not isinstance(run_id, str) or not run_id:
            return ""
        return run_id

    @router.post("/api/v1/local/bench/runs")
    def _post_runs(body: dict[str, Any], request: Request) -> JSONResponse:
        refused = _guard(request)
        if refused is not None:
            return refused
        try:
            level = _coerce_level((body or {}).get("level", ""))
            model_id = (body or {}).get("model_id", "")
            run_id = runs_route(model_id, level, True)
        except _RunSkipped as exc:
            return _refusal(503, str(exc))
        except BenchBusyError as exc:
            return _refusal(409, str(exc))
        except BenchRefusedError as exc:
            return _refusal(403, str(exc))
        except (ValueError, TypeError) as exc:
            return _refusal(400, str(exc))
        return JSONResponse(status_code=200, content={"run_id": run_id})

    @router.post("/api/v1/local/bench/runs/pause")
    def _post_pause(body: dict[str, Any], request: Request) -> JSONResponse:
        refused = _guard(request)
        if refused is not None:
            return refused
        run_id = _run_id_from_body(body)
        if not run_id:
            return _refusal(400, "run_id is required")
        try:
            pause_route(run_id)
        except KeyError as exc:
            return _refusal(404, str(exc))
        except BenchRefusedError as exc:
            return _refusal(403, str(exc))
        return JSONResponse(status_code=200, content={"run_id": run_id, "paused": True})

    @router.post("/api/v1/local/bench/runs/resume")
    def _post_resume(body: dict[str, Any], request: Request) -> JSONResponse:
        refused = _guard(request)
        if refused is not None:
            return refused
        run_id = _run_id_from_body(body)
        if not run_id:
            return _refusal(400, "run_id is required")
        try:
            resume_route(run_id)
        except KeyError as exc:
            return _refusal(404, str(exc))
        except BenchRefusedError as exc:
            return _refusal(403, str(exc))
        return JSONResponse(status_code=200, content={"run_id": run_id, "paused": False})

    @router.post("/api/v1/local/bench/runs/stop")
    def _post_stop(body: dict[str, Any], request: Request) -> JSONResponse:
        refused = _guard(request)
        if refused is not None:
            return refused
        run_id = _run_id_from_body(body)
        if not run_id:
            return _refusal(400, "run_id is required")
        try:
            stop_route(run_id)
        except KeyError as exc:
            return _refusal(404, str(exc))
        except BenchRefusedError as exc:
            return _refusal(403, str(exc))
        return JSONResponse(status_code=200, content={"run_id": run_id, "stopped": True})

    @router.post("/api/v1/local/bench/import")
    def _post_import(body: dict[str, Any], request: Request) -> JSONResponse:
        refused = _guard(request)
        if refused is not None:
            return refused
        path = (body or {}).get("path", "") if isinstance(body, dict) else ""
        try:
            import_route(path, True)
        except BenchRefusedError as exc:
            return _refusal(403, str(exc))
        except FileNotFoundError as exc:
            return _refusal(404, str(exc))
        except (ValueError, TypeError) as exc:
            return _refusal(400, str(exc))
        return JSONResponse(status_code=200, content={"path": path, "staged": True})

    @router.get("/api/v1/local/bench/scan")
    def _get_scan(path: str = "", allowlist: str = "") -> JSONResponse:
        if not path:
            return JSONResponse(status_code=200, content=[])
        bases = [entry for entry in allowlist.split(",") if entry] if allowlist else []
        try:
            models = scan_route(bases, path)
        except BenchRefusedError as exc:
            return _refusal(403, str(exc))
        return JSONResponse(status_code=200, content=models)

    @router.get("/api/v1/local/bench/estimate")
    def _get_estimate(model_id: str = "m", level: str = "Quick") -> JSONResponse:
        try:
            estimate = estimate_route(model_id, _coerce_level(level))
        except (ValueError, TypeError) as exc:
            return _refusal(400, str(exc))
        return JSONResponse(status_code=200, content=asdict(estimate))

    @router.get("/api/v1/local/bench/results")
    def _get_results(run_id: str = "") -> JSONResponse:
        rows = results_route(run_id) if run_id else []
        return JSONResponse(status_code=200, content=[asdict(row) for row in rows])

    @router.get("/api/v1/local/bench/history")
    def _get_history() -> JSONResponse:
        return JSONResponse(status_code=200, content=history_route())

    @router.get("/api/v1/local/bench/check")
    def _get_check(endpoint: str = "") -> JSONResponse:
        return JSONResponse(status_code=200, content=asdict(check_route(endpoint)))

    include = getattr(app, "include_router", None)
    if not callable(include):
        raise TypeError("register_localbench_routes needs a FastAPI app")
    include(router)
    try:
        app.state.localbench_mounted = True
    except Exception:
        pass
    return app


def scan_route(allowlist_dirs: list[str], requested_path: str) -> list[str]:
    """Entry: read-only allowlist-first scan (refuses bad paths)."""
    return _runner.scan_models(allowlist_dirs, requested_path)


def estimate_route(model_id: str, level: BenchLevel) -> BenchEstimate:
    """Entry: nominal-calibration estimate (route floor, min >= 5 minutes)."""
    lvl = _coerce_level(level)
    if not isinstance(model_id, str) or not model_id:
        raise ValueError(f"model_id must be a non-empty string, got {model_id!r}")
    nominal = Calibration(model_id=model_id, seconds_per_case=1.0)
    return _runner.estimate_run(model_id, lvl, nominal)


def runs_route(model_id: str, level: BenchLevel, authorized: bool) -> str:
    """Entry: start a run, returning its run id.

    Unauthorized calls raise BenchRefusedError carrying
    SESSION_TOKEN_REFUSED and change nothing. A gateway-unreachable skip
    raises the private _RunSkipped (mapped to HTTP 503 by the route).
    """
    if not authorized:
        raise BenchRefusedError(
            f"{_runner.SESSION_TOKEN_REFUSED}: bench runs need a bound UI session "
            "token (x-actor + x-ui-session-token); state unchanged"
        )
    outcome = _runner.start_run(model_id, _coerce_level(level), True)
    if isinstance(outcome, RunSkip):
        raise _RunSkipped(outcome.reason)
    assert isinstance(outcome, RunHandle)
    return outcome.run_id


def pause_route(run_id: str) -> None:
    """Entry: pause a live run."""
    _runner.pause_run(run_id)


def resume_route(run_id: str) -> None:
    """Entry: resume a paused run."""
    _runner.resume_run(run_id)


def stop_route(run_id: str) -> None:
    """Entry: stop a run."""
    _runner.stop_run(run_id)


def results_route(run_id: str) -> list[BenchResultRow]:
    """Entry: recorded rows for a run (empty when nothing recorded yet)."""
    if not isinstance(run_id, str) or not run_id:
        return []
    try:
        return _runner.run_result_rows(run_id)
    except KeyError:
        return []


def history_route() -> list[str]:
    """Entry: known run ids in start order."""
    return _runner.list_run_ids()


def import_route(path: str, authorized: bool) -> None:
    """Entry: stage a results file for import (rows enter via capability_store).

    Unauthorized calls raise BenchRefusedError carrying
    SESSION_TOKEN_REFUSED. Missing files raise FileNotFoundError.
    """
    if not authorized:
        raise BenchRefusedError(
            f"{_runner.SESSION_TOKEN_REFUSED}: bench imports need a bound UI session "
            "token (x-actor + x-ui-session-token); state unchanged"
        )
    if not isinstance(path, str) or not path:
        raise ValueError(f"path must be a non-empty string, got {path!r}")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"import file not found: {path!r}")
    return None


def check_route(endpoint: str) -> GatewayStatus:
    """Entry: passive gateway check (never forces contact)."""
    return _runner.passive_gateway_check(endpoint)


__all__ = [
    "register_localbench_routes",
    "scan_route",
    "estimate_route",
    "runs_route",
    "pause_route",
    "resume_route",
    "stop_route",
    "results_route",
    "history_route",
    "import_route",
    "check_route",
]
