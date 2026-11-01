"""K03 FXCATALOG set-A runner: contract_test.

Validates stdlib-schema samples: params carry (or files hold) a JSON
schema subset (type, required, properties, items, enum, string/number
bounds, pattern, additionalProperties) plus a list of samples. Any
invalid sample is FAIL; all valid is PASS; no schema/samples is
UNSUPPORTED, never PASS.

Stdlib only. No DATA reads at runtime. No hardcoded PASS.
"""

from __future__ import annotations

import json
import os
import re
import sys

RUNNER_ID = "contract_test"
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
    "Validates samples against a stdlib JSON-schema subset; any "
    "invalid sample FAILs."
)

_DEFAULT_SCHEMA_FILES = ("contract.schema.json", "schema.json")
_DEFAULT_SAMPLES_FILES = ("samples.json",)


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


def _check_type(value, name):
    if name == "string":
        return isinstance(value, str)
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if name == "boolean":
        return isinstance(value, bool)
    if name == "array":
        return isinstance(value, list)
    if name == "object":
        return isinstance(value, dict)
    if name == "null":
        return value is None
    return False


def _validate(value, schema, where):
    errors = []
    if not isinstance(schema, dict):
        return ["%s: bad schema node" % where]
    want = schema.get("type")
    if want is not None:
        names = want if isinstance(want, list) else [want]
        if not any(
            isinstance(item, str) and _check_type(value, item) for item in names
        ):
            return ["%s: expected type %s" % (where, want)]
    if isinstance(value, dict):
        for key in schema.get("required", []) or []:
            if key not in value:
                errors.append("%s: missing required %r" % (where, key))
        props = schema.get("properties", {}) or {}
        if isinstance(props, dict):
            for key, subschema in props.items():
                if key in value:
                    errors += _validate(
                        value[key], subschema, "%s.%s" % (where, key)
                    )
        if schema.get("additionalProperties") is False and isinstance(props, dict):
            for key in value:
                if key not in props:
                    errors.append("%s: extra property %r" % (where, key))
    if isinstance(value, list):
        items = schema.get("items")
        if isinstance(items, dict):
            for index, entry in enumerate(value):
                errors += _validate(entry, items, "%s[%d]" % (where, index))
        if isinstance(schema.get("minItems"), int) and len(value) < schema["minItems"]:
            errors.append("%s: too few items" % where)
        if isinstance(schema.get("maxItems"), int) and len(value) > schema["maxItems"]:
            errors.append("%s: too many items" % where)
    if "enum" in schema and value not in schema["enum"]:
        errors.append("%s: not one of enum" % where)
    if isinstance(value, str):
        if isinstance(schema.get("minLength"), int) and len(value) < schema["minLength"]:
            errors.append("%s: string too short" % where)
        if isinstance(schema.get("maxLength"), int) and len(value) > schema["maxLength"]:
            errors.append("%s: string too long" % where)
        if isinstance(schema.get("pattern"), str):
            try:
                if not re.search(schema["pattern"], value):
                    errors.append("%s: pattern mismatch" % where)
            except re.error:
                errors.append("%s: bad schema pattern" % where)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(schema.get("minimum"), (int, float)) and value < schema["minimum"]:
            errors.append("%s: below minimum" % where)
        if isinstance(schema.get("maximum"), (int, float)) and value > schema["maximum"]:
            errors.append("%s: above maximum" % where)
    return errors


def _load_file(project_root, rel):
    full = os.path.abspath(os.path.join(project_root, rel))
    if full != project_root and not full.startswith(project_root + os.sep):
        raise ValueError("outside project: %s" % rel)
    with open(full, "r", encoding="utf-8") as handle:
        return json.load(handle)


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

    schema = params.get("schema")
    samples = params.get("samples")
    try:
        if schema is None and params.get("schema_file"):
            schema = _load_file(project_root, params["schema_file"])
        if samples is None and params.get("samples_file"):
            samples = _load_file(project_root, params["samples_file"])
        if schema is None:
            for candidate in _DEFAULT_SCHEMA_FILES:
                full = os.path.join(project_root, candidate)
                if os.path.isfile(full):
                    schema = _load_file(project_root, candidate)
                    break
        if samples is None:
            for candidate in _DEFAULT_SAMPLES_FILES:
                full = os.path.join(project_root, candidate)
                if os.path.isfile(full):
                    samples = _load_file(project_root, candidate)
                    break
    except (OSError, ValueError) as exc:
        report({}, "FAIL", "unreadable contract file: %s" % exc, 1)
        return 0
    if schema is None or samples is None:
        report({}, "UNSUPPORTED", "no_schema_or_samples", 0)
        return 0
    if not isinstance(schema, dict):
        report({}, "BLOCKED", "bad_params schema", 0)
        return 0
    if not isinstance(samples, list):
        report({}, "BLOCKED", "bad_params samples", 0)
        return 0
    if not samples:
        report({"samples": 0}, "UNSUPPORTED", "no_samples", 0)
        return 0

    errors = []
    for index, sample in enumerate(samples):
        for message in _validate(sample, schema, "samples[%d]" % index):
            errors.append(message)
    payload = {"samples": len(samples), "errors": errors}
    if errors:
        report(
            payload,
            "FAIL",
            "%d error(s) in %d sample(s)" % (len(errors), len(samples)),
            len(samples),
        )
    else:
        report(payload, "PASS", "%d sample(s) valid" % len(samples), len(samples))
    return 0


if __name__ == "__main__":
    sys.exit(main())
