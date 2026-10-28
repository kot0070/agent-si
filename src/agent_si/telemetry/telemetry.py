"""Telemetry event store (Manifest §55 TELEMETRY_EVENT; §20A secrets; §59 export).

Append-only TelemetryEvent envelopes plus SecretRef handles, redact(), and
the §59 export allowlist. Unknown event_type is rejected (new types are a
new vocabulary version, never silent); a duplicate event_id returns the
stored record; corrections are new records. Raw secrets never enter the
store: append() refuses envelopes carrying known raw values, and every
render/export path goes through redact().
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, FrozenSet, Iterable, List, Mapping, Optional, Tuple

try:
    from iface.frozen_manifest import manifest
except ImportError:  # alternate layout: the iface/ directory itself on sys.path
    from frozen_manifest import manifest

EVENT_VOCABULARY_VERSION = 1
"""Bump when a new event_type is added (Manifest §55: never silent)."""

EVENT_VOCABULARY: Dict[str, FrozenSet[str]] = {
    "PROJECT_CREATED": frozenset(),
    "PROJECT_UPDATED": frozenset(),
    "TASK_CREATED": frozenset({"task_id"}),
    "TASK_TRANSITIONED": frozenset({"task_id"}),
    "RUN_CREATED": frozenset({"task_id", "run_id"}),
    "RUN_STARTED": frozenset({"task_id", "run_id"}),
    "RUN_TERMINATED": frozenset({"task_id", "run_id"}),
    "ATTEMPT_STARTED": frozenset({"task_id", "run_id", "attempt_id"}),
    "ATTEMPT_FINISHED": frozenset({"task_id", "run_id", "attempt_id"}),
    "SUBTASK_DISPATCHED": frozenset({"task_id", "subtask_id"}),
    "VERIFICATION_COMPLETED": frozenset({"task_id", "run_id"}),
    "AUDIT_COMPLETED": frozenset({"task_id", "run_id"}),
    "PROVIDER_USAGE_REPORTED": frozenset(),
    "SYSTEM_INCIDENT_LOGGED": frozenset(),
}
"""event_type -> required identity fields (Manifest §55: type sets identity).

