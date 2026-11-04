"""FB2B4R served proof: staged B1 KB rows drive auditor eligibility (F04).

Drives REAL product code under src/agent_si/ with the real seam app
(create_app + TestClient, raise_server_exceptions=False). No network:
the provider transport (urllib urlopen) is faked in-process exactly like
the sibling FXKB lanes; keys are bait (never real). Fixtures live only
in this file.

Row map:
  F04 openai-only set, no B1 rows staged -> NO_ELIGIBLE_AUDITOR
    (registry is_eligible False, select_auditor raises, served
    POST /api/v1/assurance/finalize answers phase BLOCKED with code
    NO_ELIGIBLE_AUDITOR) even though the openai candidate IS
    registered -- the LIVE-SIGNAL "openai candidate has no capability
    evidence".
  F04 gone with B1 rows: after served POST /api/v1/kb/update stages
    the openai row with sourced fields, the SAME no-refs candidate
    (exactly what the served path registers) is eligible off the
    staged KB rows: is_eligible True, select_auditor picks
    openai/gpt-4o at L2, and served finalize returns an audit with
    verdict != NO_ELIGIBLE_AUDITOR.
  Negatives: empty-model pairs and UNKNOWN-price rows never yield
    evidence (prices are never invented) and stay ineligible.

RED without the registry wiring: the GREEN-leg test below fails
(is_eligible stays False, select_auditor raises, finalize stays
BLOCKED) because nothing consults the staged KB rows.
"""

import copy
import json
import os
import sys
import urllib.request as _urlreq

_HERE = os.path.dirname(os.path.abspath(__file__))
_WS = os.path.dirname(_HERE)
_SRC = os.path.join(_WS, "src")
for _p in (_WS, _SRC):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import fastapi.testclient as _tc  # noqa: E402

from agent_si.assurance import audit_registry as _areg  # noqa: E402
from agent_si.backend.app import create_app  # noqa: E402
from agent_si.backend.orchestration import steplimits as _steplimits  # noqa: E402
from agent_si.kb import retriever as _kbsev  # noqa: E402
from agent_si.model_kb import kb as _kb  # noqa: E402
from agent_si.model_kb import loader as _loader  # noqa: E402

OPENAI_PROVIDER = "openai"
OPENAI_MODEL = "gpt-4o"

#: Exact shipped-preset contributor model id (never reworded); the
#: implementer side of the served finalize proof.
CONTRIBUTOR_MODEL = _areg.MODEL_ID

CONTRACT = "contract-hash-fb2b4r"

APP_TOKEN = "fb2b4r-app-token"
BAIT = "FAKE-FB2B4R-BAIT-0000-zzzz-not-a-real-key"
HEADERS = {"x-actor": "ui-probe", "x-ui-session-token": APP_TOKEN}


class _FakeResp:
    def __init__(self, payload):
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fake_chat(request, timeout=None):
    return _FakeResp({"choices": [{"message": {"content": "fb2b4r hi"},
                                   "finish_reason": "stop"}],
                      "usage": {"input_tokens": 4, "output_tokens": 6}})


def _settings(store_dir):
    return {"store_dir": store_dir,
            "ui_session_token": APP_TOKEN,
            "secret_store": "memory"}


class _ProofRegistry(_areg.AuditorRegistry):
    """Concrete binding of the real sourcing entries; adds nothing."""


def _no_ref_candidate():
    """The served path registers candidates with no refs (F04 signal)."""
    return _areg.AuditorCandidate(
        provider_id=OPENAI_PROVIDER, provider_instance=None,
        model=OPENAI_MODEL, capability_evidence_refs=(),
        registered_at="")


def _unknown_catalog():
    """Hermetic UNKNOWN-field catalog: openai row present, unevidenced."""
    row = _kb.make_model_row(OPENAI_PROVIDER, OPENAI_MODEL)
    return _kb.make_catalog([row], kb_version=1, updated_at="2026-10-11")


def _create_project_and_task(client, tag=""):
    resp = client.post("/api/v1/projects",
                       json={"name": "fb2b4r-test",
                             "folder_ref": "dock-fb2b4r%s" % tag},
                       headers=HEADERS)
    assert resp.status_code == 200, resp.text
    project_id = resp.json()["project"]["project_id"]
    resp = client.post(
        "/api/v1/projects/%s/tasks" % project_id,
        json={"title": "assure me", "scope": ["scope-fb2b4r"]},
        headers=HEADERS)
    assert resp.status_code == 200, resp.text
    return project_id, resp.json()["task"]["task_id"]


