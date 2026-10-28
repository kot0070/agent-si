"""K02R4 backend shim: the frozen ENGINE lazy-import path (M-MANAGER).

Thin re-export shim ONLY: re-exports run_task_streamed and RunEvent
from the canonical runtime manager with zero added logic, so the
frozen ENGINE lazy import (agent_si.backend.chat_stream MANAGER_MODULE)
resolves. No logic lives here; the canonical module owns the run.
"""

from __future__ import annotations

from agent_si.runtime.manager import RunEvent, run_task_streamed

__all__ = [
    "RunEvent",
    "run_task_streamed",
]
