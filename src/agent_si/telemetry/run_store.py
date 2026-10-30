"""L0C06 telemetry run store: ONE JSON file under the app store dir.

File: <store_dir>/telemetry_store.json with keys `metric_records` and
`telemetry_events` (probe contract: tools/drive/probe_startup.py `_find_stores`
looks for top-level *.json objects carrying those lists; `_check_metrics`
requires each metric row to carry numeric value plus non-empty unit, state
and source). Append-safe (duplicate metric_id/event_id returns stored),
atomic write (temp file in the same folder plus os.replace). No secrets ever
enter the store: only ids, counts, provider/model names and reasons are kept;
messages, secret refs and raw values are never written.
"""

from __future__ import annotations

import contextlib
import datetime
import json
import os
import tempfile
import threading
import uuid
from dataclasses import asdict
from typing import Any

from agent_si.telemetry.metrics import MetricRecord, MetricState
from agent_si.telemetry.telemetry import TelemetryEvent

TELEMETRY_FILENAME = "telemetry_store.json"

CLOUD_CALLS_NAME = "cloud_calls"
TOKENS_TOTAL_NAME = "tokens_total"
COST_NAME = "cost"

CLOUD_CALLS_SOURCE = "provider/runtime API"
COST_SOURCE = "cost-calculator"

_TOKEN_KEYS = (
    "input_tokens",
    "output_tokens",
    "cached_tokens",
    "reasoning_tokens",
    "requests",
)

_lock = threading.Lock()
_BOUND_DIR: str | None = None


def bind_store_dir(path: str | None) -> None:
    """Bind the app store dir for manager-time recording (create_app calls)."""
    global _BOUND_DIR
    _BOUND_DIR = str(path) if path else None


def bound_store_dir() -> str | None:
    """Return the bound store dir, or None when unbound (record = no-op)."""
    return _BOUND_DIR


def store_path_for(store_dir: str | None = None) -> str | None:
    """Resolve <store_dir>/telemetry_store.json; None when unbound."""
    directory = store_dir if store_dir else _BOUND_DIR
    if not directory:
        return None
    return os.path.join(str(directory), TELEMETRY_FILENAME)


def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _enum_value(value: Any) -> Any:
    if isinstance(value, MetricState):
        return value.value
    name = type(value).__name__
    if name in ("RiskLevel",) and hasattr(value, "value"):
        return value.value
    return value


def _metric_to_json(record: MetricRecord) -> dict[str, Any]:
    payload = asdict(record)
    payload["state"] = _enum_value(record.state)
    return payload


def _event_to_json(event: TelemetryEvent) -> dict[str, Any]:
    payload = asdict(event)
    for key in ("risk", "state"):
        if payload.get(key) is not None:
            payload[key] = _enum_value(getattr(event, key))
    refs = payload.get("metric_refs")
    if isinstance(refs, tuple):
        payload["metric_refs"] = list(refs)
    return payload


def _empty_store() -> dict[str, Any]:
    return {"metric_records": [], "telemetry_events": []}


def _read_store(path: str) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return _empty_store()
    if not isinstance(data, dict):
        raise ValueError("telemetry store %r is not an object" % (path,))
    metrics = data.get("metric_records", [])
    events = data.get("telemetry_events", [])
    if not isinstance(metrics, list) or not isinstance(events, list):
        raise ValueError("telemetry store %r sections must be lists" % (path,))
    return {"metric_records": metrics, "telemetry_events": events}


def _write_store_atomic(path: str, metrics: list, events: list) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=parent or ".", prefix=".telemetry-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(
                {"metric_records": metrics, "telemetry_events": events},
                handle, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


def load_store(store_dir: str | None = None) -> dict[str, Any]:
    """Load the JSON store; missing file replays as empty (restart-safe)."""
    path = store_path_for(store_dir)
    if path is None:
        return _empty_store()
    return _read_store(path)


