"""K09-A retrieval engine and KB behaviour home, STEP2.

Owns the manifest-touch gate (_manifest_touched): read_section refuses
section content until manifest_lookup has touched the kb in this process.
Owns the telemetry records (_RECORDS via _record) and the savings report;
record_* also forwards best-effort to the lane-B telemetry module.
attach/detach/list wrappers live here so registry.py stays storage-only:
models <- registry <- retriever, no cycles. The frozen interface module
holds types and signatures only; this module holds every behaviour body.
"""

from __future__ import annotations

import hashlib
from typing import Any, Optional

try:  # portable first (PYTHONPATH=src or tests inserting src)
    from agent_si.kb import guard, models, registry
    from agent_si.kb.models import (
        InstructionBlockedError,
        KnowledgeChunk,
        KnowledgeSource,
        ManifestRequiredError,
        RetrievalPolicy,
        WholeKbReadRefused,
    )
except ImportError:  # legacy root-based harness (import src.agent_si...)
    from src.agent_si.kb import guard, models, registry
    from src.agent_si.kb.models import (
        InstructionBlockedError,
        KnowledgeChunk,
        KnowledgeSource,
        ManifestRequiredError,
        RetrievalPolicy,
        WholeKbReadRefused,
    )

try:
    from src.agent_si.domain.contracts import ArtifactRef
except ImportError:  # alternate layout: the agent_si/ directory itself on sys.path
    from agent_si.domain.contracts import ArtifactRef

import sys as _mod_sys

_mod_sys.modules.setdefault(
    "src." + __name__ if not __name__.startswith("src.") else __name__[4:],
    _mod_sys.modules[__name__],
)
"""Dual-harness identity: root-based (src.*) and src-based (agent_si.*)
imports resolve to this same module object, so module-global lane
state (_manifest_touched, _RECORDS) is shared whatever path is used."""

_manifest_touched: set = set()

_WHOLE_KB_IDS = ("*", "all", "")

_RECORDS: list = []


def _record(kind: str, role: str, agent: str, tokens: int, cost: float) -> None:
    _RECORDS.append(
        {"role": role, "agent": agent, "tokens": tokens, "cost": cost,
         "kind": kind}
    )
    try:
        from agent_si.kb import telemetry as _lane_b
    except ImportError:
        from src.agent_si.kb import telemetry as _lane_b

        _forward = {
            "hit": _lane_b.record_hit,
            "miss": _lane_b.record_miss,
            "web_fallback": _lane_b.record_web_fallback,
        }[kind]
        _forward(role, agent, tokens, cost)
    except Exception:
        pass


def discard_manifest_touch(kb_id: str) -> None:
    """Forget one kb's manifest touch (used on attach/detach epochs)."""
    _manifest_touched.discard(kb_id)


def attach_kb(source: KnowledgeSource) -> str:
    kb_id = registry.register(source)
    # Attaching starts a new measurement epoch: tests share one pytest
    # process and module-global telemetry would otherwise accumulate.
    _RECORDS.clear()
    discard_manifest_touch(kb_id)
    return kb_id


def detach_kb(kb_id: str) -> None:
    registry.unregister(kb_id)
    discard_manifest_touch(kb_id)


def list_kbs(project_id: str, role: Optional[str] = None) -> list[KnowledgeSource]:
    return registry.sources_for(project_id, role)


def set_role_kb_enabled(project_id: str, role: str, kb_id: str, enabled: bool) -> None:
    registry.set_enabled(project_id, role, kb_id, enabled)


def manifest_lookup(kb_id: str, query: str) -> list[str]:
    """Manifest lookup: KeyError when unattached, else touch + find."""
    if not registry.is_attached(kb_id):
        raise KeyError(kb_id)
    _manifest_touched.add(kb_id)
    return registry.find_sections(kb_id, query)


