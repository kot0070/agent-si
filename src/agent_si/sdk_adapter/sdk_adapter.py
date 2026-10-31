"""OpenAI Agents SDK adapter (Manifest sections 6, 14B, 20A, 43).

SDK calls live ONLY in this module. The orchestration interface never calls
the SDK directly and never rebuilds SDK client configuration.

Frozen rules honored here:

- Non-OpenAI providers always use the Chat Completions endpoint; no other
  conversational endpoint is ever assumed.
- Provider clients use max_retries 0 (no hidden recovery); the constructor
  refuses any other value. Runner retries come ONLY from the
  RoutingDecision-bound RunConfig.
- Every result is posted as SdkRunResult carrying output_ref.
- Agent Builder imports are untrusted input until revalidated against an
  expected content hash; unrevalidated workflows are never executed.
- SecretRefs only: secret_refs entries must be SecretRef records; inline
  values are never accepted and never touch output refs.

Module default: USE_SDK_UNLESS_DOCUMENTED_CRITICAL_BLOCKER. The SDK is used
unless a documented critical blocker (evidence + decision record +
independent audit, per section 43) selects a replacement.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable, Dict, Tuple

# Wiring-only import: the attempt loop lives in runner.py; the public surface below stays unchanged (0C_ARCHITECTURE.md:139).
from agent_si.sdk_adapter.runner import run_sdk_turn

try:
    from iface.frozen_manifest import manifest
except ImportError:  # alternate layout: the iface/ directory itself on sys.path
    from frozen_manifest import manifest

try:  # real SDK when present; the adapter never needs it at import time
    import agents as _agents_sdk

    if not hasattr(_agents_sdk, "Agent"):
        _agents_sdk = None
except ImportError:
    _agents_sdk = None

SDK_AVAILABLE = _agents_sdk is not None
"""True when the real SDK package is importable; the fallback echo runner otherwise."""

USE_SDK_UNLESS_DOCUMENTED_CRITICAL_BLOCKER = True
"""Module default (Manifest section 43): stay on the SDK unless a documented
critical blocker (evidence + decision record + independent audit) says otherwise."""

CHAT_COMPLETIONS_TRANSPORT = "chat_completions"
SDK_DEFAULT_TRANSPORT = "sdk_default"

_OPENAI_PROVIDER_NAMES = frozenset({"openai"})


def transport_for_provider(provider: str) -> str:
    """Return the SDK transport for *provider* (Manifest section 43).

    OpenAI providers use the SDK default path; every other provider uses the
    Chat Completions endpoint. No other conversational endpoint is assumed.
    """
    if str(provider).strip().lower() in _OPENAI_PROVIDER_NAMES:
        return SDK_DEFAULT_TRANSPORT
    return CHAT_COMPLETIONS_TRANSPORT


# Error codes (Manifest 21A pattern: module constant + Exception.code).
# Task-ordered (HD 17:26): every error condition in this module raises an
# error carrying one of these codes. Subclasses keep the builtin base type
# so existing ValueError/TypeError pins still hold.
SDK_CLIENT_MAX_RETRIES_NONZERO = "SDK_CLIENT_MAX_RETRIES_NONZERO"
SDK_RUN_CONFIG_REQUIRED = "SDK_RUN_CONFIG_REQUIRED"
SDK_SECRET_REFS_MUST_BE_RECORDS = "SDK_SECRET_REFS_MUST_BE_RECORDS"
BUILDER_WORKFLOW_HASH_MISMATCH = "BUILDER_WORKFLOW_HASH_MISMATCH"
BUILDER_WORKFLOW_NOT_REVALIDATED = "BUILDER_WORKFLOW_NOT_REVALIDATED"
L3_PROVIDER_MUST_DIFFER = "L3_PROVIDER_MUST_DIFFER"
L3_KEY_REF_REQUIRED = "L3_KEY_REF_REQUIRED"


class SdkClientConfigError(ValueError):
    """Provider client built with max_retries != 0 (Manifest 14B)."""

    code = SDK_CLIENT_MAX_RETRIES_NONZERO


class RunConfigRequiredError(ValueError):
    """run() called without its RoutingDecision-bound RunConfig (14B)."""

    code = SDK_RUN_CONFIG_REQUIRED


class SecretRefTypeError(TypeError):
    """secret_refs entry is not a SecretRef record (Manifest 20A)."""

    code = SDK_SECRET_REFS_MUST_BE_RECORDS


class BuilderWorkflowHashMismatchError(ValueError):
    """Agent Builder workflow hash mismatch; still untrusted (section 6)."""

    code = BUILDER_WORKFLOW_HASH_MISMATCH


@dataclass(frozen=True)
class SecretRef:
    """Manifest section 20A SecretRef. Agents receive refs, never raw values."""

    secret_id: str
    provider_id: str = ""
    type: str = ""
    scope: str = ""
    source: str = ""
    created_at: str = ""
    last_rotated_at: str = ""


@dataclass(frozen=True)
class SdkClientConfig:
    """Provider client configuration. max_retries stays 0 (section 14B)."""

    max_retries: int = 0


@dataclass(frozen=True)
class RoutingDecisionBinding:
    """RoutingDecision fields this adapter consumes (Manifest section 28)."""

    decision_id: str
    project_id: str
    task_id: str
    run_id: str
    routing_snapshot_id: str = ""
    selected_provider: str = ""
    selected_model: str = ""
    route: str = ""
    strategy: str = ""
    reason: str = ""


@dataclass(frozen=True)
class RunConfig:
    """Runner configuration bound to exactly one RoutingDecision (section 14B).

    Runner retries come ONLY from max_runner_retries, which the caller binds
    from the active RetryPolicy budget (executor_attempt_max) for the bound
    decision. The adapter never invents a retry budget.
    """

    decision_id: str
    project_id: str
    task_id: str
    run_id: str
    selected_provider: str
    selected_model: str
    route: str
    strategy: str
    max_runner_retries: int

    @classmethod
    def from_routing_decision(
        cls, decision: RoutingDecisionBinding, *, executor_attempt_max: int
    ) -> "RunConfig":
        """Bind a RoutingDecision plus its RetryPolicy budget (section 14B)."""
        return cls(
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


@dataclass(frozen=True)
class SdkRunResult:
    """Adapter result shape (Manifest ports section). Always carries output_ref."""

    run_id: str
    output_ref: str
    provider: str = ""
    model: str = ""
    status: Any = manifest.ExecutionAttemptStatus.SUCCEEDED
    error_ref: str = ""


@dataclass(frozen=True)
class AgentBuilderWorkflow:
    """An imported Agent Builder workflow: untrusted input until revalidated."""

    workflow_ref: str
    content_hash: str
    revalidated: bool = False


class WorkflowNotRevalidatedError(Exception):
    """An Agent Builder workflow was executed before revalidation (section 6)."""

    code = BUILDER_WORKFLOW_NOT_REVALIDATED


class L3ProviderMustDifferError(ValueError):
    """L3 audit bound to the same provider as the audited decision."""

    code = L3_PROVIDER_MUST_DIFFER


class L3KeyRefRequiredError(TypeError):
    """L3 audit bound without its own SecretRef record."""

    code = L3_KEY_REF_REQUIRED


@dataclass(frozen=True)
class L3AuditBinding:
    """Independent-audit binding (MVP_ACCEPT-168): the L3 auditor runs on
    a separate cloud provider with its own key ref, never on the
    decided provider and never on an inline secret value."""

    project_id: str
    task_id: str
    run_id: str
    decision_id: str
    selected_provider: str
    selected_model: str
    l3_provider: str
    l3_model: str
    key_ref: SecretRef


def bind_l3_audit(decision: RoutingDecisionBinding, *,
                  l3_provider: str, l3_model: str,
                  key_ref: SecretRef) -> L3AuditBinding:
    """Bind an L3 independent audit to a separate provider path (168).

    The L3 provider must differ from the decided provider and the key
    must be a SecretRef record (refs only, never inline values).
    """
    if not isinstance(key_ref, SecretRef):
        raise L3KeyRefRequiredError(
            "L3 audit needs its own SecretRef record; inline values "
            "and missing refs are never accepted [L3_KEY_REF_REQUIRED]")
    if not l3_provider or not l3_model:
        raise L3KeyRefRequiredError(
            "L3 audit needs an l3_provider and l3_model "
            "[L3_KEY_REF_REQUIRED]")
    if str(l3_provider).strip().lower() == \
            str(decision.selected_provider).strip().lower():
        raise L3ProviderMustDifferError(
            "L3 audit must run on a separate provider, not %r "
            "[L3_PROVIDER_MUST_DIFFER]" % (decision.selected_provider,))
    return L3AuditBinding(
        project_id=decision.project_id, task_id=decision.task_id,
        run_id=decision.run_id, decision_id=decision.decision_id,
        selected_provider=decision.selected_provider,
        selected_model=decision.selected_model,
        l3_provider=str(l3_provider), l3_model=str(l3_model),
        key_ref=key_ref)


def revalidate_agent_builder_workflow(
    workflow: AgentBuilderWorkflow, *, expected_hash: str
) -> AgentBuilderWorkflow:
    """Return a revalidated copy iff the content hash matches (section 6).

    The input stays untouched; a mismatch raises instead of trusting.
    """
    if workflow.content_hash != expected_hash:
        raise BuilderWorkflowHashMismatchError(
            "Agent Builder workflow hash mismatch; still untrusted"
        )
    return replace(workflow, revalidated=True)


# BEGIN K13R1 (M-ECHO)
SDK_RUNNER_UNBOUND = "SDK_RUNNER_UNBOUND"


class RunnerUnboundError(RuntimeError):
    """run() called with no runner wired; pass runner=... explicitly."""

    code = SDK_RUNNER_UNBOUND


class OpenAIAgentsSDKAdapter:
    """The single SDK-call boundary (Manifest section 43).

    The client configuration is built ONCE here in __init__ and never rebuilt
    per call; per-call behavior varies only through the RoutingDecision-bound
    RunConfig passed to run().
    """

    def __init__(
        self,
        *,
        client_config: SdkClientConfig | None = None,
        runner: Callable[[Dict[str, Any]], Dict[str, Any]] | None = None,
    ) -> None:
        config = client_config if client_config is not None else SdkClientConfig()
        if config.max_retries != 0:
            raise SdkClientConfigError(
                "provider clients use max_retries 0 (Manifest 14B); got %r"
                % (config.max_retries,)
            )
        self._client_config = config
        self._runner = runner
        self._calls_made = 0

    @property
    def client_config(self) -> SdkClientConfig:
        """The single client configuration built at construction."""
        return self._client_config

    @property
    def calls_made(self) -> int:
        """SDK runner invocations so far (core accounting input, never a total)."""
        return self._calls_made

    def build_run_config(
        self, decision: RoutingDecisionBinding, *, executor_attempt_max: int
    ) -> RunConfig:
        """Bind a RoutingDecision plus its retry budget into a RunConfig."""
        return RunConfig.from_routing_decision(
            decision, executor_attempt_max=executor_attempt_max
        )

    def run(
        self,
        *,
        run_config: RunConfig,
        input_ref: str,
        secret_refs: Tuple[SecretRef, ...] = (),
    ) -> SdkRunResult:
        """Run one SDK invocation chain; return SdkRunResult with output_ref."""
        if run_config is None:
            raise RunConfigRequiredError(
                "run_config is required; retries bind to it (14B)"
            )
        for ref in secret_refs or ():
            if not isinstance(ref, SecretRef):
                raise SecretRefTypeError(
                    "secret_refs must be SecretRef records; "
                    "inline values are never accepted"
                )
        if self._runner is None:
            raise RunnerUnboundError(
                "OpenAIAgentsSDKAdapter has no runner wired; pass runner=..."
            )
# END K13R1 (M-ECHO)
        transport = transport_for_provider(run_config.selected_provider)
        secret_ids = tuple(ref.secret_id for ref in (secret_refs or ()))
        # The attempt loop lives in runner.py; K02 reaches this entry only
        # through the single-entry facade (orchestration_interface.py:72).
        outcome = run_sdk_turn(
            run_config=run_config,
            input_ref=input_ref,
            secret_ids=secret_ids,
            transport=transport,
            turn_budget=run_config.max_runner_retries,
            sdk_call=self._runner,
        )
        self._calls_made += outcome.attempts_made
        if outcome.ok:
            return SdkRunResult(
                run_id=run_config.run_id,
                output_ref="artifact:run/%s/output" % run_config.run_id,
                provider=run_config.selected_provider,
                model=run_config.selected_model,
                status=manifest.ExecutionAttemptStatus.SUCCEEDED,
            )
        return SdkRunResult(
            run_id=run_config.run_id,
            output_ref="artifact:run/%s/output" % run_config.run_id,
            provider=run_config.selected_provider,
            model=run_config.selected_model,
            status=manifest.ExecutionAttemptStatus.FAILED,
            error_ref=outcome.error,
        )

    def execute_builder_workflow(
        self,
        workflow: AgentBuilderWorkflow,
        *,
        run_config: RunConfig,
        input_ref: str,
        secret_refs: Tuple[SecretRef, ...] = (),
    ) -> SdkRunResult:
        """Execute an Agent Builder workflow only after revalidation (section 6)."""
        if not isinstance(workflow, AgentBuilderWorkflow) or not workflow.revalidated:
            raise WorkflowNotRevalidatedError(
                "Agent Builder import is untrusted until revalidated"
            )
        return self.run(
            run_config=run_config, input_ref=input_ref, secret_refs=secret_refs
        )

    def run_l3_audit(
        self,
        binding: L3AuditBinding,
        *,
        input_ref: str,
        secret_ref: SecretRef,
        runner: Callable[[Dict[str, Any]], Dict[str, Any]] | None = None,
    ) -> SdkRunResult:
        """Run one L3 independent-audit turn (MVP_ACCEPT-168).

        The audit runs on the bound separate provider path with the
        bound key ref only (refs cross the runner boundary, never
        values). Exactly one audited turn: a failed audit is recorded,
        never retried blindly.
        """
        if not isinstance(binding, L3AuditBinding):
            raise L3KeyRefRequiredError(
                "run_l3_audit needs an L3AuditBinding "
                "[L3_KEY_REF_REQUIRED]")
        if not isinstance(secret_ref, SecretRef) or \
                secret_ref.secret_id != binding.key_ref.secret_id:
            raise L3KeyRefRequiredError(
                "run_l3_audit needs the bound L3 SecretRef record "
                "[L3_KEY_REF_REQUIRED]")
        effective = runner if runner is not None else self._runner
        if effective is None:
            raise RunnerUnboundError(
                "L3 audit has no runner wired; pass runner=..."
            )
        audit_config = RunConfig(
            decision_id=binding.decision_id,
            project_id=binding.project_id, task_id=binding.task_id,
            run_id=binding.run_id,
            selected_provider=binding.l3_provider,
            selected_model=binding.l3_model,
            route="L3_AUDIT", strategy="independent",
            max_runner_retries=1)
        outcome = run_sdk_turn(
            run_config=audit_config,
            input_ref=input_ref,
            secret_ids=(secret_ref.secret_id,),
            transport=transport_for_provider(binding.l3_provider),
            turn_budget=audit_config.max_runner_retries,
            sdk_call=effective,
        )
        self._calls_made += outcome.attempts_made
        if outcome.ok:
            return SdkRunResult(
                run_id=binding.run_id,
                output_ref="artifact:run/%s/output" % binding.run_id,
                provider=binding.l3_provider,
                model=binding.l3_model,
                status=manifest.ExecutionAttemptStatus.SUCCEEDED,
            )
        return SdkRunResult(
            run_id=binding.run_id,
            output_ref="artifact:run/%s/output" % binding.run_id,
            provider=binding.l3_provider,
            model=binding.l3_model,
            status=manifest.ExecutionAttemptStatus.FAILED,
            error_ref=outcome.error,
        )


def verified_sdk_surface() -> dict[str, Any]:
    """Return the verified SDK surface architecture conclusions may use.

    The surface is exactly this module's ``__all__`` names that resolve
    to real module objects (verified by lookup at call time), plus the
    SDK availability flag from the real guarded import. Anything beyond
    these names is unverified and must not carry conclusions (SDK-132).
    """
    here = globals()
    names = sorted(here.get("__all__", ()))
    missing = [name for name in names if name not in here]
    return {
        "sdk_available": SDK_AVAILABLE,
        "surface": [name for name in names if name not in missing],
        "unverified": missing,
    }


__all__ = [
    "SDK_AVAILABLE",
    "USE_SDK_UNLESS_DOCUMENTED_CRITICAL_BLOCKER",
    "CHAT_COMPLETIONS_TRANSPORT",
    "SDK_DEFAULT_TRANSPORT",
    "transport_for_provider",
    "verified_sdk_surface",
    "SecretRef",
    "SdkClientConfig",
    "RoutingDecisionBinding",
    "RunConfig",
    "SdkRunResult",
    "AgentBuilderWorkflow",
    "L3AuditBinding",
    "bind_l3_audit",
    "L3ProviderMustDifferError",
    "L3KeyRefRequiredError",
    "BuilderWorkflowHashMismatchError",
    "RunConfigRequiredError",
    "SdkClientConfigError",
    "SecretRefTypeError",
    "WorkflowNotRevalidatedError",
    "revalidate_agent_builder_workflow",
    "L3_PROVIDER_MUST_DIFFER",
    "L3_KEY_REF_REQUIRED",
    "BUILDER_WORKFLOW_HASH_MISMATCH",
    "BUILDER_WORKFLOW_NOT_REVALIDATED",
    "SDK_CLIENT_MAX_RETRIES_NONZERO",
    "SDK_RUN_CONFIG_REQUIRED",
    "SDK_SECRET_REFS_MUST_BE_RECORDS",
    "OpenAIAgentsSDKAdapter",
]
