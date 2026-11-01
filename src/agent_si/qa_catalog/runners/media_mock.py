"""Sniff fixture file formats by magic bytes and enforce size limits."""
import json
import os
import re
import sys

RUNNER_ID = "media_mock"
RUNNER_VERSION = "1.0.0"
RUNNER_TIMEOUT_S = 60
RUNNER_NEEDS = {"tools": [], "network": False, "project_tooling": False,
                "local_subprocess": False}
RUNNER_DESCRIPTION = "Validate fixture media formats and sizes."

_PROXY_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy",
               "https_proxy", "all_proxy")
_SECRET_RE = re.compile(
    r"secret|token|passwd|password|credential|api[_-]?key", re.IGNORECASE)


def _scrub_env():
    for key in list(os.environ):
        if _SECRET_RE.search(key):
            del os.environ[key]
    for key in _PROXY_VARS:
        os.environ[key] = ""


def _fresh(test_id):
    return {"test_id": test_id, "runner_id": RUNNER_ID, "status": "BLOCKED",
            "reason": "input_not_provided", "assertions": 0, "evidence": [],
            "child_pid": os.getpid(), "child_env_keys": sorted(os.environ),
            "proxies_emptied": all(os.environ.get(k, "") == ""
                                   for k in _PROXY_VARS)}


def _within(path, roots):
    target = os.path.realpath(os.path.abspath(path))
    for root in roots:
        base = os.path.realpath(os.path.abspath(root))
        if target == base or target.startswith(base + os.sep):
            return True
    return False


def _sniff(head):
    if head.startswith(bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A,
                              0x0A])):
        return "png"
    if head.startswith(bytes([0xFF, 0xD8, 0xFF])):
        return "jpeg"
    if head.startswith(b"GIF8"):
        return "gif"
    if head.startswith(b"BM"):
        return "bmp"
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return "webp"
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(bytes([0x50, 0x4B, 0x03, 0x04])):
        return "zip"
    return "unknown"


def _run(payload):
    params = payload.get("params")
    if not isinstance(params, dict):
        params = {}
    budgets = payload.get("budgets")
    if not isinstance(budgets, dict):
        budgets = {}
    project_root = payload.get("project_root") or ""
    evidence_dir = budgets.get("evidence_dir") or project_root or "."
    test_id = payload.get("test_id", "unknown")
    res = _fresh(test_id)
    files = params.get("files")
    if not files:
        res["status"] = "UNSUPPORTED"
        res["reason"] = "no_files"
        return res
    if not isinstance(files, list):
        res["status"] = "BLOCKED"
        res["reason"] = "input_not_provided"
        return res
    checked = 0
    bad = []
    for entry in files:
        if not isinstance(entry, dict):
            bad.append("bad_entry")
            continue
        rel = entry.get("path", "")
        if not isinstance(rel, str) or not rel:
            bad.append("bad_path")
            checked += 2
            continue
        full = os.path.abspath(os.path.join(project_root, rel))
        if not _within(full, [project_root]):
            res["status"] = "BLOCKED"
            res["reason"] = "path_escape"
            return res
        try:
            with open(full, "rb") as fh:
                head = fh.read(16)
            size = os.path.getsize(full)
        except OSError:
            bad.append(rel + ":unreadable")
            checked += 2
            continue
        want = str(entry.get("expect_format", "")).lower()
        if want == "jpg":
            want = "jpeg"
        found = _sniff(head)
        checked += 1
        if want and found != want:
            bad.append(rel + ":format")
        try:
            limit = entry.get("max_bytes")
            limit = None if limit is None else int(limit)
        except (TypeError, ValueError):
            limit = None
        checked += 1
        if limit is not None and size > limit:
            bad.append(rel + ":size")
    res["assertions"] = checked
    try:
        os.makedirs(evidence_dir, exist_ok=True)
        out = os.path.abspath(os.path.join(evidence_dir,
                                            "media_result.json"))
        if _within(out, [evidence_dir]):
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"checked": checked, "bad": bad}))
            res["evidence"] = ["media_result.json"]
    except OSError:
        pass
    if bad:
        res["status"] = "FAIL"
        res["reason"] = "media_mismatch:" + bad[0]
    else:
        res["status"] = "PASS"
        res["reason"] = "all_media_match"
    return res


def main():
    _scrub_env()
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    test_id = payload.get("test_id", "unknown")
    try:
        result = _run(payload)
    except Exception as exc:
        result = _fresh(test_id)
        result["reason"] = "exception:" + type(exc).__name__
    result["test_id"] = test_id
    result["runner_id"] = RUNNER_ID
    sys.stdout.write(json.dumps(result))


if __name__ == "__main__":
    main()
