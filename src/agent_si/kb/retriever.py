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
