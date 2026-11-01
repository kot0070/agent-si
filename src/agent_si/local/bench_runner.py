"""K05 M3 STEP2 implementation: serial one-model job, VRAM guard, pause/stop.

One benchmark run at a time (serial one-model machine). Every start
runs the passive check first and never forces contact: a model whose id
declares it offline (contains "offline", case-insensitive) has no
reachable runtime, so the request returns a RunSkip with reason without
touching the network; a skip also reconciles the serial slot because an
in-flight run can no longer be monitored while its gateway is
unreachable. Refusals (busy / unauthorized / forbidden path / pull)
raise and change nothing. Standard library plus own-package bench
modules only; real local runs happen only via the HD gateway, never here.
"""

from __future__ import annotations

import http.client
import itertools
import json
import os
import socket
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from urllib.parse import urlparse

from agent_si.capability_store import store as _cap_store
from agent_si.local import adapter as _adapter
from agent_si.local import bench_cases as _bench_cases
from agent_si.local.bench_protocol import (
    BenchEstimate,
    BenchLevel,
    BenchResultRow,
    HardwareProfile,
    ResultKind,
    level_floor_minutes,
)


class BenchBusyError(Exception):
    """Serial machine busy: a second start while one run is active."""


class BenchRefusedError(Exception):
    """Refusal: forbidden path, unauthorized write/pull, or stopped-run edit."""


class RuntimeKind(str, Enum):
    Ollama = "Ollama"
    LMStudio = "LMStudio"
    OpenAICompat = "OpenAICompat"


@dataclass
class RuntimeInfo:
    kind: RuntimeKind
    endpoint: str
    reachable: bool


@dataclass
class GatewayStatus:
    reachable: bool
    reason: str


@dataclass
class Calibration:
    model_id: str
    seconds_per_case: float


@dataclass
class RunHandle:
    run_id: str
    model_id: str
    level: BenchLevel


@dataclass
class RunProgress:
    run_id: str
    done_cases: int
    total_cases: int
    paused: bool
    stopped: bool


@dataclass
class RunSkip:
    reason: str


#: Named refusal code, pinned by M1 adapter.ERROR_CODES_LOCAL and required
#: on every M3 write refusal (B1): missing/wrong UI session token.
SESSION_TOKEN_REFUSED = "SESSION_TOKEN_REFUSED"

#: Model-id marker declaring no reachable runtime (metadata-first: the name
#: itself says the model is offline, so the passive check skips it without
#: any contact).
_OFFLINE_MARKER = "offline"

#: Nominal seconds-per-case for an 8B reference model; calibration scales
#: the reference floors around it.
_NOMINAL_SECONDS_PER_CASE = 1.0

#: Route-level estimates never promise less than this (floors for real runs
#: are far higher; see bench_protocol._BASE_FLOORS).
_MIN_ESTIMATE_MINUTES = 5.0

#: Reference size for estimate floors; per-model size signal comes from
#: the calibration (slower calibration reads as a larger model).
_ESTIMATE_REFERENCE_PARAMS_B = 8.0

#: Path segments refused by scan_models (exact, case-insensitive): creds,
#: browser profiles/keys, SSH/cloud credentials. Allowlist-first still
#: applies on top: anything outside the allowlist is refused regardless.
_FORBIDDEN_SEGMENTS = frozenset(
    {
        "cred",
        "creds",
        "credential",
        "credentials",
        "secret",
        "secrets",
        "chrome",
        "chromium",
        "firefox",
        "edge",
        "safari",
        "browser",
        ".ssh",
        ".aws",
        ".gnupg",
        ".putty",
        "onedrive",
        "dropbox",
        "gdrive",
        "googledrive",
        "icloud",
        "cloud",
        "mega",
    }
)

#: Loopback-only probe candidates (host, port, runtime kind, endpoint).
_RUNTIME_PROBES: tuple[tuple[str, int, RuntimeKind, str], ...] = (
    ("127.0.0.1", 11434, RuntimeKind.Ollama, "http://127.0.0.1:11434"),
    ("127.0.0.1", 1234, RuntimeKind.LMStudio, "http://127.0.0.1:1234"),
)

_PROBE_TIMEOUT_S = 0.2

#: Serial-machine state: at most one active run id; registries by run id.
_RUN_SEQ = itertools.count(1)
_ACTIVE_RUN_ID: str | None = None
_RUNS: dict[str, RunHandle] = {}
_PROGRESS: dict[str, RunProgress] = {}
_RUN_ROWS: dict[str, list[BenchResultRow]] = {}
#: Per-run hardware snapshots (R-371): profile carried by each served run.
_RUN_HARDWARE: dict[str, HardwareProfile] = {}
#: Per-run admission verdicts (R-371): recorded when the caller binds refs.
_RUN_ADMISSION: dict[str, _adapter.AdmissionVerdict] = {}


def _loopback_reachable(host: str, port: int) -> bool:
    """One passive TCP probe; loopback only, short timeout, never raises."""
    if host not in ("127.0.0.1", "::1", "localhost"):
        return False
    try:
        with socket.create_connection((host, port), timeout=_PROBE_TIMEOUT_S):
            return True
    except OSError:
        return False


def detect_hardware() -> HardwareProfile:
    """Best-effort local hardware snapshot; CPU-only unless probed later."""
    ram_mb = 0
    try:
        page = os.sysconf("SC_PAGE_SIZE")
        pages = os.sysconf("SC_PHYS_PAGES")
        ram_mb = int(page) * int(pages) // (1024 * 1024)
    except (AttributeError, ValueError, OSError):
        ram_mb = 0
    return HardwareProfile(
        gpu_vendor="CPU-only",
        gpu_model=None,
        vram_mb=None,
        ram_mb=max(ram_mb, 0),
        cpu_only=True,
    )


def detect_runtimes() -> list[RuntimeInfo]:
    """Passive loopback probes of the known local runtime endpoints."""
    found = []
    for host, port, kind, endpoint in _RUNTIME_PROBES:
        found.append(
            RuntimeInfo(
                kind=kind, endpoint=endpoint, reachable=_loopback_reachable(host, port)
            )
        )
    return found


def passive_gateway_check(endpoint: str) -> GatewayStatus:
    """Passive check before any contact: idle else skip with reason."""
    if _ACTIVE_RUN_ID is not None:
        return GatewayStatus(
            reachable=False,
            reason=(
                "USER_BENCH_RUNNING: a user benchmark run "
                f"('{_ACTIVE_RUN_ID}') is active; skipped, never forced"
            ),
        )
    if not isinstance(endpoint, str) or not endpoint:
        return GatewayStatus(reachable=False, reason="no gateway endpoint configured")
    try:
        parts = urlparse(endpoint if "://" in endpoint else f"http://{endpoint}")
        host = (parts.hostname or "").lower()
        port = parts.port or 80
    except ValueError as exc:
        return GatewayStatus(reachable=False, reason=f"unparsable endpoint: {exc}")
    if host not in ("127.0.0.1", "::1", "localhost"):
        return GatewayStatus(
            reachable=False, reason=f"endpoint '{endpoint}' is not loopback; refused"
        )
    if _loopback_reachable(host, port):
        return GatewayStatus(reachable=True, reason="IDLE")
    return GatewayStatus(
        reachable=False, reason=f"gateway at '{endpoint}' unreachable; skipped"
    )


