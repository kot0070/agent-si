"""K03 FXCATALOG set-A runner: link_check.

Fetches loopback pages (params.base_url plus paths, or explicit urls),
extracts same-origin links and verifies each one responds below 400.
External (non-loopback) links are recorded as skipped and never
fetched; an explicitly non-loopback base/URL is BLOCKED with reason
non_loopback. Broken links are FAIL; a clean page set is PASS; no
checkable same-origin links is UNSUPPORTED, never PASS.

Stdlib only. Never real services: loopback only. No hardcoded PASS.
"""

from __future__ import annotations

import http.client
import ipaddress
import json
import os
import socket
import ssl
import sys
import time
import urllib.parse
from html.parser import HTMLParser

RUNNER_ID = "link_check"
RUNNER_VERSION = "1.0.0"
RUNNER_TIMEOUT_S = 120
RUNNER_NEEDS = {
    "tools": [],
    "network": True,
    "project_tooling": False,
    "local_subprocess": False,
    "env": [],
}
RUNNER_DESCRIPTION = (
    "Verifies same-origin loopback links respond below 400; "
    "external links skipped, non-loopback input BLOCKED."
)


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.urls = []

    def handle_starttag(self, tag, attrs):
        item = dict(attrs)
        if tag == "a" and item.get("href"):
            self.urls.append(item["href"])
        elif tag in ("img", "script") and item.get("src"):
            self.urls.append(item["src"])
        elif tag == "link" and item.get("href"):
            self.urls.append(item["href"])


def _read_input():
    raw = sys.stdin.buffer.read().decode("utf-8")
    request = json.loads(raw)
    project_root = os.path.abspath(request.get("project_root", "") or ".")
    budgets = request.get("budgets", {}) or {}
    try:
        timeout_s = float(budgets.get("timeout_s", 60.0))
    except (TypeError, ValueError):
        timeout_s = 60.0
    evidence_dir = os.path.abspath(budgets.get("evidence_dir", "") or ".")
    params = request.get("params", {}) or {}
    return project_root, request.get("test_id", ""), params, timeout_s, evidence_dir


def _emit(test_id, status, reason, assertions, evidence):
    sys.stdout.write(
        json.dumps(
            {
                "test_id": test_id,
                "runner_id": RUNNER_ID,
                "status": status,
                "reason": reason,
                "assertions": assertions,
                "evidence": evidence,
            }
        )
        + "\n"
    )
    sys.stdout.flush()


def _loopback_ok(host):
    try:
        parsed = ipaddress.ip_address(host)
        if parsed.is_loopback:
            return True, ""
        return False, "non_loopback"
    except ValueError:
        pass
    if host.lower() == "localhost":
        return True, ""
    try:
        infos = socket.getaddrinfo(host, None, family=socket.AF_UNSPEC)
    except socket.gaierror:
        return False, "unresolvable_host"
    if not infos:
        return False, "unresolvable_host"
    for info in infos:
        try:
            if not ipaddress.ip_address(info[4][0]).is_loopback:
                return False, "non_loopback"
        except ValueError:
            return False, "non_loopback"
    return True, ""


def _fetch(scheme, host, port, path, timeout_s):
    if scheme == "https":
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        connection = http.client.HTTPSConnection(
            host, port, timeout=timeout_s, context=context
        )
    else:
        connection = http.client.HTTPConnection(host, port, timeout=timeout_s)
    try:
        connection.request("GET", path or "/")
        response = connection.getresponse()
        body = response.read(262144)
        return response.status, body
    finally:
        connection.close()


