# K04 row R-325 — rule-driven script picker (watcher on local AI).
"""Pick a script plus parameters per rule from registry plus model KB.

Pure selection over the live ProviderRegistry and KB reader passed in:
each candidate resolves in order against routing-eligible instances plus
KB facts (unknown price counts as expensive, unknown capability counts
as ineligible). The first eligible candidate wins; parameters travel
verbatim. Any registry or KB failure is fail-closed DOWN. Seam contact
happens only through the two callables given to run_rule; this module
imports no journal or notify package and handles no tokens at all.

Bench steer (K05OPEN2, hardened K05OPEN3): when recorded bench rows
support one split (cloud vs local) for the rule's case (rule_id ==
case_id), candidates of that split sort first — stable, so the existing
first-eligible order stays the tie-break. Only finalized (stopped) runs'
MEASURED rows count: an active run is still growing, so its rows are not
read-only originals yet, and PROXY rows are non-measured evidence that
never steers. Levels compare in equal wall-clock minutes (Quick 5,
Standard 15, Deep 30); the deepest wall-clock level wins and the steer
note cites its minutes. Within a level the majority split wins, ties
broken by the latest row. Bench input is read-only via run_result_rows;
any bench failure keeps the legacy order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional

PICKED = "PICKED"
DOWN = "DOWN"

_RULE_KEYS = frozenset({"rule_id", "candidates"})
_CANDIDATE_KEYS = frozenset({"script", "parameters", "requires"})
_REQUIRES_KEYS = frozenset(
    {"provider_type", "capability", "max_input_price", "model"})
_PROVIDER_TYPES = ("local", "cloud")

# Token/secret material never travels as a script parameter. Mirrors the
# inline-key field names rejected by providers.registry.contracts plus the
# token/session keys this picker never handles. Compared case-insensitively.
_FORBIDDEN_PARAMETER_KEYS = frozenset({
    "api_key", "apikey", "api_secret", "secret_value", "client_secret",
    "access_token", "password", "authorization", "x-api-key",
    "token", "session_token", "session", "secret",
})


@dataclass(frozen=True)
class PickResult:
    """One picker verdict: chosen script or fail-closed DOWN."""
    status: str
    rule_id: str
    script: Optional[str]
    parameters: Dict[str, Any]
    reason: str
    provider_id: Optional[str] = None
    model: Optional[str] = None
    journal_entry: Dict[str, Any] = field(default_factory=dict)
    notify_payload: Optional[Dict[str, Any]] = None


class _RegistryFailed(Exception):
    """Internal: a live-registry read failed (fail-closed, never escapes)."""


class _KbFailed(Exception):
    """Internal: a model-KB read failed (fail-closed, never escapes)."""


def _down(rule_id: str, reason: str) -> PickResult:
    """Fail-closed verdict: no script, empty parameters, plain reason."""
    return PickResult(status=DOWN, rule_id=rule_id, script=None,
                      parameters={}, reason=reason,
                      provider_id=None, model=None,
                      journal_entry={"rule_id": rule_id, "status": DOWN,
                                     "reason": reason},
                      notify_payload=None)


def _check_requires(index: int, requires: Any) -> dict:
    """Validate one candidate's requires mapping; unknown keys are errors."""
    if not isinstance(requires, Mapping):
        raise ValueError("candidate %d requires is not a mapping" % index)
    unknown = sorted(k for k in requires if k not in _REQUIRES_KEYS)
    if unknown:
        raise ValueError("candidate %d unknown requires key(s): %s"
                         % (index, ", ".join(unknown)))
    checked: Dict[str, Any] = {}
    if "provider_type" in requires:
        provider_type = requires["provider_type"]
        if provider_type not in _PROVIDER_TYPES:
            raise ValueError("candidate %d bad provider_type: %r"
                             % (index, provider_type))
        checked["provider_type"] = provider_type
    if "capability" in requires:
        capability = requires["capability"]
        if (not isinstance(capability, str) or not capability
                or len(capability.split()) != 1):
            raise ValueError("candidate %d capability is not one token: %r"
                             % (index, capability))
        checked["capability"] = capability
    if "max_input_price" in requires:
        price = requires["max_input_price"]
        if (isinstance(price, bool)
                or not isinstance(price, (int, float))):
            raise ValueError("candidate %d max_input_price is not a number: "
                             "%r" % (index, price))
        checked["max_input_price"] = price
    if "model" in requires:
        model = requires["model"]
        if not isinstance(model, str) or not model:
            raise ValueError("candidate %d model is not an id: %r"
                             % (index, model))
        checked["model"] = model
    return checked


