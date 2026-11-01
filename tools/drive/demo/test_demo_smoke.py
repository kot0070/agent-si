"""Pytest smoke test for the C2DEMO runnable demo pack.

Lane A (coder B). Stdlib + pytest + subprocess only; no product imports.
Works before AND after lane B lands its scripts via dynamic discovery.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

EXPECTED_MINIMUM = 4
PER_SCRIPT_TIMEOUT_S = 120

EXPECTED_KEYS = frozenset(
    {
        "run_id",
        "demo",
        "model",
        "endpoint",
        "fixture_class",
        "attempts",
        "verification",
        "audit",
        "watcher_rule",
        "exit_code",
        "cause",
    }
)

RUN_ID_RE = re.compile(r"^run_id: DEMO-\d+-\d{8}-\d+$")
ARTIFACT_RE = re.compile(r"^artifact: .+$")


def _repo_root():
    return Path(__file__).resolve().parents[3]


def _demo_dir():
    return _repo_root() / "tools" / "drive" / "demo"


def _discover_demo_scripts():
    d = _demo_dir()
    if not d.is_dir():
        return []
    scripts = [
        p
        for p in sorted(d.glob("demo_*.py"))
        if p.is_file() and not p.name.startswith("test_")
    ]
    return scripts


def _verdict_of(node):
    if isinstance(node, dict):
        return node.get("verdict")
    return node


def _run_one_script(script, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    root = _repo_root()
    proc = subprocess.run(
        [sys.executable, str(script), "--out", str(out_dir)],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=PER_SCRIPT_TIMEOUT_S,
    )
    assert proc.returncode == 0, (
        f"{script.name}: exit code {proc.returncode} != 0\n"
        f"stdout: {proc.stdout!r}\n"
        f"stderr: {proc.stderr!r}"
    )
    lines = proc.stdout.splitlines()
    assert len(lines) == 2, (
        f"{script.name}: expected exactly 2 stdout lines, got {len(lines)}: "
        f"{proc.stdout!r}"
    )
    assert RUN_ID_RE.match(lines[0]), (
        f"{script.name}: line 1 does not match "
        f"^run_id: DEMO-<n>-<YYYYMMDD>-<n>$: {lines[0]!r}"
    )
    assert ARTIFACT_RE.match(lines[1]), (
        f"{script.name}: line 2 does not match ^artifact: <path>$: {lines[1]!r}"
    )
    run_id = lines[0].split("run_id:", 1)[1].strip()
    artifact_raw = lines[1].split("artifact:", 1)[1].strip()
    artifact_path = Path(artifact_raw)
    if not artifact_path.is_absolute():
        artifact_path = root / artifact_path
    assert artifact_path.is_file(), (
        f"{script.name}: artifact path does not exist: {artifact_raw!r} "
        f"(resolved {artifact_path})"
    )
    data = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), (
        f"{script.name}: artifact JSON is not an object: {type(data)}"
    )
    assert set(data.keys()) == set(EXPECTED_KEYS), (
        f"{script.name}: artifact keys {sorted(data.keys())} != "
        f"expected {sorted(EXPECTED_KEYS)} "
        f"(missing={sorted(set(EXPECTED_KEYS) - set(data.keys()))} "
        f"extra={sorted(set(data.keys()) - set(EXPECTED_KEYS))})"
    )
    assert isinstance(data["attempts"], list), (
        f"{script.name}: artifact 'attempts' is not a list: "
        f"{data['attempts']!r}"
    )
    assert data["run_id"] == run_id, (
        f"{script.name}: artifact run_id {data['run_id']!r} != "
        f"printed run_id {run_id!r}"
    )
    return run_id, artifact_path, data


def test_pack_complete():
    scripts = _discover_demo_scripts()
    if len(scripts) < EXPECTED_MINIMUM:
        missing = EXPECTED_MINIMUM - len(scripts)
        present = [p.name for p in scripts] or ["<none>"]
        pytest.fail(
            "file-not-found (FileNotFoundError): demo pack incomplete: "
            f"found {len(scripts)} demo script(s), expected minimum "
            f"{EXPECTED_MINIMUM}; missing {missing} script slot(s); "
            f"present: {', '.join(present)}",
            pytrace=False,
        )


def test_demo_scripts_conform(tmp_path):
    scripts = _discover_demo_scripts()
    if not scripts:
        pytest.skip("no demo scripts discovered yet; see test_pack_complete")
    out_dir = tmp_path / "artifacts"
    for script in scripts:
        _run_one_script(script, out_dir)


def test_forced_failure_no_false_pass(tmp_path):
    scripts = _discover_demo_scripts()
    if len(scripts) < EXPECTED_MINIMUM:
        pytest.skip(
            "forced-failure script has not landed yet: pack incomplete "
            f"(found {len(scripts)}, expected minimum {EXPECTED_MINIMUM})"
        )
    out_dir = tmp_path / "artifacts"
    produced = []
    for script in scripts:
        _, artifact_path, data = _run_one_script(script, out_dir)
        produced.append((script, artifact_path, data))
    caused = [(s, p, d) for (s, p, d) in produced if d.get("cause") is not None]
    if not caused:
        names = ", ".join(s.name for (s, _, _) in produced)
        pytest.fail(
            "full pack landed but no leg with non-null cause found; "
            f"checked: {names}",
            pytrace=False,
        )
    for script, artifact_path, data in caused:
        demo = data.get("demo", script.name)
        audit_verdict = _verdict_of(data.get("audit"))
        verification_verdict = _verdict_of(data.get("verification"))
        assert audit_verdict != "PASS", (
            f"false PASS: demo={demo!r} script={script.name} "
            f"artifact={artifact_path} audit.verdict={audit_verdict!r} "
            f"verification.verdict={verification_verdict!r} "
            f"cause={data.get('cause')!r}"
        )
        assert verification_verdict != "PASS", (
            f"false PASS: demo={demo!r} script={script.name} "
            f"artifact={artifact_path} verification.verdict="
            f"{verification_verdict!r} audit.verdict={audit_verdict!r} "
            f"cause={data.get('cause')!r}"
        )