def read_section(kb_id: str, section_id: str) -> KnowledgeChunk:
    """Read one section: whole-KB refusal, manifest gate, guard screen."""
    if section_id in _WHOLE_KB_IDS:
        raise WholeKbReadRefused("whole-KB read refused for %r" % (kb_id,))
    if kb_id not in _manifest_touched:
        raise ManifestRequiredError("manifest lookup required for %r" % (kb_id,))
    if not registry.is_attached(kb_id):
        raise KeyError(kb_id)
    text = registry.section_text(kb_id, section_id)
    evidence_ref = guard.screen(text)
    if evidence_ref is not None:
        raise InstructionBlockedError(
            "instruction content blocked in %s#%s (%s)"
            % (kb_id, section_id, evidence_ref)
        )
    tokens = models.count_tokens(text)
    return KnowledgeChunk(
        kb_id=kb_id,
        section_id=section_id,
        text=text,
        tokens=tokens,
        instruction_status="DATA_ONLY",
        citation="%s#%s" % (kb_id, section_id),
    )


def retrieve(
    query: str,
    project_id: str,
    role: str,
    policy: Optional[RetrievalPolicy] = None,
) -> tuple[list[KnowledgeChunk], dict[str, Any]]:
    """Retrieve across the role-visible KBs; miss/block shapes included."""
    sources = registry.sources_for(project_id, role)
    if not sources:
        return [], models.new_section_log()
    chunks: list[KnowledgeChunk] = []
    touches: list[Any] = []
    for source in sources:
        for section_id in manifest_lookup(source.kb_id, query):
            chunk = read_section(source.kb_id, section_id)
            chunks.append(chunk)
            touches.append(
                models.SectionTouch(source.kb_id, section_id, chunk.tokens)
            )
    token_cost = sum(chunk.tokens for chunk in chunks)
    section_log = {"touches": touches, "token_cost": token_cost}
    if chunks:
        tokens = token_cost
        record_hit(role, "kb-retriever", tokens, tokens * 0.001)
    else:
        tokens = models.count_tokens(query)
        record_miss(role, "kb-retriever", tokens, tokens * 0.001)
        if policy is not None and policy.web_second_allowed:
            record_web_fallback(
                role, "kb-retriever", tokens, tokens * 0.001
            )
    return chunks, section_log


def record_hit(role: str, agent: str, tokens: int, cost: float) -> None:
    _record("hit", role, agent, tokens, cost)


def record_miss(role: str, agent: str, tokens: int, cost: float) -> None:
    _record("miss", role, agent, tokens, cost)


def record_web_fallback(role: str, agent: str, tokens: int, cost: float) -> None:
    _record("web_fallback", role, agent, tokens, cost)


def savings_report() -> dict[str, Any]:
    hits = sum(1 for record in _RECORDS if record["kind"] == "hit")
    misses = sum(1 for record in _RECORDS if record["kind"] == "miss")
    web_fallbacks = sum(
        1 for record in _RECORDS if record["kind"] == "web_fallback"
    )
    tokens = sum(record["tokens"] for record in _RECORDS)
    cost = sum(record["cost"] for record in _RECORDS)
    return {
        "hits": hits,
        "misses": misses,
        "web_fallbacks": web_fallbacks,
        "tokens": tokens,
        "cost": cost,
    }


# K09UT1 handoff: size-based KB handoff packaging. Retrieval results at or
# below HANDOFF_INLINE_TOKEN_LIMIT travel inline; larger results travel by
# ArtifactRef (payload stored once by sha256; only the reference crosses
# the provider boundary). instruction_status stays DATA_ONLY either way;
# every chunk was already screened by guard.screen at read time.

HANDOFF_INLINE_TOKEN_LIMIT = 500

_ARTIFACT_BLOBS: dict[str, bytes] = {}


def _chunk_field(chunk: Any, name: str, default: Any) -> Any:
    """Read one chunk field from a chunk object or a served JSON mapping."""
    if hasattr(chunk, name):
        return getattr(chunk, name)
    if isinstance(chunk, dict):
        return chunk.get(name, default)
    return default


