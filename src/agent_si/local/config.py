"""Local-AI settings: validated LocalAIConfig persistence with per-project scope and explicit endpoint, model, and permission fields.

Every mutation is validated through validate_config (validate_endpoint,
validate_model, validate_permission) and carries a per-change
DecisionRecord built by record_decision; save_config and update_config
refuse a missing decision record. Scope: one project_key never reads
another project_key — load_config enforces the project-scope guard, and
update_config accepts only EXPLICIT_CONFIG_FIELDS keys (endpoint_url,
model_id, permission_scope, local_only_mode). load_config, save_config
and update_config persist LocalAIConfig; get_local_ai_view serves the
stored config as a LocalAISettingsView. enforce_local_only raises on any
attempted cloud call and local_only_warnings warns on weak evidence.
ERROR_CODES_M2 names the frozen settings codes.
Standard library + typing only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

#: M2 settings codes (one per TASK row; frozen: rename only via HD request).
LOCAL_AI_PROJECT_SCOPE_VIOLATION = "LOCAL_AI_PROJECT_SCOPE_VIOLATION"
LOCAL_AI_INVALID_ENDPOINT = "LOCAL_AI_INVALID_ENDPOINT"
LOCAL_AI_INVALID_MODEL = "LOCAL_AI_INVALID_MODEL"
LOCAL_AI_INVALID_PERMISSION = "LOCAL_AI_INVALID_PERMISSION"
LOCAL_AI_AMBIGUOUS_FIELD = "LOCAL_AI_AMBIGUOUS_FIELD"
LOCAL_AI_LOCAL_ONLY_VIOLATION = "LOCAL_AI_LOCAL_ONLY_VIOLATION"
LOCAL_AI_DECISION_RECORD_REQUIRED = "LOCAL_AI_DECISION_RECORD_REQUIRED"
LOCAL_AI_CONFIG_NOT_FOUND = "LOCAL_AI_CONFIG_NOT_FOUND"

#: Frozen M2 code set (row map: -70 scope, -181 endpoint/model/permission,
#: SPEC30 ambiguous, M-P4-133/BP06-48 local-only, [111] decision, -526 view).
ERROR_CODES_M2 = (
    LOCAL_AI_PROJECT_SCOPE_VIOLATION,
    LOCAL_AI_INVALID_ENDPOINT,
    LOCAL_AI_INVALID_MODEL,
    LOCAL_AI_INVALID_PERMISSION,
    LOCAL_AI_AMBIGUOUS_FIELD,
    LOCAL_AI_LOCAL_ONLY_VIOLATION,
    LOCAL_AI_DECISION_RECORD_REQUIRED,
    LOCAL_AI_CONFIG_NOT_FOUND,
)

#: Only explicit patch keys ever accepted by update_config (SPEC 30).
EXPLICIT_CONFIG_FIELDS = (
    "endpoint_url",
    "model_id",
    "permission_scope",
    "local_only_mode",
)

#: K07B settings.localAi key names (K07 renders, K05 serves; names only).
LOCAL_AI_TITLE_KEY = "settings.localAi.title"
LOCAL_AI_PURPOSE_KEY = "settings.localAi.purpose"
LOCAL_AI_NEED_IT_NOW_KEY = "settings.localAi.needItNow"

#: Permission allowlist (frozen row -181: only this scope is servable).
_ALLOWED_PERMISSION_SCOPES = ("local-contact-allowed",)

#: Capability-evidence values counted as weak under LOCAL-ONLY mode.
_WEAK_EVIDENCE_VALUES = ("UNKNOWN", "NO-DATA")


class LocalAISettingsError(Exception):
    """Settings failure; carries one ERROR_CODES_M2 code in `code`."""

    code: str

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class DecisionRecord:
    """K05-own per-change record (K13 DecisionRecord by name; K02 names only)."""

    decision_id: str
    project_id: str
    statement: str
    reason: str
    authority: str
    created_at: str


@dataclass(frozen=True)
class LocalAIConfig:
    """Project-scoped stored config; sole persistence shape (B0B-181)."""

    project_key: str
    endpoint_url: str
    model_id: str
    permission_scope: str
    local_only_mode: bool = False
    capability_evidence: str = "UNKNOWN"


@dataclass(frozen=True)
class LocalAISettingsView:
    """Stored config served to the K07 settings.localAi view (ARCH-526)."""

    project_key: str
    title_key: str
    purpose_key: str
    need_it_now_key: str
    config: LocalAIConfig


def _default_config(project_key: str) -> LocalAIConfig:
    """Seed default stored config for one project key."""
    return LocalAIConfig(
        project_key=project_key,
        endpoint_url="http://127.0.0.1:11434",
        model_id="llama3.1:8b",
        permission_scope="local-contact-allowed",
    )


#: In-memory store, seeded with the proj-a default (B0B-181).
_STORE: Dict[str, LocalAIConfig] = {"proj-a": _default_config("proj-a")}


def validate_endpoint(endpoint_url: str) -> None:
    """Reject a bad endpoint with LOCAL_AI_INVALID_ENDPOINT."""
    url = endpoint_url.strip() if isinstance(endpoint_url, str) else ""
    if not (url.startswith("http://") or url.startswith("https://")):
        raise LocalAISettingsError(
            LOCAL_AI_INVALID_ENDPOINT,
            "endpoint_url must use http(s)://: %r" % (endpoint_url,),
        )
    rest = url.split("://", 1)[1]
    if not rest.strip():
        raise LocalAISettingsError(
            LOCAL_AI_INVALID_ENDPOINT,
            "endpoint_url must use http(s)://: %r" % (endpoint_url,),
        )


def validate_model(model_id: str) -> None:
    """Reject a bad model with LOCAL_AI_INVALID_MODEL."""
    if not isinstance(model_id, str) or not model_id.strip():
        raise LocalAISettingsError(
            LOCAL_AI_INVALID_MODEL,
            "model_id must be a non-empty string",
        )


def validate_permission(permission_scope: str) -> None:
    """Reject a bad permission with LOCAL_AI_INVALID_PERMISSION."""
    if permission_scope not in _ALLOWED_PERMISSION_SCOPES:
        raise LocalAISettingsError(
            LOCAL_AI_INVALID_PERMISSION,
            "permission_scope %r is not allowed" % (permission_scope,),
        )


def validate_config(config: LocalAIConfig) -> None:
    """Validate every explicit field of one stored config."""
    validate_endpoint(config.endpoint_url)
    validate_model(config.model_id)
    validate_permission(config.permission_scope)


def record_decision(project_id: str, statement: str, reason: str,
                    authority: str) -> DecisionRecord:
    """Per-change decision record for one validated mutation ([111])."""
    return DecisionRecord(
        decision_id="dec-%s" % uuid4().hex[:12],
        project_id=project_id,
        statement=statement,
        reason=reason,
        authority=authority,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def load_config(project_key: str, reader_project_key: str) -> LocalAIConfig:
    """Load stored config; cross-key reads raise PROJECT_SCOPE_VIOLATION."""
    if project_key != reader_project_key:
        raise LocalAISettingsError(
            LOCAL_AI_PROJECT_SCOPE_VIOLATION,
            "reader %r must not read project %r"
            % (reader_project_key, project_key),
        )
    try:
        return _STORE[project_key]
    except KeyError:
        raise LocalAISettingsError(
            LOCAL_AI_CONFIG_NOT_FOUND,
            "no stored config for project %r" % (project_key,),
        ) from None


def save_config(config: LocalAIConfig,
                decision: Optional[DecisionRecord]) -> LocalAIConfig:
    """Persist validated config; missing decision raises DECISION_REQUIRED."""
    if decision is None:
        raise LocalAISettingsError(
            LOCAL_AI_DECISION_RECORD_REQUIRED,
            "save_config needs a per-change decision record",
        )
    if decision.project_id != config.project_key:
        raise LocalAISettingsError(
            LOCAL_AI_PROJECT_SCOPE_VIOLATION,
            "decision project %r must match config project %r"
            % (decision.project_id, config.project_key),
        )
    validate_config(config)
    _STORE[config.project_key] = config
    return config


def update_config(project_key: str, patch: Dict[str, Any],
                  decision: Optional[DecisionRecord]) -> LocalAIConfig:
    """Validate + persist one explicit-field patch with its decision record."""
    if decision is None:
        raise LocalAISettingsError(
            LOCAL_AI_DECISION_RECORD_REQUIRED,
            "update_config needs a per-change decision record",
        )
    if decision.project_id != project_key:
        raise LocalAISettingsError(
            LOCAL_AI_PROJECT_SCOPE_VIOLATION,
            "decision project %r must match config project %r"
            % (decision.project_id, project_key),
        )
    for key in patch:
        if key not in EXPLICIT_CONFIG_FIELDS:
            raise LocalAISettingsError(
                LOCAL_AI_AMBIGUOUS_FIELD,
                "patch key %r is not an explicit config field" % (key,),
            )
    current = load_config(project_key, project_key)
    merged = {
        "project_key": current.project_key,
        "endpoint_url": current.endpoint_url,
        "model_id": current.model_id,
        "permission_scope": current.permission_scope,
        "local_only_mode": current.local_only_mode,
        "capability_evidence": current.capability_evidence,
    }
    for key in EXPLICIT_CONFIG_FIELDS:
        if key in patch:
            merged[key] = patch[key]
    updated = LocalAIConfig(**merged)
    return save_config(updated, decision)


def get_local_ai_view(project_key: str,
                      reader_project_key: str) -> LocalAISettingsView:
    """Serve the stored config to the K07 settings.localAi view (ARCH-526)."""
    config = load_config(project_key, reader_project_key)
    return LocalAISettingsView(
        project_key=config.project_key,
        title_key=LOCAL_AI_TITLE_KEY,
        purpose_key=LOCAL_AI_PURPOSE_KEY,
        need_it_now_key=LOCAL_AI_NEED_IT_NOW_KEY,
        config=config,
    )


def enforce_local_only(config: LocalAIConfig,
                       attempted_cloud_call: bool) -> None:
    """LOCAL-ONLY: any cloud call raises LOCAL_ONLY_VIOLATION (zero cloud)."""
    if config.local_only_mode and attempted_cloud_call:
        raise LocalAISettingsError(
            LOCAL_AI_LOCAL_ONLY_VIOLATION,
            "local-only project %r must make zero cloud calls"
            % (config.project_key,),
        )


def local_only_warnings(config: LocalAIConfig) -> List[str]:
    """LOCAL-ONLY: warn where capability evidence is weak (UNKNOWN/NO-DATA)."""
    if not config.local_only_mode:
        return []
    evidence = config.capability_evidence
    marker = evidence.strip().upper() if isinstance(evidence, str) else ""
    if marker in _WEAK_EVIDENCE_VALUES or not marker:
        return [
            "weak capability evidence %r under local-only mode "
            "for project %r" % (evidence, config.project_key)
        ]
    return []
