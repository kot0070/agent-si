"""K05 M3 STEP2: 0390 fingerprint-index migration test (stdlib sqlite3 only)."""
from __future__ import annotations

import pathlib
import sqlite3
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))

_MIGRATION = (
    pathlib.Path(__file__).resolve().parents[2]
    / "src"
    / "agent_si"
    / "adapters"
    / "sqlite"
    / "migration_scripts"
    / "0390_localbench_evidence.sql"
)

#: Minimal K13 capability-evidence shape: the table plus the fingerprint
#: column the 0390 index targets (owner DDL stays read-only elsewhere).
_K13_CAPABILITY_EVIDENCE_DDL = """
CREATE TABLE IF NOT EXISTS capability_evidence_records (
    id INTEGER PRIMARY KEY,
    model_id TEXT NOT NULL,
    task_class TEXT NOT NULL,
    environment_fingerprint TEXT,
    evidence_ref TEXT NOT NULL
)
"""

#: The K05 read-time fingerprint lookup the index must serve.
_FINGERPRINT_LOOKUP = (
    "SELECT id, model_id, task_class FROM capability_evidence_records "
    "WHERE environment_fingerprint = ?"
)


def _fresh_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(_K13_CAPABILITY_EVIDENCE_DDL)
    return conn


def _apply(conn: sqlite3.Connection) -> None:
    conn.executescript(_MIGRATION.read_text(encoding="utf-8"))


def _index_names(conn: sqlite3.Connection) -> list[str]:
    return [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'"
        ).fetchall()
    ]


def test_0390_applies_on_k13_schema() -> None:
    assert _MIGRATION.is_file()
    conn = _fresh_db()
    try:
        _apply(conn)
        assert "idx_capability_evidence_fingerprint" in _index_names(conn)
    finally:
        conn.close()


def test_0390_second_start_idempotent() -> None:
    conn = _fresh_db()
    try:
        _apply(conn)
        _apply(conn)
        names = _index_names(conn)
        assert names.count("idx_capability_evidence_fingerprint") == 1
    finally:
        conn.close()


def test_0390_fingerprint_lookup_uses_index() -> None:
    conn = _fresh_db()
    try:
        _apply(conn)
        conn.executemany(
            "INSERT INTO capability_evidence_records "
            "(model_id, task_class, environment_fingerprint, evidence_ref) "
            "VALUES (?, ?, ?, ?)",
            [
                (f"m-{n:04d}", "qa", f"fp-{n:04d}", f"cap:m-{n:04d}:qa:v1")
                for n in range(1000)
            ],
        )
        conn.execute("ANALYZE capability_evidence_records")
        rows = conn.execute(_FINGERPRINT_LOOKUP, ("fp-0007",)).fetchall()
        assert [row[1] for row in rows] == ["m-0007"]
        plan = "\n".join(
            str(row) for row in conn.execute(
                f"EXPLAIN QUERY PLAN {_FINGERPRINT_LOOKUP}", ("fp-0007",)
            ).fetchall()
        )
        assert "idx_capability_evidence_fingerprint" in plan
    finally:
        conn.close()
