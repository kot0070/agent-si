"""M-REG extension registries: section-44 lookup/health plus bulk handoff.

Covers extension_registries.py (Provider/Model/Capability/Tool/
KnowledgeSource/Verifier/Auditor registries): register/lookup/health,
(runtime, name) keying, bulk handoff reissued as ArtifactRef, and the
no-execution/no-routing/no-secret member rule.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import hashlib

from agent_si.storage import extension_registries as registries
from agent_si.domain.contracts import ArtifactRef

ALL = (
    registries.ProviderRegistry,
    registries.ModelRegistry,
    registries.CapabilityRegistry,
    registries.ToolRegistry,
    registries.KnowledgeSourceRegistry,
    registries.VerifierRegistry,
    registries.AuditorRegistry,
)

NAMES = {
    "ProviderRegistry": "acme-cloud",
    "ModelRegistry": "acme-large-1",
    "CapabilityRegistry": "acme-vision",
    "ToolRegistry": "acme-search",
    "KnowledgeSourceRegistry": "acme-docs",
    "VerifierRegistry": "acme-check",
    "AuditorRegistry": "acme-audit",
}

FORBIDDEN = (
    "execute",
    "exec",
    "run",
    "call",
    "dispatch",
    "route",
    "rout",
    "secret",
    "token",
    "password",
    "credential",
    "api_key",
)


def _payload(cls):
    return {"label": NAMES[cls.__name__], "kind": cls.__name__, "tier": "standard"}


def test_bp05_2_register_lookup_health():
    for cls in ALL:
        reg = cls()
        name = NAMES[cls.__name__]
        assert reg.lookup(name) is None
        payload = _payload(cls)
        stored = reg.register(name, payload)
        assert stored == {"name": name, "runtime": "default", "payload": payload}
        assert reg.lookup(name) == stored
        assert reg.lookup(name, "default") == stored
        assert reg.health(name) == {
            "status": "registered",
            "name": name,
            "runtime": "default",
        }
        assert reg.health("no-such-entry")["status"] == "missing"
        assert reg.list() == [stored]
        assert reg.entries() == [stored]


def test_bp05_3_no_execution_routing_secret_members():
    for cls in ALL:
        for member in dir(cls):
            if member.startswith("__") and member.endswith("__"):
                continue  # Python machinery, not product semantics
            core = member.lower().replace("runtime", "")  # mandated name
            for frag in FORBIDDEN:
                assert frag not in core, (cls.__name__, member, frag)
        reg = cls()
        entry = reg.register("probe", {"note": "plain"})
        for field in entry:
            core = field.lower().replace("runtime", "")
            for frag in FORBIDDEN:
                assert frag not in core, (cls.__name__, field, frag)


def test_arch169_same_name_two_runtimes_distinct():
    for cls in ALL:
        reg = cls()
        name = "shared-%s" % NAMES[cls.__name__]
        first = reg.register(name, {"site": "local"}, runtime="local")
        second = reg.register(name, {"site": "cloud"}, runtime="cloud-eu")
        assert reg.lookup(name, "local") == first
        assert reg.lookup(name, "cloud-eu") == second
        assert first is not second
        assert first != second
        assert reg.health(name, "local")["status"] == "registered"
        assert reg.health(name, "cloud-eu")["status"] == "registered"
        assert len(reg.list()) == 2
        assert len(reg.entries()) == 2


def test_bp05_54_bulk_handoff_reissued_as_artifactref():
    data = bytes((idx * 37 + 11) % 256 for idx in range(100_000))
    assert len(data) == 100_000
    digest = hashlib.sha256(data).hexdigest()
    for cls in ALL:
        reg = cls()
        first = reg.handoff("bulk-blob", data)
        assert isinstance(first, ArtifactRef)
        assert first.hash == digest
        assert first.hash_algorithm == "sha256"
        assert first.size == len(data)
        assert digest in first.artifact_id
        second = reg.handoff("bulk-blob", bytes(data))
        assert second == first  # identical content -> equal ref
        assert len(reg._blobs) == 1  # single stored blob, no inline duplication
        text_ref = reg.handoff("bulk-note", "hello")
        assert isinstance(text_ref, ArtifactRef)
        assert text_ref.size == len("hello".encode("utf-8"))


def test_artifactref_fields_equal_frozen_stub():
    from dataclasses import fields

    from iface.frozen_manifest import interface_stub

    product_fields = [f.name for f in fields(ArtifactRef)]
    stub_fields = [f.name for f in fields(interface_stub.ArtifactRef)]
    assert product_fields == stub_fields
