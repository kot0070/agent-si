"""M-P4-143 competitor CLI: audit records into findings, rank them.

Reads a JSON file (or standard input with ``-``) holding a list of package
records and prints JSON to standard output. ``audit`` prints findings that
carry source and quote; ``rank`` prints the findings ordered by the rank
rules. Foreign input (unreadable file, invalid JSON, a top-level value that
is not a list, a record that is not a mapping, a missing package name, a
non-string source or quote) is reported on standard error with exit 1.
Exit 0 always means the printed JSON is the full result. Stdlib only, no
network, no providers; portable path handling, never a machine path.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from typing import Any, List, Optional

try:
    from tools.competitor.audit import audit_packages as _audit_packages
    from tools.competitor.audit import findings_to_records
    from tools.competitor.rank import rank_findings
except ImportError:
    sys.path.insert(
        0,
        os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ),
    )
    from tools.competitor.audit import audit_packages as _audit_packages
    from tools.competitor.audit import findings_to_records
    from tools.competitor.rank import rank_findings


def _read_records(path: str) -> Any:
    if path == "-":
        text = sys.stdin.read()
    else:
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
    return json.loads(text)


def _check_records(records: Any) -> list[Mapping[str, Any]]:
    if not isinstance(records, list):
        raise ValueError("input must be a JSON list of package records")
    for entry in records:
        if not isinstance(entry, Mapping):
            raise ValueError("each package record must be a JSON object")
        package = entry.get("package")
        if not isinstance(package, str) or package.strip() == "":
            raise ValueError("each package record needs a non-empty package name")
        for key in ("source", "quote"):
            if key in entry and not isinstance(entry[key], str):
                raise ValueError("record field %r must be a string" % key)
    return records


def _write_findings(findings: Any) -> int:
    sys.stdout.write(json.dumps(findings_to_records(findings), indent=2))
    sys.stdout.write("\n")
    return 0


def audit_command(path: str) -> int:
    """Audit the input records and print findings carrying source+quote."""
    try:
        records = _check_records(_read_records(path))
    except (OSError, ValueError) as exc:
        print("competitor audit: %s" % exc, file=sys.stderr)
        return 1
    return _write_findings(_audit_packages(records))


def rank_command(path: str) -> int:
    """Audit the input records and print the ranked findings."""
    try:
        records = _check_records(_read_records(path))
    except (OSError, ValueError) as exc:
        print("competitor rank: %s" % exc, file=sys.stderr)
        return 1
    return _write_findings(rank_findings(_audit_packages(records)))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="competitor",
        description="Audit competitor package records into ranked findings.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    audit = sub.add_parser(
        "audit", help="print findings carrying source and quote"
    )
    audit.add_argument("input", help="JSON file with package records ('-' for stdin)")
    rank = sub.add_parser("rank", help="print findings ordered by the rank rules")
    rank.add_argument("input", help="JSON file with package records ('-' for stdin)")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "audit":
        return audit_command(args.input)
    if args.command == "rank":
        return rank_command(args.input)
    build_parser().print_usage(sys.stderr)
    return 2
