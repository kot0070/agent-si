"""Attempt/retry/fallback/correction counters (Manifest sections 16, 17A).

Counters kept distinct: retry_count, fallback_count, correction_count,
attempt_count. Authoritative, persistent, atomic updates, restart-safe:
every mutation is persisted (tmp file + atomic replace + fsync) before it
is returned, and state is reloaded from disk on construction, so a restart
resumes exact values and never double-counts.

Budget rule (section 16): a retry/fallback/attempt is allowed only while
its per-type limit AND the global attempt cap remain. The correction loop
is always a NEW run: the new run scope starts with reset counters while
the task-scoped correction count keeps incrementing (section 17C).
Phase-0 counters live in a separate namespace and never consume runtime
budgets. Exhaustion never auto-escalates; it raises BudgetExhaustedError
and the caller follows failure precedence / FallbackPolicy.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Union

try:
    from iface.frozen_manifest import manifest
except ImportError:  # alternate layout: the iface/ directory itself on sys.path
    from frozen_manifest import manifest

RETRY = "retry"
FALLBACK = "fallback"
CORRECTION = "correction"
ATTEMPT = "attempt"
COUNTED_KINDS = (RETRY, FALLBACK, CORRECTION, ATTEMPT)

PHASE0_PREFIX = "phase0:"
STATE_VERSION = 1


class BudgetExhaustedError(Exception):
    """A per-type or global counter budget is exhausted (Manifest section 16).

    Carries scope, kind, value, limit, and which budget bound ("per-type"
    or "global"). Exhaustion never auto-escalates; the caller follows
    failure precedence / FallbackPolicy.
    """

    def __init__(
        self, scope: str, kind: str, value: int, limit: int, budget: str
    ) -> None:
        super().__init__(
            "counter budget exhausted: scope=%r kind=%r value=%d limit=%d "
            "budget=%s" % (scope, kind, value, limit, budget)
        )
        self.scope = scope
        self.kind = kind
        self.value = value
        self.limit = limit
        self.budget = budget


class CorruptCounterStateError(Exception):
    """Persisted counter state exists but is unreadable; refusing silent reset."""


@dataclass(frozen=True)
class CounterBudgets:
    """Section 16 RetryPolicy caps plus fallback caps plus the global cap.

    Per-type retry/correction defaults are the manifest DEFAULTS; fallback
    per-run/per-task caps are local policy defaults (the manifest names the
    fields max_fallbacks_per_run / max_fallbacks_per_task without numeric
    defaults). global_attempt_cap None derives to 1 initial + executor max.
    """

    executor_attempt_max: int = 3
    provider_retry_max: int = 2
    format_retry_max: int = 1
    verification_retry_max: int = 1
    verification_correction_max: int = 2
    audit_correction_max: int = 2
    runtime_correction_max: int = 3
    max_fallbacks_per_run: int = 2
    max_fallbacks_per_task: int = 5
    global_attempt_cap: Optional[int] = None

    @property
    def effective_global_attempt_cap(self) -> int:
        """Global cap: explicit value, else initial attempt + executor max."""
        if self.global_attempt_cap is not None:
            return self.global_attempt_cap
        return 1 + self.executor_attempt_max


@dataclass(frozen=True)
class CounterSnapshot:
    """Point-in-time view of the four distinct counters for one scope."""

    scope: str
    retry_count: int = 0
    fallback_count: int = 0
    correction_count: int = 0
    attempt_count: int = 0


def run_scope(run_id: str) -> str:
    """Scope key for per-run counters (correction loop = new run = new key)."""
    return "run:%s" % run_id


def task_scope(task_id: str) -> str:
    """Scope key for per-task counters (correction totals, task fallbacks)."""
    return "task:%s" % task_id


def _blank_counts() -> Dict[str, int]:
    return {RETRY: 0, FALLBACK: 0, CORRECTION: 0, ATTEMPT: 0}


def _load_state(path: Path) -> Dict[str, Dict[str, int]]:
    try:
        text = path.read_bytes().decode("utf-8")
    except FileNotFoundError:
        return {}
    try:
        doc = json.loads(text)
    except ValueError as exc:
        raise CorruptCounterStateError(
            "counter state at %s is not valid JSON: %s" % (path, exc)
        )
    if not isinstance(doc, dict) or not isinstance(doc.get("scopes"), dict):
        raise CorruptCounterStateError(
            "counter state at %s has no 'scopes' object" % path
        )
    scopes: Dict[str, Dict[str, int]] = {}
    for scope, counts in doc["scopes"].items():
        if not isinstance(counts, dict):
            raise CorruptCounterStateError(
                "counter state at %s: scope %r is not an object" % (path, scope)
            )
        merged = _blank_counts()
        for kind in COUNTED_KINDS:
            value = counts.get(kind, 0)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise CorruptCounterStateError(
                    "counter state at %s: scope %r kind %r is not a "
                    "non-negative int" % (path, scope, kind)
                )
            merged[kind] = value
        scopes[str(scope)] = merged
    return scopes


def _save_state(path: Path, scopes: Dict[str, Dict[str, int]]) -> None:
    """Persist atomically: tmp file + flush + fsync + atomic replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    payload = json.dumps(
        {"version": STATE_VERSION, "scopes": scopes},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    with open(tmp, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


class FileCounterStore(manifest.CounterStore):
    """Manifest CounterStore port: atomic, restart-safe counter bumps.

    increment(scope, kind, limit) -> value: bumps one named counter in one
    scope, enforcing the supplied limit. Backed by ReworkCounterRecord /
    FallbackCounterRecord-shaped persisted state (scope -> kind -> value).
    """

    def __init__(self, path: Union[str, Path]) -> None:
        self._path = Path(path)
        self._lock = threading.RLock()

    def increment(self, scope: str, kind: str, limit: int) -> int:
        with self._lock:
            scopes = _load_state(self._path)
            counts = scopes.setdefault(str(scope), _blank_counts())
            value = counts.get(str(kind), 0)
            if value >= limit:
                raise BudgetExhaustedError(str(scope), str(kind), value, limit, "per-type")
            value += 1
            counts[str(kind)] = value
            _save_state(self._path, scopes)
            return value

    def load(self, scope: str, kind: str) -> int:
        """Current value without mutating (restart-safe read)."""
        with self._lock:
            scopes = _load_state(self._path)
            return scopes.get(str(scope), {}).get(str(kind), 0)


class PersistentCounters:
    """Four-apart, budgeted, restart-safe counters (sections 16, 17A, 17C).

    One instance owns one state file. Scopes are opaque strings; use
    run_scope()/task_scope() for the run/task convention. Correction totals
    belong in a task scope (section 17C runtime_correction_count[task_id]);
    run scopes reset on every correction loop via new_run()/record_correction().
    """

    def __init__(
        self, path: Union[str, Path], budgets: CounterBudgets = CounterBudgets()
    ) -> None:
        self._path = Path(path)
        self._budgets = budgets
        self._lock = threading.RLock()

    @property
    def budgets(self) -> CounterBudgets:
        return self._budgets

    @staticmethod
    def _key(scope: str, phase0: bool) -> str:
        if phase0:
            return PHASE0_PREFIX + scope
        return scope

    @staticmethod
    def _require_kind(kind: str) -> str:
        if kind not in COUNTED_KINDS:
            raise ValueError("unknown counter kind %r; counted kinds: %s" % (kind, COUNTED_KINDS))
        return kind

    def _snapshot_locked(self, key: str, scopes: Dict[str, Dict[str, int]]) -> CounterSnapshot:
        counts = scopes.get(key, _blank_counts())
        return CounterSnapshot(
            scope=key,
            retry_count=counts[RETRY],
            fallback_count=counts[FALLBACK],
            correction_count=counts[CORRECTION],
            attempt_count=counts[ATTEMPT],
        )

    def snapshot(self, scope: str, *, phase0: bool = False) -> CounterSnapshot:
        """Current counts for a scope; Phase-0 reads its separate namespace."""
        with self._lock:
            return self._snapshot_locked(self._key(scope, phase0), _load_state(self._path))

    def new_run(self, scope: str) -> CounterSnapshot:
        """Reset a run scope: the correction loop is a new run (section 17A)."""
        with self._lock:
            scopes = _load_state(self._path)
            scopes[str(scope)] = _blank_counts()
            _save_state(self._path, scopes)
            return self._snapshot_locked(str(scope), scopes)

    def _per_type_limit(self, key: str, kind: str) -> int:
        budgets = self._budgets
        if kind == RETRY:
            return budgets.executor_attempt_max
        if kind == FALLBACK:
            if key.startswith("task:") or key.startswith(PHASE0_PREFIX + "task:"):
                return budgets.max_fallbacks_per_task
            return budgets.max_fallbacks_per_run
        if kind == CORRECTION:
            return budgets.runtime_correction_max
        return budgets.effective_global_attempt_cap

    def _check_locked(
        self, key: str, kind: str, counts: Dict[str, int]
    ) -> None:
        """Enforce per-type AND global budgets before any bump (section 16)."""
        limit = self._per_type_limit(key, kind)
        if counts[kind] >= limit:
            raise BudgetExhaustedError(key, kind, counts[kind], limit, "per-type")
        if kind in (RETRY, FALLBACK, ATTEMPT):
            cap = self._budgets.effective_global_attempt_cap
            if counts[ATTEMPT] >= cap:
                raise BudgetExhaustedError(key, kind, counts[ATTEMPT], cap, "global")

    def budget_remaining(self, scope: str, kind: str, *, phase0: bool = False) -> int:
        """Binding remaining budget for kind: min(per-type, global) where both apply."""
        self._require_kind(kind)
        key = self._key(scope, phase0)
        with self._lock:
            counts = _load_state(self._path).get(key, _blank_counts())
            remaining = self._per_type_limit(key, kind) - counts[kind]
            if kind in (RETRY, FALLBACK, ATTEMPT):
                global_remaining = (
                    self._budgets.effective_global_attempt_cap - counts[ATTEMPT]
                )
                remaining = min(remaining, global_remaining)
            return max(0, remaining)

    def _bump_locked(
        self, scopes: Dict[str, Dict[str, int]], key: str, *kinds: str
    ) -> CounterSnapshot:
        counts = scopes.setdefault(key, _blank_counts())
        for kind in kinds:
            self._check_locked(key, kind, counts)
        for kind in kinds:
            counts[kind] += 1
        _save_state(self._path, scopes)
        return self._snapshot_locked(key, scopes)

    def record_initial(self, scope: str, *, phase0: bool = False) -> CounterSnapshot:
        """Initial execution-producing assignment: attempt only, never retry budget."""
        with self._lock:
            scopes = _load_state(self._path)
            return self._bump_locked(scopes, self._key(scope, phase0), ATTEMPT)

    def record_retry(self, scope: str, *, phase0: bool = False) -> CounterSnapshot:
        """Same-run retry: same run + new attempt; retry AND attempt counted apart."""
        with self._lock:
            scopes = _load_state(self._path)
            return self._bump_locked(scopes, self._key(scope, phase0), RETRY, ATTEMPT)

    def record_fallback(self, scope: str, *, phase0: bool = False) -> CounterSnapshot:
        """Fallback: fallback AND attempt counted apart (same-run or new run)."""
        with self._lock:
            scopes = _load_state(self._path)
            return self._bump_locked(scopes, self._key(scope, phase0), FALLBACK, ATTEMPT)

    def record_verification_only(
        self, scope: str, *, phase0: bool = False
    ) -> CounterSnapshot:
        """Verifier/check-only retry: no new attempt, never correction_count."""
        with self._lock:
            return self._snapshot_locked(
                self._key(scope, phase0), _load_state(self._path)
            )

    def record_correction(
        self, task_id: str, new_run_id: str
    ) -> CounterSnapshot:
        """Correction loop after failed verification/audit: always a NEW run.

        Increments the task-scoped correction total (section 17C runtime
        count; every correction run increments it) and resets the new run
        scope. Returns the reset new-run snapshot.
        """
        with self._lock:
            scopes = _load_state(self._path)
            task_key = task_scope(task_id)
            counts = scopes.setdefault(task_key, _blank_counts())
            self._check_locked(task_key, CORRECTION, counts)
            counts[CORRECTION] += 1
            run_key = run_scope(new_run_id)
            scopes[run_key] = _blank_counts()
            _save_state(self._path, scopes)
            return self._snapshot_locked(run_key, scopes)


__all__ = [
    "RETRY",
    "FALLBACK",
    "CORRECTION",
    "ATTEMPT",
    "COUNTED_KINDS",
    "PHASE0_PREFIX",
    "BudgetExhaustedError",
    "CorruptCounterStateError",
    "CounterBudgets",
    "CounterSnapshot",
    "FileCounterStore",
    "PersistentCounters",
    "run_scope",
    "task_scope",
]
