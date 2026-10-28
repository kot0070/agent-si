"""K13 runner lane: SDK runner module RED-to-GREEN (M-RUNNER, CODER-1-Sprint).

Covers the new agent_si.sdk_adapter.runner module plus the adapter.run
delegation wiring. K04 is touched only through the existing
RoutingDecisionBinding shape; K02 only through OrchestrationInterface.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import pytest

from iface.frozen_manifest import manifest
from agent_si.sdk_adapter import sdk_adapter
from agent_si.sdk_adapter.runner import (
    SDK_RUNNER_UNAVAILABLE,
    SdkRunnerUnavailableError,
    SdkTurnOutcome,
    run_sdk_turn,
)
from agent_si.sdk_adapter.sdk_adapter import (
    OpenAIAgentsSDKAdapter,
    RoutingDecisionBinding,
    RunConfig,
    RunnerUnboundError,
    SdkClientConfig,
    SdkRunResult,
    SecretRef,
)
from agent_si.sdk_adapter.orchestration_interface import (
    OrchestrationInterface,
    TurnRequest,
)


def _decision():
    return RoutingDecisionBinding(
        decision_id="dec-1",
        project_id="P1",
        task_id="T1",
        run_id="run-1",
        routing_snapshot_id="snap-1",
        selected_provider="meta",
        selected_model="meta/muse-spark-1.3-contributor",
        route="CLOUD",
        strategy="single",
        reason="runner-lane",
    )


def _run_config(executor_attempt_max=2):
    decision = _decision()
    return RunConfig(
        decision_id=decision.decision_id,
        project_id=decision.project_id,
        task_id=decision.task_id,
        run_id=decision.run_id,
        selected_provider=decision.selected_provider,
        selected_model=decision.selected_model,
        route=decision.route,
        strategy=decision.strategy,
        max_runner_retries=int(executor_attempt_max),
    )


def _stub_sdk_call(calls, *, fail_first=0):
    def _call(call):
        calls.append(dict(call))
        if len(calls) <= fail_first:
            return {"ok": False, "error": "boom-%d" % len(calls)}
        return {"ok": True, "output_text": "echo:%s" % call["input_ref"]}

    return _call


def _wired_adapter(calls, *, fail_first=0, executor_attempt_max=2):
    adapter = OpenAIAgentsSDKAdapter(
        client_config=SdkClientConfig(),
        runner=_stub_sdk_call(calls, fail_first=fail_first),
    )
    return adapter, _run_config(executor_attempt_max)


def test_turn_budget_two_retries_then_success():
    calls = []
    events = []
    outcome = run_sdk_turn(
        run_config=_run_config(2),
        input_ref="in-1",
        secret_ids=(),
        transport="chat_completions",
        turn_budget=2,
        events=events,
        sdk_call=_stub_sdk_call(calls, fail_first=2),
    )
    assert isinstance(outcome, SdkTurnOutcome)
    assert outcome.ok is True
    assert outcome.output_text == "echo:in-1"
    assert outcome.attempts_made == 3
    assert [record["attempt"] for record in events] == [1, 2, 3]
    assert all(
        set(record) == {"attempt", "provider", "model", "transport", "ok", "error"}
        for record in events
    )
    assert [record["ok"] for record in events] == [False, False, True]


def test_turn_budget_zero_single_attempt():
    calls = []
    outcome = run_sdk_turn(
        run_config=_run_config(0),
        input_ref="in-9",
        transport="chat_completions",
        turn_budget=0,
        sdk_call=_stub_sdk_call(calls, fail_first=99),
    )
    assert outcome.ok is False
    assert outcome.attempts_made == 1
    assert outcome.error == "boom-1"
    assert len(calls) == 1


def test_payload_keys_unchanged():
    calls = []
    config = _run_config(2)
    outcome = run_sdk_turn(
        run_config=config,
        input_ref="in-2",
        secret_ids=("s-1",),
        transport="chat_completions",
        turn_budget=2,
        sdk_call=_stub_sdk_call(calls),
    )
    assert outcome.ok is True
    assert len(calls) == 1
    assert set(calls[0]) == {
        "transport",
        "provider",
        "model",
        "input_ref",
        "secret_ids",
        "attempt",
    }
    assert calls[0]["provider"] == "meta"
    assert calls[0]["model"] == "meta/muse-spark-1.3-contributor"
    assert calls[0]["transport"] == "chat_completions"
    assert calls[0]["input_ref"] == "in-2"
    assert calls[0]["secret_ids"] == ("s-1",)
    assert calls[0]["attempt"] == 1


def test_adapter_run_delegates_to_runner():
    calls = []
    adapter, config = _wired_adapter(calls, fail_first=1, executor_attempt_max=2)
    result = adapter.run(
        run_config=config,
        input_ref="in-echo",
        secret_refs=(SecretRef(secret_id="s-1"),),
    )
    assert isinstance(result, SdkRunResult)
    assert result.status == manifest.ExecutionAttemptStatus.SUCCEEDED
    assert result.output_ref == "artifact:run/run-1/output"
    assert result.provider == "meta"
    assert result.model == "meta/muse-spark-1.3-contributor"
    assert calls[0]["secret_ids"] == ("s-1",)
    assert adapter.calls_made == len(calls) == 2


def test_unwired_still_raises():
    adapter = OpenAIAgentsSDKAdapter()
    config = adapter.build_run_config(_decision(), executor_attempt_max=1)
    with pytest.raises(RunnerUnboundError) as excinfo:
        adapter.run(run_config=config, input_ref="in-unwired")
    assert excinfo.value.code == sdk_adapter.SDK_RUNNER_UNBOUND
    assert isinstance(excinfo.value, RuntimeError)


def test_run_turn_clean_delegates():
    calls = []
    adapter, config = _wired_adapter(calls)
    interface = OrchestrationInterface(adapter=adapter)
    request = TurnRequest(
        project_id="P1",
        task_id="T1",
        run_id="run-1",
        contract_hash="h1",
        input_ref="in-clean",
        tool_results=("lookup result: the balance is 12 units.",),
        secret_refs=(),
        run_config=config,
    )
    result = interface.run_turn(request)
    assert result.executed is True
    assert result.approval_requested is False
    assert result.output_ref == "artifact:run/run-1/output"
    assert adapter.calls_made == 1


def test_no_agents_package_raises_unavailable():
    try:
        import agents as _probe

        has_agent = hasattr(_probe, "Agent")
    except ImportError:
        has_agent = False
    if has_agent:
        pytest.skip("agents package is importable; absence path not taken")
    with pytest.raises(SdkRunnerUnavailableError) as excinfo:
        run_sdk_turn(
            run_config=_run_config(0),
            input_ref="in-absent",
            transport="chat_completions",
            turn_budget=0,
            sdk_call=None,
        )
    assert excinfo.value.code == SDK_RUNNER_UNAVAILABLE
    assert isinstance(excinfo.value, RuntimeError)
