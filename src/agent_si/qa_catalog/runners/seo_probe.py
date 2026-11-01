"""Fetch a loopback URL or fixture file and check required SEO meta tags."""
import ipaddress
import json
import os
import re
import sys
import urllib.parse
from html.parser import HTMLParser

RUNNER_ID = "seo_probe"
RUNNER_VERSION = "1.0.0"
RUNNER_TIMEOUT_S = 60
RUNNER_NEEDS = {"tools": [], "network": True, "project_tooling": False,
                "local_subprocess": False}
RUNNER_DESCRIPTION = "Check required SEO meta tags on a loopback page."

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


def _loopback_url(url):
    try:
        parts = urllib.parse.urlsplit(url)
    except Exception:
        return False
    if parts.scheme not in ("http", "https"):
        return False
    host = (parts.hostname or "").strip().lower()
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _fetch(url, timeout):
    import urllib.request
    req = urllib.request.Request(url,
                                 headers={"User-Agent": "qa-catalog-runner"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read()


class _Meta(HTMLParser):
    def __init__(self):
        super().__init__()
        self.found = set()
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        data = {str(k).lower(): (v or "") for k, v in attrs}
        if tag == "title":
            self._in_title = True
        if tag == "meta":
            if str(data.get("charset", "")).strip():
                self.found.add("charset")
            name = str(data.get("name", "")).lower()
            prop = str(data.get("property", "")).lower()
            if name in ("description", "viewport") and data.get("content"):
                self.found.add(name)
            if prop.startswith("og:") and data.get("content"):
                self.found.add(prop)

    def handle_data(self, data):
        if self._in_title and data.strip():
            self.found.add("title")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False


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
    url = params.get("url")
    if not url or not isinstance(url, str):
        res["status"] = "UNSUPPORTED"
        res["reason"] = "no_url"
        return res
    require = params.get("require_tags") or []
    if not isinstance(require, list):
        require = [require]
    timeout = budgets.get("timeout_s") or 30
    try:
        timeout = min(float(timeout), 20.0)
    except (TypeError, ValueError):
        timeout = 20.0
    text = None
    if url.lower().startswith(("http://", "https://")):
        if not _loopback_url(url):
            res["status"] = "BLOCKED"
            res["reason"] = "non_loopback"
            return res
        try:
            _, body = _fetch(url, timeout)
        except Exception:
            res["status"] = "FAIL"
            res["reason"] = "fetch_failed"
            res["assertions"] = 1
            return res
        text = body.decode("utf-8", errors="replace")
    else:
        full = os.path.abspath(os.path.join(project_root, url))
        if not _within(full, [project_root]):
            res["status"] = "BLOCKED"
            res["reason"] = "path_escape"
            return res
        try:
            with open(full, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            res["status"] = "FAIL"
            res["reason"] = "read_failed"
            res["assertions"] = 1
            return res
    parser = _Meta()
    try:
        parser.feed(text)
    except Exception:
        pass
    wanted = [str(t).lower() for t in require]
    missing = [t for t in wanted if t not in parser.found]
    res["assertions"] = 1 + len(wanted)
    detail = {"url": url, "found": sorted(parser.found), "missing": missing}
    try:
        os.makedirs(evidence_dir, exist_ok=True)
        out = os.path.abspath(os.path.join(evidence_dir, "seo_result.json"))
        if _within(out, [evidence_dir]):
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(detail))
            res["evidence"] = ["seo_result.json"]
    except OSError:
        pass
    if missing:
        res["status"] = "FAIL"
        res["reason"] = "missing_tags:" + ",".join(missing)
    else:
        res["status"] = "PASS"
        res["reason"] = "all_required_tags_present"
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
