"""K09-B validator tests, STEP2.

Covers the CLI (accept good, reject each malformed fixture with its exact
code) plus one direct validate_kb_dir condition per error code. Real
fixtures only; no fakes.
"""

import os
import sys

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)

from tools.kb_validator.iface import (
    KB_MANIFEST_MISSING,
    KB_PURPOSE_MISSING,
    KB_SECTIONS_MISSING,
    KbValidationResult,
    validate_kb_dir,
)
from tools.kb_validator.validate_kb import main

FIX = os.path.join(_WS, "tests", "fixtures", "k09b")


def test_cli_accepts_good(capsys):
    kb_dir = os.path.join(FIX, "good")
    assert main([kb_dir]) == 0
    out = capsys.readouterr().out
    assert kb_dir in out
    assert "OK" in out


def test_cli_rejects_missing_manifest(capsys):
    kb_dir = os.path.join(FIX, "no-manifest")
    assert main([kb_dir]) == 1
    out = capsys.readouterr().out
    assert kb_dir in out
    assert KB_MANIFEST_MISSING in out


def test_cli_rejects_missing_sections(capsys):
    kb_dir = os.path.join(FIX, "no-sections")
    assert main([kb_dir]) == 1
    out = capsys.readouterr().out
    assert kb_dir in out
    assert KB_SECTIONS_MISSING in out


def test_cli_rejects_missing_purpose(capsys):
    kb_dir = os.path.join(FIX, "no-purpose")
    assert main([kb_dir]) == 1
    out = capsys.readouterr().out
    assert kb_dir in out
    assert KB_PURPOSE_MISSING in out


def test_iface_manifest_condition():
    kb_dir = os.path.join(FIX, "no-manifest")
    result = validate_kb_dir(kb_dir)
    assert isinstance(result, KbValidationResult)
    assert result.kb_dir == kb_dir
    assert result.ok is False
    assert result.error_code == KB_MANIFEST_MISSING


def test_iface_sections_condition():
    kb_dir = os.path.join(FIX, "no-sections")
    result = validate_kb_dir(kb_dir)
    assert isinstance(result, KbValidationResult)
    assert result.kb_dir == kb_dir
    assert result.ok is False
    assert result.error_code == KB_SECTIONS_MISSING


def test_iface_purpose_condition():
    kb_dir = os.path.join(FIX, "no-purpose")
    result = validate_kb_dir(kb_dir)
    assert isinstance(result, KbValidationResult)
    assert result.kb_dir == kb_dir
    assert result.ok is False
    assert result.error_code == KB_PURPOSE_MISSING


def test_iface_echoes_kb_dir_on_success():
    kb_dir = os.path.join(FIX, "good")
    result = validate_kb_dir(kb_dir)
    assert isinstance(result, KbValidationResult)
    assert result.kb_dir == kb_dir
    assert result.ok is True
    assert result.error_code is None
