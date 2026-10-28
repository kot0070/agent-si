"""K06 services socket stage (M-D-D51).

Real entry point for outbound socket use. ``open_channel`` runs the
channel evaluation first (which persists its record), and only a
persisted allow verdict reaches the socket: any other outcome
returns deny without touching the network. The socket connects to
the pinned address carried by the evaluation record and never
resolves the host again. Every socket waits at most ``timeout``
seconds, so a hung peer cannot stall the turn; any socket error
denies fail-closed.
"""

from __future__ import annotations

import contextlib
import importlib
import importlib.util
import os
import socket
from typing import Any

_MAX_TIMEOUT = 60.0

_EVAL: Any | None = None


def _evaluation_module() -> Any:
    """Return the channel evaluation module without a hard import."""
    global _EVAL
    if _EVAL is None:
        try:
            _EVAL = importlib.import_module("agent_si.services.channel_eval")
        except ImportError:
            path = os.path.join(
                os.path.dirname(os.path.realpath(__file__)), "channel_eval.py"
            )
            spec = importlib.util.spec_from_file_location(
                "agent_si_services_channel_eval", path
            )
            if spec is None or spec.loader is None:
                raise ImportError("cannot locate channel evaluation module")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            _EVAL = module
    return _EVAL


def _deny(reason: str, code: str) -> dict[str, Any]:
    """Build a deny result that names a stable evidence reference."""
    return {
        "decision": "deny",
        "reason": reason,
        "evidence_ref": "channel:%s" % (code,),
    }


def open_channel(
    target: dict[str, Any],
    policy: dict[str, Any] | None = None,
    store_path: str | None = None,
    timeout: float = 5.0,
) -> dict[str, Any]:
    """Evaluate the channel, then open one bounded socket on allow.

    The evaluation record is persisted before any socket use; deny
    verdicts from evaluation return here with no socket opened. On
    allow, one TCP connection is opened to the pinned address with
    the given timeout and closed at once; success returns allow
    bound to the persisted record, any failure returns deny.
    """
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not 0 < timeout <= _MAX_TIMEOUT
    ):
        return _deny(
            "refused: socket timeout is not usable",
            "deny:E_BAD_TIMEOUT",
        )
    evaluation = _evaluation_module()
    verdict = evaluation.evaluate_channel(
        target, policy=policy, store_path=store_path
    )
    if not isinstance(verdict, dict) or verdict.get("decision") != "allow":
        if isinstance(verdict, dict):
            return {
                "decision": "deny",
                "reason": str(verdict.get("reason", "refused: channel denied")),
                "evidence_ref": str(
                    verdict.get("evidence_ref", "channel:deny:E_UNKNOWN")
                ),
            }
        return _deny("refused: channel denied", "deny:E_UNKNOWN")
    record = verdict.get("record")
    if not isinstance(record, dict):
        return _deny("refused: channel has no persisted evaluation", "deny:E_NO_RECORD")
    pinned = record.get("pinned_ip")
    port = record.get("port")
    channel_id = record.get("channel_id", "")
    if (
        not isinstance(pinned, str)
        or not pinned
        or isinstance(port, bool)
        or not isinstance(port, int)
        or not 1 <= port <= 65535
    ):
        return _deny("refused: channel pin is not usable", "deny:E_BAD_PIN")
    sock = None
    try:
        sock = socket.create_connection((pinned, port), timeout=float(timeout))
    except Exception as exc:
        return {
            "decision": "deny",
            "reason": "refused: socket use failed (%s)" % (type(exc).__name__,),
            "evidence_ref": "channel:deny:E_SOCKET",
        }
    finally:
        if sock is not None:
            with contextlib.suppress(OSError):
                sock.close()
    return {
        "decision": "allow",
        "reason": "channel open to %s:%d" % (pinned, port),
        "evidence_ref": "channel:allow:%s" % (channel_id,),
    }
