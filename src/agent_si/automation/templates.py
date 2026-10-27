"""Automation templates (Lane B STEP2): working no-code builder.

Owns REALIZATION_MAP entry ``automation.template.instantiate``
(:func:`instantiate`). Templates are declarative no-code specs whose steps
reference only built-in observe/notify actions or imported packs
(built-in-or-import only): :func:`instantiate` refuses any id that is
neither built in nor imported with ``TEMPLATE_NOT_FOUND``, and
:func:`materialize` expands an instantiated template into a working
automation plan in which every step declares its outputs.

Every materialized plan pins the exact model id ``MODEL_ID``.
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

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

__all__ = (
    "MODEL_ID",
    "ACTION_CATALOG",
    "BUILTIN_TEMPLATE_IDS",
    "list_templates",
    "import_template",
    "instantiate",
    "materialize",
)

#: Exact model id carried by every materialized plan (verified exactly).
MODEL_ID = "meta/muse-spark-1.3-contributor"

#: Built-in observe/notify action catalog: action name to declared outputs.
#: No action here starts or stops external services.
ACTION_CATALOG: Dict[str, Tuple[str, ...]] = {
    "service.check": ("service_id", "state", "checked_at"),
    "service.watch": ("project_id", "changed", "checked_at"),
    "apps.card.read": ("project_id", "service_ids", "paused"),
    "container.scan": ("service_id", "verdict", "counts"),
    "journal.notify": ("entry_id", "timestamp"),
    "outage.signal": ("report_id", "stopped"),
}


def _steps(*specs: Tuple[str, Dict[str, Any], Tuple[str, ...]]) -> List[Dict[str, Any]]:
    return [
        {"action": action, "with": dict(params), "outputs": list(outputs)}
        for action, params, outputs in specs
    ]


_BUILTINS: Dict[str, Dict[str, Any]] = {
    "tpl-nightly": {
        "name": "nightly",
        "version": 1,
        "description": "Nightly sweep: check the API service, watch for "
        "changes, notify the journal.",
        "steps": _steps(
            ("service.check", {"service_id": "svc-api"}, ("service_id", "state", "checked_at")),
            ("service.watch", {"project_id": "proj-a"}, ("project_id", "changed", "checked_at")),
            ("journal.notify", {"kind": "AUTOMATION_RUN"}, ("entry_id", "timestamp")),
        ),
    },
    "tpl-healthcheck": {
        "name": "healthcheck",
        "version": 1,
        "description": "Health probe: check the API service then read the "
        "apps card facts.",
        "steps": _steps(
            ("service.check", {"service_id": "svc-api"}, ("service_id", "state", "checked_at")),
            ("apps.card.read", {"project_id": "proj-a"}, ("project_id", "service_ids", "paused")),
        ),
    },
    "tpl-container-audit": {
        "name": "container-audit",
        "version": 1,
        "description": "Read-only container audit: scan declared "
        "configuration for leaked values, notify the journal.",
        "steps": _steps(
            ("container.scan", {"service_id": "svc-container"}, ("service_id", "verdict", "counts")),
            ("journal.notify", {"kind": "SERVICE_STATE"}, ("entry_id", "timestamp")),
        ),
    },
    "tpl-usage-report": {
        "name": "usage-report",
        "version": 1,
        "description": "Usage rollup: read apps card facts, notify the "
        "journal.",
        "steps": _steps(
            ("apps.card.read", {"project_id": "proj-a"}, ("project_id", "service_ids", "paused")),
            ("journal.notify", {"kind": "AUTOMATION_RUN"}, ("entry_id", "timestamp")),
        ),
    },
    "tpl-watch-sweep": {
        "name": "watch-sweep",
        "version": 1,
        "description": "Watch sweep: observe service states for changes, "
        "notify the journal.",
        "steps": _steps(
            ("service.watch", {"project_id": "proj-a"}, ("project_id", "changed", "checked_at")),
            ("journal.notify", {"kind": "SERVICE_STATE"}, ("entry_id", "timestamp")),
        ),
    },
    "tpl-outage-drill": {
        "name": "outage-drill",
        "version": 1,
        "description": "Outage drill: check the cache service, rehearse the "
        "stop-and-report signal path, notify the journal.",
        "steps": _steps(
            ("service.check", {"service_id": "svc-cache"}, ("service_id", "state", "checked_at")),
            ("outage.signal", {"service_id": "svc-cache"}, ("report_id", "stopped")),
            ("journal.notify", {"kind": "OUTAGE_SIGNAL"}, ("entry_id", "timestamp")),
        ),
    },
}

BUILTIN_TEMPLATE_IDS: Tuple[str, ...] = tuple(_BUILTINS)

#: Imported templates: validated specs registered through import_template.
_IMPORTS: Dict[str, Dict[str, Any]] = {}


def _validate_spec(template_id: str, spec: Any) -> Dict[str, Any]:
    if not isinstance(spec, dict):
        raise ValueError("template spec for %r must be a mapping" % (template_id,))
    for field in ("name", "version", "steps"):
        if field not in spec:
            raise ValueError(
                "template spec for %r misses field %r" % (template_id, field)
            )
    steps = spec["steps"]
    if not isinstance(steps, list) or not steps:
        raise ValueError("template spec for %r needs a non-empty step list" % (template_id,))
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ValueError(
                "template spec for %r step %d must be a mapping" % (template_id, index)
            )
        action = step.get("action")
        if action not in ACTION_CATALOG:
            raise ValueError(
                "template spec for %r step %d uses unknown action %r "
                "(built-in-or-import only)" % (template_id, index, action)
            )
        outputs = step.get("outputs")
        if not isinstance(outputs, (list, tuple)) or not outputs:
            raise ValueError(
                "template spec for %r step %d must declare outputs" % (template_id, index)
            )
        allowed = ACTION_CATALOG[action]
        for output in outputs:
            if output not in allowed:
                raise ValueError(
                    "template spec for %r step %d declares undeclared output %r "
                    "for action %r" % (template_id, index, output, action)
                )
        params = step.get("with", {})
        if not isinstance(params, dict):
            raise ValueError(
                "template spec for %r step %d params must be a mapping" % (template_id, index)
            )
    return {
        "name": str(spec["name"]),
        "version": int(spec["version"]),
        "description": str(spec.get("description", "")),
        "steps": [
            {
                "action": str(step["action"]),
                "with": dict(step.get("with", {})),
                "outputs": [str(output) for output in step["outputs"]],
            }
            for step in steps
        ],
    }


def list_templates() -> Tuple[str, ...]:
    """Built-in plus imported template ids."""
    return tuple(_BUILTINS) + tuple(_IMPORTS)


def import_template(template_id: str, spec: Dict[str, Any]) -> str:
    """Register an imported no-code template spec (validated, else ValueError)."""
    if template_id in _BUILTINS:
        raise ValueError("template id %r is built in" % (template_id,))
    _IMPORTS[template_id] = _validate_spec(template_id, spec)
    return template_id


def _lookup(template_id: str) -> Dict[str, Any]:
    if template_id in _BUILTINS:
        return _BUILTINS[template_id]
    if template_id in _IMPORTS:
        return _IMPORTS[template_id]
    raise _auto_iface().AutomationError(
        "TEMPLATE_NOT_FOUND", "unknown template %r" % (template_id,)
    )


def instantiate(
    project_id: str,
    template_id: str,
    session_token: Optional[str] = None,
) -> auto_iface.AutomationTemplate:
    """REALIZATION_MAP ``automation.template.instantiate``.

    ``session_token`` is accepted for entry-point parity; refusal of missing
    or invalid tokens is enforced at the route seam, not here.
    """
    spec = _lookup(template_id)
    _auto_iface().journal_append_event(
        project_id,
        "automation",
        "AUTOMATION_RUN",
        "instantiate %s" % template_id,
        (template_id,),
    )
    return _auto_iface().AutomationTemplate(
        template_id=template_id,
        project_id=project_id,
        name=spec["name"],
        version=int(spec["version"]),
    )


def materialize(project_id: str, template_id: str) -> Dict[str, Any]:
    """Expand a template into a working automation plan (outputs declared)."""
    spec = _lookup(template_id)
    steps: List[Dict[str, Any]] = []
    for index, step in enumerate(spec["steps"]):
        action = step["action"]
        outputs = [str(output) for output in step["outputs"]]
        if action not in ACTION_CATALOG or not outputs:
            raise ValueError(
                "template %r step %d is not runnable" % (template_id, index)
            )
        steps.append(
            {"action": action, "with": dict(step["with"]), "outputs": outputs}
        )
    return {
        "template_id": template_id,
        "project_id": project_id,
        "name": spec["name"],
        "version": int(spec["version"]),
        "model": MODEL_ID,
        "steps": steps,
    }
