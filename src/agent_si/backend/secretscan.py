"""K12OPEN1 HC-3 secret/private scan (pure logic, no I/O).

SCAN_PATTERNS pairs each finding code with the compiled patterns that
raise it; scan_files walks submission files (plus the optional notes
pseudo-file) and reports one {code, path, message} finding per hit.
"""

from __future__ import annotations

import re

#: A file carries something shaped like a credential.
SECRET_DETECTED = "SECRET_DETECTED"

#: A file path or body points at a private location.
PRIVATE_PATH = "PRIVATE_PATH"

_MESSAGES = {
    SECRET_DETECTED: "submission carries a possible secret",
    PRIVATE_PATH: "submission references a private path",
}

#: (finding code, compiled patterns) pairs owned by this part.
SCAN_PATTERNS = (
    (
        SECRET_DETECTED,
        (
            re.compile(r"sk-[A-Za-z0-9]{8,}"),
            re.compile(r"AKIA[0-9A-Z]{16}"),
            re.compile(r"gh[pousr]_[A-Za-z0-9]{8,}"),
            re.compile(r"xox[bpars]-[A-Za-z0-9-]{8,}"),
            re.compile(
                r"(?i)\b(api[_-]?key|secret|password|passwd|token)\b"
                r"\s*[:=]\s*\S+"
            ),
        ),
    ),
    (
        PRIVATE_PATH,
        (
            re.compile(r"/home/[^\s\"']+"),
            re.compile(r"C:\\Users\\[^\s\"']+", re.IGNORECASE),
            re.compile(r"(?i)\.ssh/[^\s\"']*"),
            re.compile(r"(?i)\.(pem|key)\b"),
            re.compile(r"(?i)/private/[^\s\"']+"),
        ),
    ),
)

#: Pseudo-file path under which the free-text notes are scanned.
NOTES_PATH = "notes"


def _as_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return str(value)


def _scan_one(path: str, body: str) -> list:
    """Findings for a single path/body pair, at most one per code."""
    findings = []
    for code, patterns in SCAN_PATTERNS:
        if code == SECRET_DETECTED:
            haystacks = (body,)
        else:
            haystacks = (path, body)
        if any(
            pattern.search(hay)
            for hay in haystacks
            for pattern in patterns
        ):
            findings.append(
                {"code": code, "path": path, "message": _MESSAGES[code]}
            )
    return findings


def scan_files(files: object, notes: object = None) -> list:
    """Scan submission files plus optional notes for secrets/paths."""
    findings = []
    if isinstance(files, list):
        for entry in files:
            if not isinstance(entry, dict):
                continue
            findings.extend(
                _scan_one(_as_text(entry.get("path")),
                          _as_text(entry.get("content")))
            )
    note_text = _as_text(notes)
    if note_text.strip():
        findings.extend(_scan_one(NOTES_PATH, note_text))
    return findings