def _check_candidate(index: int, candidate: Any) -> tuple:
    """Validate one candidate; returns (script, parameters, requires)."""
    if not isinstance(candidate, Mapping):
        raise ValueError("candidate %d is not a mapping" % index)
    unknown = sorted(k for k in candidate if k not in _CANDIDATE_KEYS)
    if unknown:
        raise ValueError("candidate %d unknown key(s): %s"
                         % (index, ", ".join(unknown)))
    script = candidate.get("script")
    if not isinstance(script, str) or not script:
        raise ValueError("candidate %d script is not a name: %r"
                         % (index, script))
    parameters = candidate.get("parameters", {})
    if not isinstance(parameters, Mapping):
        raise ValueError("candidate %d parameters is not a mapping" % index)
    requires = _check_requires(index, candidate.get("requires", {}))
    return (script, dict(parameters), requires)


def _check_rule(rule: Any) -> tuple:
    """Validate a rule; returns (rule_id, checked candidates)."""
    if not isinstance(rule, Mapping):
        raise ValueError("rule is not a mapping")
    unknown = sorted(k for k in rule if k not in _RULE_KEYS)
    if unknown:
        raise ValueError("rule unknown key(s): %s" % ", ".join(unknown))
    rule_id = rule.get("rule_id")
    if not isinstance(rule_id, str) or not rule_id:
        raise ValueError("rule rule_id is not a name: %r" % (rule_id,))
    candidates = rule.get("candidates")
    if (not isinstance(candidates, (list, tuple)) or not candidates
            or any(not isinstance(item, Mapping) for item in candidates)):
        raise ValueError("rule candidates is not a non-empty list")
    checked = [_check_candidate(index, item)
               for index, item in enumerate(candidates)]
    return (rule_id, checked)


def _forbidden_keys(parameters: Mapping) -> list:
    """Parameter keys carrying token/secret material (fail the candidate)."""
    return sorted(key for key in parameters
                  if isinstance(key, str)
                  and key.lower() in _FORBIDDEN_PARAMETER_KEYS)


def _resolve_candidate(requires: Mapping, contracts: list, registry: Any,
                       kb_reader: Any) -> Optional[tuple]:
    """First (provider_id, model) pair satisfying one candidate, or None.

    Contracts arrive pre-sorted, so resolution order is deterministic.
    Registry reads raise _RegistryFailed; KB reads raise _KbFailed.
    """
    for contract in contracts:
        if ("provider_type" in requires
                and contract.provider_type != requires["provider_type"]):
            continue
        for model in contract.models:
            if "model" in requires and model != requires["model"]:
                continue
            try:
                eligible = registry.is_routing_eligible(
                    contract.provider_id, model)
            except Exception as exc:
                raise _RegistryFailed(str(type(exc))) from None
            if not eligible:
                continue
            try:
                facts = kb_reader.facts(contract.provider_id, model)
            except Exception as exc:
                raise _KbFailed(str(type(exc))) from None
            if "capability" in requires:
                modalities = facts.modalities if facts is not None else ()
                if requires["capability"] not in (modalities or ()):
                    continue
            if "max_input_price" in requires:
                price = facts.input_price if facts is not None else None
                if (isinstance(price, bool)
                        or not isinstance(price, (int, float))
                        or price > requires["max_input_price"]):
                    continue
            return (contract.provider_id, model)
    return None


def _picked_reason(rule_id: str, script: str, position: int,
                   requires: Mapping) -> str:
    """Plain-language reason: rule id plus matched condition names."""
    names = [key for key in ("provider_type", "capability",
                             "max_input_price", "model") if key in requires]
    if names:
        return ("rule '%s' picked script '%s' (candidate %d): matched %s"
                % (rule_id, script, position + 1, ", ".join(names)))
    return ("rule '%s' picked script '%s' (candidate %d): matched a "
            "routing-eligible instance" % (rule_id, script, position + 1))


