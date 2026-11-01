"""K07NEXT5 served boundary: 4 open K07 rows as JSON routes.

Every GET route is an open read and returns a deterministic
server-shaped JSON document; the POST route enforces the frozen
USER_WRITE guard (401 missing x-actor, 403 bad token, exactly like
the chat_stream handler in backend/app.py and the console project
write routes). All routes are registered by mount() onto the real
create_app() app with app.py untouched. Row contracts are quoted
from the repo ground truth named in each function docstring.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from agent_si.backend.console_projects_write import (
    _enforce_user_write as _require_user_write,
)
from agent_si.backend.local_connect import list_models
from agent_si.backend.localbench_routes import (
    check_route,
    estimate_route,
    history_route,
    results_route,
    scan_route,
)
from agent_si.budget.observe import map_service_status
from agent_si.local import config as local_config
from agent_si.local.bench_protocol import build_prestart_warnings

#: Registry health order asserted by the outage fixture row: the
#: provider walks ONLINE into DEGRADED into OFFLINE into UNKNOWN.
_TRANSITION_ORDER = ("ONLINE", "DEGRADED", "OFFLINE", "UNKNOWN")

_VALID_LEVELS = ("Quick", "Standard", "Deep")


def _decision_body(request_body: Any) -> dict[str, Any]:
    if not isinstance(request_body, dict):
        raise HTTPException(
            status_code=400, detail="write needs a JSON object body")
    project_key = request_body.get("project_key")
    patch = request_body.get("patch")
    statement = request_body.get("statement")
    reason = request_body.get("reason")
    authority = request_body.get("authority")
    if not (isinstance(project_key, str) and project_key.strip()):
        raise HTTPException(
            status_code=400, detail="project_key is required")
    if not isinstance(patch, dict):
        raise HTTPException(
            status_code=400, detail="patch must be an object")
    for key in patch:
        if key not in local_config.EXPLICIT_CONFIG_FIELDS:
            raise HTTPException(
                status_code=400,
                detail="patch key %r is not an explicit config field" % (key,))
    for field_name, value in (
            ("statement", statement), ("reason", reason),
            ("authority", authority)):
        if not (isinstance(value, str) and value.strip()):
            raise HTTPException(
                status_code=400,
                detail="decision record fields are required")
    return {
        "project_key": project_key.strip(),
        "patch": patch,
        "statement": statement.strip(),
        "reason": reason.strip(),
        "authority": authority.strip(),
    }


async def local_ai_decision_update(request: Request) -> dict[str, Any]:
    """Row 111-UI: local-AI settings write carries its decision record.

    Quoted from src/agent_si/local/config.py (update_config refuses a
    missing decision with LOCAL_AI_DECISION_RECORD_REQUIRED; save_config
    persists the validated config; record_decision builds the per-change
    record): the guarded write stores the patch with its decision_id and
    the read leg below serves it back.
    """
    _require_user_write(request)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(
            status_code=400, detail="write needs a JSON body") from None
    fields = _decision_body(body)
    decision = local_config.record_decision(
        fields["project_key"], fields["statement"],
        fields["reason"], fields["authority"])
    try:
        stored = local_config.update_config(
            fields["project_key"], fields["patch"], decision)
    except local_config.LocalAISettingsError as exc:
        if exc.code != local_config.LOCAL_AI_CONFIG_NOT_FOUND:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        config = local_config.LocalAIConfig(
            project_key=fields["project_key"],
            endpoint_url=fields["patch"].get(
                "endpoint_url", "http://127.0.0.1:11434"),
            model_id=fields["patch"].get("model_id", "llama3.1:8b"),
            permission_scope=fields["patch"].get(
                "permission_scope", "local-contact-allowed"),
            local_only_mode=bool(fields["patch"].get("local_only_mode", False)),
        )
        try:
            stored = local_config.save_config(config, decision)
        except local_config.LocalAISettingsError as save_exc:
            raise HTTPException(
                status_code=400, detail=str(save_exc)) from save_exc
    return {
        "row": "111-UI",
        "decision_id": decision.decision_id,
        "config": {
            "project_key": stored.project_key,
            "endpoint_url": stored.endpoint_url,
            "model_id": stored.model_id,
            "permission_scope": stored.permission_scope,
            "local_only_mode": stored.local_only_mode,
        },
    }


async def local_ai_view(request: Request) -> dict[str, Any]:
    """Row 111-UI read leg: the settings view over the stored config.

    Quoted from src/agent_si/local/config.py (get_local_ai_view serves
    the stored config to the K07 settings.localAi view; load_config
    enforces the project-scope guard): the view carries the frozen
    title key plus the stored config, so the write above reads back.
    """
    project_key = request.query_params.get("project_key", "")
    try:
        view = local_config.get_local_ai_view(project_key, project_key)
    except local_config.LocalAISettingsError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "row": "111-UI",
        "project_key": view.project_key,
        "title_key": view.title_key,
        "purpose_key": view.purpose_key,
        "need_it_now_key": view.need_it_now_key,
        "config": {
            "project_key": view.config.project_key,
            "endpoint_url": view.config.endpoint_url,
            "model_id": view.config.model_id,
            "permission_scope": view.config.permission_scope,
            "local_only_mode": view.config.local_only_mode,
        },
    }


async def bench_tab(request: Request) -> dict[str, Any]:
    """Row R-341-UI: benchmark settings tab over the K05 bench entries.

    Quoted from src/agent_si/backend/localbench_routes.py (scan_route
    allowlist-first read-only scan, estimate_route nominal-calibration
    estimate, results_route recorded rows, history_route known run ids,
    check_route passive gateway check) plus
    src/agent_si/local/bench_protocol.py (build_prestart_warnings:
    duration + PC-load + do-not-use-PC pre-start warnings): the tab
    carries path scan, level estimate with duration, warnings and
    per-model results in one document.
    """
    params = request.query_params
    model_id = params.get("model_id", "")
    level = params.get("level", "Quick")
    if level not in _VALID_LEVELS:
        raise HTTPException(
            status_code=400, detail="unknown bench level: %r" % (level,))
    if not model_id:
        raise HTTPException(
            status_code=400, detail="model_id is required")
    path = params.get("path", "")
    allowlist = [entry for entry in params.get("allowlist", "").split(",")
                 if entry]
    if not path:
        models: list[str] = []
    else:
        from agent_si.local.bench_runner import BenchRefusedError

        try:
            models = scan_route(allowlist, path)
        except BenchRefusedError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
    try:
        estimate = estimate_route(model_id, level)  # type: ignore[arg-type]
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    pc_in_use = params.get("pc_in_use", "") == "1"
    warnings = build_prestart_warnings(estimate, pc_in_use)
    run_id = params.get("run_id", "")
    rows = results_route(run_id)
    by_model: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_model.setdefault(row.model_id, []).append(asdict(row))
    gateway = check_route(params.get("endpoint", ""))
    return {
        "row": "R-341-UI",
        "scan": models,
        "estimate": {
            "model_id": estimate.model_id,
            "level": estimate.level.value,
            "minutes_min": estimate.minutes_min,
            "minutes_max": estimate.minutes_max,
        },
        "warnings": [
            {"code": warning.code, "message": warning.message}
            for warning in warnings
        ],
        "results": [asdict(row) for row in rows],
        "results_by_model": by_model,
        "history": history_route(),
        "gateway": asdict(gateway),
    }


async def local_ai_settings_view(request: Request) -> dict[str, Any]:
    """Row B0B-UNCOVERED_ARCH-526: Local AI view of the stored config.

    Quoted from src/agent_si/local/config.py (get_local_ai_view serves
    the stored LocalAIConfig as a LocalAISettingsView) plus
    src/agent_si/backend/local_connect.py (list_models reads the known
    local models): the view presents the stored config, the local
    endpoint and the models together.
    """
    project_key = request.query_params.get("project_key", "")
    try:
        view = local_config.get_local_ai_view(project_key, project_key)
    except local_config.LocalAISettingsError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "row": "B0B-UNCOVERED_ARCH-526",
        "project_key": view.project_key,
        "title_key": view.title_key,
        "purpose_key": view.purpose_key,
        "need_it_now_key": view.need_it_now_key,
        "config": {
            "project_key": view.config.project_key,
            "endpoint_url": view.config.endpoint_url,
            "model_id": view.config.model_id,
            "permission_scope": view.config.permission_scope,
            "local_only_mode": view.config.local_only_mode,
        },
        "endpoint_url": view.config.endpoint_url,
        "models": [asdict(row) for row in list_models()],
    }


async def provider_health_transitions(request: Request) -> dict[str, Any]:
    """Row B0B-UNCOVERED_MVP_ACCEPT-199: outage health transitions.

    Quoted from src/agent_si/budget/observe.py (map_service_status:
    ONLINE maps UP, DEGRADED stays, OFFLINE maps DOWN, UNKNOWN maps DOWN
    with reason unknown-health, fail-closed): the outage fixture walks
    the registry ONLINE into UNKNOWN and asserts the provider service
    transitions UP into DEGRADED into DOWN.
    """
    del request
    rows = []
    for registry_status in _TRANSITION_ORDER:
        service, reason = map_service_status(registry_status)
        rows.append({
            "registry": registry_status,
            "service": service,
            "reason": reason,
        })
    return {
        "row": "B0B-UNCOVERED_MVP_ACCEPT-199",
        "rows": rows,
        "transitions": [row["service"] for row in rows],
    }


ROUTES = (
    ("post", "/api/v1/app/local-ai/decision-update",
     "local_ai_decision_update", local_ai_decision_update),
    ("get", "/api/v1/app/local-ai/view",
     "local_ai_view", local_ai_view),
    ("get", "/api/v1/app/bench/tab",
     "bench_tab", bench_tab),
    ("get", "/api/v1/app/local-ai/settings-view",
     "local_ai_settings_view", local_ai_settings_view),
    ("get", "/api/v1/app/provider-health/transitions",
     "provider_health_transitions", provider_health_transitions),
)


def mount(app: FastAPI) -> FastAPI:
    """Register every K07NEXT5 served route on the real FastAPI app.

    App.py stays untouched; the caller passes the create_app() app.
    Returns the app for chaining.
    """
    for method, path, name, fn in ROUTES:
        registrar = getattr(app, method)
        registrar(path, name="k07next5_" + name)(fn)
    return app
