"""Guarded dispatcher for the lane A worker tool belt.

Behaviour of the real implementation:
- G1 argv-only guard: ``argv`` is a list of words; a shell string is
  rejected with :exc:`TypeError` before anything else runs.
- MH-3 task-authorized list: when ``task_authorized`` is given as a
  sequence, a tool outside it is deterministically rejected with
  :exc:`ToolNotAuthorizedError` (code TOOL_NOT_AUTHORIZED) plus a guard
  record; nothing executes and no side effect happens.
- every call goes through ``toolguard.evaluate`` (read-only G2/G5 usage;
  resolved lazily so this lane never owns ``toolguard``).
- installer auto-install stays disabled: unknown tools raise
  :exc:`ToolNotFoundError`, they are never fetched or installed.
- real child pids are reported to the watcher.
- tool output is DATA, never instructions.
"""

from __future__ import annotations

import collections.abc
import importlib
import sys
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .registry import (
    ToolNotAuthorizedError,
    ToolRegistry,
    _checked_argv,
    _checked_auth,
    _shaped_result,
)
from .types import ActionClass, Argv, AuthMapping, ToolResult

if TYPE_CHECKING:  # read-only contract usage; never a runtime import here
    from agent_si.toolguard import evaluate  # noqa: F401


_REAL_REGISTRY = ToolRegistry()


def get_registry() -> ToolRegistry:
    """Return the process-wide tool registry."""
    return _REAL_REGISTRY


def _resolve_evaluate():
    """Return ``toolguard.evaluate`` without a static import of the lane."""
    module = sys.modules.get("agent_si.toolguard")
    func = getattr(module, "evaluate", None) if module is not None else None
    if callable(func):
        return func
    guard = importlib.import_module("agent_si.toolguard.guard")
    return guard.evaluate


ESCALATED: str = "ESCALATED"
"""Frozen run state after retry/correction budget exhaustion: parked."""


_DEFAULT_RETRY_BUDGET: int = 3
"""Denied retries tolerated per run before the run parks as ESCALATED."""


