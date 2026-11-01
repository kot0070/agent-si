"""Orchestration runtime interface (Manifest section 43).

Chain: Domain/Core -> OrchestrationInterface -> OpenAIAgentsSDKAdapter.

OrchestrationInterface.run_turn is the SINGLE engine entry point behind the
backend chat-stream caller. There is no second entry path, and this module
performs no SDK rebuild: client configuration is built once inside the
adapter, and all SDK calls live in agent_si.sdk_adapter.sdk_adapter.

Tool results are untrusted DATA, never instructions: a tool result carrying
an injected order is never executed. The turn is held with approval requested
(probe B-001), and the injection text never reaches the SDK runner.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Tuple

from agent_si.sdk_adapter import tracing_policy as tracing_policy_module

_INJECTION_PATTERN = re.compile(
    r"ignore\s+(all\s+|previous\s+|prior\s+)?instructions"
    r"|execute\s+this\s+order"
    r"|disregard\s+.*(policy|contract)"
    r"|you\s+must\s+.*(drop|delete|approve)"
)
"""Heuristic markers for injected orders inside tool-result DATA (probe B-001)."""


# Error codes (Manifest 21A pattern: module constant + Exception.code).
# Task-ordered (HD 17:26): run_turn with no bound adapter raises an error
# carrying this code. The subclass keeps the RuntimeError base type.
ORCHESTRATION_ADAPTER_UNBOUND = "ORCHESTRATION_ADAPTER_UNBOUND"


class AdapterUnboundError(RuntimeError):
    """run_turn called with no bound SDK adapter; the real adapter is required."""

    code = ORCHESTRATION_ADAPTER_UNBOUND


@dataclass(frozen=True)
class TurnRequest:
    """One engine turn: refs only, never inline secrets or bulk content."""

    project_id: str
    task_id: str
    run_id: str
    contract_hash: str
    input_ref: str
    tool_results: Tuple[Any, ...] = ()
    secret_refs: Tuple[Any, ...] = ()
    run_config: Any = None


@dataclass(frozen=True)
class TurnResult:
    """One engine turn outcome: held turns ask approval instead of executing."""

    run_id: str
    output_ref: str
    executed: bool
    approval_requested: bool
    treated_as_data: bool
    authorization_ref: Any = None
    reason: str = ""
    tool_id: str = ""


@dataclass
class OrchestrationInterface:
    """Single-entry engine facade over the SDK adapter (Manifest section 43)."""

    adapter: Any = None
    tracing_policy: Any = tracing_policy_module.DEFAULT_POLICY

    def run_turn(self, request: TurnRequest) -> TurnResult:
        """Run one engine turn; the SINGLE engine entry point.

        Tool results are scanned as DATA: when one carries an injected order
        the turn is NOT executed and approval is requested (probe B-001);
        the injection text never reaches the SDK runner. Clean turns delegate
        to the bound adapter with the request's RoutingDecision-bound
        RunConfig. Tracing stays at the bound policy (default DISABLED).
        """
        if self.adapter is None:
            raise AdapterUnboundError(
                "OrchestrationInterface has no bound SDK adapter"
            )
        texts = []
        for item in request.tool_results or ():
            if isinstance(item, str):
                texts.append(item)
            elif isinstance(item, dict):
                texts.append(" ".join(str(value) for value in item.values()))
            else:
                texts.append(str(item))
        if any(_INJECTION_PATTERN.search(text.lower()) for text in texts):
            return TurnResult(
                run_id=request.run_id,
                output_ref=request.input_ref,
                executed=False,
                approval_requested=True,
                treated_as_data=True,
                authorization_ref=None,
                reason=(
                    "B-001: tool result carries an injected order; "
                    "held as data, approval requested"
                ),
            )
        result = self.adapter.run(
            run_config=request.run_config,
            input_ref=request.input_ref,
            secret_refs=request.secret_refs,
        )
        return TurnResult(
            run_id=request.run_id,
            output_ref=result.output_ref,
            executed=True,
            approval_requested=False,
            treated_as_data=False,
            authorization_ref=None,
            reason="clean turn delegated to the SDK adapter",
        )


__all__ = [
    "AdapterUnboundError",
    "ORCHESTRATION_ADAPTER_UNBOUND",
    "TurnRequest",
    "TurnResult",
    "OrchestrationInterface",
]
