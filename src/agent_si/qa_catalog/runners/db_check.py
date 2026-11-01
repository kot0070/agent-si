"""K03 FXCATALOG set-A runner: db_check.

Applies .sql migration files in sorted order onto a scratch sqlite
database created inside evidence_dir, runs params.seeds, then evaluates
params.invariants (SELECT-only queries with equals/min_count/max_count
expectations). Any error or mismatch is FAIL; all green is PASS; no
.sql files, seeds or invariants is UNSUPPORTED, never PASS.

Stdlib only (sqlite3). No DATA reads at runtime. No hardcoded PASS.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys

RUNNER_ID = "db_check"
RUNNER_VERSION = "1.0.0"
RUNNER_TIMEOUT_S = 120
RUNNER_NEEDS = {
    "tools": [],
    "network": False,
    "project_tooling": False,
    "local_subprocess": False,
    "env": [],
}
RUNNER_DESCRIPTION = (
    "Applies .sql migrations on scratch sqlite in evidence, runs "
    "seeds, evaluates SELECT invariants."
)

_AUTO_DIRS = ("migrations", "sql", "db", "db/migrations")
_DB_NAME = "db_check.sqlite"


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


def _find_dir(project_root):
    for rel in _AUTO_DIRS:
        full = os.path.join(project_root, rel)
        if not os.path.isdir(full):
            continue
        try:
            names = os.listdir(full)
        except OSError:
            continue
        if any(item.lower().endswith(".sql") for item in names):
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

    def report(payload, status, reason, assertions, extra=()):
        with open(os.path.join(evidence_dir, name), "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        _emit(test_id, status, reason, assertions, [name] + list(extra))

    wanted = params.get("migrations_dir")
    if wanted is not None and not isinstance(wanted, str):
        report({}, "BLOCKED", "bad_params migrations_dir", 0)
        return 0
    seeds = params.get("seeds", [])
    if not isinstance(seeds, list) or not all(
        isinstance(item, str) for item in seeds
    ):
        report({}, "BLOCKED", "bad_params seeds", 0)
        return 0
    invariants = params.get("invariants", [])
    if not isinstance(invariants, list) or not all(
        isinstance(item, dict) for item in invariants
    ):
        report({}, "BLOCKED", "bad_params invariants", 0)
        return 0

    sql_files = []
    if wanted is not None:
        migrations_dir = os.path.abspath(os.path.join(project_root, wanted))
        if migrations_dir != project_root and not migrations_dir.startswith(
            project_root + os.sep
        ):
            report({}, "BLOCKED", "bad_params migrations_dir", 0)
            return 0
        if not os.path.isdir(migrations_dir):
            report({}, "FAIL", "missing_migrations_dir", 1)
            return 0
        sql_files = sorted(
            os.path.join(migrations_dir, item)
            for item in os.listdir(migrations_dir)
            if item.lower().endswith(".sql")
        )
    else:
        migrations_dir = _find_dir(project_root)
        if migrations_dir is not None:
            sql_files = sorted(
                os.path.join(migrations_dir, item)
                for item in os.listdir(migrations_dir)
                if item.lower().endswith(".sql")
            )
    if not sql_files and not seeds and not invariants:
        report({}, "UNSUPPORTED", "no_migrations", 0)
        return 0

    db_path = os.path.join(evidence_dir, _DB_NAME)
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except OSError:
        report({}, "BLOCKED", "scratch_unwritable", 0)
        return 0
    statements = 0
    applied = []
    try:
        connection = sqlite3.connect(db_path)
    except Exception as exc:
        report({}, "BLOCKED", "sqlite_unavailable: %s" % exc, 0)
        return 0
    try:
        for full in sql_files:
            rel = os.path.relpath(full, project_root)
            try:
                with open(full, "r", encoding="utf-8") as handle:
                    script = handle.read()
            except (OSError, UnicodeError) as exc:
                report(
                    {"applied": applied},
                    "FAIL",
                    "unreadable migration %s: %s" % (rel, exc),
                    statements + 1,
                    (_DB_NAME,),
                )
                return 0
            try:
                connection.executescript(script)
            except Exception as exc:
                report(
                    {"applied": applied},
                    "FAIL",
                    "migration_error %s: %s" % (rel, exc),
                    statements + 1,
                    (_DB_NAME,),
                )
                return 0
            statements += 1
            applied.append(rel)
        for seed in seeds:
            if not seed.strip():
                continue
            try:
                connection.executescript(seed)
            except Exception as exc:
                report(
                    {"applied": applied},
                    "FAIL",
                    "seed_error: %s" % exc,
                    statements + 1,
                    (_DB_NAME,),
                )
                return 0
            statements += 1
        connection.commit()
        checked = []
        for invariant in invariants:
            sql = invariant.get("sql", "")
            if not isinstance(sql, str) or not sql.strip():
                report(
                    {"applied": applied, "checked": checked},
                    "FAIL",
                    "invariant_not_select",
                    statements + 1,
                    (_DB_NAME,),
                )
                return 0
            head = sql.strip().lstrip("(").upper()
            if not (head.startswith("SELECT") or head.startswith("WITH")):
                report(
                    {"applied": applied, "checked": checked},
                    "FAIL",
                    "invariant_not_select",
                    statements + 1,
                    (_DB_NAME,),
                )
                return 0
            try:
                rows = connection.execute(sql).fetchall()
            except Exception as exc:
                report(
                    {"applied": applied, "checked": checked},
                    "FAIL",
                    "invariant_error: %s" % exc,
                    statements + 1,
                    (_DB_NAME,),
                )
                return 0
            statements += 1
            problems = []
            if "equals" in invariant and (
                not rows or rows[0][0] != invariant["equals"]
            ):
                problems.append(
                    "expected %r got %r"
                    % (invariant["equals"], rows[0][0] if rows else None)
                )
            if "min_count" in invariant and len(rows) < int(
                invariant["min_count"]
            ):
                problems.append(
                    "rows %d < min_count %s" % (len(rows), invariant["min_count"])
                )
            if "max_count" in invariant and len(rows) > int(
                invariant["max_count"]
            ):
                problems.append(
                    "rows %d > max_count %s" % (len(rows), invariant["max_count"])
                )
            checked.append({"sql": sql, "rows": len(rows), "problems": problems})
            if problems:
                report(
                    {"applied": applied, "checked": checked},
                    "FAIL",
                    "invariant_mismatch: %s" % "; ".join(problems),
                    statements,
                    (_DB_NAME,),
                )
                return 0
    finally:
        try:
            connection.close()
        except Exception:
            pass
    report(
        {"applied": applied, "checked": len(invariants)},
        "PASS",
        "%d statement(s) ok" % statements,
        statements if statements else 1,
        (_DB_NAME,),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