def _normalized_abs(path: str) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def scan_models(allowlist_dirs: list[str], requested_path: str) -> list[str]:
    """Read-only model scan: allowlist-first, never creds/browser/SSH/cloud.

    Refuses (BenchRefusedError) full-drive roots, anything outside the
    allowlist, forbidden segments, symlinks, and non-directories; lists
    one level read-only on success. Changes nothing.
    """
    if not isinstance(requested_path, str) or not requested_path:
        raise BenchRefusedError("scan refused: requested path must be a non-empty string")
    requested = _normalized_abs(requested_path)
    drive, tail = os.path.splitdrive(requested)
    if tail in ("", os.sep) or requested in ("/", "\\"):
        raise BenchRefusedError(f"scan refused: full-drive root '{requested_path}'")
    allowlist: list[str] = []
    for entry in allowlist_dirs or []:
        if not isinstance(entry, str) or not entry:
            raise BenchRefusedError("scan refused: allowlist holds an empty entry")
        norm = _normalized_abs(entry)
        if not os.path.isabs(norm):
            raise BenchRefusedError(f"scan refused: allowlist entry not absolute: {entry!r}")
        allowlist.append(norm)
    def _under(base: str) -> bool:
        if requested == base:
            return True
        try:
            return os.path.commonpath([requested, base]) == base
        except ValueError:
            return False

    under_allowlist = any(_under(base) for base in allowlist)
    if not under_allowlist:
        raise BenchRefusedError(
            f"scan refused: '{requested_path}' is outside the scan allowlist"
        )
    separators = {os.sep}
    if os.altsep:
        separators.add(os.altsep)
    lowered = requested.lower()
    for sep in separators:
        lowered = lowered.replace(sep, "/")
    segments = set(lowered.split("/"))
    hit = segments & _FORBIDDEN_SEGMENTS
    if hit:
        raise BenchRefusedError(
            f"scan refused: forbidden path segment {sorted(hit)[0]!r} in '{requested_path}'"
        )
    if os.path.islink(requested_path) or os.path.realpath(requested_path) != os.path.abspath(
        requested_path
    ):
        raise BenchRefusedError(f"scan refused: symlink target '{requested_path}'")
    if not os.path.isdir(requested_path):
        raise BenchRefusedError(f"scan refused: not a directory: '{requested_path}'")
    return sorted(os.listdir(requested_path))


def calibrate(model_id: str, chat: object) -> Calibration:
    """Short timed calibration probe through the injected chat seam."""
    if not isinstance(model_id, str) or not model_id:
        raise ValueError(f"model_id must be a non-empty string, got {model_id!r}")
    chat_fn = getattr(chat, "chat", None)
    if not callable(chat_fn):
        raise TypeError("chat seam must expose chat(model_id, prompt) -> dict")
    prompt = f"bench-calibration-v1:{model_id}"
    start = time.perf_counter()
    reply = chat_fn(model_id, prompt)
    elapsed = time.perf_counter() - start
    if not isinstance(reply, dict):
        raise ValueError(f"chat seam must return a dict, got {type(reply).__name__}")
    return Calibration(model_id=model_id, seconds_per_case=max(elapsed, 1e-9))


def estimate_run(
    model_id: str, level: BenchLevel, calibration: Calibration
) -> BenchEstimate:
    """Per-model pre-run estimate driven by the calibration timing."""
    lvl = BenchLevel(level)
    if not isinstance(model_id, str) or not model_id:
        raise ValueError(f"model_id must be a non-empty string, got {model_id!r}")
    floor_lo, floor_hi = level_floor_minutes(lvl, _ESTIMATE_REFERENCE_PARAMS_B)
    factor = max(float(calibration.seconds_per_case), 0.0) / _NOMINAL_SECONDS_PER_CASE
    minutes_min = max(_MIN_ESTIMATE_MINUTES, floor_lo * factor)
    minutes_max = max(minutes_min, floor_hi * factor)
    return BenchEstimate(
        level=lvl, model_id=model_id, minutes_min=minutes_min, minutes_max=minutes_max
    )


#: --- Additive benchmark-steered split record (M-P4-129; new names only).
#: The queue_run benchmark path writes how deep the benchmark went; the
#: cloud-vs-local split decision reads it. With no benchmark recorded the
#: split stays fail-closed to cloud; with a benchmark, deeper measured
#: evidence steers local exactly like the adapter steering rule.
_STEER_LEVEL_DEPTH = {"quick": 0, "standard": 1, "deep": 2}

#: Pristine steer state: no benchmark, no level, zero depth.
_SPLIT_STEER_INITIAL = {"benchmarked": False, "level": None, "depth": 0}

#: Live steer state: replaced wholesale by _note_benchmark_steer.
_SPLIT_STEER: dict = dict(_SPLIT_STEER_INITIAL)


def split_steer_record() -> dict:
    """Steering record (M-P4-129): how deep the benchmark path went.

    Pristine until a benchmark run starts on the queue_run benchmark
    path (served POST /runs goes through start_run directly and leaves
    the record pristine): ``benchmarked`` False with no level. Written
    by the benchmark path, read by the split decision.
    """
    return dict(_SPLIT_STEER)


def _note_benchmark_steer(level: BenchLevel) -> None:
    """Record that a benchmark run started at a level (never raises)."""
    try:
        lvl = BenchLevel(level)
    except (ValueError, TypeError, AttributeError):
        return
    _SPLIT_STEER.clear()
    _SPLIT_STEER.update(
        {
            "benchmarked": True,
            "level": lvl.value,
            "depth": _STEER_LEVEL_DEPTH.get(lvl.value.lower(), 0),
        }
    )


def steered_split(summary: dict) -> dict:
    """Cloud-vs-local split steered by benchmark results (M-P4-129).

    With no benchmark recorded the verdict is fail-closed to cloud, even
    for a Deep measured summary. With a benchmark, the summary steers by
    the adapter steering rule: measured evidence beating proxy at
    Standard depth or deeper goes local, anything else stays cloud.
    """
    if not isinstance(summary, dict):
        raise TypeError(f"summary must be a dict, got {type(summary).__name__}")
    if not _SPLIT_STEER.get("benchmarked"):
        return {
            "split": "cloud",
            "reason": (
                "CLOUD: no benchmark recorded on the benchmark path; "
                "fail-closed to cloud"
            ),
        }
    return _adapter.recommend_split(summary)


def _reconcile_slot_on_skip() -> None:
    """Settle an in-flight run when a skip proves the gateway unreachable."""
    global _ACTIVE_RUN_ID
    if _ACTIVE_RUN_ID is not None:
        progress = _PROGRESS.get(_ACTIVE_RUN_ID)
        if progress is not None:
            progress.stopped = True
        _ACTIVE_RUN_ID = None
    _journal_append("slot_reconciled")


#: Task class for busy-skip safety evidence (R-360): the passive check
#: refusing a run while the machine is busy records ambient evidence.
_BUSY_SKIP_TASK_CLASS = "localbench:busy-skip"

#: Task-class family for run evidence rows (R-371): one per bench level.
_RUN_EVIDENCE_TASK_CLASS_PREFIX = "localbench:"


def _utc_now_iso() -> str:
    """Current UTC time as an ISO-8601 string for evidence rows."""
    return datetime.now(timezone.utc).isoformat()


def _hardware_fingerprint(hardware: HardwareProfile) -> str:
    """Stable fingerprint of a hardware snapshot (no machine paths)."""
    return "|".join(
        [
            str(hardware.gpu_vendor),
            str(hardware.gpu_model),
            str(hardware.vram_mb),
            str(hardware.ram_mb),
            str(hardware.cpu_only),
        ]
    )


def _record_busy_skip_evidence(model_id: str) -> None:
    """Record ambient evidence for a busy-skip (R-360); never raises.

    Best-effort: a store failure never breaks the busy refusal itself.
    """
    try:
        task_class = _BUSY_SKIP_TASK_CLASS
        _cap_store._register_row(
            _cap_store.CapabilityEvidenceRecord(
                model_id=model_id,
                task_class=task_class,
                tier=_cap_store.EvidenceTier.PROXY,
                score=None,
                score_type=None,
                sample_count=None,
                confidence=None,
                benchmark_version=None,
                measured_at=_utc_now_iso(),
                runtime="localbench",
                runtime_version=None,
                environment_fingerprint=None,
                freshness_state=_cap_store.FreshnessState.CURRENT.value,
                evidence_ref=f"cap:{model_id}:{task_class}:v1",
                source="localbench passive check",
            )
        )
    except Exception:
        return


def _record_run_proxy_evidence(
    model_id: str, level: BenchLevel, hardware: HardwareProfile
) -> None:
    """Record PROXY evidence for a started run (R-371); never raises.

    The row carries the run's hardware profile fingerprint while no
    benchmark measurement exists yet; a later MEASURED row for the same
    key supersedes it. Best-effort: never breaks the run start itself.
    """
    try:
        task_class = f"{_RUN_EVIDENCE_TASK_CLASS_PREFIX}{BenchLevel(level).value}"
        _cap_store._register_row(
            _cap_store.CapabilityEvidenceRecord(
                model_id=model_id,
                task_class=task_class,
                tier=_cap_store.EvidenceTier.PROXY,
                score=None,
                score_type=None,
                sample_count=None,
                confidence=None,
                benchmark_version=None,
                measured_at=_utc_now_iso(),
                runtime="localbench",
                runtime_version=None,
                environment_fingerprint=_hardware_fingerprint(hardware),
                freshness_state=_cap_store.FreshnessState.CURRENT.value,
                evidence_ref=f"cap:proxy:{model_id}:{task_class}:v1",
                source="localbench run start",
            )
        )
    except Exception:
        return


