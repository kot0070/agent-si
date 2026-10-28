"""K13 extension registries (Manifest section 44 lookup/health views + bulk handoff).

Implements ProviderRegistry, ModelRegistry, CapabilityRegistry,
ToolRegistry, KnowledgeSourceRegistry, VerifierRegistry and
AuditorRegistry with real in-memory behavior shared through one private
base class:

- register(name, payload, runtime="default") stores an entry verbatim
  under neutral keys; lookup(name, runtime="default") returns a copy.
- entries are keyed (runtime, name): the same name under two runtimes
  holds two distinct entries.
- health(name, runtime="default") reports status + name + runtime.
- list()/entries() replay stored entries in insertion order.
- handoff(name, content, runtime="default") stores bulk bytes/str once
  by sha256 and returns an ArtifactRef (no repeated inline copy).

No network, no model calls. Member and field names stay neutral: no
execution/selection/secret vocabulary anywhere on the classes.
"""

from __future__ import annotations

import hashlib
import threading
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

from agent_si.domain.contracts import ArtifactRef

DEFAULT_RUNTIME = "default"
_MEDIA_TYPE_BYTES = "application/octet-stream"


def _key(name: str, runtime: str) -> Tuple[str, str]:
    if not isinstance(name, str) or not name:
        raise ValueError("registry entry needs a non-empty name")
    if not isinstance(runtime, str) or not runtime:
        raise ValueError("registry entry needs a non-empty runtime")
    return (runtime, name)


class _ExtensionRegistryBase:
    """Shared (runtime, name) keyed store plus sha256 bulk-handoff mechanics."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._order: List[Tuple[str, str]] = []
        self._blobs: Dict[str, bytes] = {}

    def register(
        self, name: str, payload: Any, runtime: str = DEFAULT_RUNTIME
    ) -> Dict[str, Any]:
        """Store *payload* verbatim under *name* for *runtime*; return a copy."""
        key = _key(name, runtime)
        stored = dict(payload) if isinstance(payload, Mapping) else payload
        entry = {"name": name, "runtime": runtime, "payload": stored}
        with self._lock:
            if key not in self._entries:
                self._order.append(key)
            self._entries[key] = entry
            return dict(entry)

    def lookup(
        self, name: str, runtime: str = DEFAULT_RUNTIME
    ) -> Optional[Dict[str, Any]]:
        """Return a copy of the (runtime, name) entry, or None when absent."""
        with self._lock:
            entry = self._entries.get(_key(name, runtime))
            return dict(entry) if entry is not None else None

    def health(
        self, name: str, runtime: str = DEFAULT_RUNTIME
    ) -> Dict[str, Any]:
        """Report status + name + runtime for one (runtime, name) slot."""
        with self._lock:
            known = _key(name, runtime) in self._entries
        return {
            "status": "registered" if known else "missing",
            "name": name,
            "runtime": runtime,
        }

    def list(self) -> List[Dict[str, Any]]:
        """Replay all stored entries in insertion order."""
        with self._lock:
            return [dict(self._entries[key]) for key in self._order]

    def entries(self) -> List[Dict[str, Any]]:
        """Alias of list(): all stored entries in insertion order."""
        return self.list()

    def handoff(
        self,
        name: str,
        content: Union[bytes, str],
        runtime: str = DEFAULT_RUNTIME,
    ) -> Any:
        """Store bulk *content* once by sha256; return its ArtifactRef."""
        _key(name, runtime)
        if isinstance(content, str):
            data = content.encode("utf-8")
        else:
            data = bytes(content)
        digest = hashlib.sha256(data).hexdigest()
        with self._lock:
            if digest not in self._blobs:
                self._blobs[digest] = data
        return ArtifactRef(
            artifact_id="artifact-" + digest,
            hash=digest,
            hash_algorithm="sha256",
            media_type=_MEDIA_TYPE_BYTES,
            size=len(data),
        )


class ProviderRegistry(_ExtensionRegistryBase):
    """Manifest section 44 provider registry (lookup + health views)."""


class ModelRegistry(_ExtensionRegistryBase):
    """Manifest section 44 model registry (lookup + health views)."""


class CapabilityRegistry(_ExtensionRegistryBase):
    """Manifest section 44 capability registry (lookup + health views)."""


class ToolRegistry(_ExtensionRegistryBase):
    """Manifest section 44 tool registry (lookup + health views)."""


class KnowledgeSourceRegistry(_ExtensionRegistryBase):
    """Manifest section 44 knowledge source registry (lookup + health views)."""


class VerifierRegistry(_ExtensionRegistryBase):
    """Manifest section 44 verifier registry (lookup + health views)."""


class AuditorRegistry(_ExtensionRegistryBase):
    """Manifest section 44 auditor registry (lookup + health views)."""


__all__ = [
    "ProviderRegistry",
    "ModelRegistry",
    "CapabilityRegistry",
    "ToolRegistry",
    "KnowledgeSourceRegistry",
    "VerifierRegistry",
    "AuditorRegistry",
]
