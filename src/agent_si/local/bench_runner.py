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


def resume_run(run_id: str) -> None:
    """Resume a paused run; refused on unknown or already-stopped runs."""
    progress = _require_progress(run_id)
    if progress.stopped:
        raise BenchRefusedError(f"resume refused: run '{run_id}' already stopped")
    progress.paused = False


def stop_run(run_id: str) -> None:
    """Stop a run and free the serial slot when it was the active run."""
    global _ACTIVE_RUN_ID
    progress = _require_progress(run_id)
    progress.stopped = True
    if _ACTIVE_RUN_ID == run_id:
        _ACTIVE_RUN_ID = None


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
        return handle
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
    return lease
