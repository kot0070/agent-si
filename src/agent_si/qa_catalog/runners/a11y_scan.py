"""K03 FXCATALOG set-A runner: a11y_scan.

Scans .html files with the stdlib parser: images need alt text,
inputs need labels, the document needs lang + a non-empty title,
headings must not skip levels, and links/buttons need accessible
names. Any violation is FAIL; a clean tree is PASS; no .html files
(or no checkable elements) is UNSUPPORTED, never PASS.

Stdlib only. No DATA reads at runtime. No hardcoded PASS.
"""

from __future__ import annotations

import json
import os
import sys
from html.parser import HTMLParser

RUNNER_ID = "a11y_scan"
RUNNER_VERSION = "1.0.0"
RUNNER_TIMEOUT_S = 60
RUNNER_NEEDS = {
    "tools": [],
    "network": False,
    "project_tooling": False,
    "local_subprocess": False,
    "env": [],
}
RUNNER_DESCRIPTION = (
    "Scans html for img alt, input labels, lang/title, heading order "
    "and link/button names."
)

_SKIP_DIRS = (".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build")

_LABELABLE = (
    "text",
    "password",
    "email",
    "number",
    "search",
    "tel",
    "url",
    "checkbox",
    "radio",
    "file",
)


class _Doc(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.images = []
        self.inputs = []
        self.labels_for = set()
        self.label_depth = 0
        self.lang = None
        self.in_title = False
        self.title_text = ""
        self.title_count = 0
        self.headings = []
        self.named = []
        self._text_stack = []

    def handle_starttag(self, tag, attrs):
        item = dict(attrs)
        if tag == "html":
            self.lang = (item.get("lang") or "").strip()
        elif tag == "img":
            self.images.append((item.get("alt"), self.getpos()))
        elif tag == "input":
            kind = (item.get("type") or "text").lower()
            self.inputs.append(
                (
                    kind,
                    (item.get("id") or "").strip(),
                    (item.get("aria-label") or "").strip(),
                    (item.get("aria-labelledby") or "").strip(),
                    self.label_depth > 0,
                    self.getpos(),
                )
            )
        elif tag == "label":
            target = (item.get("for") or "").strip()
            if target:
                self.labels_for.add(target)
            self.label_depth += 1
        elif tag == "title":
            self.in_title = True
            self.title_count += 1
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.headings.append((int(tag[1]), self.getpos()))
        elif tag in ("a", "button"):
            self._text_stack.append(
                [
                    tag,
                    "",
                    (item.get("aria-label") or "").strip(),
                    (item.get("title") or "").strip(),
                    self.getpos(),
                    "img" if tag == "a" else "",
                ]
            )
        if tag == "img" and self._text_stack and self._text_stack[-1][0] in (
            "a",
            "button",
        ):
            alt = (item.get("alt") or "").strip()
            if alt:
                self._text_stack[-1][1] += alt

    def handle_endtag(self, tag):
        if tag == "label" and self.label_depth:
            self.label_depth -= 1
        if tag == "title":
            self.in_title = False
        if self._text_stack and self._text_stack[-1][0] == tag:
            entry = self._text_stack.pop()
            text = entry[1].strip()
            self.named.append((entry[0], text, entry[2], entry[3], entry[4]))

    def handle_data(self, data):
        if self.in_title:
            self.title_text += data
        if self._text_stack:
            self._text_stack[-1][1] += data


def _read_input():
    raw = sys.stdin.buffer.read().decode("utf-8")
    request = json.loads(raw)
    project_root = os.path.abspath(request.get("project_root", "") or ".")
    budgets = request.get("budgets", {}) or {}
    evidence_dir = os.path.abspath(budgets.get("evidence_dir", "") or ".")
    params = request.get("params", {}) or {}
    return project_root, request.get("test_id", ""), params, evidence_dir


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


def main() -> int:
    try:
        project_root, test_id, params, evidence_dir = _read_input()
    except Exception as exc:
        _emit("", "BLOCKED", "bad_input: %s" % exc, 0, [])
        return 0
    os.makedirs(evidence_dir, exist_ok=True)
    paths = params.get("paths", ["."])
    if not isinstance(paths, list) or not all(
        isinstance(item, str) for item in paths
    ):
        _emit(test_id, "BLOCKED", "bad_params paths", 0, [])
        return 0

    candidates = []
    for rel in paths:
        full = os.path.abspath(os.path.join(project_root, rel))
        if full != project_root and not full.startswith(project_root + os.sep):
            continue
        if os.path.isfile(full) and full.lower().endswith((".html", ".htm")):
            candidates.append(full)
        elif os.path.isdir(full):
            for dirpath, dirnames, filenames in os.walk(full):
                dirnames[:] = [item for item in dirnames if item not in _SKIP_DIRS]
                for filename in filenames:
                    if filename.lower().endswith((".html", ".htm")):
                        candidates.append(os.path.join(dirpath, filename))
    candidates = sorted(set(candidates))

    name = RUNNER_ID + ".json"
    violations = []
    elements = 0
    files = 0
    for full in candidates:
        rel = os.path.relpath(full, project_root)
        try:
            with open(full, "r", encoding="utf-8") as handle:
                text = handle.read()
        except (OSError, UnicodeError):
            continue
        files += 1
        doc = _Doc()
        try:
            doc.feed(text)
            doc.close()
        except Exception:
            violations.append({"path": rel, "rule": "unparseable"})
            continue
        for alt, pos in doc.images:
            elements += 1
            if not (alt or "").strip():
                violations.append(
                    {"path": rel, "line": pos[0], "rule": "img_missing_alt"}
                )
        for kind, ident, aria, labelledby, wrapped, pos in doc.inputs:
            if kind == "hidden":
                continue
            if kind not in _LABELABLE and kind not in ("submit", "button"):
                elements += 1
                continue
            elements += 1
            ok = bool(aria or labelledby or wrapped)
            if not ok and ident:
                ok = ident in doc.labels_for
            if kind in ("submit", "button") and not ok:
                ok = True
            if not ok:
                violations.append(
                    {"path": rel, "line": pos[0], "rule": "input_missing_label"}
                )
        elements += 1
        if not (doc.lang or ""):
            violations.append({"path": rel, "line": 1, "rule": "html_missing_lang"})
        elements += 1
        if not doc.title_text.strip():
            violations.append({"path": rel, "line": 1, "rule": "title_missing"})
        previous = 0
        for level, pos in doc.headings:
            elements += 1
            if previous and level > previous + 1:
                violations.append(
                    {
                        "path": rel,
                        "line": pos[0],
                        "rule": "heading_order_skip",
                    }
                )
            previous = level
        for tag, text_content, aria, title, pos in doc.named:
            elements += 1
            if not (text_content or aria or title):
                violations.append(
                    {
                        "path": rel,
                        "line": pos[0],
                        "rule": "%s_missing_name" % tag,
                    }
                )
    with open(os.path.join(evidence_dir, name), "w", encoding="utf-8") as handle:
        json.dump(
            {"files": files, "elements": elements, "violations": violations},
            handle,
            indent=2,
        )
    if not files or not elements:
        _emit(test_id, "UNSUPPORTED", "no_checkable_elements", 0, [name])
    elif violations:
        _emit(
            test_id,
            "FAIL",
            "%d violation(s) in %d element(s)" % (len(violations), elements),
            elements,
            [name],
        )
    else:
        _emit(
            test_id,
            "PASS",
            "%d element(s) ok" % elements,
            elements,
            [name],
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
