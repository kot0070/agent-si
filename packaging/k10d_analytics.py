"""K10D analytics seam: deterministic views over the authoritative stores.

Rows covered: B0B-UNCOVERED_MVP_ACCEPT-158, -160, -161, -172, -129.
Every value here is derived from TelemetryEvent plus MetricRecord store
rows (the JSON telemetry store file); nothing is read from chat text or
from live in-memory rows, and no number is ever invented: unevidenced
tokens or cost report as UNAVAILABLE, never zero. stdlib only, no network,
no providers, no I/O inside these helpers (callers load the store file).
Deterministic: all outputs are sorted by key.
"""

from __future__ import annotations

UNAVAILABLE = "UNAVAILABLE"

K10D_TEST_FILE = "tests/test_k10d_served.py"

_ROUTES = {
    "B0B-UNCOVERED_MVP_ACCEPT-158":
        "GET /api/v1/analytics/telemetry deterministic totals",
    "B0B-UNCOVERED_MVP_ACCEPT-160":
        "packaging/k10d_analytics.py by_model_provider seam",
    "B0B-UNCOVERED_MVP_ACCEPT-161":
        "GET /api/v1/analytics/telemetry authoritative stores",
    "B0B-UNCOVERED_MVP_ACCEPT-172":
        "tests/fixtures/k10d_fixtures.json TEST FIXTURES seam",
    "B0B-UNCOVERED_MVP_ACCEPT-129":
        "docs/reports/K10D.md command index + "
        "tools/start.py k10d_command_index seam",
}

_TESTS = {
    "B0B-UNCOVERED_MVP_ACCEPT-158":
        "test_k10d_158_totals_deterministic",
    "B0B-UNCOVERED_MVP_ACCEPT-160":
        "test_k10d_160_per_model_provider",
    "B0B-UNCOVERED_MVP_ACCEPT-161":
        "test_k10d_161_authoritative_only",
    "B0B-UNCOVERED_MVP_ACCEPT-172":
        "test_k10d_172_fixture_rows_labelled",
    "B0B-UNCOVERED_MVP_ACCEPT-129":
        "test_k10d_129_command_index",
}


def served_rows_k10d() -> list:
    """Return the K10D served map: one entry per open K10D row."""
    rows = []
    for row_id in sorted(_ROUTES):
        rows.append(
            {
                "row": row_id,
                "route": _ROUTES[row_id],
                "test": "%s::%s" % (K10D_TEST_FILE, _TESTS[row_id]),
            }
        )
    return rows


def authoritative_origins() -> dict:
    """Allowed versus refused analytics origins for row -161."""
    return {
        "allowed": ["metric-records-store", "telemetry-events-store"],
        "refused": ["chat-text", "live-rows"],
    }


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def totals_from_stores(metrics: list, events: list) -> dict:
    """Deterministic totals summed from store rows only (row -158)."""
    totals: dict = {}
    for row in metrics:
        if not isinstance(row, dict):
            continue
        value = row.get("value")
        if not _is_number(value):
            continue
        name = str(row.get("metric_name", ""))
        totals[name] = totals.get(name, 0) + value
    tasks = sorted(
        {
            str(item.get("task_id"))
            for item in events
            if isinstance(item, dict) and item.get("task_id")
        }
    )
    return {
        "metric_records": len(metrics),
        "telemetry_events": len(events),
        "totals": {name: totals[name] for name in sorted(totals)},
        "tasks": tasks,
    }


def _measured_amount(row: dict | None) -> tuple:
    """Return (value, evidenced) for one linked metric row."""
    if not isinstance(row, dict):
        return None, False
    if row.get("state") != "MEASURED":
        return None, False
    value = row.get("value")
    if not _is_number(value):
        return None, False
    return value, True


