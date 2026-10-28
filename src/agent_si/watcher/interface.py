"""K08 watcher-side frozen cross-package interface (shapes only, no logic).

Frozen sources: RECORDS/day0/0C_ARCHITECTURE.md sec 12 (0C wins clashes;
K08 watcher prefix src/agent_si/watcher/, routes backend/watcher_routes.py
plus backend/stop_all.py), RECORDS/day0/K13_MANIFEST.md sections 21
(GovernanceArtifact hashes consumed by the integrity check) and 45A/46
(severity names reused exactly, never redefined), RECORDS/day1/K02 and K04
frozen interfaces, the automation-side interface (JournalKind order plus
JournalEntry fields reused exactly) and the context-keeper interface
(shared severity names). Other packages code against this module only;
lane internals (names starting with _) are never imported. Every function
body is `...` (no logic): real behaviour lives in the owning lane module
named in REALIZATION_MAP. Standard library only.
Watcher serves stored facts only and never computes values, never writes
the workspace and never touches budget; every rule evaluation records one
WATCH_DECISION journal row.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Tuple

__all__ = (
    "JournalKind",
    "WatchVerdict",
    "JournalEntry",
    "WatchDecision",
    "GuardDecision",
    "EngineTick",
    "IntegrityReport",
    "WatcherStatus",
    "StopReceipt",
    "WatcherError",
    "ERROR_CODES",
    "PRESETS",
    "HTTP_ROUTES",
    "ROUTE_ENTRY_POINTS",
    "REALIZATION_MAP",
    "SURFACE_FUNCTIONS",
    "append_event",
    "list_events",
    "verify_integrity",
    "evaluate_rule",
    "engine_tick",
    "engine_decide",
    "apply_preset",
    "get_status",
    "guard_check_escape",
    "stop_all_request_stop",
)


class JournalKind(str, Enum):
    """Frozen journal event kinds carried on journal.append_event."""

    WATCH_DECISION = "WATCH_DECISION"
    TAMPER_ATTEMPT = "TAMPER_ATTEMPT"
    GUARD_BLOCK = "GUARD_BLOCK"
    STOP_ALL = "STOP_ALL"
    SERVICE_STATE = "SERVICE_STATE"
    AUTOMATION_RUN = "AUTOMATION_RUN"
    CONTEXT_CHECKPOINT = "CONTEXT_CHECKPOINT"
    CONTEXT_RECOVERY = "CONTEXT_RECOVERY"
    OUTAGE_SIGNAL = "OUTAGE_SIGNAL"


class WatchVerdict(str, Enum):
    """Frozen rule-card verdicts recorded on WATCH_DECISION rows."""

    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    ESCALATE = "ESCALATE"


@dataclass(frozen=True)
class JournalEntry:
    """Frozen journal.append_event receipt."""

    entry_id: str
    timestamp: str
    hash: str = ""


@dataclass(frozen=True)
class WatchDecision:
    """Frozen rule evaluation outcome plus its WATCH_DECISION row ref."""

    decision_id: str
    project_id: str
    rule_id: str
    verdict: WatchVerdict = WatchVerdict.ALLOW
    journal_entry_id: str = ""
    decided_at: str = ""


@dataclass(frozen=True)
class GuardDecision:
    """Frozen guard.check_escape outcome: allowed plus the reason."""

    allowed: bool = False
    reason: str = ""


@dataclass(frozen=True)
class EngineTick:
    """Frozen watcher.engine.tick outcome: the rule cards fired plus when."""

    project_id: str
    fired: Tuple[str, ...] = ()
    checked_at: str = ""


@dataclass(frozen=True)
class IntegrityReport:
    """Frozen watcher.verify_integrity outcome over stored hashes."""

    project_id: str
    ok: bool
    checked_at: str = ""
    mismatched_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class WatcherStatus:
    """Frozen watcher.status.get payload: served stored facts only, never computed."""

    project_id: str
    integrity_ok: bool = False
    journal_head: str = ""
    generated_at: str = ""


@dataclass(frozen=True)
class StopReceipt:
    """Frozen stop_all.request_stop receipt: accepted plus the reason."""

    accepted: bool = False
    reason: str = ""


class WatcherError(Exception):
    """Frozen watcher error: code is one of ERROR_CODES."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


#: Frozen watcher error-code names; each is raised in its own condition.
ERROR_CODES = (
    "RULE_NOT_FOUND",
    "GOVERNANCE_MISMATCH",
    "JOURNAL_KIND_UNKNOWN",
    "STOP_REASON_MISSING",
    "PRESET_NOT_FOUND",
    "SESSION_TOKEN_MISSING",
    "SESSION_TOKEN_INVALID",
)

#: Frozen watcher preset names: cautious / standard / strict; a fresh
#: project seeds the default preset.
PRESETS = (
    "cautious",
    "standard",
    "strict",
)

