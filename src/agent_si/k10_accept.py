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
