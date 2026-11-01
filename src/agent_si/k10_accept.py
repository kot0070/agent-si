"""K10ST4 M-P4-162: final acceptance status from live probes.

Row: kit BUILD_PLAN M-P4-162 "final acceptance covers Docker, declared
services, PowerShell". get_acceptance_status probes this host live at
call time: Docker and PowerShell are resolved on PATH and asked a
harmless version question, and each declared service gets a loopback
TCP connect. "ok" is true only when every probe passes; each probe
names what was seen, and anything not probed reports available false
with a reason. Stdlib only, no providers; the only I/O is the probes
themselves, and nothing here mutates settings or globals. The record
helpers below keep their fixed data rows for other lanes; only the
acceptance status is probed.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess

#: Third-party direct dependencies pinned by this checkout (name plus
#: pinned version taken from pyproject.toml / frontend/package.json;
#: each package's own installed metadata carries its licence text).
_THIRD_PARTY_NOTICES: tuple[dict[str, str], ...] = (
    {"name": "fastapi", "version": "0.162.0"},
    {"name": "openai-agents", "version": "0.20.0"},
    {"name": "react", "version": "19.3.1"},
    {"name": "react-router-dom", "version": "7.18.4"},
    {"name": "zod", "version": "4.6.7"},
)


#: Default product port probed for the declared backend service
#: (AGENT_SI_PORT default in env.example and app-config.example.json).
_DEFAULT_BACKEND_PORT = 8770

#: Harmless per-probe timeouts, in seconds.
_DOCKER_TIMEOUT_S = 10.0
_POWERSHELL_TIMEOUT_S = 15.0
_SERVICE_TIMEOUT_S = 3.0

#: Cap on quoted subprocess output kept inside a probe detail.
_SEEN_OUTPUT_LIMIT = 200


def _shorten(text: object) -> str:
    """Collapse whitespace and cap quoted probe output."""
    _clean = " ".join(str(text).split())
    if len(_clean) > _SEEN_OUTPUT_LIMIT:
        return _clean[:_SEEN_OUTPUT_LIMIT] + "..."
    return _clean


def _probe_docker() -> dict:
    """Probe Docker live: on PATH plus a harmless version call."""
    _exe = shutil.which("docker")
    if _exe is None:
        return {
            "available": False,
            "detail": "docker not on PATH",
        }
    try:
        _proc = subprocess.run(
            [_exe, "--version"],
            capture_output=True,
            text=True,
            timeout=_DOCKER_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired) as _exc:
        return {
            "available": False,
            "detail": (
                f"seen: 'docker --version' failed ({_shorten(_exc)})"
            ),
        }
    _seen = _shorten((_proc.stdout or "") + (_proc.stderr or ""))
    if _proc.returncode != 0:
        return {
            "available": False,
            "detail": (
                f"seen: 'docker --version' exit {_proc.returncode} -> "
                f"{_seen!r}"
            ),
        }
    return {
        "available": True,
        "detail": f"seen: 'docker --version' -> {_seen!r}",
    }


def _probe_powershell() -> dict:
    """Probe PowerShell live: on PATH plus a harmless version call."""
    _exe = shutil.which("powershell") or shutil.which("pwsh")
    if _exe is None:
        return {
            "available": False,
            "detail": "powershell/pwsh not on PATH",
        }
    _label = os.path.basename(_exe)
    try:
        _proc = subprocess.run(
            [_exe, "-NoProfile", "-Command",
             "$PSVersionTable.PSVersion.ToString()"],
            capture_output=True,
            text=True,
            timeout=_POWERSHELL_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired) as _exc:
        return {
            "available": False,
            "detail": (
                f"seen: '{_label}' version call failed ({_shorten(_exc)})"
            ),
        }
    _seen = _shorten((_proc.stdout or "") + (_proc.stderr or ""))
    if _proc.returncode != 0:
        return {
            "available": False,
            "detail": (
                f"seen: '{_label}' version call exit "
                f"{_proc.returncode} -> {_seen!r}"
            ),
        }
    return {
        "available": True,
        "detail": f"seen: '{_label}' version -> {_seen!r}",
    }


def _backend_port() -> int | None:
    """Return the declared backend port, or None when unparsable."""
    _raw = os.environ.get("AGENT_SI_PORT", "")
    if not str(_raw).strip():
        return _DEFAULT_BACKEND_PORT
    try:
        _port = int(str(_raw).strip())
    except ValueError:
        return None
    if 1 <= _port <= 65535:
        return _port
    return None


def _probe_backend_service() -> dict:
    """Probe the declared backend service: loopback TCP connect."""
    _port = _backend_port()
    if _port is None:
        return {
            "name": "backend",
            "declared": True,
            "available": False,
            "detail": (
                "seen: AGENT_SI_PORT="
                f"{os.environ.get('AGENT_SI_PORT', '')!r} is not a "
                "valid port; not probed"
            ),
        }
    _target = f"127.0.0.1:{_port}"
    try:
        with socket.create_connection(
                ("127.0.0.1", _port),
                timeout=_SERVICE_TIMEOUT_S):
            pass
    except (OSError, ValueError) as _exc:
        return {
            "name": "backend",
            "declared": True,
            "available": False,
            "endpoint": _target,
            "detail": (
                f"seen: TCP connect to {_target} failed ({_shorten(_exc)})"
            ),
        }
    return {
        "name": "backend",
        "declared": True,
        "available": True,
        "endpoint": _target,
        "detail": f"seen: TCP connect to {_target} open",
    }


def _probe_frontend_service() -> dict:
    """Report the declared frontend service: no endpoint, not probed."""
    return {
        "name": "frontend",
        "declared": True,
        "available": False,
        "detail": (
            "not probed: no declared frontend endpoint exists in "
            "product config, so there is nothing to connect to"
        ),
    }


def get_acceptance_status() -> dict:
    """Probe Docker, declared services and PowerShell live.

    "ok" is true only when every probe passes; each probe names what
    was seen, and anything not probed reports available false with a
    reason.
    """
    _docker = _probe_docker()
    _powershell = _probe_powershell()
    _services = [_probe_backend_service(), _probe_frontend_service()]
    _ok = bool(
        _docker["available"]
        and _powershell["available"]
        and all(_svc["available"] for _svc in _services)
    )
    return {
        "ok": _ok,
        "docker": _docker,
        "services": _services,
        "powershell": _powershell,
    }


def license_notice_record() -> dict:
    """Return the fixed recorded licence and third-party notice record.

    Row HC-4: the product ships under the MIT licence with the
    owner copyright, and the README names each pinned third-party
    direct dependency. Loopback recorded data only: plain in-code
    values, stdlib only, no network, no providers, no I/O,
    deterministic. Pure function, no settings or global mutation.
    """
    return {
        "license": "MIT",
        "copyright": "Copyright (c) 2026 Ivan Soprun",
        "licence_file": "LICENSE",
        "third_party": [dict(_item) for _item in _THIRD_PARTY_NOTICES],
        "source": (
            "recorded: HC-4 coverage (loopback fixture, not read live)"
        ),
        "snippet": (
            "verbatim recorded: 'LICENSE MIT plus copyright plus "
            "third-party notices'"
        ),
    }


def frontend_offline_record() -> dict:
    """Return the fixed recorded frontend offline-install record.

    Row LIVE0-01: the frontend installs offline from cached tarballs
    only, never from a registry at install time; the declared
    @types set stays intact. Loopback recorded data only: plain
    in-code values, stdlib only, no network, no providers, no I/O,
    deterministic. Pure function, no settings or global mutation.
    """
    return {
        "procedure": "offline-install-from-cached-tarballs",
        "manifest": "frontend/package.json",
        "lockfile": "frontend/package-lock.json",
        "types": ["@types/react", "@types/react-dom"],
        "claim": (
            "The frontend installs offline from cached tarballs "
            "only, with the declared @types set intact."
        ),
        "source": (
            "recorded: LIVE0-01 coverage (loopback fixture, not read live)"
        ),
        "snippet": (
            "verbatim recorded: 'frontend cached tarballs only, "
            "declared @types set intact'"
        ),
    }


#: MVP verdict tokens: binary ACCEPTED / NOT_ACCEPTED (rows 209/210).
MVP_ACCEPTED = "ACCEPTED"
MVP_NOT_ACCEPTED = "NOT_ACCEPTED"

#: Host shortfall blockers (rows 214/215): missing local permission, the
#: auditor provider, and a second real provider. Same order, same spelling.
HOST_BLOCKER_MISSING_LOCAL_PERMISSION = "missing local permission"
HOST_BLOCKER_MISSING_AUDITOR_PROVIDER = "auditor provider"
HOST_BLOCKER_MISSING_SECOND_REAL_PROVIDER = "second real provider"

HOST_BLOCKERS: tuple = (
    HOST_BLOCKER_MISSING_LOCAL_PERMISSION,
    HOST_BLOCKER_MISSING_AUDITOR_PROVIDER,
    HOST_BLOCKER_MISSING_SECOND_REAL_PROVIDER,
)


def mvp_verdict(acceptance_items=None, *, local_permission=False,
                auditor_provider=False, second_real_provider=False) -> dict:
    """Return the binary MVP verdict for acceptance items plus host flags.

    Row 209/210: verdict is exactly ACCEPTED iff every acceptance item
    holds, else exactly NOT_ACCEPTED. Row 212: a shortfall lists each
    failed item in blockers. Rows 214/215: when any host condition is
    unmet the blockers also carry the 3 host-blocker constants (missing
    local permission, auditor provider, second real provider) in frozen
    order. Pure function, stdlib only, no I/O.
    """
    items = dict(acceptance_items) if acceptance_items else {}
    blockers = [name for name, holds in items.items() if not holds]
    if not (local_permission and auditor_provider and second_real_provider):
        blockers.extend(HOST_BLOCKERS)
    verdict = MVP_ACCEPTED if not blockers else MVP_NOT_ACCEPTED
    return {"verdict": verdict, "blockers": blockers}
