"""Compare two PPM P6 fixture images byte by byte against a threshold."""
import json
import os
import re
import sys

RUNNER_ID = "visual_diff"
RUNNER_VERSION = "1.0.0"
RUNNER_TIMEOUT_S = 60
RUNNER_NEEDS = {"tools": [], "network": False, "project_tooling": False,
                "local_subprocess": False}
RUNNER_DESCRIPTION = "Byte-compare two PPM images under a threshold."

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


def _read_ppm(project_root, name):
    full = os.path.abspath(os.path.join(project_root, name))
    if not _within(full, [project_root]):
        return None, "path_escape"
    try:
        with open(full, "rb") as fh:
            raw = fh.read()
    except OSError:
        return None, "read_failed"
    tokens = []
    pos = 0
    header_end = 0
    if not raw.startswith(b"P6"):
        return None, "malformed_ppm"
    pos = 2
    while len(tokens) < 3:
        while pos < len(raw) and chr(raw[pos]).isspace():
            pos += 1
        if pos < len(raw) and raw[pos:pos + 1] == b"#":
            while pos < len(raw) and raw[pos:pos + 1] != b"\n":
                pos += 1
            continue
        start = pos
        while pos < len(raw) and not chr(raw[pos]).isspace():
            pos += 1
        if start == pos:
            return None, "malformed_ppm"
        tokens.append(raw[start:pos])
        header_end = pos
    try:
        width = int(tokens[0])
        height = int(tokens[1])
        maxval = int(tokens[2])
    except ValueError:
        return None, "malformed_ppm"
    if width <= 0 or height <= 0 or maxval != 255:
        return None, "malformed_ppm"
    if header_end < len(raw) and raw[header_end:header_end + 1] == b"\n":
        header_end += 1
    data = raw[header_end:]
    if len(data) < width * height * 3:
        return None, "malformed_ppm"
    return {"width": width, "height": height,
            "data": data[:width * height * 3]}, ""


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
    baseline = params.get("baseline")
    actual = params.get("actual")
    if not baseline or not actual:
        res["status"] = "UNSUPPORTED"
        res["reason"] = "no_images"
        return res
    try:
        threshold = float(params.get("threshold", 0.0))
    except (TypeError, ValueError):
        res["status"] = "BLOCKED"
        res["reason"] = "input_not_provided"
        return res
    first, err1 = _read_ppm(project_root, baseline)
    second, err2 = _read_ppm(project_root, actual)
    if first is None:
        res["status"] = "BLOCKED" if err1 in ("path_escape",
                                              "malformed_ppm") else "FAIL"
        res["reason"] = err1
        res["assertions"] = 1
        return res
    if second is None:
        res["status"] = "BLOCKED" if err2 in ("path_escape",
                                              "malformed_ppm") else "FAIL"
        res["reason"] = err2
        res["assertions"] = 1
        return res
    if (first["width"] != second["width"]
            or first["height"] != second["height"]):
        res["status"] = "FAIL"
        res["reason"] = "dimension_mismatch"
        res["assertions"] = 1
        return res
    first_bytes = first["data"]
    second_bytes = second["data"]
    overlap = min(len(first_bytes), len(second_bytes))
    diff = sum(1 for i in range(overlap)
               if first_bytes[i] != second_bytes[i])
    diff += abs(len(first_bytes) - len(second_bytes))
    total = max(len(first_bytes), len(second_bytes), 1)
    ratio = diff / total
    res["assertions"] = 1
    try:
        os.makedirs(evidence_dir, exist_ok=True)
        out = os.path.abspath(os.path.join(evidence_dir,
                                            "visual_result.json"))
        if _within(out, [evidence_dir]):
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"diff_bytes": diff, "total": total,
                                     "ratio": ratio, "threshold": threshold}))
            res["evidence"] = ["visual_result.json"]
    except OSError:
        pass
    if ratio <= threshold:
        res["status"] = "PASS"
        res["reason"] = "within_threshold"
    else:
        res["status"] = "FAIL"
        res["reason"] = "above_threshold:%.4f" % ratio
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
