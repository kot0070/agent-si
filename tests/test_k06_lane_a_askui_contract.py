"""Lane A ASK-UI behaviour contract (STEP1: expected RED).

Every test reaches the real implementation through the package entry point
``agent_si.backend.ui_session``. No fakes, no app boot, no network.

STEP1 status: the entry point holds types + signatures only (bodies are
``...``), so each test below MUST fail until the real implementation lands.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from agent_si.backend import ui_session  # noqa: E402
from agent_si.backend.ui_session import AskOption  # noqa: E402

# Tests-only placeholder secret handle. Never a real credential.
FAKE_SECRET_REF = "FAKE-OF-secret-ref-for-contract-test-only"


def _g4_shape(card: object) -> None:
    assert hasattr(card, "ask_id") and card.ask_id  # type: ignore[attr-defined]
    assert hasattr(card, "kind") and card.kind  # type: ignore[attr-defined]
    assert hasattr(card, "summary") and card.summary  # type: ignore[attr-defined]
    assert hasattr(card, "options") and card.options  # type: ignore[attr-defined]
    assert hasattr(card, "resume_token") and card.resume_token  # type: ignore[attr-defined]


def test_create_ask_card_returns_g4_shape() -> None:
    card = ui_session.create_ask_card(
        kind="approval",
        summary="Approve the migration plan?",
        options=[
            AskOption(option_id="yes", label="Yes"),
            AskOption(option_id="no", label="No"),
        ],
        secret_ref=FAKE_SECRET_REF,
    )
    _g4_shape(card)
    assert card.kind == "approval"
    assert [o.option_id for o in card.options] == ["yes", "no"]


def test_approve_ask_returns_resolution() -> None:
    result = ui_session.approve_ask(
        ask_id="ask-1",
        option_id="yes",
        resume_token="resume-1",
    )
    assert result.ask_id == "ask-1"
    assert result.approved_option_id == "yes"
    assert result.resume_token


def test_resume_ask_returns_card() -> None:
    card = ui_session.resume_ask(resume_token="resume-1")
    _g4_shape(card)


def test_list_sessions_after_restart(tmp_path: Path) -> None:
    sessions = ui_session.list_sessions(store_path=tmp_path)
    assert isinstance(sessions, list)


def test_secret_ref_opaque_never_in_logs() -> None:
    ref = ui_session.SecretRef(FAKE_SECRET_REF)
    assert FAKE_SECRET_REF not in repr(ref)
    assert FAKE_SECRET_REF not in str(ref)


# HD SECURITY binding: every write entry (create_ask_card, approve_ask,
# resume_ask) refuses a missing/empty token and a forged token with
# PermissionError. create_ask_card takes no token itself, so its two tests
# drive the token through the flow (create, then approve/resume).
# Tests-only forged handle. Never a real credential.
FAKE_FORGED_TOKEN = "FAKE-OF-forged-resume-token-for-contract-test-only"


def _flow_options() -> list[AskOption]:
    return [
        AskOption(option_id="yes", label="Yes"),
        AskOption(option_id="no", label="No"),
    ]


def test_approve_ask_refuses_missing_token() -> None:
    with pytest.raises(PermissionError):
        ui_session.approve_ask(ask_id="ask-1", option_id="yes", resume_token="")


def test_approve_ask_refuses_forged_token() -> None:
    with pytest.raises(PermissionError):
        ui_session.approve_ask(
            ask_id="ask-1",
            option_id="yes",
            resume_token=FAKE_FORGED_TOKEN,
        )


def test_resume_ask_refuses_missing_token() -> None:
    with pytest.raises(PermissionError):
        ui_session.resume_ask(resume_token="")


def test_resume_ask_refuses_forged_token() -> None:
    with pytest.raises(PermissionError):
        ui_session.resume_ask(resume_token=FAKE_FORGED_TOKEN)


def test_create_ask_card_flow_refuses_missing_token() -> None:
    ui_session.create_ask_card(
        kind="approval",
        summary="Approve the migration plan?",
        options=_flow_options(),
        secret_ref=FAKE_SECRET_REF,
    )
    with pytest.raises(PermissionError):
        ui_session.approve_ask(ask_id="ask-1", option_id="yes", resume_token="")


def test_create_ask_card_flow_refuses_forged_token() -> None:
    ui_session.create_ask_card(
        kind="approval",
        summary="Approve the migration plan?",
        options=_flow_options(),
        secret_ref=FAKE_SECRET_REF,
    )
    with pytest.raises(PermissionError):
        ui_session.resume_ask(resume_token=FAKE_FORGED_TOKEN)


def test_http_open_read_route_reachable() -> None:
    # Frozen K02 seam: TestClient(create_app(...)) from agent_si.backend.app.
    # create_app does NOT exist yet, so this MUST fail now with ImportError
    # (expected STEP1 RED); do not catch it.
    from agent_si.backend.app import create_app
    from fastapi.testclient import TestClient

    client = TestClient(create_app())
    response = client.get("/api/v1/sessions")
    assert response.status_code == 200


def test_http_write_without_token_refused() -> None:
    # Same frozen seam; a write with no x-ui-session-token must be 401/403.
    # Expected STEP1 RED (ImportError) until K02 lands; do not catch it.
    from agent_si.backend.app import create_app
    from fastapi.testclient import TestClient

    client = TestClient(create_app())
    response = client.post(
        "/api/v1/asks",
        json={
            "kind": "approval",
            "summary": "Approve the migration plan?",
            "options": [
                {"option_id": "yes", "label": "Yes"},
                {"option_id": "no", "label": "No"},
            ],
        },
    )
    assert response.status_code in (401, 403)
