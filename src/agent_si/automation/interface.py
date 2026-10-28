"""K08 automation-side frozen cross-package interface (shapes only, no logic).

Frozen sources: RECORDS/day0/0C_ARCHITECTURE.md sec 12 (0C wins clashes),
RECORDS/day1/K02_INTERFACE.md, RECORDS/day1/K04_INTERFACE.md,
RECORDS/day1/K04_INTERFACE_STUB.py, RECORDS/day1/K07A_api_iface.ts,
RECORDS/day1/K07A_app_iface.ts, RECORDS/day1/K07A_ui_iface.ts,
RECORDS/day1/K07B_IFACE.d.ts,
RECORDS/day1/K13 V5 interface transcription (cd6fbd6d) plus its contract
test (e9c2d320) and the K13 manifest (f256bab4): K13-owned names
(BudgetGate calls, K13 error names, severity levels) are reused exactly
and never redefined here; 0C wins every clash, then K13 V5 names.
Other packages code against this module only; lane internals (names
starting with _) are never imported. Every function body is `...`
(no logic): real behaviour lives in the owning lane module named
in REALIZATION_MAP. Standard library only.
Automation observes budget only through BUDGET_CALLS_ALLOWLIST and
notifies on change; it never starts or stops external services itself.
Pause is global plus per-project, and every timer, launcher and metric
action checks it before acting.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Tuple

__all__ = (
    "ServiceState",
    "ServiceCheckKind",
    "JournalKind",
    "AutomationRunState",
    "TriggerKind",
    "OutageSeverity",
    "ServiceStatus",
    "JournalEntry",
    "AppsCardData",
    "AutomationRun",
    "AutomationTrigger",
    "AutomationTemplate",
    "OutageReport",
    "StopReceipt",
    "AutomationError",
    "ERROR_CODES",
    "BUDGET_CALLS_ALLOWLIST",
    "HTTP_ROUTES",
    "ROUTE_ENTRY_POINTS",
    "REALIZATION_MAP",
    "SURFACE_FUNCTIONS",
    "set_global_pause",
    "is_pause_effective",
    "get_service_status",
    "run_service_check",
    "get_apps_card",
    "start_run",
    "fire_trigger",
    "instantiate_template",
    "launch",
    "resume",
    "signal_outage",
    "journal_append_event",
    "guard_check_escape",
    "stop_all_request_stop",
)


class ServiceState(str, Enum):
    """Frozen service states served by service.status.get."""

    UP = "UP"
    DOWN = "DOWN"
    DEGRADED = "DEGRADED"


class ServiceCheckKind(str, Enum):
    """Frozen check types; container checks are read-only."""

    HTTP = "HTTP"
    TCP = "TCP"
    CONTAINER_READONLY = "CONTAINER_READONLY"


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


class AutomationRunState(str, Enum):
    """Frozen automation run states."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TriggerKind(str, Enum):
    """Frozen trigger kinds: timers, launchers and metric triggers."""

    TIMER = "TIMER"
    LAUNCHER = "LAUNCHER"
    METRIC = "METRIC"


