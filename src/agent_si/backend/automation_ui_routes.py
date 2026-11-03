"""FXAUTO served Automations page surface (separate UI router).

New routes for the Settings > Automations screen. They live on their own
``ui_router`` so the frozen ``automation_routes.router`` keeps covering
``HTTP_ROUTES`` exactly (see test_router_covers_http_routes_exactly) and
the frozen ``automation/interface.py`` is untouched. Reads are open;
writes need a live session token (``SESSION_TOKEN_MISSING`` -> 401,
``SESSION_TOKEN_INVALID`` -> 403), mirroring automation_routes.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, HTTPException, Request

from agent_si.automation import pause, runner, rules, scheduler, templates
from agent_si.automation import triggers

_IFACE_MODULE = "agent_si.automation.interface"


def _auto_iface():
    try:
        return sys.modules[_IFACE_MODULE]
    except KeyError:
        import agent_si.automation.interface as _mod

        return _mod


ui_router = APIRouter()

_auth_hook: Optional[Callable[[str], bool]] = None
_rate_hook: Optional[Callable[[str], bool]] = None


def configure(
    auth_hook: Optional[Callable[[str], bool]] = None,
    rate_hook: Optional[Callable[[str], bool]] = None,
) -> Dict[str, Any]:
    """Install composition-root hooks (same owners as automation_routes)."""
    global _auth_hook, _rate_hook
    _auth_hook = auth_hook
    _rate_hook = rate_hook
    return {"auth_hook": _auth_hook is not None,
            "rate_hook": _rate_hook is not None}


def token_live(token: Optional[str]) -> bool:
    """True only when the configured auth hook accepts the token."""
    return (
        _auth_hook is not None
        and isinstance(token, str)
        and bool(token)
        and bool(_auth_hook(token))
    )


_STATUS_BY_CODE: Dict[str, int] = {
    "SESSION_TOKEN_MISSING": 401,
    "SESSION_TOKEN_INVALID": 403,
    "TRIGGER_NOT_FOUND": 404,
    "AUTOMATION_RUN_NOT_FOUND": 404,
    "TEMPLATE_NOT_FOUND": 404,
    "AUTOMATION_PAUSED": 409,
    "INVALID_RULE": 400,
}


def _fail(code: str, detail: str = "") -> None:
    raise HTTPException(
        status_code=_STATUS_BY_CODE.get(code, 400),
        detail={"code": code, "detail": detail},
    )


def _automation_error(err: Any) -> None:
    _fail(str(getattr(err, "code", "INVALID_RULE") or "INVALID_RULE"),
          str(getattr(err, "detail", "") or ""))


async def _body(request: Request) -> Dict[str, Any]:
    try:
        data = await request.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _token_of(request: Request, data: Dict[str, Any]) -> Optional[str]:
    header = request.headers.get("x-ui-session-token")
    if isinstance(header, str) and header:
        return header
    value = data.get("session_token")
    if isinstance(value, str) and value:
        return value
    return None


def _guard_post(request: Request, data: Dict[str, Any]) -> str:
    token = _token_of(request, data)
    if token is None:
        _fail("SESSION_TOKEN_MISSING", "POST needs a live session token")
        raise AssertionError("unreachable")
    if not token_live(token):
        _fail("SESSION_TOKEN_INVALID", "unknown session token")
        raise AssertionError("unreachable")
    if _rate_hook is not None:
        try:
            allowed = bool(_rate_hook(token))
        except Exception:
            allowed = False
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail={"code": "RATE_LIMITED", "detail": "rate hook refused"},
            )
    return token


def _iso(epoch: Any) -> Optional[str]:
    try:
        stamp = float(epoch)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(stamp, tz=timezone.utc).isoformat().replace(
        "+00:00", "Z")


def _rule_row(rule: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "rule_id": rule["rule_id"],
        "name": rule["name"],
        "project_id": rule["project_id"],
        "when_kind": rule["when_kind"],
        "when_detail": rule["when_detail"],
        "if_text": rule.get("if_text", ""),
        "do": rule["do"],
        "miss": rule["miss"],
        "enabled": bool(rule.get("enabled", True)),
        "next_run_at": _iso(rule.get("next_run_at")),
        "last_run_id": rule.get("last_run_id"),
    }


#: Builder drafts for the six pre-plan service templates (Use fills the
#: builder; nothing runs until Save). Plan templates carry their own
#: drafts in templates.TEMPLATE_UI.
_SIX_DRAFTS: Dict[str, Dict[str, str]] = {
    "tpl-nightly": {
        "when_kind": "schedule", "when_detail": "daily-22:00",
        "do": "notify", "miss": "once",
    },
    "tpl-healthcheck": {
        "when_kind": "schedule", "when_detail": "every-3h",
        "do": "notify", "miss": "once",
    },
    "tpl-container-audit": {
        "when_kind": "schedule", "when_detail": "every-3h",
        "do": "notify", "miss": "once",
    },
    "tpl-usage-report": {
        "when_kind": "schedule", "when_detail": "every-3h",
        "do": "notify", "miss": "once",
    },
    "tpl-watch-sweep": {
        "when_kind": "schedule", "when_detail": "every-30m",
        "do": "notify", "miss": "once",
    },
    "tpl-outage-drill": {
        "when_kind": "event", "when_detail": "app-started",
        "do": "notify", "miss": "once",
    },
}


def _template_row(template_id: str) -> Dict[str, Any]:
    spec = templates._lookup(template_id)
    meta = templates.TEMPLATE_UI.get(template_id)
    if meta is not None:
        trigger_key = str(meta["trigger_key"])
        action_key = str(meta["action_key"])
        draft = dict(meta["draft"])
    else:
        trigger_key = "fxauto.chips.onDemand"
        action_key = "fxauto.chips.notify"
        six = _SIX_DRAFTS.get(template_id, {
            "when_kind": "schedule", "when_detail": "every-3h",
            "do": "notify", "miss": "once",
        })
        draft = {"if_text": "", **six}
    return {
        "template_id": template_id,
        "name": str(spec.get("name", template_id)),
        "description": str(spec.get("description", "")),
        "trigger_key": trigger_key,
        "action_key": action_key,
        "draft": draft,
    }


@ui_router.get("/api/v1/automations/rules")
def ui_list_rules(project_id: str) -> Any:
    """List automation rules for one project (open)."""
    return {"rules": [_rule_row(rule)
                      for rule in rules.list_rules(project_id)]}


@ui_router.post("/api/v1/automations/rules")
async def ui_create_rule(request: Request) -> Any:
    """Create a rule from the builder draft (token)."""
    data = await _body(request)
    _guard_post(request, data)
    project_id = data.get("project_id", "")
    if not isinstance(project_id, str) or not project_id:
        _fail("INVALID_RULE", "project_id is required")
        raise AssertionError("unreachable")
    try:
        rule = rules.create_rule(
            project_id,
            str(data.get("name", "")),
            str(data.get("when_kind", "")),
            str(data.get("when_detail", "")),
            if_text=str(data.get("if_text", "")),
            do=str(data.get("do", "notify")),
            miss=str(data.get("miss", "once")),
            enabled=bool(data.get("enabled", True)),
        )
    except ValueError as exc:
        _fail("INVALID_RULE", str(exc))
        raise AssertionError("unreachable")
    except _auto_iface().AutomationError as err:
        _automation_error(err)
        raise AssertionError("unreachable")
    current = rules.get_rule(project_id, rule["rule_id"])
    current["next_run_at"] = next(
        (row.get("next_run_at")
         for row in rules.list_rules(project_id)
         if row["rule_id"] == rule["rule_id"]),
        None,
    )
    return {"rule": _rule_row(current)}


@ui_router.put("/api/v1/automations/rules/{rule_id}")
async def ui_set_rule(rule_id: str, request: Request) -> Any:
    """Flip a rule off/on (token)."""
    data = await _body(request)
    _guard_post(request, data)
    project_id = data.get("project_id", "")
    if not isinstance(project_id, str) or not project_id:
        _fail("INVALID_RULE", "project_id is required")
        raise AssertionError("unreachable")
    try:
        rule = rules.set_enabled(
            project_id, rule_id, bool(data.get("enabled", True)))
    except _auto_iface().AutomationError as err:
        _automation_error(err)
        raise AssertionError("unreachable")
    return {"rule": _rule_row(rule)}


@ui_router.post("/api/v1/automations/rules/{rule_id}/run")
async def ui_run_rule(rule_id: str, request: Request) -> Any:
    """Run now: fire a rule, execute its DO or open an approval (token)."""
    data = await _body(request)
    _guard_post(request, data)
    project_id = data.get("project_id", "")
    if not isinstance(project_id, str) or not project_id:
        _fail("INVALID_RULE", "project_id is required")
        raise AssertionError("unreachable")
    try:
        fired = rules.fire_rule(project_id, rule_id, reason="manual")
    except _auto_iface().AutomationError as err:
        _automation_error(err)
        raise AssertionError("unreachable")
    return {
        "run": fired["run"],
        "result": fired["result"],
        "approval": fired["approval"],
    }


@ui_router.get("/api/v1/automations/runs")
def ui_list_runs(project_id: str) -> Any:
    """Recorded automation runs: time, rule, state, plain result (open)."""
    rows = []
    for row in rules.run_history(project_id):
        rows.append({
            "run_id": row["run_id"],
            "time": _iso(row["time"]),
            "rule": row["rule"],
            "state": row["state"],
            "result": row["result"],
        })
    return {"runs": rows}


@ui_router.get("/api/v1/automations/templates")
def ui_list_templates() -> Any:
    """Plan templates first, then the service presets (open)."""
    return {"templates": [_template_row(template_id)
                          for template_id in templates.list_templates()]}


@ui_router.get("/api/v1/automations/checkpoints")
def ui_list_checkpoints(project_id: str) -> Any:
    """Checkpoints written by automations, latest first (open)."""
    rows = rules.checkpoints(project_id)
    out = []
    for row in rows:
        out.append({
            "checkpoint_id": row["checkpoint_id"],
            "time": row["time"],
            "digest": row["digest"],
            "rule": row["rule"],
            "run_id": row["run_id"],
        })
    latest = out[0] if out else None
    return {"checkpoints": out, "latest": latest}


@ui_router.post("/api/v1/automations/checkpoints/{checkpoint_id}/resume")
async def ui_resume_checkpoint(checkpoint_id: str,
                               request: Request) -> Any:
    """Resume the run behind a checkpoint within budget and time guards."""
    data = await _body(request)
    _guard_post(request, data)
    project_id = data.get("project_id", "")
    if not isinstance(project_id, str) or not project_id:
        _fail("INVALID_RULE", "project_id is required")
        raise AssertionError("unreachable")
    run_id = rules.checkpoint_run(project_id, checkpoint_id)
    if run_id is None:
        _fail("AUTOMATION_RUN_NOT_FOUND",
              "no running run for this checkpoint")
        raise AssertionError("unreachable")
    try:
        resumed = runner.resume(project_id, run_id)
    except _auto_iface().AutomationError as err:
        _automation_error(err)
        raise AssertionError("unreachable")
    return {
        "checkpoint_id": checkpoint_id,
        "run_id": resumed.run_id,
        "state": resumed.state,
    }


@ui_router.get("/api/v1/automations/pause/project")
def ui_get_project_pause(project_id: str) -> Any:
    """Per-project automation switch state (open)."""
    return {"project_id": project_id,
            "paused": bool(pause.get_project(project_id))}


@ui_router.post("/api/v1/automations/pause/project")
async def ui_set_project_pause(request: Request) -> Any:
    """Flip the per-project automation switch (token)."""
    data = await _body(request)
    _guard_post(request, data)
    project_id = data.get("project_id", "")
    if not isinstance(project_id, str) or not project_id:
        _fail("INVALID_RULE", "project_id is required")
        raise AssertionError("unreachable")
    pause.set_project(project_id, bool(data.get("paused", False)))
    return {"project_id": project_id,
            "paused": bool(pause.get_project(project_id))}


@ui_router.get("/api/v1/automations/approvals")
def ui_list_approvals(project_id: str) -> Any:
    """Approval requests for strong rule actions, pending first (open)."""
    return {"approvals": rules.list_approvals(project_id)}


@ui_router.post("/api/v1/automations/approvals/{approval_id}")
async def ui_decide_approval(approval_id: str, request: Request) -> Any:
    """Approve or reject a pending strong action (token)."""
    data = await _body(request)
    _guard_post(request, data)
    project_id = data.get("project_id", "")
    if not isinstance(project_id, str) or not project_id:
        _fail("INVALID_RULE", "project_id is required")
        raise AssertionError("unreachable")
    try:
        decided = rules.decide_approval(
            project_id, approval_id, bool(data.get("approved", False)))
    except _auto_iface().AutomationError as err:
        _automation_error(err)
        raise AssertionError("unreachable")
    return {"approval": decided}


@ui_router.get("/api/v1/automations/triggers")
def ui_list_triggers(project_id: str) -> Any:
    """Trigger rows behind the rules, for the on/off audit trail (open)."""
    return {"triggers": [dict(row) for row in
                         triggers.list_triggers(project_id)]}