def _require_admission_refs(admission: dict) -> dict[str, str]:
    """Validate a caller-bound admission bundle (R-371).

    Returns the four admission refs; malformed bundles raise ValueError
    (programmer error, never a run refusal).
    """
    if not isinstance(admission, dict):
        raise ValueError(f"admission must be a refs dict, got {admission!r}")
    refs: dict[str, str] = {}
    for key in (
        "capability_store_ref",
        "health_ref",
        "gateway_state_ref",
        "permission_scope",
    ):
        value = admission.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"admission bundle needs a non-empty string {key!r}")
        refs[key] = value
    return refs


def start_run(
    model_id: str,
    level: BenchLevel,
    authorized: bool,
    admission: dict | None = None,
    chat_endpoint: str | None = None,
) -> RunHandle | RunSkip:
    """Start a serial run: passive check, then auth, then the busy guard.

    While the machine is busy the passive check skips with reason
    BUSY_SKIP: the skip records capability evidence, and nothing is
    pulled or deleted (R-360). Every started run carries its hardware
    profile snapshot with PROXY evidence until a benchmark measurement
    lands (R-371). When the caller binds the four admission refs, the
    run is admitted through the production admission path first and a
    refusal raises fail-closed with no run created; without refs the
    start behaves exactly as before. The optional chat_endpoint is the
    run-start chain winner (served POST body, else remembered check);
    without it the executor falls back to the env var, else stays idle.
    """
    lvl = BenchLevel(level)
    if not isinstance(model_id, str) or not model_id:
        raise ValueError(f"model_id must be a non-empty string, got {model_id!r}")
    if _OFFLINE_MARKER in model_id.lower():
        _reconcile_slot_on_skip()
        return RunSkip(
            reason=(
                f"gateway unreachable for model '{model_id}': model is marked "
                "offline (no reachable runtime); skipped without contact"
            )
        )
    if not authorized:
        raise BenchRefusedError(
            f"{SESSION_TOKEN_REFUSED}: run start needs a bound UI session token "
            "(x-actor + x-ui-session-token); state unchanged"
        )
    global _ACTIVE_RUN_ID
    if _ACTIVE_RUN_ID is not None:
        _record_busy_skip_evidence(model_id)
        raise BenchBusyError(
            f"BUSY_SKIP: serial one-model machine busy: run '{_ACTIVE_RUN_ID}' "
            "is active; wait or stop it first; skipped by the passive check "
            "without contact; nothing pulled or deleted; state unchanged"
        )
    admission_verdict = None
    if admission is not None:
        refs = _require_admission_refs(admission)
        admission_verdict = _adapter.check_admission(
            refs["capability_store_ref"],
            refs["health_ref"],
            refs["gateway_state_ref"],
            refs["permission_scope"],
        )
        if not admission_verdict.admitted:
            raise BenchRefusedError(
                f"{admission_verdict.reason}; state unchanged"
            )
    run_id = f"run-{next(_RUN_SEQ):04d}"
    handle = RunHandle(run_id=run_id, model_id=model_id, level=lvl)
    _RUNS[run_id] = handle
    _PROGRESS[run_id] = RunProgress(
        run_id=run_id,
        done_cases=0,
        total_cases=len(_bench_cases.list_cases(lvl)),
        paused=False,
        stopped=False,
    )
    _RUN_ROWS[run_id] = []
    _ACTIVE_RUN_ID = run_id
    hardware = detect_hardware()
    _RUN_HARDWARE[run_id] = hardware
    _record_run_proxy_evidence(model_id, lvl, hardware)
    if admission_verdict is not None:
        _RUN_ADMISSION[run_id] = admission_verdict
    _journal_append("start_run")
    _start_executor_thread(
        run_id, model_id, lvl, _resolve_bench_chat_endpoint(chat_endpoint)
    )
    return handle


def _require_progress(run_id: str) -> RunProgress:
    try:
        return _PROGRESS[run_id]
    except KeyError:
        raise KeyError(f"unknown run_id: {run_id!r}") from None


def pause_run(run_id: str) -> None:
    """Pause a live run; refused on unknown or already-stopped runs."""
    progress = _require_progress(run_id)
    if progress.stopped:
        raise BenchRefusedError(f"pause refused: run '{run_id}' already stopped")
    progress.paused = True
    _journal_append("pause_run")


def resume_run(run_id: str) -> None:
    """Resume a paused run; refused on unknown or already-stopped runs."""
    progress = _require_progress(run_id)
    if progress.stopped:
        raise BenchRefusedError(f"resume refused: run '{run_id}' already stopped")
    progress.paused = False
    _journal_append("resume_run")


def stop_run(run_id: str) -> None:
    """Stop a run and free the serial slot when it was the active run."""
    global _ACTIVE_RUN_ID
    progress = _require_progress(run_id)
    progress.stopped = True
    if _ACTIVE_RUN_ID == run_id:
        _ACTIVE_RUN_ID = None
    _journal_append("stop_run")


def run_progress(run_id: str) -> RunProgress:
    """Visible progress for a known run; KeyError on unknown run ids."""
    return _require_progress(run_id)


def run_result_rows(run_id: str) -> list[BenchResultRow]:
    """Rows recorded for a run (empty until a real run records rows)."""
    _require_progress(run_id)
    return list(_RUN_ROWS.get(run_id, []))


def run_hardware(run_id: str) -> HardwareProfile:
    """Hardware profile snapshot carried by a run (R-371).

    KeyError on unknown run ids, mirroring run_result_rows.
    """
    _require_progress(run_id)
    try:
        return _RUN_HARDWARE[run_id]
    except KeyError:
        raise KeyError(f"no hardware snapshot for run_id: {run_id!r}") from None


def run_admission(run_id: str) -> _adapter.AdmissionVerdict | None:
    """Admission verdict bound at run start (R-371), if refs were bound.

    None when the run started without an admission bundle; KeyError on
    unknown run ids, mirroring run_result_rows.
    """
    _require_progress(run_id)
    return _RUN_ADMISSION.get(run_id)


#: Warning code for a bench record whose floors promise real wall-clock
#: time (R-341): every scan record carries it.
_BENCH_DURATION_WARNING = "BENCH_DURATION"

#: Warning code for a bench record started while the PC is in use
#: (R-341): carried only when pc_in_use is true.
_BENCH_PC_IN_USE_WARNING = "BENCH_PC_IN_USE"


