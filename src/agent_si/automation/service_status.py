"""Automation service status and checks (Lane B STEP2).

Owns REALIZATION_MAP entries ``service.status.get`` (:func:`get`) and
``service.check.run`` (:func:`run_check`). Observe plus notify only (R-366):
this lane never starts or stops external services; it observes declared
endpoints (loopback by default) and budget state, then notifies through the
watcher journal.

Usage fields (``in_use`` / ``last_used`` / ``last_agent``) come from dispatch
plus egress metadata only (R-337), never from probes. Container checks are
read-only: they verify declared configuration holds secret references only
and report verdict plus counts plus locations, never values. Protected rows
refuse every check before execution and journal the refusal.

Cross-lane calls resolve late off the frozen automation contract module
at call time so tests can install doubles. Budget is observed through
the frozen K04 name
``agent_si.budget.gate.BudgetGate.get_state``; while K04 has not landed the
observation degrades to ``None`` and notification continues.
"""

from __future__ import annotations

import socket
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional, TYPE_CHECKING, Tuple

if TYPE_CHECKING:
    from agent_si.automation import interface as auto_iface


#: Dotted name of the frozen automation contract module. Product code
#: keeps no static import of it; the module object is resolved late at
#: call time, so raised errors, returned rows and cross-lane calls are
#: the same objects the contract tests use.
_IFACE_MODULE = "agent_si.automation.interface"


def _auto_iface():
    """Return the frozen automation contract module object."""
    try:
        return sys.modules[_IFACE_MODULE]
    except KeyError:
        raise RuntimeError(
            "frozen contract %r is not imported" % (_IFACE_MODULE,)
        )

__all__ = (
    "LeakReport",
    "get",
    "run_check",
    "scan_container",
    "observe_budget",
    "service_ids",
    "services_for_project",
    "declare_service",
    "record_usage",
    "record_egress",
    "declare_container_descriptor",
)


SECRETREF_PREFIX = "secretref:"

_SECRET_NAME_PARTS = ("PASSWORD", "SECRET", "TOKEN", "KEY")

_SLOW_AFTER_SECONDS = 1.0
_PROBE_TIMEOUT_SECONDS = 2.0


def _utcnow() -> str:
    """Current UTC time rendered like the frozen contract timestamps."""
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


_SEED_NOW = "2026-10-27T00:00:00Z"


def _seed_meta(agent: str, active: bool) -> Dict[str, object]:
    return {"active": active, "last_used": _SEED_NOW, "last_agent": agent}


#: Stored service rows: declared endpoints only (loopback by default).
#: ``state`` is the last observed state; ``timestamp`` its observation time.
_SERVICES: Dict[str, Dict[str, object]] = {
    "svc-api": {
        "kind": "http",
        "host": "127.0.0.1",
        "http_port": 8000,
        "tcp_port": 8001,
        "path": "/healthz",
        "protected": False,
        "project_id": "proj-a",
        "state": "UP",
        "timestamp": _SEED_NOW,
    },
    "svc-loopback": {
        "kind": "tcp",
        "host": "127.0.0.1",
        "http_port": 9000,
        "tcp_port": 9000,
        "path": "/",
        "protected": False,
        "project_id": "proj-b",
        "state": "UP",
        "timestamp": _SEED_NOW,
    },
    "svc-container": {
        "kind": "container",
        "host": "127.0.0.1",
        "http_port": 0,
        "tcp_port": 0,
        "path": "/",
        "protected": False,
        "project_id": "proj-b",
        "state": "UP",
        "timestamp": _SEED_NOW,
    },
    "svc-cache": {
        "kind": "http",
        "host": "127.0.0.1",
        "http_port": 8002,
        "tcp_port": 8003,
        "path": "/healthz",
        "protected": False,
        "project_id": "proj-b",
        "state": "DOWN",
        "timestamp": _SEED_NOW,
    },
    "svc-vault": {
        "kind": "http",
        "host": "127.0.0.1",
        "http_port": 8200,
        "tcp_port": 8201,
        "path": "/healthz",
        "protected": True,
        "project_id": "proj-b",
        "state": "DEGRADED",
        "timestamp": _SEED_NOW,
    },
}

