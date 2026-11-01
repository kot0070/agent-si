"""K10FIXT2 served map: per-row proof on REAL surfaces only (TPL1-NEW).

Rows (kit BUILD_PLAN, this order):
172 fixture capability rows labelled TEST FIXTURES with provenance, never
    measured evidence -- pack fixture files plus demo_local output plus the
    telemetry store seam (fixture ids absent from MEASURED rows).
173 fixture pack ships under checkout, not measured evidence -- the manifest
    plus provenance files under tools/drive/demo with sha256 seals.
217 TEST FIXTURE rows prove wiring only, never measured evidence --
    GET /k10/accept plus GET /api/v1/analytics/telemetry via create_app.
225 local demo needs a permission-gated local runtime plus capability
    evidence for the fixture class -- demo_local.py run as a script.
227 split demo includes real cloud verification over the local draft output
    with draft-hash binding -- demo_split.py run as a script.
229 unavailable local legs use labelled localhost doubles as TEST FIXTURES --
    GET /api/v1/local/status plus /models via create_app plus demo outputs.
Every row hits a REAL surface: an existing route through create_app in
src/agent_si/backend/app.py, a demo script run as a script, or pack files
shipped under checkout. No new product module. No test-mounted routes.
Loopback TEST data only; no network, no installs.
"""

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import fastapi.testclient  # noqa: E402

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.telemetry import run_store as store  # noqa: E402
from agent_si.telemetry.metrics import MetricState  # noqa: E402

DEMO_DIR = ROOT / "tools" / "drive" / "demo"
FIXTURES_LOCAL = DEMO_DIR / "fixtures_local.json"
FIXTURES_REMOTE = DEMO_DIR / "fixtures_remote.json"
MANIFEST_PATH = DEMO_DIR / "fixture_pack_manifest.json"
PROVENANCE_PATH = DEMO_DIR / "fixture_pack_provenance.json"

ROW_172 = "B0B-UNCOVERED_MVP_ACCEPT-172"
ROW_173 = "B0B-UNCOVERED_MVP_ACCEPT-173"
ROW_217 = "B0B-UNCOVERED_MVP_ACCEPT-217"
ROW_225 = "B0B-UNCOVERED_MVP_ACCEPT-225"
ROW_227 = "B0B-UNCOVERED_MVP_ACCEPT-227"
ROW_229 = "B0B-UNCOVERED_MVP_ACCEPT-229"

HASH_FIELDS = ("pack_manifest_sha256", "fixture_sha256")
SCRIPT_TIMEOUT_S = 120


def _canonical_bytes(obj) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True)
            + "\n").encode("utf-8")