def _finalize_body(project_id, task_id, run_id, proj_dir):
    evidence = "ev-fb2b4r-1"
    return {
        "project_id": project_id,
        "task_id": task_id,
        "run_id": run_id,
        "contract_hash": CONTRACT,
        "project_dir": str(proj_dir),
        "work_refs": ["work-fb2b4r-1"],
        "artifact_refs": ["art-fb2b4r-1"],
        "evidence_refs": [evidence],
        "producer_session_refs": ["sess-prod-fb2b4r-1"],
        "tool_rows": [
            {"tool": "writer", "evidence_ref": evidence, "ok": True},
        ],
        "criteria": [{
            "ac_id": "ac-fb2b4r-1",
            "evidence_required": True,
            "evidence_refs": [evidence],
            "severity": "MEDIUM",
            "verification_method": "grounded-evidence",
        }],
        "implementer_model_ids": [CONTRIBUTOR_MODEL],
        # Openai-only set with NO capability evidence refs: the exact
        # F04 LIVE-SIGNAL payload shape the served path registers.
        "auditor_candidates": [{
            "provider_id": OPENAI_PROVIDER,
            "model": OPENAI_MODEL,
        }],
        "task_class": "served-turn",
        "minimum_level": "L2",
    }


def _save_and_connect_openai(client):
    resp = client.post("/api/v1/providers/keys",
                       json={"preset_id": OPENAI_PROVIDER,
                             "key_value": BAIT},
                       headers=HEADERS)
    assert resp.status_code == 201, resp.text
    assert BAIT not in resp.text
    key_ref = resp.json()["key_ref"]
    conn = client.post("/api/v1/providers/connect",
                       json={"preset_id": OPENAI_PROVIDER,
                             "model": OPENAI_MODEL,
                             "key_ref": key_ref},
                       headers=HEADERS)
    assert conn.status_code == 200, conn.text
    assert BAIT not in conn.text
    return key_ref


def test_openai_only_no_refs_blocked_without_b1_rows(tmp_path):
    """RED doc: UNKNOWN-field row keeps the openai-only set ineligible."""
    seed = _kb.bound_catalog()
    prev_persist = getattr(_kb, "_PERSIST_DIR", None)
    try:
        _kb.bind_catalog(_unknown_catalog())
        assert _kbsev.auditor_capability_evidence(
            OPENAI_PROVIDER, OPENAI_MODEL) == ()
        red = _ProofRegistry()
        red.register_candidate(_no_ref_candidate())
        assert red.is_eligible(OPENAI_PROVIDER, OPENAI_MODEL) is False
        try:
            red.select_auditor("served-turn", (CONTRIBUTOR_MODEL,), "L2")
        except _areg.NoEligibleAuditorError as exc:
            assert exc.code == _areg.NO_ELIGIBLE_AUDITOR
        else:
            raise AssertionError("selected without B1 rows")
        _steplimits._reset_state()
        store = tmp_path / "store-red"
        store.mkdir()
        proj = tmp_path / "proj-red"
        proj.mkdir()
        app = create_app(_settings(str(store)))
        client = _tc.TestClient(app, raise_server_exceptions=False)
        project_id, task_id = _create_project_and_task(client)
        resp = client.post(
            "/api/v1/assurance/finalize",
            json=_finalize_body(
                project_id, task_id, "run-fb2b4r-red", proj),
            headers=HEADERS)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["phase"] == "BLOCKED", data
        assert data["code"] == _areg.NO_ELIGIBLE_AUDITOR, data
        assert data["audit_id"] is None, data
    finally:
        _steplimits._reset_state()
        _kb.bind_catalog(seed)
        try:
            _kb.set_persist_dir(prev_persist)
        except Exception:
            pass


