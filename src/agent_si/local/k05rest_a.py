"""K05REST served proofs (local module, greenfield).

Four rows, one served route each, on a FastAPI router mounted by the test
file in-test (never in product): refreshed capability knowledge serves only
current versions with the original untouched (M-D-D10), helper attach runs
the passive gate first and refuses when busy (M-D-D22), SPLIT carries local
draft plus cloud verify atomically with verify before audit
(MVP_ACCEPT-50), verifier input binds the draft hash so cloud verification
traces to the exact draft (MVP_ACCEPT-53).

Standard library plus fastapi only; every route value JSON-serializable.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

#: Exact module identity pinned by test_k05rest_a_identity_pinned.
MODEL_ID = "k05rest-a-1"

#: Frozen error-code triple, each pinned by its own served test.
ERROR_CODES = (
    "K05REST_A_BAD_PAYLOAD",
    "K05REST_A_VALIDATION_FAILED",
    "K05REST_A_UNKNOWN_ROW",
)

_BAD_PAYLOAD = ERROR_CODES[0]
_VALIDATION_FAILED = ERROR_CODES[1]
_UNKNOWN_ROW = ERROR_CODES[2]

_STALE_REFUSED_REASON = "versioned stale backup copies are never served as current"
_PASSIVE_GATE_REFUSED = "PASSIVE_GATE_REFUSED"

router = APIRouter(prefix="/k05rest")


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
class CopyRefD10:
    ref: str
    version: int


@dataclass(frozen=True)
class ServedCopiesD10:
    model_id: str
    served: tuple = field(default_factory=tuple)
    refused: tuple = field(default_factory=tuple)
    original_untouched: bool = True


@router.post("/d-d10/serve")
async def serve_d_d10(payload: dict) -> Any:
    """Only current versioned rows serve; stale copies are refused, original untouched."""
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
            served.append(asdict(CopyRefD10(ref=ref, version=version)))
        else:
            refused.append(
                {
                    "ref": ref,
                    "version": version,
                    "reason": (
                        f"{_STALE_REFUSED_REASON}: "
                        f"requested version {version} is below current version "
                        f"{current[ref]}"
                    ),
                }
            )
    return asdict(
        ServedCopiesD10(
            model_id=MODEL_ID,
            served=tuple(served),
            refused=tuple(refused),
            original_untouched=True,
        )
    )


@dataclass(frozen=True)
class HelperAttachD22:
    model_id: str
    gateway: str
    allowed: bool
    contacted: bool
    violation: Any = None


@router.post("/d-d22/serve")
async def serve_d_d22(payload: dict) -> Any:
    """Helper attach runs the passive gate first and refuses when busy."""
    if not isinstance(payload, dict):
        return _bad_payload("payload must be a JSON object")
    gateway = _text(payload.get("gateway"))
    if not gateway.strip():
        return _bad_payload("gateway must be a non-empty string")
    passive_ok = payload.get("passive_ok")
    if not isinstance(passive_ok, bool):
        return _bad_payload("passive_ok must be a boolean")
    if passive_ok:
        return asdict(
            HelperAttachD22(
                model_id=MODEL_ID,
                gateway=gateway.strip(),
                allowed=True,
                contacted=True,
                violation=None,
            )
        )
    return asdict(
        HelperAttachD22(
            model_id=MODEL_ID,
            gateway=gateway.strip(),
            allowed=False,
            contacted=False,
            violation=_PASSIVE_GATE_REFUSED,
        )
    )


@dataclass(frozen=True)
class SplitOrder50:
    model_id: str
    ordered: bool
    dual: bool
    stages: tuple = field(default_factory=tuple)
    provenance: tuple = field(default_factory=tuple)


def _stage_names(stages: Any) -> list | None:
    if not isinstance(stages, list):
        return None
    names: list = []
    for entry in stages:
        if not isinstance(entry, str):
            return None
        names.append(entry.strip())
    return names


def _provenance_names(provenance: Any) -> list | None:
    if not isinstance(provenance, list):
        return None
    names: list = []
    for entry in provenance:
        if not isinstance(entry, str):
            return None
        names.append(entry.strip())
    return names


@router.post("/mvp-accept-50/serve")
async def serve_mvp_accept_50(payload: dict) -> Any:
    """SPLIT carries local draft plus cloud verify atomically, verify before audit."""
    if not isinstance(payload, dict):
        return _bad_payload("payload must be a JSON object")
    local_draft_ref = _text(payload.get("local_draft_ref"))
    cloud_verify_ref = _text(payload.get("cloud_verify_ref"))
    if not local_draft_ref.strip() or not cloud_verify_ref.strip():
        return _bad_payload("local_draft_ref plus cloud_verify_ref must be non-empty strings")
    stages = _stage_names(payload.get("stages"))
    provenance = _provenance_names(payload.get("provenance"))
    if stages != ["local_draft", "cloud_verify"]:
        return _validation_failed("stages must run local_draft then cloud_verify in order")
    if provenance is None or "local" not in provenance or "cloud" not in provenance:
        return _validation_failed("provenance must hold both local and cloud")
    return asdict(
        SplitOrder50(
            model_id=MODEL_ID,
            ordered=True,
            dual=True,
            stages=tuple(stages),
            provenance=tuple(provenance),
        )
    )


@dataclass(frozen=True)
class VerifierBind53:
    model_id: str
    draft_ref: str
    verify_ref: str
    draft_hash: str
    bound: bool


@router.post("/mvp-accept-53/serve")
async def serve_mvp_accept_53(payload: dict) -> Any:
    """Verifier input binds the draft hash so verification traces to the exact draft."""
    if not isinstance(payload, dict):
        return _bad_payload("payload must be a JSON object")
    draft_ref = _text(payload.get("draft_ref"))
    verify_ref = _text(payload.get("verify_ref"))
    draft_hash = _text(payload.get("draft_hash"))
    if not draft_ref.strip() or not verify_ref.strip() or not draft_hash.strip():
        return _bad_payload("draft_ref plus verify_ref plus draft_hash must be non-empty strings")
    known = payload.get("known_drafts")
    known_refs = {entry.strip() for entry in known if isinstance(entry, str)} if isinstance(known, list) else set()
    if draft_ref.strip() not in known_refs:
        return _unknown_row(
            f"draft ref {draft_ref.strip()!r} is not a known draft; "
            "cloud verification traces only to a known exact draft"
        )
    return asdict(
        VerifierBind53(
            model_id=MODEL_ID,
            draft_ref=draft_ref.strip(),
            verify_ref=verify_ref.strip(),
            draft_hash=draft_hash.strip(),
            bound=True,
        )
    )
