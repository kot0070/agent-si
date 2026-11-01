"""FXDEVRUN: the autonomous dev engine (KANAPKA FXDEVRUN).

Small modules, never one file: ``protocol`` (wire JSON), ``records``
(run rows), ``roles`` (adapters, ledger, budget), ``actions`` (the
agent jail and the exec tool), ``audit`` (fresh auditor judging real
files and outputs), ``engine`` (the single public entry).
"""

from __future__ import annotations

from agent_si.runtime.devrun.engine import (
    run_dev_task,
    wants_devrun,
)

__all__ = [
    "run_dev_task",
    "wants_devrun",
]