@dataclass(frozen=True)
class EscalationCard:
    """In-product escalation card for a run parked as ESCALATED.

    Carries the run id, the frozen state, the parking reason, the
    evidence refs and the resume/discard actions; JSON-serializable via
    :meth:`to_dict` so the same card serves the chat loop and the run
    view with no silent park.
    """

    run_id: str
    state: str = ESCALATED
    reason: str = ""
    evidence_refs: tuple[str, ...] = ()
    resume_action: str = ""
    discard_action: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return the card as plain JSON-serializable values."""
        return {
            "run_id": self.run_id,
            "state": self.state,
            "reason": self.reason,
            "evidence_refs": list(self.evidence_refs),
            "resume_action": self.resume_action,
            "discard_action": self.discard_action,
        }


class EscalationParkedError(PermissionError):
    """Refusal carrying the escalation card of a parked run.

    Subclasses :exc:`PermissionError` so parked refusals keep the
    existing denial handling; ``card`` is the stored
    :class:`EscalationCard` for the run.
    """

    def __init__(self, card: EscalationCard) -> None:
        """Carry the stored escalation card on the refusal."""
        super().__init__(
            "run %r parked as ESCALATED: %s" % (card.run_id, card.reason)
        )
        self.card = card


_ESCALATION_LOCK = threading.Lock()
_ESCALATION_CARDS: dict[str, EscalationCard] = {}
_DENIAL_COUNTS: dict[str, int] = {}


def get_escalation(run_id: str) -> EscalationCard | None:
    """Return the stored escalation card for ``run_id``, if parked."""
    with _ESCALATION_LOCK:
        return _ESCALATION_CARDS.get(run_id)


def _resolve_run_id(
    auth_dict: dict[str, Any], run_id: str | None
) -> str | None:
    """Return the explicit run id, else the ``run_id`` auth claim."""
    if isinstance(run_id, str) and run_id:
        return run_id
    candidate = auth_dict.get("run_id")
    if isinstance(candidate, str) and candidate:
        return candidate
    return None


def _checked_task_authorized(task_authorized: bool | None) -> None:
    """Refuse when the explicit task-authorized signal denies.

    ``None`` carries no signal and falls through to the toolguard
    ladder; ``True`` passes; ``False`` refuses with
    :exc:`PermissionError` before any parked or guard work. Any other
    value refuses closed with :exc:`TypeError`.
    """
    if task_authorized is None or task_authorized is True:
        return
    if task_authorized is False:
        raise PermissionError("task_authorized denied: task not authorized")
    raise TypeError("task_authorized must be True, False or None")


def _resolve_parked_card(
    parked: EscalationCard | collections.abc.Mapping[str, EscalationCard],
    run_id: str | None,
) -> EscalationCard | None:
    """Return the explicit parked card applying to ``run_id``.

    ``parked`` is either a stored :class:`EscalationCard` for this run
    or a read-only table of run id to card. A card naming another run
    refuses with :exc:`ValueError`; a table with no card for
    ``run_id`` (or no ``run_id`` at all) yields None so the stored
    escalation lookup still applies. Anything else refuses with
    :exc:`TypeError`.
    """
    if isinstance(parked, EscalationCard):
        if run_id is not None and parked.run_id != run_id:
            raise ValueError(
                f"parked card run {parked.run_id!r} does not match run {run_id!r}"
            )
        return parked
    if isinstance(parked, collections.abc.Mapping):
        if run_id is None:
            return None
        card = parked.get(run_id)
        if card is None:
            return None
        if not isinstance(card, EscalationCard):
            raise TypeError(
                "parked table must map run ids to EscalationCard"
            )
        return card
    raise TypeError(
        "parked must be an EscalationCard or a mapping of run ids to cards"
    )


def _note_denial(
    run_id: str,
    tool: str,
    reason: str,
    verdict: dict[str, Any],
    retry_budget: int | None,
) -> EscalationCard | None:
    """Count one denial; park the run with a card past its budget.

    Returns the stored card when this denial exhausts the retry
    budget, else None. The parked card keeps the denial reason and
    the toolguard evidence ref plus resume/discard actions.
    """
    del tool
    budget = _DEFAULT_RETRY_BUDGET if retry_budget is None else retry_budget
    evidence = verdict.get("evidence_ref")
    refs = (str(evidence),) if evidence else ()
    with _ESCALATION_LOCK:
        count = _DENIAL_COUNTS.get(run_id, 0) + 1
        _DENIAL_COUNTS[run_id] = count
        if count <= budget:
            return None
        card = EscalationCard(
            run_id=run_id,
            state=ESCALATED,
            reason=reason,
            evidence_refs=refs,
            resume_action="resume:%s" % (run_id,),
            discard_action="discard:%s" % (run_id,),
        )
        _ESCALATION_CARDS[run_id] = card
        return card


def guarded_dispatch(
    argv: Argv,
    action_class: ActionClass,
    auth: AuthMapping,
    *,
    tool: str,
    registry: ToolRegistry | None = None,
    task_authorized: bool | collections.abc.Sequence[str] | None = None,
    guard_store: list | None = None,
    run_id: str | None = None,
    retry_budget: int | None = None,
    parked: EscalationCard | collections.abc.Mapping[str, EscalationCard] | None = None,
) -> ToolResult:
    """Evaluate ``toolguard.evaluate`` then run the ``tool`` route.

    ``argv`` must be a list of words (G1); ``action_class`` is one of
    R0-R3; ``auth`` carries identity, scopes and approvals. Deny
    order: an explicit ``task_authorized`` denial refuses first (a
    ``False`` signal, or a sequence not listing ``tool``, which raises
    :exc:`ToolNotAuthorizedError` and files to ``guard_store`` when
    given), then the parked-run refusal (explicit ``parked`` card or
    table, else the stored card for ``run_id``), then
    ``toolguard.evaluate``.
    A parked run raises :exc:`EscalationParkedError` with its card and
    performs no further guard work. Denials count against the run's
    retry budget (``run_id`` kwarg or ``run_id`` auth claim,
    ``retry_budget`` overrides the default of 3); the denial that
    exhausts the budget parks the run as ESCALATED.
    """
    argv_list = _checked_argv(argv)
    if task_authorized is None or task_authorized is True:
        pass
    elif task_authorized is False:
        raise PermissionError("task_authorized denied: task not authorized")
    elif tool not in list(task_authorized):
        reason = "tool %r is outside the task-authorized list" % (tool,)
        if guard_store is not None:
            from .guard_records import TOOL_NOT_AUTHORIZED
            from .guard_records import record_guard_decision as _record

            _record(
                guard_store,
                tool=tool,
                decision="deny",
                reason=reason,
                evidence_ref="toolguard:deny:task-list:%s" % (tool[:40],),
                error_code=TOOL_NOT_AUTHORIZED,
            )
        raise ToolNotAuthorizedError("TOOL_NOT_AUTHORIZED: %s" % (reason,))
    if isinstance(auth, collections.abc.Mapping):
        auth_dict = dict(auth)
    else:
        auth_dict = {}
    resolved_run = _resolve_run_id(auth_dict, run_id)
    if parked is not None:
        explicit = _resolve_parked_card(parked, resolved_run)
        if explicit is not None:
            raise EscalationParkedError(explicit)
    if resolved_run is not None:
        stored = get_escalation(resolved_run)
        if stored is not None:
            raise EscalationParkedError(stored)
    evaluate = _resolve_evaluate()
    verdict = evaluate(argv_list, action_class, auth_dict)
    if isinstance(verdict, dict) and verdict.get("decision") == "deny":
        reason = str(verdict.get("reason"))
        if resolved_run is not None:
            card = _note_denial(
                resolved_run, tool, reason, verdict, retry_budget
            )
            if card is not None:
                raise EscalationParkedError(card)
        raise PermissionError(
            "toolguard denied: %s" % (reason,)
        )
    _checked_auth(auth)
    target = registry if registry is not None else get_registry()
    return target.dispatch(tool, argv_list, action_class, auth)
