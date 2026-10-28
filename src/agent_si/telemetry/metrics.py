"""Metrics (Manifest §11 METRIC_SEMANTICS; §11A TIME_ACCOUNTING_SEMANTICS).

MetricRecord rows carry value+unit+state+source (all required at write);
cost exists only via CostCalculator over a PricingSnapshot (UNAVAILABLE
without prices, never zero/estimated); ACTIVE_WALL_TIME is the union of
active execution intervals (parallel counts once, never a role-time sum).
No AI-generated numbers: every row names its recorded source.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


class MetricState(str, Enum):
    """Manifest §11 ENUM MetricState."""

    MEASURED = "MEASURED"
    CALCULATED = "CALCULATED"
    ESTIMATED = "ESTIMATED"
    INFERRED = "INFERRED"
    UNAVAILABLE = "UNAVAILABLE"


TIME_METRIC_NAMES = frozenset(
    {
        "active_wall_time",
        "ai_execution_time",
        "role_execution_time",
        "waiting_time",
    }
)
"""Manifest §11A time metric names."""


class MetricError(Exception):
    """Base error for metric records."""


class InvalidIntervalError(MetricError):
    """A wall-time interval is malformed (end before start, non-numeric)."""


@dataclass(frozen=True)
class MetricRecord:
    """Manifest §11 MetricRecord: value+unit+state+source required at write."""

    metric_id: str = ""
    project_id: str = ""
    metric_name: str = ""
    value: float = 0.0
    unit: str = ""
    state: MetricState = MetricState.UNAVAILABLE
    source: str = ""
    task_id: Optional[str] = None
    run_id: Optional[str] = None
    recorded_at: str = ""

    def __post_init__(self) -> None:
        if not self.metric_id:
            raise ValueError("metric_id is REQUIRED")
        if not self.project_id:
            raise ValueError("project_id is REQUIRED")
        if not self.metric_name:
            raise ValueError("metric_name is REQUIRED")
        if self.value is None or isinstance(self.value, bool):
            raise ValueError("value is REQUIRED (a real number)")
        if not isinstance(self.value, (int, float)):
            raise ValueError("value must be numeric, got %r" % type(self.value))
        if not self.unit:
            raise ValueError("unit is REQUIRED")
        if isinstance(self.state, str) and not isinstance(self.state, MetricState):
            object.__setattr__(self, "state", MetricState(self.state))
        if not isinstance(self.state, MetricState):
            raise ValueError("state is REQUIRED (a MetricState)")
        if not self.source:
            raise ValueError("source is REQUIRED (canonical provenance field)")


@dataclass(frozen=True)
class PricingSnapshot:
    """Manifest §11 PricingSnapshot: authoritative when used for cost."""

    pricing_snapshot_id: str = ""
    provider_id: str = ""
    model_id: str = ""
    currency: str = ""
    effective_at: str = ""
    source: str = ""
    created_at: str = ""
    hash: str = ""
    input_token_price: Optional[float] = None
    output_token_price: Optional[float] = None
    cached_token_price: Optional[float] = None
    reasoning_token_price: Optional[float] = None
    request_price: Optional[float] = None
    other_rules: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "pricing_snapshot_id",
            "provider_id",
            "model_id",
            "currency",
            "source",
        ):
            if not getattr(self, name):
                raise ValueError("%s is REQUIRED" % name)
        if not isinstance(self.other_rules, tuple):
            object.__setattr__(
                self, "other_rules", tuple(self.other_rules or ())
            )


@dataclass(frozen=True)
class TokenUsage:
    """Measured token/request usage feeding CostCalculator (never estimated)."""

    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    requests: int = 0

    def __post_init__(self) -> None:
        for name in (
            "input_tokens",
            "output_tokens",
            "cached_tokens",
            "reasoning_tokens",
            "requests",
        ):
            count = getattr(self, name)
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                raise ValueError("%s must be a non-negative int" % name)


class CostCalculator:
    """Cost only via a PricingSnapshot (Manifest §11).

    Without a snapshot, or when a needed price is missing, the result is
    an UNAVAILABLE record: cost is never zero and never estimated.
    Historical cost reproduces by passing the original snapshot.
    """

    @staticmethod
    def calculate(
        usage: TokenUsage,
        snapshot: Optional[PricingSnapshot],
        *,
        metric_id: str,
        project_id: str,
        task_id: Optional[str] = None,
        run_id: Optional[str] = None,
        recorded_at: str = "",
        source: str = "",
    ) -> MetricRecord:
        legs = (
            (usage.input_tokens, None if snapshot is None else snapshot.input_token_price),
            (
                usage.output_tokens,
                None if snapshot is None else snapshot.output_token_price,
            ),
            (
                usage.cached_tokens,
                None if snapshot is None else snapshot.cached_token_price,
            ),
            (
                usage.reasoning_tokens,
                None if snapshot is None else snapshot.reasoning_token_price,
            ),
            (usage.requests, None if snapshot is None else snapshot.request_price),
        )
        needed = [(count, price) for count, price in legs if count]
        priced = snapshot is not None and needed and all(
            price is not None for _, price in needed
        )
        if not priced:
            return MetricRecord(
                metric_id=metric_id,
                project_id=project_id,
                metric_name="cost",
                value=0.0,
                unit="unknown" if snapshot is None else snapshot.currency,
                state=MetricState.UNAVAILABLE,
                source=source or "cost-calculator",
                task_id=task_id,
                run_id=run_id,
                recorded_at=recorded_at,
            )
        assert snapshot is not None
        total = sum(count * price for count, price in needed if price is not None)
        return MetricRecord(
            metric_id=metric_id,
            project_id=project_id,
            metric_name="cost",
            value=total,
            unit=snapshot.currency,
            state=MetricState.CALCULATED,
            source=source or snapshot.source,
            task_id=task_id,
            run_id=run_id,
            recorded_at=recorded_at,
        )


def active_wall_time(intervals: Iterable[Tuple[float, float]]) -> float:
    """Union length of active execution intervals (§11A ACTIVE_WALL_TIME).

    Parallel intervals count once; disjoint intervals add. Raises
    InvalidIntervalError on malformed input.
    """
    spans = []
    for start, end in intervals:
        if (
            not isinstance(start, (int, float))
            or not isinstance(end, (int, float))
            or isinstance(start, bool)
            or isinstance(end, bool)
        ):
            raise InvalidIntervalError("interval bounds must be numbers")
        if end < start:
            raise InvalidIntervalError("interval end before start")
        spans.append((float(start), float(end)))
    total = 0.0
    cursor: Optional[float] = None
    for start, end in sorted(spans):
        if cursor is None:
            cursor = start
            edge = end
        elif start <= edge:
            edge = max(edge, end)
        else:
            total += edge - cursor
            cursor, edge = start, end
    if cursor is not None:
        total += edge - cursor
    return total


class MetricRecordLog:
    """Append-only MetricRecord store (Manifest §55 + ports shape).

    Duplicate metric_id returns the stored record (re-collection with an
    identical ref attaches without duplicating measured totals).
    """

    def __init__(self) -> None:
        self._records: Dict[str, MetricRecord] = {}

    def append(self, record: MetricRecord) -> MetricRecord:
        stored = self._records.get(record.metric_id)
        if stored is not None:
            return stored
        self._records[record.metric_id] = record
        return record

    def load(self, metric_id: str) -> Optional[MetricRecord]:
        return self._records.get(metric_id)

    def list_by_project(self, project_id: str) -> List[MetricRecord]:
        return [
            record
            for record in self._records.values()
            if record.project_id == project_id
        ]

    def __len__(self) -> int:
        return len(self._records)
