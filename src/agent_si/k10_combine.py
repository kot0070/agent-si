"""K10ST4 M-P4-166: combine best plus KB plus benchmark plus Watcher (loopback).

Row: kit BUILD_PLAN M-P4-166 "every package combines best plus KB plus
benchmark plus Watcher on DEFAULT". This module carries a small FIXED
recorded dataset: plain in-code values, stdlib only, no network, no
providers, no I/O, deterministic. DEFAULT always includes all four parts.
Pure function, no settings or global mutation.
"""

from __future__ import annotations


def combine_default(package_id: str) -> dict:
    """Return the fixed recorded DEFAULT combine for one package id."""
    return {
        "package_id": package_id,
        "best": {
            "package_id": package_id,
            "detail": (
                "recorded: best-row pick on loopback fixture "
                "(not routed live)"
            ),
        },
        "kb": {
            "package_id": package_id,
            "detail": (
                "recorded: knowledge-base row on loopback fixture "
                "(not fetched live)"
            ),
        },
        "benchmark": {
            "package_id": package_id,
            "detail": (
                "recorded: benchmark row on loopback fixture "
                "(not measured live)"
            ),
        },
        "watcher": {
            "package_id": package_id,
            "detail": (
                "recorded: Watcher row on loopback fixture "
                "(not watched live)"
            ),
        },
        "mode": "default",
    }
