"""K10ST1-B data-dir consumer lane (M-P4-134 / LIVE0-04, TPL1-NEW).

testid: k10st1-migrate (lives ONLY in this file).

Row 1431 (M-P4-134): first start migrates settings+credentials, with the
originals kept (copy, never move; repeat starts never overwrite).
Row 1705 (LIVE0-04): the product start path supplies the data dir from
the consumer-layer env read, with no harness settings; a
harness-sourced dir is rejected.
"""

import os
import sys

import pytest

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend.app import (  # noqa: E402
    create_app,
    get_data_dir,
    migrate_legacy_data,
)

TEST_SETTINGS = b'{"theme": "dark", "lane": "k10st1-migrate"}'
TEST_CREDENTIALS = b'{"loopback": "test-only"}'


def _clean_settings(token="k10st1-migrate-token"):
    return {
        "ui_session_token": token,
        "secret_store": "memory",
        "testing": True,
    }


def _isolate_home(monkeypatch, home):
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))


def test_k10st1_migrate_first_start_copies_settings_credentials(
    tmp_path, monkeypatch
):
    """Row M-P4-134: first start migrates settings+credentials."""
    legacy_home = tmp_path / "home"
    legacy_home.mkdir()
    legacy = legacy_home / ".agent_si"
    legacy.mkdir()
    (legacy / "settings.json").write_bytes(TEST_SETTINGS)
    (legacy / "credentials.json").write_bytes(TEST_CREDENTIALS)
    _isolate_home(monkeypatch, legacy_home)
    data_dir = tmp_path / "data"

    report = migrate_legacy_data(str(data_dir), legacy_dir=str(legacy))
    assert report == {
        "settings.json": "copied",
        "credentials.json": "copied",
    }

    monkeypatch.setenv("AGENT_SI_DATA_DIR", str(data_dir))
    app = create_app(_clean_settings())

    assert app.state.data_dir == os.path.abspath(str(data_dir))
    for name, payload in (
        ("settings.json", TEST_SETTINGS),
        ("credentials.json", TEST_CREDENTIALS),
    ):
        assert (data_dir / name).read_bytes() == payload
        assert (legacy / name).read_bytes() == payload

    (data_dir / "settings.json").write_bytes(b'{"theme": "edited"}')
    create_app(_clean_settings())
    assert (data_dir / "settings.json").read_bytes() == b'{"theme": "edited"}'
    assert (legacy / "settings.json").read_bytes() == TEST_SETTINGS


def test_k10st1_migrate_consumer_env_dir_no_harness(tmp_path, monkeypatch):
    """Row LIVE0-04: data dir from the consumer-layer env read."""
    home = tmp_path / "home"
    home.mkdir()
    _isolate_home(monkeypatch, home)
    data_dir = tmp_path / "data"
    monkeypatch.setenv("AGENT_SI_DATA_DIR", str(data_dir))

    app = create_app(_clean_settings())
    expected = os.path.abspath(str(data_dir))
    assert app.state.data_dir == expected
    assert app.state.k02r3_store_dir == expected
    assert app.state.k04_ctx is not None
    assert app.state.k04_ctx.store.data_dir == expected

    other = tmp_path / "other"
    other.mkdir()
    harness = _clean_settings()
    harness["store_dir"] = str(other)
    with pytest.raises(ValueError):
        create_app(harness)

    same = _clean_settings()
    same["store_dir"] = str(data_dir)
    assert create_app(same).state.data_dir == expected

    monkeypatch.delenv("AGENT_SI_DATA_DIR")
    assert get_data_dir(_clean_settings()) is None
