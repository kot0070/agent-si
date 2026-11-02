"""FXSPLASH RED: splash mark + i18n + first-start gating, failure page, icon bundle."""
from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from agent_si import sidecar  # noqa: E402


def test_splash_has_inline_mark_no_network_no_path_en():
    html = sidecar._splash_html(first_start=False, lang="en")
    assert "<svg" in html
    assert "Starting" in html
    assert "http://" not in html and "https://" not in html
    assert "C:\\" not in html and "D:\\" not in html and "/home/" not in html
    assert "C:" not in html


def test_splash_uk_and_first_start_gating():
    normal = sidecar._splash_html(first_start=False, lang="uk")
    first = sidecar._splash_html(first_start=True, lang="uk")
    assert "minute" not in normal and "хвилин" not in normal
    assert ("minute" in first) or ("хвилин" in first)


def test_failure_page_keeps_fields_and_escapes():
    html = sidecar._failure_html("<b>&\"x\"", "/tmp/logs here", lang="en")
    assert "&lt;b&gt;" in html and "&amp;" in html and "&quot;" in html
    assert "<b>" not in html
    assert "Log files:" in html or "logs" in html.lower()
    assert "Next step" in html or "next step" in html.lower()


def test_frozen_asset_ref_resolves_inside_bundle(monkeypatch, tmp_path):
    meipass = tmp_path / "meipass"
    (meipass / "assets").mkdir(parents=True)
    src = os.path.join(_ROOT, "src", "agent_si", "assets", "icon.ico")
    import shutil

    shutil.copyfile(src, meipass / "assets" / "icon.ico")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
    assert sidecar._asset_ref("icon.ico") == str(
        meipass / "assets" / "icon.ico")
    assert os.path.isfile(sidecar._asset_ref("icon.ico"))


def test_icon_bundle_sizes_and_spec_and_frozen():
    ico = os.path.join(_ROOT, "src", "agent_si", "assets", "icon.ico")
    assert os.path.isfile(ico), "icon.ico missing"
    with open(ico, "rb") as handle:
        blob = handle.read()
    assert blob[:4] == b"\x00\x00\x01\x00"
    count = struct.unpack("<H", blob[4:6])[0]
    widths = {blob[6 + 16 * i] or 256 for i in range(count)}
    for need in (16, 24, 32, 48, 64, 128, 256):
        assert need in widths, f"ico missing size {need}"
    spec = Path(
        _ROOT, "packaging", "sidecar", "agent_si_sidecar.spec").read_text(
        encoding="utf-8")
    assert "icon.ico" in spec