#: Import-time snapshot of the seed service rows. Real checks mutate the
#: stored rows in place, so suites that run a check before a status
#: assertion observe the mutated row unless the seed rows are restored
#: (order-dependent). reset_state() below restores exactly this snapshot.
_SEED_STATES: Dict[str, Tuple[str, str]] = {
    service_id: (str(row["state"]), str(row["timestamp"]))
    for service_id, row in _SERVICES.items()
}

#: Dispatch metadata (R-337): which agent last used each service and whether
#: the service is currently in use. Stored facts, never probe-derived.
_DISPATCH_META: Dict[str, Dict[str, object]] = {
    "svc-api": _seed_meta("agent-1", True),
    "svc-loopback": _seed_meta("agent-2", False),
    "svc-container": _seed_meta("agent-1", True),
    "svc-cache": _seed_meta("agent-3", False),
    "svc-vault": _seed_meta("agent-1", False),
}

#: Egress metadata (R-337): last observed egress per service. Stored facts.
_EGRESS_META: Dict[str, Dict[str, object]] = {
    service_id: {"last_egress": _SEED_NOW} for service_id in _SERVICES
}

#: Declared container descriptors: environment entries hold secret
#: references only (``secretref:...``), never raw values.
_CONTAINER_DESCRIPTORS: Dict[str, Dict[str, object]] = {
    "svc-container": {
        "env": {
            "SVC_CONTAINER_API_TOKEN": "secretref:svc-container/api-token",
            "SVC_CONTAINER_DB_PASSWORD": "secretref:svc-container/db-password",
            "PORT": "9000",
        },
        "files": ("/etc/svc/config.yaml",),
    },
}


@dataclass(frozen=True)
class LeakReport:
    """Read-only container scan outcome: verdict, counts, locations only."""

    service_id: str
    verdict: str
    checked: int
    findings: int
    locations: Tuple[str, ...] = ()
    checked_at: str = ""


def service_ids() -> Tuple[str, ...]:
    """Stored service ids in registry order."""
    return tuple(_SERVICES)


def services_for_project(project_id: str) -> Tuple[str, ...]:
    """Stored service ids scoped to one project (stored facts only)."""
    return tuple(
        service_id
        for service_id, row in _SERVICES.items()
        if row["project_id"] == project_id
    )


#: Service kinds a declared row may carry. Container rows accept only the
#: read-only container check; every other kind accepts HTTP/TCP checks.
_ALLOWED_KINDS = ("http", "tcp", "container")


def declare_service(
    service_id: str,
    *,
    kind: str = "http",
    host: str = "127.0.0.1",
    http_port: int = 0,
    tcp_port: int = 0,
    path: str = "/",
    protected: bool = False,
    project_id: str = "",
) -> str:
    """Declare (add or refresh) a stored service row from caller inputs.

    New rows start fail-closed (``DOWN``) with a computed UTC declaration
    stamp until the first :func:`run_check` records a real observation;
    refreshing an existing row replaces its declared endpoint config but
    keeps its last observed ``state``/``timestamp``. Usage metadata and
    container descriptors are left untouched (see :func:`record_usage`,
    :func:`record_egress`, :func:`declare_container_descriptor`).
    ``ValueError`` for bad inputs.
    """
    if not isinstance(service_id, str) or not service_id:
        raise ValueError("service_id must be a non-empty string")
    if kind not in _ALLOWED_KINDS:
        raise ValueError("unknown service kind %r" % (kind,))
    if not isinstance(project_id, str) or not project_id:
        raise ValueError("project_id must be a non-empty string")
    row = _SERVICES.get(service_id)
    if row is None:
        _SERVICES[service_id] = {
            "kind": kind,
            "host": str(host),
            "http_port": int(http_port),
            "tcp_port": int(tcp_port),
            "path": str(path),
            "protected": bool(protected),
            "project_id": project_id,
            "state": "DOWN",
            "timestamp": _utcnow(),
        }
    else:
        row["kind"] = kind
        row["host"] = str(host)
        row["http_port"] = int(http_port)
        row["tcp_port"] = int(tcp_port)
        row["path"] = str(path)
        row["protected"] = bool(protected)
        row["project_id"] = project_id
    return service_id


