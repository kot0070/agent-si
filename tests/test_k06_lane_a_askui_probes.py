"""Lane A ASK-UI probes (STEP2): restart persistence, backslash-exact, roots gate.

Reaches the real implementation through ``agent_si.backend.ui_session``.
Runs after the contract file in the same process (filename sorts after it).
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from agent_si.backend import ui_session  # noqa: E402

# Probe-only handles. Never real credentials.
PROBE_SECRET_HANDLE = "PROBE-ONLY-secret-handle-not-a-credential"
PROBE_FORGED_TOKEN = "PROBE-ONLY-forged-resume-token-not-a-credential"
PROBE_BACKSLASH_SUMMARY = "deploy C:\\Users\\ops\\run\\\\tail then verify"


def _probe_options() -> list:
    return [
        ui_session.AskOption(option_id="yes", label="Yes"),
        ui_session.AskOption(option_id="no", label="No"),
    ]


def test_l080_positive_control_happy_flow() -> None:
    card = ui_session.create_ask_card(
        kind="approval",
        summary="Approve the migration plan?",
        options=_probe_options(),
        secret_ref=PROBE_SECRET_HANDLE,
    )
    assert card.ask_id
    assert card.resume_token
    assert isinstance(card.options, tuple)
    result = ui_session.approve_ask(
        ask_id=card.ask_id,
        option_id="yes",
        resume_token=card.resume_token,
    )
    assert result.ask_id == card.ask_id
    assert result.approved_option_id == "yes"
    assert result.resume_token == card.resume_token
    resumed = ui_session.resume_ask(resume_token=card.resume_token)
    assert resumed.ask_id == card.ask_id
    assert resumed.summary == "Approve the migration plan?"


def test_r313_sessions_after_restart(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AGENT_SI_SESSION_STORE", str(tmp_path))
    importlib.reload(ui_session)
    card = ui_session.create_ask_card(
        kind="choice",
        summary="Pick a region",
        options=_probe_options(),
        secret_ref=PROBE_SECRET_HANDLE,
    )
    stored = list(tmp_path.glob("*.json"))
    assert stored, "create_ask_card must append a session record to the default store"
    importlib.reload(ui_session)
    sessions = ui_session.list_sessions(store_path=str(tmp_path))
    assert any(s.session_id == card.ask_id and s.title == "Pick a region" for s in sessions)


def test_backslash_exact_round_trip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AGENT_SI_SESSION_STORE", str(tmp_path))
    importlib.reload(ui_session)
    exact = PROBE_BACKSLASH_SUMMARY
    card = ui_session.create_ask_card(
        kind="approval",
        summary=exact,
        options=_probe_options(),
    )
    assert card.summary == exact
    result = ui_session.approve_ask(
        ask_id=card.ask_id,
        option_id="no",
        resume_token=card.resume_token,
    )
    assert result.approved_option_id == "no"
    resumed = ui_session.resume_ask(resume_token=card.resume_token)
    assert resumed.summary == exact
    raw_texts = [p.read_text(encoding="utf-8") for p in tmp_path.glob("*.json")]
    assert raw_texts
    assert any(json.loads(text)["title"] == exact for text in raw_texts)
    sessions = ui_session.list_sessions(store_path=str(tmp_path))
    assert any(s.session_id == card.ask_id and s.title == exact for s in sessions)


def test_b012_roots_gate_inside_ok_outside_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("AGENT_SI_SESSION_ROOTS", str(tmp_path))
    inside = tmp_path / "sub"
    sessions = ui_session.list_sessions(store_path=str(inside))
    assert isinstance(sessions, list)
    cased = str(tmp_path).upper()
    assert isinstance(ui_session.list_sessions(store_path=cased), list)
    outside = str(tmp_path) + "_outside"
    with pytest.raises(PermissionError) as excinfo:
        ui_session.list_sessions(store_path=outside)
    assert outside in str(excinfo.value)


def test_b012_roots_unset_open(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("AGENT_SI_SESSION_ROOTS", raising=False)
    sessions = ui_session.list_sessions(store_path=tmp_path)
    assert isinstance(sessions, list)


def test_probe_rejects_forged_token() -> None:
    with pytest.raises(PermissionError):
        ui_session.approve_ask(
            ask_id="ask-9999",
            option_id="yes",
            resume_token=PROBE_FORGED_TOKEN,
        )
    with pytest.raises(PermissionError):
        ui_session.resume_ask(resume_token=PROBE_FORGED_TOKEN)
