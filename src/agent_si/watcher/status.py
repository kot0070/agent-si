"""Watcher status: stored facts only, never computed (lane A STEP2).

Owns the REALIZATION_MAP entry ``watcher.status.get`` (:func:`get`).
The payload replays stored facts: integrity from the stored verify, the
journal head from the stored rows, plus the stored generation stamp.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Tuple

from agent_si.watcher import integrity as integrity_store
from agent_si.watcher import journal as journal_store
from agent_si.watcher import stats as stats_home
from agent_si.watcher.journal import ERROR_CODES, WatcherError

__all__ = (
    "ERROR_CODES",
    "WatcherError",
    "WatcherStatus",
    "get",
    "reset_state",
)


@dataclass(frozen=True)
class WatcherStatus:
    """Status payload: project, stored integrity, stored journal head.

    Plus the watcher model truth: the exact model name that answered
    the latest abnormal WATCH_DECISION row (a stored fact), or
    "Rules only" when no model answered yet.

    FXWATCH served numbers (engine-held, never invented): rule checks
    done, alerts raised, last check time, watcher model calls plus
    tokens (0 while quiet), what it watches now (live runs plus live
    agents), last action summary in stored words, per-rule fired
    counts. Unknown times/rows read "" and render as "not known".
    """

    project_id: str
    integrity_ok: bool = False
    journal_head: str = ""
    generated_at: str = ""
    watcher_model: str = "Rules only"
    checks_done: int = 0
    alerts_raised: int = 0
    last_check_at: str = ""
    watcher_calls: int = 0
    watcher_tokens: int = 0
    watched_runs: int = 0
    watched_agents: int = 0
    last_action: str = ""
    rules_fired: Tuple[Tuple[str, int], ...] = ()


def _utcnow() -> str:
    """Current UTC time rendered like the frozen timestamps."""
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _watcher_model(project_id: str) -> str:
    """Exact model that answered the latest abnormal decision, else Rules.

    Reads stored WATCH_DECISION rows only: the newest row carrying both
    a ``model=`` and an ``action=`` marker names the model that
    answered; default-action and OFF-marker rows name no model.
    """
    try:
        rows = journal_store.stored_rows(str(project_id), "WATCH_DECISION")
    except Exception:
        return "Rules only"
    for row in reversed(list(rows)):
        try:
            summary = str(row.summary)
        except Exception:
            continue
        if "model=" not in summary or "action=" not in summary:
            continue
        try:
            name = summary.split("model=", 1)[1].split()[0].strip()
        except (IndexError, AttributeError):
            continue
        if name:
            return name
    return "Rules only"


def _watched_now(project_id: str) -> Tuple[int, int]:
    """Live runs for the project plus live agents now (real served rows)."""
    runs = 0
    try:
        from agent_si.automation import runner as _runner_home

        live_states = ("RUNNING", "PENDING")
        count = 0
        for run in _runner_home.list_runs(str(project_id)):
            try:
                if str(getattr(run, "state", "")) in live_states:
                    count += 1
            except Exception:
                continue
        runs = int(count)
    except Exception:
        runs = 0
    agents = 0
    try:
        from agent_si.backend import agents_live as _live_home

        store = getattr(_live_home, "_LIVE_ROWS", {})
        if isinstance(store, dict):
            # FXZERO R4: a finished run is not watched: count live rows
            # only, never RETURNED/BLOCKED history.
            is_live = getattr(_live_home, "is_live_row", None)
            for row in store.values():
                try:
                    if not isinstance(row, dict):
                        continue
                    if callable(is_live):
                        if is_live(row):
                            agents += 1
                    elif str(row.get("status", "")).upper() in (
                            "RUNNING", "QUEUED", "CREATED", "PENDING"):
                        agents += 1
                except Exception:
                    continue
    except Exception:
        agents = 0
    return runs, agents


def _last_action(project_id: str) -> str:
    """Newest stored row summary (WATCH_DECISION preferred), else ""."""
    try:
        decisions = journal_store.stored_rows(str(project_id), "WATCH_DECISION")
        if decisions:
            return str(decisions[-1].summary or "")
    except Exception:
        pass
    try:
        rows = journal_store.stored_rows(str(project_id))
        if rows:
            return str(rows[-1].summary or "")
    except Exception:
        pass
    return ""


def get(project_id: str) -> WatcherStatus:
    """Serve stored facts: stored verify plus stored journal head."""
    key = str(project_id)
    try:
        integrity_store.verify(key)
        ok = True
    except WatcherError:
        ok = False
    rows = journal_store.list_events(key)
    # K08F2: generated_at is the time of the stored facts served (the
    # stored head stamp; "" when nothing is stored), so two reads with
    # no state change serve equal payloads.
    if rows:
        head = rows[-1].entry_id
        generated_at = rows[-1].timestamp
    else:
        head = ""
        generated_at = ""
    try:
        counters = stats_home.get_stats(key)
    except Exception:
        counters = {}
    try:
        fired_map = dict(counters.get("fired", {}))  # type: ignore[arg-type]
    except Exception:
        fired_map = {}
    try:
        rules_fired = tuple(
            (str(rule_id), int(count))
            for rule_id, count in sorted(fired_map.items())
        )
    except Exception:
        rules_fired = ()
    watched_runs, watched_agents = _watched_now(key)
    return WatcherStatus(
        project_id=key,
        integrity_ok=ok,
        journal_head=head,
        generated_at=generated_at,
        watcher_model=_watcher_model(key),
        checks_done=int(counters.get("checks_done", 0)),  # type: ignore[arg-type]
        alerts_raised=int(counters.get("alerts_raised", 0)),  # type: ignore[arg-type]
        last_check_at=str(counters.get("last_check_at", "")),  # type: ignore[arg-type]
        watcher_calls=int(counters.get("watcher_calls", 0)),  # type: ignore[arg-type]
        watcher_tokens=int(counters.get("watcher_tokens", 0)),  # type: ignore[arg-type]
        watched_runs=int(watched_runs),
        watched_agents=int(watched_agents),
        last_action=_last_action(key),
        rules_fired=rules_fired,
    )


def reset_state() -> None:
    """Status keeps no per-run state; present for probe isolation."""
    return None
