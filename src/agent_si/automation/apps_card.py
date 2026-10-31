"""Automation apps card (Lane B STEP2).

Owns REALIZATION_MAP entry ``apps.card.get`` (:func:`get_apps_card`).
Serves stored facts only, never computed values: the service id list comes
from the stored service registry and the paused flag comes from the pause
lane through the module-attribute seam :func:`is_pause_effective` (tests
install a FAKE-OF double there).
"""

from __future__ import annotations

import dataclasses
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


#: Late-built served card row: the frozen AppsCardData shape plus additive
#: served columns. Built lazily off the frozen base at call time so the
#: frozen shape itself never changes; the row IS-A AppsCardData.
_ServedAppsCard = None


def _served_card_cls():
    """Return the served card row class (frozen base, additive columns)."""
    global _ServedAppsCard
    base = _auto_iface().AppsCardData
    if _ServedAppsCard is None or not issubclass(_ServedAppsCard, base):
        @dataclasses.dataclass(frozen=True)
        class ServedAppsCard(base):
            services: tuple = ()
            safe_to_close: bool = True
            close_prompt: str = ""

        _ServedAppsCard = ServedAppsCard
    return _ServedAppsCard


def get_apps_card(project_id: str) -> auto_iface.AppsCardData:
    """REALIZATION_MAP ``apps.card.get``: stored facts for one project.

    Returns the frozen ``AppsCardData`` row plus additive served columns
    (``services`` named entries, ``safe_to_close``, ``close_prompt``) drawn
    from the same stored facts: service names come from the stored service
    registry and the closing prompt reflects the stored run rows. The
    frozen shape itself never changes.
    """
    from agent_si.automation import runner as runner_lane

    service_ids = service_status.services_for_project(project_id)
    active = [
        run.run_id
        for run in runner_lane.list_runs(project_id)
        if run.state == "RUNNING"
    ]
    return _served_card_cls()(
        project_id=project_id,
        service_ids=service_ids,
        paused=bool(is_pause_effective(project_id)),
        generated_at=datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        services=tuple(
            {"service_id": service_id, "name": service_id}
            for service_id in service_ids
        ),
        safe_to_close=not active,
        close_prompt=(
            ""
            if not active
            else "runs still active ("
            + ", ".join(active)
            + "); closing now may interrupt them"
        ),
    )
