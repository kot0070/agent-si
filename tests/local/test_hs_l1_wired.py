"""HS-L1: every declared local writer resolves to a production caller (RED-first).

backend/local_connect.py plus local/adapter.py and local/gateway.py
declare REALIZATION_MAP dotted targets under agent_si.local.service,
but that module is absent: any resolver gets ModuleNotFoundError.
Each dotted target must import to the real callable (wired through
the owning lane), or the map entry goes with a note.
"""
from __future__ import annotations

import importlib
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))

from agent_si.backend import local_connect as _lc  # noqa: E402
from agent_si.local import adapter as _adapter  # noqa: E402
from agent_si.local import gateway as _gateway  # noqa: E402


def _resolve(dotted):
    parts = dotted.split(".")
    for depth in range(len(parts) - 1, 0, -1):
        try:
            target = importlib.import_module(".".join(parts[:depth]))
        except ModuleNotFoundError:
            continue
        for part in parts[depth:]:
            target = getattr(target, part)
        assert callable(target), dotted
        return target
    raise AssertionError("unresolvable: %s" % dotted)


def test_local_connect_targets_resolve():
    """backend/local_connect map targets import to callables."""
    for name, dotted in _lc.REALIZATION_MAP.items():
        assert callable(getattr(_lc, name)), name
        _resolve(dotted)


def test_service_delegates_to_lane_implementations():
    """The facade calls the real owning-lane functions, not copies."""
    from agent_si.local import service as _service

    status = _service.LocalRuntimeService.get_status()
    assert status.status == "NOT_CONFIGURED"
    assert _service.LocalRuntimeService.list_models() == ()
    assert _service.GatewayService.passive_check is not None


def test_adapter_gateway_targets_resolve():
    """adapter/gateway map targets import to callables."""
    for name, dotted in _adapter.REALIZATION_MAP.items():
        assert callable(getattr(_adapter, name)), name
        _resolve(dotted)
    for name, dotted in _gateway.REALIZATION_MAP.items():
        assert callable(getattr(_gateway, name)), name
        _resolve(dotted)
