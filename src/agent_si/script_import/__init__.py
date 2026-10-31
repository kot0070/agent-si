"""Lane B script-import prefix (K06): user scripts run sandboxed on facts only.

Composed public entry: import_script (validate -> dry-run -> approval/hash-pin
-> add_script). Frozen pin published in the MGR-2-PinImport task folder.
"""

from __future__ import annotations

from typing import Any

from .approval import check_hash_pin, record_approval
from .contract import (
    AddScriptResult,
    ApprovalRecord,
    DeclaredPower,
    DryRunResult,
    HashPinCheck,
    ImportContract,
    ImportErrorCode,
    ImportResult,
    ValidationResult,
)
from .dry_run import dry_run
from .registry import add_script, is_shadow, reset_registry
from .validation import validate

__all__ = [
    "AddScriptResult",
    "ApprovalRecord",
    "DeclaredPower",
    "DryRunResult",
    "HashPinCheck",
    "ImportContract",
    "ImportErrorCode",
    "ImportResult",
    "ValidationResult",
    "add_script",
    "check_hash_pin",
    "dry_run",
    "import_script",
    "is_shadow",
    "record_approval",
    "reset_registry",
    "validate",
]


def import_script(
    contract: ImportContract,
    source_text: str,
    sample_facts: list[dict[str, Any]],
    approval: ApprovalRecord | None = None,
    approved_by: str = "",
) -> ImportResult:
    """Run the full import chain for one user script.

    Steps in order: validate every sample, sandbox dry run, approval
    (record a fresh one when none is given, else check the hash pin),
    then register the script. Every failure carries a code from
    ImportErrorCode and never echoes input payloads back.
    """
    if not isinstance(sample_facts, list) or len(sample_facts) == 0:
        return {
            "ok": False,
            "script_id": "",
            "error_code": "E_DRY_RUN_FAILED",
            "approval": None,
        }
    for facts in sample_facts:
        checked = validate(facts, contract)
        if not checked["ok"]:
            return {
                "ok": False,
                "script_id": "",
                "error_code": checked["error_code"],
                "approval": None,
            }
    rehearsed = dry_run(contract, sample_facts)
    if not rehearsed["ok"]:
        return {
            "ok": False,
            "script_id": "",
            "error_code": rehearsed["error_code"],
            "approval": None,
        }
    digest = contract.get("contract_hash") if isinstance(contract, dict) else ""
    if approval is None:
        if not isinstance(approved_by, str) or not approved_by:
            return {
                "ok": False,
                "script_id": "",
                "error_code": "E_APPROVAL_MISSING",
                "approval": None,
            }
        approval = record_approval(digest, approved_by)
    else:
        pin = check_hash_pin(approval, digest)
        if not pin["match"]:
            return {
                "ok": False,
                "script_id": "",
                "error_code": pin["error_code"],
                "approval": approval,
            }
    added = add_script(contract, source_text)
    if not added["ok"]:
        return {
            "ok": False,
            "script_id": "",
            "error_code": added["error_code"],
            "approval": approval,
        }
    return {
        "ok": True,
        "script_id": added["script_id"],
        "error_code": "",
        "approval": approval,
    }
