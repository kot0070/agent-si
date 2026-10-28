"""K06 services channel evaluation (M-D-D51).

Evaluates one outbound channel (host plus port) and persists the
evaluation record before any socket use. Fail-closed: any error or
unknown input denies, and an allow verdict is only returned after
its record is durable in the store. Connection targets are pinned
at evaluation time: an allow verdict carries the resolved address
and later stages use that pinned address without resolving again.

The store is a JSON-lines file. Appends go through a temp file in
the same directory plus os.replace, so a persisted record is never
a torn write. Temporary locations come from tempfile only; no
fixed system path is embedded here.
"""

from __future__ import annotations

import concurrent.futures
import contextlib
import ipaddress
import json
import os
import socket
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Any

STORE_FILENAME = "agent_si_channel_eval.jsonl"

_POLICY_KEYS = frozenset({"deny_hosts", "resolve_timeout"})

_DEFAULT_RESOLVE_TIMEOUT = 5.0
_MAX_TIMEOUT = 60.0


class _Unresolved(Exception):
    """Raised when a host cannot be pinned to one address."""


def default_store_path() -> str:
    """Return the default record-store path inside the OS temp area."""
    return os.path.join(tempfile.gettempdir(), STORE_FILENAME)


def _now() -> str:
    """Return the current UTC time as an ISO string."""
    return datetime.now(timezone.utc).isoformat()


def _new_channel_id() -> str:
    """Return a fresh channel identifier."""
    return uuid.uuid4().hex


