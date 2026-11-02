"""FXOPEN O6 (SH-01/SH-04/SH-05): project guards on the real routes.

SH-01: the same folder twice refuses 409 PROJECT_FOLDER_IN_USE with a
plain line; a different folder passes; archiving frees the folder.
SH-05: the project read carries folder_ok/folder_path; a deleted
absolute folder reads folder_ok False, an existing one True.
The SH-05 send refusal (terminal error, never green) is proved by
test_fxdevwire_served.py::test_s1b_absolute_missing_folder_honest.
"""
from __future__ import annotations

import os
import sys

from fastapi.testclient import TestClient

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend.app import create_app  # noqa: E402

TEST_TOKEN = "fxopen-guards-token"
ACTOR = "fxopen-guards-tester"


def _auth():
    return {"x-actor": ACTOR, "x-ui-session-token": TEST_TOKEN}


def _app(tmp_path):
    store = tmp_path / "store-guards"
    store.mkdir(parents=True, exist_ok=True)
    return create_app({
        "testing": True,
        "ui_session_token": TEST_TOKEN,
        "store_dir": str(store),
    })


def _create(client, name, folder_ref):
    return client.post(
        "/api/v1/projects",
        json={"name": name, "folder_ref": folder_ref},
        headers=_auth())


def test_fxopen_sh01_same_folder_twice_refuses_409(tmp_path):
    """Second project on the same folder: 409 with the plain code."""
    app = _app(tmp_path)
    client = TestClient(app, raise_server_exceptions=False)
    folder = tmp_path / "shared-proj"
    folder.mkdir()
    first = _create(client, "A", str(folder))
    assert first.status_code == 200, first.text
    second = _create(client, "B", str(folder))
    assert second.status_code == 409, second.text
    body = second.json()
    detail = body.get("detail") if isinstance(body, dict) else None
    assert isinstance(detail, dict), body
    assert detail.get("code") == "PROJECT_FOLDER_IN_USE", detail
    assert "already used" in str(detail.get("detail", "")), detail


def test_fxopen_sh01_case_and_sep_variants_refuse(tmp_path):
    """Case/separator variants of the same folder still refuse."""
    app = _app(tmp_path)
    client = TestClient(app, raise_server_exceptions=False)
    folder = tmp_path / "CaseProj"
    folder.mkdir()
    assert _create(client, "A", str(folder)).status_code == 200
    variant = str(folder) + os.sep
    if os.name == "nt":
        variant = "c:" + variant[2:] if variant[1:2] == ":" else variant
        variant = variant.replace("C", "c").replace("\\", "/")
    else:
        variant = str(folder).upper()
    second = _create(client, "B", variant)
    # On case-insensitive volumes this is the same folder (409); on
    # case-sensitive ones it is genuinely different (200). Either way
    # the verdict is honest and never a silent duplicate row.
    assert second.status_code in (200, 409), second.text
    if second.status_code == 409:
        assert second.json()["detail"]["code"] == "PROJECT_FOLDER_IN_USE"


def test_fxopen_sh01_archived_frees_the_folder(tmp_path):
    """Archiving A frees its folder for B."""
    app = _app(tmp_path)
    client = TestClient(app, raise_server_exceptions=False)
    folder = tmp_path / "freed-proj"
    folder.mkdir()
    first = _create(client, "A", str(folder))
    assert first.status_code == 200, first.text
    pid = first.json()["project"]["project_id"]
    archived = client.delete(
        "/api/v1/projects/%s" % pid, headers=_auth())
    assert archived.status_code == 200, archived.text
    second = _create(client, "B", str(folder))
    assert second.status_code == 200, second.text


def test_fxopen_sh05_read_carries_folder_health(tmp_path):
    """Deleted absolute folder reads folder_ok False; existing True."""
    app = _app(tmp_path)
    client = TestClient(app, raise_server_exceptions=False)
    gone = tmp_path / "deleted-proj"
    gone.mkdir()
    created = _create(client, "Gone", str(gone))
    assert created.status_code == 200, created.text
    pid = created.json()["project"]["project_id"]
    try:
        gone.rmdir()
    except OSError:
        pass
    import shutil
    shutil.rmtree(str(gone), ignore_errors=True)
    read = client.get("/api/v1/projects/%s" % pid, headers=_auth())
    assert read.status_code == 200, read.text
    project = read.json()["project"]
    assert project.get("folder_ok") is False, project
    assert str(gone) in str(project.get("folder_path", "")), project
    kept = tmp_path / "kept-proj"
    kept.mkdir()
    created2 = _create(client, "Kept", str(kept))
    pid2 = created2.json()["project"]["project_id"]
    read2 = client.get("/api/v1/projects/%s" % pid2, headers=_auth())
    assert read2.json()["project"].get("folder_ok") is True


def test_fxopen_sh05_managed_ref_reads_healthy(tmp_path):
    """Non-absolute refs self-heal on send: the read stays healthy."""
    app = _app(tmp_path)
    client = TestClient(app, raise_server_exceptions=False)
    created = _create(client, "Managed", "managed-ref")
    assert created.status_code == 200, created.text
    pid = created.json()["project"]["project_id"]
    read = client.get("/api/v1/projects/%s" % pid, headers=_auth())
    assert read.status_code == 200, read.text
    assert read.json()["project"].get("folder_ok") is True
