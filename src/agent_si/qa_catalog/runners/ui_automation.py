"""Evaluate click/fill/assert_text/navigate steps against a fixture DOM."""
import json
import os
import re
import sys
from html.parser import HTMLParser

RUNNER_ID = "ui_automation"
RUNNER_VERSION = "1.0.0"
RUNNER_TIMEOUT_S = 60
RUNNER_NEEDS = {"tools": [], "network": False, "project_tooling": False,
                "local_subprocess": False}
RUNNER_DESCRIPTION = "Replay UI steps against a local fixture DOM."

ACTIONS = ("click", "fill", "assert_text", "navigate")

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


class _Node:
    def __init__(self, tag, attrs):
        self.tag = tag
        self.attrs = dict(attrs)
        self.text = ""
        self.children = []
        self.clicked = False


class _Dom(HTMLParser):
    def __init__(self):
        super().__init__()
        self.root = _Node("root", {})
        self._stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, attrs)
        self._stack[-1].children.append(node)
        self._stack.append(node)

    def handle_endtag(self, tag):
        if len(self._stack) > 1:
            self._stack.pop()

    def handle_data(self, data):
        self._stack[-1].text += data


def _all_nodes(node):
    yield node
    for child in node.children:
        yield from _all_nodes(child)


def _matches(node, selector):
    if selector.startswith("#"):
        return node.attrs.get("id", "") == selector[1:]
    if selector.startswith("."):
        classes = str(node.attrs.get("class", "")).split()
        return selector[1:] in classes
    return node.tag == selector.lower()


def _find(root, selector):
    for node in _all_nodes(root):
        if node.tag != "root" and _matches(node, selector):
            return node
    return None


def _load_dom(project_root, name):
    full = os.path.abspath(os.path.join(project_root, name))
    if not _within(full, [project_root]):
        return None, "path_escape"
    try:
        with open(full, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return None, "read_failed"
    dom = _Dom()
    try:
        dom.feed(text)
    except Exception:
        return None, "parse_failed"
    return dom.root, ""


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
    steps = params.get("steps")
    if not steps:
        res["status"] = "UNSUPPORTED"
        res["reason"] = "no_steps"
        return res
    if not isinstance(steps, list):
        res["status"] = "BLOCKED"
        res["reason"] = "input_not_provided"
        return res
    if params.get("driver", "fixture-dom") != "fixture-dom":
        res["status"] = "BLOCKED"
        res["reason"] = "needs-driver"
        return res
    dom_file = params.get("dom_file")
    if not dom_file or not isinstance(dom_file, str):
        res["status"] = "BLOCKED"
        res["reason"] = "input_not_provided"
        return res
    root, error = _load_dom(project_root, dom_file)
    if root is None:
        res["status"] = "BLOCKED" if error == "path_escape" else "FAIL"
        res["reason"] = error
        res["assertions"] = 1
        return res
    failed = []
    executed = 0
    for step in steps:
        if not isinstance(step, dict):
            failed.append("bad_step")
            continue
        action = step.get("action")
        selector = step.get("selector", "")
        if action in ("click", "fill", "assert_text") and not selector:
            res["status"] = "BLOCKED"
            res["reason"] = "empty_selector"
            return res
        if action == "navigate":
            target = step.get("value", "")
            if not isinstance(target, str) or not target:
                failed.append("bad_navigate")
                executed += 1
                continue
            root, error = _load_dom(project_root, target)
            if root is None:
                failed.append("navigate_failed")
            executed += 1
        elif action == "click":
            node = _find(root, selector)
            if node is None:
                failed.append("no_match:" + selector)
            else:
                node.clicked = True
            executed += 1
        elif action == "fill":
            node = _find(root, selector)
            if node is None:
                failed.append("no_match:" + selector)
            else:
                node.attrs["value"] = step.get("value", "")
            executed += 1
        elif action == "assert_text":
            node = _find(root, selector)
            want = str(step.get("text", ""))
            if node is None or want not in node.text:
                failed.append("assert_failed:" + selector)
            executed += 1
        else:
            res["status"] = "BLOCKED"
            res["reason"] = "unknown_action"
            return res
    res["assertions"] = executed
    try:
        os.makedirs(evidence_dir, exist_ok=True)
        out = os.path.abspath(os.path.join(evidence_dir, "ui_result.json"))
        if _within(out, [evidence_dir]):
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"executed": executed,
                                     "failed": failed}))
            res["evidence"] = ["ui_result.json"]
    except OSError:
        pass
    if failed:
        res["status"] = "FAIL"
        res["reason"] = "step_failed:" + failed[0]
    else:
        res["status"] = "PASS"
        res["reason"] = "all_steps_hold"
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
