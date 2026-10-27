"""K09-B savings report, STEP2 (implemented behaviour).

FROZEN-IFACE-K09B-v1: function name is frozen, do not rename.
Figures derive only from stored telemetry records.
"""

from __future__ import annotations

from typing import Any

from src.agent_si.kb import telemetry


def savings_report() -> dict[str, Any]:
    records = telemetry.list_records()
    return {
        "hits": sum(1 for r in records if r.kind == "hit"),
        "misses": sum(1 for r in records if r.kind == "miss"),
        "web_fallbacks": sum(1 for r in records if r.kind == "web_fallback"),
        "tokens": sum(r.tokens for r in records),
        "cost": sum(r.cost for r in records),
    }
