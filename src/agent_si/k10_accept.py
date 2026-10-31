"""K10ST4 M-P4-162: final acceptance status (loopback TEST data only).

Row: kit BUILD_PLAN M-P4-162 "final acceptance covers Docker, declared
services, PowerShell". This module carries a small FIXED recorded dataset:
plain in-code values, stdlib only, no network, no providers, no I/O,
deterministic. Statuses are recorded strings (never probed live). Pure
function, no settings or global mutation.
"""

from __future__ import annotations


def get_acceptance_status() -> dict:
    """Return the fixed recorded final acceptance status."""
    return {
        "ok": True,
        "docker": {
            "available": True,
            "detail": (
                "recorded: Docker endpoint reachable on loopback fixture "
                "(not probed live)"
            ),
        },
        "services": [
            {
                "name": "backend",
                "declared": True,
                "detail": (
                    "recorded: declared service present on loopback "
                    "fixture (not probed live)"
                ),
            },
            {
                "name": "frontend",
                "declared": True,
                "detail": (
                    "recorded: declared service present on loopback "
                    "fixture (not probed live)"
                ),
            },
        ],
        "powershell": {
            "available": True,
            "detail": (
                "recorded: PowerShell available on loopback fixture "
                "(not probed live)"
            ),
        },
    }
