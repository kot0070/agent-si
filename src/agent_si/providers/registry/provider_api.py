"""Provider facade: key-only connect plus health views plus leftover help.

The facade wires one wrapped registry through injected ports only. It
never touches the network and never holds raw key material: access
travels as SecretRef values, and every repr or view carries ids only.

Leftover-key rules (provisional, additive):
- M-P4-144 own-prefix only: a name outside the app prefix refuses with
  NOT_OWN_PREFIX.
- M-P4-145 names plus dates only: the list view strips every other
  field; deleting a missing entry refuses with NOT_FOUND.
- M-P4-146 live-linked never deletable: refuses with LIVE_LINKED.
- M-P4-147 explicit confirm plus session token: refuses with
  CONFIRM_REQUIRED or TOKEN_REQUIRED.
- M-P4-148 audit-logged by entry name on success.
- M-P4-149 in-repo runs use fakes only; the real store goes through
  the provisioning gateway.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .contracts import RAW_INLINE_FIELD_NAMES, SecretRef, coerce_secret_ref

#: Development model id. Documentation example only: never a default,
#: never in a signature, never in a fallback chain.
NON_DEFAULT_EXAMPLE = "meta/muse-spark-1.3-contributor"

#: Per-instance provider health states. Latest check wins.
PROVIDER_STATUSES = ("ONLINE", "DEGRADED", "OFFLINE", "UNKNOWN")

#: Raised (as the ValueError message head) when no store entry exists.
CREDENTIAL_ENTRY_MISSING = "CREDENTIAL_ENTRY_MISSING"

PROVIDER_UNEVIDENCED = "PROVIDER_UNEVIDENCED"

NOT_OWN_PREFIX = "NOT_OWN_PREFIX"
NOT_FOUND = "NOT_FOUND"
LIVE_LINKED = "LIVE_LINKED"
CONFIRM_REQUIRED = "CONFIRM_REQUIRED"
TOKEN_REQUIRED = "TOKEN_REQUIRED"

#: Verbatim leftover-key rule map (M-P4-144 through M-P4-149).
LEFTOVER_RULES = {
    "M-P4-144": "own-prefix only: refuse with NOT_OWN_PREFIX",
    "M-P4-145": "names plus dates only: refuse with NOT_FOUND",
    "M-P4-146": "live-linked never deletable: refuse with LIVE_LINKED",
    "M-P4-147": "explicit confirm plus session token: "
    "refuse with CONFIRM_REQUIRED or TOKEN_REQUIRED",
    "M-P4-148": "audit-logged by entry name on success",
    "M-P4-149": "fakes only in-repo; the real store goes through "
    "the provisioning gateway",
}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ProviderContracts:
    """Facade descriptor: identity plus endpoint plus ref plus view flags."""

    provider_id: str
    type: str
    base_url: str
    secret_ref: SecretRef
    instance_id: str = "default"
    evidenced: bool = False
    health: str = "UNKNOWN"
    mock: bool = False

    def describe(self) -> dict:
        return {
            "provider_id": self.provider_id,
            "type": self.type,
            "base_url": self.base_url,
            "secret_ref": self.secret_ref.describe(),
            "instance_id": self.instance_id,
            "evidenced": self.evidenced,
            "health": self.health,
            "mock": self.mock,
        }

    def __repr__(self) -> str:
        text = (
            "ProviderContracts(provider_id=%r, type=%r, base_url=%r, "
            "secret_id=%r, instance_id=%r, evidenced=%r, health=%r, "
            "mock=%r)"
            % (
                self.provider_id,
                self.type,
                self.base_url,
                self.secret_ref.secret_id,
                self.instance_id,
                self.evidenced,
                self.health,
                self.mock,
            )
        )
        if not self.evidenced:
            text = text[:-1] + ", code=%r)" % (PROVIDER_UNEVIDENCED,)
        return text


def _field(descriptor: Any, name: str) -> Any:
    if isinstance(descriptor, Mapping):
        return descriptor.get(name)
    return getattr(descriptor, name, None)


def _reject_inline(descriptor: Any) -> None:
    if not isinstance(descriptor, Mapping):
        return
    found = [key for key in descriptor if key in RAW_INLINE_FIELD_NAMES]
    for nested_key in ("secret_ref", "credential_ref"):
        nested = descriptor.get(nested_key)
        if isinstance(nested, Mapping):
            found += [key for key in nested if key in RAW_INLINE_FIELD_NAMES]
    if found:
        raise ValueError(
            "inline key material rejected: %s" % sorted(set(found))
        )


def _resolve_ref(descriptor: Any, secret_ref: Any) -> SecretRef:
    candidate = secret_ref
    if candidate is None:
        if isinstance(descriptor, Mapping):
            candidate = descriptor.get("secret_ref",
                                       descriptor.get("credential_ref"))
        elif descriptor is not None:
            candidate = getattr(descriptor, "secret_ref", None)
    if candidate is None:
        raise ValueError("secret_ref is required")
    if isinstance(candidate, SecretRef):
        return candidate
    if isinstance(candidate, Mapping):
        return coerce_secret_ref(candidate)
    raise ValueError("secret_ref must be a SecretRef or a field mapping")


class ProviderAPI:
    """Key-only provider facade over an injected registry.

    Ports: registry (duck-typed ProviderRegistry), credential_store
    (delete(secret_id)/has(secret_id)), audit_sink (append(record)),
    and an optional usage_probe callable shaped like
    probe(provider_id, instance_id, usage_transport,
    stream_transport=None, evidence_ref=None).
    """

    def __init__(self, registry: Any, credential_store: Any,
                 audit_sink: Any, usage_probe: Any = None) -> None:
        if registry is None or credential_store is None or audit_sink is None:
            raise ValueError(
                "registry, credential_store and audit_sink are required")
        self._registry = registry
        self._store = credential_store
        self._audit = audit_sink
        self._usage_probe = usage_probe
        self._providers: dict = {}
        # K04BIND1: per-instance last evidence-failure reason (never secret).
        self._errors: dict = {}

    def register_provider(self, descriptor: Any, secret_ref: Any = None,
                          *, model: str | None = None,
                          instance_id: str | None = None,
                          evidence_ref: str | None = None,
                          mock: bool = False) -> ProviderContracts:
        provider_id = _field(descriptor, "provider_id")
        ptype = _field(descriptor, "type")
        base_url = _field(descriptor, "base_url")
        for label, value in (("provider_id", provider_id),
                             ("type", ptype), ("base_url", base_url)):
            if not isinstance(value, str) or not value:
                raise ValueError("%r must be a non-empty string" % label)
        ref = _resolve_ref(descriptor, secret_ref)
        _reject_inline(descriptor)
        resolved_model = model
        if resolved_model is None:
            resolved_model = _field(descriptor, "model")
        if not isinstance(resolved_model, str) or not resolved_model:
            raise ValueError("model is required: presets never bake one in")
        resolved_instance = (
            instance_id or _field(descriptor, "instance_id") or "default"
        )
        self._registry.register_instance({
            "provider": provider_id,
            "provider_type": ptype,
            "model": resolved_model,
            "base_url": base_url,
            "credential_ref": ref,
            "instance_id": resolved_instance,
            "mock": bool(mock),
        })
        return self._track(provider_id, ptype, base_url, ref,
                           resolved_instance, resolved_model,
                           evidence_ref, mock)

    def connect_via_preset(self, preset_id: str, secret_ref: Any, *,
                           model: str | None = None,
                           instance_id: str | None = None,
                           evidence_ref: str | None = None,
                           mock: bool = False,
                           base_url: str | None = None) -> ProviderContracts:
        from .presets import build_config, get_preset

        preset = get_preset(preset_id)
        ref = _resolve_ref(None, secret_ref)
        if not isinstance(model, str) or not model:
            raise ValueError("model is required: presets never bake one in")
        resolved_instance = instance_id or "default"
        config = build_config(
            preset_id,
            model=model,
            credential_ref=ref,
            base_url=base_url,
            instance_id=resolved_instance,
            mock=mock,
        )
        self._registry.register_instance(config)
        return self._track(
            preset["provider_id"], preset["provider_type"],
            config["base_url"], ref, config["instance_id"], model,
            evidence_ref, mock,
        )

    def _track(self, provider_id: str, ptype: str, base_url: str,
               ref: SecretRef, instance_id: str, model: str,
               evidence_ref: str | None, mock: bool) -> ProviderContracts:
        record = self._providers.get(provider_id)
        if record is None:
            record = {
                "type": ptype,
                "base_url": base_url,
                "secret_ref": ref,
                "models": {},
                "mock": bool(mock),
            }
            self._providers[provider_id] = record
        record["models"][instance_id] = model
        if evidence_ref is not None:
            if not evidence_ref:
                raise ValueError("evidence_ref must be a non-empty string")
            self._registry.record_credential_evidence(
                provider_id, instance_id, evidence_ref)
        return self._view(provider_id, instance_id)

    def _view(self, provider_id: str, instance_id: str) -> ProviderContracts:
        record = self._providers[provider_id]
        evidenced = any(
            bool(self._registry.credential_evidenced(provider_id, inst))
            for inst in record["models"]
        )
        # K04BIND1: evidence-failure overrides the view health to ERROR.
        err = self._errors.get((provider_id, instance_id))
        if err is not None:
            health = "ERROR"
        else:
            try:
                health = self._registry.provider_status(
                    provider_id, instance_id)
            except ValueError:
                health = "UNKNOWN"
        return ProviderContracts(
            provider_id=provider_id,
            type=record["type"],
            base_url=record["base_url"],
            secret_ref=record["secret_ref"],
            instance_id=instance_id,
            evidenced=evidenced,
            health=health,
            mock=record["mock"],
        )

    # K04BIND1: evidence-failure reason port (never secret material).
    def set_provider_error(self, provider_id: str,
                           instance_id: str | None,
                           reason: str) -> ProviderContracts:
        inst = instance_id or "default"
        text = str(reason or "provider check failed")
        self._errors[(provider_id, inst)] = text
        try:
            self._registry.record_health(provider_id, inst, "OFFLINE",
                                         error=text)
        except Exception:
            pass
        return self._view(provider_id, inst)

    def clear_provider_error(self, provider_id: str,
                             instance_id: str | None) -> None:
        inst = instance_id or "default"
        self._errors.pop((provider_id, inst), None)

    def get_provider_error(self, provider_id: str,
                           instance_id: str | None = None) -> str | None:
        inst = instance_id or "default"
        hit = self._errors.get((provider_id, inst))
        if hit is not None:
            return hit
        for (pid, _inst), text in self._errors.items():
            if pid == provider_id:
                return text
        return None

    def get_evidence_ref(self, provider_id: str,
                         instance_id: str | None = None) -> str | None:
        inst = instance_id or "default"
        try:
            ref_map = getattr(self._registry, "_ref_evidence", None)
            if isinstance(ref_map, dict):
                value = ref_map.get((provider_id, inst))
                return str(value) if value else None
        except Exception:
            pass
        return None

    def last_provider_error(self) -> str | None:
        # K04BIND1: newest verbatim failure reason for the chat NO_PROVIDER
        # message (never secret; callers never log the key).
        if not self._errors:
            return None
        try:
            return next(reversed(list(self._errors.values())))
        except Exception:
            for text in self._errors.values():
                return text
        return None

    def get_provider(self, provider_id: str) -> ProviderContracts | None:
        stored_id = provider_id
        if isinstance(provider_id, str):
            want = provider_id.strip().lower()
            for key in self._providers:
                if isinstance(key, str) and key.strip().lower() == want:
                    stored_id = key
                    break
        record = self._providers.get(stored_id)
        if record is None:
            return None
        instances = record["models"]
        if "default" in instances:
            instance = "default"
        else:
            instance = sorted(instances)[0]
        return self._view(stored_id, instance)

    def list_providers(
        self, only_evidenced: bool = False
    ) -> list[ProviderContracts]:
        views = []
        for provider_id in sorted(self._providers):
            view = self.get_provider(provider_id)
            if only_evidenced and not view.evidenced:
                continue
            views.append(view)
        return views

    def is_evidenced(self, provider_id: str) -> bool:
        record = self._providers.get(provider_id)
        if record is None:
            return False
        return any(
            bool(self._registry.credential_evidenced(provider_id, inst))
            for inst in record["models"]
        )

    def record_health(self, provider_id: str,
                      provider_instance: str | None,
                      health: str) -> ProviderContracts:
        if health not in PROVIDER_STATUSES:
            raise ValueError("unknown provider status: %r" % (health,))
        if self._providers.get(provider_id) is None:
            raise ValueError("unknown provider: %r" % (provider_id,))
        instance = provider_instance or "default"
        self._registry.record_health(provider_id, instance, health)
        return self._view(provider_id, instance)

    def remove_provider(self, provider_id: str) -> None:
        record = self._providers.get(provider_id)
        if record is None:
            raise ValueError("unknown provider: %r" % (provider_id,))
        secret_id = record["secret_ref"].secret_id
        if not self._store.has(secret_id):
            raise ValueError(
                "%s: no entry for %r" % (CREDENTIAL_ENTRY_MISSING, secret_id)
            )
        contracts = getattr(self._registry, "_contracts", None)
        by_identity = getattr(self._registry, "_by_identity", None)
        evidence = getattr(self._registry, "_ref_evidence", None)
        if contracts is None or by_identity is None or evidence is None:
            raise ValueError("registry does not expose instance storage")
        for key in [key for key in contracts if key[0] == provider_id]:
            del contracts[key]
        for key in [key for key in evidence if key[0] == provider_id]:
            del evidence[key]
        for ident in [ident for ident, key in by_identity.items()
                      if key[0] == provider_id]:
            del by_identity[ident]
        del self._providers[provider_id]
        # K04BIND1: drop any recorded failure reason with the provider.
        for key in [key for key in self._errors if key[0] == provider_id]:
            del self._errors[key]
        self._store.delete(secret_id)
        return None

    def probe_usage(self, provider_id: str, instance_id: str = "default",
                    usage_transport: Any = None,
                    stream_transport: Any = None,
                    evidence_ref: str | None = None) -> dict:
        if self._usage_probe is None:
            raise ValueError("usage probe port is not configured")
        return self._usage_probe(
            provider_id, instance_id or "default", usage_transport,
            stream_transport=stream_transport, evidence_ref=evidence_ref,
        )

    def list_leftover_keys(self, store_view: Mapping[str, Any],
                           app_prefix: str) -> dict:
        return list_leftover_keys(store_view, app_prefix)

    def request_delete_entry(self, store: Any, *, name: str,
                             app_prefix: str, confirmed: bool,
                             session_token: str | None,
                             live_provider_ids: Collection[str],
                             reason: str) -> dict:
        return request_delete_entry(
            store, self._audit, name=name, app_prefix=app_prefix,
            confirmed=confirmed, session_token=session_token,
            live_provider_ids=live_provider_ids, reason=reason,
        )

    def __repr__(self) -> str:
        return "ProviderAPI(providers=%d)" % len(self._providers)


def list_leftover_keys(store_view: Mapping[str, Any],
                       app_prefix: str) -> dict:
    """List entries under the app prefix, names plus dates only."""
    if not app_prefix:
        raise ValueError("app_prefix is required")
    entries = []
    for name in store_view:
        if not isinstance(name, str) or not name.startswith(app_prefix):
            continue
        try:
            item = store_view[name]
        except KeyError:
            continue
        stamp = ""
        if isinstance(item, Mapping):
            stamp = item.get("last_used_at", "")
        entries.append({"name": name, "last_used_at": str(stamp or "")})
    entries.sort(key=lambda entry: entry["name"])
    return {"entries": entries}


def request_delete_entry(store: Any, audit_sink: Any, *, name: str,
                         app_prefix: str, confirmed: bool,
                         session_token: str | None,
                         live_provider_ids: Collection[str],
                         reason: str) -> dict:
    """Delete one leftover entry only when every M-P4-144..147 hold."""
    if not app_prefix:
        raise ValueError("app_prefix is required")
    if not isinstance(name, str) or not name.startswith(app_prefix):
        return {"removed": False, "reason": NOT_OWN_PREFIX,
                "rule": "M-P4-144", "entry": name}
    try:
        present = name in store
    except TypeError:
        present = False
    if not present:
        return {"removed": False, "reason": NOT_FOUND,
                "rule": "M-P4-145", "entry": name}
    if live_provider_ids is not None and name in live_provider_ids:
        return {"removed": False, "reason": LIVE_LINKED,
                "rule": "M-P4-146", "entry": name}
    if confirmed is not True:
        return {"removed": False, "reason": CONFIRM_REQUIRED,
                "rule": "M-P4-147", "entry": name}
    if not session_token:
        return {"removed": False, "reason": TOKEN_REQUIRED,
                "rule": "M-P4-147", "entry": name}
    del store[name]
    audit_sink.append(
        {"entry": name, "reason": reason, "at": _utcnow_iso()})
    return {"removed": True, "entry": name}


__all__ = [
    "ProviderContracts",
    "ProviderAPI",
    "PROVIDER_UNEVIDENCED",
    "NON_DEFAULT_EXAMPLE",
    "PROVIDER_STATUSES",
    "CREDENTIAL_ENTRY_MISSING",
    "NOT_OWN_PREFIX",
    "NOT_FOUND",
    "LIVE_LINKED",
    "CONFIRM_REQUIRED",
    "TOKEN_REQUIRED",
    "LEFTOVER_RULES",
    "list_leftover_keys",
    "request_delete_entry",
]
