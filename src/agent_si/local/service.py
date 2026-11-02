# Copyright (c) 2026 Ivan Soprun
"""K05 local service facade (HS-L1 wiring).

The backend/local_connect.py, local/adapter.py and local/gateway.py
REALIZATION_MAPs name this module's dotted targets; it was absent, so
any resolver got ModuleNotFoundError. Every class here delegates to
the real owning-lane implementation (no logic, no state, stdlib
plus agent_si only):

- LocalRuntimeService -> backend.local_connect entry points
- LocalAdapter -> local.adapter lane functions
- LifecycleService -> local.adapter lifecycle functions
- GatewayService -> local.gateway.passive_check
"""

from __future__ import annotations

from typing import Any


class LocalRuntimeService:
    """Local runtime entries owned by backend.local_connect."""

    @staticmethod
    def get_status() -> Any:
        from agent_si.backend import local_connect as _lane

        return _lane.get_status()

    @staticmethod
    def connect(runtime_ref: str, session_token: Any) -> Any:
        from agent_si.backend import local_connect as _lane

        return _lane.connect(runtime_ref, session_token)

    @staticmethod
    def disconnect(session_token: Any) -> Any:
        from agent_si.backend import local_connect as _lane

        return _lane.disconnect(session_token)

    @staticmethod
    def list_models() -> Any:
        from agent_si.backend import local_connect as _lane

        return _lane.list_models()


class LocalAdapter:
    """Local decision entries owned by local.adapter."""

    @staticmethod
    def check_eligibility(*args: Any, **kwargs: Any) -> Any:
        from agent_si.local import adapter as _lane

        return _lane.check_eligibility(*args, **kwargs)

    @staticmethod
    def record_explicit_pin(*args: Any, **kwargs: Any) -> Any:
        from agent_si.local import adapter as _lane

        return _lane.record_explicit_pin(*args, **kwargs)

    @staticmethod
    def record_split_decision(*args: Any, **kwargs: Any) -> Any:
        from agent_si.local import adapter as _lane

        return _lane.record_split_decision(*args, **kwargs)

    @staticmethod
    def routing_continues(*args: Any, **kwargs: Any) -> Any:
        from agent_si.local import adapter as _lane

        return _lane.routing_continues(*args, **kwargs)

    @staticmethod
    def check_admission(*args: Any, **kwargs: Any) -> Any:
        from agent_si.local import adapter as _lane

        return _lane.check_admission(*args, **kwargs)

    @staticmethod
    def record_verifier_decision(*args: Any, **kwargs: Any) -> Any:
        from agent_si.local import adapter as _lane

        return _lane.record_verifier_decision(*args, **kwargs)

    @staticmethod
    def reexamine_verifier_content(*args: Any, **kwargs: Any) -> Any:
        from agent_si.local import adapter as _lane

        return _lane.reexamine_verifier_content(*args, **kwargs)

    @staticmethod
    def confirm_verifier_link(*args: Any, **kwargs: Any) -> Any:
        from agent_si.local import adapter as _lane

        return _lane.confirm_verifier_link(*args, **kwargs)

    @staticmethod
    def route_by_policy(*args: Any, **kwargs: Any) -> Any:
        from agent_si.local import adapter as _lane

        return _lane.route_by_policy(*args, **kwargs)


class LifecycleService:
    """Lifecycle entries owned by local.adapter."""

    @staticmethod
    def position(*args: Any, **kwargs: Any) -> Any:
        from agent_si.local import adapter as _lane

        return _lane.lifecycle_position(*args, **kwargs)

    @staticmethod
    def advance(*args: Any, **kwargs: Any) -> Any:
        from agent_si.local import adapter as _lane

        return _lane.advance_lifecycle(*args, **kwargs)


class GatewayService:
    """Gateway probe owned by local.gateway."""

    @staticmethod
    def passive_check(*args: Any, **kwargs: Any) -> Any:
        from agent_si.local import gateway as _lane

        return _lane.passive_check(*args, **kwargs)


__all__ = [
    "GatewayService",
    "LifecycleService",
    "LocalAdapter",
    "LocalRuntimeService",
]
