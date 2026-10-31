"""Module-level provider facade functions (frozen K04 section 3.2 surface).

Thin delegation over
:class:`agent_si.providers.registry.provider_api.ProviderAPI`: every
function below carries the EXACT frozen name, parameter list and order
from ``src/agent_si/routing/interface.py`` (``descriptor, secret_ref`` /
``provider_id`` / ``only_evidenced`` / ``provider_instance`` /
``health``) with no extra parameters and no defaults, and forwards to
the matching :class:`ProviderAPI` method with real behavior (no
reimplementation, no placeholder data).

Model placement: ``register_provider`` passes ``descriptor`` and
``secret_ref`` straight through, so the model comes from inside the
descriptor mapping itself (``descriptor["model"]`` or
``descriptor.model``); the facade adds no ``model`` keyword because the
frozen signature has none.

Backing instance: callers with a provisioned stack call
:func:`configure` with their own :class:`ProviderAPI` (registry plus
real credential store, audit sink and usage probe). Without
:func:`configure` the functions fall back to a lazy in-memory default
built here from :class:`ProviderRegistry` plus a minimal ephemeral
credential store and audit sink (standard library only). The default
exists so the facade is usable standalone; its store entries are seeded
explicitly after provisioning, and :func:`remove_provider` surfaces
``CREDENTIAL_ENTRY_MISSING`` when the entry is absent, exactly like the
wired path. Standard library plus ``agent_si`` only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, List, Optional

import json as _json
import os as _os

from .provider_api import ProviderAPI, ProviderContracts
from .registry import ProviderRegistry

if TYPE_CHECKING:
    from agent_si.routing.interface import SecretRef


class _MemoryCredentialStore:
    """Ephemeral credential-store stand-in for the lazy default backing.

    Entries are seeded explicitly after provisioning; ``has``/``delete``
    mirror the store port :class:`ProviderAPI` removes through. The save
    route writes through ``set_secret`` (plus ``store``/``put``/``set``
    aliases); call-time readers use ``get_secret`` (plus ``get``/
    ``retrieve``/``read`` aliases and mapping read). Values never appear
    in repr or errors.
    """

    def __init__(self) -> None:
        self._entries: dict = {}

    def seed(self, secret_id: str, payload: Any = "ephemeral-entry") -> None:
        self._entries[secret_id] = payload

    def set_secret(self, secret_id: str, value: Any) -> None:
        if not isinstance(secret_id, str) or not secret_id:
            raise ValueError("secret_id is required")
        if not isinstance(value, str) or not value:
            raise ValueError("key value is required")
        self._entries[secret_id] = value

    def store(self, secret_id: str, value: Any) -> None:
        self.set_secret(secret_id, value)

    def put(self, secret_id: str, value: Any) -> None:
        self.set_secret(secret_id, value)

    def set(self, secret_id: str, value: Any) -> None:
        self.set_secret(secret_id, value)

    def store_secret(self, secret_id: str, value: Any) -> None:
        self.set_secret(secret_id, value)

    def get_secret(self, secret_id: str) -> str:
        try:
            value = self._entries[secret_id]
        except KeyError:
            raise KeyError(secret_id) from None
        if isinstance(value, dict):
            inner = value.get("value", "")
            if isinstance(inner, str) and inner:
                return inner
            raise KeyError(secret_id)
        if isinstance(value, str) and value:
            return value
        return str(value)

    def get(self, secret_id: str, default: Any = None) -> Any:
        try:
            return self.get_secret(secret_id)
        except (KeyError, ValueError):
            return default

    def retrieve(self, secret_id: str) -> str:
        return self.get_secret(secret_id)

    def read(self, secret_id: str) -> str:
        return self.get_secret(secret_id)

    def get_secret_value(self, secret_id: str) -> str:
        return self.get_secret(secret_id)

    def __getitem__(self, secret_id: str) -> dict:
        try:
            value = self._entries[secret_id]
        except KeyError:
            raise KeyError(secret_id) from None
        if isinstance(value, dict):
            return dict(value)
        return {"value": self.get_secret(secret_id)}

    def __contains__(self, secret_id: object) -> bool:
        return isinstance(secret_id, str) and secret_id in self._entries

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(list(self._entries))

    def __len__(self) -> int:
        return len(self._entries)

    def has(self, secret_id: str) -> bool:
        return secret_id in self._entries

    def delete(self, secret_id: str) -> None:
        if secret_id not in self._entries:
            raise KeyError(secret_id)
        del self._entries[secret_id]

    def __delitem__(self, secret_id: str) -> None:
        self.delete(secret_id)

    def __repr__(self) -> str:
        return "MemoryCredentialStore(entries=%d)" % len(self._entries)


class _MemoryAuditSink:
    """Ephemeral audit sink for the lazy default backing."""

    def __init__(self) -> None:
        self.records: list = []

    def append(self, record: Any) -> None:
        self.records.append(dict(record))


class _FileAuditSink:
    """Persistent append-only JSON-lines audit sink for the served OS stack.

    One record per append to ``path`` (never the secret value); readable
    back after restart via :attr:`records`. Only entry names travel here.
    """

    _SECRET_KEYS = frozenset({
        "key_value", "value", "secret", "secret_value", "key",
        "api_key", "apikey", "token", "password", "blob",
    })

    def __init__(self, path: str) -> None:
        if not isinstance(path, str) or not path.strip():
            raise ValueError("audit path is required")
        self._path = str(path)
        parent = _os.path.dirname(_os.path.abspath(self._path))
        if parent:
            _os.makedirs(parent, exist_ok=True)
        with open(self._path, "a", encoding="utf-8"):
            pass

    @property
    def path(self) -> str:
        return self._path

    def append(self, record: Any) -> None:
        try:
            if isinstance(record, dict):
                cleaned = dict(record)
            else:
                cleaned = {"entry": str(record)}
        except Exception:
            cleaned = {"entry": "unrepresentable"}
        for _k in list(cleaned.keys()):
            if str(_k).lower() in self._SECRET_KEYS:
                cleaned.pop(_k, None)
        line = _json.dumps(cleaned, ensure_ascii=False, sort_keys=True)
        with open(self._path, "a", encoding="utf-8") as _fh:
            _fh.write(line + "\n")

    @property
    def records(self) -> list:
        out: list = []
        try:
            with open(self._path, "r", encoding="utf-8") as _fh:
                for _line in _fh:
                    _line = _line.strip()
                    if not _line:
                        continue
                    try:
                        out.append(_json.loads(_line))
                    except Exception:
                        continue
        except FileNotFoundError:
            return []
        return out

    def __repr__(self) -> str:
        return "FileAuditSink(path=%r)" % (self._path,)


_configured_api: ProviderAPI | None = None


def configure(api: ProviderAPI | None) -> ProviderAPI | None:
    """Bind the backing :class:`ProviderAPI` (pass None to reset to lazy).

    Returns the previously bound instance (None when the lazy default
    was in effect) so callers can restore it. The argument must expose
    the five delegated methods; anything else raises ValueError.
    """
    global _configured_api
    previous = _configured_api
    if api is None:
        _configured_api = None
        return previous
    for name in (
        "register_provider",
        "get_provider",
        "list_providers",
        "record_health",
        "remove_provider",
    ):
        if not callable(getattr(api, name, None)):
            raise ValueError(
                "configure needs a ProviderAPI with %r" % (name,)
            )
    _configured_api = api
    return previous


def _current() -> ProviderAPI:
    if _configured_api is not None:
        return _configured_api
    return ProviderAPI(
        ProviderRegistry(), _MemoryCredentialStore(), _MemoryAuditSink()
    )


def ephemeral_stack() -> tuple:
    """Provision one app-scoped ProviderAPI stack (ephemeral store+sink).

    For integration hosts (e.g. backend create_app) that own the whole
    stack's lifecycle: a fresh ProviderRegistry plus the sanctioned
    ephemeral credential store and audit sink. Entries are seeded
    explicitly after provisioning (same rule as the lazy default).
    Returns (api, credential_store, audit_sink).
    """
    store = _MemoryCredentialStore()
    sink = _MemoryAuditSink()
    return ProviderAPI(ProviderRegistry(), store, sink), store, sink


def memory_stack() -> tuple:
    """Provision one memory-backed stack (tests and isolation probes).

    Same shape as :func:`ephemeral_stack` with the full value port
    (``set_secret``/``get_secret`` plus ``has``/``delete``); the save
    route writes through it and the disconnect path removes through it.
    """
    return ephemeral_stack()


def os_stack(*, label_suffix: str = "",
             namespace: str | None = None,
             timeout_s: float = 5.0,
             audit_path: str | None = None) -> tuple:
    """Provision one OS-backed stack (Windows Credential Manager).

    Entries live under the product namespace (leftover-keys ``"app:"``)
    with the optional label suffix (HD live run uses ``"TEST"``).
    The audit sink is the persistent append-only JSON-lines file at
    ``audit_path`` (never the secret value). Raises OSError off Windows;
    callers surface it, never a silent memory fallback.
    """
    if _os.name != "nt":
        raise OSError("OS credential store needs Windows")
    from .os_credential_store import APP_NAMESPACE, OSCredentialStore

    store = OSCredentialStore(
        label_suffix=str(label_suffix or ""),
        namespace=str(namespace or APP_NAMESPACE),
        timeout_s=float(timeout_s or 5.0),
    )
    if audit_path is None:
        audit_path = _os.path.join(_os.getcwd(), "provider_audit.jsonl")
    sink = _FileAuditSink(str(audit_path))
    return ProviderAPI(ProviderRegistry(), store, sink), store, sink


def register_provider(descriptor: ProviderContracts,
                      secret_ref: SecretRef) -> ProviderContracts:
    """Key-only connect; the model travels inside the descriptor mapping."""
    return _current().register_provider(descriptor, secret_ref)


def get_provider(provider_id: str) -> Optional[ProviderContracts]:
    """Return the provider view, or None for an unknown id (exact match)."""
    return _current().get_provider(provider_id)


def list_providers(only_evidenced: bool) -> List[ProviderContracts]:
    """List provider views, stable-sorted; only evidenced when asked."""
    return _current().list_providers(only_evidenced)


def record_health(provider_id: str, provider_instance: Optional[str],
                  health: str) -> ProviderContracts:
    """Record per-instance health; the latest check wins."""
    return _current().record_health(provider_id, provider_instance, health)


def remove_provider(provider_id: str) -> None:
    """Remove the provider cleanly, including the store entry."""
    return _current().remove_provider(provider_id)


__all__ = [
    "ProviderContracts",
    "configure",
    "ephemeral_stack",
    "memory_stack",
    "os_stack",
    "register_provider",
    "get_provider",
    "list_providers",
    "record_health",
    "remove_provider",
]
