"""STEP 1 interface types for the Lane B script-import prefix (G5/G6/G8).

Facts JSON in, result JSON out; declared power plus forbidden list;
approval record plus hash pin; additions only, never shadow of standard
scripts. Types only. STEP 2 waits HD freeze.
"""

from __future__ import annotations

from enum import Enum
from typing import TypedDict

CONTRACT_VERSION: str = "1"

FORBIDDEN_CAPABILITIES: tuple[str, ...] = ("secret-keys", "network-access")


class ImportErrorCode(str, Enum):
    SCHEMA_INVALID = "E_SCHEMA_INVALID"
    DRY_RUN_FAILED = "E_DRY_RUN_FAILED"
    APPROVAL_MISSING = "E_APPROVAL_MISSING"
    HASH_PIN_MISMATCH = "E_HASH_PIN_MISMATCH"
    SHADOW_REFUSED = "E_SHADOW_REFUSED"
    SECRET_REFUSED = "E_SECRET_REFUSED"
    NETWORK_DENIED = "E_NETWORK_DENIED"
    UNTRUSTED_DATA = "E_UNTRUSTED_DATA"


class DeclaredPower(TypedDict):
    name: str
    scope: str


class ImportContract(TypedDict):
    name: str
    version: str
    contract_hash: str
    declared_powers: list[DeclaredPower]
    forbidden: list[str]


class ValidationResult(TypedDict):
    ok: bool
    error_code: str


class DryRunResult(TypedDict):
    ok: bool
    error_code: str
    sample_count: int


class ApprovalRecord(TypedDict):
    approval_id: str
    contract_hash: str
    approved_by: str
    approved_at: str


class HashPinCheck(TypedDict):
    match: bool
    error_code: str


class AddScriptResult(TypedDict):
    ok: bool
    script_id: str
    error_code: str