class OutageSeverity(str, Enum):
    """Frozen outage severities for the one-stop-and-report signal."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class ServiceStatus:
    """Frozen service.status.get payload."""

    service_id: str
    state: str
    timestamp: str
    in_use: bool = False
    last_used: str = ""
    last_agent: str = ""


@dataclass(frozen=True)
class JournalEntry:
    """Frozen journal.append_event receipt."""

    entry_id: str
    timestamp: str
    hash: str = ""


@dataclass(frozen=True)
class AppsCardData:
    """Frozen apps-card payload: served stored facts only, never computed."""

    project_id: str
    service_ids: Tuple[str, ...] = ()
    paused: bool = False
    generated_at: str = ""


@dataclass(frozen=True)
class AutomationRun:
    """Frozen automation run record."""

    run_id: str
    project_id: str
    template_id: str = ""
    trigger_id: Optional[str] = None
    state: str = "PENDING"
    started_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class AutomationTrigger:
    """Frozen automation trigger definition."""

    trigger_id: str
    project_id: str
    kind: str = "TIMER"
    schedule_ref: str = ""
    enabled: bool = True


@dataclass(frozen=True)
class AutomationTemplate:
    """Frozen automation template definition."""

    template_id: str
    project_id: str
    name: str = ""
    version: int = 1


@dataclass(frozen=True)
class OutageReport:
    """Frozen one-stop-and-report signal receipt."""

    report_id: str
    project_id: str
    service_id: str
    severity: str = "HIGH"
    journal_entry_id: str = ""
    stopped: bool = False
    reported_at: str = ""


@dataclass(frozen=True)
class StopReceipt:
    """Frozen stop_all.request_stop receipt."""

    project_id: str
    stopped: bool = False
    reason: str = ""


@dataclass(frozen=True)
class AutomationError(Exception):
    """Frozen automation error: code is one of ERROR_CODES."""

    code: str
    detail: str = ""


#: Frozen automation error-code names; each is raised in its own condition.
ERROR_CODES = (
    "AUTOMATION_PAUSED",
    "AUTOMATION_RUN_NOT_FOUND",
    "AUTOMATION_RUN_ACTIVE",
    "TRIGGER_NOT_FOUND",
    "TEMPLATE_NOT_FOUND",
    "SERVICE_NOT_FOUND",
    "SERVICE_CHECK_REFUSED",
    "PAUSE_REASON_MISSING",
    "SESSION_TOKEN_MISSING",
    "SESSION_TOKEN_INVALID",
)

#: Budget calls automation may observe/notify through; observe plus notify
#: only, never control of external services.
BUDGET_CALLS_ALLOWLIST = (
    "get_state",
    "compare_and_reserve",
    "settle",
    "replay",
    "select",
    "record_fallback",
)

#: Frozen automation HTTP surface: (method, path) pairs served from
#: backend/automation_routes.py through the entry points below.
HTTP_ROUTES = (
    ("GET", "/api/v1/automations/pause"),
    ("POST", "/api/v1/automations/pause"),
    ("GET", "/api/v1/services/{id}/status"),
    ("POST", "/api/v1/services/{id}/check"),
    ("GET", "/api/v1/apps/card"),
    ("POST", "/api/v1/automations/runs"),
    ("POST", "/api/v1/automations/triggers/{id}/fire"),
    ("POST", "/api/v1/automations/templates/{id}/instantiate"),
    ("POST", "/api/v1/automations/runs/{id}/launch"),
    ("POST", "/api/v1/automations/runs/{id}/resume"),
    ("POST", "/api/v1/outage/signal"),
)

#: Every route maps to exactly one entry point in this module.
ROUTE_ENTRY_POINTS = {
    "GET /api/v1/automations/pause": "is_pause_effective",
    "POST /api/v1/automations/pause": "set_global_pause",
    "GET /api/v1/services/{id}/status": "get_service_status",
    "POST /api/v1/services/{id}/check": "run_service_check",
    "GET /api/v1/apps/card": "get_apps_card",
    "POST /api/v1/automations/runs": "start_run",
    "POST /api/v1/automations/triggers/{id}/fire": "fire_trigger",
    "POST /api/v1/automations/templates/{id}/instantiate": "instantiate_template",
    "POST /api/v1/automations/runs/{id}/launch": "launch",
    "POST /api/v1/automations/runs/{id}/resume": "resume",
    "POST /api/v1/outage/signal": "signal_outage",
}

#: Frozen function name to owning lane implementation (dotted path).
#: Cross-lane references (journal, guard, stop_all) are called by the
#: owning lanes and never implemented here.
REALIZATION_MAP = {
    "pause.set_global": "agent_si.automation.pause.set_global",
    "pause.is_effective": "agent_si.automation.pause.is_effective",
    "service.status.get": "agent_si.automation.service_status.get",
    "service.check.run": "agent_si.automation.service_status.run_check",
    "apps.card.get": "agent_si.automation.apps_card.get_apps_card",
    "automation.run.start": "agent_si.automation.runner.start_run",
    "automation.trigger.fire": "agent_si.automation.triggers.fire_trigger",
    "automation.template.instantiate": "agent_si.automation.templates.instantiate",
    "automation.launch": "agent_si.automation.launcher.launch",
    "automation.resume": "agent_si.automation.runner.resume",
    "outage.signal": "agent_si.automation.outage.signal_outage",
    "journal.append_event": "agent_si.watcher.journal.append_event",
    "guard.check_escape": "agent_si.toolguard.escape.check_escape",
    "stop_all.request_stop": "agent_si.backend.stop_all.request_stop",
}

#: Every cross-package surface name maps to exactly one entry point in
#: this module; routes reach the same entry points via ROUTE_ENTRY_POINTS.
SURFACE_FUNCTIONS = {
    "pause.set_global": "set_global_pause",
    "pause.is_effective": "is_pause_effective",
    "service.status.get": "get_service_status",
    "service.check.run": "run_service_check",
    "apps.card.get": "get_apps_card",
    "automation.run.start": "start_run",
    "automation.trigger.fire": "fire_trigger",
    "automation.template.instantiate": "instantiate_template",
    "automation.launch": "launch",
    "automation.resume": "resume",
    "outage.signal": "signal_outage",
    "journal.append_event": "journal_append_event",
    "guard.check_escape": "guard_check_escape",
    "stop_all.request_stop": "stop_all_request_stop",
}


def set_global_pause(paused: bool, reason: str, session_token: Optional[str] = None) -> None:
    """Pause surface set_global: raise PAUSE_REASON_MISSING on empty reason."""
    ...


def is_pause_effective(project_id: str) -> bool:
    """Pause surface is_effective: global flag plus per-project flag."""
    ...


def get_service_status(service_id: str) -> ServiceStatus:
    """Service status get: raise SERVICE_NOT_FOUND for unknown services."""
    ...


def run_service_check(service_id: str, check: ServiceCheckKind, session_token: Optional[str] = None) -> ServiceStatus:
    """Service check run: raise SERVICE_CHECK_REFUSED for refused checks."""
    ...


def get_apps_card(project_id: str) -> AppsCardData:
    """Apps-card data: served stored facts only, never computed values."""
    ...


def start_run(project_id: str, template_id: str, session_token: Optional[str] = None) -> AutomationRun:
    """Automation run entry: checks pause, observes budget, records journal."""
    ...


def fire_trigger(project_id: str, trigger_id: str, session_token: Optional[str] = None) -> AutomationRun:
    """Automation trigger entry: raises AUTOMATION_PAUSED while effective."""
    ...


def instantiate_template(project_id: str, template_id: str, session_token: Optional[str] = None) -> AutomationTemplate:
    """Automation template entry: raises TEMPLATE_NOT_FOUND when unknown."""
    ...


def launch(project_id: str, run_id: str, session_token: Optional[str] = None) -> AutomationRun:
    """Automation launch entry: raises AUTOMATION_RUN_ACTIVE when active."""
    ...


def resume(project_id: str, run_id: str, session_token: Optional[str] = None) -> AutomationRun:
    """Automation resume entry: raises AUTOMATION_RUN_NOT_FOUND when unknown."""
    ...


def signal_outage(project_id: str, service_id: str, severity: str, summary: str, session_token: Optional[str] = None) -> OutageReport:
    """Outage one-stop-and-report signal via stop_all plus journal entries."""
    ...


def journal_append_event(project_id: str, source: str, kind: str, summary: str, refs: Tuple[str, ...]) -> JournalEntry:
    """Cross-lane reference: owned by the watcher lane, called, never built here."""
    ...


def guard_check_escape(project_id: str, path: str) -> bool:
    """Cross-lane reference: called before workspace writes, never built here."""
    ...


def stop_all_request_stop(project_id: str, reason: str) -> StopReceipt:
    """Cross-lane reference: stop-all lane receipt, called, never built here."""
    ...
