"""FXLOC C3: local_connect REALIZATION_MAP names a real module.

Every map entry must import (module + class + method resolve to a
callable); the service delegates to the real entry points (fake
endpoint only: detached/loopback behaviour, no Ollama).
"""
from __future__ import annotations

import importlib
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))

from agent_si.backend import local_connect  # noqa: E402

_TOKEN = "fxloc-c3-token"


def _resolve(target: str):
    parts = target.split(".")
    assert len(parts) >= 2, target
    for cut in range(len(parts) - 1, 0, -1):
        try:
            obj = importlib.import_module(".".join(parts[:cut]))
        except ImportError:
            continue
        for part in parts[cut:]:
            obj = getattr(obj, part)
        return obj
    raise AssertionError("unresolvable: %s" % target)


def test_every_realization_map_entry_imports():
    assert local_connect.REALIZATION_MAP, "empty REALIZATION_MAP"
    for name, target in local_connect.REALIZATION_MAP.items():
        assert callable(getattr(local_connect, name)), name
        resolved = _resolve(target)
        assert callable(resolved), (name, target)


def test_service_delegates_to_real_entries():
    from agent_si.local import service

    assert service.LocalRuntimeService.get_status().status == \
        local_connect.get_status().status == "NOT_CONFIGURED"
    assert service.LocalRuntimeService.list_models() == ()
    status = service.LocalRuntimeService.connect(
        "fxloc-c3-ref", session_token=_TOKEN)
    assert status.status == "NOT_CONFIGURED"
    assert local_connect.get_status().reason != ""
    service.LocalRuntimeService.disconnect(session_token=_TOKEN)
    assert service.LocalRuntimeService.list_models() == ()
    assert local_connect.get_status().status == "NOT_CONFIGURED"
