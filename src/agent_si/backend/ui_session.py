"""Lane A UI-session ASK contract (STEP2 implementation).

G4 ASK card: {ask_id, kind, summary, options, resume_token}; approval card
in chat; ASK buttons in chat + run view click-resume; sessions listed
after restart (session records persist as JSON under the default store
directory and list_sessions unions files with in-memory entries).

G5 SecretRef is opaque: repr/str never expose the wrapped value.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, NewType, Optional, Sequence

AskId = NewType("AskId", str)
ResumeToken = NewType("ResumeToken", str)


class SecretRef(str):
    """Opaque secret handle. repr/str stay redacted (G5)."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "SecretRef('***')"

    def __str__(self) -> str:
        return "***"


AskKind = Literal["approval", "choice", "confirm"]

_ASK_KINDS = ("approval", "choice", "confirm")


@dataclass(frozen=True)
class AskOption:
    option_id: str
    label: str


@dataclass(frozen=True)
class AskCard:
    ask_id: str
    kind: str
    summary: str
    options: tuple[AskOption, ...]
    resume_token: str


@dataclass(frozen=True)
class ApprovalResult:
    ask_id: str
    approved_option_id: str
    resume_token: str


@dataclass(frozen=True)
class SessionSummary:
    session_id: str
    title: str


_cards_by_token: dict[str, AskCard] = {}
_token_by_ask_id: dict[str, str] = {}
_next_ask_n = 1


def _default_store_dir() -> Path:
    override = os.environ.get("AGENT_SI_SESSION_STORE")
    if override:
        return Path(override)
    return Path(tempfile.gettempdir()) / "agent_si_ui_sessions"


def _persist_card(card: AskCard) -> None:
    store_dir = _default_store_dir()
    store_dir.mkdir(parents=True, exist_ok=True)
    record = {"session_id": card.ask_id, "kind": card.kind, "title": card.summary}
    (store_dir / f"{card.ask_id}.json").write_text(
        json.dumps(record), encoding="utf-8"
    )


def create_ask_card(
    *,
    kind: AskKind,
    summary: str,
    options: Sequence[AskOption],
    secret_ref: Optional[str] = None,
) -> AskCard:
    global _next_ask_n
    if kind not in _ASK_KINDS:
        raise ValueError(f"unknown ask kind: {kind!r}")
    n = _next_ask_n
    _next_ask_n += 1
    card = AskCard(
        ask_id=f"ask-{n}",
        kind=kind,
        summary=summary,
        options=tuple(options),
        resume_token=f"resume-{n}",
    )
    _cards_by_token[card.resume_token] = card
    _token_by_ask_id[card.ask_id] = card.resume_token
    _persist_card(card)
    return card


def _lookup_card(ask_id: str, resume_token: str) -> AskCard:
    card = _cards_by_token.get(resume_token)
    if card is None:
        raise PermissionError(f"unknown resume token for ask {ask_id!r}")
    if card.ask_id != ask_id:
        raise PermissionError(f"resume token does not match ask {ask_id!r}")
    return card


def approve_ask(
    *,
    ask_id: str,
    option_id: str,
    resume_token: str,
) -> ApprovalResult:
    if not ask_id or not option_id or not resume_token:
        raise PermissionError("missing ask approval credential")
    card = _lookup_card(ask_id, resume_token)
    if option_id not in {o.option_id for o in card.options}:
        raise PermissionError(f"unknown option {option_id!r} for ask {ask_id!r}")
    return ApprovalResult(
        ask_id=card.ask_id,
        approved_option_id=option_id,
        resume_token=card.resume_token,
    )


def resume_ask(*, resume_token: str) -> AskCard:
    if not resume_token:
        raise PermissionError("missing resume token")
    card = _cards_by_token.get(resume_token)
    if card is None:
        raise PermissionError("unknown resume token")
    return card


def _canonical(path: str | Path) -> str:
    return os.path.normcase(os.path.realpath(os.fspath(path)))


def _check_roots(store_path: str | Path) -> None:
    raw = os.environ.get("AGENT_SI_SESSION_ROOTS")
    if raw is None:
        return
    roots = [entry for entry in raw.split(os.pathsep) if entry]
    if not roots:
        return
    candidate = _canonical(store_path)
    for root in roots:
        base = _canonical(root)
        if candidate == base or candidate.startswith(base + os.sep):
            return
    raise PermissionError(f"session store path outside allowed roots: {store_path}")


def _read_session_file(path: Path) -> SessionSummary | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    session_id = data.get("session_id", data.get("ask_id"))
    title = data.get("title", data.get("summary"))
    if not session_id or not isinstance(title, str):
        return None
    return SessionSummary(session_id=session_id, title=title)


def list_sessions(*, store_path: str | Path) -> list[SessionSummary]:
    _check_roots(store_path)
    found: dict[str, str] = {}
    try:
        files = sorted(Path(store_path).glob("*.json"))
    except OSError:
        files = []
    for path in files:
        summary = _read_session_file(path)
        if summary is not None:
            found.setdefault(summary.session_id, summary.title)
    for card in _cards_by_token.values():
        found.setdefault(card.ask_id, card.summary)
    return [
        SessionSummary(session_id=session_id, title=found[session_id])
        for session_id in sorted(found)
    ]
