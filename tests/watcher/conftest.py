"""Watcher test-side setup: REAL stored seal-vs-hash mismatch for one frozen test.

The frozen ``test_verify_integrity_mismatch_raises`` expects
``iface.verify_integrity("proj-tampered")`` to raise GOVERNANCE_MISMATCH,
but the module autouse ``_reset_lane_state`` resets every lane store and
only ever seeds ``proj-a`` -- nothing seals or tampers ``"proj-tampered"``.
A plain autouse conftest fixture would run BEFORE that module reset and be
wiped, so this setup runs in a ``pytest_runtest_setup`` hook (trylast, so it
lands after the module fixture) scoped by nodeid to the single frozen test,
leaving every other watcher test untouched.

Only real product APIs are used: one journal row is appended, the project is
sealed, then the LIVE stored row dict (the same ``journal._ROWS`` dicts that
``stored_rows()``/``verify`` read, as in the frozen SPEC-21 tamper tests) is
mutated so the recomputed digest diverges from the sealed pin. No
``register_mismatch`` forced flag, no doubles, no FAKE-OF lines.
"""

import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.append(str(SRC))

import agent_si.watcher.integrity as _integrity
import agent_si.watcher.journal as _journal


@pytest.hookimpl(trylast=True)
def pytest_runtest_setup(item):
    """Seed then tamper "proj-tampered" after the module reset (one test only)."""
    if "test_verify_integrity_mismatch_raises" not in item.nodeid:
        return
    _journal.append_event(
        "proj-tampered", "watcher", "SERVICE_STATE", "boot", ("ref-boot",)
    )
    _integrity.seal("proj-tampered")
    _journal._ROWS["proj-tampered"][0]["summary"] = "rewritten by attacker"
