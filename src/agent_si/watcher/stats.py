"""Watcher stats: engine-held counters served by status (FXWATCH).

Counters live in the watcher engine lane (src/agent_si/watcher) and are
updated only inside the existing check loop: engine.tick records one
check per evaluated card plus alerts/fired per abnormal decision;
rules.evaluate records one model call plus tokens when the watcher
model answers. No new polling: status.get replays these counters plus
stored journal facts and live run/agent rows.
"""

from __future__ import annotations

from typing import Dict, Tuple

__all__ = (
    "record_tick",
    "record_model_call",
    "get_stats",
    "reset_state",
)

_CHECKS: Dict[str, int] = {}
_ALERTS: Dict[str, int] = {}
_LAST_CHECK: Dict[str, str] = {}
_CALLS: Dict[str, int] = {}
_TOKENS: Dict[str, int] = {}
_FIRED: Dict[str, Dict[str, int]] = {}


def _tokens_of(usage: object) -> int:
    try:
        data = dict(usage) if isinstance(usage, dict) else {}
    except Exception:
        return 0

    def _num(value: object) -> int:
        if isinstance(value, bool):
            return 0
        if isinstance(value, int) and value > 0:
            return value
        try:
            num = int(str(value))
        except (TypeError, ValueError):
            return 0
        return num if num > 0 else 0

    inp = _num(data.get("input_tokens")) or _num(data.get("prompt_tokens"))
    out = _num(data.get("output_tokens")) or _num(data.get("completion_tokens"))
    if inp or out:
        return int(inp + out)
    total = _num(data.get("total_tokens"))
    if total:
        return int(total)
    total = 0
    for key, value in data.items():
        try:
            if "token" in str(key).lower():
                total += _num(value)
        except Exception:
            continue
    return int(total)


def record_tick(project_id: str, checked_at: str,
                decisions: Tuple[Tuple[str, str], ...] = ()) -> None:
    """Record one engine pass: checks per card, alerts per journaled row.

    FXZERO R4: an unchanged repeat (no new row, repeat flag set) still
    counts into the per-rule fired tally: one condition, one alert,
    repeats counted on it. Two-tuples stay accepted (legacy callers).
    """
    key = str(project_id)
    items = tuple(decisions)
    _CHECKS[key] = int(_CHECKS.get(key, 0)) + len(items)
    fired = _FIRED.setdefault(key, {})
    alerts = 0
    for item in items:
        try:
            rule_id = str(item[0])
            journal_entry_id = str(item[1] or "")
            repeat = bool(item[2]) if len(item) > 2 else False
        except (IndexError, TypeError, AttributeError):
            continue
        if journal_entry_id:
            alerts += 1
            fired[rule_id] = int(fired.get(rule_id, 0)) + 1
        elif repeat:
            fired[rule_id] = int(fired.get(rule_id, 0)) + 1
    _ALERTS[key] = int(_ALERTS.get(key, 0)) + alerts
    _LAST_CHECK[key] = str(checked_at)


def record_model_call(project_id: str, usage: object = None) -> None:
    """Record one answered watcher-model call plus its tokens."""
    key = str(project_id)
    _CALLS[key] = int(_CALLS.get(key, 0)) + 1
    _TOKENS[key] = int(_TOKENS.get(key, 0)) + _tokens_of(usage)


def get_stats(project_id: str) -> Dict[str, object]:
    """Serve the engine-held counters for one project (never invented)."""
    key = str(project_id)
    return {
        "checks_done": int(_CHECKS.get(key, 0)),
        "alerts_raised": int(_ALERTS.get(key, 0)),
        "last_check_at": str(_LAST_CHECK.get(key, "")),
        "watcher_calls": int(_CALLS.get(key, 0)),
        "watcher_tokens": int(_TOKENS.get(key, 0)),
        "fired": dict(_FIRED.get(key, {})),
    }


def reset_state() -> None:
    """Drop all counters (probe isolation)."""
    _CHECKS.clear()
    _ALERTS.clear()
    _LAST_CHECK.clear()
    _CALLS.clear()
    _TOKENS.clear()
    _FIRED.clear()
