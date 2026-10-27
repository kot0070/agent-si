"""Lane B STEP2 pause flags: project-wide switch plus per-project switches.
Everything here only records intent; callers check is_effective before acting.
"""

import sys

#: Dotted name of the frozen automation contract module. Product code
#: keeps no static import of it; the module object is resolved late at
#: call time, so the raised error is the same class the tests catch.
_IFACE_MODULE = "agent_si.automation.interface"


def _auto_iface():
    """Return the frozen automation contract module object."""
    try:
        return sys.modules[_IFACE_MODULE]
    except KeyError:
        raise RuntimeError(
            "frozen contract %r is not imported" % (_IFACE_MODULE,)
        )

_GLOBAL_PAUSED = False
_GLOBAL_REASON = ""
_PROJECT_FLAGS = {}


def reset_state():
    """Clear the project-wide flag and every per-project flag."""
    global _GLOBAL_PAUSED, _GLOBAL_REASON
    _GLOBAL_PAUSED = False
    _GLOBAL_REASON = ""
    _PROJECT_FLAGS.clear()


def set_global(paused, reason):
    """Set the project-wide pause flag; pausing needs a non-empty reason."""
    global _GLOBAL_PAUSED, _GLOBAL_REASON
    if paused and not reason:
        raise _auto_iface().AutomationError(
            code="PAUSE_REASON_MISSING",
            detail="pausing needs a non-empty reason",
        )
    _GLOBAL_PAUSED = bool(paused)
    _GLOBAL_REASON = reason if paused else ""


def set_project(project_id, paused):
    """Set the pause flag scoped to one project."""
    _PROJECT_FLAGS[project_id] = bool(paused)


def is_effective(project_id):
    """Report whether the pause applies: project-wide flag or this project."""
    if _GLOBAL_PAUSED:
        return True
    return bool(_PROJECT_FLAGS.get(project_id, False))
