"""K03 catalog lane STEP2: user overlay with audit trail.

Every planned test id exists in the catalog or a user overlay; the overlay
carries its own audit trail.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

#: Frozen error-code names for this module (each pinned in its own test).
ERROR_CODES_OVERLAY = (
    "DUPLICATE_TEST_ID",
    "OVERLAY_ON_UNKNOWN_VERSION",
)


class OverlayError(Exception):
    """Overlay failure carrying the frozen ``.code`` name."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class OverlayTest:
    test_id: str
    intent: str
    kind: str
    oracle: str
    reason: str


@dataclass(frozen=True)
class UserOverlay:
    overlay_id: str
    project_id: str
    base_version: int
    tests: Tuple[OverlayTest, ...]
    audit_trail: Tuple[str, ...]


#: Ids owned by the frozen catalog; an overlay id must avoid all of these.
_FROZEN_CATALOG_IDS = ("t-boot", "t-chat", "t-export")

_OVERLAY_SEQ = [0]


def create_overlay(project_id: str, base_version: int) -> UserOverlay:
    """Open a user overlay on a known catalog version."""
    if base_version < 1:
        raise OverlayError(
            "OVERLAY_ON_UNKNOWN_VERSION",
            "unknown catalog version %r for overlay" % base_version,
        )
    _OVERLAY_SEQ[0] += 1
    overlay_id = "overlay-%s-v%d-%03d" % (
        project_id,
        base_version,
        _OVERLAY_SEQ[0],
    )
    return UserOverlay(
        overlay_id=overlay_id,
        project_id=project_id,
        base_version=base_version,
        tests=(),
        audit_trail=(
            "created overlay %s on catalog version %d" % (overlay_id, base_version),
        ),
    )


def add_overlay_test(overlay: UserOverlay, test: OverlayTest) -> UserOverlay:
    """Append one user test; id collisions with catalog or overlay refused."""
    taken = set(_FROZEN_CATALOG_IDS) | {known.test_id for known in overlay.tests}
    if test.test_id in taken:
        raise OverlayError(
            "DUPLICATE_TEST_ID",
            "test id %r already exists in the catalog or overlay"
            % test.test_id,
        )
    return UserOverlay(
        overlay_id=overlay.overlay_id,
        project_id=overlay.project_id,
        base_version=overlay.base_version,
        tests=overlay.tests + (test,),
        audit_trail=overlay.audit_trail
        + (
            "added overlay test %s: %s" % (test.test_id, test.reason),
        ),
    )


def overlay_audit_trail(overlay: UserOverlay) -> Tuple[str, ...]:
    """Audit trail of overlay operations, oldest entry first."""
    return tuple(overlay.audit_trail)


#: Entry points: logical name -> symbol in this module.
ENTRY_POINTS = {
    "create_overlay": "create_overlay",
    "add_overlay_test": "add_overlay_test",
    "overlay_audit_trail": "overlay_audit_trail",
}
