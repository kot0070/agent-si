"""Declared-params runner feed (STEP 2 implementation, G7).

Runners are fed via declared params only: feed entries carry exactly
the declared params, anything undeclared is reported as dropped, never
fed. The dry-run entry for enabled scripts lives on the
detected-environment page (see page.py).
"""

from __future__ import annotations

from typing import Any


def list_runners() -> list[str]:
    """List the known runner names."""
    return ["default"]


def declared_runner_params(runner_name: str) -> dict[str, Any]:
    """Return the declared params for a runner; {} when unknown."""

    def declared() -> dict[str, dict[str, Any]]:
        return {
            "default": {
                "timeout_s": 60,
                "dry_run": True,
                "max_retries": 0,
            },
        }

    params = declared().get(runner_name)
    return dict(params) if params is not None else {}


def feed_runners(runner_name: str, params: dict[str, Any]) -> dict[str, Any]:
    """Feed a runner with declared params only; extras are dropped."""

    def redact(key: str, value: Any) -> Any:
        hints = ("secret", "token", "password", "credential", "api_key")
        if any(hint in key.lower() for hint in hints):
            return "SecretRef(redacted)"
        return value

    declared = declared_runner_params(runner_name)
    given = dict(params)
    fed = {
        key: redact(key, given[key]) for key in declared if key in given
    }
    dropped = sorted(key for key in given if key not in declared)
    return {
        "runner": runner_name,
        "known": runner_name in list_runners(),
        "params": fed,
        "dropped": dropped,
        "dry_run": True,
        "fed": True,
    }
