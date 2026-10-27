"""STEP 2 entry: sandbox dry run on sample facts before approval (G6).

Every sample is validated first; any sample failure fails the run without
echoing payloads. Declared powers that reach past the sandbox (network or
secret stores) are denied before any sample runs.
"""

from __future__ import annotations

from typing import Any

from .contract import DryRunResult, ImportContract
from .validation import validate


def _denial_code(contract: ImportContract) -> str:
    powers = contract.get("declared_powers")
    forbidden = contract.get("forbidden")
    if not isinstance(powers, list) or not isinstance(forbidden, list):
        return ""
    for power in powers:
        if not isinstance(power, dict):
            continue
        name = power.get("name", "")
        scope = power.get("scope", "")
        text = (str(name) + " " + str(scope)).lower()
        if "network" in text and "network-access" in forbidden:
            return "E_NETWORK_DENIED"
        if "secret" in text and "secret-keys" in forbidden:
            return "E_SECRET_REFUSED"
    return ""


def dry_run(
    contract: ImportContract,
    sample_facts: list[dict[str, Any]],
) -> DryRunResult:
    if not isinstance(contract, dict):
        return {"ok": False, "error_code": "E_SCHEMA_INVALID", "sample_count": 0}
    denial = _denial_code(contract)
    if denial:
        return {"ok": False, "error_code": denial, "sample_count": 0}
    if not isinstance(sample_facts, list) or len(sample_facts) == 0:
        return {"ok": False, "error_code": "E_DRY_RUN_FAILED", "sample_count": 0}
    for facts in sample_facts:
        checked = validate(facts, contract)
        if not checked["ok"]:
            return {"ok": False, "error_code": "E_DRY_RUN_FAILED", "sample_count": 0}
    return {"ok": True, "error_code": "", "sample_count": len(sample_facts)}