#: Frozen watcher HTTP surface: (method, path) pairs served from
#: backend/watcher_routes.py plus backend/stop_all.py through the entry
#: points below.
HTTP_ROUTES = (
    ("GET", "/api/v1/watcher/status"),
    ("GET", "/api/v1/watcher/journal"),
    ("POST", "/api/v1/watcher/integrity-check"),
    ("POST", "/api/v1/watcher/rules/{id}/evaluate"),
    ("POST", "/api/v1/stop-all"),
)

#: Every route maps to exactly one entry point in this module.
ROUTE_ENTRY_POINTS = {
    "GET /api/v1/watcher/status": "get_status",
    "GET /api/v1/watcher/journal": "list_events",
    "POST /api/v1/watcher/integrity-check": "verify_integrity",
    "POST /api/v1/watcher/rules/{id}/evaluate": "evaluate_rule",
    "POST /api/v1/stop-all": "stop_all_request_stop",
}

#: Frozen function name to owning lane implementation (dotted path).
#: Cross-lane references (guard, stop_all) are called by the owning lanes
#: and never implemented here.
REALIZATION_MAP = {
    "journal.append_event": "agent_si.watcher.journal.append_event",
    "journal.list_events": "agent_si.watcher.journal.list_events",
    "watcher.verify_integrity": "agent_si.watcher.integrity.verify",
    "watcher.evaluate_rule": "agent_si.watcher.rules.evaluate",
    "watcher.engine.tick": "agent_si.watcher.engine.tick",
    "watcher.engine.decide": "agent_si.watcher.engine.decide",
    "watcher.preset.apply": "agent_si.watcher.presets.apply",
    "watcher.status.get": "agent_si.watcher.status.get",
    "guard.check_escape": "agent_si.toolguard.escape.check_escape",
    "stop_all.request_stop": "agent_si.backend.stop_all.request_stop",
}

#: Every cross-package surface name maps to exactly one entry point in
#: this module; routes reach the same entry points via ROUTE_ENTRY_POINTS.
SURFACE_FUNCTIONS = {
    "journal.append_event": "append_event",
    "journal.list_events": "list_events",
    "watcher.verify_integrity": "verify_integrity",
    "watcher.evaluate_rule": "evaluate_rule",
    "watcher.engine.tick": "engine_tick",
    "watcher.engine.decide": "engine_decide",
    "watcher.preset.apply": "apply_preset",
    "watcher.status.get": "get_status",
    "guard.check_escape": "guard_check_escape",
    "stop_all.request_stop": "stop_all_request_stop",
}


def append_event(project_id: str, source: str, kind: str, summary: str, refs: Tuple[str, ...]) -> JournalEntry:
    """Journal append: raise JOURNAL_KIND_UNKNOWN for unknown kinds."""
    ...


def list_events(project_id: str, kind: str = "") -> Tuple[JournalEntry, ...]:
    """Journal read: stored rows only, never computed; empty kind reads all kinds."""
    ...


def verify_integrity(project_id: str, session_token: str = "") -> IntegrityReport:
    """Integrity check over stored governance hashes: raise GOVERNANCE_MISMATCH on mismatch; POST route refuses with SESSION_TOKEN_MISSING when session_token is missing and SESSION_TOKEN_INVALID when wrong, before any write."""
    ...


def evaluate_rule(project_id: str, rule_id: str, session_token: str = "") -> WatchDecision:
    """Rule-card evaluation over stored facts: raise RULE_NOT_FOUND for unknown rules; records one WATCH_DECISION row; POST route refuses with SESSION_TOKEN_MISSING when session_token is missing and SESSION_TOKEN_INVALID when wrong, before any write."""
    ...


def engine_tick(project_id: str) -> EngineTick:
    """Engine tick: fire due rule cards now; each firing records one WATCH_DECISION row."""
    ...


def engine_decide(project_id: str, card_id: str, script: str, params: Tuple[str, ...]) -> WatchDecision:
    """Engine decide: commit the rule-allowed script plus params chosen for a fired card; raise RULE_NOT_FOUND for unknown cards; records one WATCH_DECISION row."""
    ...


def apply_preset(project_id: str, preset_id: str) -> Tuple[str, ...]:
    """Preset apply: install the preset's rule cards; return the installed card ids; raise PRESET_NOT_FOUND for unknown presets."""
    ...


def get_status(project_id: str) -> WatcherStatus:
    """Watcher status: served stored facts only, never computed values."""
    ...


def guard_check_escape(agent_id: str, path: str, workspace_root: str) -> GuardDecision:
    """Guard escape check before workspace writes: allow paths inside workspace_root, block escapes; never built here."""
    ...


def stop_all_request_stop(actor: str, project_id: str, grant_ref: str = "", session_token: str = "") -> StopReceipt:
    """Stop-all receipt: USER always accepted; Director needs a live grant_ref (raise STOP_REASON_MISSING when missing; expired grants refused); other actors refused; never built here; POST route refuses with SESSION_TOKEN_MISSING when session_token is missing and SESSION_TOKEN_INVALID when wrong, before any stop is recorded."""
    ...
