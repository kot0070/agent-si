"""Lane B STEP2 launcher: moves queued runs to RUNNING under guard.

Launch checks the pause before acting, asks the guard hook before the state
move, refuses active runs, and sends a journal notice on every launch.
"""

import sys

from agent_si.automation import pause as pause_flags
from agent_si.automation import runner


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

_journal = None
_guard = None


def set_journal_hook(hook):
    """Set the journal notice hook (or None to silence notices)."""
    global _journal
    _journal = hook


def set_guard_hook(hook):
    """Set the guard check hook (or None to skip guard checks)."""
    global _guard
    _guard = hook


def launch(project_id, run_id):
    """Launch a queued run; refused while paused or when the guard refuses."""
    run = runner.get_run(project_id, run_id)
    if run.state == "RUNNING":
        raise _auto_iface().AutomationError(
            code="AUTOMATION_RUN_ACTIVE",
            detail="run %s already active" % run_id,
        )
    if pause_flags.is_effective(project_id):
        raise _auto_iface().AutomationError(
            code="AUTOMATION_PAUSED",
            detail="automation paused for %s" % project_id,
        )
    if _guard is not None and not _guard(project_id, "runs/%s" % run_id):
        raise _auto_iface().AutomationError(
            code="AUTOMATION_PAUSED",
            detail="guard check refused launch of %s" % run_id,
        )
    launched = runner.activate_run(project_id, run_id)
    if _journal is not None:
        _journal(
            project_id,
            "launcher",
            "AUTOMATION_RUN",
            "run launched %s" % run_id,
            refs=(run_id,),
        )
    return launched