def record_usage(
    service_id: str,
    *,
    active: bool,
    last_agent: str,
    last_used: Optional[str] = None,
) -> Dict[str, object]:
    """Record dispatch metadata for a declared service from caller inputs.

    ``last_used`` defaults to the current UTC time when omitted. Raises
    ``SERVICE_NOT_FOUND`` for undeclared ids.
    """
    if service_id not in _SERVICES:
        raise _auto_iface().AutomationError(
            "SERVICE_NOT_FOUND", "unknown service %r" % (service_id,)
        )
    stamp = _utcnow() if last_used is None else str(last_used)
    _DISPATCH_META[service_id] = {
        "active": bool(active),
        "last_used": stamp,
        "last_agent": str(last_agent),
    }
    return dict(_DISPATCH_META[service_id])


def record_egress(
    service_id: str, *, last_egress: Optional[str] = None
) -> Dict[str, object]:
    """Record egress metadata for a declared service from caller inputs.

    ``last_egress`` defaults to the current UTC time when omitted. Raises
    ``SERVICE_NOT_FOUND`` for undeclared ids.
    """
    if service_id not in _SERVICES:
        raise _auto_iface().AutomationError(
            "SERVICE_NOT_FOUND", "unknown service %r" % (service_id,)
        )
    stamp = _utcnow() if last_egress is None else str(last_egress)
    _EGRESS_META[service_id] = {"last_egress": stamp}
    return dict(_EGRESS_META[service_id])


def declare_container_descriptor(
    service_id: str, *, env: Dict[str, object], files: object = ()
) -> Dict[str, object]:
    """Store a declared container descriptor from caller inputs (stored facts).

    Secret-looking entries must carry ``secretref:`` references only; a raw
    value raises ``ValueError`` before anything is stored. Raises
    ``SERVICE_NOT_FOUND`` for undeclared ids.
    """
    if service_id not in _SERVICES:
        raise _auto_iface().AutomationError(
            "SERVICE_NOT_FOUND", "unknown service %r" % (service_id,)
        )
    if not isinstance(env, dict):
        raise ValueError("descriptor env must be a mapping")
    if not isinstance(files, (tuple, list)):
        raise ValueError("descriptor files must be a tuple or list")
    stored_env: Dict[str, object] = {}
    for name, value in env.items():
        if _looks_secret(name) and not (
            isinstance(value, str) and value.startswith(SECRETREF_PREFIX)
        ):
            raise ValueError(
                "descriptor entry %r must be a secret reference" % (name,)
            )
        stored_env[str(name)] = value
    stored_files = tuple(str(path) for path in files)
    _CONTAINER_DESCRIPTORS[service_id] = {
        "env": stored_env,
        "files": stored_files,
    }
    return {"env": dict(stored_env), "files": stored_files}


def reset_state() -> None:
    """Restore the seed service states and timestamps (test isolation).

    Real checks mutate the stored rows in place; without a reset, a
    suite that runs a check on a service before a status assertion on
    the same service observes the mutated row (order-dependent). The
    seed rows' ``state``/``timestamp`` values are restored, and rows
    plus metadata added through :func:`declare_service` (and its
    companion record APIs) are dropped; no seed row is added or removed.
    """
    for service_id, (state, stamp) in _SEED_STATES.items():
        row = _SERVICES.get(service_id)
        if row is None:
            continue
        row["state"] = state
        row["timestamp"] = stamp
    for service_id in [key for key in _SERVICES if key not in _SEED_STATES]:
        del _SERVICES[service_id]
    for registry in (_DISPATCH_META, _EGRESS_META, _CONTAINER_DESCRIPTORS):
        for service_id in [key for key in registry if key not in _SEED_STATES]:
            del registry[service_id]


