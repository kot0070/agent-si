"""K09-B telemetry counters, STEP2 (implemented behaviour).

FROZEN-IFACE-K09B-v1: type and function names are frozen, do not rename.
Module-global stored-records list; reports derive only from stored records.
"""

from __future__ import annotations

from dataclasses import dataclass

import sys as _mod_sys

_mod_sys.modules.setdefault(
    "src." + __name__ if not __name__.startswith("src.") else __name__[4:],
    _mod_sys.modules[__name__],
)
"""Dual-harness identity: root-based (src.*) and src-based (agent_si.*)
imports resolve to this same module object, so module-global stores
(_records) are shared whatever path the harness uses."""


@dataclass
class KbTelemetryRecord:
    role: str
    agent: str
    tokens: int
    cost: float
    kind: str


_records: list[KbTelemetryRecord] = []


def record_hit(role: str, agent: str, tokens: int, cost: float) -> None:
    _records.append(KbTelemetryRecord(role, agent, tokens, cost, "hit"))


def record_miss(role: str, agent: str, tokens: int, cost: float) -> None:
    _records.append(KbTelemetryRecord(role, agent, tokens, cost, "miss"))


def record_web_fallback(role: str, agent: str, tokens: int, cost: float) -> None:
    _records.append(KbTelemetryRecord(role, agent, tokens, cost, "web_fallback"))


def list_records() -> list[KbTelemetryRecord]:
    return list(_records)
