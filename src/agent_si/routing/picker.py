# K04 row R-325 — rule-driven script picker (watcher on local AI).
"""Pick a script plus parameters per rule from registry plus model KB.

Pure selection over the live ProviderRegistry and KB reader passed in:
each candidate resolves in order against routing-eligible instances plus
KB facts (unknown price counts as expensive, unknown capability counts
as ineligible). The first eligible candidate wins; parameters travel
verbatim. Any registry or KB failure is fail-closed DOWN. Seam contact
happens only through the two callables given to run_rule; this module
imports no journal or notify package and handles no tokens at all.
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


def pick(rule: Mapping, registry: Any, kb_reader: Any) -> PickResult:
    """Choose a script plus verbatim parameters for a rule (pure selection).

    Raises ValueError on a malformed rule. Any live-registry or KB read
    failure returns DOWN (fail-closed); so does a rule no instance can
    satisfy. Never calls a seam.
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
    for position, (script, parameters, requires) in enumerate(candidates):
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
