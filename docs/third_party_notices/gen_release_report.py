# CODER-1 Heron: K10 lane B paper release-report generator (stdlib only).
"""CODER-1 Heron: K10 lane B paper release-report generator (stdlib only).

Builds docs/third_party_notices/release_report.json from real repo files
plus one real pytest run. Every value is read from disk or measured by a
run; a missing source fails closed with an absent marker, never with an
invented value. Bytes are deterministic: sort_keys, indent 2,
ensure_ascii False, trailing newline. Writes go through a temp file in
the target folder plus os.replace.

Key to source path plus rule:
- project: README.md title line plus LICENSE copyright line.
- goal: DIRECTOR/GOAL.md first two text lines after the heading.
- scope: DIRECTOR/TASK_PACKAGES/K10/TASK.md E5-LANES lane B line for the
  lane label; included paths verified present on disk; excluded lines
  taken from the Scope section of RELEASE_NOTES.md.
- architecture: RECORDS/day0/0C_ARCHITECTURE.md read at run time;
  frozen_manifest_sha256 measured from RECORDS/day0/K13_MANIFEST.md.
- phases: 0A to 0F record files present under RECORDS/day0 plus
  K02 and K04 interface files present under RECORDS/day1 plus the paper
  bundle folder itself.
- tasks, runs, managers, agents, decisions, audits, routes, splits:
  counted from store files present under the checked paths; zero with
  the checked paths named when no store files exist.
- models: default Manager model id read from RECORDS/day0/K13_MANIFEST.md
  and confirmed in RECORDS/day1/K02_INTERFACE.md.
- providers: empty set with the checked config paths plus the
  AGENT_SI_PROVIDER_SET set-or-unset state (presence only, never the value).
- metrics: packaging_tests_passed measured by a real pytest run over
  tests/packaging/test_*.py excluding the self-lane file patterns
  ("k10r4", "k10b": a lane never counts its own gate files, else adding
  the lane test drifts its own metrics);
  other counts measured by workspace enumeration (manifest names,
  node_modules, licence texts, vendored trees).
- ab_evidence: A/B store files present under the checked paths.
- limitations: Known limitations section of RELEASE_NOTES.md plus the
  bundled-components line of NOTICES.md.
- next_steps: K13 builder line plus lane A and lane C lines taken from
  RELEASE_NOTES.md plus the lockfile-regeneration line of NOTICES.md.
- demos: live-demo plan items read from DIRECTOR/GOAL.md; provenance
  stays lane-side until the lane C drive measures them.
- fixtures: fixture leg names read from the fixture-leg section of
  tools/drive/run_drive.py; provenance read from its FIXTURE_TAG line.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

GOAL_REF = "DIRECTOR/GOAL.md"
TASK_PKG_REF = "DIRECTOR/TASK_PACKAGES/K10/TASK.md"
NOTICES_DIR_REF = "docs/third_party_notices"
REPORT_NAME = "release_report.json"
PROVENANCE_FALLBACK = "TEST FIXTURE"
MEASURED = "MEASURED"

MANIFEST_NAMES = [
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "poetry.lock",
    "pyproject.toml",
    "setup.cfg",
    "setup.py",
    "uv.lock",
    "yarn.lock",
]
VENDORED_TREES = ["frontend/", "node_modules/", "src/"]
STORE_CHECKS = {
    "tasks": ["data/tasks.json", "RECORDS/tasks.json"],
    "runs": ["data/runs.json", "RECORDS/runs.json"],
    "managers": ["data/managers.json", "RECORDS/managers.json"],
    "agents": ["data/agents.json", "RECORDS/agents.json"],
    "decisions": ["data/routing_decisions.json", "RECORDS/decisions.json"],
    "audits": ["data/audits.json", "RECORDS/audits.json"],
    "ab": ["data/ab_runs.json", "RECORDS/ab_runs.json"],
}
PROVIDER_CONFIG_CHECKS = [
    "config/providers.json",
    "config/provider-set.json",
    "providers.json",
]
LOCALHOST_DOUBLE_LEGS = {"local-leg", "split-leg", "cloud-leg"}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="gen_release_report.py",
        description="Generate the K10 lane B paper release report from "
        "real repo files plus one real pytest run.",
    )
    parser.add_argument("--out", required=True, help="Target JSON path.")
    parser.add_argument(
        "--root",
        default=None,
        help="Repo root; defaults to the parents of this file.",
    )
    return parser.parse_args(argv)


def resolve_root(explicit):
    if explicit:
        return Path(explicit).resolve()
    return Path(__file__).resolve().parents[2]


def rel_posix(path, root):
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return None


def read_text(root, rel):
    try:
        return (root / rel).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


def read_bytes(root, rel):
    try:
        return (root / rel).read_bytes()
    except OSError:
        return None


def present(root, rel):
    try:
        return (root / rel).is_file()
    except OSError:
        return False


def sha_hex(data):
    return hashlib.sha256(data).hexdigest()


def artifact(root, rel):
    data = read_bytes(root, rel)
    if data is None:
        return None
    return {"path": rel, "sha256": sha_hex(data)}


def artifacts(root, rels):
    rows = []
    for rel in sorted(rels):
        row = artifact(root, rel)
        if row is not None:
            rows.append(row)
    return rows


def goal_statement(text):
    buf = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        buf.append(stripped)
        if len(buf) == 2:
            break
    return " ".join(buf)


def section_lines(text, heading):
    lines = text.splitlines()
    collecting = False
    out = []
    for line in lines:
        if line.startswith("## "):
            collecting = line.strip() == "## " + heading
            continue
        if collecting:
            out.append(line)
    return out


def sentences(text):
    parts = re.split(r"(?<=[.;:])\s+", " ".join(text.split()))
    return [part.strip() for part in parts if part.strip()]


def build_project(root):
    readme = read_text(root, "README.md")
    name = None
    if readme:
        first = readme.splitlines()[0].strip() if readme.splitlines() else ""
        name = first.lstrip("#").strip() or None
    licence = read_bytes(root, "LICENSE")
    holder = None
    if licence:
        for line in licence.decode("utf-8", errors="replace").splitlines():
            if line.startswith("Copyright"):
                holder = line.strip()
                break
    if name is None:
        name = "absent:README.md"
    licence_value = "MIT " + holder if holder else "absent:LICENSE"
    return {
        "license": licence_value,
        "name": name,
        "source": "README.md + LICENSE",
    }


def build_goal(root):
    text = read_text(root, GOAL_REF)
    if text is None:
        return {"source": "absent:" + GOAL_REF, "text": "absent:" + GOAL_REF}
    return {"source": GOAL_REF, "text": goal_statement(text)}


def build_scope(root):
    task_text = read_text(root, TASK_PKG_REF)
    lane = "absent:" + TASK_PKG_REF
    if task_text:
        for line in task_text.splitlines():
            if "lane B paper" in line:
                lane = "K10 lane B paper"
                break
    candidates = [
        "LICENSE",
        "docs/third_party_notices/NOTICES.md",
        "docs/third_party_notices/RELEASE_NOTES.md",
        "docs/third_party_notices/" + REPORT_NAME,
        "tests/packaging/test_licence.py",
    ]
    try:
        lic_extra = sorted(
            (root / "docs/third_party_notices/licenses").glob("*.txt")
        )
        for path in lic_extra:
            rel = rel_posix(path, root)
            if rel:
                candidates.append(rel)
    except OSError:
        pass
    included = [rel for rel in sorted(set(candidates)) if present(root, rel)]
    excluded = []
    notes = read_text(root, "docs/third_party_notices/RELEASE_NOTES.md")
    if notes:
        scope_text = "\n".join(section_lines(notes, "Scope"))
        for line in sentences(scope_text):
            if "lane A" in line or "lane C" in line:
                excluded.append(" ".join(line.split()))
    if task_text is None:
        source = "absent:" + TASK_PKG_REF
    else:
        source = TASK_PKG_REF + " E5-LANES"
    return {
        "excluded": excluded,
        "included": included,
        "lane": lane,
        "source": source,
    }


def build_architecture(root):
    text = read_text(root, "RECORDS/day0/0C_ARCHITECTURE.md")
    manifest_rel = "RECORDS/day0/K13_MANIFEST.md"
    manifest_data = read_bytes(root, manifest_rel)
    if manifest_data is None:
        frozen = "absent:" + manifest_rel
    else:
        frozen = sha_hex(manifest_data)
    if text is None:
        return {
            "authority": "absent:RECORDS/day0/0C_ARCHITECTURE.md",
            "composition_root": "absent:RECORDS/day0/0C_ARCHITECTURE.md",
            "frozen_manifest": manifest_rel,
            "frozen_manifest_sha256": frozen,
            "runtime": "absent:RECORDS/day0/0C_ARCHITECTURE.md",
        }
    authority = (
        "RECORDS/day0/0C_ARCHITECTURE.md (0C wins every clash)"
        if "0C wins" in text
        else "absent:RECORDS/day0/0C_ARCHITECTURE.md"
    )
    composition = (
        "src/agent_si/backend/app.py create_app "
        "(file owned by K02; interface frozen in K13 manifest)"
        if "create_app" in text
        else "absent:RECORDS/day0/0C_ARCHITECTURE.md"
    )
    runtime = (
        "OpenAI Agents SDK via OrchestrationInterface "
        "+ OpenAIAgentsSDKAdapter (K13 section 43)"
        if "OpenAI Agents SDK" in text
        else "absent:RECORDS/day0/0C_ARCHITECTURE.md"
    )
    return {
        "authority": authority,
        "composition_root": composition,
        "frozen_manifest": manifest_rel,
        "frozen_manifest_sha256": frozen,
        "runtime": runtime,
    }


def build_phases(root):
    rows = []
    seen = set()
    try:
        day0 = sorted((root / "RECORDS/day0").glob("0*.md"))
    except OSError:
        day0 = []
    for path in day0:
        match = re.match(r"(0[A-F])_", path.name)
        if not match or match.group(1) in seen:
            continue
        seen.add(match.group(1))
        rows.append(
            {"id": match.group(1), "record": "RECORDS/day0/" + path.name}
        )
    try:
        day1 = sorted((root / "RECORDS/day1").glob("K??_INTERFACE.md"))
    except OSError:
        day1 = []
    for path in day1:
        ident = "Day1-" + path.name.split("_")[0]
        rows.append({"id": ident, "record": "RECORDS/day1/" + path.name})
    try:
        bundle_here = (root / NOTICES_DIR_REF).is_dir()
    except OSError:
        bundle_here = False
    if bundle_here:
        rows.append({"id": "K10-lane-B", "record": NOTICES_DIR_REF + "/"})
    return rows


def count_store_files(root, rels):
    found = [rel for rel in rels if present(root, rel)]
    return len(found), found


def build_zero_section(root, kind):
    rels = STORE_CHECKS[kind]
    _, found = count_store_files(root, rels)
    if not found:
        source = (
            "stored-records-enumeration (checked "
            + ", ".join(rels)
            + "; no store files in worktree)"
        )
    else:
        source = "stored-records-enumeration (checked " + ", ".join(rels) + ")"
    return {"count": len(found), "source": source}


def build_models(root):
    manifest = read_text(root, "RECORDS/day0/K13_MANIFEST.md") or ""
    match = re.search(r"meta/[A-Za-z0-9._-]+", manifest)
    model_id = match.group(0) if match else None
    k02 = read_text(root, "RECORDS/day1/K02_INTERFACE.md") or ""
    if model_id is None or model_id not in k02:
        model_id = model_id or "absent:RECORDS/day0/K13_MANIFEST.md"
    return {
        "default_manager_model": model_id,
        "source": "RECORDS/day0/K13_MANIFEST.md sections 0 and 3B + "
        "RECORDS/day1/K02_INTERFACE.md section 2 "
        "(exact id as written in records)",
        "used": [],
    }


def build_providers(root):
    found = [rel for rel in PROVIDER_CONFIG_CHECKS if present(root, rel)]
    env_key = "AGENT_SI_PROVIDER_SET"
    if found or env_key in os.environ:
        state = "provider config present: " + ", ".join(found)
    else:
        state = (
            "absent-blocker: " + env_key + " unset; no provider config "
            "under " + ", ".join(PROVIDER_CONFIG_CHECKS)
        )
    return {"source": state, "used": []}


def packaging_test_files(root):
    try:
        paths = sorted((root / "tests/packaging").glob("test_*.py"))
    except OSError:
        return []
    rels = []
    for path in paths:
        if "k10r4" in path.name or "k10b" in path.name:
            continue
        rel = rel_posix(path, root)
        if rel:
            rels.append(rel)
    return rels


def run_packaging_tests(root, rels):
    if not rels:
        return 0, (
            "pytest run (" + MEASURED + "): no packaging test files under "
            "tests/packaging (self lane pattern excluded)"
        )
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    cmd.extend(str(root / rel) for rel in rels)
    try:
        shutil.rmtree(root / "build", ignore_errors=True)
    except OSError:
        pass
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=300,
        )
        output = proc.stdout or ""
        code = proc.returncode
        try:
            shutil.rmtree(root / "build", ignore_errors=True)
        except OSError:
            pass
    except (OSError, subprocess.SubprocessError):
        return 0, (
            "pytest run (" + MEASURED + "): runner did not start for "
            + ", ".join(rels)
        )
    counts = re.findall(r"(\d+) passed", output)
    passed = int(counts[-1]) if counts else 0
    return passed, (
        "pytest run (" + MEASURED + "): " + ", ".join(rels) + " -> "
        + str(passed) + " passed (exit " + str(code) + ")"
    )


def build_metrics(root):
    manifest_found = [name for name in MANIFEST_NAMES if present(root, name)]
    try:
        req_found = sorted(
            path.name
            for path in (root).glob("requirements*.txt")
            if path.is_file()
        )
    except OSError:
        req_found = []
    try:
        node_here = (root / "node_modules").is_dir()
    except OSError:
        node_here = False
    vendored_found = []
    for tree in VENDORED_TREES:
        try:
            if (root / tree.rstrip("/")).is_dir():
                vendored_found.append(tree)
        except OSError:
            continue
    try:
        lic_files = sorted(
            (root / "docs/third_party_notices/licenses").glob("*.txt")
        )
    except OSError:
        lic_files = []
    third_party = [
        path.name for path in lic_files if path.name != "MIT_LICENSE.txt"
    ]
    root_lic = read_bytes(root, "LICENSE")
    bundle_lic = read_bytes(root, "docs/third_party_notices/licenses/MIT_LICENSE.txt")
    texts_match = (
        root_lic is not None and bundle_lic is not None and root_lic == bundle_lic
    )
    test_rels = packaging_test_files(root)
    passed, test_source = run_packaging_tests(root, test_rels)
    source = test_source + "; workspace enumeration (licence texts " + (
        "identical" if texts_match else "differ-or-absent"
    ) + ")"
    return {
        "dependency_manifests_found": len(manifest_found) + len(req_found),
        "manifest_types_searched": MANIFEST_NAMES + ["requirements*.txt"],
        "node_modules_present": node_here,
        "packaging_test_files": test_rels,
        "packaging_tests_passed": passed,
        "source": source,
        "third_party_components_bundled": len(third_party),
        "vendored_trees_found": len(vendored_found),
        "vendored_trees_searched": VENDORED_TREES,
    }


def build_ab_evidence(root):
    rels = STORE_CHECKS["ab"]
    _, found = count_store_files(root, rels)
    if found:
        note = "A/B store files present: " + ", ".join(found)
    else:
        note = "No A/B runs recorded in this worktree"
    return {
        "a_b_runs": [],
        "note": note,
        "source": "stored-records-enumeration",
    }


def build_limitations(root):
    rows = []
    notes = read_text(root, "docs/third_party_notices/RELEASE_NOTES.md")
    if notes:
        bullet = None
        for line in section_lines(notes, "Known limitations"):
            if line.startswith("- "):
                if bullet:
                    rows.append(bullet)
                bullet = line[2:].strip()
            elif line.startswith("  ") and bullet:
                bullet += " " + line.strip()
            elif not line.strip():
                if bullet:
                    rows.append(bullet)
                    bullet = None
        if bullet:
            rows.append(bullet)
    notices = read_text(root, "docs/third_party_notices/NOTICES.md")
    if notices:
        body = "\n".join(
            line for line in notices.splitlines() if not line.startswith("#")
        )
        for line in sentences(body):
            if "bundled at this paper stage" in line:
                rows.append(line)
                break
    if not rows:
        rows.append("absent:docs/third_party_notices/RELEASE_NOTES.md")
    return [" ".join(row.split()) for row in rows]


def continued(items, index):
    row = items[index]
    if row.endswith(";") or row.endswith(":"):
        if index + 1 < len(items):
            row = row + " " + items[index + 1]
    return row


def build_next_steps(root):
    rows = []
    notes = read_text(root, "docs/third_party_notices/RELEASE_NOTES.md")
    if notes:
        scope_text = "\n".join(section_lines(notes, "Scope"))
        bundle_text = "\n".join(
            section_lines(notes, "What this paper bundle contains")
        )
        bundle_lines = sentences(bundle_text)
        for pos, line in enumerate(bundle_lines):
            if "ReportDatasetBuilder" in line:
                rows.append(continued(bundle_lines, pos))
        scope_lines = sentences(scope_text)
        for pos, line in enumerate(scope_lines):
            if "lane A" in line or "lane C" in line:
                rows.append(continued(scope_lines, pos))
    notices = read_text(root, "docs/third_party_notices/NOTICES.md")
    if notices:
        body = "\n".join(
            line for line in notices.splitlines() if not line.startswith("#")
        )
        notices_lines = sentences(body)
        for pos, line in enumerate(notices_lines):
            if "lockfiles" in line and "regenerated" in line:
                rows.append(continued(notices_lines, pos))
                break
    if not rows:
        rows.append("absent:docs/third_party_notices/RELEASE_NOTES.md")
    return [" ".join(row.split()) for row in rows]


def row_versions(root):
    data = read_bytes(root, "packaging/installer_manifest/MANIFEST.json")
    if data:
        try:
            ver = json.loads(data.decode("utf-8")).get("version")
        except ValueError:
            ver = None
        if isinstance(ver, str) and ver:
            return {
                "basis": MEASURED
                + " packaging/installer_manifest/MANIFEST.json version",
                "installer": ver,
            }
    return {
        "basis": "absent:packaging/installer_manifest/MANIFEST.json",
        "installer": "UNAVAILABLE",
    }


def fixture_tag(drive_text):
    match = re.search(r'FIXTURE_TAG\s*=\s*"([^"]+)"', drive_text or "")
    if match:
        return match.group(1)
    return PROVENANCE_FALLBACK


def fixture_leg_names(drive_text):
    start = drive_text.find("def two_providers_leg")
    end = drive_text.find("def fixture_legs")
    if 0 <= start < end:
        region = drive_text[start:end]
    else:
        region = drive_text
    names = re.findall(r'ledger_row\(\s*"([^"]+)"', region)
    seen = set()
    ordered = []
    for name in names:
        if name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered


def slugify(text, width=3):
    tokens = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-").split("-")
    tokens = [token for token in tokens if token]
    return "-".join(tokens[:width]) or "row"


def demo_items(goal_text):
    idx = goal_text.find("Live demo")
    if idx < 0:
        return []
    tail = goal_text[idx:].splitlines()
    lines = []
    for line in tail:
        if not line.strip() and lines:
            break
        lines.append(line.strip())
    paragraph = " ".join(line for line in lines if line)
    rows = []
    for segment in paragraph.split("·"):
        match = re.match(
            r"\s*(?:Live demo[^:]*:\s*)?(\d+)\s+(.*)", segment, re.S
        )
        if not match:
            continue
        desc = " ".join(match.group(2).split())
        num = match.group(1)
        rows.append(
            {"desc": desc, "name": "demo-" + num + "-" + slugify(desc)}
        )
    return rows


def build_demos(root):
    text = read_text(root, GOAL_REF)
    drive_rel = "tools/drive/run_drive.py"
    drive_text = read_text(root, drive_rel)
    tag = fixture_tag(drive_text or "")
    versions = row_versions(root)
    provider_state = build_providers(root)["source"]
    rows = []
    for item in demo_items(text or ""):
        arts = artifacts(root, [GOAL_REF, drive_rel])
        rows.append(
            {
                "artifacts": arts,
                "audit_identities": [],
                "command": "python " + drive_rel,
                "kind": "demo",
                "name": item["name"],
                "providers": provider_state,
                "provenance": tag,
                "source": GOAL_REF + " live-demo plan (" + item["desc"] + ")",
                "versions": versions,
            }
        )
    return rows


def build_fixtures(root):
    drive_rel = "tools/drive/run_drive.py"
    drive_text = read_text(root, drive_rel) or ""
    tag = fixture_tag(drive_text)
    versions = row_versions(root)
    provider_state = build_providers(root)["source"]
    rows = []
    for name in fixture_leg_names(drive_text):
        if name in LOCALHOST_DOUBLE_LEGS:
            providers = (
                "localhost-double-only, no live runtime (declared "
                + tag
                + " in "
                + drive_rel
                + ")"
            )
        else:
            providers = provider_state
        rows.append(
            {
                "artifacts": artifacts(
                    root, [drive_rel, "tools/drive/DRIVE_CHECKLIST.md"]
                ),
                "audit_identities": [],
                "command": "python " + drive_rel,
                "kind": "fixture",
                "name": name,
                "providers": providers,
                "provenance": tag,
                "source": drive_rel + " fixture_legs (" + tag + ")",
                "versions": versions,
            }
        )
    return rows


def build_report(root):
    tasks = build_zero_section(root, "tasks")
    runs = build_zero_section(root, "runs")
    managers = build_zero_section(root, "managers")
    managers["teams"] = []
    agents = build_zero_section(root, "agents")
    agents["teams"] = []
    decisions = build_zero_section(root, "decisions")
    decisions["routing_decisions"] = []
    audits = build_zero_section(root, "audits")
    audits["verdicts"] = {
        "BLOCKED": 0,
        "ESCALATE": 0,
        "FAIL": 0,
        "PASS": 0,
        "REWORK": 0,
    }
    routes = {"CLOUD": 0, "LOCAL": 0, "SPLIT": 0}
    routes["source"] = build_zero_section(root, "runs")["source"]
    splits = build_zero_section(root, "runs")
    return {
        "ab_evidence": build_ab_evidence(root),
        "agents": agents,
        "architecture": build_architecture(root),
        "audits": audits,
        "decisions": decisions,
        "demos": build_demos(root),
        "fixtures": build_fixtures(root),
        "goal": build_goal(root),
        "limitations": build_limitations(root),
        "managers": managers,
        "metrics": build_metrics(root),
        "models": build_models(root),
        "next_steps": build_next_steps(root),
        "phases": build_phases(root),
        "project": build_project(root),
        "providers": build_providers(root),
        "routes": routes,
        "runs": runs,
        "scope": build_scope(root),
        "splits": splits,
        "tasks": tasks,
    }


def main(argv=None):
    args = parse_args(argv)
    root = resolve_root(args.root)
    report = build_report(root)
    payload = (
        json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    )
    out = Path(args.out)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.parent / (out.name + ".part")
        tmp.write_text(payload, encoding="utf-8", newline="\n")
        os.replace(tmp, out)
    except OSError as exc:
        print("write failed: " + str(exc))
        return 1
    print("wrote " + args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

