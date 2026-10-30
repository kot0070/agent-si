"""K06 retry-budget exhaustion park (MH-1).

After the retry/correction budget is exhausted the run parks as
ESCALATED and the user gets an in-product escalation card (reason,
evidence refs, resume/discard) in chat and run view; no silent park.
The store is owned by the caller (per-app state on the served path);
this module holds no global state.
"""

from __future__ import annotations

from typing import Any

ESCALATED = "ESCALATED"

ESCALATION_CARD_TESTID = "escalation-card"


def build_escalation_card(
    run_id: str,
    reason: str,
    evidence_refs: list[str],
) -> dict[str, Any]:
    """Build the in-product escalation card (plain data, never a command)."""
    return {
        "testid": ESCALATION_CARD_TESTID,
        "state": ESCALATED,
        "run_id": run_id,
        "reason": reason,
        "evidence_refs": list(evidence_refs),
        "actions": ["resume", "discard"],
    }


def get_run_state(
    store: dict[str, dict[str, Any]],
    run_id: str,
) -> dict[str, Any]:
    """Return the tracked state for ``run_id`` (created on first sight)."""
    state = store.get(run_id)
    if state is None:
        state = {
            "run_id": run_id,
            "failures": 0,
            "state": "RUNNING",
            "evidence_refs": [],
            "card": None,
        }
        store[run_id] = state
    return state


def record_attempt(
    store: dict[str, dict[str, Any]],
    run_id: str,
    *,
    ok: bool,
    evidence_ref: str,
    budget: int,
) -> dict[str, Any]:
    """Record one retry/correction attempt against ``budget``.

    A passing attempt clears the failure count. A failing attempt past
    the budget parks the run as ESCALATED and attaches the escalation
    card; the park is returned, never silent.
    """
    state = get_run_state(store, run_id)
    refs = state["evidence_refs"]
    if evidence_ref not in refs:
        refs.append(evidence_ref)
    if ok:
        state["failures"] = 0
        state["state"] = "RUNNING"
        state["card"] = None
        return dict(state)
    state["failures"] = int(state.get("failures", 0)) + 1
    if state["failures"] > max(int(budget), 0):
        state["state"] = ESCALATED
        state["card"] = build_escalation_card(
            run_id,
            "retry/correction budget exhausted after %d failed attempts"
            % (state["failures"],),
            list(refs),
        )
    return dict(state)


def resume_run(
    store: dict[str, dict[str, Any]],
    run_id: str,
) -> dict[str, Any]:
    """Resume a parked run: failures cleared, back to RUNNING."""
    state = get_run_state(store, run_id)
    state["failures"] = 0
    state["state"] = "RUNNING"
    state["card"] = None
    return dict(state)


def discard_run(
    store: dict[str, dict[str, Any]],
    run_id: str,
) -> dict[str, Any]:
    """Discard a parked run: terminal DISCARDED, card kept as evidence."""
    state = get_run_state(store, run_id)
    state["state"] = "DISCARDED"
    return dict(state)
