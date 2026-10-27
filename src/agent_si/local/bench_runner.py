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

import itertools
import json
import os
import socket
import time
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse

from agent_si.local import bench_cases as _bench_cases
from agent_si.local.bench_protocol import (
    BenchEstimate,
    BenchLevel,
    BenchResultRow,
    HardwareProfile,
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


def _reconcile_slot_on_skip() -> None:
    """Settle an in-flight run when a skip proves the gateway unreachable."""
    global _ACTIVE_RUN_ID
    if _ACTIVE_RUN_ID is not None:
        progress = _PROGRESS.get(_ACTIVE_RUN_ID)
        if progress is not None:
            progress.stopped = True
        _ACTIVE_RUN_ID = None
    _journal_append("slot_reconciled")


def start_run(model_id: str, level: BenchLevel, authorized: bool) -> RunHandle | RunSkip:
    """Start a serial run: passive check, then auth, then the busy guard."""
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
        raise BenchBusyError(
            f"serial one-model machine busy: run '{_ACTIVE_RUN_ID}' is active; "
            "wait or stop it first; state unchanged"
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
    _journal_append("start_run")
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
