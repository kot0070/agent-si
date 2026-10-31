"""Package split into N disjoint parts (frozen K02_INTERFACE sect. 3).

ROW93 split opt-in N disjoint parts, ROW100 bounded context per part,
ROW32 fanout running/queued with over-cap queued never dropped,
R-359 multi-manager settings shape. R-301 decomposition records name the
TeamCard model facts used; ARCH-705 issuance checks the corrections hash;
shared refs are ARTIFACT_REF or SecretRef-only (never raw secrets);
cap queues carry position + estimated start; writes are HOT-WRITE.
V2 ONE-HOME: the shared kernel helpers (ensure_compact_english,
is_compact_english, hot_write_text) live in common.py and TeamCard in
teamcard.py; both are re-exported here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Mapping, Sequence  # noqa: UP035  # frozen-cite K02

from .common import ensure_compact_english, hot_write_text, is_compact_english
from .teamcard import TeamCard, worker_context

MODEL_ID = "meta/muse-spark-1.3-contributor"

ARTIFACT_PREFIX = "artifact://"
ARTIFACT_REF_PREFIX = "ARTIFACT_REF:"
SECRET_REF_KEY = "secret_ref"


class SCOPE_OVERLAP(Exception):
    """Overlapping part scopes refused; message cites conflicting scopes."""


@dataclass(frozen=True)
class PartRef:
    package_id: str
    contract_hash: str
    gate_verdict_ref: str
    audit_verdict_ref: str


@dataclass
class MultiManagerSettings:
    multi_manager_mode: bool
    max_parallel_managers: int
    overlap: bool
    integration_policy: str
    model_pool_per_manager: dict = field(default_factory=dict)


_GATE_SCOPES: dict[str, frozenset[str]] = {}

_ISSUED_CORRECTIONS: dict[str, str] = {}


def make_secret_ref(name: str) -> dict[str, str]:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("secret ref name must be non-empty")
    return {SECRET_REF_KEY: name.strip()}


def is_shared_ref(value: object) -> bool:
    """Shared refs are ARTIFACT_REF strings or SecretRef mappings only."""
    if isinstance(value, str):
        return value.startswith(ARTIFACT_PREFIX) or value.startswith(
            ARTIFACT_REF_PREFIX
        )
    if isinstance(value, Mapping):
        ref = value.get(SECRET_REF_KEY)
        return isinstance(ref, str) and bool(ref.strip()) and len(value) == 1
    return False


def _scope_key(value: str | Mapping[str, Any]) -> str:
    if isinstance(value, Mapping):
        return f"{SECRET_REF_KEY}:{value[SECRET_REF_KEY]}"
    return value


def corrections_hash(corrections: Sequence[Mapping[str, Any]]) -> str:
    """Hash the user-corrections channel state (ARCH-705 issuance check)."""
    items: list[Mapping[str, Any]] = list(corrections)
    for item in items:
        if not isinstance(item, Mapping):
            raise ValueError("corrections must be mappings")
    payload = json.dumps(
        [dict(item) for item in items], sort_keys=True, separators=(",", ":")
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def issued_corrections_hash(package_id: str) -> str | None:
    return _ISSUED_CORRECTIONS.get(package_id)


def split_package(
    package_id: str,
    goal: str,
    context_refs: Sequence[str | Mapping[str, Any]],
    max_parts: int,
    corrections: Sequence[Mapping[str, Any]] = (),
    expected_corrections_hash: str | None = None,
) -> list[PartRef]:
    """Split context refs into N contiguous disjoint parts.

    N = min(max_parts, len(context_refs)); chunk sizes differ by at most 1.
    Shared refs must be ARTIFACT_REF strings or SecretRef mappings (raw
    secrets refused). When expected_corrections_hash is given, issuance is
    refused unless the corrections channel hashes to it (ARCH-705).
    """
    if not isinstance(package_id, str) or not package_id.strip():
        raise ValueError("package_id must be a non-blank string")
    if not isinstance(goal, str) or not goal.strip():
        raise ValueError("goal must be a non-blank string")
    refs = list(context_refs)
    if not refs:
        raise ValueError("context_refs must be non-empty")
    for ref in refs:
        if not is_shared_ref(ref):
            raise ValueError(
                "context_refs must be ARTIFACT_REF or SecretRef-only shared refs"
            )
    if (
        not isinstance(max_parts, int)
        or isinstance(max_parts, bool)
        or max_parts < 1
    ):
        raise ValueError("max_parts must be an int >= 1")
    digest = corrections_hash(list(corrections))
    if expected_corrections_hash is not None and digest != expected_corrections_hash:
        raise ValueError(
            "stale corrections: corrections hash does not match issuance"
        )
    total = len(refs)
    count = min(max_parts, total)
    base, extra = divmod(total, count)
    contract_hash = sha256(
        (package_id + "\0" + goal).encode("utf-8")
    ).hexdigest()
    parts: list[PartRef] = []
    cursor = 0
    for index in range(count):
        size = base + (1 if index < extra else 0)
        chunk = refs[cursor : cursor + size]
        cursor += size
        gate_ref = f"gate:{package_id}:part-{index:03d}"
        audit_ref = f"audit:{package_id}:part-{index:03d}"
        _GATE_SCOPES[gate_ref] = frozenset(_scope_key(ref) for ref in chunk)
        parts.append(
            PartRef(
                package_id=package_id,
                contract_hash=contract_hash,
                gate_verdict_ref=gate_ref,
                audit_verdict_ref=audit_ref,
            )
        )
    _ISSUED_CORRECTIONS[package_id] = digest
    return parts


def validate_disjoint(parts: list[PartRef]) -> None:
    """Return None when part scopes are pairwise disjoint.

    Raises SCOPE_OVERLAP on any pairwise scope intersection (including the
    same ref twice); raises ValueError on an unknown gate_verdict_ref.
    """
    scopes: list[frozenset[str]] = []
    for part in parts:
        try:
            scopes.append(_GATE_SCOPES[part.gate_verdict_ref])
        except KeyError:
            raise ValueError(
                f"unknown gate_verdict_ref: {part.gate_verdict_ref}"
            ) from None
    for first in range(len(scopes)):
        for second in range(first + 1, len(scopes)):
            clash = scopes[first] & scopes[second]
            if clash:
                raise SCOPE_OVERLAP(
                    f"SCOPE_OVERLAP: conflicting scopes {sorted(clash)}"
                )
    return


def fanout(
    parts: list[PartRef],
    settings: MultiManagerSettings,
) -> tuple[list[PartRef], list[PartRef]]:
    """Split parts into (running, queued); union equals input, never dropped."""
    cap = settings.max_parallel_managers
    if not isinstance(cap, int) or isinstance(cap, bool) or cap < 1:
        raise ValueError("max_parallel_managers must be an int >= 1")
    ordered = list(parts)
    if not ordered:
        return ([], [])
    if not settings.multi_manager_mode:
        return (ordered[:1], ordered[1:])
    return (ordered[:cap], ordered[cap:])


FACT_PART_SIZE_VS_MODEL = "part-size-vs-model"
FACT_LONG_CONTEXT_ROUTING = "long-context-routing"
FACT_CHEAP_SMALL_PARTS = "cheap-models-for-small-parts"
KNOWN_FACTS = (
    FACT_PART_SIZE_VS_MODEL,
    FACT_LONG_CONTEXT_ROUTING,
    FACT_CHEAP_SMALL_PARTS,
)

SMALL_PART_THRESHOLD = 8
LONG_CONTEXT_THRESHOLD = 64


@dataclass
class DecompositionRecord:
    record_id: str
    part_id: str
    facts_used: list[str]
    route: str
    reason: str
    artifact_ref: str


def record_decomposition(
    part_id: str, size_units: int, needs_long_context: bool = False
) -> DecompositionRecord:
    """Record which TeamCard model facts routed one part (R-301).

    Facts used always include part-size-vs-model plus the routing fact that
    fired; the reason is compact AI English and the record is served by
    ARTIFACT_REF, never inline.
    """
    if not isinstance(part_id, str) or not part_id.strip():
        raise ValueError("part_id must be a non-blank string")
    if isinstance(size_units, bool) or not isinstance(size_units, int):
        raise ValueError("size_units must be an int")
    if size_units < 0:
        raise ValueError("size_units must be >= 0")
    facts = [FACT_PART_SIZE_VS_MODEL]
    if needs_long_context or size_units > LONG_CONTEXT_THRESHOLD:
        facts.append(FACT_LONG_CONTEXT_ROUTING)
        route = "long-context"
        reason = ensure_compact_english(
            f"part {part_id} routes to long-context model "
            f"using facts {FACT_PART_SIZE_VS_MODEL} and {FACT_LONG_CONTEXT_ROUTING}"
        )
    elif size_units <= SMALL_PART_THRESHOLD:
        facts.append(FACT_CHEAP_SMALL_PARTS)
        route = "cheap-small-part"
        reason = ensure_compact_english(
            f"part {part_id} runs on a cheap model "
            f"using facts {FACT_PART_SIZE_VS_MODEL} and {FACT_CHEAP_SMALL_PARTS}"
        )
    else:
        route = "standard"
        reason = ensure_compact_english(
            f"part {part_id} keeps the standard model using fact {FACT_PART_SIZE_VS_MODEL}"  # noqa: E501  # frozen-cite K02
        )
    for fact in facts:
        if fact not in KNOWN_FACTS:
            raise ValueError(f"unknown model fact: {fact}")
    return DecompositionRecord(
        record_id=f"decomp-{part_id}",
        part_id=part_id,
        facts_used=facts,
        route=route,
        reason=reason,
        artifact_ref=f"ARTIFACT_REF:{part_id}/decomposition",
    )


@dataclass
class QueueSlot:
    part: PartRef
    position: int
    estimated_start_s: float

    def __post_init__(self) -> None:
        if not isinstance(self.part, PartRef):
            raise ValueError("queue slot needs a PartRef part")
        if isinstance(self.position, bool) or not isinstance(self.position, int):
            raise ValueError("position must be an int")
        if self.position < 0:
            raise ValueError("position must be >= 0")
        if isinstance(self.estimated_start_s, bool) or not isinstance(
            self.estimated_start_s, (int, float)
        ):
            raise ValueError("estimated_start_s must be a float")
        if float(self.estimated_start_s) < 0:
            raise ValueError("estimated_start_s must be >= 0")
        self.estimated_start_s = float(self.estimated_start_s)


def capped_queue(
    parts: Sequence[PartRef],
    settings: MultiManagerSettings,
    wall_time_s: float = 1.0,
) -> list[QueueSlot]:
    """Cap queue with position + estimated start (ROW32/M-P1-10/ARCH-755/762).

    Order follows the input parts; position is the serial index and
    estimated_start_s waves by cap (running slots start at 0.0). The
    running/queued split matches fanout exactly; nothing is dropped.
    """
    if isinstance(wall_time_s, bool) or not isinstance(wall_time_s, (int, float)):
        raise ValueError("wall_time_s must be a float")
    if float(wall_time_s) < 0:
        raise ValueError("wall_time_s must be >= 0")
    ordered = list(parts)
    running, queued = fanout(ordered, settings)
    assert running + queued == ordered
    cap = settings.max_parallel_managers if settings.multi_manager_mode else 1
    unit = float(wall_time_s)
    return [
        QueueSlot(part=part, position=index, estimated_start_s=(index // cap) * unit)
        for index, part in enumerate(ordered)
    ]


def persist_decompositions(path: str, records: Sequence[DecompositionRecord]) -> None:
    payload = [
        {
            "record_id": record.record_id,
            "part_id": record.part_id,
            "facts_used": list(record.facts_used),
            "route": record.route,
            "reason": record.reason,
            "artifact_ref": record.artifact_ref,
        }
        for record in records
    ]
    hot_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def load_decompositions(path: str) -> list[DecompositionRecord]:
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    records: list[DecompositionRecord] = []
    for item in payload:
        facts = [str(fact) for fact in item["facts_used"]]
        for fact in facts:
            if fact not in KNOWN_FACTS:
                raise ValueError(f"unknown model fact: {fact}")
        records.append(
            DecompositionRecord(
                record_id=str(item["record_id"]),
                part_id=str(item["part_id"]),
                facts_used=facts,
                route=str(item["route"]),
                reason=str(item["reason"]),
                artifact_ref=str(item["artifact_ref"]),
            )
        )
    return records


__all__ = [
    "ARTIFACT_PREFIX",
    "ARTIFACT_REF_PREFIX",
    "FACT_CHEAP_SMALL_PARTS",
    "FACT_LONG_CONTEXT_ROUTING",
    "FACT_PART_SIZE_VS_MODEL",
    "KNOWN_FACTS",
    "MODEL_ID",
    "SCOPE_OVERLAP",
    "SECRET_REF_KEY",
    "DecompositionRecord",
    "MultiManagerSettings",
    "PartRef",
    "QueueSlot",
    "TeamCard",
    "capped_queue",
    "corrections_hash",
    "ensure_compact_english",
    "fanout",
    "hot_write_text",
    "is_compact_english",
    "is_shared_ref",
    "issued_corrections_hash",
    "load_decompositions",
    "make_secret_ref",
    "persist_decompositions",
    "record_decomposition",
    "split_package",
    "validate_disjoint",
]


def serve_worker_inputs(data: Mapping[str, Any]) -> dict[str, Any]:
    """Serve row M-D-D13: worker context isolated; listed inputs only.

    Body {"worker_id", "authorized_refs", "requested_refs"}. Returns the
    worker id, the isolated (empty) worker context, and the inputs kept:
    requested refs that are shared refs (ARTIFACT_REF or SecretRef-only)
    and listed in authorized_refs. Raises ValueError on a non-object
    body, a blank worker_id, non-list ref lists, or a requested ref that
    is not a shared ref (served HTTP 400); requested refs that are
    shared but not authorized are dropped, never leaked.
    """
    if not isinstance(data, Mapping):
        raise ValueError("worker inputs body must be an object")
    worker_id = data.get("worker_id")
    if not isinstance(worker_id, str) or not worker_id.strip():
        raise ValueError("worker_id must be a non-empty string")
    authorized = data.get("authorized_refs")
    requested = data.get("requested_refs")
    if not isinstance(authorized, list) or not isinstance(requested, list):
        raise ValueError("authorized_refs and requested_refs must be lists")
    for ref in authorized:
        if not is_shared_ref(ref):
            raise ValueError("authorized_refs must be shared refs only")
    kept: list[Any] = []
    for ref in requested:
        if not is_shared_ref(ref):
            raise ValueError("requested_refs must be shared refs only")
        if ref in authorized and ref not in kept:
            kept.append(ref)
    return {
        "worker_id": worker_id.strip(),
        "context": worker_context(),
        "inputs": kept,
    }
