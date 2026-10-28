import hashlib
import json
import os
import sys

sys.path.insert(
    0,
    os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
    ),
)

import pytest

from agent_si.backend.orchestration import manifest as mf


def _base_manifest(manifest_id="m-1", version=1):
    return {
        "manifest_id": manifest_id,
        "version": version,
        "hash_algorithm": "sha256",
    }


def _sealed_manifest(manifest_id="m-1", version=1):
    base = _base_manifest(manifest_id, version)
    sealed = dict(base)
    sealed["hash"] = mf.frozen_hash(dict(base, hash="placeholder"))
    return sealed


def _ref_for(manifest):
    return {
        "package_id": "pkg-a",
        "contract_hash": manifest["hash"],
        "gate_verdict_ref": "gate-a",
        "audit_verdict_ref": "audit-a",
    }


def test_frozen_hash_is_sha256_64_hex_and_algorithm_field():
    manifest = _sealed_manifest()
    assert manifest["hash_algorithm"] == "sha256"
    digest = manifest["hash"]
    assert isinstance(digest, str)
    assert len(digest) == 64
    int(digest, 16)
    assert digest == mf.frozen_hash(manifest)


def test_frozen_hash_canonical_bytes():
    manifest = _base_manifest("m-can", 3)
    expected = hashlib.sha256(
        json.dumps(
            {
                "manifest_id": "m-can",
                "version": 3,
                "hash_algorithm": "sha256",
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    assert mf.frozen_hash(manifest) == expected


def test_round_trip_verify_true():
    manifest = _sealed_manifest("m-rt", 2)
    ref = _ref_for(manifest)
    assert mf.check_part_manifest(ref, manifest) is True


def test_tampered_hash_rejected():
    manifest = _sealed_manifest()
    manifest["hash"] = "f" * 64
    ref = {
        "package_id": "pkg-a",
        "contract_hash": "f" * 64,
        "gate_verdict_ref": "gate-a",
        "audit_verdict_ref": "audit-a",
    }
    assert mf.check_part_manifest(ref, manifest) is False


def test_tampered_fields_rejected():
    manifest = _sealed_manifest("m-orig", 1)
    manifest["manifest_id"] = "m-evil"
    ref = _ref_for(manifest)
    assert mf.check_part_manifest(ref, manifest) is False


def test_wrong_contract_hash_rejected():
    manifest = _sealed_manifest()
    ref = _ref_for(manifest)
    ref["contract_hash"] = "0" * 64
    assert ref["contract_hash"] != manifest["hash"]
    assert mf.check_part_manifest(ref, manifest) is False


def test_wrong_algorithm_rejected():
    manifest = _sealed_manifest()
    manifest["hash_algorithm"] = "md5"
    ref = _ref_for(manifest)
    assert mf.check_part_manifest(ref, manifest) is False


def test_malformed_manifests_rejected_never_raise():
    good = _sealed_manifest()
    good_ref = _ref_for(good)
    bad_manifests = [
        {},
        {"manifest_id": "m-1"},
        {"manifest_id": "m-1", "version": 1},
        {"manifest_id": "m-1", "version": 1, "hash_algorithm": "sha256"},
        {
            "manifest_id": "m-1",
            "version": 1,
            "hash_algorithm": "sha256",
            "hash": "not-hex",
        },
        {
            "manifest_id": "m-1",
            "version": "one",
            "hash_algorithm": "sha256",
            "hash": "0" * 64,
        },
        "not-a-dict",
        None,
    ]
    for bad in bad_manifests:
        assert mf.check_part_manifest(good_ref, bad) is False
    for bad_ref in [{}, {"package_id": "pkg-a"}, "x", None]:
        assert mf.check_part_manifest(bad_ref, good) is False


def test_canonical_stability_key_order():
    first = {
        "version": 7,
        "hash_algorithm": "sha256",
        "manifest_id": "m-stable",
        "hash": "ignored",
    }
    second = {
        "hash": "ignored-other",
        "manifest_id": "m-stable",
        "hash_algorithm": "sha256",
        "version": 7,
    }
    assert mf.frozen_hash(first) == mf.frozen_hash(second)


def _part_refs(manifest, tag="pkg-a", total=2):
    return [
        {
            "package_id": f"{tag}-{idx}",
            "contract_hash": manifest["hash"],
            "gate_verdict_ref": f"gate-{tag}-{idx}",
            "audit_verdict_ref": f"audit-{tag}-{idx}",
        }
        for idx in range(total)
    ]


def test_manifest_rec_type_exists_with_frozen_shape():
    assert hasattr(mf, "ManifestRec")
    rec = mf.ManifestRec("m-1", 1, [])
    data = rec.to_dict()
    assert set(data.keys()) == {
        "manifest_id",
        "version",
        "parts",
        "hash",
        "hash_algorithm",
    }


def test_build_manifest_rec_shape_and_hash():
    manifest = mf.build_manifest("m-b", 2, [])
    assert manifest["manifest_id"] == "m-b"
    assert manifest["version"] == 2
    assert manifest["parts"] == []
    assert manifest["hash_algorithm"] == "sha256"
    assert isinstance(manifest["hash"], str) and len(manifest["hash"]) == 64
    int(manifest["hash"], 16)
    assert mf.verify_manifest_hash(manifest) is True


def test_build_manifest_hash_canonical_field_order():
    parts = [
        {
            "package_id": "pkg-c-0",
            "contract_hash": "placeholder",
            "gate_verdict_ref": "gate-pkg-c-0",
            "audit_verdict_ref": "audit-pkg-c-0",
        }
    ]
    manifest = mf.build_manifest("m-can", 3, parts)
    expected = hashlib.sha256(
        json.dumps(
            {"manifest_id": "m-can", "version": 3, "parts": ["pkg-c-0"]},
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()
    assert manifest["hash"] == expected
    assert mf.canonical_manifest_bytes("m-can", 3, parts) == (
        json.dumps(
            {"manifest_id": "m-can", "version": 3, "parts": ["pkg-c-0"]},
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    )
    again = mf.build_manifest("m-can", 3, parts)
    assert again["hash"] == manifest["hash"]


def _sealed_with_refs(manifest_id="m-ok", version=1, tag="pkg-ok", total=2):
    draft = [
        {
            "package_id": f"{tag}-{idx}",
            "contract_hash": "placeholder",
            "gate_verdict_ref": f"gate-{tag}-{idx}",
            "audit_verdict_ref": f"audit-{tag}-{idx}",
        }
        for idx in range(total)
    ]
    manifest = mf.build_manifest(manifest_id, version, draft)
    for ref in manifest["parts"]:
        ref["contract_hash"] = manifest["hash"]
    return manifest


def test_check_manifest_parts_ok():
    sealed = _sealed_with_refs()
    assert mf.check_manifest(sealed) is True
    assert mf.check_manifest(sealed, list(sealed["parts"])) is True


def test_check_manifest_tampered_parts_rejected():
    sealed = _sealed_with_refs("m-t", 1, "pkg-t", 1)
    evil = dict(sealed)
    evil["parts"] = [{"package_id": "evil", "contract_hash": "0" * 64,
                      "gate_verdict_ref": "g", "audit_verdict_ref": "a"}]
    assert mf.check_manifest(evil) is False
    assert mf.verify_manifest_hash(evil) is False


def test_validate_part_ref_rejects_mismatch():
    manifest = mf.build_manifest("m-v", 1, [])
    good = {
        "package_id": "pkg-v",
        "contract_hash": manifest["hash"],
        "gate_verdict_ref": "g",
        "audit_verdict_ref": "a",
    }
    assert mf.validate_part_ref(good, manifest) is True
    bad = dict(good, contract_hash="0" * 64)
    assert bad["contract_hash"] != manifest["hash"]
    assert mf.validate_part_ref(bad, manifest) is False


def test_save_load_manifest_round_trip_hot_write(tmp_path):
    manifest = _sealed_with_refs("m-io", 1, "pkg-io", 2)
    path = str(tmp_path / "manifest.json")
    assert mf.save_manifest(manifest, path) == path
    with open(path, "rb") as handle:
        raw = handle.read()
    assert b"\r" not in raw
    loaded = mf.load_manifest(path)
    assert loaded == manifest
    assert mf.check_manifest(loaded) is True


def test_load_manifest_hash_mismatch_rejected(tmp_path):
    manifest = mf.build_manifest("m-tamper", 1, [])
    path = str(tmp_path / "manifest.json")
    mf.save_manifest(manifest, path)
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    data["version"] = 999
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, sort_keys=True, indent=2)
        handle.write("\n")
    with pytest.raises(ValueError):
        mf.load_manifest(path)


def test_save_manifest_hash_mismatch_refused(tmp_path):
    manifest = mf.build_manifest("m-save", 1, [])
    manifest["version"] = 2
    with pytest.raises(ValueError):
        mf.save_manifest(manifest, str(tmp_path / "manifest.json"))
