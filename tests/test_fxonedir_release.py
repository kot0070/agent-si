"""FXDIR item-3 gate: an exe hash alone no longer proves the build.

The release report must hash the portable ZIP plus the installer
setup exe plus the folder manifest (MANIFEST/HASH of the staged
folder) — never the frozen one-file exe alone. Static only: the
values come from a real generator run against this tree.
"""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "packaging" / "installer_manifest" / "gen_release_report.py"

STAGE_EXE = "dist/stage/AgentSI.exe"
PORTABLE_ZIP = "dist/AgentSI-portable-0.1.0.zip"
SETUP_EXE = "dist/AgentSI-setup-0.1.0.exe"


def _load_gen():
    spec = importlib.util.spec_from_file_location(
        "fxdir_release_report", GEN)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_release_bundle_covers_zip_setup_and_folder_exe():
    build = _load_gen()
    assert hasattr(build, "BUNDLE_PATHS"), "no BUNDLE_PATHS in generator"
    paths = list(build.BUNDLE_PATHS)
    assert STAGE_EXE in paths, f"folder exe missing: {paths}"
    assert PORTABLE_ZIP in paths, f"portable zip missing: {paths}"
    assert SETUP_EXE in paths, f"installer setup missing: {paths}"
    assert not any("sidecar" in p or "portable/app" in p for p in paths), \
        f"one-file layout leaks into the bundle: {paths}"


def test_release_report_measures_real_bundle(tmp_path):
    build = _load_gen()
    out = tmp_path / "release_report.json"
    assert build.main(["--root", str(ROOT), "--out", str(out)]) == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["exe"] == "AgentSI.exe"
    assert report["version"] == "0.1.0"
    bundle = report["bundle"]
    assert set(bundle.keys()) == set(build.BUNDLE_PATHS)
    for rel, value in bundle.items():
        assert isinstance(value, (dict, str)), (rel, value)
        if isinstance(value, dict):
            assert value.get("bytes", 0) > 0, f"empty bundle file: {rel}"
