"""K12OPEN1 R-350 idea/demo public-text rules (pure logic, no I/O).

RULES is the served rule table; check_idea reports one violation per
broken rule. A rule fires when any of the supplied public texts (the
idea plus the optional presentation/demo texts) matches its pattern.
Blank or missing texts never fire: the served layer owns EMPTY_IDEA_TEXT.
"""

from __future__ import annotations

import re

#: A public idea/demo text carries something shaped like a credential.
RULE_SECRET_IN_PUBLIC_TEXT = "SECRET_IN_PUBLIC_TEXT"

#: A public idea/demo text carries a private-looking filesystem path.
RULE_PRIVATE_PATH_IN_PUBLIC_TEXT = "PRIVATE_PATH_IN_PUBLIC_TEXT"

#: Served rule table; each row carries {code, message}.
RULES = (
    {
        "code": RULE_SECRET_IN_PUBLIC_TEXT,
        "message": "public idea/demo text must not contain secrets",
    },
    {
        "code": RULE_PRIVATE_PATH_IN_PUBLIC_TEXT,
        "message": "public idea/demo text must not contain private paths",
    },
)

_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{8,}"),
    re.compile(r"xox[bpars]-[A-Za-z0-9-]{8,}"),
    re.compile(
        r"(?i)\b(api[_-]?key|secret|password|passwd|token)\b\s*[:=]\s*\S+"
    ),
)

_PRIVATE_PATH_PATTERNS = (
    re.compile(r"/home/[^\s\"']+"),
    re.compile(r"C:\\Users\\[^\s\"']+", re.IGNORECASE),
    re.compile(r"(?i)\.ssh/[^\s\"']*"),
    re.compile(r"(?i)\.(pem|key)\b"),
    re.compile(r"(?i)/private/[^\s\"']+"),
)

_RULE_PATTERNS = (
    (RULE_SECRET_IN_PUBLIC_TEXT, _SECRET_PATTERNS),
    (RULE_PRIVATE_PATH_IN_PUBLIC_TEXT, _PRIVATE_PATH_PATTERNS),
)


def _texts_of(
    idea_text: object,
    presentation: object = None,
    video_demo: object = None,
) -> list:
    """Collect the supplied public texts; non-string values are ignored."""
    texts = []
    for value in (idea_text, presentation, video_demo):
        if isinstance(value, str) and value:
            texts.append(value)
    return texts


def check_idea(
    idea_text: object,
    presentation: object = None,
    video_demo: object = None,
) -> list:
    """Report one {code, message} violation per broken public-text rule."""
    texts = _texts_of(idea_text, presentation, video_demo)
    violations = []
    for code, patterns in _RULE_PATTERNS:
        if any(
            pattern.search(text) for text in texts for pattern in patterns
        ):
            message = next(
                rule["message"] for rule in RULES if rule["code"] == code
            )
            violations.append({"code": code, "message": message})
    return violations
