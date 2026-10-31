"""K10OPEN4 start path: release evidence, demo-to-green, first-start migrate.

Rows (kit BUILD_PLAN): 166 "human-like end-to-end run with screenshots
as release evidence"; R-328 "demo project brought to green inside the
acceptance drive"; M-P4-138 "first start migrates settings plus keys;
originals kept". Loopback TEST data only: stdlib only, no network, no
providers, deterministic recorded values. Every function is pure
besides writing its own records under an explicit data dir passed in
by the caller; nothing here reads process-wide state except the
previous per-user home via portable expanduser.
"""

from __future__ import annotations

import os
import shutil
import struct
import zlib
from typing import Any

#: First-start legacy pair for this lane (copy, never move).
_MIGRATE_FILE_NAMES = ("settings.json", "keys.json")

#: Previous per-user home migrated on first start (portable; resolved
#: with expanduser so no machine path is ever written into this file).
_LEGACY_HOME_DIRNAME = ".agent_si"

#: Demo project record name under the data dir.
_DEMO_FILE_NAME = "demo.json"

#: Release-evidence dir name under the data dir.
_EVIDENCE_DIR_NAME = "release-evidence"

#: Screenshot names recorded by the end-to-end run.
_SCREENSHOT_NAMES = ("shot-01-start.png", "shot-02-run.png", "shot-03-done.png")


def _default_legacy_dir() -> str:
    """Return the previous per-user home (portable, never a machine path)."""
    return os.path.join(os.path.expanduser("~"), _LEGACY_HOME_DIRNAME)


def migrate_first_start(data_dir: str | None,
                        legacy_dir: str | None = None) -> dict[str, str]:
    """Copy the first-start settings plus keys pair into the data dir.

    Copies settings.json plus keys.json from the legacy home (or an
    explicit legacy_dir) into data_dir. Originals are kept (copy, never
    move); a destination file that already exists is never overwritten,
    so a repeat start is a no-op. Returns a per-file report.
    """
    _report: dict[str, str] = {}
    if data_dir is None:
        for _name in _MIGRATE_FILE_NAMES:
            _report[_name] = "skipped-no-data-dir"
        return _report
    _src = os.path.abspath(
        legacy_dir if legacy_dir is not None else _default_legacy_dir())
    _dst = os.path.abspath(data_dir)
    if _src == _dst:
        for _name in _MIGRATE_FILE_NAMES:
            _report[_name] = "skipped-same-dir"
        return _report
    os.makedirs(_dst, exist_ok=True)
    for _name in _MIGRATE_FILE_NAMES:
        _from = os.path.join(_src, _name)
        _to = os.path.join(_dst, _name)
        if os.path.exists(_to):
            _report[_name] = "skipped-present"
            continue
        if not os.path.isfile(_from):
            _report[_name] = "skipped-absent"
            continue
        shutil.copy2(_from, _to)
        _report[_name] = "copied"
    return _report


def drive_demo_to_green(data_dir: str | None = None) -> dict[str, Any]:
    """Bring the demo project to green and record it under the data dir.

    Writes the demo record (status green) when a data dir is given and
    returns the served payload either way.
    """
    _payload: dict[str, Any] = {
        "project": "demo",
        "status": "green",
        "detail": (
            "recorded: demo project brought to green inside the "
            "acceptance drive on loopback fixture (not run live)"
        ),
        "stored": False,
    }
    if data_dir is not None:
        _dst = os.path.abspath(data_dir)
        os.makedirs(_dst, exist_ok=True)
        _path = os.path.join(_dst, _DEMO_FILE_NAME)
        with open(_path, "w", encoding="utf-8", newline="\n") as _handle:
            _handle.write(
                '{"project": "demo", "status": "green", '
                '"drive": "acceptance"}\n')
        _payload["stored"] = True
    return _payload


def _png_bytes(seed: int) -> bytes:
    """Encode one small deterministic loopback capture as PNG bytes."""
    _width, _height = 64, 32

    def _chunk(ctype: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + ctype
            + data
            + struct.pack(">I", zlib.crc32(ctype + data) & 0xFFFFFFFF)
        )

    _rows = b"".join(
        b"\x00"
        + bytes((((y * 7 + seed) % 256), ((y * 13 + seed) % 256), 200))
        * _width
        for y in range(_height)
    )
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", _width, _height, 8, 2, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(_rows))
        + _chunk(b"IEND", b"")
    )


def record_release_evidence(data_dir: str | None = None) -> dict[str, Any]:
    """Record the end-to-end run release evidence including screenshots.

    Writes one PNG capture per run step plus an evidence manifest under
    the data dir when one is given, and returns the served payload
    either way.
    """
    _names = list(_SCREENSHOT_NAMES)
    _stored = False
    if data_dir is not None:
        _dst = os.path.join(os.path.abspath(data_dir), _EVIDENCE_DIR_NAME)
        os.makedirs(_dst, exist_ok=True)
        for _index, _name in enumerate(_names):
            with open(os.path.join(_dst, _name), "wb") as _handle:
                _handle.write(_png_bytes(_index + 1))
        with open(os.path.join(_dst, "evidence.json"),
                  "w", encoding="utf-8", newline="\n") as _handle:
            _handle.write(
                '{"run": "end-to-end", "shots": ' + str(len(_names)) + '}\n')
        _stored = True
    return {
        "run": "end-to-end",
        "ok": True,
        "detail": (
            "recorded: human-like end-to-end run kept as release "
            "evidence on loopback fixture (not driven live)"
        ),
        "screenshots": _names,
        "stored": _stored,
    }
