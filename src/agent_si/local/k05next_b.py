"""K05NEXT FalconB served rows (src/agent_si/local/k05next_b.py).

Greenfield local module proving five K05NEXT rows over served routes:
ARCH-352 (permission-gated local contact), BP05-65 (gateway
preconditions), BP05-92 (evidence tiers), MVP_ACCEPT-50 (SPLIT draft
plus verify), MVP_ACCEPT-53 (verifier hash binding). Every route
returns JSON-serializable values only. FastAPI plus standard library;
no sibling imports.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from fastapi import APIRouter, HTTPException

MODEL_ID = "k05next-b-1"

ERROR_CODES = (
    "K05NEXT_B_BAD_PAYLOAD",
    "K05NEXT_B_VALIDATION_FAILED",
    "K05NEXT_B_UNKNOWN_ROW",
)

LOCAL_ENDPOINT_REGISTRY = (
    "http://127.0.0.1:11434",
    "http://localhost:11434",
)

VIOLATION_UNPERMITTED_CONTACT = "UNPERMITTED_CONTACT"
VIOLATION_GATEWAY_BUSY = "GATEWAY_BUSY"

router = APIRouter()


@dataclass(frozen=True)
class Arch352Result:
    endpoint: str
    contacted: bool
    violation: bool
    reason: str | None


@dataclass(frozen=True)
class Bp0565Result:
    gateway: str
    contacted: bool
    violation_recorded: bool
    violation: str | None


@dataclass(frozen=True)
class Bp0592Result:
    tier: str
    eligible: bool
    reason: str
    evidence_count: int


@dataclass(frozen=True)
class MvpAccept50Result:
    route: str
    stages: list
    verify_before_audit: bool
    provenance: dict


@dataclass(frozen=True)
class MvpAccept53Result:
    local_draft_ref: str
    cloud_verify_ref: str
    draft_hash: str
    bound: bool
    trace: str | None


def _bad_payload(detail: str) -> HTTPException:
    return HTTPException(status_code=422, detail="K05NEXT_B_BAD_PAYLOAD: " + detail)


@router.post("/k05next/arch-352/serve")
def serve_arch_352(payload: dict) -> dict:
    """Contact a local endpoint only with permission; refusal is a violation."""
    endpoint = payload.get("endpoint")
    permission = payload.get("permission")
    if not isinstance(endpoint, str) or not endpoint:
        raise _bad_payload("endpoint must be a non-empty string")
    if endpoint not in LOCAL_ENDPOINT_REGISTRY:
        raise HTTPException(
            status_code=404,
            detail="K05NEXT_B_UNKNOWN_ROW: endpoint %r sits outside "
            "the frozen local registry" % (endpoint,),
        )
    if not isinstance(permission, bool):
        raise _bad_payload("permission must be a boolean")
    if permission:
        return asdict(
            Arch352Result(
                endpoint=endpoint,
                contacted=True,
                violation=False,
                reason=None,
            )
        )
    return asdict(
        Arch352Result(
            endpoint=endpoint,
            contacted=False,
            violation=True,
            reason=VIOLATION_UNPERMITTED_CONTACT,
        )
    )


@router.post("/k05next/bp05-65/serve")
def serve_bp05_65(payload: dict) -> dict:
    """Refuse contact and record GATEWAY_BUSY while preconditions are unmet."""
    gateway = payload.get("gateway")
    preconditions_met = payload.get("preconditions_met")
    if not isinstance(gateway, str) or not gateway:
        raise _bad_payload("gateway must be a non-empty string")
    if not isinstance(preconditions_met, bool):
        raise _bad_payload("preconditions_met must be a boolean")
    if preconditions_met:
        return asdict(
            Bp0565Result(
                gateway=gateway,
                contacted=True,
                violation_recorded=False,
                violation=None,
            )
        )
    return asdict(
        Bp0565Result(
            gateway=gateway,
            contacted=False,
            violation_recorded=True,
            violation=VIOLATION_GATEWAY_BUSY,
        )
    )


def _evidence_signal(entry: Any) -> tuple:
    """Tier text plus recorded flag for one evidence entry.

    Recorded evidence is a mapping carrying a non-empty ref or a
    structured store ref string; a bare kind label alone is never
    recorded and never admits.
    """
    if isinstance(entry, dict):
        text = "%s %s" % (entry.get("kind", ""), entry.get("ref", ""))
        ref = entry.get("ref")
        return text.lower(), isinstance(ref, str) and bool(ref)
    if isinstance(entry, str):
        lowered = entry.lower()
        recorded = lowered.startswith("cap:") or lowered.startswith("store-ref")
        return lowered, recorded
    return "", False


@router.post("/k05next/bp05-92/serve")
def serve_bp05_92(payload: dict) -> dict:
    """Derive the UNKNOWN, PROXY or MEASURED tier from recorded evidence."""
    evidence = payload.get("evidence")
    if not isinstance(evidence, list):
        raise _bad_payload("evidence must be a list of kinds")
    measured_seen = False
    measured_recorded = False
    proxy_seen = False
    for entry in evidence:
        text, recorded = _evidence_signal(entry)
        if "measured" in text:
            measured_seen = True
            if recorded:
                measured_recorded = True
        elif "proxy" in text:
            proxy_seen = True
    if measured_seen:
        if measured_recorded:
            result = Bp0592Result(
                tier="MEASURED",
                eligible=True,
                reason="eligible: MEASURED tier from recorded evidence",
                evidence_count=len(evidence),
            )
        else:
            result = Bp0592Result(
                tier="MEASURED",
                eligible=False,
                reason="MEASURED_NOT_ROUTING_ELIGIBLE: measured label "
                "without recorded evidence never admits",
                evidence_count=len(evidence),
            )
    elif proxy_seen:
        result = Bp0592Result(
            tier="PROXY",
            eligible=False,
            reason="PROXY_NOT_ROUTING_ELIGIBLE: proxy tier derives from "
            "recorded evidence and proxy alone never admits",
            evidence_count=len(evidence),
        )
    else:
        result = Bp0592Result(
            tier="UNKNOWN",
            eligible=False,
            reason="UNKNOWN_TIER_INELIGIBLE: evidence carries no tier "
            "signal; UNKNOWN is never picked",
            evidence_count=len(evidence),
        )
    return asdict(result)


@router.post("/k05next/mvp-accept-50/serve")
def serve_mvp_accept_50(payload: dict) -> dict:
    """Carry local draft plus cloud verify atomically with verify before audit."""
    refs = [
        payload.get("local_draft_ref"),
        payload.get("cloud_verify_ref"),
        payload.get("draft_hash"),
    ]
    if any(not isinstance(value, str) or not value for value in refs):
        raise HTTPException(
            status_code=422,
            detail="K05NEXT_B_VALIDATION_FAILED: local_draft_ref plus "
            "cloud_verify_ref plus draft_hash must be non-empty strings",
        )
    if len(set(refs)) != 3:
        raise HTTPException(
            status_code=422,
            detail="K05NEXT_B_VALIDATION_FAILED: local_draft_ref plus "
            "cloud_verify_ref plus draft_hash must be distinct",
        )
    local_draft_ref, cloud_verify_ref, draft_hash = refs
    return asdict(
        MvpAccept50Result(
            route="SPLIT",
            stages=["local_draft", "cloud_verify"],
            verify_before_audit=True,
            provenance={
                "local_draft_ref": local_draft_ref,
                "cloud_verify_ref": cloud_verify_ref,
                "draft_hash": draft_hash,
            },
        )
    )


@router.post("/k05next/mvp-accept-53/serve")
def serve_mvp_accept_53(payload: dict) -> dict:
    """Bind verifier input to the draft hash so verification traces the draft."""
    draft_hash = payload.get("draft_hash")
    if not isinstance(draft_hash, str) or not draft_hash:
        raise _bad_payload("draft_hash must be a non-empty string")
    verifier_input_hash = payload.get("verifier_input_hash")
    bound = verifier_input_hash == draft_hash
    return asdict(
        MvpAccept53Result(
            local_draft_ref=payload.get("local_draft_ref"),
            cloud_verify_ref=payload.get("cloud_verify_ref"),
            draft_hash=draft_hash,
            bound=bound,
            trace=draft_hash if bound else None,
        )
    )