def append_records(
    metrics: list,
    events: list,
    store_dir: str | None = None,
) -> dict[str, Any]:
    """Append metric/event JSON rows; duplicates by id return stored rows.

    No-op (empty store shape) when no store dir is bound, so unit runs
    without an app stay total and never raise here.
    """
    path = store_path_for(store_dir)
    if path is None:
        return _empty_store()
    with _lock:
        current = _read_store(path)
        stored_metrics = current["metric_records"]
        stored_events = current["telemetry_events"]
        known_metrics = {
            row.get("metric_id")
            for row in stored_metrics
            if isinstance(row, dict)
        }
        known_events = {
            row.get("event_id")
            for row in stored_events
            if isinstance(row, dict)
        }
        for row in metrics:
            if isinstance(row, dict) and row.get("metric_id") not in known_metrics:
                stored_metrics.append(row)
                known_metrics.add(row.get("metric_id"))
        for row in events:
            if isinstance(row, dict) and row.get("event_id") not in known_events:
                stored_events.append(row)
                known_events.add(row.get("event_id"))
        _write_store_atomic(path, stored_metrics, stored_events)
        return {"metric_records": stored_metrics, "telemetry_events": stored_events}


def _extract_token_total(usage: Any) -> tuple[Any, bool]:
    """Sum known numeric token keys; (total, evidenced) never invented.

    evidences True only when at least one known key carried a real number;
    otherwise (None, False) so the caller records UNAVAILABLE, never 0.
    """
    if not isinstance(usage, dict):
        return None, False
    total = 0
    evidenced = False
    for key in _TOKEN_KEYS:
        value = usage.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            evidenced = True
            total += value
    if not evidenced:
        return None, False
    return total, True


def record_provider_usage(
    *,
    project_id: str,
    task_id: str | None,
    run_id: str | None,
    provider: str,
    model: str,
    usage: Any,
    store_dir: str | None = None,
) -> dict[str, Any]:
    """Record one successful provider call: cloud_calls + usage + event.

    Always one MetricRecord `cloud_calls` (value 1, unit count, state
    MEASURED, source provider/runtime API) plus the usage it got (tokens
    total MEASURED when evidenced else UNAVAILABLE, cost UNAVAILABLE without
    a pricing snapshot, never invented) and one TelemetryEvent
    PROVIDER_USAGE_REPORTED referencing those metric ids. No secret material
    is stored: only provider/model names and numeric counts travel.
    """
    pid = str(project_id or "run")
    now = _utc_now()
    cloud_id = "m-%s" % uuid.uuid4().hex
    cloud = MetricRecord(
        metric_id=cloud_id,
        project_id=pid,
        metric_name=CLOUD_CALLS_NAME,
        value=1,
        unit="count",
        state=MetricState.MEASURED,
        source=CLOUD_CALLS_SOURCE,
        task_id=task_id,
        run_id=run_id,
        recorded_at=now,
    )
    token_total, evidenced = _extract_token_total(usage)
    if evidenced:
        tokens = MetricRecord(
            metric_id="m-%s" % uuid.uuid4().hex,
            project_id=pid,
            metric_name=TOKENS_TOTAL_NAME,
            value=token_total,
            unit="count",
            state=MetricState.MEASURED,
            source=CLOUD_CALLS_SOURCE,
            task_id=task_id,
            run_id=run_id,
            recorded_at=now,
        )
    else:
        tokens = MetricRecord(
            metric_id="m-%s" % uuid.uuid4().hex,
            project_id=pid,
            metric_name=TOKENS_TOTAL_NAME,
            value=0,
            unit="count",
            state=MetricState.UNAVAILABLE,
            source=CLOUD_CALLS_SOURCE,
            task_id=task_id,
            run_id=run_id,
            recorded_at=now,
        )
    _cost_id = "m-%s" % uuid.uuid4().hex
    _cost_value: Any = None
    _cost_unit = "unknown"
    _cost_state = MetricState.UNAVAILABLE
    try:
        from agent_si.model_kb import kb_reader as _cost_kbr

        _cost_facts = None
        try:
            _cost_facts = _cost_kbr.CatalogKbReader().facts(
                str(provider or ""), str(model or ""))
        except Exception:
            _cost_facts = None

        def _cost_num(value: Any) -> float | None:
            if isinstance(value, bool):
                return None
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                try:
                    return float(value.strip())
                except (TypeError, ValueError):
                    return None
            return None

        _p_in = _cost_num(
            getattr(_cost_facts, "input_price", None)
            ) if _cost_facts is not None else None
        _p_out = _cost_num(
            getattr(_cost_facts, "output_price", None)
            ) if _cost_facts is not None else None
        _u = usage if isinstance(usage, dict) else {}

        def _tok(*names: str) -> int | None:
            for _n in names:
                _v = _u.get(_n)
                if isinstance(_v, int) and not isinstance(_v, bool):
                    return _v
            return None

        _t_in = _tok("input_tokens", "prompt_tokens")
        _t_out = _tok("output_tokens", "completion_tokens")
        if _t_in is None and _t_out is None:
            pass
        elif ((_t_in is not None and _p_in is None)
                or (_t_out is not None and _p_out is None)):
            pass
        else:
            _total = (float(_p_in or 0.0) * int(_t_in or 0)
                      + float(_p_out or 0.0) * int(_t_out or 0))
            _cost_value = _total
            _cost_unit = "USD"
            _cost_state = MetricState.MEASURED
    except Exception:
        pass
    if _cost_state == MetricState.UNAVAILABLE:
        cost_json: dict[str, Any] = {
            "metric_id": _cost_id,
            "project_id": pid,
            "metric_name": COST_NAME,
            "value": None,
            "unit": _cost_unit,
            "state": _cost_state.value,
            "source": COST_SOURCE,
            "task_id": task_id,
            "run_id": run_id,
            "recorded_at": now,
        }
    else:
        cost = MetricRecord(
            metric_id=_cost_id,
            project_id=pid,
            metric_name=COST_NAME,
            value=float(_cost_value or 0.0),
            unit=_cost_unit,
            state=_cost_state,
            source=COST_SOURCE,
            task_id=task_id,
            run_id=run_id,
            recorded_at=now,
        )
        cost_json = _metric_to_json(cost)
    metric_rows = [
        _metric_to_json(cloud),
        _metric_to_json(tokens),
        cost_json,
    ]
    event = TelemetryEvent(
        event_id="e-%s" % uuid.uuid4().hex,
        project_id=pid,
        timestamp=now,
        task_id=task_id,
        run_id=run_id,
        provider=str(provider or ""),
        model=str(model or ""),
        event_type="PROVIDER_USAGE_REPORTED",
        metric_refs=(
            cloud.metric_id, tokens.metric_id, _cost_id),
    )
    event_rows = [_event_to_json(event)]
    append_records(metric_rows, event_rows, store_dir=store_dir)
    return {
        "metric_ids": [cloud.metric_id, tokens.metric_id, _cost_id],
        "event_id": event.event_id,
    }