def main() -> int:
    try:
        project_root, test_id, params, timeout_s, evidence_dir = _read_input()
    except Exception as exc:
        _emit("", "BLOCKED", "bad_input: %s" % exc, 0, [])
        return 0
    os.makedirs(evidence_dir, exist_ok=True)
    name = RUNNER_ID + ".json"

    def report(payload, status, reason, assertions):
        with open(os.path.join(evidence_dir, name), "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        _emit(test_id, status, reason, assertions, [name])

    explicit = params.get("urls")
    base_url = params.get("base_url")
    pages = []
    if explicit is not None:
        if not isinstance(explicit, list) or not all(
            isinstance(item, str) for item in explicit
        ):
            report({}, "BLOCKED", "bad_params urls", 0)
            return 0
        for item in explicit:
            try:
                parts = urllib.parse.urlsplit(item)
            except ValueError:
                report({}, "BLOCKED", "bad_params urls", 0)
                return 0
            if parts.scheme not in ("http", "https") or not parts.hostname:
                report({}, "BLOCKED", "bad_params urls", 0)
                return 0
            ok, why = _loopback_ok(parts.hostname)
            if not ok:
                report({"url": item}, "BLOCKED", why, 0)
                return 0
            try:
                port = parts.port or (443 if parts.scheme == "https" else 80)
            except ValueError:
                report({}, "BLOCKED", "bad_params urls", 0)
                return 0
            pages.append(
                (parts.scheme, parts.hostname, port, parts.path or "/")
            )
    else:
        if base_url is None:
            report({}, "UNSUPPORTED", "no_base_url", 0)
            return 0
        if not isinstance(base_url, str):
            report({}, "BLOCKED", "bad_params base_url", 0)
            return 0
        try:
            parts = urllib.parse.urlsplit(base_url)
        except ValueError:
            report({}, "BLOCKED", "bad_params base_url", 0)
            return 0
        if parts.scheme not in ("http", "https") or not parts.hostname:
            report({}, "BLOCKED", "bad_params base_url", 0)
            return 0
        ok, why = _loopback_ok(parts.hostname)
        if not ok:
            report({"base_url": base_url}, "BLOCKED", why, 0)
            return 0
        try:
            port = parts.port or (443 if parts.scheme == "https" else 80)
        except ValueError:
            report({}, "BLOCKED", "bad_params base_url", 0)
            return 0
        paths = params.get("paths", ["/"])
        if not isinstance(paths, list) or not all(
            isinstance(item, str) for item in paths
        ):
            report({}, "BLOCKED", "bad_params paths", 0)
            return 0
        for item in paths:
            if not item.startswith("/"):
                report({}, "BLOCKED", "bad_params paths", 0)
                return 0
            pages.append((parts.scheme, parts.hostname, port, item))
    if not pages:
        report({}, "UNSUPPORTED", "no_pages", 0)
        return 0

    deadline = time.perf_counter() + max(1.0, timeout_s)
    origin = (pages[0][0], pages[0][1], pages[0][2])
    checked = []
    skipped = []
    broken = []
    seen = set()
    for scheme, host, port, path in pages:
        key = (scheme, host, port, path)
        if key in seen:
            continue
        seen.add(key)
        remaining = max(0.5, min(10.0, deadline - time.perf_counter()))
        started = time.perf_counter()
        try:
            status, body = _fetch(scheme, host, port, path, remaining)
        except Exception as exc:
            broken.append(
                {"url": "%s://%s:%d%s" % (scheme, host, port, path),
                 "error": "fetch_error: %s" % exc}
            )
            continue
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if status >= 400:
            broken.append(
                {"url": "%s://%s:%d%s" % (scheme, host, port, path),
                 "status": status}
            )
            continue
        parser = _Links()
        try:
            parser.feed(body.decode("utf-8", "replace"))
        except Exception:
            continue
        base = "%s://%s:%d%s" % (scheme, host, port, path)
        for href in parser.urls:
            absolute = urllib.parse.urljoin(base, href)
            try:
                sub = urllib.parse.urlsplit(absolute)
            except ValueError:
                continue
            if sub.scheme not in ("http", "https"):
                skipped.append(absolute)
                continue
            ok, _ = _loopback_ok(sub.hostname or "")
            if (
                (sub.scheme, sub.hostname, sub.port or (443 if sub.scheme == "https" else 80))
                != origin
                or not ok
            ):
                skipped.append(absolute)
                continue
            target = (sub.scheme, sub.hostname, sub.port or (443 if sub.scheme == "https" else 80), sub.path or "/")
            if target in seen:
                continue
            seen.add(target)
            remaining = max(0.5, min(10.0, deadline - time.perf_counter()))
            started = time.perf_counter()
            try:
                status, _ = _fetch(target[0], target[1], target[2], target[3], remaining)
            except Exception as exc:
                broken.append({"url": absolute, "error": "fetch_error: %s" % exc})
                continue
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            entry = {"url": absolute, "status": status,
                     "latency_ms": round(elapsed_ms, 1)}
            if status >= 400:
                broken.append(entry)
            else:
                checked.append(entry)
    payload = {"checked": checked, "broken": broken, "skipped": skipped}
    if broken:
        first = broken[0].get("url", "?")
        report(
            payload,
            "FAIL",
            "%d broken link(s), first %s" % (len(broken), first),
            len(checked) + len(broken),
        )
    elif not checked:
        report(payload, "UNSUPPORTED", "no_links", 0)
    else:
        report(
            payload, "PASS", "%d link(s) ok" % len(checked), len(checked)
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
