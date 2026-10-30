"""K09-B savings report, STEP2 (implemented behaviour).

FROZEN-IFACE-K09B-v1: function name is frozen, do not rename.
Figures derive only from stored telemetry records.
"""

from __future__ import annotations

from typing import Any

try:
    from agent_si.kb import telemetry
except ImportError:
    from src.agent_si.kb import telemetry

import sys as _mod_sys

_mod_sys.modules.setdefault(
    "src." + __name__ if not __name__.startswith("src.") else __name__[4:],
    _mod_sys.modules[__name__],
)
"""Dual-harness identity: root-based (src.*) and src-based (agent_si.*)
imports resolve to this same module object."""


def savings_report() -> dict[str, Any]:
    records = telemetry.list_records()
    return {
        "hits": sum(1 for r in records if r.kind == "hit"),
        "misses": sum(1 for r in records if r.kind == "miss"),
        "web_fallbacks": sum(1 for r in records if r.kind == "web_fallback"),
        "tokens": sum(r.tokens for r in records),
        "cost": sum(r.cost for r in records),
    }