def bench_scan_record(
    allowlist_dirs: list[str],
    requested_path: str,
    model_id: str,
    model_params_b: float,
    level: BenchLevel | str,
    pc_in_use: bool,
    work_dir: str,
) -> dict:
    """Scan -> level -> run record with duration + warnings (R-341).

    Read-only model scan first (allowlist-first, never creds/browser/SSH
    paths), then the size-scaled level floors for the model, then the
    record: models found, level, floor range, warnings (BENCH_DURATION
    always, plus BENCH_PC_IN_USE while the PC is in use), scan
    duration, task class and evidence ref. The record lands in the
    capability base as MEASURED evidence so get_evidence(model_id,
    task_class) serves it and require_current(evidence_ref) resolves to
    the model. The work dir must be a real directory: the record belongs
    to a run workspace, never to a phantom path. Scan refusals raise
    BenchRefusedError; malformed inputs raise ValueError.
    """
    if not isinstance(model_id, str) or not model_id:
        raise ValueError(f"model_id must be a non-empty string, got {model_id!r}")
    try:
        lvl = BenchLevel(level)
    except (ValueError, TypeError, AttributeError):
        raise ValueError(f"level must be a bench level, got {level!r}") from None
    try:
        params_b = float(model_params_b)
    except (TypeError, ValueError):
        raise ValueError(
            f"model_params_b must be a number, got {model_params_b!r}"
        ) from None
    if isinstance(params_b, bool) or not params_b > 0.0 or params_b != params_b:
        raise ValueError(
            f"model_params_b must be a positive finite number, got {model_params_b!r}"
        )
    if not isinstance(pc_in_use, bool):
        raise ValueError(f"pc_in_use must be a bool, got {pc_in_use!r}")
    if not isinstance(work_dir, str) or not work_dir:
        raise ValueError(f"work_dir must be a non-empty string, got {work_dir!r}")
    if not os.path.isdir(work_dir):
        raise ValueError(f"work_dir is not a directory: {work_dir!r}")
    started = time.perf_counter()
    models = scan_models(allowlist_dirs, requested_path)
    duration_s = max(0.0, time.perf_counter() - started)
    floor_min, floor_max = level_floor_minutes(lvl, params_b)
    warnings = [
        {
            "code": _BENCH_DURATION_WARNING,
            "message": (
                f"level {lvl.value} floor promises "
                f"{floor_min:.1f}-{floor_max:.1f} minutes of wall-clock "
                "benchmark time"
            ),
        }
    ]
    if pc_in_use:
        warnings.append(
            {
                "code": _BENCH_PC_IN_USE_WARNING,
                "message": "PC is in use: benchmark shares the machine",
            }
        )
    task_class = f"localbench:scan:{lvl.value}"
    evidence_ref = f"cap:{model_id}:{task_class}:v1"
    hardware = detect_hardware()
    _cap_store._register_row(
        _cap_store.CapabilityEvidenceRecord(
            model_id=model_id,
            task_class=task_class,
            tier=_cap_store.EvidenceTier.MEASURED,
            score=float(len(models)),
            score_type="scanned_model_count",
            sample_count=len(models),
            confidence=1.0 if models else 0.0,
            benchmark_version=None,
            measured_at=_utc_now_iso(),
            runtime="localbench",
            runtime_version=None,
            environment_fingerprint=_hardware_fingerprint(hardware),
            freshness_state=_cap_store.FreshnessState.CURRENT.value,
            evidence_ref=evidence_ref,
            source=os.path.abspath(requested_path),
        )
    )
    return {
        "models": models,
        "level": lvl.value,
        "floor_minutes_min": floor_min,
        "floor_minutes_max": floor_max,
        "warnings": warnings,
        "duration_s": duration_s,
        "evidence_ref": evidence_ref,
        "task_class": task_class,
        "work_dir": work_dir,
    }


def list_run_ids() -> list[str]:
    """Known run ids in start order (history read)."""
    return sorted(_RUNS)


def pull_model(model_id: str, authorized: bool) -> None:
    """Never pull without explicit user auth; pulls run via HD gateway only."""
    if not authorized:
        raise BenchRefusedError(
            f"{SESSION_TOKEN_REFUSED}: model pulls need explicit user authorization "
            "(x-actor + x-ui-session-token); nothing pulled"
        )
    raise BenchRefusedError(
        f"pull refused: model '{model_id}' pulls run only via the HD gateway "
        "with explicit user authorization; no pull performed here"
    )


#: --- Additive Manager scheduler queue (B0B-UNCOVERED_ARCH-189/767, SPEC 38).
#: The serial machine still admits at most one active run and start_run keeps
#: refusing busy; excess demand waits here instead. Safety caps (auth,
#: forbidden path, pull) are non-count limits and still raise — only the busy
#: count-limit queues. Every queued item and every active run carries an
#: owner plus an expiry measured on the real clock (time.monotonic).
MAX_ACTIVE_RUNS = 1
MAX_QUEUED_RESERVATIONS = 16
DEFAULT_RESERVATION_TTL_S = 600.0
DEFAULT_LEASE_TTL_S = 600.0


@dataclass
class RunReservation:
    """Queued demand: owner + expiry; promoted FIFO when the slot frees."""

    reservation_id: str
    owner: str
    model_id: str
    level: BenchLevel
    created_at: float
    expires_at: float
    status: str


@dataclass
class RunLease:
    """Active-run hold: owner + expiry; at most MAX_ACTIVE_RUNS are live."""

    lease_id: str
    run_id: str
    owner: str
    created_at: float
    expires_at: float
    released: bool = False


_RESERVATION_SEQ = itertools.count(1)
_LEASE_SEQ = itertools.count(1)
_RESERVATIONS: dict[str, RunReservation] = {}
_QUEUE: list[str] = []
_LEASES: dict[str, RunLease] = {}
_RUN_LEASE: dict[str, str] = {}


def _now_s() -> float:
    """Real-clock seconds for scheduler expiry (tests sleep past short TTLs)."""
    return time.monotonic()


def _require_owner(owner: str) -> str:
    if not isinstance(owner, str) or not owner:
        raise ValueError(f"owner must be a non-empty string, got {owner!r}")
    return owner


def _require_ttl(ttl_s: float, name: str) -> float:
    try:
        value = float(ttl_s)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a positive finite number of seconds") from None
    if not value > 0.0 or value in (float("inf"), float("-inf")) or value != value:
        raise ValueError(f"{name} must be a positive finite number of seconds")
    return value


def _live_queue(now: float) -> list[str]:
    """Queued, unexpired reservation ids in FIFO order (marks the expired)."""
    live: list[str] = []
    for rid in _QUEUE:
        rsv = _RESERVATIONS.get(rid)
        if rsv is None or rsv.status != "queued":
            continue
        if rsv.expires_at <= now:
            rsv.status = "expired"
            continue
        live.append(rid)
    return live


def _create_lease(run_id: str, owner: str, ttl_s: float, now: float) -> RunLease:
    lease_id = f"lease-{next(_LEASE_SEQ):04d}"
    lease = RunLease(
        lease_id=lease_id,
        run_id=run_id,
        owner=owner,
        created_at=now,
        expires_at=now + ttl_s,
    )
    _LEASES[lease_id] = lease
    _RUN_LEASE[run_id] = lease_id
    return lease


def queue_run(
    model_id: str,
    level: BenchLevel,
    authorized: bool,
    owner: str,
    ttl_s: float = DEFAULT_RESERVATION_TTL_S,
    lease_ttl_s: float = DEFAULT_LEASE_TTL_S,
) -> RunHandle | RunSkip | RunReservation:
    """Scheduler entry: start now when the slot is free, else queue.

    Offline models skip (never queued); safety refusals (unauthorized) raise
    BenchRefusedError and queue nothing. A busy machine queues a
    reservation carrying owner + expiry instead of refusing, unless the
    queue itself is full (BenchBusyError). A free slot with no live queue
    starts through start_run and attaches an owner+expiry lease.
    """
    lvl = BenchLevel(level)
    if not isinstance(model_id, str) or not model_id:
        raise ValueError(f"model_id must be a non-empty string, got {model_id!r}")
    if _OFFLINE_MARKER in model_id.lower():
        _reconcile_slot_on_skip()
        return RunSkip(
            reason=(
                f"gateway unreachable for model '{model_id}': model is marked "
                "offline (no reachable runtime); skipped without contact"
            )
        )
    if not authorized:
        raise BenchRefusedError(
            f"{SESSION_TOKEN_REFUSED}: run queue needs a bound UI session token "
            "(x-actor + x-ui-session-token); state unchanged"
        )
    _require_owner(owner)
    ttl = _require_ttl(ttl_s, "ttl_s")
    lease_ttl = _require_ttl(lease_ttl_s, "lease_ttl_s")
    now = _now_s()
    live = _live_queue(now)
    if _ACTIVE_RUN_ID is None and not live:
        handle = start_run(model_id, lvl, True)
        assert isinstance(handle, RunHandle)
        _note_benchmark_steer(lvl)
        _create_lease(handle.run_id, owner, lease_ttl, now)
        _journal_append("queue_run_started")
        return handle
    if len(live) >= MAX_QUEUED_RESERVATIONS:
        raise BenchBusyError(
            f"scheduler queue full ({MAX_QUEUED_RESERVATIONS} waiting); "
            "state unchanged"
        )
    reservation_id = f"rsv-{next(_RESERVATION_SEQ):04d}"
    made = _now_s()
    reservation = RunReservation(
        reservation_id=reservation_id,
        owner=owner,
        model_id=model_id,
        level=lvl,
        created_at=made,
        expires_at=made + ttl,
        status="queued",
    )
    _RESERVATIONS[reservation_id] = reservation
    _QUEUE.append(reservation_id)
    _journal_append("reservation_queued")
    return reservation


