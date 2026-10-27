"""STEP 2 entries: approval record plus hash-pin re-approval check (G6).

An approval pins one exact contract hash. Any changed hash fails the pin
until a fresh approval is recorded for the new hash.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .contract import ApprovalRecord, HashPinCheck


def record_approval(contract_hash: str, approved_by: str) -> ApprovalRecord:
    digest = contract_hash if isinstance(contract_hash, str) else ""
    return {
        "approval_id": "apr-" + digest,
        "contract_hash": digest,
        "approved_by": approved_by,
        "approved_at": datetime.now(timezone.utc).isoformat(),
    }


def check_hash_pin(record: ApprovalRecord, contract_hash: str) -> HashPinCheck:
    match = isinstance(record, dict) and record.get("contract_hash") == contract_hash
    return {"match": match, "error_code": "" if match else "E_HASH_PIN_MISMATCH"}
