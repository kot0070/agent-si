"""Validate a mock geo track: ranges and consecutive haversine gaps."""
import json
import math
import os
import re
import sys

RUNNER_ID = "geo_mock"
RUNNER_VERSION = "1.0.0"
RUNNER_TIMEOUT_S = 60
RUNNER_NEEDS = {"tools": [], "network": False, "project_tooling": False,
                "local_subprocess": False}
RUNNER_DESCRIPTION = "Check mock geo points and gap distances."

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


def _haversine_km(lat1, lon1, lat2, lon2):
    radius = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lam = math.radians(lon2 - lon1)
    arc = (math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1)
           * math.cos(phi2) * math.sin(delta_lam / 2.0) ** 2)
    return 2.0 * radius * math.asin(min(1.0, math.sqrt(arc)))


def _run(payload):
    params = payload.get("params")
    if not isinstance(params, dict):
        params = {}
    budgets = payload.get("budgets")
    if not isinstance(budgets, dict):
        budgets = {}
    evidence_dir = budgets.get("evidence_dir") or payload.get(
        "project_root") or "."
    test_id = payload.get("test_id", "unknown")
    res = _fresh(test_id)
    if params.get("permission") != "granted":
        res["status"] = "UNSUPPORTED"
        res["reason"] = "permission_not_granted"
        return res
    points = params.get("points")
    if not points:
        res["status"] = "UNSUPPORTED"
        res["reason"] = "no_points"
        return res
    if not isinstance(points, list):
        res["status"] = "BLOCKED"
        res["reason"] = "input_not_provided"
        return res
    try:
        gap = params.get("max_gap_km")
        gap = None if gap is None else float(gap)
    except (TypeError, ValueError):
        gap = None
    coords = []
    out_of_range = False
    for point in points:
        if not isinstance(point, dict):
            out_of_range = True
            continue
        try:
            lat = float(point["lat"])
            lon = float(point["lon"])
        except (KeyError, TypeError, ValueError):
            out_of_range = True
            continue
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            out_of_range = True
            continue
        coords.append((lat, lon))
    res["assertions"] = max(1, len(points))
    gap_breach = None
    if gap is not None and len(coords) >= 2:
        for first, second in zip(coords, coords[1:]):
            dist = _haversine_km(first[0], first[1], second[0], second[1])
            if dist > gap:
                gap_breach = dist
                break
    try:
        os.makedirs(evidence_dir, exist_ok=True)
        out = os.path.abspath(os.path.join(evidence_dir, "geo_result.json"))
        if _within(out, [evidence_dir]):
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"points": len(coords),
                                     "out_of_range": out_of_range,
                                     "gap_breach_km": gap_breach}))
            res["evidence"] = ["geo_result.json"]
    except OSError:
        pass
    if out_of_range:
        res["status"] = "FAIL"
        res["reason"] = "coordinate_out_of_range"
    elif gap_breach is not None:
        res["status"] = "FAIL"
        res["reason"] = "gap_breach:%.2fkm" % gap_breach
    else:
        res["status"] = "PASS"
        res["reason"] = "track_within_limits"
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
