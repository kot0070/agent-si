"""Lane B STEP2 pause flags: project-wide switch plus per-project switches.
Everything here only records intent; callers check is_effective before acting.
Pause decisions are governed: set_global and set_project record a journal
notice when a journal hook is bound (the same hook convention as the runner
lane); global decisions are recorded under the empty system scope,
per-project decisions under their own project.
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
_journal = None


def reset_state():
    """Clear the project-wide flag, every per-project flag and the hook."""
    global _GLOBAL_PAUSED, _GLOBAL_REASON, _journal
    _GLOBAL_PAUSED = False
    _GLOBAL_REASON = ""
    _PROJECT_FLAGS.clear()
    _journal = None


def set_journal_hook(hook):
    """Set the journal notice hook (or None to silence notices)."""
    global _journal
    _journal = hook


def _notify(project_id, summary, refs=()):
    """Record one AUTOMATION_RUN notice when a journal hook is bound."""
    if _journal is not None:
        _journal(project_id, "pause", "AUTOMATION_RUN", summary, refs=refs)


def set_global(paused, reason):
    """Set the project-wide pause flag; pausing needs a non-empty reason.

    The decision is journaled under the empty system scope.
    """
    global _GLOBAL_PAUSED, _GLOBAL_REASON
    if paused and not reason:
        raise _auto_iface().AutomationError(
            code="PAUSE_REASON_MISSING",
            detail="pausing needs a non-empty reason",
        )
    _GLOBAL_PAUSED = bool(paused)
    _GLOBAL_REASON = reason if paused else ""
    if paused:
        _notify("", "global pause set: %s" % (reason,))
    else:
        _notify("", "global pause cleared")


def set_project(project_id, paused):
    """Set the pause flag scoped to one project; the decision is journaled."""
    _PROJECT_FLAGS[project_id] = bool(paused)
    if paused:
        _notify(project_id, "project pause set %s" % (project_id,))
    else:
        _notify(project_id, "project pause cleared %s" % (project_id,))


def is_effective(project_id):
    """Report whether the pause applies: project-wide flag or this project."""
    if _GLOBAL_PAUSED:
        return True
    return bool(_PROJECT_FLAGS.get(project_id, False))


def get_project(project_id):
    """Report the per-project switch alone (ignores the global flag)."""
    return bool(_PROJECT_FLAGS.get(project_id, False))
