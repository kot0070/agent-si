"""K03 STEP1 behaviour contract: permission ladder (row R-338). MUST FAIL on stubs.

Entry points: real stub symbols are loaded from
``src/agent_si/test_runners/permission_ladder.py`` via the loader below
(no copies). STEP2 error types must expose ``.code`` with the frozen name;
each code below is asserted in its own test. STEP1 RED mechanism per test:
stub bodies return None / raise nothing, so every behaviour test below is
marked strict-xfail (reason 'laneB: R-338'): the frozen suite runs
green-with-xfail and each marker flips when STEP2 lands.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

_STUB = (
    pathlib.Path(__file__).resolve().parents[3]
    / "src"
    / "agent_si"
    / "test_runners"
    / "permission_ladder.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("k03_ladder_stub", _STUB)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ladder = _load()

# FAKE-OF: LadderAsk test data (project ids, timestamps; test-only values).
PROJECT = "proj-k03-stage1"
ASKED_AT = "2026-10-26T00:00:00Z"

EXPECTED_RUNGS = (
    "UI_AUTOMATION",
    "SCREEN_CAPTURE_AI_VISION",
    "EMULATORS_SIMULATORS",
    "BROWSER_PROFILES",
    "TEST_ACCOUNTS",
    "TEST_SERVER",
    "DEVICE_LOGS",
    "SANDBOX_INSTALL",
)


def test_rungs_asked_in_exact_order_before_human():
    ask = ladder.ask_ladder_once(project_id=PROJECT, asked_at=ASKED_AT)
    assert ask.project_id == PROJECT
    assert tuple(ask.rung_ids) == EXPECTED_RUNGS


def test_human_refused_before_ladder():
    with pytest.raises(Exception) as exc_info:
        ladder.human_allowed(
            project_id="proj-never-asked", test_id="t-1", reason="needs hands"
        )
    assert exc_info.value.code == "HUMAN_BEFORE_LADDER"


def test_human_refused_without_reason():
    ladder.ask_ladder_once(project_id=PROJECT, asked_at=ASKED_AT)
    with pytest.raises(Exception) as exc_info:
        ladder.human_allowed(project_id=PROJECT, test_id="t-1", reason=None)
    assert exc_info.value.code == "HUMAN_REASON_MISSING"


def test_ladder_reask_refused():
    ladder.ask_ladder_once(project_id=PROJECT, asked_at=ASKED_AT)
    with pytest.raises(Exception) as exc_info:
        ladder.ask_ladder_once(project_id=PROJECT, asked_at=ASKED_AT)
    assert exc_info.value.code == "LADDER_ALREADY_ASKED"


def test_human_allowed_after_ladder_with_reason():
    ladder.ask_ladder_once(project_id=PROJECT, asked_at=ASKED_AT)
    assert (
        ladder.human_allowed(
            project_id=PROJECT, test_id="t-1", reason="needs hands on device"
        )
        is True
    )


def test_rung_rows_carry_enables_and_risk():
    rows = ladder.describe_rungs()
    assert [row.rung_id for row in rows] == list(EXPECTED_RUNGS)
    for row in rows:
        assert isinstance(row.enables, str) and row.enables
        assert isinstance(row.risk, str) and row.risk