def _blank_hashes(obj):
    if isinstance(obj, dict):
        return {k: ("" if k in HASH_FIELDS else _blank_hashes(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [_blank_hashes(v) for v in obj]
    return obj


def _canonical_fixture_sha(data) -> str:
    return hashlib.sha256(_canonical_bytes(_blank_hashes(data))).hexdigest()


def _raw_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _rows_by_id(data):
    return {row["row"]: row for row in data["rows"]}


def _assert_labelled_pack_row(row, source_suffix):
    assert row["label"] == "TEST FIXTURES", row
    provenance = row["provenance"]
    assert provenance["source"].replace("\\", "/").endswith(
        source_suffix), provenance
    assert len(provenance["pack_manifest_sha256"]) == 64, provenance
    assert len(provenance["fixture_sha256"]) == 64, provenance


def _client(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("AGENT_SI_SECRET_STORE", "memory")
    store_dir = tmp_path / "store"
    store_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("AGENT_SI_DATA_DIR", str(store_dir))
    app = create_app(
        {
            "ui_session_token": "k10fixt2-test-token-00000000000001",
            "secret_store": "memory",
            "testing": True,
        }
    )
    return fastapi.testclient.TestClient(app), store_dir
def _seed_two_usages(store_dir):
    store.record_provider_usage(
        project_id="k10fixt2-proj",
        task_id="task-k10fixt2-1",
        run_id="run-k10fixt2-1",
        provider="k10fixt2-provider-a",
        model="k10fixt2-model-a",
        usage={"input_tokens": 100, "output_tokens": 50},
        store_dir=str(store_dir),
    )
    store.record_provider_usage(
        project_id="k10fixt2-proj",
        task_id="task-k10fixt2-1",
        run_id="run-k10fixt2-1",
        provider="k10fixt2-provider-b",
        model="k10fixt2-model-b",
        usage={"input_tokens": 200, "output_tokens": 25},
        store_dir=str(store_dir),
    )
    store.record_run_terminated(
        project_id="k10fixt2-proj",
        task_id="task-k10fixt2-1",
        run_id="run-k10fixt2-1",
        reason="done",
        store_dir=str(store_dir),
    )


def _measured_ids(store_dir):
    with open(store_dir / "telemetry_store.json", encoding="utf-8") as handle:
        saved = json.load(handle)
    return {
        row.get("metric_id")
        for row in saved["metric_records"]
        if isinstance(row, dict)
        and row.get("state") == MetricState.MEASURED.value
    }


def _run_script(script_name, tmp_path, *extra_args):
    out_dir = tmp_path / ("artifacts-" + script_name.replace(".py", ""))
    out_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, str(DEMO_DIR / script_name),
         "--out", str(out_dir), *extra_args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=SCRIPT_TIMEOUT_S,
    )
    return proc, out_dir


def _artifact_of(proc, out_dir):
    assert proc.returncode == 0, (proc.returncode, proc.stdout, proc.stderr)
    lines = proc.stdout.splitlines()
    assert len(lines) == 2, proc.stdout
    assert lines[0].startswith("run_id: "), proc.stdout
    assert lines[1].startswith("artifact: "), proc.stdout
    raw = lines[1].split("artifact:", 1)[1].strip()
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    assert path.is_file(), raw
    return _load_json(path), path


def test_k10fixt2_172_fixture_rows_labelled(tmp_path, monkeypatch):
    """Row 172 served through the pack fixture files plus demo_local output."""
    data = _load_json(FIXTURES_LOCAL)
    row = _rows_by_id(data)[ROW_172]
    _assert_labelled_pack_row(row, "tools/drive/demo/demo_local.py")
    assert "labelled TEST FIXTURES" in row["claim"], row
    assert _canonical_fixture_sha(data) == row["provenance"][
        "fixture_sha256"], row
    assert _raw_sha(MANIFEST_PATH) == row["provenance"][
        "pack_manifest_sha256"], row
    assert data["label"] == "TEST FIXTURES", data
    proc, out_dir = _run_script("demo_local.py", tmp_path)
    artifact, _ = _artifact_of(proc, out_dir)
    assert artifact["fixture_class"] == data["fixture_class"], artifact
    assert artifact["verification"]["label"] == "TEST FIXTURES", artifact
    assert (artifact["verification"]["capabilities"]
            == list(data["capabilities"])), artifact
    provenance = artifact["verification"]["provenance"]
    _assert_labelled_pack_row(
        {"label": "TEST FIXTURES", "provenance": provenance}, "")
    client, store_dir = _client(tmp_path, monkeypatch)
    _seed_two_usages(store_dir)
    resp = client.get("/api/v1/analytics/telemetry")
    assert resp.status_code == 200, resp.text
    for row_id in _rows_by_id(data):
        assert row_id not in _measured_ids(store_dir), row_id


def test_k10fixt2_173_pack_ships_under_checkout(tmp_path):
    """Row 173 served through the manifest plus provenance pack files."""
    assert MANIFEST_PATH.is_file(), str(MANIFEST_PATH)
    assert PROVENANCE_PATH.is_file(), str(PROVENANCE_PATH)
    manifest = _load_json(MANIFEST_PATH)
    assert manifest["label"] == "TEST FIXTURES", manifest
    listed = {entry["path"]: entry["sha256"]
              for entry in manifest["files"]}
    assert set(listed) == {
        "tools/drive/demo/fixtures_local.json",
        "tools/drive/demo/fixtures_remote.json",
    }, manifest
    assert listed["tools/drive/demo/fixtures_local.json"] == (
        _canonical_fixture_sha(_load_json(FIXTURES_LOCAL))), manifest
    assert listed["tools/drive/demo/fixtures_remote.json"] == (
        _canonical_fixture_sha(_load_json(FIXTURES_REMOTE))), manifest
    provenance = _load_json(PROVENANCE_PATH)
    assert provenance["label"] == "TEST FIXTURES", provenance
    origins = {entry["script"]: entry["sha256"]
               for entry in provenance["origins"]}
    assert set(origins) == {
        "tools/drive/demo/demo_local.py",
        "tools/drive/demo/demo_split.py",
        "tools/drive/demo/demo_cloud.py",
    }, provenance
    for script, digest in origins.items():
        assert digest == _raw_sha(ROOT / script), script
    assert provenance["manifest_sha256"] == _raw_sha(MANIFEST_PATH)
def test_k10fixt2_217_wiring_only(tmp_path, monkeypatch):
    """Row 217 served through GET /k10/accept plus the telemetry route."""
    data = _load_json(FIXTURES_REMOTE)
    row = _rows_by_id(data)[ROW_217]
    _assert_labelled_pack_row(row, "tools/drive/demo/demo_split.py")
    assert "wiring only" in row["claim"], row
    assert _canonical_fixture_sha(data) == row["provenance"][
        "fixture_sha256"], row
    client, store_dir = _client(tmp_path, monkeypatch)
    resp = client.get("/k10/accept")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["testid"] == "k10st4-accept", body
    assert "MEASURED" not in json.dumps(body), body
    for row_id in list(_rows_by_id(_load_json(FIXTURES_LOCAL))) + list(
            _rows_by_id(data)):
        assert row_id not in json.dumps(body), row_id
    _seed_two_usages(store_dir)
    tele = client.get("/api/v1/analytics/telemetry")
    assert tele.status_code == 200, tele.text
    measured = _measured_ids(store_dir)
    for row_id in list(_rows_by_id(_load_json(FIXTURES_LOCAL))) + list(
            _rows_by_id(data)):
        assert row_id not in measured, row_id


def test_k10fixt2_225_permission_gated_local(tmp_path):
    """Row 225 served through demo_local.py run as a script."""
    data = _load_json(FIXTURES_LOCAL)
    row = _rows_by_id(data)[ROW_225]
    _assert_labelled_pack_row(row, "tools/drive/demo/demo_local.py")
    assert "permission-gated" in row["claim"], row
    denied = copy.deepcopy(data)
    denied.pop("permission", None)
    denied_path = tmp_path / "fixtures_denied.json"
    denied_path.write_text(
        _canonical_bytes(denied).decode("utf-8"), encoding="utf-8")
    denied_out = tmp_path / "artifacts-denied"
    denied_out.mkdir(exist_ok=True)
    proc = subprocess.run(
        [sys.executable, str(DEMO_DIR / "demo_local.py"),
         "--out", str(denied_out), "--fixtures", str(denied_path)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=SCRIPT_TIMEOUT_S,
    )
    assert proc.returncode != 0, (proc.returncode, proc.stdout)
    assert "error:" in proc.stdout, proc.stdout
    assert list(denied_out.glob("DEMO-1-*.json")) == []
    proc, _ = _run_script("demo_local.py", tmp_path)
    artifact, _ = _artifact_of(proc, tmp_path / "artifacts-demo_local")
    verification = artifact["verification"]
    assert verification["label"] == "TEST FIXTURES", artifact
    assert (verification["capabilities"]
            == list(data["capabilities"])), artifact
    assert "never MEASURED" in verification["capability_evidence_tier"], (
        artifact)
    _assert_labelled_pack_row(
        {"label": "TEST FIXTURES",
         "provenance": verification["provenance"]}, "")
def test_k10fixt2_227_split_real_cloud_verification(tmp_path):
    """Row 227 served through demo_split.py run as a script."""
    data = _load_json(FIXTURES_REMOTE)
    row = _rows_by_id(data)[ROW_227]
    _assert_labelled_pack_row(row, "tools/drive/demo/demo_split.py")
    assert "draft-hash binding" in row["claim"], row
    draft_proc, _ = _run_script("demo_local.py", tmp_path)
    draft_artifact, draft_path = _artifact_of(
        draft_proc, tmp_path / "artifacts-demo_local")
    draft_bytes = draft_path.read_bytes()
    draft_hash = hashlib.sha256(draft_bytes).hexdigest()
    proc, out_dir = _run_script(
        "demo_split.py", tmp_path, "--local-draft", str(draft_path))
    artifact, artifact_path = _artifact_of(proc, out_dir)
    verification = artifact["verification"]
    assert verification["result"] == "PASS", artifact
    assert verification["draft_hash"] == draft_hash, artifact
    assert verification["recomputed_match"] is True, artifact
    assert verification["draft_run_id"] == draft_artifact["run_id"], artifact
    assert verification["label"] == "TEST FIXTURES", artifact
    kept = artifact_path.parent / verification["draft_ref"]
    assert kept.is_file(), verification
    assert hashlib.sha256(kept.read_bytes()).hexdigest() == draft_hash
    audit = artifact["audit"]
    assert audit["binding"] is True, artifact
    assert audit["draft_hash"] == draft_hash, artifact
    attempts = artifact["attempts"]
    assert attempts[0]["route"] == "LOCAL", artifact
    assert attempts[1]["route"] == "CLOUD", artifact
    assert attempts[1]["evidence_ref"].endswith(draft_hash), artifact
    auto_proc, auto_out = _run_script("demo_split.py", tmp_path)
    auto_artifact, auto_path = _artifact_of(auto_proc, auto_out)
    auto_kept = auto_path.parent / auto_artifact["verification"]["draft_ref"]
    assert auto_kept.is_file(), auto_artifact
    assert hashlib.sha256(auto_kept.read_bytes()).hexdigest() == (
        auto_artifact["verification"]["draft_hash"]), auto_artifact


def test_k10fixt2_229_localhost_doubles_labelled(tmp_path, monkeypatch):
    """Row 229 served through the local routes plus labelled demo outputs."""
    data = _load_json(FIXTURES_LOCAL)
    row = _rows_by_id(data)[ROW_229]
    _assert_labelled_pack_row(row, "tools/drive/demo/demo_local.py")
    assert "localhost doubles" in row["claim"], row
    client, _ = _client(tmp_path, monkeypatch)
    status = client.get("/api/v1/local/status")
    assert status.status_code == 200, status.text
    assert status.json()["status"] == "NOT_CONFIGURED", status.text
    models = client.get("/api/v1/local/models")
    assert models.status_code == 200, models.text
    assert models.json() == [], models.text
    proc, _ = _run_script("demo_local.py", tmp_path)
    artifact, _ = _artifact_of(proc, tmp_path / "artifacts-demo_local")
    assert artifact["endpoint"].startswith("http://localhost"), artifact
    assert artifact["verification"]["label"] == "TEST FIXTURES", artifact
    cloud_proc, _ = _run_script("demo_cloud.py", tmp_path)
    cloud_proc, _ = _run_script("demo_cloud.py", tmp_path)
    cloud_artifact, _ = _artifact_of(
        cloud_proc, tmp_path / "artifacts-demo_cloud")
    assert cloud_artifact["verification"]["label"] == "TEST FIXTURES", (
        cloud_artifact)
    assert cloud_artifact["verification"]["provenance"] == (
        _load_json(FIXTURES_REMOTE)["provenance"]), cloud_artifact
