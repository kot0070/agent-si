"""FXSETUP static gate: Inno Setup installer contract plus stage hygiene.

RED-first: fails until packaging/installer/agent_si.iss exists and
packaging/installer/build.py grows the ISCC setup step.

Covers the HD2 FXSETUP items:
1. .iss built from the exe-build stage folder (dist/stage): AppId from
   com.agentsi.app, every visible name 'Agent SI', version as the
   portable (0.1.0), publisher + copyright line as About shows them,
   LICENSE shown by the wizard, third-party notices installed,
   English + Ukrainian, PrivilegesRequired=lowest, per-user
   {localappdata}/Programs/Agent SI, Start-menu entry, optional desktop
   icon, uninstaller, run-after-install, no console. Uninstall leaves
   the user's data folder unless the user opts into deleting it.
   Fresh install starts clean: the stage scan proves no projects,
   keys, or test data ride in the payload (clean fixture PASS,
   dirty fixture FAIL).
2. build.py setup step: compiles the .iss when ISCC is found, names the
   output AgentSI-setup-<version>.exe, records its sha256 in the
   SHA256SUMS.txt next to the portable; a missing ISCC fails loud,
   never a silent skip.
"""

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ISS = ROOT / "packaging/installer/agent_si.iss"
BUILD_PY = ROOT / "packaging/installer/build.py"

APP_ID = "com.agentsi.app"
APP_NAME = "Agent SI"
APP_VERSION = "0.1.0"
PUBLISHER = "Ivan Soprun"
COPYRIGHT_LINE = "Copyright (c) 2026 Ivan Soprun"


def _read_iss():
    assert ISS.is_file(), f"installer script missing: {ISS}"
    return ISS.read_text(encoding="utf-8-sig")


def _setup_directives(text):
    """Map of [Setup] Key -> raw value (first occurrence wins)."""
    in_setup = False
    found = {}
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_setup = stripped.lower() == "[setup]"
            continue
        if not in_setup or not stripped or stripped.startswith(";"):
            continue
        if "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if key and key not in found:
            found[key] = value.strip()
    return found


def _section_names(text, section):
    """Name: values of one [section] (e.g. Icons, Tasks, Run)."""
    in_section = False
    names = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_section = stripped.lower() == f"[{section.lower()}]"
            continue
        if not in_section or not stripped or stripped.startswith(";"):
            continue
        match = re.search(r"(?:^|;\s*)Name\s*:\s*([^;]+)", stripped,
                          re.IGNORECASE)
        if match:
            names.append(match.group(1).strip().strip('"'))
    return names


def _load_build_module():
    spec = importlib.util.spec_from_file_location("fxsetup_build", BUILD_PY)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# --- item 1: installer identity -------------------------------------------

def test_iss_identity_matches_about_and_plan():
    setup = _setup_directives(_read_iss())
    assert setup.get("AppId") == APP_ID, f"AppId: {setup.get('AppId')!r}"
    assert setup.get("AppName") == APP_NAME, \
        f"AppName: {setup.get('AppName')!r}"
    assert PUBLISHER in setup.get("AppPublisher", ""), \
        f"AppPublisher: {setup.get('AppPublisher')!r}"
    assert COPYRIGHT_LINE in setup.get("AppCopyright", ""), \
        f"AppCopyright: {setup.get('AppCopyright')!r}"


def test_iss_version_is_the_portable_version():
    text = _read_iss()
    setup = _setup_directives(text)
    raw_version = setup.get("AppVersion", "")
    if raw_version.startswith("{#"):
        macro = raw_version.strip("{#}")
        define = re.search(
            r"#define\s+" + re.escape(macro) + r'\s+"([^"]+)"', text)
        assert define is not None, f"version macro {macro} undefined"
        raw_version = define.group(1)
    assert raw_version == APP_VERSION, f"AppVersion: {raw_version!r}"


def test_iss_every_visible_name_reads_agent_si():
    text = _read_iss()
    setup = _setup_directives(text)
    visible = [setup.get("AppName", ""),
               setup.get("AppVerName", setup.get("AppName", "")),
               setup.get("DefaultGroupName", "")]
    visible += _section_names(text, "Icons")
    # Tasks carry internal ids (e.g. desktopicon), not visible names;
    # their Description renders from the standard messages.
    assert visible, "no visible names found in .iss"
    for name in visible:
        assert APP_NAME in name, f"visible name misses '{APP_NAME}': {name!r}"


