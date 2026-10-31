"""K04R3B lane proof: KB refresh-as-proposal plus key save-delete edges.

F4: builds a proposal from fetched text, apply fails without
confirmation, apply succeeds with confirmation, and key delete
removes the credential-store entry (served keys path on the memory
store with loopback TEST data only; the leftover finder no longer
lists the entry, names only, never values).
"""
import copy
import json
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import fastapi.testclient  # noqa: E402

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.model_kb import kb, updater  # noqa: E402

ALLOWLISTED = updater.KB_SOURCE_ALLOWLIST[0] + "/models"
DAY = "2026-10-29"
BAIT = "FAKE-K04R3B-BAIT-4417-qqqq-not-a-real-key"

APP_TOKEN = "k04r3b-app-token"
HEADERS = {"x-actor": "ui-probe", "x-ui-session-token": APP_TOKEN}


def _row(provider_id="openai", model_id="gpt-4o"):
    fields = {}
    for name in kb.ROW_FIELD_NAMES:
        if name == "source_links":
            fields[name] = kb.sourced([ALLOWLISTED], ALLOWLISTED, DAY)
        else:
            fields[name] = kb.sourced(f"sample-{name}", ALLOWLISTED,
                                      DAY)
    return kb.make_model_row(provider_id, model_id, fields)


def _catalog():
    return kb.make_catalog([_row()], kb_version=3, updated_at=DAY)


def _fetched_text():
    return json.dumps({
        "models": [{"provider_id": "openai", "model_id": "gpt-4o",
                    "fields": {"purpose": "flagship chat"}}]})


def _proposal(catalog):
    fetched = updater.fetch_source(
        ALLOWLISTED, lambda url: _fetched_text())
    return updater.propose_update(catalog, ALLOWLISTED, fetched, DAY)


def test_proposal_built_from_fetched_text():
    catalog = _catalog()
    before = copy.deepcopy(catalog)
    proposal = _proposal(catalog)
    assert proposal["changes"] != []
    assert proposal["retrieved_at"] == DAY
    assert updater.validate_proposal(catalog, proposal) == []
    for change in proposal["changes"]:
        assert change["retrieved_at"] == DAY
        assert change["source"] == ALLOWLISTED
    assert catalog == before


def test_apply_fails_without_confirmation():
    catalog = _catalog()
    proposal = _proposal(catalog)
    before = copy.deepcopy(catalog)
    for confirm in (False, None, "yes"):
        with pytest.raises(updater.KB_PROPOSAL_NOT_APPROVED):
            updater.apply_proposal(catalog, proposal,
                                   user_confirmed=confirm)
    assert catalog == before


def test_apply_succeeds_with_confirmation():
    catalog = _catalog()
    proposal = _proposal(catalog)
    result = updater.apply_proposal(catalog, proposal,
                                    user_confirmed=True)
    assert result["applied"] is True
    updated = result["catalog"]
    assert updated["version"]["kb_version"] == 4
    assert updated["version"]["updated_at"] == DAY
    row = updated["models"][0]
    assert row["fields"]["purpose"]["value"] == "flagship chat"
    assert row["fields"]["purpose"]["source"] == ALLOWLISTED
    assert row["fields"]["purpose"]["retrieved_at"] == DAY
    assert kb.validate_catalog(updated) == []


def test_key_delete_removes_store_entry(tmp_path):
    settings = {"store_dir": str(tmp_path / "appdata"),
                "ui_session_token": APP_TOKEN,
                "secret_store": "memory"}
    app = create_app(settings)
    client = fastapi.testclient.TestClient(app)
    store = app.state.k04_ctx.credential_store
    assert store is not None
    saved = client.post("/api/v1/providers/keys",
                        json={"preset_id": "openai",
                              "key_value": BAIT},
                        headers=HEADERS)
    assert saved.status_code == 201, saved.text
    assert set(saved.json()) == {"key_ref"}, saved.text
    assert BAIT not in saved.text
    assert "openai" in updater.find_leftover_keys(store)
    assert BAIT not in str(updater.find_leftover_keys(store))
    key_ref = saved.json()["key_ref"]
    conn = client.post("/api/v1/providers/connect",
                       json={"preset_id": "openai", "model": "m-k04r3b",
                             "key_ref": key_ref},
                       headers=HEADERS)
    assert conn.status_code == 200, conn.text
    disc = client.post("/api/v1/providers/openai/disconnect", json={},
                       headers=HEADERS)
    assert disc.status_code == 200, disc.text
    assert disc.json() == {"removed": True, "provider_id": "openai"}
    assert store.has("openai") is False
    assert "openai" not in updater.find_leftover_keys(store)
    assert BAIT not in str(app.state.k04_ctx.audit_sink.records)
