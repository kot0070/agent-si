"""K06 Lane A toolguard -- ASK card shape helpers.

ASK cards carry ask_id, kind, summary, options and resume_token.
A card is plain data describing a question; resuming needs the
opaque token the card carried, and an empty token resumes
nothing.
"""

from __future__ import annotations

from typing import Any

ASK_CARD_FIELDS: tuple[str, ...] = (
    "ask_id",
    "kind",
    "summary",
    "options",
    "resume_token",
)


def build_ask_card(
    ask_id: str,
    kind: str,
    summary: str,
    options: list[str],
    resume_token: str,
) -> dict[str, Any]:
    """Build the ASK card dict with exactly the card fields."""
    return {
        "ask_id": ask_id,
        "kind": kind,
        "summary": summary,
        "options": list(options),
        "resume_token": resume_token,
    }


def resume_from_token(
    resume_token: str,
) -> dict[str, Any]:
    """Resume from a token; an empty or missing token refuses."""
    if not isinstance(resume_token, str) or not resume_token:
        raise PermissionError("cannot resume: empty resume token")
    return {"resume_token": resume_token}