def test_iss_license_shown_and_notices_installed():
    text = _read_iss()
    setup = _setup_directives(text)
    license_file = setup.get("LicenseFile", "")
    assert license_file, "LicenseFile directive missing"
    resolved = (ISS.parent / license_file).resolve()
    assert resolved.is_file(), f"LicenseFile missing: {resolved}"
    assert "Copyright (c) 2026 Ivan Soprun" in resolved.read_text(
        encoding="utf-8"), "LICENSE misses the copyright line"
    files_section = re.search(r"\[Files\](.*?)(?:^\[|\Z)", text,
                              re.IGNORECASE | re.MULTILINE | re.DOTALL)
    assert files_section is not None, "[Files] section missing"
    files_blob = files_section.group(1)
    assert "dist" in files_blob and "stage" in files_blob, \
        "no [Files] entry installs from the exe-build stage folder"
    assert "NOTICES.md" in files_blob, \
        "[Files] does not install the third-party notices"


# --- item 1: per-user install, languages, shortcuts, run -------------------

def test_iss_english_and_ukrainian():
    text = _read_iss()
    languages = re.search(r"\[Languages\](.*?)(?:^\[|\Z)", text,
                          re.IGNORECASE | re.MULTILINE | re.DOTALL)
    assert languages is not None, "[Languages] section missing"
    blob = languages.group(1).lower()
    assert re.search(r'name\s*:\s*"?(en|english)"?', blob), \
        "[Languages] misses English"
    assert re.search(r'name\s*:\s*"?uk(rainian)?"?', blob), \
        "[Languages] misses Ukrainian"
    assert "ukrainian.isl" in blob, \
        "[Languages] does not wire the Ukrainian messages file"


def test_iss_per_user_lowest_privilege():
    setup = _setup_directives(_read_iss())
    assert setup.get("PrivilegesRequired", "").lower() == "lowest", \
        f"PrivilegesRequired: {setup.get('PrivilegesRequired')!r}"
    dest = setup.get("DefaultDirName", "")
    assert dest.lower() == "{localappdata}\\programs\\agent si", \
        f"DefaultDirName: {dest!r}"


def test_iss_start_menu_desktop_icon_and_run_after_install():
    text = _read_iss()
    setup = _setup_directives(text)
    assert APP_NAME in setup.get("DefaultGroupName", ""), \
        "no 'Agent SI' Start-menu group"
    icons = _section_names(text, "Icons")
    assert any(n.lower().startswith("{group}") for n in icons), \
        "no Start-menu icon"
    assert any("desktop" in n.lower() for n in icons), \
        "no desktop icon entry"
    tasks = _section_names(text, "Tasks")
    desktop_tasks = [t for t in tasks if "desktop" in t.lower()]
    assert desktop_tasks, "desktop icon is not an opt-in task"
    run_section = re.search(r"\[Run\](.*?)(?:^\[|\Z)", text,
                            re.IGNORECASE | re.MULTILINE | re.DOTALL)
    assert run_section is not None, "[Run] section missing"
    run_blob = run_section.group(1)
    assert "AgentSI.exe" in run_blob, "[Run] does not start AgentSI.exe"
    assert "postinstall" in run_blob.lower(), \
        "[Run] entry is not a post-install launch"
    assert "cmd" not in run_blob.lower().split("filename")[0], \
        "[Run] must not go through a console"


# --- item 1: uninstall keeps data by default --------------------------------

def test_iss_uninstall_leaves_data_unless_user_opts_in():
    text = _read_iss()
    code = re.search(r"\[Code\](.*)\Z", text,
                     re.IGNORECASE | re.MULTILINE | re.DOTALL)
    assert code is not None, "[Code] section missing (data opt-in lives there)"
    code_blob = code.group(1)
    assert re.search(r"MsgBox\s*\(", code_blob), \
        "[Code] never asks the user about the data folder"
    uninstall = re.search(r"\[UninstallDelete\](.*?)(?:^\[|\Z)", text,
                           re.IGNORECASE | re.MULTILINE | re.DOTALL)
    assert uninstall is not None, "[UninstallDelete] section missing"
    for line in uninstall.group(1).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            continue
        if re.search(r"data", stripped, re.IGNORECASE):
            assert re.search(r"Check\s*:", stripped, re.IGNORECASE), \
                f"data deleted unconditionally: {stripped!r}"


# --- item 1: clean-stage scan on fixtures ------------------------------------

def _stage_fixture(base, dirty=False):
    # FXDIR: mirrors the real one-folder stage layout (AgentSI.exe at
    # the stage root, support files beside it).
    stage = base / "stage"
    stage.mkdir(parents=True)
    (stage / "AgentSI.exe").write_bytes(b"exe")
    (stage / "LICENSE").write_text("MIT\nCopyright (c) 2026 Ivan Soprun\n")
    notices = stage / "docs" / "third_party_notices"
    notices.mkdir(parents=True)
    (notices / "NOTICES.md").write_text("# notices\n")
    if dirty == "data-dir":
        data = stage / "data"
        data.mkdir()
        (data / "projects.db").write_text("user project rows")
    elif dirty == "key-file":
        (stage / ".env").write_text("SECRET=topsecret\n")
    elif dirty == "test-data":
        runs = stage / "runs"
        runs.mkdir()
        (runs / "test_run.json").write_text("{}")
    return stage