def by_model_provider(snapshot: dict) -> dict:
    """Per-model and per-provider calls plus tokens plus cost (row -160).

    Groups PROVIDER_USAGE_REPORTED events by (provider, model) via their
    linked metric rows. Tokens or cost with no MEASURED numeric row
    report as UNAVAILABLE, never zero.
    """
    metrics = snapshot.get("metric_records", [])
    events = snapshot.get("telemetry_events", [])
    by_id = {
        row.get("metric_id"): row
        for row in metrics
        if isinstance(row, dict) and row.get("metric_id")
    }
    groups: dict = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("event_type") != "PROVIDER_USAGE_REPORTED":
            continue
        key = (str(event.get("provider", "")), str(event.get("model", "")))
        slot = groups.setdefault(
            key, {"calls": 0, "tokens": 0, "tokens_hit": False,
                  "cost": 0.0, "cost_hit": False})
        slot["calls"] += 1
        refs = event.get("metric_refs", [])
        for ref in refs if isinstance(refs, list) else []:
            linked = by_id.get(ref)
            if not isinstance(linked, dict):
                continue
            name = str(linked.get("metric_name", ""))
            if name == "tokens_total":
                value, hit = _measured_amount(linked)
                if hit:
                    slot["tokens"] += value
                    slot["tokens_hit"] = True
            elif name == "cost":
                value, hit = _measured_amount(linked)
                if hit:
                    slot["cost"] += float(value)
                    slot["cost_hit"] = True
    per_model = []
    for provider, model in sorted(groups):
        slot = groups[(provider, model)]
        per_model.append(
            {
                "provider": provider,
                "model": model,
                "calls": slot["calls"],
                "tokens": slot["tokens"] if slot["tokens_hit"]
                else UNAVAILABLE,
                "cost": slot["cost"] if slot["cost_hit"] else UNAVAILABLE,
            }
        )
    providers: dict = {}
    for provider, model in sorted(groups):
        slot = groups[(provider, model)]
        agg = providers.setdefault(
            provider, {"calls": 0, "tokens": 0, "tokens_hit": False,
                       "cost": 0.0, "cost_hit": False})
        agg["calls"] += slot["calls"]
        if slot["tokens_hit"]:
            agg["tokens"] += slot["tokens"]
            agg["tokens_hit"] = True
        if slot["cost_hit"]:
            agg["cost"] += float(slot["cost"])
            agg["cost_hit"] = True
    per_provider = [
        {
            "provider": provider,
            "calls": providers[provider]["calls"],
            "tokens": providers[provider]["tokens"]
            if providers[provider]["tokens_hit"] else UNAVAILABLE,
            "cost": providers[provider]["cost"]
            if providers[provider]["cost_hit"] else UNAVAILABLE,
        }
        for provider in sorted(providers)
    ]
    return {"per_model": per_model, "per_provider": per_provider}


def verify_totals_against_store(reported: dict, snapshot: dict) -> dict:
    """Accept totals only when they equal the store recomputation.

    Row -161 guard: invented numbers that are not in the store raise
    ValueError instead of being served.
    """
    metrics = snapshot.get("metric_records", [])
    events = snapshot.get("telemetry_events", [])
    honest = totals_from_stores(metrics, events)["totals"]
    if dict(reported) != dict(honest):
        raise ValueError(
            "reported totals %r do not match store totals %r"
            % (reported, honest)
        )
    return dict(honest)


def validate_fixture_rows(rows: list) -> list:
    """Accept fixture rows only when labelled TEST FIXTURES (row -172).

    Every row must carry label TEST FIXTURES plus non-empty provenance
    stating it is never measured evidence; anything else raises
    ValueError so unlabelled rows can never pass as evidence.
    """
    if not isinstance(rows, list) or not rows:
        raise ValueError("fixture rows must be a non-empty list")
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("fixture row must be an object: %r" % (row,))
        if row.get("label") != "TEST FIXTURES":
            raise ValueError(
                "fixture row %r is not labelled TEST FIXTURES" % (row,)
            )
        provenance = row.get("provenance", "")
        if not provenance or "never measured evidence" not in str(provenance):
            raise ValueError(
                "fixture row %r lacks provenance" % (row,)
            )
    return list(rows)
