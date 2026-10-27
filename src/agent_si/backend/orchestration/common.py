"""Canonical shared kernel for orchestration lanes (integration-owned assembly).

This module dedups the DecisionRow/DecisionLog/ApplyOutcome/surface_rejection/
utc_now/hot_write_text truth previously copied across teamcard, ledger, parts,
graph, offload, steplimits, delta and gates. Lanes keep their own copies until
the integration Manager rewires them; nothing here imports any lane module
or interface.py (stdlib only: os, dataclasses, datetime).

Choice recorded (v2 C6/C12/C18; M4 drift left in place, behavior unchanged):
BOTH outcome shapes are carried as two dataclasses, not one unified dict.
ApplyOutcome {accepted, reason, row, surfaced} is the accepted-form used by
teamcard/ledger/parts/graph; AppliedOutcome {applied, reason, decision_ref}
is the applied-form kept by offload/steplimits/delta. V2 ONE-HOME (§20):
this kernel also carries the delta lane's plain-string surface form
(surface_rejection accepts a reason string), its dict-row log form
(DecisionLog takes an optional backing list with add/next_id/to_list)
and the path-returning hot_write_text; the offload/steplimits
plain-isoformat timestamps stay in their lanes. The kernel follows the
teamcard/ledger/gates/delta majority (compact-English surface,
Z-suffixed UTC isoformat).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def is_compact_english(text: str) -> bool:
    if not text or not text.strip():
        return False
    if any(ord(ch) > 127 for ch in text):
        return False
    words = text.split()
    return bool(words) and "  " not in text.strip() and text == text.strip()


def ensure_compact_english(text: str) -> str:
    cleaned = " ".join(text.split())
    if not is_compact_english(cleaned):
        raise ValueError("record text must be compact AI English (ascii, trimmed)")
    return cleaned


def hot_write_text(path: str, text: str) -> str:
    tmp_path = f"{path}.tmp-{os.getpid()}"
    with open(tmp_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    os.replace(tmp_path, path)
    return path


@dataclass
class DecisionRow:
    decision_id: str
    scope: str
    statement: str
    reason: str
    authority: str
    created_at: str


class DecisionLog:
    def __init__(self, backing: list | None = None) -> None:
        self.rows: list = backing if isinstance(backing, list) else []
        self._counters: dict[str, int] = {}

    def append(
        self, scope: str, statement: str, reason: str, authority: str, created_at: str
    ) -> DecisionRow:
        seq = self._counters.get(scope, 0) + 1
        self._counters[scope] = seq
        row = DecisionRow(
            decision_id=f"{scope}-{seq:04d}",
            scope=scope,
            statement=statement,
            reason=reason,
            authority=authority,
            created_at=created_at,
        )
        self.rows.append(row)
        return row

    def __len__(self) -> int:
        return len(self.rows)

    def __iter__(self):
        return iter(self.rows)

    def to_list(self) -> list:
        return self.rows

    def next_id(self, scope: str) -> str:
        count = sum(
            1 for r in self.rows if isinstance(r, dict) and r.get("scope") == scope
        )
        return f"{scope}-{count + 1:04d}"

    def add(self, scope: str, statement: str, reason: str, authority: str) -> dict:
        decision_id = self.next_id(scope)
        for row in self.rows:
            if isinstance(row, dict) and row.get("decision_id") == decision_id:
                raise ValueError(
                    f"POLICY_CONFLICT: duplicate decision_id {decision_id}"
                )
        row = {
            "decision_id": decision_id,
            "scope": scope,
            "statement": statement,
            "reason": reason,
            "authority": authority,
            "created_at": utc_now(),
        }
        self.rows.append(row)
        return row

    def __getitem__(self, index):
        return self.rows[index]


@dataclass
class ApplyOutcome:
    accepted: bool
    reason: str
    row: DecisionRow | None = None
    surfaced: str = ""


@dataclass
class AppliedOutcome:
    applied: bool
    reason: str
    decision_ref: str | None = None


def surface_rejection(outcome: ApplyOutcome | AppliedOutcome | str) -> str:
    if isinstance(outcome, str):
        return ensure_compact_english(outcome)
    if isinstance(outcome, ApplyOutcome):
        ok = outcome.accepted
    elif isinstance(outcome, AppliedOutcome):
        ok = outcome.applied
    else:
        raise TypeError(
            "surface_rejection needs ApplyOutcome, AppliedOutcome or str, "
            f"got {type(outcome).__name__}"
        )
    if ok:
        return ensure_compact_english("change applied")
    return ensure_compact_english(f"change refused: {outcome.reason}")
