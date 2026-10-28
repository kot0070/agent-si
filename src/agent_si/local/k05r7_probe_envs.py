"""K05R7 M-PROBE bench seam: offline probe envs, loopback-only (M-D-D15/D41).

Probe knobs resolve ONLY from ``AGENT_SI_PROBE_*`` environment entries.
Product-infra env (``AGENT_SI_BENCH_JOURNAL`` and every other ``AGENT_SI_*``
name outside the probe prefix) never affects probe resolution. Every probe
target is loopback-only and every socket opened here is a loopback socket;
non-loopback, unparsable or unreachable endpoints are refused fail-closed
before any external contact. Standard library only; portable APIs only.
"""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

#: Only env names with this prefix feed probe resolution (M-D-D15).
PROBE_ENV_PREFIX = "AGENT_SI_PROBE_"

#: Probe endpoint override, e.g. "http://127.0.0.1:11434".
PROBE_ENDPOINT_ENV = "AGENT_SI_PROBE_ENDPOINT"

#: Probe socket timeout in seconds, e.g. "0.2".
PROBE_TIMEOUT_ENV = "AGENT_SI_PROBE_TIMEOUT_S"

#: Hosts a probe may ever touch: loopback only (offline-only).
PROBE_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})

#: Default probe socket timeout (s); bad timeout env falls back here.
DEFAULT_PROBE_TIMEOUT_S = 0.2

#: Default loopback probe targets used when no probe endpoint is configured.
#: Items are (host, port, endpoint); loopback-only by construction.
DEFAULT_PROBE_TARGETS: tuple[tuple[str, int, str], ...] = (
    ("127.0.0.1", 11434, "http://127.0.0.1:11434"),
    ("127.0.0.1", 1234, "http://127.0.0.1:1234"),
)


class ProbeRefusedError(Exception):
    """Fail-closed probe refusal: non-loopback/unparsable/unreachable endpoint."""


@dataclass
class ProbeSkip:
    """Skip outcome: the probe endpoint is unusable; no contact was made."""

    reason: str


@dataclass
class ProbeEnv:
    """Resolved offline probe knobs: endpoint plus socket timeout."""

    endpoint: str | None
    timeout_s: float


def _live_environ(environ=None):
    return os.environ if environ is None else environ


def probe_env_snapshot(environ=None) -> dict:
    """Only the AGENT_SI_PROBE_* entries; product infra env never appears."""
    env = _live_environ(environ)
    snap: dict = {}
    try:
        items = env.items()
    except AttributeError:
        return snap
    for key, value in items:
        if isinstance(key, str) and key.startswith(PROBE_ENV_PREFIX):
            snap[key] = value
    return snap


def resolve_probe_endpoint(environ=None) -> str | None:
    """Probe endpoint from AGENT_SI_PROBE_ENDPOINT only; None when unset."""
    raw = probe_env_snapshot(environ).get(PROBE_ENDPOINT_ENV)
    if not isinstance(raw, str) or not raw.strip():
        return None
    return raw.strip()


def resolve_probe_timeout_s(environ=None) -> float:
    """Probe timeout from AGENT_SI_PROBE_TIMEOUT_S; default on bad values."""
    raw = probe_env_snapshot(environ).get(PROBE_TIMEOUT_ENV)
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        return DEFAULT_PROBE_TIMEOUT_S
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_PROBE_TIMEOUT_S
    if value != value or value in (float("inf"), float("-inf")) or value <= 0.0:
        return DEFAULT_PROBE_TIMEOUT_S
    return value


def resolve_probe_env(environ=None) -> ProbeEnv:
    """Full probe knobs from AGENT_SI_PROBE_* only (M-D-D15)."""
    return ProbeEnv(
        endpoint=resolve_probe_endpoint(environ),
        timeout_s=resolve_probe_timeout_s(environ),
    )


def probe_host_allowed(host: object) -> bool:
    """Loopback hosts only; everything else is refused before any contact."""
    return isinstance(host, str) and host.lower() in PROBE_LOOPBACK_HOSTS


def probe_reachable(host: str, port: int, timeout_s: float | None = None) -> bool:
    """One loopback TCP probe; False (no contact) for non-loopback hosts."""
    if not probe_host_allowed(host):
        return False
    if isinstance(port, bool) or not isinstance(port, int):
        return False
    if port < 1 or port > 65535:
        return False
    timeout = timeout_s
    if (
        not isinstance(timeout, (int, float))
        or isinstance(timeout, bool)
        or timeout != timeout
        or timeout in (float("inf"), float("-inf"))
        or timeout <= 0.0
    ):
        timeout = DEFAULT_PROBE_TIMEOUT_S
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, ValueError):
        return False


def _split_probe_endpoint(endpoint: str) -> tuple[str, int]:
    """Parse (host, port); raise ProbeRefusedError when unparsable (no contact)."""
    if not isinstance(endpoint, str) or not endpoint.strip():
        raise ProbeRefusedError(
            "probe refused: no probe endpoint configured; skipped without contact"
        )
    text = endpoint.strip()
    try:
        parts = urlparse(text if "://" in text else f"http://{text}")
        host = (parts.hostname or "").lower()
        port = parts.port or 80
    except (ValueError, OverflowError, AttributeError) as exc:
        raise ProbeRefusedError(
            f"probe refused: unparsable endpoint {endpoint!r} ({exc}); "
            "skipped without contact"
        ) from None
    if not host:
        raise ProbeRefusedError(
            f"probe refused: unparsable endpoint {endpoint!r} (no host); "
            "skipped without contact"
        )
    return host, port


def probe_targets(environ=None) -> tuple[tuple[str, int, str], ...]:
    """Loopback-only probe targets; non-loopback env yields no targets."""
    endpoint = resolve_probe_endpoint(environ)
    if endpoint is None:
        return DEFAULT_PROBE_TARGETS
    try:
        host, port = _split_probe_endpoint(endpoint)
    except ProbeRefusedError:
        return ()
    if not probe_host_allowed(host):
        return ()
    return ((host, port, endpoint),)


def guard_probe_endpoint(
    endpoint: str | None = None,
    environ=None,
    timeout_s: float | None = None,
) -> str:
    """Fail-closed host check BEFORE any contact (M-D-D41).

    Non-loopback or unparsable endpoints raise ProbeRefusedError with zero
    socket contact; loopback endpoints get one loopback guard probe and
    raise ProbeRefusedError when unreachable. Returns the normalized
    endpoint when a loopback runtime answers.
    """
    eff = endpoint if endpoint is not None else resolve_probe_endpoint(environ)
    if eff is None or (isinstance(eff, str) and not eff.strip()):
        raise ProbeRefusedError(
            "probe refused: no probe endpoint configured; skipped without contact"
        )
    host, port = _split_probe_endpoint(eff)
    if not probe_host_allowed(host):
        raise ProbeRefusedError(
            f"probe refused: endpoint {eff!r} is not loopback; refused without contact"
        )
    timeout = timeout_s if timeout_s is not None else resolve_probe_timeout_s(environ)
    if not probe_reachable(host, port, timeout):
        raise ProbeRefusedError(
            f"probe refused: loopback endpoint {eff!r} unreachable; "
            "skipped without external contact"
        )
    return f"http://{host}:{port}"


def check_probe_endpoint(
    endpoint: str | None = None,
    environ=None,
    timeout_s: float | None = None,
) -> str | ProbeSkip:
    """Skip-style guard: normalized endpoint, or ProbeSkip (never raises)."""
    try:
        return guard_probe_endpoint(endpoint, environ, timeout_s)
    except ProbeRefusedError as exc:
        return ProbeSkip(reason=str(exc))
