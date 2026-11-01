"""FXBENCH1: the Local bench scan the window sends reaches the real route.

The window sends the typed folder as path and as its allowlist entry
(frontend/src/settings/LocalBenchTypes.ts expandBenchScan). The route stays
allowlist-first: no allowlist, a drive root and forbidden segments are refused.
"""

from __future__ import annotations

import os
import pathlib
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from agent_si.backend.app import create_app  # noqa: E402

SCAN = "/api/v1/local/bench/scan"


def _client() -> TestClient:
    return TestClient(create_app({"env": "test", "ui_session_token": "fxbench1"}))


def test_window_scan_lists_the_typed_folder(tmp_path):
    (tmp_path / "local-a.gguf").write_text("weights", encoding="utf-8")
    folder = str(tmp_path)
    answer = _client().get(SCAN, params={"path": folder, "allowlist": folder})
    assert answer.status_code == 200, answer.text
    assert answer.json() == ["local-a.gguf"]


def test_scan_without_allowlist_stays_refused(tmp_path):
    answer = _client().get(SCAN, params={"path": str(tmp_path)})
    assert answer.status_code == 403, answer.text


def test_window_scan_refuses_a_drive_root():
    root = os.path.splitdrive(os.getcwd())[0] + os.sep
    answer = _client().get(SCAN, params={"path": root, "allowlist": root})
    assert answer.status_code == 403, answer.text


def test_window_scan_refuses_a_credentials_folder(tmp_path):
    secret = tmp_path / ".ssh"
    secret.mkdir()
    (secret / "id_rsa").write_text("key", encoding="utf-8")
    folder = str(secret)
    answer = _client().get(SCAN, params={"path": folder, "allowlist": folder})
    assert answer.status_code == 403, answer.text
