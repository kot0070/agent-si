"""M-P4-143 served: tools/competitor CLI entry to ranked findings.

Row M-P4-143 (competitor findings source+quote ranked rules+packages) is
served through the new tools/competitor module with zero int seam
(greenfield): findings carry source+quote, the ranked list orders them by
the rank rules, and the CLI entry runs via tools/competitor/__main__.py.

Routes:
  tools/competitor/__main__.py audit
  tools/competitor/__main__.py rank
Proving tests: this file (tests/test_k10ph2e_a143_served.py).
Loopback TEST data only; no network, no installs, no mocks in product code.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.competitor import audit as audit_mod  # noqa: E402
from tools.competitor import rank as rank_mod  # noqa: E402

TAG = "tests/test_k10ph2e_a143_served.py"
ROW = "M-P4-143"
ROUTE_AUDIT = "tools/competitor/__main__.py audit"
ROUTE_RANK = "tools/competitor/__main__.py rank"
MAIN = ROOT / "tools" / "competitor" / "__main__.py"

RECORDS = [
    {"package": "pkg-b", "source": "recorded: kit plan", "quote": "verbatim line b"},
    {"package": "pkg-a", "source": "", "quote": "verbatim line a"},
    {"package": "pkg-c", "source": "recorded: kit plan", "quote": ""},
]


def run_cli(*args, cwd=None):
    return subprocess.run(
        [sys.executable, str(MAIN), *args],
        cwd=str(cwd or ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )


def write_records(tmp_path, records):
    path = tmp_path / "competitor_records.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    return path


def test_k10ph2e_a143_audit_served(tmp_path):
    """Row M-P4-143 served through tools/competitor/__main__.py audit."""
    assert ROUTE_AUDIT == "tools/competitor/__main__.py audit"
    path = write_records(tmp_path, RECORDS)
    proc = run_cli("audit", str(path))
    assert proc.returncode == 0, proc.stderr
    findings = json.loads(proc.stdout)
    assert [item["package"] for item in findings] == ["pkg-b", "pkg-a", "pkg-c"]
    for item in findings:
        for key in ("rule", "package", "source", "quote", "detail"):
            assert key in item, item
    by_package = {item["package"]: item for item in findings}
    assert by_package["pkg-b"]["rule"] == "competitor-recorded"
    assert by_package["pkg-b"]["source"] == "recorded: kit plan"
    assert by_package["pkg-b"]["quote"] == "verbatim line b"
    assert by_package["pkg-a"]["rule"] == "competitor-source-missing"
    assert by_package["pkg-c"]["rule"] == "competitor-quote-missing"
    assert findings == audit_mod.findings_to_records(
        audit_mod.audit_packages(RECORDS)
    ), findings


def test_k10ph2e_a143_rank_rules_packages_served(tmp_path):
    """Row M-P4-143 ranked list served through tools/competitor/__main__.py rank."""
    assert ROUTE_RANK == "tools/competitor/__main__.py rank"
    path = write_records(tmp_path, RECORDS)
    proc = run_cli("rank", str(path))
    assert proc.returncode == 0, proc.stderr
    ranked = json.loads(proc.stdout)
    assert [item["package"] for item in ranked] == ["pkg-a", "pkg-c", "pkg-b"]
    assert [item["rule"] for item in ranked] == [
        "competitor-source-missing",
        "competitor-quote-missing",
        "competitor-recorded",
    ]
    assert set(rank_mod.RULE_SEVERITY) == set(audit_mod.AUDIT_RULES)
    assert rank_mod.ranked_packages(ranked) == ["pkg-a", "pkg-c", "pkg-b"]
    assert rank_mod.rank_findings(list(reversed(ranked))) == ranked


def test_k10ph2e_a143_cli_entry_runs():
    """Row M-P4-143 CLI entry runs as a script and as a module."""
    script_help = run_cli("--help")
    assert script_help.returncode == 0, script_help.stderr
    assert "audit" in script_help.stdout and "rank" in script_help.stdout
    module_help = subprocess.run(
        [sys.executable, "-m", "tools.competitor", "--help"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert module_help.returncode == 0, module_help.stderr
    assert "audit" in module_help.stdout and "rank" in module_help.stdout


def test_k10ph2e_a143_empty_input_fails(tmp_path):
    """Row M-P4-143 negative probe: an empty input file still fails."""
    empty = tmp_path / "competitor_empty.json"
    empty.write_text("", encoding="utf-8")
    for command in ("audit", "rank"):
        proc = run_cli(command, str(empty))
        assert proc.returncode != 0, (command, proc.returncode, proc.stdout)


def test_k10ph2e_a143_foreign_input_fails(tmp_path):
    """Row M-P4-143 negative probe: foreign input shapes still fail."""
    cases = {
        "object": {"package": "pkg-a"},
        "text": "just a string",
        "non_mapping": ["pkg-a"],
        "missing_package": [{"source": "s", "quote": "q"}],
        "blank_package": [{"package": "  ", "source": "s", "quote": "q"}],
        "non_string_quote": [
            {"package": "pkg-a", "source": "s", "quote": 7},
        ],
    }
    for name, payload in cases.items():
        path = tmp_path / ("competitor_foreign_%s.json" % name)
        path.write_text(json.dumps(payload), encoding="utf-8")
        for command in ("audit", "rank"):
            proc = run_cli(command, str(path))
            assert proc.returncode != 0, (name, command, proc.stdout)
            assert proc.stderr.strip() != "", (name, command)
