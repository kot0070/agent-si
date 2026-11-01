"""K03 FXCATALOG set-A runner: i18n_parity.

Compares locale JSON files key-by-key against the base locale: missing
keys and empty translations are FAIL. Extra keys fail only under
strict_extra. No locale dir (or no base locale) is UNSUPPORTED when
undiscovered, never PASS.

Stdlib only. No DATA reads at runtime. No hardcoded PASS.
"""

from __future__ import annotations

import json
import os
import sys

RUNNER_ID = "i18n_parity"
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
    "Compares locale JSON key parity against the base locale; "
    "missing keys and empty values FAIL."
)

_AUTO_DIRS = ("locale", "locales", "i18n", "_locales", "frontend/src/locale")


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


def _flatten(value, prefix=""):
    flat = {}
    if isinstance(value, dict):
        for key, item in value.items():
            name = "%s.%s" % (prefix, key) if prefix else str(key)
            flat.update(_flatten(item, name))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            flat.update(_flatten(item, "%s[%d]" % (prefix, index)))
    else:
        flat[prefix] = value
    return flat


def _find_dir(project_root):
    for rel in _AUTO_DIRS:
        full = os.path.join(project_root, rel)
        if not os.path.isdir(full):
            continue
        try:
            names = os.listdir(full)
        except OSError:
            continue
        if any(item.lower().endswith(".json") for item in names):
            return full
    return None


def main() -> int:
    try:
        project_root, test_id, params, evidence_dir = _read_input()
    except Exception as exc:
        _emit("", "BLOCKED", "bad_input: %s" % exc, 0, [])
        return 0
    os.makedirs(evidence_dir, exist_ok=True)
    name = RUNNER_ID + ".json"

    def report(payload, status, reason, assertions):
        with open(os.path.join(evidence_dir, name), "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        _emit(test_id, status, reason, assertions, [name])

    wanted = params.get("locales_dir")
    if wanted is not None and not isinstance(wanted, str):
        report({}, "BLOCKED", "bad_params locales_dir", 0)
        return 0
    base = params.get("base", "en")
    if not isinstance(base, str) or not base:
        report({}, "BLOCKED", "bad_params base", 0)
        return 0
    strict_extra = params.get("strict_extra", False)
    if not isinstance(strict_extra, bool):
        report({}, "BLOCKED", "bad_params strict_extra", 0)
        return 0

    if wanted is not None:
        locales_dir = os.path.abspath(os.path.join(project_root, wanted))
        if locales_dir != project_root and not locales_dir.startswith(
            project_root + os.sep
        ):
            report({}, "BLOCKED", "bad_params locales_dir", 0)
            return 0
        if not os.path.isdir(locales_dir):
            report({"locales_dir": wanted}, "FAIL", "missing_locales_dir", 1)
            return 0
    else:
        locales_dir = _find_dir(project_root)
        if locales_dir is None:
            report({}, "UNSUPPORTED", "no_locales_dir", 0)
            return 0
    try:
        files = sorted(
            item for item in os.listdir(locales_dir) if item.lower().endswith(".json")
        )
    except OSError:
        report({}, "FAIL", "unreadable_locales_dir", 1)
        return 0
    base_file = base + ".json"
    if base_file not in files:
        report(
            {"locales_dir": os.path.relpath(locales_dir, project_root)},
            "FAIL",
            "missing_base_locale",
            1,
        )
        return 0
    try:
        with open(os.path.join(locales_dir, base_file), "r", encoding="utf-8") as handle:
            base_data = json.load(handle)
    except (OSError, ValueError):
        report({}, "FAIL", "bad_base_json", 1)
        return 0
    if not isinstance(base_data, dict):
        report({}, "FAIL", "bad_base_json", 1)
        return 0
    base_flat = _flatten(base_data)
    if not base_flat:
        report({"base_keys": 0}, "FAIL", "empty_base", 1)
        return 0

    comparisons = 0
    violations = []
    locales = []
    for filename in files:
        if filename == base_file:
            continue
        try:
            with open(
                os.path.join(locales_dir, filename), "r", encoding="utf-8"
            ) as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            violations.append({"locale": filename, "key": "", "rule": "bad_json"})
            comparisons += 1
            continue
        if not isinstance(data, dict):
            violations.append({"locale": filename, "key": "", "rule": "bad_json"})
            comparisons += 1
            continue
        flat = _flatten(data)
        locales.append(filename)
        for key in sorted(base_flat):
            comparisons += 1
            if key not in flat:
                violations.append(
                    {"locale": filename, "key": key, "rule": "missing_key"}
                )
            elif isinstance(flat[key], str) and flat[key] == "":
                violations.append(
                    {"locale": filename, "key": key, "rule": "empty_value"}
                )
        if strict_extra:
            for key in sorted(flat):
                if key not in base_flat:
                    comparisons += 1
                    violations.append(
                        {"locale": filename, "key": key, "rule": "extra_key"}
                    )
    payload = {
        "locales_dir": os.path.relpath(locales_dir, project_root),
        "base": base,
        "base_keys": len(base_flat),
        "locales": locales,
        "comparisons": comparisons,
        "violations": violations,
    }
    if violations:
        report(
            payload,
            "FAIL",
            "%d violation(s) across %d comparison(s)"
            % (len(violations), comparisons),
            comparisons,
        )
    else:
        report(
            payload,
            "PASS",
            "%d comparison(s) across %d locale(s)"
            % (comparisons, len(locales)),
            comparisons,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