def pump_queue(lease_ttl_s: float = DEFAULT_LEASE_TTL_S) -> RunHandle | None:
    """Promote the oldest live reservation when the slot is free.

    Returns the new RunHandle (with an owner+expiry lease), or None when
    the machine is busy or no live reservation waits. Expired waiters are
    marked expired and skipped. Never starts a second parallel run.
    """
    lease_ttl = _require_ttl(lease_ttl_s, "lease_ttl_s")
    now = _now_s()
    if _ACTIVE_RUN_ID is not None:
        return None
    while _QUEUE:
        rid = _QUEUE[0]
        rsv = _RESERVATIONS.get(rid)
        if rsv is None or rsv.status != "queued":
            _QUEUE.pop(0)
            continue
        if rsv.expires_at <= now:
            rsv.status = "expired"
            _QUEUE.pop(0)
            continue
        _QUEUE.pop(0)
        handle = start_run(rsv.model_id, rsv.level, True)
        assert isinstance(handle, RunHandle)
        _note_benchmark_steer(rsv.level)
        rsv.status = "promoted"
        _create_lease(handle.run_id, rsv.owner, lease_ttl, _now_s())
        _journal_append("pump_promoted")
        return handle
    _journal_append("pump_sweep")
    return None


def cancel_reservation(reservation_id: str, owner: str) -> RunReservation:
    """Cancel a queued reservation; only its owner may cancel it."""
    try:
        rsv = _RESERVATIONS[reservation_id]
    except KeyError:
        raise KeyError(f"unknown reservation_id: {reservation_id!r}") from None
    if rsv.owner != owner:
        raise BenchRefusedError(
            f"cancel refused: reservation '{reservation_id}' is owned by "
            f"'{rsv.owner}'; state unchanged"
        )
    if rsv.status != "queued":
        raise BenchRefusedError(
            f"cancel refused: reservation '{reservation_id}' is {rsv.status}; "
            "state unchanged"
        )
    rsv.status = "cancelled"
    try:
        _QUEUE.remove(reservation_id)
    except ValueError:
        pass
    _journal_append("reservation_cancelled")
    return rsv


def list_reservations() -> list[RunReservation]:
    """All reservation records in request order (history read)."""
    return [_RESERVATIONS[rid] for rid in sorted(_RESERVATIONS)]


def lease_for_run(run_id: str) -> RunLease | None:
    """Lease attached to a run, or None when the run holds no lease."""
    lease_id = _RUN_LEASE.get(run_id)
    if lease_id is None:
        return None
    return _LEASES.get(lease_id)


def _require_lease(lease_id: str) -> RunLease:
    try:
        return _LEASES[lease_id]
    except KeyError:
        raise KeyError(f"unknown lease_id: {lease_id!r}") from None


def lease_is_live(lease_id: str) -> bool:
    """A lease is live while unreleased, unexpired, and holding the slot."""
    lease = _require_lease(lease_id)
    if lease.released:
        return False
    if lease.expires_at <= _now_s():
        return False
    return _ACTIVE_RUN_ID == lease.run_id


def renew_lease(
    lease_id: str, owner: str, ttl_s: float = DEFAULT_LEASE_TTL_S
) -> RunLease:
    """Extend a live lease; only its owner may renew it."""
    lease = _require_lease(lease_id)
    if lease.owner != owner:
        raise BenchRefusedError(
            f"renew refused: lease '{lease_id}' is owned by "
            f"'{lease.owner}'; state unchanged"
        )
    if not lease_is_live(lease_id):
        raise BenchRefusedError(
            f"renew refused: lease '{lease_id}' is no longer live; "
            "state unchanged"
        )
    lease.expires_at = _now_s() + _require_ttl(ttl_s, "ttl_s")
    _journal_append("lease_renewed")
    return lease


def release_lease(lease_id: str, owner: str) -> RunLease:
    """Release a lease; only its owner may release it (idempotent)."""
    lease = _require_lease(lease_id)
    if lease.owner != owner:
        raise BenchRefusedError(
            f"release refused: lease '{lease_id}' is owned by "
            f"'{lease.owner}'; state unchanged"
        )
    lease.released = True
    _journal_append("lease_released")
    return lease


#: --- Additive M-BENCH restart journal (K05R5 M-BENCH leak 1; new names only).
#: Scheduler state above lives in module dicts: a process exit loses the
#: active run, the FIFO queue and every lease/reservation. This section
#: persists that state to a journal file (one JSON snapshot line per
#: mutation) and rebuilds it after a restart. Existing dicts, counters and
#: every public signature above are unchanged. Journal durability is
#: best-effort: an unwritable journal never breaks scheduling; recovery
#: reads the last complete snapshot line and ignores torn tail lines.
JOURNAL_ENV_VAR = "AGENT_SI_BENCH_JOURNAL"

_JOURNAL_SCHEMA_V = 1

#: Explicit journal path override (tests); None means read the env var.
_JOURNAL_PATH_OVERRIDE: str | None = None


def set_journal_path(path: str | None) -> None:
    """Point the scheduler journal at a file; None clears the override.

    The override wins over $AGENT_SI_BENCH_JOURNAL for the process. The env
    var (read live on every access) is the restart-proof channel: it
    survives module reloads and process restarts, the override does not.
    """
    global _JOURNAL_PATH_OVERRIDE
    if path is not None and (not isinstance(path, str) or not path):
        raise ValueError(f"journal path must be a non-empty string, got {path!r}")
    _JOURNAL_PATH_OVERRIDE = path


def journal_path() -> str | None:
    """Active journal file: the override, else $AGENT_SI_BENCH_JOURNAL, else None."""
    if _JOURNAL_PATH_OVERRIDE is not None:
        return _JOURNAL_PATH_OVERRIDE
    env = os.environ.get(JOURNAL_ENV_VAR)
    if isinstance(env, str) and env:
        return env
    return None


def _journal_snapshot_dict(event: str) -> dict:
    """Full scheduler snapshot with TTLs stored as remaining seconds."""
    now = _now_s()
    return {
        "v": _JOURNAL_SCHEMA_V,
        "event": event,
        "wall_at": time.time(),
        "active_run_id": _ACTIVE_RUN_ID,
        "runs": [
            {
                "run_id": rid,
                "model_id": handle.model_id,
                "level": handle.level.value,
            }
            for rid, handle in _RUNS.items()
        ],
        "progress": [
            {
                "run_id": rid,
                "done_cases": prog.done_cases,
                "total_cases": prog.total_cases,
                "paused": prog.paused,
                "stopped": prog.stopped,
            }
            for rid, prog in _PROGRESS.items()
        ],
        "reservations": [
            {
                "reservation_id": rsv.reservation_id,
                "owner": rsv.owner,
                "model_id": rsv.model_id,
                "level": rsv.level.value,
                "expires_in_s": rsv.expires_at - now,
                "status": rsv.status,
            }
            for rsv in _RESERVATIONS.values()
        ],
        "queue": [rid for rid in _QUEUE],
        "leases": [
            {
                "lease_id": lease.lease_id,
                "run_id": lease.run_id,
                "owner": lease.owner,
                "expires_in_s": lease.expires_at - now,
                "released": lease.released,
            }
            for lease in _LEASES.values()
        ],
        "run_lease": {run_id: lease_id for run_id, lease_id in _RUN_LEASE.items()},
    }


def _journal_append(event: str) -> None:
    """Append one snapshot line; best-effort, never raises into scheduling."""
    path = journal_path()
    if path is None:
        return
    try:
        line = json.dumps(_journal_snapshot_dict(event), sort_keys=True)
    except (TypeError, ValueError):
        return
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        return


def _journal_id_num(prefix: str, value: object) -> int | None:
    """Numeric suffix of a generated id (run-0007 -> 7), else None."""
    if not isinstance(value, str) or not value.startswith(prefix):
        return None
    try:
        return int(value[len(prefix):])
    except ValueError:
        return None