def observe_budget(service_id: str) -> Optional[object]:
    """Observe-only budget read through the frozen K04 name.

    Returns the gate's state record, or ``None`` while K04 has not landed.
    Never reserves, settles, or otherwise controls budget.
    """
    try:
        from agent_si.budget.gate import BudgetGate
    except ImportError:
        return None
    return BudgetGate().get_state(service_id)


def _usage(service_id: str) -> Tuple[bool, str, str]:
    """Merge dispatch plus egress metadata (R-337) into usage fields."""
    dispatch = _DISPATCH_META.get(service_id, {})
    egress = _EGRESS_META.get(service_id, {})
    last_used = str(dispatch.get("last_used", ""))
    last_egress = str(egress.get("last_egress", ""))
    if last_egress > last_used:
        last_used = last_egress
    return (
        bool(dispatch.get("active", False)),
        last_used,
        str(dispatch.get("last_agent", "")),
    )


def _status_of(service_id: str) -> auto_iface.ServiceStatus:
    row = _SERVICES[service_id]
    in_use, last_used, last_agent = _usage(service_id)
    return _auto_iface().ServiceStatus(
        service_id=service_id,
        state=str(row["state"]),
        timestamp=str(row["timestamp"]),
        in_use=in_use,
        last_used=last_used,
        last_agent=last_agent,
    )


def get(service_id: str) -> auto_iface.ServiceStatus:
    """REALIZATION_MAP ``service.status.get``: stored row plus metadata."""
    if service_id not in _SERVICES:
        raise _auto_iface().AutomationError(
            "SERVICE_NOT_FOUND", "unknown service %r" % (service_id,)
        )
    observe_budget(service_id)
    return _status_of(service_id)


def _coerce_kind(check: object) -> str:
    """Accept the frozen check-kind member or its name (duck-typed).

    Returns the kind name; refuses anything else before execution.
    """
    name = getattr(check, "value", check)
    if not isinstance(name, str):
        name = str(name)
    if name in ("HTTP", "TCP", "CONTAINER_READONLY"):
        return name
    raise _auto_iface().AutomationError(
        "SERVICE_CHECK_REFUSED", "unknown check kind %r" % (check,)
    )


def _kind_allowed(row: Dict[str, object], kind: str) -> bool:
    if kind == "CONTAINER_READONLY":
        return row["kind"] == "container"
    if row["kind"] == "container":
        return kind == "CONTAINER_READONLY"
    return kind in ("HTTP", "TCP")


def _refuse_pre_exec(service_id: str, project_id: str, reason: str) -> None:
    """Journal a pre-execution refusal, then raise ``SERVICE_CHECK_REFUSED``."""
    _auto_iface().journal_append_event(
        project_id,
        "automation",
        "SERVICE_STATE",
        "check refused: %s" % reason,
        (service_id,),
    )
    raise _auto_iface().AutomationError("SERVICE_CHECK_REFUSED", reason)


def _probe_http(host: str, port: int, path: str,
                timeout: float = _PROBE_TIMEOUT_SECONDS) -> Tuple[bool, bool]:
    """Loopback HTTP probe; returns ``(reachable_healthy, slow)``."""
    url = "http://%s:%d%s" % (host, port, path)
    start = time.monotonic()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            code = int(response.status)
    except (OSError, urllib.error.URLError, ValueError):
        return False, False
    slow = (time.monotonic() - start) >= _SLOW_AFTER_SECONDS
    return 200 <= code < 300, slow


def _probe_tcp(host: str, port: int,
               timeout: float = _PROBE_TIMEOUT_SECONDS) -> Tuple[bool, bool]:
    """Loopback TCP probe; returns ``(reachable, slow)``."""
    start = time.monotonic()
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
    except OSError:
        return False, False
    try:
        sock.close()
    except OSError:
        pass
    slow = (time.monotonic() - start) >= _SLOW_AFTER_SECONDS
    return True, slow


