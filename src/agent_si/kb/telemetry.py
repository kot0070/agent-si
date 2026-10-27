"""K09-B telemetry counters, STEP2 (implemented behaviour).

FROZEN-IFACE-K09B-v1: type and function names are frozen, do not rename.
Module-global stored-records list; reports derive only from stored records.
"""

from __future__ import annotations

from dataclasses import dataclass


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
