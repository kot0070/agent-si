# K04 Lane A2 — executable role profiles (Director, Manager, worker, auditor, Watcher).
# Fresh install: no role holds a model until the user picks PINNED or AUTO
# (every resolution BLOCKED with a reason). The Manager binds the
# DefaultManagerProfile and is never re-selected per run.
"""RoleModelProfile storage + resolution; single/multi-provider modes."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Tuple

from . import types as T
from . import fallback as F


@dataclass(frozen=True)
class Resolution:
    role: str
    project_id: str
    status: str  # READY | BLOCKED | PINNED_UNHEALTHY
    provider: Optional[str]
    model: Optional[str]
    mode: Optional[str]
    reason: str
    profile_ref: Optional[str] = None


def make_default_manager_profile(provider: str, model: str, *,
                                 profile_id: str = "DMP-001",
                                 version: int = 1,
                                 binding: str = "DEFAULT") -> T.DefaultManagerProfile:
    """Build the project Manager profile from explicit caller values.

    Provider and model are required arguments: no vendor/model literal
    lives in code paths; the shipped preset is project configuration.
    """
    return T.DefaultManagerProfile(
        profile_id=profile_id, version=version,
        provider=provider, model=model, binding=binding,
        hash=T.stable_hash({"profile": profile_id, "version": version,
                            "provider": provider, "model": model}))


class RoleTable:
    """In-memory role profiles with optional JSON persistence via a store."""

    def __init__(self, store=None) -> None:
        self._rows: Dict[Tuple[str, str], T.RoleModelProfile] = {}
        self._store = store

    def set_profile(self, profile: T.RoleModelProfile) -> None:
        if not isinstance(profile, T.RoleModelProfile):
            raise ValueError("set_profile needs a RoleModelProfile")
        self._rows[(profile.project_id, profile.role)] = profile
        if self._store is not None:
            self._store.save_role_profile(profile)

    def get_profile(self, project_id: str, role: str) -> Optional[T.RoleModelProfile]:
        row = self._rows.get((project_id, role))
        if row is None and self._store is not None:
            data = self._store.get_role_profile(project_id, role)
            if data is not None:
                row = T.RoleModelProfile(**data)
                self._rows[(project_id, role)] = row
        return row

    def reload(self, project_id: str) -> None:
        if self._store is None:
            return
        for data in self._store.list_role_profiles(project_id):
            row = T.RoleModelProfile(**data)
            self._rows[(project_id, row.role)] = row

    def list_profiles(self, project_id: str) -> List[T.RoleModelProfile]:
        self.reload(project_id)
        return [row for (proj, _role), row in sorted(self._rows.items())
                if proj == project_id]

    def resolve(self, project_id: str, role: str, *,
                provider_health: Mapping = None,
                model_health: Mapping = None,
                exclude_pairs: Tuple[Tuple[str, str], ...] = ()) -> Resolution:
        """Resolve one role: READY, BLOCKED, or PINNED_UNHEALTHY (never a swap)."""
        profile = self.get_profile(project_id, role)
        if profile is None:
            return Resolution(role, project_id, "BLOCKED", None, None, None,
                              "NO_PROFILE_BLOCKED: no profile for role %r: "
                              "pick PINNED or AUTO "
                              "(fresh install holds no model)" % role)
        if profile.mode == "AUTO":
            if exclude_pairs:
                return Resolution(role, project_id, "READY", None, None,
                                  "AUTO",
                                  "AUTO: model chosen per task "
                                  "(auditor kept off implementer pairs)",
                                  _profile_ref(profile))
            return Resolution(role, project_id, "READY", None, None, "AUTO",
                              "AUTO: model chosen per task",
                              _profile_ref(profile))
        if profile.mode == "pool":
            binding = (self._store.get_pool(project_id, role)
                       if self._store is not None and
                       hasattr(self._store, "get_pool") else None)
            if binding is None:
                return Resolution(role, project_id, "BLOCKED", None, None,
                                  "pool",
                                  "pool mode needs a stored binding "
                                  "for role %r" % role,
                                  _profile_ref(profile))
            return Resolution(role, project_id, "READY", None, None, "pool",
                              "pool: resolved per task via stored binding",
                              _profile_ref(profile))
        # PINNED: health decides READY vs PINNED_UNHEALTHY; never a silent swap.
        provider = str(profile.provider)
        model = str(profile.model)
        if (provider, model) in tuple(exclude_pairs or ()):
            return Resolution(role, project_id, "BLOCKED", provider, model,
                              "PINNED",
                              "pinned %s/%s excluded (auditor must differ "
                              "from implementers)" % (provider, model),
                              _profile_ref(profile))
        phealth = (provider_health or {}).get(provider)
        mhealth = (model_health or {}).get((provider, model))
        pok = phealth is not None and getattr(phealth, "status", phealth) == "ONLINE"
        if isinstance(phealth, Mapping):
            pok = phealth.get("status") == "ONLINE"
        mok = mhealth is not None and getattr(mhealth, "status", mhealth) == "READY"
        if isinstance(mhealth, Mapping):
            mok = mhealth.get("status") == "READY"
        if pok and mok:
            return Resolution(role, project_id, "READY", provider, model,
                              "PINNED", "pinned %s/%s healthy" % (provider, model),
                              _profile_ref(profile))
        return Resolution(
            role, project_id, "PINNED_UNHEALTHY", provider, model, "PINNED",
            "pinned %s/%s unhealthy: replace only via the fallback path "
            "(stored FallbackRecord + telemetry), never silently" % (provider, model),
            _profile_ref(profile))


def _profile_ref(profile: T.RoleModelProfile) -> str:
    return "role:%s:%s:v%d" % (profile.role, profile.project_id, profile.version)


@dataclass(frozen=True)
class ModelRef:
    """Single (provider, model) handle for a PINNED role.

    Mirrors the frozen interface ModelRef (provider_id/model): provider is
    the provider id, model the exact verbatim model id.
    """

    provider: str
    model: str


_role_scope = threading.local()


def bind_role_table(table):
    """Bind the server-side RoleTable for the frozen resolve_role_model.

    Accepts the caller's RoleTable and returns it unchanged.
    resolve_role_model reads this binding; an unbound call keeps
    today's store-less behavior.
    """
    _role_scope.table = table
    return table


def unbind_role_table():
    """Clear the bound role table (call in finally after resolve_role_model)."""
    _role_scope.table = None


def resolve_role_model(role: str, project_id: str) -> ModelRef:
    """Frozen facade: the single model bound to a PINNED role.

    Frozen params only (no **ctx): resolution runs against the bound
    RoleTable (see bind_role_table); unbound it falls back to a
    store-less RoleTable, so with only (role, project_id) no profile
    can be found and the call raises ValueError carrying
    NO_PROFILE_BLOCKED plus the reason. A PINNED profile ->
    ModelRef(provider, model); any other mode (pool, AUTO) ->
    ValueError carrying NO_PROFILE_BLOCKED naming the mode: there is
    no single model to return, per-task resolution still goes through
    RoleTable.resolve.
    RoleTable.resolve itself is unchanged.
    """
    table = getattr(_role_scope, "table", None)
    if table is None:
        table = RoleTable()
    profile = table.get_profile(project_id, role)
    if profile is None:
        raise ValueError(
            "NO_PROFILE_BLOCKED: no profile for role %r in project %r "
            "(pick PINNED or AUTO; a fresh install holds no model)"
            % (role, project_id))
    if profile.mode == "PINNED":
        return ModelRef(provider=str(profile.provider),
                        model=str(profile.model))
    raise ValueError(
        "NO_PROFILE_BLOCKED: role %r in project %r has mode %r, so no "
        "single model can be returned (resolve per task instead)"
        % (role, project_id, profile.mode))


def apply_single_provider(table: RoleTable, project_id: str,
                          provider: str, model: str,
                          binding: str = "DEFAULT") -> None:
    """Single-provider mode: pin every role to the one configured model."""
    for role in T.ROLES:
        table.set_profile(T.RoleModelProfile(
            role=role, project_id=project_id, mode="PINNED",
            provider=provider, model=model, binding=binding,
            version=1,
            hash=T.stable_hash({"role": role, "project": project_id,
                                "provider": provider, "model": model})))


def resolve_manager(profile: T.DefaultManagerProfile, *,
                    to_provider: Optional[str] = None,
                    to_model: Optional[str] = None,
                    trigger: Optional[str] = None,
                    trigger_ref: Optional[str] = None,
                    reason: str = "model_fail",
                    project_id: Optional[str] = None,
                    task_id: Optional[str] = None,
                    run_id: Optional[str] = None,
                    store=None, emitter=None):
    """Bind the Manager profile; re-select only via a recorded trigger.

    Without a target this returns (None, profile): the router keeps the
    profile model and never re-selects per run. With a target, the trigger
    must be recorded (fallback | routing_decision | user_override).
    """
    if to_provider is None and to_model is None:
        return None, profile
    if trigger not in T.MANAGER_TRIGGER_SOURCES:
        raise ValueError(
            "Manager model change needs a recorded trigger "
            "(fallback, routing_decision, user_override); got %r" % (trigger,))
    if not (project_id and task_id and run_id):
        raise ValueError("Manager replacement needs project/task/run ids "
                         "for the FallbackRecord")
    return F.replace_manager_model(
        profile, to_provider=to_provider, to_model=to_model, reason=reason,
        trigger=trigger, trigger_ref=trigger_ref or "",
        project_id=project_id, task_id=task_id, run_id=run_id,
        store=store, emitter=emitter)


NO_TARGET_FLOW_DEFAULT = "NO_TARGET_FLOW_DEFAULT"


class TargetFlowMissingError(ValueError):
    """TARGET_FLOW has no configured entry for a role (never a default)."""

    code = NO_TARGET_FLOW_DEFAULT


def _target_flow_pair(config, role: str) -> Tuple[str, str]:
    """Read one TARGET_FLOW entry as a (provider, model) pair.

    Accepts {"provider", "model"} mappings or (provider, model) pairs.
    Anything else (missing role, unknown role key, incomplete entry)
    raises TargetFlowMissingError: there is no hard-coded role default.
    """
    if not isinstance(config, Mapping) or role not in T.ROLES:
        raise TargetFlowMissingError(
            "TARGET_FLOW has no configured entry for role %r "
            "[NO_TARGET_FLOW_DEFAULT]" % (role,))
    entry = config.get(role)
    provider = model = None
    if isinstance(entry, Mapping):
        provider, model = entry.get("provider"), entry.get("model")
    elif isinstance(entry, (tuple, list)) and len(entry) == 2:
        provider, model = entry
    if not provider or not model:
        raise TargetFlowMissingError(
            "TARGET_FLOW entry for role %r needs provider and model "
            "[NO_TARGET_FLOW_DEFAULT]" % (role,))
    return str(provider), str(model)


def resolve_target_flow(config, role: str, *, project_id: str) -> ModelRef:
    """Resolve one role model from TARGET_FLOW configuration (UID-17).

    Every role model comes from the caller's configuration mapping; a
    role without a configured entry raises instead of falling back to a
    hard-coded default. project_id is carried for parity with resolve.
    """
    _ = project_id
    provider, model = _target_flow_pair(config, role)
    return ModelRef(provider=provider, model=model)


def load_target_flow(table: RoleTable, config, *,
                     project_id: str) -> Dict[str, Dict[str, str]]:
    """Load every role profile from TARGET_FLOW as PINNED (UID-17).

    All-or-nothing: every role in T.ROLES must be configured or nothing
    is stored (no partial defaults). Returns {role: {provider, model}}.
    """
    loaded: Dict[str, Dict[str, str]] = {}
    for role in T.ROLES:
        provider, model = _target_flow_pair(config, role)
        loaded[role] = {"provider": provider, "model": model}
    for role, pair in loaded.items():
        table.set_profile(T.RoleModelProfile(
            role=role, project_id=project_id, mode="PINNED",
            provider=pair["provider"], model=pair["model"],
            binding="TARGET_FLOW", version=1,
            hash=T.stable_hash({"role": role, "project": project_id,
                                "provider": pair["provider"],
                                "model": pair["model"]})))
    return loaded