task_id is null only for project/system/provider events; run_id is null
before run creation or for non-run events; attempt_id/subtask_id are null
when not attempt-/subtask-scoped.
"""

EXPORT_ALLOWLIST = frozenset(
    {
        "PROJECT",
        "GOAL",
        "SCOPE",
        "ARCH",
        "PHASES",
        "TASKS",
        "RUNS",
        "MANAGERS",
        "AGENTS",
        "MODELS",
        "PROVIDERS",
        "ROUTES",
        "SPLIT_STRATEGIES",
        "ROUTING_DECISIONS",
        "FALLBACKS",
        "TIME",
        "TOKENS",
        "COST",
        "LOCAL_CALLS",
        "CLOUD_CALLS",
        "RETRIES",
        "REWORKS",
        "FAILURES",
        "INCIDENTS",
        "DEVIATIONS",
        "AMENDMENTS",
        "SECURITY",
        "TESTS",
        "AUDITS",
        "LIMITATIONS",
        "RISKS",
        "CONTEXT_INTEGRITY",
        "CONTEXT_VIOLATIONS",
        "BUDGET",
        "SDK_TRACING_POLICY",
        "USAGE_REPORTING_CAPABILITY",
        "FINAL_STATUS",
    }
)
"""Frozen §59 report-dataset key set: exports hold these keys only."""

REDACTED = "[REDACTED]"


class TelemetryError(Exception):
    """Base error for the telemetry event store."""


class MissingProjectIdError(TelemetryError):
    """project_id is REQUIRED on every TelemetryEvent (Manifest §55)."""


class UnknownEventTypeError(TelemetryError):
    """event_type is outside EVENT_VOCABULARY (Manifest §55: rejected)."""


class MissingIdentityFieldError(TelemetryError):
    """event_type requires an identity field left null (Manifest §55)."""


class SecretLeakRefusedError(TelemetryError):
    """Envelope carries a known raw secret value: refused (§20A)."""


@dataclass(frozen=True)
class TelemetryEvent:
    """Manifest §55 TelemetryEvent envelope (NOT a multi-metric record)."""

    event_id: str = ""
    project_id: str = ""
    timestamp: str = ""
    task_id: Optional[str] = None
    run_id: Optional[str] = None
    attempt_id: Optional[str] = None
    subtask_id: Optional[str] = None
    parent_id: Optional[str] = None
    role: Optional[str] = None
    task_class: Optional[str] = None
    risk: Optional[manifest.RiskLevel] = None
    state: Optional[str] = None
    route: Optional[str] = None
    split_strategy: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    provider_instance: Optional[str] = None
    event_type: str = ""
    retry: Optional[str] = None
    verification_ref: Optional[str] = None
    audit_ref: Optional[str] = None
    re_execution: Optional[str] = None
    error_ref: Optional[str] = None
    fallback_reason: Optional[str] = None
    capability_rule: Optional[str] = None
    capability_evidence_ref: Optional[str] = None
    routing_decision_ref: Optional[str] = None
    routing_snapshot_id: Optional[str] = None
    resource_state_ref: Optional[str] = None
    metric_refs: Tuple[str, ...] = ()
    final_status: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.project_id:
            raise MissingProjectIdError("project_id is REQUIRED")
        if self.event_type not in EVENT_VOCABULARY:
            raise UnknownEventTypeError(
                "unknown event_type %r (vocabulary v%s)"
                % (self.event_type, EVENT_VOCABULARY_VERSION)
            )
        missing = [
            name
            for name in EVENT_VOCABULARY[self.event_type]
            if getattr(self, name) is None
        ]
        if missing:
            raise MissingIdentityFieldError(
                "event_type %r requires %s" % (self.event_type, sorted(missing))
            )
        if isinstance(self.risk, str) and not isinstance(
            self.risk, manifest.RiskLevel
        ):
            object.__setattr__(self, "risk", manifest.RiskLevel(self.risk))
        if not isinstance(self.metric_refs, tuple):
            object.__setattr__(self, "metric_refs", tuple(self.metric_refs or ()))


@dataclass(frozen=True)
class SecretRef:
    """Manifest §20A SecretRef: handles travel, raw values never do."""

    secret_id: str = ""
    provider_id: str = ""
    type: str = ""
    scope: str = ""
    source: str = ""
    created_at: str = ""
    last_rotated_at: str = ""

    def __post_init__(self) -> None:
        if not self.secret_id:
            raise ValueError("secret_id is REQUIRED")


def _iter_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from _iter_strings(item)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            yield from _iter_strings(item)


def contains_raw_secret(value: Any, secrets: Iterable[str]) -> bool:
    """True iff any known raw secret value occurs anywhere in value."""
    texts = list(_iter_strings(value))
    for secret in secrets or ():
        if secret and any(secret in text for text in texts):
            return True
    return False


def redact(value: Any, secrets: Iterable[str]) -> Any:
    """Replace every known raw secret occurrence with REDACTED (§20A).

    Walks mappings/sequences recursively, so wrapped secrets (nested
    dicts, lists, tuples, prefixed/suffixed values) are redacted too.
    SecretRef handles carry no raw values and pass through unchanged.
    """
    known = [secret for secret in (secrets or ()) if secret]
    if isinstance(value, SecretRef):
        return value
    if isinstance(value, str):
        for secret in known:
            if secret in value:
                value = value.replace(secret, REDACTED)
        return value
    if isinstance(value, Mapping):
        return {key: redact(item, known) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(redact(item, known) for item in value)
    if isinstance(value, list):
        return [redact(item, known) for item in value]
    if isinstance(value, (set, frozenset)):
        return type(value)(redact(item, known) for item in value)
    return value


def filter_export_dataset(dataset: Mapping[str, Any]) -> Dict[str, Any]:
    """Keep only §59 allowlisted keys; private content never exports."""
    return {key: dataset[key] for key in EXPORT_ALLOWLIST if key in dataset}


def export_event(event: TelemetryEvent, secrets: Iterable[str] = ()) -> Dict[str, Any]:
    """Redacted envelope mapping for logs/reports (never raw secrets)."""
    return redact(asdict(event), secrets)


class TelemetryEventLog:
    """Append-only TelemetryEvent store (Manifest §55 + ports shape).

    append() refuses envelopes carrying known raw secret values (§20A)
    and returns the stored record on duplicate event_id (no duplicate).
    """

    def __init__(self) -> None:
        self._records: Dict[str, TelemetryEvent] = {}

    def append(
        self, event: TelemetryEvent, known_secrets: Iterable[str] = ()
    ) -> TelemetryEvent:
        known = list(known_secrets or ())
        if contains_raw_secret(asdict(event), known):
            raise SecretLeakRefusedError(
                "envelope carries a raw secret value: refused"
            )
        stored = self._records.get(event.event_id)
        if stored is not None:
            return stored
        self._records[event.event_id] = event
        return event

    def load(self, event_id: str) -> Optional[TelemetryEvent]:
        return self._records.get(event_id)

    def list_by_project(self, project_id: str) -> List[TelemetryEvent]:
        return [
            event for event in self._records.values() if event.project_id == project_id
        ]

    def __len__(self) -> int:
        return len(self._records)