def test_stage_scan_clean_fixture_passes(tmp_path):
    build = _load_build_module()
    assert hasattr(build, "scan_stage_clean"), \
        "build.py has no scan_stage_clean"
    violations = build.scan_stage_clean(_stage_fixture(tmp_path))
    assert violations == [], f"clean stage flagged: {violations}"


def test_stage_scan_dirty_fixtures_fail(tmp_path):
    build = _load_build_module()
    for dirty in ("data-dir", "key-file", "test-data"):
        stage = _stage_fixture(tmp_path / dirty, dirty=dirty)
        violations = build.scan_stage_clean(stage)
        assert violations, f"dirty stage ({dirty}) passed the scan"


# --- item 2 (FXDIR): one-folder shortcuts ------------------------------------
# Owner 16:50: Start-menu entry + desktop shortcut, BOTH checked by
# default in the wizard, both named 'Agent SI' with the SI icon,
# opening AgentSI.exe in its folder with the working directory set
# to it; uninstall removes both.


def _icons_entries(text):
    section = re.search(r"\[Icons\](.*?)(?:^\[|\Z)", text,
                        re.IGNORECASE | re.MULTILINE | re.DOTALL)
    assert section is not None, "[Icons] section missing"
    entries = []
    for line in section.group(1).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            continue
        entries.append(stripped)
    return entries


def _tasks_lines(text):
    section = re.search(r"\[Tasks\](.*?)(?:^\[|\Z)", text,
                        re.IGNORECASE | re.MULTILINE | re.DOTALL)
    assert section is not None, "[Tasks] section missing"
    lines = []
    for line in section.group(1).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            continue
        lines.append(stripped)
    return lines


def test_iss_shortcuts_open_exe_at_folder_root():
    entries = _icons_entries(_read_iss())
    targets = [e for e in entries if "AgentSI.exe" in e]
    assert len(targets) >= 2, \
        f"need Start-menu + desktop AgentSI.exe icons, found: {entries}"
    for entry in targets:
        assert re.search(r'Filename\s*:\s*"\{app\}\\AgentSI\.exe"', entry), \
            f"shortcut not at the folder root: {entry!r}"
        assert re.search(r'WorkingDir\s*:\s*"\{app\}"', entry,
                         re.IGNORECASE), \
            f"shortcut misses WorkingDir {{app}}: {entry!r}"


def test_iss_desktop_shortcut_checked_by_default():
    lines = _tasks_lines(_read_iss())
    desktop = [ln for ln in lines if "desktopicon" in ln.lower()]
    assert desktop, "no desktopicon task in [Tasks]"
    for line in desktop:
        assert "unchecked" not in line.lower(), \
            f"desktop shortcut not checked by default: {line!r}"


def test_iss_uninstall_display_icon_at_folder_root():
    setup = _setup_directives(_read_iss())
    icon = setup.get("UninstallDisplayIcon", "")
    assert icon == "{app}\\AgentSI.exe", \
        f"UninstallDisplayIcon not at the folder root: {icon!r}"


# --- item 2: ISCC step -------------------------------------------------------

def test_build_missing_iscc_fails_loud_not_silent(tmp_path, monkeypatch,
                                                  capsys):
    build = _load_build_module()
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "pf"))
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path / "pf86"))
    monkeypatch.setattr(build.shutil, "which", lambda *a, **k: None)
    assert build.find_iscc() is None, "ISCC unexpectedly found"
    rc = build.main(["--setup"])
    assert rc != 0, "--setup passed without ISCC: silent skip"
    out = capsys.readouterr()
    assert "ISCC" in (out.out + out.err), \
        "missing-ISCC failure does not name ISCC"


def test_build_records_setup_hash_next_to_portable(tmp_path):
    build = _load_build_module()
    assert hasattr(build, "record_setup_hash"), \
        "build.py has no record_setup_hash"
    dist = tmp_path / "dist"
    dist.mkdir()
    setup_exe = dist / "AgentSI-setup-0.1.0.exe"
    setup_exe.write_bytes(b"setup-bytes")
    sums = build.record_setup_hash(dist, setup_exe)
    assert sums.is_file(), "SHA256SUMS.txt not written"
    lines = sums.read_text(encoding="utf-8").splitlines()
    assert any(line.endswith("AgentSI-setup-0.1.0.exe") for line in lines), \
        f"setup exe missing from SHA256SUMS.txt: {lines}"
    sums2 = build.record_setup_hash(dist, setup_exe)
    assert sums2.read_text(encoding="utf-8").splitlines() == lines, \
        "record_setup_hash is not idempotent"