def _append_record(store_path: str, record: dict[str, Any]) -> None:
    """Append one record to the JSON-lines store atomically.

    Existing content is kept verbatim, the new line is added, and
    the file is swapped in with os.replace from a temp file in the
    same directory. Any failure raises to the caller, which must
    treat it as fail-closed.
    """
    directory = os.path.dirname(os.path.abspath(store_path))
    os.makedirs(directory, exist_ok=True)
    try:
        with open(store_path, "r", encoding="utf-8") as handle:
            previous = handle.read()
    except FileNotFoundError:
        previous = ""
    if previous and not previous.endswith("\n"):
        previous += "\n"
    payload = previous + json.dumps(record, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        dir=directory, prefix=".channel_eval_", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(tmp_name, store_path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


def load_records(store_path: str) -> list[dict[str, Any]]:
    """Read persisted evaluation records, skipping blank lines.

    Lines that are not JSON objects are skipped; reading never
    raises for content problems (an empty list means no usable
    records). Decisions never depend on this reader.
    """
    try:
        with open(store_path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except FileNotFoundError:
        return []
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _check_policy(policy: Any) -> tuple[dict[str, Any], str | None]:
    """Validate the policy mapping; return (cleaned, error-code)."""
    if policy is None:
        return {"deny_hosts": [], "resolve_timeout": _DEFAULT_RESOLVE_TIMEOUT}, None
    if not isinstance(policy, dict):
        return {}, "E_BAD_POLICY"
    if any(key not in _POLICY_KEYS for key in policy):
        return {}, "E_BAD_POLICY"
    deny_hosts = policy.get("deny_hosts", [])
    if not isinstance(deny_hosts, list) or any(
        not isinstance(item, str) or not item for item in deny_hosts
    ):
        return {}, "E_BAD_POLICY"
    resolve_timeout = policy.get("resolve_timeout", _DEFAULT_RESOLVE_TIMEOUT)
    if (
        isinstance(resolve_timeout, bool)
        or not isinstance(resolve_timeout, (int, float))
        or not 0 < resolve_timeout <= _MAX_TIMEOUT
    ):
        return {}, "E_BAD_POLICY"
    return (
        {
            "deny_hosts": [item.lower() for item in deny_hosts],
            "resolve_timeout": float(resolve_timeout),
        },
        None,
    )


def _check_target(target: Any) -> tuple[str, int, str | None]:
    """Validate the target; return (host, port, error-code)."""
    if not isinstance(target, dict):
        return "", 0, "E_BAD_TARGET"
    host = target.get("host")
    port = target.get("port")
    if not isinstance(host, str) or not host:
        return "", 0, "E_BAD_TARGET"
    if isinstance(port, bool) or not isinstance(port, int):
        return "", 0, "E_BAD_TARGET"
    if not 1 <= port <= 65535:
        return "", 0, "E_BAD_TARGET"
    return host, port, None


def _pin_address(host: str, resolve_timeout: float) -> str:
    """Pin a host to one numeric address, resolving once at most.

    IP literals need no lookup. Names resolve through one bounded
    getaddrinfo call; a timeout or lookup failure raises
    _Unresolved so the caller denies fail-closed instead of
    waiting out the turn.
    """
    try:
        literal = str(ipaddress.ip_address(host))
    except ValueError:
        literal = ""
    if literal:
        return literal
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            socket.getaddrinfo, host, None, socket.AF_UNSPEC, socket.SOCK_STREAM
        )
        try:
            infos = future.result(timeout=resolve_timeout)
        except Exception as exc:
            raise _Unresolved("cannot resolve host %r" % (host,)) from exc
    if not infos:
        raise _Unresolved("cannot resolve host %r" % (host,))
    return str(infos[0][4][0])


def _deny_verdict(
    code: str,
    reason: str,
    record: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build a deny verdict, bound to its record when persisted."""
    if record is not None:
        evidence_ref = "channel-eval:deny:%s" % (record["channel_id"],)
    else:
        evidence_ref = "channel-eval:deny:%s" % (code,)
    return {
        "decision": "deny",
        "reason": reason,
        "evidence_ref": evidence_ref,
        "record": record,
    }


def evaluate_channel(
    target: dict[str, Any],
    policy: dict[str, Any] | None = None,
    store_path: str | None = None,
) -> dict[str, Any]:
    """Evaluate one channel and persist the record before returning.

    Returns a verdict dict with decision (allow or deny), reason,
    evidence_ref and the persisted record (None only when the target
    was not a mapping or the store write failed). Every deny path
    denies fail-closed; allow is returned only after its record is
    durable. This function never opens a socket: resolution is a
    bounded lookup and pinning only.
    """
    store = store_path if isinstance(store_path, str) and store_path else default_store_path()
    clean_policy, policy_error = _check_policy(policy)
    host, port, target_error = _check_target(target)
    channel_id = _new_channel_id()
    if target_error is not None:
        return _deny_verdict(
            target_error,
            "refused: channel target is not usable (%s)" % (target_error,),
            None,
        )
    if policy_error is not None:
        record = {
            "channel_id": channel_id,
            "host": host,
            "port": port,
            "pinned_ip": "",
            "decision": "deny",
            "reason": policy_error,
            "evidence_ref": "",
            "created_at": _now(),
        }
        record["evidence_ref"] = "channel-eval:deny:%s" % (channel_id,)
        try:
            _append_record(store, record)
        except OSError:
            return _deny_verdict(
                "E_STORE",
                "refused: evaluation store unavailable",
                None,
            )
        return _deny_verdict(
            policy_error,
            "refused: channel policy is not usable (%s)" % (policy_error,),
            record,
        )
    try:
        pinned = _pin_address(host, clean_policy["resolve_timeout"])
    except _Unresolved:
        record = {
            "channel_id": channel_id,
            "host": host,
            "port": port,
            "pinned_ip": "",
            "decision": "deny",
            "reason": "E_UNRESOLVED",
            "evidence_ref": "",
            "created_at": _now(),
        }
        record["evidence_ref"] = "channel-eval:deny:%s" % (channel_id,)
        try:
            _append_record(store, record)
        except OSError:
            return _deny_verdict(
                "E_STORE",
                "refused: evaluation store unavailable",
                None,
            )
        return _deny_verdict(
            "E_UNRESOLVED",
            "refused: channel host cannot be pinned (%s)" % (host,),
            record,
        )
    if host.lower() in clean_policy["deny_hosts"] or pinned.lower() in clean_policy["deny_hosts"]:
        record = {
            "channel_id": channel_id,
            "host": host,
            "port": port,
            "pinned_ip": pinned,
            "decision": "deny",
            "reason": "E_DENIED_BY_POLICY",
            "evidence_ref": "",
            "created_at": _now(),
        }
        record["evidence_ref"] = "channel-eval:deny:%s" % (channel_id,)
        try:
            _append_record(store, record)
        except OSError:
            return _deny_verdict(
                "E_STORE",
                "refused: evaluation store unavailable",
                None,
            )
        return _deny_verdict(
            "E_DENIED_BY_POLICY",
            "refused: channel host denied by policy (%s)" % (host,),
            record,
        )
    record = {
        "channel_id": channel_id,
        "host": host,
        "port": port,
        "pinned_ip": pinned,
        "decision": "allow",
        "reason": "evaluated",
        "evidence_ref": "",
        "created_at": _now(),
    }
    record["evidence_ref"] = "channel-eval:allow:%s" % (channel_id,)
    try:
        _append_record(store, record)
    except OSError:
        return _deny_verdict(
            "E_STORE",
            "refused: evaluation store unavailable",
            None,
        )
    return {
        "decision": "allow",
        "reason": "channel evaluated and persisted for %s:%d" % (pinned, port),
        "evidence_ref": "channel-eval:allow:%s" % (channel_id,),
        "record": record,
    }