#: BenchLevel value names ordered by depth (Quick < Standard < Deep).
_LEVEL_NAMES = ("Quick", "Standard", "Deep")

#: BenchLevel hard-floor wall-clock minutes (staged durations 5-15-30:
#: Quick 5, Standard 15, Deep 30). One shared mapping gives every level
#: equal wall-clock meaning: levels rank by these minutes and the steer
#: note cites the winning level's minutes.
_LEVEL_WALL_MINUTES = {"Quick": 5.0, "Standard": 15.0, "Deep": 30.0}


def _level_name(minutes: float) -> str:
    """Level name for wall-clock minutes (exact shared-map lookup)."""
    for name in _LEVEL_NAMES:
        if _LEVEL_WALL_MINUTES[name] == minutes:
            return name
    raise KeyError(minutes)


def _bench_preferred_split(rule_id: str, contracts: list) -> Optional[tuple]:
    """Preferred split from recorded bench rows, or None (keep order).

    Read-only over the real bench store (list_run_ids plus run_result_rows
    plus run_progress; never writes). Rows are scoped to this rule's case
    (rule_id == case_id); a row supports the split serving its model — the
    first contract in deterministic order holding that model; rows naming
    no served model are ignored, as are rows for other cases. Only rows
    from finalized (stopped) runs count — an active run is still growing,
    so its rows are not read-only originals yet. Only MEASURED rows count:
    PROXY rows are non-measured evidence and never steer. Each row's level
    comes from its run's handle (bench_runner exposes no public level
    reader; read-only and guarded — a run without a readable level is
    skipped); levels compare in equal wall-clock minutes from
    _LEVEL_WALL_MINUTES, so the deepest wall-clock level wins (Standard
    beats Quick, Deep beats Standard).
    Within the winning level the majority split wins; a tie breaks by the
    latest row. Runs compare in start order (run ids sort chronologically)
    and rows in list order, so the outcome is deterministic.

    Any bench failure — or no supporting rows — yields None and the caller
    keeps the existing first-eligible order.
    """
    try:
        from agent_si.local import bench_runner as _runner
        from agent_si.local.bench_protocol import BenchLevel as _BenchLevel
        from agent_si.local.bench_protocol import ResultKind as _ResultKind
    except Exception:
        return None
    try:
        run_ids = sorted(_runner.list_run_ids())
    except Exception:
        return None
    if not run_ids:
        return None
    try:
        model_split = {}
        for contract in contracts:
            for model in contract.models:
                if model not in model_split:
                    model_split[model] = contract.provider_type
        if not model_split:
            return None
        handles = _runner._RUNS
    except Exception:
        return None
    best = {}
    for seq_run, run_id in enumerate(run_ids):
        try:
            progress = _runner.run_progress(run_id)
        except Exception:
            continue
        if not progress.stopped:
            continue
        try:
            depth = _LEVEL_WALL_MINUTES[
                _BenchLevel(handles[run_id].level).value]
        except Exception:
            continue
        try:
            rows = _runner.run_result_rows(run_id)
        except Exception:
            continue
        for seq_row, row in enumerate(rows):
            try:
                if row.case_id != rule_id:
                    continue
                if _ResultKind(row.kind) is not _ResultKind.MEASURED:
                    continue
                split = model_split.get(row.model_id)
            except Exception:
                continue
            if split not in ("local", "cloud"):
                continue
            entry = best.get(split)
            if entry is None or depth > entry[0]:
                best[split] = [depth, 1, (seq_run, seq_row)]
            elif depth == entry[0]:
                entry[1] += 1
                entry[2] = (seq_run, seq_row)
    if not best:
        return None
    top = max(entry[0] for entry in best.values())
    top_name = _level_name(top)
    contenders = sorted(split for split, entry in best.items()
                        if entry[0] == top)
    if len(contenders) == 1:
        winner = contenders[0]
    else:
        votes = max(best[split][1] for split in contenders)
        leaders = sorted(split for split in contenders
                         if best[split][1] == votes)
        if len(leaders) == 1:
            winner = leaders[0]
        else:
            winner = max(leaders, key=lambda split: best[split][2])
    entry = best[winner]
    others = sorted(split for split in best if split != winner)
    if others:
        over = "; overrode " + ", ".join(
            "%s (%s)" % (other, _level_name(best[other][0]))
            for other in others)
    else:
        over = ""
    note = ("bench steer to '%s' (%s ~%g min, %d row(s)%s)"
            % (winner, top_name, top, entry[1], over))
    return (winner, note)


