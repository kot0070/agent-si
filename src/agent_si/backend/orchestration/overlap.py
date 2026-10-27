"""Early-start gate + multi-manager planning (frozen K02 contract).

GATE-RULE: may_start_early is true only when the part's gate_verdict_ref
AND audit_verdict_ref both resolve to stored PASS, else false, never raises.

MultiMgr frozen shape (dicts only, self-contained)::
    {multi_manager_mode, max_parallel_managers, overlap,
     integration_policy, model_pool_per_manager}

Rules:
- mode off -> exactly one running Manager, the rest queue (never drop).
- over-capacity parts queue in order, never drop.
- overlap off -> no early start even on stored PASS+PASS refs.
- invalid config blocked: validate_* returns (False, reason).
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "may_start_early",
    "early_start_allowed",
    "validate_multi_manager_settings",
]

MODEL_ID = "meta/muse-spark-1.3-contributor"

_GATE_VERDICTS: dict[str, str] = {}
_AUDIT_VERDICTS: dict[str, str] = {}


def _record_gate_verdict(ref_str: str, verdict: str) -> None:
    _GATE_VERDICTS[str(ref_str)] = str(verdict)


def _record_audit_verdict(ref_str: str, verdict: str) -> None:
    _AUDIT_VERDICTS[str(ref_str)] = str(verdict)


def _clear_verdicts() -> None:
    _GATE_VERDICTS.clear()
    _AUDIT_VERDICTS.clear()


def may_start_early(ref: dict) -> bool:
    try:
        if not isinstance(ref, dict):
            return False
        gate_ref = ref.get("gate_verdict_ref")
        audit_ref = ref.get("audit_verdict_ref")
        if not isinstance(gate_ref, str) or not gate_ref.strip():
            return False
        if not isinstance(audit_ref, str) or not audit_ref.strip():
            return False
        return (
            _GATE_VERDICTS.get(gate_ref) == "PASS"
            and _AUDIT_VERDICTS.get(audit_ref) == "PASS"
        )
    except Exception:
        return False


def _setting(settings: Any, key: str, default: Any = None) -> Any:
    if isinstance(settings, dict):
        return settings.get(key, default)
    return getattr(settings, key, default)


def validate_multi_manager_settings(settings: Any) -> tuple[bool, str]:
    """Validate a MultiMgr settings dict. Returns (ok, reason)."""
    try:
        if not isinstance(settings, dict):
            return (False, "POLICY_CONFLICT: settings must be a dict")
        mode = settings.get("multi_manager_mode")
        if not isinstance(mode, bool):
            return (False, "POLICY_CONFLICT: multi_manager_mode must be bool")
        cap = settings.get("max_parallel_managers")
        if isinstance(cap, bool) or not isinstance(cap, int):
            return (False, "POLICY_CONFLICT: max_parallel_managers must be int >= 1")
        if cap < 1:
            return (
                False,
                "POLICY_CONFLICT: max_parallel_managers must be int >= 1",
            )
        overlap = settings.get("overlap")
        if not isinstance(overlap, bool):
            return (False, "POLICY_CONFLICT: overlap must be bool")
        policy = settings.get("integration_policy")
        if not isinstance(policy, str) or policy.strip() == "":
            return (
                False,
                "POLICY_CONFLICT: integration_policy must be a non-empty string",
            )
        pool = settings.get("model_pool_per_manager")
        if not isinstance(pool, dict):
            return (False, "POLICY_CONFLICT: model_pool_per_manager must be a dict")
        return (True, "ok")
    except Exception as exc:
        return (False, "POLICY_CONFLICT: settings validation error %s" % type(exc).__name__)


def early_start_allowed(ref: dict, overlap: Any = True, settings: Any = None) -> bool:
    """Early-start decision honouring the overlap flag.

    overlap off -> False even when stored refs are PASS+PASS.
    The flag may be passed directly (bool) or via a settings dict
    (second positional arg or `settings=`); settings wins when given.
    Never raises.
    """
    try:
        source: Any = settings if settings is not None else (overlap if isinstance(overlap, dict) else None)
        flag: Any = _setting(source, "overlap", True) if source is not None else overlap
        if flag is False:
            return False
        return may_start_early(ref)
    except Exception:
        return False
