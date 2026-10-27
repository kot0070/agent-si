"""M-MISS K13 missing rows: behaviour proofs for the four OPEN rows.

Covers B0B-UNCOVERED_BP05-2 (register/lookup/health views),
B0B-UNCOVERED_BP05-3 (no execution/routing/secret surface),
B0B-UNCOVERED_ARCH-169 (same name distinct across runtimes) and
B0B-UNCOVERED_BP05-54 (bulk handoff re-issued as ArtifactRef) through the
real entry points (agent_si.storage.extension_registries classes and
agent_si.domain.contracts.ArtifactRef).

Names, payloads and runtimes do not overlap tests/k13/test_registries.py:
heron-* names, heron-lab/heron-edge/heron-cloud runtimes, cross-runtime
health/list behaviour, blob dedup across names, ref equality semantics.
"""

import hashlib
import sys
from dataclasses import fields
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from agent_si.domain.contracts import ArtifactRef
from agent_si.storage import extension_registries as registries

ALL = (
    registries.ProviderRegistry,
    registries.ModelRegistry,
    registries.CapabilityRegistry,
    registries.ToolRegistry,
    registries.KnowledgeSourceRegistry,
    registries.VerifierRegistry,
    registries.AuditorRegistry,
)

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

ALLOWED_PUBLIC = {"register", "lookup", "health", "list", "entries", "handoff"}


def test_bp05_2_registration_lookup_health_views():
    reg = registries.KnowledgeSourceRegistry()
    assert reg.lookup("heron-field-notes", "heron-lab") is None
    payload = {"label": "heron-field-notes", "tier": "heron-bronze"}
    stored = reg.register("heron-field-notes", payload, runtime="heron-lab")
    assert stored == {
        "name": "heron-field-notes",
        "runtime": "heron-lab",
        "payload": payload,
    }
    stored["runtime"] = "mutated"
    assert reg.lookup("heron-field-notes", "heron-lab") == {
        "name": "heron-field-notes",
        "runtime": "heron-lab",
        "payload": payload,
    }
    assert reg.health("heron-field-notes", "heron-lab") == {
        "status": "registered",
        "name": "heron-field-notes",
        "runtime": "heron-lab",
    }
    assert reg.health("heron-absent-notes", "heron-lab") == {
        "status": "missing",
        "name": "heron-absent-notes",
        "runtime": "heron-lab",
    }
    second = reg.register("heron-lab-log", {"tier": "heron-silver"}, runtime="heron-lab")
    assert reg.list() == [
        {
            "name": "heron-field-notes",
            "runtime": "heron-lab",
            "payload": payload,
        },
        second,
    ]
    assert reg.entries() == reg.list()


def test_bp05_3_no_execution_routing_secret_surface():
    for cls in ALL:
        public = {
            member
            for member in dir(cls)
            if not (member.startswith("__") and member.endswith("__"))
        }
        assert public <= ALLOWED_PUBLIC, (cls.__name__, public)
        for member in public:
            core = member.lower().replace("runtime", "")
            for frag in FORBIDDEN:
                assert frag not in core, (cls.__name__, member, frag)
        reg = cls()
        entry = reg.register("heron-probe", {"note": "heron-plain"})
        assert set(entry) == {"name", "runtime", "payload"}
        for field in entry:
            core = field.lower().replace("runtime", "")
            for frag in FORBIDDEN:
                assert frag not in core, (cls.__name__, field, frag)


def test_arch169_same_name_distinct_runtimes():
    reg = registries.ModelRegistry()
    name = "heron-shared-weights"
    edge = reg.register(name, {"site": "heron-edge-dc"}, runtime="heron-edge")
    cloud = reg.register(name, {"site": "heron-cloud-dc"}, runtime="heron-cloud")
    assert reg.lookup(name, "heron-edge") == edge
    assert reg.lookup(name, "heron-cloud") == cloud
    assert edge != cloud
    assert reg.health(name, "heron-edge")["status"] == "registered"
    assert reg.health(name, "heron-cloud")["status"] == "registered"
    assert reg.health(name, "heron-missing-dc")["status"] == "missing"
    assert reg.lookup(name) is None
    assert len(reg.list()) == 2
    assert len(reg.entries()) == 2


def test_bp05_54_bulk_handoff_reissued_as_artifactref():
    reg = registries.ToolRegistry()
    data = b"heron-bulk-payload-" * 64
    digest = hashlib.sha256(data).hexdigest()
    first = reg.handoff("heron-blob-a", data)
    assert isinstance(first, ArtifactRef)
    assert first.hash == digest
    assert first.hash_algorithm == "sha256"
    assert first.size == len(data)
    assert digest in first.artifact_id
    second = reg.handoff("heron-blob-b", bytes(data))
    assert second == first
    assert len(reg._blobs) == 1
    other = b"heron-other-payload-" * 64
    third = reg.handoff("heron-blob-a", other)
    assert third != first
    assert third.hash == hashlib.sha256(other).hexdigest()
    assert len(reg._blobs) == 2
    text_ref = reg.handoff("heron-note", "heron-text")
    assert isinstance(text_ref, ArtifactRef)
    assert text_ref.size == len("heron-text".encode("utf-8"))
    for ref in (first, third, text_ref):
        for field in fields(ref):
            assert getattr(ref, field.name) != data