def pick(rule: Mapping, registry: Any, kb_reader: Any) -> PickResult:
    """Choose a script plus verbatim parameters for a rule (pure selection).

    Raises ValueError on a malformed rule. Any live-registry or KB read
    failure returns DOWN (fail-closed); so does a rule no instance can
    satisfy. Recorded bench rows may reorder candidates toward the
    supported split (bench steer); without bench support the first eligible
    candidate wins. Never calls a seam.
    """
    rule_id, candidates = _check_rule(rule)
    try:
        entries = registry.instances()
        contracts = [registry.contract_for(entry["provider_id"],
                                           entry["instance_id"])
                     for entry in entries]
    except Exception:
        return _down(rule_id, "rule '%s' is DOWN: fail-closed on registry "
                              "error" % rule_id)
    contracts.sort(key=lambda item: (item.provider_id, item.instance_id))
    try:
        steer = _bench_preferred_split(rule_id, contracts)
    except Exception:
        steer = None
    order = list(enumerate(candidates))
    if steer is not None:
        preferred = steer[0]
        order.sort(key=lambda item: (
            0 if item[1][2].get("provider_type", preferred) == preferred
            else 1, item[0]))
    for position, (script, parameters, requires) in order:
        if _forbidden_keys(parameters):
            continue
        try:
            hit = _resolve_candidate(requires, contracts, registry, kb_reader)
        except _KbFailed:
            return _down(rule_id, "rule '%s' is DOWN: fail-closed on model "
                                  "KB error" % rule_id)
        except Exception:
            return _down(rule_id, "rule '%s' is DOWN: fail-closed on "
                                  "registry error" % rule_id)
        if hit is None:
            continue
        provider_id, model = hit
        reason = _picked_reason(rule_id, script, position, requires)
        if (steer is not None
                and requires.get("provider_type") == steer[0]):
            reason = "%s; %s" % (reason, steer[1])
        return PickResult(
            status=PICKED, rule_id=rule_id, script=script,
            parameters=dict(parameters), reason=reason,
            provider_id=provider_id, model=model,
            journal_entry={"rule_id": rule_id, "status": PICKED,
                           "script": script, "provider_id": provider_id,
                           "model": model, "parameters": dict(parameters),
                           "reason": reason},
            notify_payload={"rule_id": rule_id, "status": PICKED,
                            "script": script, "provider_id": provider_id,
                            "model": model, "reason": reason})
    return _down(rule_id, "rule '%s' picked nothing: no routing-eligible "
                          "instance matched any of %d candidate(s)"
                 % (rule_id, len(candidates)))


def run_rule(rule: Mapping, registry: Any, kb_reader: Any,
             journal_append: Any = None, notify: Any = None) -> PickResult:
    """Run pick, then report a PICKED verdict through the given callables.

    Each seam callable fires at most once, only when provided and only on
    PICKED. A raising seam returns DOWN naming that seam call
    (fail-closed); the notify call is skipped when journaling already
    failed. Calls only the two passed-in callables.
    """
    result = pick(rule, registry, kb_reader)
    if result.status != PICKED:
        return result
    if journal_append is not None:
        try:
            journal_append(result.journal_entry)
        except Exception:
            return _down(result.rule_id, "rule '%s' is DOWN: fail-closed on "
                                         "journal_append error"
                         % result.rule_id)
    if notify is not None:
        try:
            notify(result.notify_payload)
        except Exception:
            return _down(result.rule_id, "rule '%s' is DOWN: fail-closed on "
                                         "notify error" % result.rule_id)
    return result
