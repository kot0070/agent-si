"""OpenAI Agents SDK runner (Manifest sections 14B, 43).

Single-turn execution behind the SDK adapter: the adapter computes
transport and secret refs, this module runs the attempt loop and returns
an SdkTurnOutcome. Refs only cross this boundary, never inline secrets.
"""

from __future__ import annotations

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
) -> SdkTurnOutcome:
    """Run one SDK turn; return the outcome with the attempts made.

    Provider, model and the retry bound come structurally off run_config;
    this function never rebuilds SDK client configuration. Each attempt
    calls sdk_call with one mapping; a provided events list gains one
    record per attempt. A truthy ok outcome stops the loop; attempts past
    turn_budget stop it as failed; no other stop condition exists.
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
        # Only two exits: truthy ok above, or attempts past the budget here; client retries stay refused (sdk_adapter.py:240).
        if attempt > turn_budget:
            return SdkTurnOutcome(
                ok=False, output_text="", error=_error_text(outcome), attempts_made=attempt
            )
