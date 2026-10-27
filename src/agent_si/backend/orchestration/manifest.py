"""Frozen manifest hash + ManifestRec build/check/persistence (frozen K02 contract).

ManifestRec frozen shape::
    {manifest_id, version, parts, hash, hash_algorithm}

hash is hex-sha256 over the canonical bytes of the ordered fields
(manifest_id, version, parts); hash_algorithm is always "sha256".
Persistence is HOT-WRITE (temp file in the same directory + os.replace,
LF endings). Hash-mismatched refs and manifests are rejected, never raised
on the boolean paths; load_manifest raises ValueError on mismatch.
"""

from __future__ import annotations

import hashlib as _hashlib
import json as _json
import os as _os

__all__ = [
    "frozen_hash",
    "check_part_manifest",
    "ManifestRec",
    "canonical_manifest_bytes",
    "manifest_hash",
    "build_manifest",
    "verify_manifest_hash",
    "validate_part_ref",
    "check_manifest",
    "save_manifest",
    "load_manifest",
]


def _canonical_bytes(manifest_id: str, version: int, hash_algorithm: str) -> bytes:
    canonical = {
        "hash_algorithm": hash_algorithm,
        "manifest_id": manifest_id,
        "version": version,
    }
    return _json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def frozen_hash(manifest: dict) -> str:
    manifest_id = str(manifest["manifest_id"])
    version = int(manifest["version"])
    hash_algorithm = str(manifest["hash_algorithm"])
    return _hashlib.sha256(
        _canonical_bytes(manifest_id, version, hash_algorithm)
    ).hexdigest()


def check_part_manifest(ref: dict, manifest: dict) -> bool:
    try:
        if not isinstance(ref, dict) or not isinstance(manifest, dict):
            return False
        if manifest.get("hash_algorithm") != "sha256":
            return False
        stored = manifest.get("hash")
        if not isinstance(stored, str) or len(stored) != 64:
            return False
        try:
            int(stored, 16)
        except ValueError:
            return False
        if stored != frozen_hash(manifest):
            return False
        contract = ref.get("contract_hash")
        if not isinstance(contract, str):
            return False
        return contract == stored
    except Exception:
        return False


class ManifestRec:
    """ManifestRec record type: {manifest_id, version, parts, hash, hash_algorithm}."""

    def __init__(
        self,
        manifest_id: str,
        version: int,
        parts: list,
        hash: str = "",
        hash_algorithm: str = "sha256",
    ) -> None:
        self.manifest_id = str(manifest_id)
        self.version = int(version)
        self.parts = list(parts)
        self.hash = str(hash)
        self.hash_algorithm = str(hash_algorithm)

    def to_dict(self) -> dict:
        return {
            "manifest_id": self.manifest_id,
            "version": self.version,
            "parts": list(self.parts),
            "hash": self.hash,
            "hash_algorithm": self.hash_algorithm,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ManifestRec":
        if not isinstance(data, dict):
            raise ValueError("POLICY_CONFLICT: manifest must be a dict")
        return cls(
            manifest_id=data.get("manifest_id", ""),
            version=data.get("version", 0),
            parts=data.get("parts", []),
            hash=data.get("hash", ""),
            hash_algorithm=data.get("hash_algorithm", "sha256"),
        )


def _part_identity(part: object) -> object:
    if isinstance(part, dict):
        package_id = part.get("package_id")
        if isinstance(package_id, str):
            return package_id
    return part


def canonical_manifest_bytes(manifest_id: str, version: int, parts: list) -> bytes:
    canonical = {
        "manifest_id": str(manifest_id),
        "version": int(version),
        "parts": [_part_identity(part) for part in list(parts)],
    }
    return _json.dumps(
        canonical, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def manifest_hash(manifest: dict) -> str:
    return _hashlib.sha256(
        canonical_manifest_bytes(
            str(manifest["manifest_id"]),
            int(manifest["version"]),
            list(manifest.get("parts", [])),
        )
    ).hexdigest()


def build_manifest(manifest_id: str, version: int, parts: list) -> dict:
    items = list(parts)
    rec = ManifestRec(str(manifest_id), int(version), items)
    rec.hash = _hashlib.sha256(
        canonical_manifest_bytes(rec.manifest_id, rec.version, rec.parts)
    ).hexdigest()
    rec.hash_algorithm = "sha256"
    return rec.to_dict()


def verify_manifest_hash(manifest: dict) -> bool:
    try:
        if not isinstance(manifest, dict):
            return False
        if manifest.get("hash_algorithm") != "sha256":
            return False
        stored = manifest.get("hash")
        if not isinstance(stored, str) or len(stored) != 64:
            return False
        try:
            int(stored, 16)
        except ValueError:
            return False
        return stored == manifest_hash(manifest)
    except Exception:
        return False


def validate_part_ref(ref: dict, manifest: dict) -> bool:
    try:
        if not isinstance(ref, dict) or not isinstance(manifest, dict):
            return False
        package_id = ref.get("package_id")
        contract = ref.get("contract_hash")
        gate_ref = ref.get("gate_verdict_ref")
        audit_ref = ref.get("audit_verdict_ref")
        if not isinstance(package_id, str) or not package_id.strip():
            return False
        if not isinstance(contract, str):
            return False
        if not isinstance(gate_ref, str) or not isinstance(audit_ref, str):
            return False
        if not verify_manifest_hash(manifest):
            return False
        return contract == manifest.get("hash")
    except Exception:
        return False


def check_manifest(manifest: dict, refs: list | None = None) -> bool:
    try:
        if not verify_manifest_hash(manifest):
            return False
        if refs is None:
            refs = manifest.get("parts", [])
        if not isinstance(refs, list):
            return False
        return all(validate_part_ref(ref, manifest) for ref in refs)
    except Exception:
        return False


def _hot_write_text(path: str, text: str) -> None:
    directory = _os.path.dirname(_os.path.abspath(path))
    tmp_path = _os.path.join(directory, ".tmp-manifest-%d" % _os.getpid())
    with open(tmp_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    _os.replace(tmp_path, path)


def save_manifest(manifest: dict, path: str) -> str:
    if not isinstance(manifest, dict):
        raise ValueError("POLICY_CONFLICT: manifest must be a dict")
    if not verify_manifest_hash(manifest):
        raise ValueError("POLICY_CONFLICT: manifest hash mismatch, save refused")
    text = _json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
    _hot_write_text(str(path), text)
    return str(path)


def load_manifest(path: str) -> dict:
    with open(str(path), "r", encoding="utf-8", newline=None) as handle:
        data = _json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("POLICY_CONFLICT: manifest file must hold a dict")
    for key in ("manifest_id", "version", "parts", "hash", "hash_algorithm"):
        if key not in data:
            raise ValueError("POLICY_CONFLICT: manifest missing key %s" % key)
    if not verify_manifest_hash(data):
        raise ValueError("POLICY_CONFLICT: manifest hash mismatch, load refused")
    return data
