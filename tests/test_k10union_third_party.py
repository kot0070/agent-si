"""K10P1UNION single proof: third-party notices + licence + installer ships them.

(a) docs/third_party_notices/NOTICES.md names every runtime dep from
    pyproject dependencies plus frontend package.json dependencies, each
    with a licence id and the manifest-pinned version.
(b) licenses/MIT_LICENSE.txt and root LICENSE carry the required
    copyright line.
(c) packaging/installer/build.py ENTRIES ships LICENSE, NOTICES.md and
    MIT_LICENSE.txt, and a real build_zip artifact holds all of them.
"""

import importlib.util
import json
import re
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTICES = ROOT / "docs/third_party_notices/NOTICES.md"
MIT_LICENSE = ROOT / "licenses/MIT_LICENSE.txt"
ROOT_LICENSE = ROOT / "LICENSE"
COPYRIGHT_LINE = "Copyright (c) 2026 Ivan Soprun"

# Licence ids verified read-only from the local environment before the
# union port (venv dist-info METADATA License-Expression fields and
# frontend/node_modules/*/package.json license fields).
EXPECTED_LICENCES = {
    "fastapi": "MIT",
    "openai-agents": "MIT",
    "pywebview": "BSD 3-Clause",
    "uvicorn": "BSD 3-Clause",
    "react": "MIT",
    "react-router-dom": "MIT",
    "zod": "MIT",
}

REQUIRED_ZIP_MEMBERS = {
    "LICENSE",
    "docs/third_party_notices/NOTICES.md",
    "licenses/MIT_LICENSE.txt",
}


def _pyproject_runtime_deps():
    with open(ROOT / "pyproject.toml", "rb") as handle:
        project = tomllib.load(handle)["project"]
    deps = {}
    for req in project["dependencies"]:
        name = re.split(r"[<>=!~\s\[]", req, maxsplit=1)[0].strip()
        pin = req[len(name):].strip()
        version = pin.lstrip("=").strip() if pin.startswith("==") else pin
        deps[name] = version
    return deps


def _frontend_runtime_deps():
    package = json.loads(
        (ROOT / "frontend/package.json").read_text(encoding="utf-8"))
    return dict(package["dependencies"])


def _notices_table(text):
    rows = {}
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 4:
            continue
        if set(cells) == {"component"} or set(cells) == {"-"}:
            continue
        if cells[0] in ("component", "(none)", ""):
            continue
        if re.fullmatch(r"-+", cells[0]):
            continue
        rows[cells[0]] = {"version": cells[1], "license": cells[2],
                          "source": cells[3]}
    return rows


def _load_build_module():
    path = ROOT / "packaging/installer/build.py"
    spec = importlib.util.spec_from_file_location("k10union_build", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_notices_names_every_runtime_dep_with_licence_id():
    text = NOTICES.read_text(encoding="utf-8")
    table = _notices_table(text)
    expected = _pyproject_runtime_deps()
    expected.update(_frontend_runtime_deps())
    assert set(expected) <= set(table), (
        "NOTICES.md misses runtime deps: "
        + ", ".join(sorted(set(expected) - set(table))))
    for name, version in expected.items():
        row = table[name]
        assert row["license"] == EXPECTED_LICENCES[name], (
            name + ": licence " + row["license"] + " != "
            + EXPECTED_LICENCES[name])
        assert row["version"] == version, (
            name + ": version " + row["version"] + " != manifest " + version)


def test_licence_texts_carry_copyright_line():
    for path in (MIT_LICENSE, ROOT_LICENSE):
        lines = path.read_text(encoding="utf-8").splitlines()
        assert COPYRIGHT_LINE in lines, str(path) + " misses copyright line"


def test_installer_entries_ship_licence_and_notices():
    build = _load_build_module()
    shipped = set(build.ENTRIES.values())
    assert shipped >= REQUIRED_ZIP_MEMBERS, (
        "ENTRIES misses: "
        + ", ".join(sorted(REQUIRED_ZIP_MEMBERS - shipped)))
    # FXSCRUB R5: lane package reports stay repo-only, never in the
    # shipped bundle (no shipped page links docs/reports/*).
    assert not [e for e in shipped if e.startswith("docs/reports/")], (
        "ENTRIES must not ship docs/reports/")
    _status, missing = build.check_entries(ROOT)
    assert not missing, "installer entries missing on disk: " + str(missing)
    out_dir = ROOT / "_task/K10P1UNION/tmp"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "k10union_build.zip"
    if out_path.is_file():
        out_path.unlink()
    build.build_zip(ROOT, out_path)
    with zipfile.ZipFile(out_path) as archive:
        members = set(archive.namelist())
    assert members >= REQUIRED_ZIP_MEMBERS, (
        "zip misses: " + ", ".join(sorted(REQUIRED_ZIP_MEMBERS - members)))
    assert not [m for m in members if m.startswith("docs/reports/")], (
        "zip must not ship docs/reports/")
