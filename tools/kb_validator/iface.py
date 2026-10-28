"""K09-B KB validator surface interface, STEP2 (implemented).

FROZEN-IFACE-K09B-v1: type, function and error-code names are frozen.
Validator is standalone stdlib only and mirrors the registry rules; product
code never imports this module as a contract.
KB dir shape: manifest.json + sections/*.md + purpose declaration.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

KB_MANIFEST_MISSING = "KB_MANIFEST_MISSING"
KB_SECTIONS_MISSING = "KB_SECTIONS_MISSING"
KB_PURPOSE_MISSING = "KB_PURPOSE_MISSING"


@dataclass
class KbValidationResult:
    ok: bool
    kb_dir: str
    error_code: Optional[str] = None


def _load_manifest(kb_dir: str) -> Optional[dict]:
    """Manifest dict, or None when missing/unparseable/non-dict."""
    if not os.path.isdir(kb_dir):
        return None
    try:
        with open(os.path.join(kb_dir, "manifest.json"), encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _has_sections(kb_dir: str) -> bool:
    """True with sections/*.md or flat top-level *.md (the ONE adapter).

    Only .md files count, so manifest.json and purpose.txt never qualify.
    """
    sections_dir = os.path.join(kb_dir, "sections")
    if os.path.isdir(sections_dir):
        try:
            entries = os.listdir(sections_dir)
        except OSError:
            entries = []
        if any(
            name.endswith(".md")
            and os.path.isfile(os.path.join(sections_dir, name))
            for name in entries
        ):
            return True
    try:
        top = os.listdir(kb_dir)
    except OSError:
        return False
    return any(
        name.endswith(".md") and os.path.isfile(os.path.join(kb_dir, name))
        for name in top
    )


def validate_kb_dir(kb_dir: str) -> KbValidationResult:
    """Validate a KB dir; checks run manifest, then sections, then purpose."""
    manifest = _load_manifest(kb_dir)
    if manifest is None:
        return KbValidationResult(
            ok=False, kb_dir=kb_dir, error_code=KB_MANIFEST_MISSING
        )
    if not _has_sections(kb_dir):
        return KbValidationResult(
            ok=False, kb_dir=kb_dir, error_code=KB_SECTIONS_MISSING
        )
    purpose = manifest.get("purpose")
    purpose_ok = os.path.isfile(os.path.join(kb_dir, "purpose.txt")) or (
        isinstance(purpose, str) and purpose.strip() != ""
    )
    if not purpose_ok:
        return KbValidationResult(
            ok=False, kb_dir=kb_dir, error_code=KB_PURPOSE_MISSING
        )
    return KbValidationResult(ok=True, kb_dir=kb_dir, error_code=None)
