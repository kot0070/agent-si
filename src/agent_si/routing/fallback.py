# K04 Lane A2 — fallback chain builder + FallbackRecord handling.
# Pinned models and the Manager model are replaced ONLY through this path,
# always with a stored record (frozen reason set, manifest section 17) and
# a telemetry event.
"""Canonical fallback: build chains, record replacements, never blind-retry."""

from __future__ import annotations

import threading
import uuid
from typing import Dict, List, Mapping, Optional, Tuple

from . import types as T
from .telemetry_port import TelemetryEmitter, routing_event


# --------------------------------------------------------------------------
# Server-side id scope for the frozen record_fallback facade (same pattern
# as router.bind_select_scope / roles.bind_role_table): the 7 frozen refs
# stay on the signature; project/task/run ids arrive via this binding.

_fallback_scope = threading.local()


def bind_fallback_ctx(mapping):
    """Bind the server-side id scope for build_fallback_record.

    Accepts the request-scoped id mapping (project_id, task_id,
    source_run_id, plus optional replacement_run_id, source_attempt_id
    and fallback_id) and returns it unchanged. build_fallback_record
    reads this binding; an unbound call keeps today's missing-id
    ValueError behavior.
    """
    _fallback_scope.mapping = mapping
    return mapping


def unbind_fallback_ctx():
    """Clear the bound fallback scope (call in finally after the record)."""
    _fallback_scope.mapping = None


def build_fallback_chain(winner: Tuple[str, str],
                         runners_up: List[Tuple[str, str]]) -> Tuple[Dict[str, str], ...]:
    """Ordered fallback chain: winner first, then runners-up in rank order."""
    chain = [{"provider": winner[0], "model": winner[1]}]
    for provider, model in runners_up:
        entry = {"provider": provider, "model": model}
        if entry not in chain:
            chain.append(entry)
    return tuple(chain)


def build_fallback_record(reason: str, from_provider: str, from_model: str,
                          to_provider: str, to_model: str, policy_ref: str,
                          evidence_ref: str) -> T.FallbackRecord:
    """Frozen 7-param fallback-record facade; ids arrive via the bound scope.

    bind_fallback_ctx keys: project_id, task_id, source_run_id (all
    required; a missing one raises ValueError naming it) plus optional
    replacement_run_id, source_attempt_id and fallback_id (a fresh
    "fb-<hex>" id is minted when fallback_id is absent). The frozen
    FallbackRecord semantics hold, including the reason-enum check
    against FALLBACK_REASONS.
    """
    ctx = getattr(_fallback_scope, "mapping", None) or {}
    missing = [key for key in ("project_id", "task_id", "source_run_id")
               if not ctx.get(key)]
    if missing:
        raise ValueError(
            "build_fallback_record needs %s in ctx (project/task/run ids "
            "are server-side, never frozen params)" % ", ".join(missing))
    T.check_enum("reason", reason, T.FALLBACK_REASONS)
    return T.FallbackRecord(
        fallback_id=ctx.get("fallback_id") or "fb-%s" % uuid.uuid4().hex[:12],
        project_id=ctx["project_id"], task_id=ctx["task_id"],
        source_run_id=ctx["source_run_id"],
        replacement_run_id=ctx.get("replacement_run_id"),
        source_attempt_id=ctx.get("source_attempt_id"), reason=reason,
        from_provider=from_provider, from_model=from_model,
        to_provider=to_provider, to_model=to_model,
        policy_ref=policy_ref, evidence_ref=evidence_ref)


def _emit(emitter, event) -> None:
    if emitter is not None:
        emitter.emit(event)


def replace_pinned(*, old_provider: str, old_model: str,
                   new_provider: str, new_model: str,
                   project_id: str, task_id: str, source_run_id: str,
                   reason: str, policy_ref: str, evidence_ref: str,
                   source_attempt_id: Optional[str] = None,
                   replacement_run_id: Optional[str] = None,
                   store=None, emitter=None) -> Tuple[T.FallbackRecord, Dict[str, str]]:
    """Swap a pinned model via the canonical fallback path only.

    Same logical route/strategy keeps the same run (new attempt); a
    material change takes a new run id. Either way the record is stored
    and a telemetry event is emitted. Returns (record, new pin dict).
    """
    bind_fallback_ctx({
        "project_id": project_id, "task_id": task_id,
        "source_run_id": source_run_id,
        "replacement_run_id": (source_run_id if replacement_run_id is None
                               else replacement_run_id),
        "source_attempt_id": source_attempt_id})
    try:
        record = build_fallback_record(
            reason, old_provider, old_model,
            new_provider, new_model, policy_ref, evidence_ref)
    finally:
        unbind_fallback_ctx()
    if store is not None:
        store.save_fallback(record)
    _emit(emitter, routing_event(
        project_id=project_id, task_id=task_id,
        run_id=record.replacement_run_id or source_run_id,
        route="CLOUD", provider=new_provider, model=new_model,
        event_type="fallback_replacement",
        reason="pinned %s/%s replaced by %s/%s: %s (record %s)"
        % (old_provider, old_model, new_provider, new_model, reason,
           record.fallback_id),
        fallback_reason=reason, mock=False))
    return record, {"provider": new_provider, "model": new_model}


def replace_manager_model(profile: T.DefaultManagerProfile, *,
                          to_provider: str, to_model: str, reason: str,
                          trigger: str, trigger_ref: str,
                          project_id: str, task_id: str, run_id: str,
                          policy_ref: str = "fallback:default",
                          evidence_ref: str = "manager:trigger",
                          store=None,
                          emitter: Optional[TelemetryEmitter] = None
                          ) -> Tuple[T.FallbackRecord, T.DefaultManagerProfile]:
    """Replace the Manager model only via a recorded trigger path.

    Trigger must be one of fallback | routing_decision | user_override
    (manifest section 3B). Returns (record, new profile with version+1).
    """
    if trigger not in T.MANAGER_TRIGGER_SOURCES:
        raise ValueError(
            "Manager model change needs a recorded trigger "
            "(fallback, routing_decision, user_override); got %r" % (trigger,))
    bind_fallback_ctx({
        "project_id": project_id, "task_id": task_id,
        "source_run_id": run_id, "replacement_run_id": run_id,
        "source_attempt_id": None})
    try:
        record = build_fallback_record(
            reason, str(profile.provider), str(profile.model),
            to_provider, to_model, policy_ref,
            "%s:%s" % (trigger, trigger_ref))
    finally:
        unbind_fallback_ctx()
    new_profile = T.DefaultManagerProfile(
        profile_id=profile.profile_id, version=profile.version + 1,
        provider=to_provider, model=to_model, binding=profile.binding,
        hash=T.stable_hash({"profile": profile.profile_id,
                            "version": profile.version + 1,
                            "provider": to_provider, "model": to_model}))
    if store is not None:
        store.save_fallback(record)
        if hasattr(store, "save_manager_profile"):
            store.save_manager_profile(new_profile)
    _emit(emitter, routing_event(
        project_id=project_id, task_id=task_id, run_id=run_id,
        role="manager", provider=to_provider, model=to_model,
        event_type="manager_replacement",
        reason="Manager model %s replaced by %s via %s (record %s)"
        % (profile.model, to_model, trigger, record.fallback_id),
        fallback_reason=reason, mock=False))
    return record, new_profile
