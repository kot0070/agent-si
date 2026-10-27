"""Per-package load ledger plus bounded delta intake (lane B, coder B1).

Original code. Frozen shapes kept verbatim:
LedgerRow {package_id, agents:int, peak_concurrency:int, wall_time_s:float}.
V2 ONE-HOME: the shared kernel (ApplyOutcome, DecisionLog, DecisionRow,
utc_now, surface_rejection, hot_write_text) lives in common.py and is
re-exported here; LedgerRow/PackageLedger/package_report/persist_ledger/
load_ledger/build_package_report keep their canonical impls in this file.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

try:
    from .common import (
        ApplyOutcome,
        DecisionLog,
        DecisionRow,
        hot_write_text,
        surface_rejection,
        utc_now,
    )
except ImportError:  # lane tests load this module by file path (no package)
    import importlib.util as _importlib_util
    import sys as _fallback_sys

    _common_name = "agent_si.backend.orchestration.common"
    _common_module = _fallback_sys.modules.get(_common_name)
    if _common_module is None:
        _common_spec = _importlib_util.spec_from_file_location(
            _common_name,
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "common.py"),
        )
        _common_module = _importlib_util.module_from_spec(_common_spec)
        _fallback_sys.modules[_common_name] = _common_module
        _common_spec.loader.exec_module(_common_module)
    ApplyOutcome = _common_module.ApplyOutcome
    DecisionLog = _common_module.DecisionLog
    DecisionRow = _common_module.DecisionRow
    hot_write_text = _common_module.hot_write_text
    surface_rejection = _common_module.surface_rejection
    utc_now = _common_module.utc_now

REGISTER_PRESERVED = "PRESERVED"
REGISTER_CHANGED = "CHANGED"
REGISTER_MISSING = "MISSING"
REGISTER_CONTRADICTED = "CONTRADICTED"


@dataclass
class LedgerRow:
    package_id: str
    agents: int
    peak_concurrency: int
    wall_time_s: float

    def __post_init__(self) -> None:
        if not isinstance(self.agents, int) or isinstance(self.agents, bool):
            raise ValueError("agents must be an int")
        if not isinstance(self.peak_concurrency, int) or isinstance(self.peak_concurrency, bool):
            raise ValueError("peak_concurrency must be an int")
        if not isinstance(self.wall_time_s, (int, float)) or isinstance(
            self.wall_time_s, bool
        ):
            raise ValueError("wall_time_s must be a float")
        if self.agents < 0:
            raise ValueError("agents must be >= 0")
        if self.peak_concurrency < 0:
            raise ValueError("peak_concurrency must be >= 0")
        if float(self.wall_time_s) < 0:
            raise ValueError("wall_time_s must be >= 0")
        self.wall_time_s = float(self.wall_time_s)


class PackageLedger:
    def __init__(self) -> None:
        self.rows: dict[str, LedgerRow] = {}

    def record_row(
        self, package_id: str, agents: int, peak_concurrency: int, wall_time_s: float
    ) -> LedgerRow:
        row = LedgerRow(
            package_id=package_id,
            agents=agents,
            peak_concurrency=peak_concurrency,
            wall_time_s=wall_time_s,
        )
        self.rows[package_id] = row
        return row

    def get_row(self, package_id: str) -> LedgerRow | None:
        return self.rows.get(package_id)

    def package_ids(self) -> list[str]:
        return sorted(self.rows)


def package_report(
    ledger: PackageLedger, package_id: str, next_package_id: str | None = None
) -> dict[str, Any]:
    row = ledger.get_row(package_id)
    if row is None:
        raise KeyError(f"no ledger row for package {package_id}")
    if next_package_id is None:
        nudge = f"review package {package_id} load before starting the next package"
    else:
        nudge = (
            f"review package {package_id} load "
            f"(agents {row.agents}, peak {row.peak_concurrency}, "
            f"wall {row.wall_time_s}s) before starting package {next_package_id}"
        )
    return {
        "row": {
            "package_id": row.package_id,
            "agents": row.agents,
            "peak_concurrency": row.peak_concurrency,
            "wall_time_s": row.wall_time_s,
        },
        "nudge": nudge,
        "auto_push": False,
    }


DEFAULT_LEDGER_CONFIG: dict[str, Any] = {
    "independent_audit": True,
    "budget_left": 100,
    "agents": 0,
    "max_agents": 8,
    "peak_concurrency": 0,
    "max_concurrency": 4,
}


class LedgerConfigStore:
    def __init__(
        self, config: Mapping[str, Any] | None = None, log: DecisionLog | None = None
    ) -> None:
        self.config: dict[str, Any] = dict(DEFAULT_LEDGER_CONFIG)
        if config:
            self.config.update(config)
        self.log: DecisionLog = log if log is not None else DecisionLog()


def validate_ledger_config_change(
    patch: Mapping[str, Any], current: Mapping[str, Any]
) -> tuple[bool, str]:
    merged = dict(current)
    merged.update(patch)
    if not merged.get("independent_audit"):
        return False, "audit independence broken: independent_audit must stay true"
    try:
        cost_value = float(patch.get("cost", 0))
    except (TypeError, ValueError):
        return False, "cost must be numeric"
    if cost_value > float(merged.get("budget_left", 0)):
        return False, f"over budget: cost {cost_value} exceeds budget left"
    if int(merged.get("agents", 0)) > int(merged.get("max_agents", 0)):
        return False, "over cap: agents exceed max_agents"
    if int(merged.get("peak_concurrency", 0)) > int(merged.get("max_concurrency", 0)):
        return False, "over cap: peak concurrency exceeds max_concurrency"
    return True, "ok"


def apply_ledger_config_change(
    store: LedgerConfigStore,
    statement: str,
    reason: str,
    authority: str,
    patch: Mapping[str, Any],
) -> ApplyOutcome:
    ok, check_reason = validate_ledger_config_change(patch, store.config)
    if not ok:
        outcome = ApplyOutcome(accepted=False, reason=check_reason)
        outcome.surfaced = surface_rejection(outcome)
        return outcome
    merged = dict(store.config)
    merged.update(patch)
    store.config = merged
    row = store.log.append("ledger-config", statement, reason, authority, utc_now())
    outcome = ApplyOutcome(accepted=True, reason="applied", row=row)
    outcome.surfaced = surface_rejection(outcome)
    return outcome


def intake_bounded_delta(
    taken: list[dict[str, Any]], delta: Mapping[str, Any], bound: int
) -> dict[str, Any]:
    items = delta.get("items", [])
    count = len(list(items))
    delta_id = str(delta.get("delta_id", "delta"))
    if count > bound:
        return {
            "accepted": False,
            "reason": f"delta {delta_id} over bound: {count} items exceed {bound}",
            "delta_id": delta_id,
        }
    taken.append({"delta_id": delta_id, "count": count})
    return {"accepted": True, "reason": "intake within bound", "delta_id": delta_id}


def persist_ledger(path: str, ledger: PackageLedger) -> None:
    payload = {
        pid: {
            "package_id": row.package_id,
            "agents": row.agents,
            "peak_concurrency": row.peak_concurrency,
            "wall_time_s": row.wall_time_s,
        }
        for pid, row in ledger.rows.items()
    }
    hot_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def load_ledger(path: str) -> PackageLedger:
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    ledger = PackageLedger()
    for package_id in sorted(payload):
        item = payload[package_id]
        ledger.record_row(
            str(item["package_id"]),
            agents=int(item["agents"]),
            peak_concurrency=int(item["peak_concurrency"]),
            wall_time_s=float(item["wall_time_s"]),
        )
    return ledger


def build_package_report(
    ledger: PackageLedger,
    ordered_ids: list[str],
    out_path: str | None = None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    ids = list(ordered_ids)
    for index, package_id in enumerate(ids):
        nxt = ids[index + 1] if index + 1 < len(ids) else None
        items.append(package_report(ledger, package_id, nxt))
    if out_path is not None:
        lines = [
            f"{item['row']['package_id']} agents={item['row']['agents']} "
            f"peak={item['row']['peak_concurrency']} "
            f"wall={item['row']['wall_time_s']} nudge={item['nudge']}"
            for item in items
        ]
        hot_write_text(out_path, "\n".join(lines) + "\n")
    return items


@dataclass
class LedgerReport:
    packages: list[dict[str, Any]] = field(default_factory=list)


def build_ledger_report(
    ledger: PackageLedger,
    ordered_ids: Sequence[str],
    out_path: str | None = None,
) -> LedgerReport:
    report = LedgerReport()
    ids = list(ordered_ids)
    for index, package_id in enumerate(ids):
        nxt = ids[index + 1] if index + 1 < len(ids) else None
        report.packages.append(package_report(ledger, package_id, nxt))
    if out_path is not None:
        lines = [
            f"{item['row']['package_id']} agents={item['row']['agents']} "
            f"peak={item['row']['peak_concurrency']} "
            f"wall={item['row']['wall_time_s']} nudge={item['nudge']}"
            for item in report.packages
        ]
        hot_write_text(out_path, "\n".join(lines) + "\n")
    return report
