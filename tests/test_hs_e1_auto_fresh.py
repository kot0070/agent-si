"""HS-E1: AUTO on a fresh project with one provider (RED-first).

Fresh install holds no role profiles; the suspected blocker says
every resolution stays BLOCKED. The served AUTO path
(GET /api/v1/routing/auto) must still return a runnable
manager+model for one connected provider. One test only: green
means no rewrite.
"""
import copy
import os
import sys

from fastapi.testclient import TestClient

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.model_kb import kb as _kb  # noqa: E402

SRC = "https://example.invalid/hs-e1"
AT = "2026-11-02"

TOKEN = "hs-e1-token"


def _catalog():
    rows = [_kb.make_model_row(
        "openai", "gpt-4o",
        {"modalities": _kb.sourced("text, tools, coding", SRC, AT),
         "tool_calling": _kb.sourced("yes", SRC, AT),
         "input_token_price": _kb.sourced(1.0, SRC, AT),
         "output_token_price": _kb.sourced(2.0, SRC, AT)})]
    return _kb.make_catalog(rows, kb_version=1, updated_at=AT,
                            change_log=[], sources=[])


def test_auto_runs_on_fresh_project_with_one_provider():
    """Fresh project, one connected provider: AUTO returns a model."""
    saved = copy.deepcopy(_kb.bound_catalog())
    _kb.bind_catalog(_catalog())
    try:
        app = create_app({"testing": True, "ui_session_token": TOKEN})
        client = TestClient(app)
        resp = client.get("/api/v1/routing/auto",
                          params={"task_type": "coding",
                                  "connected": "openai"})
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"manager": "openai", "model": "gpt-4o"}
    finally:
        _kb.bind_catalog(saved)
