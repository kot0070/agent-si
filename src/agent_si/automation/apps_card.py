"""Automation apps card (Lane B STEP2).

Owns REALIZATION_MAP entry ``apps.card.get`` (:func:`get_apps_card`).
Serves stored facts only, never computed values: the service id list comes
from the stored service registry and the paused flag comes from the pause
lane through the module-attribute seam :func:`is_pause_effective` (tests
install a FAKE-OF double there).
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from agent_si.automation import service_status

if TYPE_CHECKING:
    from agent_si.automation import interface as auto_iface


#: Dotted name of the frozen automation contract module. Product code
#: keeps no static import of it; the module object is resolved late at
#: call time, so raised errors, returned rows and cross-lane calls are
#: the same objects the contract tests use.
_IFACE_MODULE = "agent_si.automation.interface"


def _auto_iface():
    """Return the frozen automation contract module object."""
    try:
        return sys.modules[_IFACE_MODULE]
    except KeyError:
        raise RuntimeError(
            "frozen contract %r is not imported" % (_IFACE_MODULE,)
        )

__all__ = ("get_apps_card", "is_pause_effective")


def is_pause_effective(project_id: str) -> bool:
    """Cross-lane seam: pause owns the flag; default reads the real lane."""
    from agent_si.automation import pause as pause_flags
    return bool(pause_flags.is_effective(project_id))


def get_apps_card(project_id: str) -> auto_iface.AppsCardData:
    """REALIZATION_MAP ``apps.card.get``: stored facts for one project."""
    return _auto_iface().AppsCardData(
        project_id=project_id,
        service_ids=service_status.services_for_project(project_id),
        paused=bool(is_pause_effective(project_id)),
        generated_at=datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
    )
