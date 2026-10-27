"""SDK tracing privacy policy (Manifest section 42A).

Explicit per-project + per-run policy. Default DISABLED: every project and
run ships with tracing off and local-processor-only handling. Hosted export
additionally needs an authorization record + a configured key + redaction.
Secrets-bearing runs refuse external export unless explicitly authorized.
Application telemetry is complete with tracing off: tracing is diagnostic
instrumentation, never the authoritative store.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SdkTracingPolicy:
    """Manifest section 42A SDKTracingPolicy. Immutable; new content = new record."""

    enabled: bool = False
    destination: str = "local-processor"
    data_classification: str = "private"
    redaction_required: bool = True
    allow_model_input: bool = False
    allow_model_output: bool = False
    allow_tool_arguments: bool = False
    allow_tool_results: bool = False
    allow_file_content: bool = False
    retention_policy: str = "local-only"
    external_export_allowed: bool = False
    project_scope: str = ""


DEFAULT_POLICY = SdkTracingPolicy()
"""Frozen default: DISABLED with local-processor-only handling."""

APP_TELEMETRY_INDEPENDENT_OF_TRACING = True
"""Application telemetry stays complete with tracing off (Manifest section 9)."""


def is_hosted_export_permitted(
    policy: SdkTracingPolicy,
    *,
    authorization_ref: object = None,
    export_key_ref: object = None,
    run_has_secrets: bool = False,
    secrets_export_authorized: bool = False,
) -> bool:
    """Return True iff a hosted trace export is permitted (section 42A).

    Hosted export needs the policy enabled with external export allowed,
    mandatory redaction, an authorization record ref, and a configured key
    ref. Secrets-bearing runs additionally need explicit secrets-export
    authorization; without it external export is refused.
    """
    if not policy.enabled:
        return False
    if not policy.external_export_allowed:
        return False
    if not policy.redaction_required:
        return False
    if not authorization_ref or not export_key_ref:
        return False
    if run_has_secrets and not secrets_export_authorized:
        return False
    return True


def app_telemetry_requires_tracing() -> bool:
    """Return False: telemetry never depends on tracing (section 9, 42A)."""
    return False


__all__ = [
    "SdkTracingPolicy",
    "DEFAULT_POLICY",
    "APP_TELEMETRY_INDEPENDENT_OF_TRACING",
    "is_hosted_export_permitted",
    "app_telemetry_requires_tracing",
]