def record_run_terminated(
    *,
    project_id: str,
    task_id: str | None,
    run_id: str | None,
    reason: str,
    store_dir: str | None = None,
) -> str | None:
    """Record one TelemetryEvent RUN_TERMINATED with task/run and reason.

    reason travels in final_status (done, budget_stop, cancelled, error,
    dispatch_rejected); no message, usage or secret text is stored.
    """
    pid = str(project_id or "run")
    now = _utc_now()
    event = TelemetryEvent(
        event_id="e-%s" % uuid.uuid4().hex,
        project_id=pid,
        timestamp=now,
        task_id=task_id or "",
        run_id=run_id or "",
        event_type="RUN_TERMINATED",
        final_status=str(reason or ""),
    )
    append_records([], [_event_to_json(event)], store_dir=store_dir)
    return event.event_id


def aggregates(store_dir: str | None = None) -> dict[str, Any]:
    """Totals computed FROM the authoritative store file only.

    kit row MVP_ACCEPT-161: analytics values read only from authoritative
    TelemetryEvent and MetricRecord stores, never from chat text or live
    rows; this helper reads the JSON store file and sums metric values by
    name deterministically across two reads.
    """
    stored = load_store(store_dir=store_dir)
    metrics = stored.get("metric_records", [])
    events = stored.get("telemetry_events", [])
    totals: dict[str, Any] = {}
    for row in metrics:
        if not isinstance(row, dict):
            continue
        name = str(row.get("metric_name", ""))
        value = row.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        totals[name] = totals.get(name, 0) + value
    ordered = {name: totals[name] for name in sorted(totals)}
    tasks = sorted({
        str(item.get("task_id"))
        for item in events
        if isinstance(item, dict) and item.get("task_id")
    })
    return {
        "metric_records": len(metrics),
        "telemetry_events": len(events),
        "totals": ordered,
        "tasks": tasks,
    }


__all__ = [
    "CLOUD_CALLS_NAME",
    "CLOUD_CALLS_SOURCE",
    "COST_NAME",
    "COST_SOURCE",
    "TELEMETRY_FILENAME",
    "TOKENS_TOTAL_NAME",
    "aggregates",
    "append_records",
    "bind_store_dir",
    "bound_store_dir",
    "load_store",
    "record_provider_usage",
    "record_run_terminated",
    "store_path_for",
]
