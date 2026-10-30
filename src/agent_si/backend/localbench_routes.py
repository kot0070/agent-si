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
Stdlib + fastapi + the own-package capability_store import path in this module.
"""

from __future__ import annotations

import csv
import json
import math
import os
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from agent_si.capability_store.import_store import import_measured_capability
from agent_si.capability_store.store import CapabilityEvidenceRecord
from agent_si.local import bench_runner as _runner
from agent_si.local.bench_protocol import (
    BenchEstimate,
    BenchLevel,
    BenchResultRow,
    ResultKind,
)
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

    @router.post("/api/v1/local/bench/runs/complete")
    def _post_complete(body: dict[str, Any], request: Request) -> JSONResponse:
        refused = _guard(request)
        if refused is not None:
            return refused
        run_id = _run_id_from_body(body)
        if not run_id:
            return _refusal(400, "run_id is required")
        try:
            outcome = complete_route(
                run_id,
                (body or {}).get("rows", []),
                True,
                project_id=(body or {}).get("project_id", "localbench"),
            )
        except KeyError as exc:
            return _refusal(404, str(exc))
        except BenchRefusedError as exc:
            return _refusal(403, str(exc))
        except (ValueError, TypeError) as exc:
            return _refusal(400, str(exc))
        return JSONResponse(status_code=200, content=outcome)

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


def complete_route(
    run_id: str,
    rows: list[dict[str, Any]],
    authorized: bool,
    project_id: str = "localbench",
) -> dict[str, Any]:
    """Entry: finish a run with result rows; unauthorized calls refuse.

    Each row is {case_id, kind, model_id}; hardware comes from the local
    snapshot (no probing, no contact). Returns the complete_run outcome
    (run_id, row count, telemetry metric ids). Unauthorized calls raise
    BenchRefusedError carrying SESSION_TOKEN_REFUSED and change nothing.
    """
    if not authorized:
        raise BenchRefusedError(
            f"{_runner.SESSION_TOKEN_REFUSED}: bench completion needs a bound "
            "UI session token (x-actor + x-ui-session-token); state unchanged"
        )
    if not isinstance(rows, list) or not rows:
        raise ValueError(
            f"rows must be a non-empty list, got {type(rows).__name__}"
        )
    hardware = _runner.detect_hardware()
    built = []
    for entry in rows:
        if not isinstance(entry, dict):
            raise ValueError(
                f"each row must be an object, got {type(entry).__name__}"
            )
        try:
            kind = ResultKind(entry.get("kind", ""))
        except ValueError:
            raise ValueError(
                f"unknown kind {entry.get('kind')!r}"
            ) from None
        case_id = entry.get("case_id", "")
        model_id = entry.get("model_id", "")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError(f"each row needs a case_id, got {case_id!r}")
        if not isinstance(model_id, str) or not model_id:
            raise ValueError(f"each row needs a model_id, got {model_id!r}")
        built.append(BenchResultRow(
            case_id=case_id, kind=kind, model_id=model_id,
            hardware=hardware))
    return _runner.complete_run(run_id, built, project_id=project_id)


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


#: Task-class prefix for localbench imports; the level names the bundle.
_IMPORT_TASK_CLASS_PREFIX = "localbench:"

#: z for the Wilson 95% interval used as the import confidence.
_WILSON_Z_95 = 1.96


def _wilson_lower_95(measured: int, total: int) -> float:
    """Wilson 95% lower bound for a measured share (stdlib math only)."""
    if not isinstance(total, int) or isinstance(total, bool) or total <= 0:
        raise ValueError(f"total must be a positive integer, got {total!r}")
    if not isinstance(measured, int) or isinstance(measured, bool):
        raise ValueError(f"measured must be an integer, got {measured!r}")
    if not 0 <= measured <= total:
        raise ValueError(f"measured {measured!r} outside 0..{total!r}")
    z = _WILSON_Z_95
    share = measured / total
    denom = 1.0 + z * z / total
    center = share + z * z / (2.0 * total)
    margin = z * math.sqrt(share * (1.0 - share) / total + z * z / (4.0 * total * total))
    return max(0.0, (center - margin) / denom)


def _read_results_rows(path: str) -> tuple[list[dict[str, str]], str]:
    """Read a results.csv bundle: (row dicts, run dir). Refuses foreign shapes."""
    with open(path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames or []
        missing = {"case_id", "kind", "model_id"} - set(fieldnames)
        if missing:
            raise ValueError(
                f"results csv {path!r} misses columns: {sorted(missing)!r}"
            )
        rows = []
        for raw in reader:
            row = {key: (value or "") for key, value in dict(raw).items() if key is not None}
            rows.append(row)
    if not rows:
        raise ValueError(f"results csv {path!r} holds no result rows")
    for row in rows:
        if not row.get("case_id", "").strip():
            raise ValueError(f"results csv {path!r} holds a row without case_id")
        if not row.get("model_id", "").strip():
            raise ValueError(f"results csv {path!r} holds a row without model_id")
        try:
            ResultKind(row.get("kind", ""))
        except ValueError:
            raise ValueError(
                f"results csv {path!r} holds unknown kind {row.get('kind')!r}"
            ) from None
    models = {row["model_id"].strip() for row in rows}
    if len(models) != 1:
        raise ValueError(
            f"results csv {path!r} mixes model ids: {sorted(models)!r}"
        )
    return rows, os.path.dirname(os.path.abspath(path))


def _import_task_class(rows: list[dict[str, str]], run_dir: str) -> str:
    """Task class for the bundle: sibling manifest level, else case-id slice."""
    manifest_path = os.path.join(run_dir, "manifest.json")
    try:
        with open(manifest_path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        doc = None
    if isinstance(doc, dict):
        try:
            return _IMPORT_TASK_CLASS_PREFIX + BenchLevel(doc.get("level")).value
        except (ValueError, TypeError, AttributeError):
            pass
    prefixes = {row["case_id"].strip()[:1].lower() for row in rows}
    slice_by_prefix = {
        "q": BenchLevel.Quick,
        "s": BenchLevel.Standard,
        "d": BenchLevel.Deep,
    }
    if len(prefixes) == 1:
        level = slice_by_prefix.get(next(iter(prefixes)))
        if level is not None:
            return _IMPORT_TASK_CLASS_PREFIX + level.value
    raise ValueError(
        f"cannot derive a bench level for import in {run_dir!r}: no usable "
        "sibling manifest.json and mixed or unknown case-id prefixes"
    )


def import_route(path: str, authorized: bool) -> CapabilityEvidenceRecord | None:
    """Entry: convert a results csv bundle into a capability measurement.

    Rows enter via the real capability_store import path (never seeded:
    model, score, sample count, confidence, fingerprint and provenance all
    derive from the csv). Unauthorized calls raise BenchRefusedError
    carrying SESSION_TOKEN_REFUSED. Missing files raise FileNotFoundError.
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
    rows, run_dir = _read_results_rows(path)
    model_id = rows[0]["model_id"].strip()
    task_class = _import_task_class(rows, run_dir)
    measured = sum(1 for row in rows if ResultKind(row["kind"]) is ResultKind.MEASURED)
    total = len(rows)
    first = rows[0]
    fingerprint_parts = [
        first.get(key, "") or ""
        for key in ("gpu_vendor", "gpu_model", "vram_mb", "ram_mb", "cpu_only")
    ]
    document = {
        "model_id": model_id,
        "task_class": task_class,
        "score": measured / total,
        "score_type": "measured_share",
        "sample_count": total,
        "confidence": _wilson_lower_95(measured, total),
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "runtime": "localbench",
        "source": os.path.abspath(path),
        "environment_fingerprint": "|".join(fingerprint_parts)
        if any(fingerprint_parts)
        else None,
    }
    staged_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", dir=run_dir, delete=False, encoding="utf-8"
        ) as fh:
            json.dump(document, fh, indent=2, sort_keys=True)
            fh.write("\n")
            staged_path = fh.name
        return import_measured_capability(staged_path, task_class)
    finally:
        if staged_path is not None:
            try:
                os.remove(staged_path)
            except OSError:
                pass


def check_route(endpoint: str) -> GatewayStatus:
    """Entry: passive gateway check (never forces contact)."""
    return _runner.passive_gateway_check(endpoint)


__all__ = [
    "check_route",
    "complete_route",
    "estimate_route",
    "history_route",
    "import_route",
    "pause_route",
    "register_localbench_routes",
    "results_route",
    "resume_route",
    "runs_route",
    "scan_route",
    "stop_route",
]
