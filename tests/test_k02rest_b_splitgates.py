"""K02REST-B split/gates seam: rows 93/94/100/118/96/M-P1-10 served.

testid k02rest-b-splitgates; one behaviour test per row via create_app +
HTTP client. Split into N disjoint parts with per-part gates plus fresh
audits, bounded per-Manager context, open-package/gate cross-check at gate
evaluation, frozen manifest hash in part validation, and Manager fan-out
bounded by scheduler caps with the excess queued.
"""

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

TEST_TOKEN = "k02rest-b-splitgates-token"


def make_client():
    app = create_app({"testing": True, "ui_session_token": TEST_TOKEN})
    headers = {"x-actor": "manager-b", "x-ui-session-token": TEST_TOKEN}
    return TestClient(app), headers


def refs(n, tag):
    return ["artifact://k02rest-b-%s/ref-%02d" % (tag, i) for i in range(n)]


def split_parts(client, headers, package_id, total, max_parts):
    resp = client.post(
        "/v1/split-gates/parts",
        json={
            "package_id": package_id,
            "goal": "serve split gates row for %s" % package_id,
            "context_refs": refs(total, package_id),
            "max_parts": max_parts,
            "opt_in": True,
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_k02rest_b_opt_in_split_disjoint():
    """kit/BUILD_PLAN.md:1295 | 93 | K02 | opt-in split into N disjoint parts, N parallel Managers | OPEN | ROWS2: OPEN - no served wiring plus calling test triple proven in int."""
    client, headers = make_client()
    package_id = "k02rest-b93-pkg"
    body = split_parts(client, headers, package_id, 5, 2)
    assert body["package_id"] == package_id
    assert body["count"] == 2
    parts = body["parts"]
    assert len(parts) == 2
    gate_refs = [part["gate_verdict_ref"] for part in parts]
    assert len(set(gate_refs)) == 2
    assert {part["contract_hash"] for part in parts} == {
        parts[0]["contract_hash"]
    }
    refused = client.post(
        "/v1/split-gates/parts",
        json={
            "package_id": package_id,
            "goal": "opt-in refused without flag",
            "context_refs": refs(2, "noopt"),
            "max_parts": 2,
            "opt_in": False,
        },
        headers=headers,
    )
    assert refused.status_code == 400
    raw = client.post(
        "/v1/split-gates/parts",
        json={
            "package_id": package_id,
            "goal": "raw secrets are never shared refs",
            "context_refs": ["plaintext-secret-not-a-ref"],
            "max_parts": 1,
            "opt_in": True,
        },
        headers=headers,
    )
    assert raw.status_code == 400
    no_actor = client.post(
        "/v1/split-gates/parts",
        json={
            "package_id": package_id,
            "goal": "guard needs an actor",
            "context_refs": refs(1, "guard"),
            "max_parts": 1,
            "opt_in": True,
        },
    )
    assert no_actor.status_code == 401
    bad_token = client.post(
        "/v1/split-gates/parts",
        json={
            "package_id": package_id,
            "goal": "guard needs a live token",
            "context_refs": refs(1, "guard"),
            "max_parts": 1,
            "opt_in": True,
        },
        headers={"x-actor": "manager-b", "x-ui-session-token": "wrong-token"},
    )
    assert bad_token.status_code == 403


def test_k02rest_b_part_gate_fresh_audit():
    """kit/BUILD_PLAN.md:1296 | 94 | K02 | each part has its own gate plus fresh audit | OPEN | ROWS2: OPEN - no served wiring plus calling test triple proven in int."""
    client, headers = make_client()
    part_a = "k02rest-b94-part-a"
    gate = client.post(
        "/v1/split-gates/part-gate",
        json={"part_id": part_a, "verdict": "PASS"},
        headers=headers,
    )
    assert gate.status_code == 200, gate.text
    assert gate.json()["gate_id"] == part_a + ":gate-001"
    audit = client.post(
        "/v1/split-gates/part-audit",
        json={
            "part_id": part_a,
            "result": "PASS",
            "auditor_session_ref": "sess-k02rest-b94-aud",
            "producer_session_refs": ["sess-k02rest-b94-prod"],
            "context_integrity": True,
        },
        headers=headers,
    )
    assert audit.status_code == 200, audit.text
    assert audit.json()["audit_id"] == part_a + ":audit-001"
    part_b = "k02rest-b94-part-b"
    gate_b = client.post(
        "/v1/split-gates/part-gate",
        json={"part_id": part_b, "verdict": "PASS"},
        headers=headers,
    )
    assert gate_b.json()["gate_id"] != gate.json()["gate_id"]
    self_audit = client.post(
        "/v1/split-gates/part-audit",
        json={
            "part_id": part_b,
            "result": "PASS",
            "auditor_session_ref": "sess-k02rest-b94-same",
            "producer_session_refs": ["sess-k02rest-b94-same"],
            "context_integrity": True,
        },
        headers=headers,
    )
    assert self_audit.status_code == 409
    no_integrity = client.post(
        "/v1/split-gates/part-audit",
        json={
            "part_id": part_b,
            "result": "PASS",
            "auditor_session_ref": "sess-k02rest-b94-aud2",
            "producer_session_refs": ["sess-k02rest-b94-prod2"],
            "context_integrity": False,
        },
        headers=headers,
    )
    assert no_integrity.status_code == 409


def test_k02rest_b_bounded_context_per_manager():
    """kit/BUILD_PLAN.md:1298 | 100 | K02 | product split with bounded context per Manager | OPEN | ROWS2: OPEN - no served wiring plus calling test triple proven in int."""
    client, headers = make_client()
    package_id = "k02rest-b100-pkg"
    resp = client.post(
        "/v1/split-gates/split-bounded",
        json={
            "package_id": package_id,
            "goal": "bounded context per manager",
            "context_refs": refs(6, "b100"),
            "max_parts": 3,
            "opt_in": True,
            "max_context_per_part": 2,
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["count"] == 3
    assert body["context_per_part"] == [2, 2, 2]
    over = client.post(
        "/v1/split-gates/split-bounded",
        json={
            "package_id": package_id,
            "goal": "bound too tight for the cap",
            "context_refs": refs(6, "b100-over"),
            "max_parts": 3,
            "opt_in": True,
            "max_context_per_part": 1,
        },
        headers=headers,
    )
    assert over.status_code == 409
    assert over.json()["detail"]["code"] == "CONTEXT_BOUND_EXCEEDED"


def test_k02rest_b_open_packages_gates_crosschecked():
    """kit/BUILD_PLAN.md:1281 | 118 | K02 | open packages and gates cross-checked at gate evaluation | OPEN | ROWS2: OPEN - no served wiring plus calling test triple proven in int."""
    client, headers = make_client()
    package_id = "k02rest-b118-pkg"
    for part_id in (package_id + ":part-a", package_id + ":integration"):
        gate = client.post(
            "/v1/split-gates/part-gate",
            json={"part_id": part_id, "verdict": "PASS"},
            headers=headers,
        )
        assert gate.status_code == 200, gate.text
        audit = client.post(
            "/v1/split-gates/part-audit",
            json={
                "part_id": part_id,
                "result": "PASS",
                "auditor_session_ref": "sess-k02rest-b118-aud",
                "producer_session_refs": ["sess-k02rest-b118-prod"],
                "context_integrity": True,
            },
            headers=headers,
        )
        assert audit.status_code == 200, audit.text
    verdict = client.post(
        "/v1/split-gates/phase-gate",
        json={
            "package_ids": [package_id],
            "open_packages": [package_id],
            "gate_reports": [
                {"package_id": package_id, "gate": "PASS", "audit": "PASS"}
            ],
        },
        headers=headers,
    )
    assert verdict.status_code == 200, verdict.text
    assert verdict.json()["gate"] == "PASS"
    assert verdict.json()["conflicts"] == []
    conflict = client.post(
        "/v1/split-gates/phase-gate",
        json={
            "package_ids": [package_id],
            "open_packages": [package_id, "k02rest-b118-still-open"],
            "gate_reports": [
                {"package_id": package_id, "gate": "PASS", "audit": "PASS"}
            ],
        },
        headers=headers,
    )
    assert conflict.status_code == 409
    assert "k02rest-b118-still-open" in conflict.json()["detail"]["conflicts"]


def test_k02rest_b_manifest_hash_part_validation():
    """kit/BUILD_PLAN.md:1287 | 96 | K02 | frozen interface manifest with hash checked in part validation | OPEN | ROWS2: OPEN - no served wiring plus calling test triple proven in int."""
    client, headers = make_client()
    manifest_id = "k02rest-b96-manifest"
    frozen = client.post(
        "/v1/split-gates/manifests",
        json={
            "manifest_id": manifest_id,
            "version": 1,
            "parts": [
                {
                    "package_id": manifest_id,
                    "contract_hash": "pending-freeze",
                    "gate_verdict_ref": "gate:k02rest-b96:part-000",
                    "audit_verdict_ref": "audit:k02rest-b96:part-000",
                }
            ],
        },
        headers=headers,
    )
    assert frozen.status_code == 200, frozen.text
    manifest = frozen.json()
    assert manifest["hash_algorithm"] == "sha256"
    assert len(manifest["hash"]) == 64
    stamped = {
        "package_id": manifest_id,
        "contract_hash": manifest["hash"],
        "gate_verdict_ref": "gate:k02rest-b96:part-000",
        "audit_verdict_ref": "audit:k02rest-b96:part-000",
    }
    valid = client.post(
        "/v1/split-gates/validate-part",
        json={"ref": stamped, "manifest": manifest},
        headers=headers,
    )
    assert valid.status_code == 200
    assert valid.json()["valid"] is True
    foreign = dict(stamped, contract_hash="0" * 64)
    invalid = client.post(
        "/v1/split-gates/validate-part",
        json={"ref": foreign, "manifest": manifest},
        headers=headers,
    )
    assert invalid.status_code == 200
    assert invalid.json()["valid"] is False
    tampered = dict(manifest, parts=[])
    tampered_check = client.post(
        "/v1/split-gates/validate-part",
        json={"ref": stamped, "manifest": tampered},
        headers=headers,
    )
    assert tampered_check.status_code == 200
    assert tampered_check.json()["valid"] is False


def test_k02rest_b_fanout_bounded_by_scheduler_caps():
    """kit/BUILD_PLAN.md:1404 | M-P1-10 | K02 | Manager fan-out bounded by scheduler caps; excess queues | OPEN | ROWS2: OPEN - no served wiring plus calling test triple proven in int."""
    client, headers = make_client()
    package_id = "k02rest-bm110-pkg"
    body = split_parts(client, headers, package_id, 5, 5)
    parts = body["parts"]
    settings = {
        "multi_manager_mode": True,
        "max_parallel_managers": 2,
        "overlap": False,
        "integration_policy": "manager-integrates",
        "model_pool_per_manager": {},
    }
    fanned = client.post(
        "/v1/split-gates/fanout",
        json={"parts": parts, "settings": settings, "wall_time_s": 1.0},
        headers=headers,
    )
    assert fanned.status_code == 200, fanned.text
    fanned_body = fanned.json()
    running = [part["gate_verdict_ref"] for part in fanned_body["running"]]
    queued = [part["gate_verdict_ref"] for part in fanned_body["queued"]]
    assert running == [part["gate_verdict_ref"] for part in parts[:2]]
    assert queued == [part["gate_verdict_ref"] for part in parts[2:]]
    assert running + queued == [part["gate_verdict_ref"] for part in parts]
    positions = [slot["position"] for slot in fanned_body["slots"]]
    assert positions == [0, 1, 2, 3, 4]
    assert [slot["estimated_start_s"] for slot in fanned_body["slots"]] == [
        0.0,
        0.0,
        1.0,
        1.0,
        2.0,
    ]
    serial = client.post(
        "/v1/split-gates/fanout",
        json={
            "parts": parts,
            "settings": dict(settings, multi_manager_mode=False),
        },
        headers=headers,
    )
    assert serial.status_code == 200
    assert len(serial.json()["running"]) == 1
    assert len(serial.json()["queued"]) == 4
    bad_cap = client.post(
        "/v1/split-gates/fanout",
        json={
            "parts": parts,
            "settings": dict(settings, max_parallel_managers=0),
        },
        headers=headers,
    )
    assert bad_cap.status_code == 400
