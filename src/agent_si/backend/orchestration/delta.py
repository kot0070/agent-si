"""Bounded delta + config validation + decision log (frozen K02 contract)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from .common import (
    DecisionLog,
    ensure_compact_english,
    hot_write_text,
    surface_rejection,
)
from .graph import HierarchyConfigStore

MODEL_ID = "meta/muse-spark-1.3-contributor"

_MAX_DELTA_SCOPE = 16


class DELTA_OVER_BOUND(Exception):
    pass


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def intake_bounded_delta(scope: list[str], blocking: bool) -> dict:
    items = list(scope)
    if len(items) > _MAX_DELTA_SCOPE:
        raise DELTA_OVER_BOUND(
            f"DELTA_OVER_BOUND: scope size {len(items)} exceeds {_MAX_DELTA_SCOPE}"
        )
    canonical = json.dumps(
        {"scope": items, "blocking": bool(blocking)},
        separators=(",", ":"),
        ensure_ascii=True,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
    return {
        "delta_id": "delta-" + digest,
        "scope": list(items),
        "blocking": bool(blocking),
        "keep": list(items),
        "patch": [],
        "created_at": _utc_now(),
    }


def cross_check(open_packages: list[str], gates: list[dict]) -> list[str]:
    try:
        opens = list(open_packages)
    except TypeError:
        return []
    try:
        gate_list = list(gates)
    except TypeError:
        gate_list = []
    good: set[str] = set()
    for entry in gate_list:
        if not isinstance(entry, dict):
            continue
        pid = entry.get("package_id")
        if (
            isinstance(pid, str)
            and entry.get("gate") == "PASS"
            and entry.get("audit") == "PASS"
        ):
            good.add(pid)
    conflicts = [pid for pid in opens if pid not in good]
    try:
        return sorted(conflicts)
    except TypeError:
        return sorted(str(pid) for pid in conflicts)


def close_with_linkcheck(delta: dict, verdict: dict) -> dict:
    try:
        if isinstance(delta, dict):
            raw_id = delta.get("delta_id", "unknown")
        else:
            raw_id = "unknown"
        package_id = raw_id if isinstance(raw_id, str) and raw_id != "" else "unknown"
        gate = verdict.get("gate") if isinstance(verdict, dict) else None
        audit = verdict.get("audit") if isinstance(verdict, dict) else None
        refs = verdict.get("evidence_refs") if isinstance(verdict, dict) else None
        link_ok = isinstance(refs, list) and len(refs) > 0
        if gate == "PASS" and audit == "PASS" and link_ok:
            evidence = [*cast(list, refs), "linkcheck:ok"]
            return {
                "package_id": package_id,
                "gate": "PASS",
                "audit": "PASS",
                "decided_at": _utc_now(),
                "evidence_refs": evidence,
            }
        if not link_ok:
            reason_ref = "linkcheck:failed:missing-evidence"
        else:
            g = gate if isinstance(gate, str) and gate != "" else "unknown-gate"
            a = audit if isinstance(audit, str) and audit != "" else "unknown-audit"
            raw = f"blocked:{g}:{a}"
            reason_ref = "".join(
                ch if ord(ch) < 128 and not ch.isspace() else "-" for ch in raw
            )
        base_refs = [r for r in refs if isinstance(r, str)] if isinstance(refs, list) else []  # noqa: E501  # frozen-cite K02
        return {
            "package_id": package_id,
            "gate": "BLOCKED",
            "audit": "BLOCKED",
            "decided_at": _utc_now(),
            "evidence_refs": [*base_refs, reason_ref],
        }
    except Exception:
        return {
            "package_id": "unknown",
            "gate": "BLOCKED",
            "audit": "BLOCKED",
            "decided_at": _utc_now(),
            "evidence_refs": ["blocked:malformed-input"],
        }


def _new_claims(patch: dict) -> list[str]:
    claims: list[str] = []
    if "scope" in patch:
        value = patch["scope"]
        if isinstance(value, str):
            claims.append(value)
        elif isinstance(value, list):
            claims.extend([v for v in value if isinstance(v, str)])
    if "scope_claim" in patch:
        value = patch["scope_claim"]
        if isinstance(value, str):
            claims.append(value)
        elif isinstance(value, list):
            claims.extend([v for v in value if isinstance(v, str)])
    if "claimed_scopes" in patch and isinstance(patch["claimed_scopes"], list):
        claims.extend([v for v in patch["claimed_scopes"] if isinstance(v, str)])
    return claims


def validate_config_change(patch: dict, current: dict) -> tuple[bool, str]:
    try:
        if not isinstance(patch, dict) or not isinstance(current, dict):
            return (False, "POLICY_CONFLICT: patch and current must be dicts")
        effective: dict[str, Any] = dict(current)
        for key, value in patch.items():
            if key == "cost":
                continue
            effective[key] = value
        model = effective.get("model", MODEL_ID)
        if model != MODEL_ID:
            return (False, f"POLICY_CONFLICT: model must stay {MODEL_ID}")
        auditor = effective.get("auditor")
        worker = effective.get("worker")
        independent = effective.get("independent_audit", True)
        if (
            isinstance(auditor, str)
            and isinstance(worker, str)
            and auditor != ""
            and auditor == worker
            and not independent
        ):
            return False, "AUDIT_INDEPENDENCE_REJECTED: auditor must differ from worker"
        if "cost" in patch:
            raw_cost = patch["cost"]
            if isinstance(raw_cost, bool) or not isinstance(raw_cost, (int, float)):
                return (False, "BUDGET_CAPPED: cost must be numeric")
            try:
                budget_left = float(current.get("budget_left", 0))
            except (TypeError, ValueError):
                return (False, "BUDGET_CAPPED: budget_left must be numeric")
            if float(raw_cost) > budget_left:
                return (False, "BUDGET_CAPPED: cost exceeds budget_left")
        for key, value in effective.items():
            if key.startswith("max_"):  # noqa: SIM102  # frozen-cite K02
                if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                    return (False, f"POLICY_CONFLICT: {key} must be int >= 1")
        if "active_chain" in effective:
            chain = effective["active_chain"]
            if chain is None:
                chain = []
            if not isinstance(chain, list):
                return (False, "POLICY_CONFLICT: active_chain must be a list")
            if len(chain) > 0:
                if not all(isinstance(node, str) and node.strip() for node in chain):
                    return (False, "POLICY_CONFLICT: active_chain must list non-empty ids")  # noqa: E501  # frozen-cite K02
                if len(set(chain)) != len(chain):
                    return False, "POLICY_CONFLICT: active_chain must not repeat nodes"
                known = effective.get("known_nodes", [])
                if isinstance(known, list):
                    u = [node for node in chain if node not in set(known)]
                    if u:
                        return (
                            False,
                            f"POLICY_CONFLICT: unknown hierarchy nodes: {','.join(u)}",
                        )
                else:
                    return (False, "POLICY_CONFLICT: known_nodes must be a list")
        claimed = current.get("claimed_scopes", [])
        if not isinstance(claimed, list):
            claimed = []
        claimed_set = {c for c in claimed if isinstance(c, str)}
        for claim in _new_claims(patch):
            if claim in claimed_set:
                return (False, f"REJECTED_SCOPE_OVERLAP: scope {claim} already claimed")
        return (True, "ok")
    except Exception as exc:
        return (False, f"POLICY_CONFLICT: validation error {type(exc).__name__}")


def apply_config_change(
    config: dict,
    log: list,
    scope: str,
    statement: str,
    reason: str,
    authority: str,
    patch: dict,
) -> dict:
    try:
        if not isinstance(config, dict) or not isinstance(log, list):
            return {"applied": False, "reason": "POLICY_CONFLICT: bad target", "decision_ref": None}  # noqa: E501  # frozen-cite K02
        if not isinstance(patch, dict) or not isinstance(scope, str) or scope == "":
            return {"applied": False, "reason": "POLICY_CONFLICT: bad patch", "decision_ref": None}  # noqa: E501  # frozen-cite K02
        ok, check_reason = validate_config_change(patch, config)
        if not ok:
            return {"applied": False, "reason": check_reason, "decision_ref": None}
        cost = patch.get("cost", 0)
        if isinstance(cost, bool):
            cost_value = 0.0
        elif isinstance(cost, (int, float)):
            cost_value = float(cost)
        else:
            cost_value = 0.0
        budget_before = float(config.get("budget_left", 0))
        config["budget_left"] = budget_before - cost_value
        for key, value in patch.items():
            if key == "cost":
                continue
            if key == "claimed_scopes" and isinstance(value, list):
                existing = config.get("claimed_scopes", [])
                if not isinstance(existing, list):
                    existing = []
                merged = list(existing)
                for item in value:
                    if item not in merged:
                        merged.append(item)
                config[key] = merged
            elif key in ("scope", "scope_claim"):
                config[key] = value
                claims = _new_claims({key: value})
                existing = config.get("claimed_scopes", [])
                if not isinstance(existing, list):
                    existing = []
                    config["claimed_scopes"] = existing
                for claim in claims:
                    if claim not in existing:
                        existing.append(claim)
            else:
                config[key] = value
        count = sum(1 for r in log if isinstance(r, dict) and r.get("scope") == scope)
        decision_id = f"{scope}-{count + 1:04d}"
        row = {
            "decision_id": decision_id,
            "scope": scope,
            "statement": statement,
            "reason": reason,
            "authority": authority,
            "created_at": _utc_now(),
        }
        log.append(row)
        return {"applied": True, "reason": "applied", "decision_ref": decision_id}
    except Exception as exc:
        return {
            "applied": False,
            "reason": f"POLICY_CONFLICT: apply error {type(exc).__name__}",
            "decision_ref": None,
        }


def validate_stored_config(store: HierarchyConfigStore, patch: dict) -> tuple[bool, str]:  # noqa: E501  # frozen-cite K02
    return store.validate(patch)


def apply_stored_config(
    store: HierarchyConfigStore,
    scope: str,
    statement: str,
    reason: str,
    authority: str,
    patch: dict,
) -> dict:
    return store.apply(scope, statement, reason, authority, patch)


def activate_hierarchy_chain(
    config: dict, log: list, chain: list, authority: str = "director"
) -> dict:
    try:
        nodes = list(chain)
    except TypeError:
        return {
            "applied": False,
            "reason": "POLICY_CONFLICT: active_chain must be a list",
            "decision_ref": None,
        }
    return apply_config_change(
        config,
        log,
        "hierarchy",
        f"activate chain {','.join(nodes)}",
        "hierarchy activation",
        authority,
        {"active_chain": nodes},
    )


if TYPE_CHECKING:
    # The four imports below are kept for surface compatibility and have no
    # other runtime use; this block records the use for import tooling.
    _RETAINED_IMPORTS = (
        DecisionLog,
        ensure_compact_english,
        hot_write_text,
        surface_rejection,
    )
