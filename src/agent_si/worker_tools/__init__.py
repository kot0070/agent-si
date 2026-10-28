"""Lane A worker tool belt.

G6: the tool belt maps to ``agent_si.worker_tools``. This package owns
only the tool registry and the guarded dispatcher surface. G1 (argv-only
guard), G2/G5 and ``toolguard`` are consumed as read-only contracts;
their implementations live in other lanes and are never imported here
at runtime (see ``dispatcher``).
"""

from .dispatcher import get_registry, guarded_dispatch
from .registry import (
    ToolEntryPoint,
    ToolFunc,
    ToolNotFoundError,
    ToolRegistry,
)
from .types import ActionClass, AuthMapping, ToolResult

__all__ = [
    "ActionClass",
    "AuthMapping",
    "ToolEntryPoint",
    "ToolFunc",
    "ToolNotFoundError",
    "ToolRegistry",
    "ToolResult",
    "get_registry",
    "guarded_dispatch",
]
