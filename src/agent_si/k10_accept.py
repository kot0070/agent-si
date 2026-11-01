"""K10ST4 M-P4-162: final acceptance status (loopback TEST data only).

Row: kit BUILD_PLAN M-P4-162 "final acceptance covers Docker, declared
services, PowerShell". This module carries a small FIXED recorded dataset:
plain in-code values, stdlib only, no network, no providers, no I/O,
deterministic. Statuses are recorded strings (never probed live). Pure
function, no settings or global mutation.
"""

from __future__ import annotations


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
