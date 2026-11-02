"""OpenAI Agents SDK runner (Manifest sections 14B, 43).

Single-turn execution behind the SDK adapter: the adapter computes
transport and secret refs, this module runs the attempt loop and returns
an SdkTurnOutcome. Refs only cross this boundary, never inline secrets.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

try:  # Guarded local import mirrors sdk_adapter.py:34-42; this module never imports sdk_adapter, so no cycle is possible (lane R1).
    import agents as _agents_sdk

    if not hasattr(_agents_sdk, "Agent"):
        _agents_sdk = None
except ImportError:
    _agents_sdk = None

SDK_RUNNER_UNAVAILABLE = "SDK_RUNNER_UNAVAILABLE"


class SdkRunnerUnavailableError(RuntimeError):
    """run_sdk_turn called with no sdk_call and no importable SDK."""

    code = SDK_RUNNER_UNAVAILABLE


# Turn result plus the attempt count; the composition layout names this runner module (0C_ARCHITECTURE.md:18).
@dataclass(frozen=True)
class SdkTurnOutcome:
    """One SDK turn outcome: success flag, output text, error text, attempts made."""

    ok: bool
    output_text: str
    error: str
    attempts_made: int


def _error_text(outcome: Mapping[str, Any]) -> str:
    raw = outcome.get("error", "sdk_run_failed")
    return raw if isinstance(raw, str) else str(raw)


def _output_text(outcome: Mapping[str, Any]) -> str:
    raw = outcome.get("output_text", "")
    return raw if isinstance(raw, str) else str(raw)


#: Hard cap on total attempts per turn (429 must never burn the budget
#: at once: backoff plus jitter separates the tries).
MAX_ATTEMPTS = 3

#: Retry-After is honoured up to this many seconds (never longer).
MAX_RETRY_AFTER_S = 30.0

#: Base backoff between attempts (doubled per attempt, plus jitter).
BACKOFF_BASE_S = 0.5


def _retry_after_s(outcome: Mapping[str, Any]) -> float | None:
    """Served Retry-After delay in seconds, or None when absent/unusable."""
    for key in ("retry_after", "retry_after_s", "retry-after"):
        try:
            raw = outcome.get(key)
        except Exception:
            continue
        if raw is None:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if value >= 0:
            return value
    return None


def _backoff_delay(attempt: int, retry_after: float | None,
                   jitter: Callable[[int], float] | None) -> float:
    """Delay before the next attempt: served Retry-After wins (capped).

    Otherwise exponential backoff off the attempt number plus jitter,
    capped at MAX_RETRY_AFTER_S. Jitter defaults to a uniform draw up
    to the backoff value; tests inject their own jitter (or zero).
    """
    if retry_after is not None:
        return min(MAX_RETRY_AFTER_S, max(0.0, retry_after))
    backoff = min(MAX_RETRY_AFTER_S,
                  BACKOFF_BASE_S * (2.0 ** max(0, int(attempt) - 1)))
    if jitter is not None:
        try:
            extra = float(jitter(int(attempt)))
        except Exception:
            extra = 0.0
    else:
        extra = random.uniform(0.0, backoff)
    return min(MAX_RETRY_AFTER_S, backoff + max(0.0, extra))


def _wait(delay: float, stop_event: Any,
          sleep: Callable[[float], None] | None) -> bool:
    """Wait out one backoff delay; return True when a stop was seen.

    A stop event waits on the event itself (Stop all never waits out
    a sleep); otherwise the injected sleep runs (tests), else
    time.sleep. Non-positive delays never sleep.
    """
    if delay <= 0:
        if stop_event is not None:
            try:
                return bool(stop_event.is_set())
            except Exception:
                return False
        return False
    if stop_event is not None:
        wait = getattr(stop_event, "wait", None)
        if callable(wait):
            try:
                wait(float(delay))
            except Exception:
                pass
            try:
                return bool(stop_event.is_set())
            except Exception:
                return False
    if sleep is not None:
        sleep(float(delay))
    else:
        time.sleep(float(delay))
    if stop_event is not None:
        try:
            return bool(stop_event.is_set())
        except Exception:
            return False
    return False


# Keyword-only entry; mirrors the adapter run entry kept signature-identical (sdk_adapter.py:267).
def run_sdk_turn(
    *,
    run_config: Any,
    input_ref: str,
    secret_ids: Tuple[str, ...] = (),
    transport: str,
    turn_budget: int,
    events: Optional[List[Dict[str, Any]]] = None,
    sdk_call: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    stop_event: Any = None,
    sleep: Callable[[float], None] | None = None,
    jitter: Callable[[int], float] | None = None,
    max_attempts: int = MAX_ATTEMPTS,
) -> SdkTurnOutcome:
    """Run one SDK turn; return the outcome with the attempts made.

    Provider, model and the retry bound come structurally off run_config;
    this function never rebuilds SDK client configuration. Each attempt
    calls sdk_call with one mapping; a provided events list gains one
    record per attempt. A truthy ok outcome stops the loop; attempts past
    the bound stop it as failed; no other stop condition exists. Failed
    attempts back off (served Retry-After up to 30 s, else exponential
    backoff plus jitter, at most 3 attempts total); a stop seen between
    attempts ends the turn as failed without another call. Refs only
    cross this boundary; guard logic stays outside this module
    (0C_ARCHITECTURE.md:92).
    """
    # Structural read off run_config; the client config stays pinned at max_retries 0 and is never rebuilt (sdk_adapter.py:118).
    provider = run_config.selected_provider
    model = run_config.selected_model
    secrets = tuple(secret_ids or ())
    if sdk_call is None:
        # Built-in single attempt through the guarded SDK import pinned for this lane (pyproject.toml:11).
        if _agents_sdk is None:
            raise SdkRunnerUnavailableError(
                "OpenAI Agents SDK is not importable; pass sdk_call=... explicitly"
            )
        agent = _agents_sdk.Agent(name="agent-si-turn", model=model)
        sdk_result = _agents_sdk.Runner.run_sync(agent, input_ref)
        text = getattr(sdk_result, "final_output", "")
        output_text = text if isinstance(text, str) else str(text)
        if events is not None:
            events.append(
                {
                    "attempt": 1,
                    "provider": provider,
                    "model": model,
                    "transport": transport,
                    "ok": True,
                    "error": "",
                }
            )
        return SdkTurnOutcome(ok=True, output_text=output_text, error="", attempts_made=1)
    # Attempt loop; the retry bound arrives via turn_budget from the RoutingDecision-bound RunConfig (sdk_adapter.py:157).
    attempt = 0
    while True:
        attempt += 1
        # Refs only cross this boundary; guard logic stays outside this module (0C_ARCHITECTURE.md:92).
        outcome = sdk_call(
            {
                "transport": transport,
                "provider": provider,
                "model": model,
                "input_ref": input_ref,
                "secret_ids": secrets,
                "attempt": attempt,
            }
        )
        succeeded = bool(outcome.get("ok"))
        if events is not None:
            events.append(
                {
                    "attempt": attempt,
                    "provider": provider,
                    "model": model,
                    "transport": transport,
                    "ok": succeeded,
                    "error": "" if succeeded else _error_text(outcome),
                }
            )
        if succeeded:
            return SdkTurnOutcome(
                ok=True,
                output_text=_output_text(outcome),
                error="",
                attempts_made=attempt,
            )
        # Attempts past the bound stop as failed; client retries stay
        # refused (sdk_adapter.py:240). The bound is the routing retry
        # budget capped at MAX_ATTEMPTS: a 429 never burns every try
        # at once, and the same provider+model rides every attempt.
        try:
            bound = int(turn_budget) + 1
        except (TypeError, ValueError):
            bound = 1
        try:
            cap = int(max_attempts)
        except (TypeError, ValueError):
            cap = MAX_ATTEMPTS
        bound = max(1, min(bound, max(1, cap), MAX_ATTEMPTS))
        if attempt >= bound:
            return SdkTurnOutcome(
                ok=False, output_text="", error=_error_text(outcome), attempts_made=attempt
            )
        # Back off before the next attempt: served Retry-After (capped
        # at 30 s) wins, else exponential backoff plus jitter. A stop
        # seen across the wait ends the turn without another call.
        delay = _backoff_delay(attempt, _retry_after_s(outcome), jitter)
        if _wait(delay, stop_event, sleep):
            return SdkTurnOutcome(
                ok=False, output_text="", error="stopped",
                attempts_made=attempt,
            )
