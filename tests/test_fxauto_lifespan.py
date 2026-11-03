"""FXAUTO ORDER 56 RED: app shutdown must end clean with rules saved.

uvicorn log showed `Application shutdown failed` with CancelledError from
the FXAUTO tick loop: `except Exception` around `await _fxauto_task`
does not catch CancelledError (BaseException), so the save on shutdown
was skipped and the failure propagated through the lifespan stack.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import fastapi.testclient  # noqa: E402

from agent_si.automation import (  # noqa: E402
    pause,
    runner,
    rules,
    scheduler,
    triggers,
)
from agent_si.backend.app import create_app  # noqa: E402


def _settings(tmp_path):
    return {"store_dir": str(tmp_path / "appdata"),
            "ui_session_token": "fxauto-shutdown-token",
            "secret_store": "memory"}


def test_lifespan_shutdown_clean_and_saves_rules(tmp_path):
    for lane in (pause, runner, scheduler, triggers):
        lane.reset_state()
    rules.reset_state()
    app = create_app(_settings(tmp_path))
    with fastapi.testclient.TestClient(app, raise_server_exceptions=True):
        pass
    saved = os.path.join(str(tmp_path), "appdata", "automation",
                         "rules.json")
    assert os.path.exists(saved), "rules must be saved on shutdown"
