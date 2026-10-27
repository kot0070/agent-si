# K04 Lane A2 — JSON-file-backed routing persistence.
# Stores decisions + assignments + snapshots + fallback records + profiles
# (role profiles, manager profile, pool bindings). The data directory is
# injected by the caller; the default lives under an app-data path the
# caller passes in, never a machine constant.
"""Portable JSON store for routing records (stdlib only)."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from . import types as T

if TYPE_CHECKING:
    from .types import RoutingAssignment, RoutingDecision, RoutingEvidenceSnapshot


def _atomic_write_json(path: str, payload: Any) -> None:
    """Write JSON atomically: temp file in the same folder + fsync + replace."""
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True, default=str)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _read_json(path: str, default: Any) -> Any:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return default


class RoutingStore:
    """JSON-file persistence for routing records under an injected dir."""

    def __init__(self, data_dir: str) -> None:
        if not data_dir:
            raise ValueError("RoutingStore needs an explicit data_dir")
        self.data_dir = os.path.abspath(data_dir)
        self.root = os.path.join(self.data_dir, "routing")
        os.makedirs(self.root, exist_ok=True)
        self._paths = {
            "decisions": os.path.join(self.root, "decisions.json"),
            "assignments": os.path.join(self.root, "assignments.json"),
            "snapshots": os.path.join(self.root, "snapshots.json"),
            "fallbacks": os.path.join(self.root, "fallbacks.json"),
            "profiles": os.path.join(self.root, "profiles.json"),
            "meta": os.path.join(self.root, "meta.json"),
        }

    # -- generic table helpers -------------------------------------------

    def _load_table(self, name: str) -> Dict[str, Any]:
        data = _read_json(self._paths[name], {})
        return data if isinstance(data, dict) else {}

    def _save_table(self, name: str, table: Dict[str, Any]) -> None:
        _atomic_write_json(self._paths[name], table)

    # -- decisions --------------------------------------------------------

    def save_decision(self, decision: T.RoutingDecision,
                      assignments, snapshot: T.RoutingEvidenceSnapshot,
                      *, turn_cap: Optional[int] = None) -> str:
        """Persist one decision with its assignments and snapshot.

        The turn-cap configuration rides in the meta envelope next to the
        frozen decision record (the frozen fields stay exactly as specified).
        """
        decisions = self._load_table("decisions")
        stored = self._load_table("assignments")
        snaps = self._load_table("snapshots")
        meta = self._load_table("meta")
        decisions[decision.decision_id] = _freeze(decision)
        stored[decision.decision_id] = [_freeze(a) for a in assignments]
        snaps[decision.routing_snapshot_id] = _freeze(snapshot)
        meta[decision.decision_id] = {
            "turn_cap": turn_cap,
            "recorded_at": T.utcnow(),
            "routing_snapshot_id": decision.routing_snapshot_id,
        }
        self._save_table("decisions", decisions)
        self._save_table("assignments", stored)
        self._save_table("snapshots", snaps)
        self._save_table("meta", meta)
        return decision.decision_id

    def get_decision(self, decision_id: str) -> Optional[Dict[str, Any]]:
        return self._load_table("decisions").get(decision_id)

    def get_assignments(self, decision_id: str) -> List[Dict[str, Any]]:
        data = self._load_table("assignments").get(decision_id, [])
        return list(data) if isinstance(data, list) else []

    def get_snapshot(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        return self._load_table("snapshots").get(snapshot_id)

    def get_meta(self, decision_id: str) -> Optional[Dict[str, Any]]:
        return self._load_table("meta").get(decision_id)

    def why_replay(self, decision_id: str) -> Tuple[RoutingDecision,
                                      List[RoutingAssignment],
                                      RoutingEvidenceSnapshot]:
        """WHY_THIS_MODEL triple replayed from persisted evidence only.

        Returns (RoutingDecision, [RoutingAssignment, ...],
        RoutingEvidenceSnapshot) reconstructed from the persisted dicts,
        or None when no such decision was persisted. Live health/resource
        state is never consulted here: the records are byte-identical to
        what was stored, so history cannot drift. The meta envelope stays
        persisted alongside (see get_meta, untouched by replay).
        """
        decision = self.get_decision(decision_id)
        if decision is None:
            return None
        snapshot = self.get_snapshot(decision.get("routing_snapshot_id", ""))
        if snapshot is None:
            return None
        return (
            T.RoutingDecision(**decision),
            [T.RoutingAssignment(**row)
             for row in self.get_assignments(decision_id)],
            T.RoutingEvidenceSnapshot(**snapshot),
        )

    # -- fallback records --------------------------------------------------

    def save_fallback(self, record: T.FallbackRecord) -> str:
        table = self._load_table("fallbacks")
        table[record.fallback_id] = _freeze(record)
        self._save_table("fallbacks", table)
        return record.fallback_id

    def list_fallbacks(self, task_id: Optional[str] = None) -> List[Dict[str, Any]]:
        rows = list(self._load_table("fallbacks").values())
        if task_id is not None:
            rows = [r for r in rows if r.get("task_id") == task_id]
        return rows

    # -- profiles ----------------------------------------------------------

    def _profiles(self) -> Dict[str, Any]:
        table = self._load_table("profiles")
        table.setdefault("roles", {})
        table.setdefault("manager", None)
        table.setdefault("pools", {})
        return table

    def save_role_profile(self, profile: T.RoleModelProfile) -> None:
        table = self._profiles()
        table["roles"]["%s\x00%s" % (profile.project_id, profile.role)] = _freeze(profile)
        self._save_table("profiles", table)

    def get_role_profile(self, project_id: str, role: str) -> Optional[Dict[str, Any]]:
        return self._profiles()["roles"].get("%s\x00%s" % (project_id, role))

    def list_role_profiles(self, project_id: str) -> List[Dict[str, Any]]:
        prefix = "%s\x00" % project_id
        return [row for key, row in self._profiles()["roles"].items()
                if key.startswith(prefix)]

    def save_manager_profile(self, profile: T.DefaultManagerProfile) -> None:
        table = self._profiles()
        table["manager"] = _freeze(profile)
        self._save_table("profiles", table)

    def get_manager_profile(self) -> Optional[Dict[str, Any]]:
        return self._profiles()["manager"]

    # -- pool bindings -----------------------------------------------------

    def save_pool(self, binding) -> None:
        if hasattr(binding, "strategy"):
            strategy = binding.strategy
            project_id, role = binding.project_id, binding.role
        else:
            strategy = binding.get("strategy")
            project_id, role = binding["project_id"], binding["role"]
        T.check_enum("strategy", strategy, T.POOL_STRATEGIES)
        table = self._profiles()
        table["pools"]["%s\x00%s" % (project_id, role)] = _freeze(binding)
        self._save_table("profiles", table)

    def get_pool(self, project_id: str, role: str):
        row = self._profiles()["pools"].get("%s\x00%s" % (project_id, role))
        if isinstance(row, dict) and row.get("strategy") in T.LEGACY_POOL_STRATEGIES:
            row = dict(row)
            row["strategy"] = T.migrate_pool_strategy(row["strategy"])
        return row


def _freeze(record: Any) -> Any:
    """Convert a frozen dataclass (possibly nested) into plain JSON data."""
    data = asdict(record)
    return json.loads(json.dumps(data, sort_keys=True, default=str))