def test_openai_only_no_refs_eligible_with_b1_rows_served(
        tmp_path, monkeypatch):
    """GREEN leg: staged B1 rows make the no-refs openai set eligible.

    RED without the registry wiring (F04): is_eligible stays False,
    select_auditor raises NO_ELIGIBLE_AUDITOR, served finalize stays
    BLOCKED. GREEN with it: eligible off staged KB rows end to end.
    """
    monkeypatch.setattr(_urlreq, "urlopen", _fake_chat)
    seed = _kb.bound_catalog()
    prev_persist = getattr(_kb, "_PERSIST_DIR", None)
    try:
        _steplimits._reset_state()
        store = tmp_path / "store-green"
        store.mkdir()
        proj = tmp_path / "proj-green"
        proj.mkdir()
        app = create_app(_settings(str(store)))
        client = _tc.TestClient(app, raise_server_exceptions=False)
        _create_project_and_task(client, "-green1")
        _save_and_connect_openai(client)
        resp = client.post("/api/v1/kb/update",
                           json={"approved_by_user": True},
                           headers=HEADERS)
        assert resp.status_code == 200, resp.text
        assert resp.json()["staged"] is True, resp.text
        for staged in resp.json()["proposals"]:
            done = client.post(
                "/api/v1/kb/proposals/apply",
                json={"proposal_id": staged["proposal_id"],
                      "approved_by_user": True},
                headers=HEADERS)
            assert done.status_code == 200, done.text
        assert done.json()["applied"] is True, done.text
        assert OPENAI_PROVIDER in [
            p.get("provider_id")
            for p in resp.json()["proposals"]], resp.text
        refs = _kbsev.auditor_capability_evidence(
            OPENAI_PROVIDER, OPENAI_MODEL)
        assert len(refs) >= 1, refs
        green = _ProofRegistry()
        green.register_candidate(_no_ref_candidate())
        assert green.is_eligible(OPENAI_PROVIDER, OPENAI_MODEL) is True
        selection = green.select_auditor(
            "served-turn", (CONTRIBUTOR_MODEL,), "L2")
        assert selection.auditor.provider_id == OPENAI_PROVIDER
        assert selection.auditor.model == OPENAI_MODEL
        assert selection.independence_level == "L2"
        project_id, task_id = _create_project_and_task(client, "-green2")
        resp = client.post(
            "/api/v1/assurance/finalize",
            json=_finalize_body(
                project_id, task_id, "run-fb2b4r-green", proj),
            headers=HEADERS)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data.get("code") != _areg.NO_ELIGIBLE_AUDITOR, data
        assert data["audit_id"], data
        assert data["audit_id"].startswith("audit-"), data
        assert data["auditor"]["provider_id"] == OPENAI_PROVIDER, data
        assert data["auditor"]["model"] == OPENAI_MODEL, data
        assert data["verdict"], data
        assert data["close_row_id"], data
    finally:
        _steplimits._reset_state()
        _kb.bind_catalog(seed)
        try:
            _kb.set_persist_dir(prev_persist)
        except Exception:
            pass


def test_empty_model_and_unknown_price_stay_ineligible(tmp_path):
    """Negatives: empty pairs and UNKNOWN prices never yield evidence."""
    seed = _kb.bound_catalog()
    prev_persist = getattr(_kb, "_PERSIST_DIR", None)
    try:
        assert _kbsev.auditor_capability_evidence(
            OPENAI_PROVIDER, "") == ()
        assert _kbsev.auditor_capability_evidence(
            "", OPENAI_MODEL) == ()
        empty = _ProofRegistry()
        empty.register_candidate(_areg.AuditorCandidate(
            provider_id=OPENAI_PROVIDER, provider_instance=None,
            model="", capability_evidence_refs=(), registered_at=""))
        assert empty.is_eligible(OPENAI_PROVIDER, "") is False
        no_price = copy.deepcopy(_unknown_catalog())
        row = _loader.find_row(no_price, OPENAI_PROVIDER, OPENAI_MODEL)
        assert row is not None
        for price_field in ("input_token_price", "output_token_price"):
            row["fields"][price_field] = {"value": "UNKNOWN",
                                          "source": "UNKNOWN",
                                          "retrieved_at": "UNKNOWN"}
        _kb.bind_catalog(no_price)
        assert _kbsev.auditor_capability_evidence(
            OPENAI_PROVIDER, OPENAI_MODEL) == ()
        probe = _ProofRegistry()
        probe.register_candidate(_no_ref_candidate())
        assert probe.is_eligible(OPENAI_PROVIDER, OPENAI_MODEL) is False
        try:
            probe.select_auditor(
                "served-turn", (CONTRIBUTOR_MODEL,), "L2")
        except _areg.NoEligibleAuditorError as exc:
            assert exc.code == _areg.NO_ELIGIBLE_AUDITOR
        else:
            raise AssertionError("UNKNOWN-price row selected")
    finally:
        _kb.bind_catalog(seed)
        try:
            _kb.set_persist_dir(prev_persist)
        except Exception:
            pass