def _chunk_status(chunk: Any) -> str:
    """Chunk status string; anything but DATA_ONLY refuses packaging."""
    status = _chunk_field(chunk, "instruction_status", "")
    return status if isinstance(status, str) else ""


def _chunk_tokens(chunk: Any) -> int:
    """Chunk token count from a chunk object or a served JSON mapping."""
    tokens = _chunk_field(chunk, "tokens", 0)
    return tokens if isinstance(tokens, int) else 0


def _handoff_line(chunk: Any) -> str:
    """One cited markdown section for a chunk object or JSON mapping."""
    citation = _chunk_field(chunk, "citation", "")
    text = _chunk_field(chunk, "text", "")
    return f"# {citation}\n\n{text}"


def _handoff_payload(items: list) -> bytes:
    """Cited payload bytes for one packaged handoff.

    Accepts chunk objects and served JSON mappings alike, so a handoff
    that crossed the served JSON boundary still resolves to its bytes.
    """
    lines = [_handoff_line(chunk) for chunk in items]
    return "\n\n---\n\n".join(lines).encode("utf-8")


def _artifact_ref_for(payload: bytes) -> ArtifactRef:
    """Store payload once by sha256; return its ArtifactRef."""
    digest = hashlib.sha256(payload).hexdigest()
    _ARTIFACT_BLOBS.setdefault(digest, payload)
    return ArtifactRef(
        artifact_id="artifact-" + digest,
        hash=digest,
        hash_algorithm="sha256",
        media_type="text/markdown",
        size=len(payload),
    )


def package_handoff(chunks: list) -> dict[str, Any]:
    """Package retrieved chunks: inline when small, ArtifactRef when large.

    Small results keep every KnowledgeChunk inline. Large results store
    the cited payload once and return its ArtifactRef; the raw text does
    not travel in the handoff dict. Every packaged chunk must carry
    DATA_ONLY; anything else is refused before a handoff is built.
    Chunk objects and served JSON mappings are both accepted.
    """
    items = list(chunks)
    for chunk in items:
        if _chunk_status(chunk) != "DATA_ONLY":
            raise InstructionBlockedError(
                "non-DATA_ONLY chunk refused at handoff packaging"
            )
    token_cost = sum(_chunk_tokens(chunk) for chunk in items)
    if token_cost <= HANDOFF_INLINE_TOKEN_LIMIT:
        return {
            "mode": "inline",
            "chunks": items,
            "token_cost": token_cost,
            "instruction_status": "DATA_ONLY",
        }
    payload = _handoff_payload(items)
    ref = _artifact_ref_for(payload)
    return {
        "mode": "ref",
        "ref": ref,
        "citations": [_chunk_field(chunk, "citation", "") for chunk in items],
        "token_cost": token_cost,
        "instruction_status": "DATA_ONLY",
    }


def resolve_handoff(handoff: dict[str, Any]) -> bytes:
    """Resolve a packaged handoff back to its payload bytes.

    Inline handoffs rebuild the cited payload from their chunks; ref
    handoffs look the payload up by ArtifactRef hash. Unknown refs raise
    KeyError (fail closed, never fabricated).
    """
    if handoff.get("mode") == "inline":
        return _handoff_payload(handoff.get("chunks", []))
    ref = handoff["ref"]
    key = ref.hash if hasattr(ref, "hash") else ref["hash"]
    return _ARTIFACT_BLOBS[key]


def retrieve_handoff(
    query: str,
    project_id: str,
    role: str,
    policy: Optional[RetrievalPolicy] = None,
) -> dict[str, Any]:
    """Retrieve through the real KB layer, then package the handoff."""
    chunks, _section_log = retrieve(query, project_id, role, policy)
    return package_handoff(chunks)

