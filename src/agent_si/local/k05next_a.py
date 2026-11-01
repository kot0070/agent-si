"""K05NEXT FalconA served proofs (local module, greenfield).

Five rows, one served route each, on a FastAPI router mounted by the test
file in-test (never in product): non-running runtimes keep UNKNOWN
capability (MVP_ACCEPT-221), evidence-less stores yield UNKNOWN
(MVP_ACCEPT-222), prose notes land as PROXY until fresh benchmarks
(BP05-94), stale versioned copies are refused as current (ARCH-367),
prose notes pass only through the labelled PROXY adapter (ARCH-373).

Standard library plus fastapi only; every route value JSON-serializable.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

#: Exact module identity pinned by test_k05next_a_identity_pinned.
MODEL_ID = "k05next-a-1"

#: Frozen error-code triple, each pinned by its own served test.
ERROR_CODES = (
    "K05NEXT_A_BAD_PAYLOAD",
    "K05NEXT_A_VALIDATION_FAILED",
    "K05NEXT_A_UNKNOWN_ROW",
)

_BAD_PAYLOAD = ERROR_CODES[0]
_VALIDATION_FAILED = ERROR_CODES[1]
_UNKNOWN_ROW = ERROR_CODES[2]

router = APIRouter(prefix="/api/v1/local")


def _error(status: int, code: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"model_id": MODEL_ID, "code": code, "detail": detail},
    )


def _bad_payload(detail: str) -> JSONResponse:
    return _error(422, _BAD_PAYLOAD, detail)


def _validation_failed(detail: str) -> JSONResponse:
    return _error(422, _VALIDATION_FAILED, detail)


def _unknown_row(detail: str) -> JSONResponse:
    return _error(404, _UNKNOWN_ROW, detail)


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


@dataclass(frozen=True)
class Eligibility221:
    model_id: str
    tier: str
    eligible: bool
    reason: str
    granted: tuple = field(default_factory=tuple)


@router.post("/mvp-accept-221/serve")
async def serve_mvp_accept_221(payload: dict) -> Any:
    """Non-running local runtimes keep UNKNOWN capability and grant nothing."""
    if not isinstance(payload, dict):
        return _bad_payload("payload must be a JSON object")
    store_ref = _text(payload.get("store_ref"))
    if not store_ref.strip():
        return _bad_payload("store_ref must be a non-empty string")
    running = payload.get("running", False)
    tiers = payload.get("tiers", [])
    levels = {t.strip().upper() for t in tiers if isinstance(t, str) and t.strip()}
    if not running:
        verdict = Eligibility221(
            model_id=MODEL_ID,
            tier="UNKNOWN",
            eligible=False,
            reason=(
                "UNKNOWN_TIER_INELIGIBLE: runtime for store ref "
                f"{store_ref!r} is not running; non-running local runtimes "
                "keep UNKNOWN capability and grant no eligibility"
            ),
            granted=(),
        )
        return asdict(verdict)
    if "MEASURED" in levels:
        verdict = Eligibility221(
            model_id=MODEL_ID,
            tier="MEASURED",
            eligible=True,
            reason=(
                "eligible: MEASURED tier evidence for store ref "
                f"{store_ref!r} on a running runtime"
            ),
            granted=("routing-eligibility",),
        )
        return asdict(verdict)
    verdict = Eligibility221(
        model_id=MODEL_ID,
        tier="UNKNOWN",
        eligible=False,
        reason=(
            "UNKNOWN_TIER_INELIGIBLE: store ref "
            f"{store_ref!r} carries UNKNOWN-only tiers; UNKNOWN is never picked"
        ),
        granted=(),
    )
    return asdict(verdict)


@dataclass(frozen=True)
class StoreColumns222:
    model_id: str
    task_class: str
    tier: str
    row_found: bool
    evidence_columns: tuple = field(default_factory=tuple)


def _evidence_columns(columns: Any) -> list:
    found = []
    if not isinstance(columns, list):
        return found
    for entry in columns:
        if not isinstance(entry, str):
            continue
        lowered = entry.strip().lower()
        if "evidence" in lowered or "benchmark" in lowered:
            found.append(entry.strip())
    return found


@router.post("/mvp-accept-222/serve")
async def serve_mvp_accept_222(payload: dict) -> Any:
    """Evidence-less capability stores yield UNKNOWN for local classes."""
    if not isinstance(payload, dict):
        return _bad_payload("payload must be a JSON object")
    model_id = _text(payload.get("model_id"))
    if not model_id.strip():
        return _bad_payload("model_id must be a non-empty string")
    task_class = _text(payload.get("task_class"))
    evidence = _evidence_columns(payload.get("columns", []))
    if not evidence:
        return asdict(
            StoreColumns222(
                model_id=MODEL_ID,
                task_class=task_class.strip(),
                tier="UNKNOWN",
                row_found=False,
                evidence_columns=(),
            )
        )
    return asdict(
        StoreColumns222(
            model_id=MODEL_ID,
            task_class=task_class.strip(),
            tier="PROXY",
            row_found=True,
            evidence_columns=tuple(evidence),
        )
    )


@dataclass(frozen=True)
class NotesBasis94:
    model_id: str
    tier: str
    freshness: str
    score: Any
    shape: Any


@router.post("/bp05-94/serve")
async def serve_bp05_94(payload: dict) -> Any:
    """Prose notes land as PROXY with UNKNOWN freshness until fresh benchmarks."""
    if not isinstance(payload, dict):
        return _bad_payload("payload must be a JSON object")
    notes = _text(payload.get("notes"))
    if not notes.strip():
        return _bad_payload("notes must be a non-empty string")
    if not payload.get("fresh_benchmark", False):
        return asdict(
            NotesBasis94(
                model_id=MODEL_ID,
                tier="PROXY",
                freshness="UNKNOWN",
                score=None,
                shape="UNKNOWN",
            )
        )
    threshold = payload.get("threshold", None)
    shape = _text(payload.get("shape"))
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        return _validation_failed("fresh_benchmark true requires a numeric threshold")
    if not shape.strip():
        return _validation_failed("fresh_benchmark true requires a shape")
    return asdict(
        NotesBasis94(
            model_id=MODEL_ID,
            tier="MEASURED",
            freshness="FRESH",
            score=threshold,
            shape=shape.strip(),
        )
    )


@dataclass(frozen=True)
class CopyRef367:
    ref: str
    version: int


@dataclass(frozen=True)
class ServedCopies367:
    model_id: str
    served: tuple
    refused: tuple


@router.post("/arch-367/serve")
async def serve_arch_367(payload: dict) -> Any:
    """Only current versioned rows serve; stale copies are refused as current."""
    if not isinstance(payload, dict):
        return _bad_payload("payload must be a JSON object")
    if any(key not in payload for key in ("copies", "current", "requested")):
        return _bad_payload("payload requires copies plus current plus requested")
    copies = payload.get("copies")
    current = payload.get("current")
    requested = payload.get("requested")
    if not isinstance(copies, list) or not isinstance(current, dict) or not isinstance(requested, list):
        return _bad_payload("copies plus requested must be lists and current a mapping")
    for entry in requested:
        if not isinstance(entry, dict):
            return _bad_payload("requested entries must hold ref plus version")
        ref = _text(entry.get("ref"))
        if not ref.strip():
            return _bad_payload("requested entries must hold ref plus version")
        if ref not in current:
            return _unknown_row(
                f"requested ref {ref!r} has no current version; "
                "only current rows serve"
            )
        if isinstance(current[ref], bool) or not isinstance(current[ref], int):
            return _bad_payload("current versions must be integers")
    served: list = []
    refused: list = []
    for entry in requested:
        ref = _text(entry.get("ref")).strip()
        version = entry.get("version")
        if isinstance(version, bool) or not isinstance(version, int):
            return _bad_payload("requested entries must hold ref plus version")
        if version >= current[ref]:
            served.append(asdict(CopyRef367(ref=ref, version=version)))
        else:
            refused.append(
                {
                    "ref": ref,
                    "version": version,
                    "reason": (
                        "versioned stale backup copies are never served as current: "
                        f"requested version {version} is below current version "
                        f"{current[ref]}"
                    ),
                }
            )
    return asdict(ServedCopies367(model_id=MODEL_ID, served=tuple(served), refused=tuple(refused)))


@dataclass(frozen=True)
class ProxyLabel373:
    model_id: str
    tier: str
    adapter: str
    label: str
    score: Any


@router.post("/arch-373/serve")
async def serve_arch_373(payload: dict) -> Any:
    """Prose notes pass only through the labelled PROXY adapter, never as scores."""
    if not isinstance(payload, dict):
        return _bad_payload("payload must be a JSON object")
    notes = _text(payload.get("notes"))
    if not notes.strip():
        return _bad_payload("notes must be a non-empty string")
    label = _text(payload.get("label"))
    if not label.strip():
        return _validation_failed("a labelled PROXY adapter call requires a label")
    return asdict(
        ProxyLabel373(
            model_id=MODEL_ID,
            tier="PROXY",
            adapter="PROXY",
            label=label.strip(),
            score=None,
        )
    )
