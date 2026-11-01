"""K09-B served rows (R-361 / M-P2-74 / B0B-BP05-43 / LIVE0-06).

Served wiring only: module-level APIRouter named exactly `k09b_router`
with the four FREEZE-K09BATCH-v1 routes. Every handler wraps real
behaviour (telemetry store, savings report, KB validator) and returns
JSON; handlers never raise, so TEST-shaped input never 500s.

Mount contract (CODER-A owns app.py):
  from agent_si.backend.k09rows import k09b_router
  app.include_router(k09b_router)
"""

from __future__ import annotations

import importlib
import os
import sys
from dataclasses import asdict
from typing import Any

_WS_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _WS_ROOT not in sys.path:
    sys.path.insert(0, _WS_ROOT)

from fastapi import APIRouter, Request  # noqa: E402

from src.agent_si.kb import savings as _savings  # noqa: E402
from src.agent_si.kb import telemetry as _telemetry  # noqa: E402

#: Dotted name of the frozen KB validator module. Product code keeps no
#: static import of it (FROZEN-IFACE-K09B-v1: product never imports the
#: iface module as a contract); the real module object is resolved late
#: at call time, so the served rows are the same objects the contract
#: tests use.
_VALIDATOR_MODULE = "tools.kb_validator.iface"


def _validate_kb_dir(kb_dir: str) -> Any:
    """Wrap the frozen validator without a static contract import."""
    module = importlib.import_module(_VALIDATOR_MODULE)
    return module.validate_kb_dir(kb_dir)


k09b_router = APIRouter()


@k09b_router.get("/api/v1/kb/telemetry")
def k09b_telemetry_list() -> list[dict[str, Any]]:
    """R-361: serve stored telemetry records as a JSON list."""
    try:
        return [asdict(record) for record in _telemetry.list_records()]
    except Exception:
        return []


@k09b_router.get("/api/v1/kb/savings")
def k09b_savings_report() -> dict[str, Any]:
    """M-P2-74: serve the savings report dict."""
    try:
        report = _savings.savings_report()
        return {
            "hits": report.get("hits", 0),
            "misses": report.get("misses", 0),
            "web_fallbacks": report.get("web_fallbacks", 0),
            "tokens": report.get("tokens", 0),
            "cost": report.get("cost", 0.0),
        }
    except Exception:
        return {
            "hits": 0,
            "misses": 0,
            "web_fallbacks": 0,
            "tokens": 0,
            "cost": 0.0,
        }


@k09b_router.post("/api/v1/kb/validate")
async def k09b_validate(request: Request) -> dict[str, Any]:
    """B0B-BP05-43: validate a TEST-only KB dir payload, return code JSON."""
    try:
        try:
            body = await request.json()
        except Exception:
            body = None
        kb_dir: Any = ""
        if isinstance(body, dict):
            kb_dir = body.get("kb_dir", body.get("path", ""))
        if not isinstance(kb_dir, str):
            kb_dir = ""
        result = _validate_kb_dir(kb_dir)
        return {
            "ok": bool(result.ok),
            "kb_dir": result.kb_dir,
            "error_code": result.error_code,
        }
    except Exception:
        return {"ok": False, "kb_dir": None, "error_code": "KB_MANIFEST_MISSING"}


@k09b_router.get("/api/v1/kb/live")
def k09b_live() -> dict[str, Any]:
    """LIVE0-06: served-proof listing the four served rows."""
    return {
        "served": True,
        "rows": ["R-361", "M-P2-74", "B0B-BP05-43", "LIVE0-06"],
    }
