"""K05R3 DISCOVER-stage permission gate (B0B-UNCOVERED_BP05-29).

enter_discover refuses permission-less probing with
K05R3_DISCOVER_PERMISSION_REFUSED (scope validated through the real
config.validate_permission allowlist) and admits only the single SCAN ->
DISCOVER step through the real adapter.advance_lifecycle order; the
identity stays UNKNOWN. scan_roots mirrors the allowlist-first scan rule
(allowlist-first, no forbidden segments, no symlinks, read-only one-level
listing) without importing bench_runner. Standard library plus
agent_si.local public imports only.
"""

from __future__ import annotations

import itertools
import os
from dataclasses import dataclass

from agent_si.local import adapter
from agent_si.local import config

#: Discover refused: probing without a permission from the allowlist.
K05R3_DISCOVER_PERMISSION_REFUSED = "K05R3_DISCOVER_PERMISSION_REFUSED"
#: Discover refused: the gate admits the SCAN -> DISCOVER step only.
K05R3_DISCOVER_STAGE_REFUSED = "K05R3_DISCOVER_STAGE_REFUSED"
#: Discover refused: scan outside the allowlist or against the scan rule.
K05R3_DISCOVER_SCAN_REFUSED = "K05R3_DISCOVER_SCAN_REFUSED"

#: New-module error-code set (frozen ERROR_CODES_* tuples elsewhere untouched).
ERROR_CODES_K05R3_DISCOVER = (
    K05R3_DISCOVER_PERMISSION_REFUSED,
    K05R3_DISCOVER_STAGE_REFUSED,
    K05R3_DISCOVER_SCAN_REFUSED,
)

#: Identity state carried by every discover grant (spec: stays UNKNOWN).
DISCOVER_IDENTITY_UNKNOWN = "UNKNOWN"

#: Path segments refused by scan_roots: creds, browser profiles/keys,
#: SSH/cloud credentials. Allowlist-first still applies on top: anything
#: outside the allowlist is refused regardless.
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


class DiscoverError(Exception):
    """Discover failure; carries one ERROR_CODES_K05R3_DISCOVER code in `code`."""

    code: str

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class DiscoverGrant:
    """Admitted DISCOVER probe: granted scope with the identity still UNKNOWN."""

    grant_id: str
    stage: adapter.LifecycleStage
    permission_scope: str
    identity_state: str = DISCOVER_IDENTITY_UNKNOWN


#: Grant ids, unique per admission in call order.
_GRANT_SEQ = itertools.count(1)


def enter_discover(
    current_stage: adapter.LifecycleStage, permission_scope: str
) -> DiscoverGrant:
    """Pass the DISCOVER gate: permission from the allowlist plus SCAN -> DISCOVER."""
    if not isinstance(permission_scope, str) or not permission_scope:
        raise DiscoverError(
            K05R3_DISCOVER_PERMISSION_REFUSED,
            "discover probing without a permission scope is refused",
        )
    try:
        config.validate_permission(permission_scope)
    except config.LocalAISettingsError as exc:
        raise DiscoverError(
            K05R3_DISCOVER_PERMISSION_REFUSED,
            "discover probing with permission scope %r is refused: %s"
            % (permission_scope, exc.message),
        ) from exc
    if current_stage is not adapter.LifecycleStage.SCAN:
        raise DiscoverError(
            K05R3_DISCOVER_STAGE_REFUSED,
            "discover gate admits SCAN -> DISCOVER only, got %r" % (current_stage,),
        )
    stage = adapter.advance_lifecycle(
        adapter.LifecycleStage.SCAN, adapter.LifecycleStage.DISCOVER
    )
    return DiscoverGrant(
        grant_id="k05r3-discover-%06d" % next(_GRANT_SEQ),
        stage=stage,
        permission_scope=permission_scope,
    )


def _normalized_abs(path: str) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def scan_roots(allowlist_dirs: list[str], requested_path: str) -> list[str]:
    """Read-only root scan: allowlist-first, never creds/browser/SSH/cloud.

    Refuses (DiscoverError) full-drive roots, anything outside the
    allowlist, forbidden segments, symlinks, and non-directories; lists
    one level read-only on success. Changes nothing.
    """
    if not isinstance(requested_path, str) or not requested_path:
        raise DiscoverError(
            K05R3_DISCOVER_SCAN_REFUSED,
            "scan refused: requested path must be a non-empty string",
        )
    requested = _normalized_abs(requested_path)
    drive, tail = os.path.splitdrive(requested)
    if tail in ("", os.sep) or requested in ("/", "\\"):
        raise DiscoverError(
            K05R3_DISCOVER_SCAN_REFUSED,
            "scan refused: full-drive root %r" % (requested_path,),
        )
    allowlist: list[str] = []
    for entry in allowlist_dirs or []:
        if not isinstance(entry, str) or not entry:
            raise DiscoverError(
                K05R3_DISCOVER_SCAN_REFUSED,
                "scan refused: allowlist holds an empty entry",
            )
        norm = _normalized_abs(entry)
        if not os.path.isabs(norm):
            raise DiscoverError(
                K05R3_DISCOVER_SCAN_REFUSED,
                "scan refused: allowlist entry not absolute: %r" % (entry,),
            )
        allowlist.append(norm)

    def _under(base: str) -> bool:
        if requested == base:
            return True
        try:
            return os.path.commonpath([requested, base]) == base
        except ValueError:
            return False

    if not any(_under(base) for base in allowlist):
        raise DiscoverError(
            K05R3_DISCOVER_SCAN_REFUSED,
            "scan refused: %r is outside the scan allowlist" % (requested_path,),
        )
    separators = {os.sep}
    if os.altsep:
        separators.add(os.altsep)
    lowered = requested.lower()
    for sep in separators:
        lowered = lowered.replace(sep, "/")
    hit = set(lowered.split("/")) & _FORBIDDEN_SEGMENTS
    if hit:
        raise DiscoverError(
            K05R3_DISCOVER_SCAN_REFUSED,
            "scan refused: forbidden path segment %r in %r"
            % (sorted(hit)[0], requested_path),
        )
    if os.path.islink(requested_path) or os.path.realpath(
        requested_path
    ) != os.path.abspath(requested_path):
        raise DiscoverError(
            K05R3_DISCOVER_SCAN_REFUSED,
            "scan refused: symlink target %r" % (requested_path,),
        )
    if not os.path.isdir(requested_path):
        raise DiscoverError(
            K05R3_DISCOVER_SCAN_REFUSED,
            "scan refused: not a directory: %r" % (requested_path,),
        )
    return sorted(os.listdir(requested_path))