def _journal_finite(value: object) -> float | None:
    """Finite float of a journal TTL-ish value, else None (fail-closed)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _journal_rebind_counters(run_max: int, rsv_max: int, lease_max: int) -> None:
    """Move the id counters past every restored id (no post-restart clash)."""
    global _RUN_SEQ, _RESERVATION_SEQ, _LEASE_SEQ
    if run_max >= 1:
        _RUN_SEQ = itertools.count(run_max + 1)
    if rsv_max >= 1:
        _RESERVATION_SEQ = itertools.count(rsv_max + 1)
    if lease_max >= 1:
        _LEASE_SEQ = itertools.count(lease_max + 1)


def recover_journal() -> dict:
    """Rebuild scheduler state from the journal file; reconcile restart effects.

    Last complete snapshot wins; torn tail lines are ignored. Queued
    reservations whose TTL survived the restart (decayed by wall clock)
    return to the FIFO; the rest expire. The interrupted active run is
    restored to history but settled stopped with the serial slot freed:
    nothing executes after a kill (same settlement as
    _reconcile_slot_on_skip). Leases restore with decayed TTLs. A missing,
    empty or fully torn journal touches nothing. Replaces live scheduler
    memory (restart use): call once at startup before scheduling. Returns
    {"restored_runs", "restored_queued", "expired", "interrupted_run_id"}.
    """
    report: dict = {
        "restored_runs": 0,
        "restored_queued": 0,
        "expired": 0,
        "interrupted_run_id": None,
    }
    path = journal_path()
    if path is None:
        return report
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw_lines = fh.read().splitlines()
    except OSError:
        return report
    snap: dict | None = None
    for line in raw_lines:
        if not line.strip():
            continue
        try:
            cand = json.loads(line)
        except ValueError:
            continue
        if (
            isinstance(cand, dict)
            and cand.get("v") == _JOURNAL_SCHEMA_V
            and isinstance(cand.get("runs"), list)
            and isinstance(cand.get("progress"), list)
            and isinstance(cand.get("reservations"), list)
            and isinstance(cand.get("queue"), list)
            and isinstance(cand.get("leases"), list)
            and isinstance(cand.get("run_lease"), dict)
        ):
            snap = cand
    if snap is None:
        return report
    now = _now_s()
    try:
        wall_at = float(snap.get("wall_at", 0.0))
    except (TypeError, ValueError):
        wall_at = 0.0
    elapsed = max(0.0, time.time() - wall_at) if wall_at > 0 else 0.0
    runs: dict[str, RunHandle] = {}
    prog: dict[str, RunProgress] = {}
    run_max = 0
    for entry in snap["runs"]:
        try:
            rid = entry["run_id"]
            mid = entry["model_id"]
            lvl = BenchLevel(entry["level"])
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
        if not isinstance(rid, str) or not rid:
            continue
        if not isinstance(mid, str) or not mid:
            continue
        runs[rid] = RunHandle(run_id=rid, model_id=mid, level=lvl)
        num = _journal_id_num("run-", rid)
        if num is not None and num > run_max:
            run_max = num
    for entry in snap["progress"]:
        try:
            rid = entry["run_id"]
            done = entry["done_cases"]
            total = entry["total_cases"]
            paused = entry["paused"]
            stopped = entry["stopped"]
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
        if not isinstance(rid, str) or rid not in runs:
            continue
        if (
            not isinstance(done, int)
            or isinstance(done, bool)
            or not isinstance(total, int)
            or isinstance(total, bool)
            or not isinstance(paused, bool)
            or not isinstance(stopped, bool)
        ):
            continue
        prog[rid] = RunProgress(
            run_id=rid,
            done_cases=done,
            total_cases=total,
            paused=paused,
            stopped=stopped,
        )
    for rid, handle in runs.items():
        if rid not in prog:
            prog[rid] = RunProgress(
                run_id=rid,
                done_cases=0,
                total_cases=len(_bench_cases.list_cases(handle.level)),
                paused=False,
                stopped=True,
            )
    reservations: dict[str, RunReservation] = {}
    rsv_max = 0
    expired = 0
    for entry in snap["reservations"]:
        try:
            rsid = entry["reservation_id"]
            owner = entry["owner"]
            mid = entry["model_id"]
            lvl = BenchLevel(entry["level"])
            remain_raw = entry["expires_in_s"]
            status = entry["status"]
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
        remain = _journal_finite(remain_raw)
        if remain is None:
            continue
        if (
            not isinstance(rsid, str)
            or not rsid
            or not isinstance(owner, str)
            or not owner
            or not isinstance(mid, str)
            or not mid
            or status not in ("queued", "promoted", "cancelled", "expired")
        ):
            continue
        if status == "queued" and remain - elapsed <= 0:
            status = "expired"
            expired += 1
        created_at = now - elapsed
        reservations[rsid] = RunReservation(
            reservation_id=rsid,
            owner=owner,
            model_id=mid,
            level=lvl,
            created_at=created_at,
            expires_at=created_at + remain,
            status=status,
        )
        num = _journal_id_num("rsv-", rsid)
        if num is not None and num > rsv_max:
            rsv_max = num
    queue = [
        rid
        for rid in snap["queue"]
        if isinstance(rid, str)
        and rid in reservations
        and reservations[rid].status == "queued"
    ]
    leases: dict[str, RunLease] = {}
    lease_max = 0
    for entry in snap["leases"]:
        try:
            lid = entry["lease_id"]
            run_id = entry["run_id"]
            owner = entry["owner"]
            remain_raw = entry["expires_in_s"]
            released = entry["released"]
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
        remain = _journal_finite(remain_raw)
        if remain is None:
            continue
        if (
            not isinstance(lid, str)
            or not lid
            or not isinstance(run_id, str)
            or not run_id
            or not isinstance(owner, str)
            or not owner
            or not isinstance(released, bool)
        ):
            continue
        created_at = now - elapsed
        leases[lid] = RunLease(
            lease_id=lid,
            run_id=run_id,
            owner=owner,
            created_at=created_at,
            expires_at=created_at + remain,
            released=released,
        )
        num = _journal_id_num("lease-", lid)
        if num is not None and num > lease_max:
            lease_max = num
    run_lease = {
        run_id: lease_id
        for run_id, lease_id in snap["run_lease"].items()
        if isinstance(run_id, str)
        and isinstance(lease_id, str)
        and run_id in runs
        and lease_id in leases
    }
    _RUNS.clear()
    _RUNS.update(runs)
    _PROGRESS.clear()
    _PROGRESS.update(prog)
    _RESERVATIONS.clear()
    _RESERVATIONS.update(reservations)
    _QUEUE[:] = queue
    _LEASES.clear()
    _LEASES.update(leases)
    _RUN_LEASE.clear()
    _RUN_LEASE.update(run_lease)
    global _ACTIVE_RUN_ID
    _ACTIVE_RUN_ID = None
    interrupted = None
    snap_active = snap.get("active_run_id")
    if isinstance(snap_active, str) and snap_active in _RUNS:
        current = _PROGRESS.get(snap_active)
        if current is not None:
            current.stopped = True
        interrupted = snap_active
    report = {
        "restored_runs": len(runs),
        "restored_queued": len(queue),
        "expired": expired,
        "interrupted_run_id": interrupted,
    }
    _journal_rebind_counters(run_max, rsv_max, lease_max)
    _journal_append("recovered")
    return report


#: --- Additive K05R7 M-PROBE bench seam (M-D-D15/M-D-D41; new names only). ---
#: Offline probe envs live in agent_si.local.k05r7_probe_envs and resolve
#: ONLY from AGENT_SI_PROBE_* entries; product-infra env
#: (AGENT_SI_BENCH_JOURNAL and every other non-probe AGENT_SI_* name) never
#: affects probe resolution. Every probe target/socket is loopback-only and
#: the host check below fails closed before any external contact. This
#: section only adds new names; every existing name/signature above is
#: unchanged.
from agent_si.local import k05r7_probe_envs as _k05r7_probe_envs


class K05R7ProbeRefusedError(BenchRefusedError):
    """Fail-closed K05R7 probe refusal: non-loopback/unparsable/unreachable."""


@dataclass
class K05R7ProbeSkip:
    """Skip-style K05R7 probe outcome; no contact was made."""

    reason: str


def k05r7_resolve_probe_env(
    environ=None,
) -> _k05r7_probe_envs.ProbeEnv:
    """Probe knobs from AGENT_SI_PROBE_* only; product infra env ignored."""
    return _k05r7_probe_envs.resolve_probe_env(environ)


def k05r7_probe_snapshot(environ=None) -> dict:
    """Only the AGENT_SI_PROBE_* entries; product infra env never appears."""
    return _k05r7_probe_envs.probe_env_snapshot(environ)


def k05r7_probe_targets(environ=None) -> tuple[tuple[str, int, str], ...]:
    """Loopback-only probe targets; non-loopback env yields no targets."""
    return _k05r7_probe_envs.probe_targets(environ)


def k05r7_guard_probe_endpoint(
    endpoint: str | None = None,
    environ=None,
) -> str:
    """Fail-closed host check before any contact; raises K05R7ProbeRefusedError."""
    try:
        return _k05r7_probe_envs.guard_probe_endpoint(endpoint, environ)
    except _k05r7_probe_envs.ProbeRefusedError as exc:
        raise K05R7ProbeRefusedError(str(exc)) from None


def k05r7_check_probe_endpoint(
    endpoint: str | None = None,
    environ=None,
) -> str | K05R7ProbeSkip:
    """Skip-style guard: normalized endpoint, or K05R7ProbeSkip (never raises)."""
    try:
        return _k05r7_probe_envs.guard_probe_endpoint(endpoint, environ)
    except _k05r7_probe_envs.ProbeRefusedError as exc:
        return K05R7ProbeSkip(reason=str(exc))


#: --- Additive OC-K05 bench->telemetry bridge (L2-D06b; new names only). ---
#: Bench runs never touched the telemetry store, so S06 totals stayed empty
#: even with bench evidence on disk. complete_run() records finished rows and
#: appends bench metric records (bench_runs/bench_cases) to the bound
#: telemetry store, making bench evidence visible to
#: GET /api/v1/analytics/telemetry. Metrics-only (no new event_type: the
#: TelemetryEvent vocabulary is frozen). Existing names/signatures above are
#: unchanged.
BENCH_TELEMETRY_SOURCE = "localbench/bench_runner"
BENCH_RUNS_METRIC = "bench_runs"
BENCH_CASES_METRIC = "bench_cases"


def complete_run(
    run_id: str,
    rows: list,
    project_id: str = "localbench",
) -> dict:
    """Finish a run: store rows, free the slot, record bench telemetry.

    Raises KeyError on unknown run ids, ValueError on empty/non-row lists.
    Telemetry append is best-effort: with no bound store dir it is skipped
    and the run still completes (returned ids lists stay empty then).
    """
    from agent_si.local.bench_protocol import BenchResultRow as _BenchRow

    progress = _require_progress(run_id)
    if not isinstance(rows, list) or not rows:
        raise ValueError(
            f"complete_run needs a non-empty row list, got {type(rows).__name__}"
        )
    for row in rows:
        if not isinstance(row, _BenchRow):
            raise ValueError(
                "complete_run rows must be BenchResultRow, "
                f"got {type(row).__name__}"
            )
    stored = _RUN_ROWS.setdefault(run_id, [])
    stored.extend(rows)
    progress.done_cases = len(stored)
    progress.stopped = True
    global _ACTIVE_RUN_ID
    if run_id == _ACTIVE_RUN_ID:
        _ACTIVE_RUN_ID = None
    _journal_append("complete_run")
    outcome: dict = {"run_id": run_id, "rows": len(stored),
                     "metric_ids": [], "event_id": None}
    try:
        from agent_si.telemetry import run_store as _run_store
        from agent_si.telemetry.metrics import MetricRecord as _MetricRecord
        from agent_si.telemetry.metrics import MetricState as _MetricState
    except ImportError:
        return outcome
    try:
        import datetime as _dt
        import uuid as _uuid

        now = _dt.datetime.now(_dt.UTC).isoformat()
        pid = str(project_id or "localbench")
        metrics = [
            _run_store._metric_to_json(
                _MetricRecord(
                    metric_id=f"m-{_uuid.uuid4().hex}",
                    project_id=pid,
                    metric_name=BENCH_RUNS_METRIC,
                    value=1,
                    unit="count",
                    state=_MetricState.MEASURED,
                    source=BENCH_TELEMETRY_SOURCE,
                    run_id=run_id,
                    recorded_at=now,
                )
            ),
            _run_store._metric_to_json(
                _MetricRecord(
                    metric_id=f"m-{_uuid.uuid4().hex}",
                    project_id=pid,
                    metric_name=BENCH_CASES_METRIC,
                    value=len(stored),
                    unit="count",
                    state=_MetricState.MEASURED,
                    source=BENCH_TELEMETRY_SOURCE,
                    run_id=run_id,
                    recorded_at=now,
                )
            ),
        ]
        stored_doc = _run_store.append_records(metrics, [])
        names = {
            row.get("metric_id")
            for row in stored_doc.get("metric_records", [])
            if isinstance(row, dict)
        }
        outcome["metric_ids"] = [
            row["metric_id"] for row in metrics if row["metric_id"] in names
        ]
    except Exception:
        pass
    return outcome

#: --- Additive F10 background executor (FB2B8; new names only). ---
#: start_run spawns one daemon thread per run; the thread walks the run's
#: frozen slice over loopback-only chat, appends one BenchResultRow per
#: case with its deterministic score, honours pause/stop, and on full
#: completion writes the MEASURED base row via the adapter seam. Contact
#: Contact
#: is loopback-only through the run-start resolved endpoint (served POST
#: body, else remembered check, else env var) used via the chat seam;
#: with no endpoint resolved the thread returns at once and the run keeps
#: today's semantics (active until stopped, no rows). Never real Ollama,
#: never non-loopback.
BENCH_CHAT_ENDPOINT_ENV = "AGENT_SI_BENCH_CHAT_ENDPOINT"

#: Per-attempt loopback chat timeout: the loopback endpoint answers fast;
#: a hung runtime never hangs the executor past stop.
_BENCH_CHAT_TIMEOUT_S = 5.0

#: Pause-wait granularity: a stop arriving during a pause aborts fast.
_BENCH_EXECUTOR_PAUSE_POLL_S = 0.05

#: Reply text kept per row: the leading chars of the scored reply.
_BENCH_REPLY_EXCERPT_CHARS = 200

#: Executor threads by run id (daemon; spawned by start_run, never joined
#: by the product: tests join them through this registry).
_RUN_THREADS: dict[str, threading.Thread] = {}


def bench_chat_endpoint() -> str | None:
    """Loopback chat endpoint from the env var (chain fallback).

    Reads the env var live; None means no runtime is configured and the
    executor performs no contact at all.
    """
    raw = os.environ.get(BENCH_CHAT_ENDPOINT_ENV, "")
    if not isinstance(raw, str) or not raw.strip():
        return None
    return raw.strip()


def _resolve_bench_chat_endpoint(chat_endpoint: str | None) -> str | None:
    """Run-start endpoint chain: explicit start arg wins, else env var.

    The served POST body (else the remembered check endpoint) arrives as
    the explicit arg; None/blank falls back to the env var; None means no
    runtime is configured and the executor performs no contact at all.
    """
    if isinstance(chat_endpoint, str) and chat_endpoint.strip():
        return chat_endpoint.strip()
    return bench_chat_endpoint()


class _EndpointChat:
    """chat-seam object bound to one loopback endpoint (executor use).

    Exposes the calibrate seam shape chat(model_id, prompt) -> dict over
    the run-start resolved endpoint.
    """

    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint

    def chat(self, model_id: str, prompt: str) -> dict:
        """One chat turn through the bound loopback endpoint."""
        return _loopback_chat(model_id, prompt, self.endpoint)


def _guard_loopback_chat_endpoint(endpoint: str) -> tuple[str, int, str]:
    """Split a chat endpoint into (host, port, path); loopback http only.

    Anything unparsable, non-http or non-loopback refuses fail-closed:
    the executor never contacts it.
    """
    try:
        parts = urlparse(endpoint if "://" in endpoint else f"http://{endpoint}")
    except ValueError as exc:
        raise BenchRefusedError(
            f"bench chat refused: unparsable endpoint {endpoint!r}; state unchanged"
        ) from exc
    if (parts.scheme or "http").lower() != "http":
        raise BenchRefusedError(
            f"bench chat refused: endpoint {endpoint!r} is not plain http; "
            "state unchanged"
        )
    host = (parts.hostname or "").lower()
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise BenchRefusedError(
            f"bench chat refused: endpoint {endpoint!r} is not loopback; "
            "state unchanged"
        )
    return host, parts.port or 80, parts.path or "/"


def _loopback_chat(model_id: str, prompt: str, endpoint: str) -> dict:
    """One chat turn over loopback HTTP only; refuses instead of reaching out.

    POSTs {"model", "prompt"} JSON to the run-start resolved endpoint and
    returns the reply dict (the calibrate chat seam contract:
    chat(model_id, prompt) -> dict). Anything unparsable, non-http or
    non-loopback refuses fail-closed; raises on unreachable runtimes,
    non-200 answers, non-JSON bodies or non-dict replies.
    """
    if not isinstance(endpoint, str) or not endpoint.strip():
        raise BenchRefusedError(
            "bench chat refused: no loopback chat endpoint configured "
            f"({BENCH_CHAT_ENDPOINT_ENV} is unset); state unchanged"
        )
    host, port, path = _guard_loopback_chat_endpoint(endpoint.strip())
    body = json.dumps({"model": model_id, "prompt": prompt}).encode("utf-8")
    try:
        conn = http.client.HTTPConnection(host, port, timeout=_BENCH_CHAT_TIMEOUT_S)
        try:
            conn.request(
                "POST",
                path,
                body,
                {
                    "Content-Type": "application/json",
                    "Content-Length": str(len(body)),
                },
            )
            response = conn.getresponse()
            status = response.status
            raw = response.read()
        finally:
            conn.close()
    except OSError as exc:
        raise BenchRefusedError(
            f"bench chat refused: loopback runtime unreachable ({exc}); "
            "state unchanged"
        ) from exc
    if status != 200:
        raise BenchRefusedError(
            f"bench chat refused: loopback runtime answered HTTP {status}; "
            "state unchanged"
        )
    try:
        reply = json.loads(raw.decode("utf-8"))
    except ValueError as exc:
        raise BenchRefusedError(
            "bench chat refused: loopback runtime answered non-JSON; "
            "state unchanged"
        ) from exc
    if not isinstance(reply, dict):
        raise ValueError(
            f"chat seam must return a dict, got {type(reply).__name__}"
        )
    return reply


def _bench_reply_text(reply: dict) -> str:
    """Deterministic reply text for scoring: first known text key, else JSON."""
    for key in ("response", "text", "output", "content"):
        value = reply.get(key)
        if isinstance(value, str) and value:
            return value
    return json.dumps(reply, sort_keys=True)


def _bench_parse_numbers(text: str) -> list[int] | None:
    """Strict comma-separated integers, else None (no stray content)."""
    parts = [part.strip() for part in text.strip().split(",")]
    if not parts or any(not part for part in parts):
        return None
    try:
        return [int(part) for part in parts]
    except ValueError:
        return None


def _bench_score_reply(rule: str, reply_text: str) -> float:
    """Score one reply against its frozen expected-answer rule.

    Returns checks passed / checks, derived only from the reply text:
    exact text, case-insensitive text, JSON object plus required keys,
    single word plus word match, parsed numbers plus ascending order.
    Unknown rules raise (fail-closed: never a score not from the reply).
    """
    text = reply_text if isinstance(reply_text, str) else ""
    kind, _, arg = rule.partition(":") if isinstance(rule, str) else ("", "", "")
    checks: list[bool] = []
    if kind == "exact" and arg != "":
        checks = [text.strip() == arg]
    elif kind == "exact-ci" and arg != "":
        checks = [text.strip().casefold() == arg.strip().casefold()]
    elif kind == "json-keys":
        keys = [part.strip() for part in arg.split(",") if part.strip()]
        if not keys:
            raise ValueError(f"unknown bench expected-answer rule {rule!r}")
        try:
            document = json.loads(text)
        except ValueError:
            document = None
        checks = [
            isinstance(document, dict),
            isinstance(document, dict)
            and all(key in document for key in keys),
        ]
    elif kind == "one-word" and arg != "":
        tokens = text.split()
        checks = [
            len(tokens) == 1,
            len(tokens) == 1 and tokens[0].casefold() == arg.strip().casefold(),
        ]
    elif kind == "numbers-asc":
        try:
            want = [int(part) for part in arg.split(",")]
        except ValueError:
            want = None
        got = _bench_parse_numbers(text)
        checks = [got is not None, got is not None and got == want]
    else:
        raise ValueError(f"unknown bench expected-answer rule {rule!r}")
    passed = sum(1 for check in checks if check)
    return passed / len(checks)


def _executor_wait_while_paused(progress: RunProgress) -> bool:
    """Wait while a run is paused; False when the run stopped meanwhile."""
    while progress.paused and not progress.stopped:
        time.sleep(_BENCH_EXECUTOR_PAUSE_POLL_S)
    return not progress.stopped


def _executor_settle(run_id: str, completed: bool) -> None:
    """Settle a background run: stopped plus the serial slot freed.

    Same settlement as stop_run (stopped, slot freed when active) so a
    finished or aborted executor never leaks the machine.
    """
    global _ACTIVE_RUN_ID
    try:
        progress = _require_progress(run_id)
    except KeyError:
        if _ACTIVE_RUN_ID == run_id:
            _ACTIVE_RUN_ID = None
        return
    if completed:
        progress.done_cases = len(_RUN_ROWS.get(run_id, []))
    progress.stopped = True
    if _ACTIVE_RUN_ID == run_id:
        _ACTIVE_RUN_ID = None
    _journal_append("executor_complete" if completed else "executor_abort")


def _executor_complete(run_id: str, model_id: str, level: BenchLevel) -> None:
    """Write the completion MEASURED row via the adapter seam, then settle.

    Only a full, unstopped slice completes: anything short settles
    aborted with no base write (fail-closed, no partial measurements).
    """
    try:
        progress = _require_progress(run_id)
    except KeyError:
        return
    if progress.stopped:
        _executor_settle(run_id, completed=False)
        return
    expected = len(_bench_cases.list_cases(level))
    rows = _RUN_ROWS.get(run_id, [])
    scores = [row.score for row in rows if isinstance(row.score, float)]
    hardware = _RUN_HARDWARE.get(run_id) or detect_hardware()
    if len(rows) != expected or len(scores) != expected or not rows:
        _executor_settle(run_id, completed=False)
        return
    try:
        _adapter.record_bench_measured(
            model_id=model_id,
            task_class=f"localbench:{BenchLevel(level).value}",
            score=sum(scores) / len(scores),
            sample_count=len(rows),
            confidence=len(rows) / expected,
            environment_fingerprint=_hardware_fingerprint(hardware),
            source="localbench background executor",
        )
    except Exception:
        _executor_settle(run_id, completed=False)
        return
    _executor_settle(run_id, completed=True)


def _execute_run(
    run_id: str, model_id: str, level: BenchLevel, chat_endpoint: str | None
) -> None:
    """Background executor body: walk the slice, score, append, complete.

    Never raises into the thread: a dead executor always settles the run
    (completed only on a full slice, aborted otherwise) and the serial
    slot never leaks after a settled run.
    """
    try:
        cases = _bench_cases.list_cases(level)
    except (ValueError, TypeError, AttributeError):
        _executor_settle(run_id, completed=False)
        return
    try:
        progress = _require_progress(run_id)
    except KeyError:
        return
    if not chat_endpoint:
        return
    chat_fn = _EndpointChat(chat_endpoint).chat
    hardware = _RUN_HARDWARE.get(run_id) or detect_hardware()
    for case in cases:
        if progress.stopped:
            return
        if not _executor_wait_while_paused(progress):
            return
        if progress.stopped:
            return
        try:
            spec = _bench_cases.quick_case_spec(case.case_id)
        except (ValueError, TypeError, AttributeError):
            _executor_settle(run_id, completed=False)
            return
        try:
            reply = chat_fn(model_id, spec.prompt)
        except Exception:
            _executor_settle(run_id, completed=False)
            return
        try:
            reply_text = _bench_reply_text(reply)
            score = _bench_score_reply(spec.rule, reply_text)
            row = BenchResultRow(
                case_id=case.case_id,
                kind=ResultKind.MEASURED,
                model_id=model_id,
                hardware=hardware,
                score=float(score),
                expected_rule=spec.rule,
                reply_excerpt=reply_text[:_BENCH_REPLY_EXCERPT_CHARS],
            )
        except (ValueError, TypeError):
            _executor_settle(run_id, completed=False)
            return
        _RUN_ROWS.setdefault(run_id, []).append(row)
        progress.done_cases = len(_RUN_ROWS[run_id])
    _executor_complete(run_id, model_id, level)


def _start_executor_thread(
    run_id: str,
    model_id: str,
    level: BenchLevel,
    chat_endpoint: str | None = None,
) -> threading.Thread:
    """Spawn the daemon background executor for a run; returns at once."""
    thread = threading.Thread(
        target=_execute_run,
        args=(run_id, model_id, level, chat_endpoint),
        name=f"bench-exec-{run_id}",
        daemon=True,
    )
    _RUN_THREADS[run_id] = thread
    thread.start()
    return thread