# FB2B4 staged-KB-rows consumer + auditor-eligibility seam (F04 re-check).
#
# The F04 fresh-audit chain stays NO_ELIGIBLE_AUDITOR with openai as the
# only other model because the auditor registry only sees its own
# in-memory candidate evidence store, where the openai candidate carries
# no capability evidence refs. After B1 the bound model-KB catalog holds
# staged rows with sourced fields, so eligibility is re-checked against
# those rows. This consumer bridges the two stores: it reads the live
# bound model-KB catalog (model_kb.kb.bound_catalog -- a DIFFERENT store
# from the registry evidence store and from this package's
# attached-source store) and derives capability evidence refs for one
# exact provider/model pair. UNKNOWN stays UNKNOWN: a row without
# sourced capability fields, or with UNKNOWN prices, yields no evidence
# -- never an invented ref -- and a fail-closed () is returned whenever
# the store is unreadable.

#: Bound-catalog fields that prove what a model can do (sourced values
#: only; negatives and UNKNOWN never count as evidence).
_KB_AUDITOR_CAPABILITY_FIELDS = ("modalities", "tool_calling", "reasoning")

#: Bound-catalog price fields that must be known: an unpriced row is not
#: a B1-complete row, so it never confers eligibility either.
_KB_AUDITOR_PRICE_FIELDS = ("input_token_price", "output_token_price")


def _kb_field_value(fields, name):
    """Sourced value of one bound-catalog field, or None when unevidenced.

    None when the field entry is missing, its value is None or the
    UNKNOWN marker, or its source is missing/UNKNOWN: evidence refs only
    ever cite per-field sourced evidence, never bare labels.
    """
    item = fields.get(name) if isinstance(fields, dict) else None
    if not isinstance(item, dict):
        return None
    value = item.get("value")
    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() in ("", "unknown"):
        return None
    source = item.get("source")
    if not isinstance(source, str) or not source.strip():
        return None
    if source.strip().lower() == "unknown":
        return None
    return value


def _kb_affirmative(value):
    """True when a sourced KB value affirms a capability (no negatives)."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return bool(value.strip()) and value.strip().lower() != "unknown"
    if isinstance(value, (list, tuple)):
        return any(
            str(item).strip() and str(item).strip().lower() != "unknown"
            for item in value
        )
    return True


def _kb_price_known(value):
    """True only for a real numeric price; UNKNOWN is never a price."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def auditor_capability_evidence(provider_id, model):
    """Capability evidence refs for one pair from staged KB rows.

    Reads the live bound model-KB catalog for the exact
    (provider_id, model) pair and returns ``kb:<provider>/<model>#<field>``
    refs -- one per sourced capability field plus both price fields -- or
    () when the pair is blank, the row is absent, a price is UNKNOWN, or
    no capability field is affirmed. Prices are never invented and
    UNKNOWN capabilities stay ineligible downstream.
    """
    pid = provider_id.strip() if isinstance(provider_id, str) else ""
    mid = model.strip() if isinstance(model, str) else ""
    if not pid or not mid:
        return ()
    try:
        from agent_si.model_kb import kb as _model_kb
        from agent_si.model_kb import loader as _model_loader
    except ImportError:
        try:
            from src.agent_si.model_kb import kb as _model_kb
            from src.agent_si.model_kb import loader as _model_loader
        except ImportError:
            return ()
    try:
        catalog = _model_kb.bound_catalog()
    except Exception:
        return ()
    if not isinstance(catalog, dict):
        return ()
    row = _model_loader.find_row(catalog, pid, mid)
    if not isinstance(row, dict):
        return ()
    fields = row.get("fields", {})
    if not isinstance(fields, dict):
        return ()
    prices = [_kb_field_value(fields, name)
              for name in _KB_AUDITOR_PRICE_FIELDS]
    if any(value is None or not _kb_price_known(value) for value in prices):
        return ()
    caps = [name for name in _KB_AUDITOR_CAPABILITY_FIELDS
            if _kb_affirmative(_kb_field_value(fields, name))]
    if not caps:
        return ()
    watched = list(caps) + list(_KB_AUDITOR_PRICE_FIELDS)
    return tuple("kb:%s/%s#%s" % (pid, mid, name) for name in watched)