def _read_descriptor(service_id: str) -> Dict[str, object]:
    """Read-only fetch of the declared container descriptor (stored facts)."""
    return dict(_CONTAINER_DESCRIPTORS.get(service_id, {}))


def _looks_secret(name: str) -> bool:
    upper = str(name).upper()
    return any(part in upper for part in _SECRET_NAME_PARTS)


def scan_container(service_id: str) -> LeakReport:
    """Read-only leak scan: secret refs only; verdict, counts, locations."""
    if service_id not in _SERVICES:
        raise _auto_iface().AutomationError(
            "SERVICE_NOT_FOUND", "unknown service %r" % (service_id,)
        )
    descriptor = _read_descriptor(service_id)
    env = descriptor.get("env", {})
    files = descriptor.get("files", ())
    if not isinstance(env, dict):
        env = {}
    if not isinstance(files, (tuple, list)):
        files = ()
    checked = 0
    locations = []
    for name, value in env.items():
        checked += 1
        if _looks_secret(name) and not (
            isinstance(value, str) and value.startswith(SECRETREF_PREFIX)
        ):
            locations.append("env:%s" % name)
    for path in files:
        checked += 1
        if _looks_secret(str(path).replace("/", "_").replace(".", "_")):
            locations.append("file:%s" % path)
    verdict = "FINDINGS" if locations else "CLEAN"
    return LeakReport(
        service_id=service_id,
        verdict=verdict,
        checked=checked,
        findings=len(locations),
        locations=tuple(locations),
        checked_at=_utcnow(),
    )


def run_check(
    service_id: str,
    check: object,
    session_token: Optional[str] = None,
) -> auto_iface.ServiceStatus:
    """REALIZATION_MAP ``service.check.run``: probe, store, notify.

    ``session_token`` is accepted for entry-point parity; refusal of missing
    or invalid tokens is enforced at the route seam, not here.
    """
    kind = _coerce_kind(check)
    row = _SERVICES.get(service_id)
    if row is None:
        raise _auto_iface().AutomationError(
            "SERVICE_NOT_FOUND", "unknown service %r" % (service_id,)
        )
    project_id = str(row["project_id"])
    observe_budget(service_id)
    if bool(row["protected"]):
        _refuse_pre_exec(service_id, project_id, "protected service")
    if not _kind_allowed(row, kind):
        _refuse_pre_exec(
            service_id,
            project_id,
            "%s check not allowed for %s service"
            % (kind, row["kind"]),
        )
    if kind == "CONTAINER_READONLY":
        report = scan_container(service_id)
        state = (
            "DEGRADED"
            if report.findings
            else "UP"
        )
    elif kind == "HTTP":
        healthy, slow = _probe_http(
            str(row["host"]), int(row["http_port"]), str(row["path"])
        )
        if not healthy and not slow:
            # Unreachable and not merely slow: distinguish refused (DOWN)
            # from an answered-but-unhealthy endpoint (DEGRADED) via a
            # second lightweight TCP dial of the same declared endpoint.
            reachable, _ = _probe_tcp(str(row["host"]), int(row["http_port"]))
            state = (
                "DEGRADED"
                if reachable
                else "DOWN"
            )
        elif healthy and not slow:
            state = "UP"
        else:
            state = "DEGRADED"
    else:
        reachable, slow = _probe_tcp(str(row["host"]), int(row["tcp_port"]))
        if reachable and not slow:
            state = "UP"
        elif reachable:
            state = "DEGRADED"
        else:
            state = "DOWN"
    row["state"] = state
    row["timestamp"] = _utcnow()
    _auto_iface().journal_append_event(
        project_id,
        "automation",
        "SERVICE_STATE",
        "%s check state %s" % (kind, state),
        (service_id,),
    )
    return _status_of(service_id)
