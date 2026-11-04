"""PLANB: a clean install carries uvicorn and the agent-si command starts the sidecar."""

from __future__ import annotations

import importlib
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def _project() -> dict:
    with open(ROOT / "pyproject.toml", "rb") as handle:
        return tomllib.load(handle)["project"]


def test_uvicorn_is_a_dependency():
    names = [dep.split("==")[0].strip().lower() for dep in _project()["dependencies"]]
    assert "uvicorn" in names
    sidecar_src = (ROOT / "src" / "agent_si" / "sidecar.py").read_text(encoding="utf-8")
    assert "import uvicorn" in sidecar_src


def test_agent_si_script_points_at_the_sidecar_main():
    target = _project()["scripts"]["agent-si"]
    module_name, _, attr = target.partition(":")
    assert (module_name, attr) == ("agent_si.sidecar", "main")
    entry = getattr(importlib.import_module(module_name), attr)
    assert callable(entry)
    sidecar = importlib.import_module("agent_si.sidecar")
    assert entry is sidecar.main


def test_agent_si_script_is_not_the_app_factory():
    assert "create_app" not in _project()["scripts"]["agent-si"]
