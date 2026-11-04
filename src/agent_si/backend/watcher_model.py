"""Bind the Watcher to the model pinned on the watcher role (PLANB W4).

The role editor saves the Watcher model through PUT /api/v1/roles/pools
(role "watcher"). Before a rule evaluation the route calls ``bind``: it
reads that stored profile, resolves it the way every other role does and
hands rules.configure_watcher_model one transport that makes the real
model call. No pinned watcher profile means no transport: Rules only.
"""

from __future__ import annotations

import json
from typing import Any

_PICK_PROMPT = (
    "You are the Watcher of a software build. Rule %s fired off its resting "
    "state. Choose the one action to take. Allowed actions:\n%s\n"
    "Reply ONLY with JSON like {\"pick\": 0} where pick is the number of "
    "the allowed action. No other text."
)


_BOUND: dict = {"transport": None}


def _display_model(provider: str, model: str) -> str:
    prefix = "%s/" % (provider,)
    return model[len(prefix):] if model.startswith(prefix) else model


def _parse_pick(text: Any, count: int) -> int | None:
    raw = str(text or "")
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(raw[start:end + 1]).get("pick")
    except Exception:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 0 <= value < count else None


def _make_transport(app: Any, resolution: dict) -> Any:
    from agent_si.runtime.devrun import roles as _roles

    local = str(resolution["provider"]) in _roles._LOCAL_LEG_IDS

    def _transport(model_name: str, rule_id: str, allowed: tuple) -> dict:
        adapter = _roles.build_adapter(app, resolution)
        listing = "\n".join(
            "%d: %s %s" % (index, action[0], " ".join(action[1]))
            for index, action in enumerate(allowed))
        messages = [{"role": "user",
                     "content": _PICK_PROMPT % (rule_id, listing)}]
        response = _roles.invoke_timed(
            adapter, messages,
            timeout_s=_roles._LOCAL_CALL_TIMEOUT_S if local else None)
        usage = getattr(response, "usage", {}) or {}
        pick = _parse_pick(getattr(response, "output_text", ""), len(allowed))
        reply: dict = {"usage": dict(usage) if isinstance(usage, dict) else {}}
        if pick is not None:
            reply["script"] = allowed[pick][0]
            reply["params"] = list(allowed[pick][1])
        return reply

    return _transport


def bind(app: Any, project_id: str) -> dict:
    """Configure the Watcher model from the stored watcher role profile."""
    from agent_si.runtime.devrun import roles as _roles
    from agent_si.watcher import rules as _rules

    table = _roles._role_table(app)
    for scope in (str(project_id), "local"):
        try:
            profile = table.get_profile(scope, "watcher") if table else None
        except Exception:
            profile = None
        if profile is None or str(getattr(profile, "mode", "")) not in (
                "PINNED", "pool"):
            continue
        try:
            resolution = _roles.resolve_role(app, scope, "watcher")
        except Exception:
            continue
        provider = str(resolution["provider"])
        name = _display_model(provider, str(resolution["model"]))
        local = provider in _roles._LOCAL_LEG_IDS
        transport = _make_transport(app, resolution)
        _BOUND["transport"] = transport
        return _rules.configure_watcher_model(
            transport=transport,
            local_model=name if local else "",
            local_connected=local,
            cloud_model="" if local else name,
            cloud_connected=not local)
    # No pin: drop only a transport this module bound earlier (a pin that
    # was removed); a transport set by anyone else stays.
    config = _rules.watcher_model_config()
    if (_BOUND["transport"] is not None
            and config.get("transport") is _BOUND["transport"]):
        _BOUND["transport"] = None
        return _rules.configure_watcher_model()
    return config
