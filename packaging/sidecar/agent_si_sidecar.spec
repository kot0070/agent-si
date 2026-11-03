# Copyright (c) 2026 Ivan Soprun
# packaging/sidecar/agent_si_sidecar.spec — PyInstaller sidecar freeze spec.
#
# Frozen: spec/app name `agent_si_sidecar`, exe `AgentSI.exe`, version `0.1.0`.
# Windowed build: console=False (no terminal/console window).
# NOTE (frozen): window flags are owned by K07 `packaging/tauri/`; this lane only
# records the requirement here and never creates that dir.
# Signature: UNSIGNED-BLOCKED (no cert in sandbox; never invent a signature).
# OFFLINE: freezing (`pyinstaller packaging/sidecar/agent_si_sidecar.spec`) uses
# local inputs only: no downloads, no installs, no remote fetches of any kind.
# TARGETS: one-file (default, `dist/sidecar/AgentSI.exe`) and one-dir
# (`AGENT_SI_SIDECAR_ONEDIR=1`, `dist/sidecar/AgentSI/AgentSI.exe` plus
# support files). The exe name, the SI icon and console=False hold on
# both; packaging/build_app.ps1 stages either into the app folder.
# datas below are staged by the owning lanes (frontend assets, migrations,
# locale files, kb-data from the model KB, watcher scripts); a source absent
# from the tree is skipped with a build-log line and waits for its owning
# lane (inputs are never synthesized by this spec).

import os

try:
    _SPEC_DIR = SPECPATH  # provided by PyInstaller at freeze time
except NameError:  # plain-python syntax check: anchor to this file
    _SPEC_DIR = os.path.dirname(os.path.abspath(__file__))

# Workspace root and src dir anchored at this spec file, so the freeze resolves
# the same inputs regardless of the shell working directory (src-first).
ROOT = os.path.abspath(os.path.join(_SPEC_DIR, "..", ".."))
SRC_DIR = os.path.join(ROOT, "src")

APP_NAME = "agent_si_sidecar"
EXE_NAME = "AgentSI.exe"
VERSION = "0.1.0"

# Entry module: provided by the backend lane (frozen here is only the target name).
# Frozen target: src/agent_si/sidecar.py.
# NOT-DONE: the entry file is absent on this tree; freezing waits for the K02
# backend lane to deliver it (composition-root owner per 0C sec 12, map row
# `src/agent_si/backend/app.py`). This lane creates no stand-in entry module.
ENTRY_SCRIPT = os.path.join(SRC_DIR, "agent_si", "sidecar.py")

if not os.path.isfile(ENTRY_SCRIPT):
    print("sidecar spec NOT-DONE: entry absent, waits for K02 backend lane: " + ENTRY_SCRIPT)

# Lane-owned payload dirs: (tree-relative source, in-freeze destination, owner).
# Frozen destination names: frontend / locale / kb-data / watcher.
# Only sources present on disk enter `datas`; a missing source is skipped with
# a build-log line and waits for its owning lane (never synthesized here).
# (No `migrations` entry: the only migration script on disk,
# 0390_localbench_evidence.sql, has no runtime reader in src, and its
# evidence field environment_fingerprint lives via capability_store /
# local adapter / localbench routes; shipping it would be dead payload.)
#   frontend   <- K07 web build output (frontend/dist; build_app.ps1 stage 1)
#   locale     <- K07 language packs (frontend/src/locale)
#   kb-data    <- K04 model KB (src/agent_si/model_kb)
#                 + K09 shipped KB (src/agent_si/kb)
#   watcher    <- K08 watcher engine + standard scripts (src/agent_si/watcher)
_DATA_CANDIDATES = [
    ("frontend/src/locale", "locale", "K07"),
    ("src/agent_si/model_kb", "kb-data/model_kb", "K04"),
    ("src/agent_si/kb", "kb-data/kb", "K09"),
    ("src/agent_si/watcher", "watcher", "K08"),
]

datas = []
_FRONTEND_DIST = os.path.join(ROOT, "frontend", "dist")
if not os.path.isdir(_FRONTEND_DIST):
    raise SystemExit(
        "sidecar spec: frontend/dist is required; run the offline web "
        "build first (npm run build --offline in frontend/)")
datas.append((_FRONTEND_DIST, "frontend"))
for _rel, _dest, _owner in _DATA_CANDIDATES:
    _abs = os.path.join(ROOT, _rel.replace("/", os.sep))
    if os.path.isdir(_abs):
        datas.append((_abs, _dest))
    else:
        print("sidecar spec: skip missing " + _owner + " input (owning lane pending): " + _rel)

# FXCATALOG lane: the frozen QA catalog data consumed by the catalog
# lane at runtime. Absent until its owning lane stages it; a missing
# file is skipped with a build-log line (never synthesized here).
_CATALOG_V2 = os.path.join(
    ROOT, "src", "agent_si", "qa_catalog", "catalog_v2.json")
if os.path.isfile(_CATALOG_V2):
    datas.append((_CATALOG_V2, "qa_catalog"))
else:
    print(
        "sidecar spec: skip missing FXCATALOG catalog data "
        "(owning lane pending): src/agent_si/qa_catalog/catalog_v2.json")

# FXLOC lane: the frozen About refs (sidecar._license_ref/_notices_ref)
# resolve to the bundle root plus docs/third_party_notices. Absent
# sources are skipped with a build-log line (never synthesized here).
_LICENSE_SRC = os.path.join(ROOT, "LICENSE")
if os.path.isfile(_LICENSE_SRC):
    datas.append((_LICENSE_SRC, "."))
else:
    print("sidecar spec: skip missing LICENSE (owning lane pending)")

_NOTICES_SRC = os.path.join(
    ROOT, "docs", "third_party_notices", "NOTICES.md")
if os.path.isfile(_NOTICES_SRC):
    datas.append((_NOTICES_SRC, os.path.join("docs", "third_party_notices")))
else:
    print(
        "sidecar spec: skip missing docs/third_party_notices/NOTICES.md "
        "(owning lane pending)")

# FXSPLASH lane: the product mark rasters (icon.ico holds the exe +
# window + taskbar icon on Windows; mark_256.png feeds README/favicon
# contexts). Absent until this lane stages them; missing sources are
# skipped with a build-log line (never synthesized here).
_ASSETS_SRC = os.path.join(ROOT, "src", "agent_si", "assets")
if os.path.isdir(_ASSETS_SRC):
    datas.append((_ASSETS_SRC, "assets"))
else:
    print("sidecar spec: skip missing FXSPLASH assets "
          "(owning lane pending): src/agent_si/assets")

# FXSPLASH: exe + window + taskbar icon. The .ico carries
# 16/24/32/48/64/128/256 (see packaging/generate_mark_assets.py).
_ICON_SRC = os.path.join(_ASSETS_SRC, "icon.ico")
_ICON = _ICON_SRC if os.path.isfile(_ICON_SRC) else None
if _ICON is None:
    print("sidecar spec: skip missing FXSPLASH icon "
          "(owning lane pending): src/agent_si/assets/icon.ico")

# FXLOC lane: the frozen host runner (catalog_v2._host_path resolves
# under sys._MEIPASS at runtime); the runner modules themselves ride
# the hiddenimports above.
_QA_RUNNERS_SRC = os.path.join(
    ROOT, "src", "agent_si", "qa_catalog", "runners")
if os.path.isdir(_QA_RUNNERS_SRC):
    datas.append((_QA_RUNNERS_SRC, os.path.join("qa_catalog", "runners")))
else:
    print(
        "sidecar spec: skip missing FXCATALOG runners "
        "(owning lane pending)")

block_cipher = None

# pathex is src-first so the frozen backend package resolves before site-packages.
# LANE FIT (INSTALLB): ROOT follows SRC so the top-level `iface` namespace
# (iface/frozen_manifest/manifest.py, imported across the app with a
# try/except fallback) resolves in the freeze. Frozen-boot evidence:
# ModuleNotFoundError: No module named 'iface' without this entry.
a = Analysis(
    [ENTRY_SCRIPT],
    pathex=[SRC_DIR, ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "iface.frozen_manifest.manifest",
        "agent_si.qa_catalog.runners.host",
        "agent_si.qa_catalog.runners.suite_invoke",
        "agent_si.qa_catalog.runners.static_lint",
        "agent_si.qa_catalog.runners.secret_scan",
        "agent_si.qa_catalog.runners.dep_audit",
        "agent_si.qa_catalog.runners.build_check",
        "agent_si.qa_catalog.runners.install_check",
        "agent_si.qa_catalog.runners.policy_gate",
        "agent_si.qa_catalog.runners.observability_lint",
        "agent_si.qa_catalog.runners.i18n_parity",
        "agent_si.qa_catalog.runners.a11y_scan",
        "agent_si.qa_catalog.runners.contract_test",
        "agent_si.qa_catalog.runners.db_check",
        "agent_si.qa_catalog.runners.file_roundtrip",
        "agent_si.qa_catalog.runners.perf_bench",
        "agent_si.qa_catalog.runners.api_smoke",
        "agent_si.qa_catalog.runners.net_probe",
        "agent_si.qa_catalog.runners.link_check",
        "agent_si.watcher.interface",
        "agent_si.automation.interface",
        "agent_si.context_keeper.interface",
        # FROZENSCAN_0101 BREAKS-IN-EXE cover (R1-R5):
        "agent_si.backend.runtime_manager",
        "agent_si.toolguard.ask",
        "agent_si.services.channel_eval",
        "tools.kb_validator.iface",
        "tools.kb_validator.validate_kb",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # FXR2E-6: the frozen K02 contract interface module
    # (src/agent_si/backend/orchestration/interface.py) ships in source
    # for the contract test only; zero product modules import it, so it
    # stays out of the frozen exe. Never delete the file.
    excludes=["agent_si.backend.orchestration.interface"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Bundle hygiene (FXRELTOOLS): test and cache files never ship. Whole
# lane dirs enter `datas` above, so drop interpreter caches, test
# trees and test modules here; runtime imports never resolve from
# them (every .pyc has a .py sibling; no non-test source imports
# __tests__). TOC entries are (dest, src, kind) triples.
_EXCLUDE_DIR_SEGS = ("__pycache__", "__tests__")
_EXCLUDE_FILE_SUFFIXES = (".pyc", ".pyo", ".test.tsx", ".test.ts")
a.datas = [
    (dest, src, kind) for (dest, src, kind) in a.datas
    if not any(seg in _EXCLUDE_DIR_SEGS for seg in dest.replace("\\", "/").split("/"))
    and not dest.replace("\\", "/").split("/")[-1].lower().endswith(_EXCLUDE_FILE_SUFFIXES)
]

# Build flavour (owner 2026-11-02: one-folder decision):
#   default (env unset) = one-file (the frozen behaviour above, unchanged);
#   AGENT_SI_SIDECAR_ONEDIR=1 = one-dir (EXE + COLLECT into the `AgentSI`
#   folder, AgentSI.exe at its root with its support files beside it).
# Both targets stay buildable; the owner flips the default later. Until
# then one-file stays the default and no caller may assume the folder.
_ONE_DIR = os.environ.get("AGENT_SI_SIDECAR_ONEDIR", "") == "1"
_ONE_DIR_FOLDER = "AgentSI"

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

_EXE_KWARGS = dict(
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_ICON,
)

if _ONE_DIR:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=EXE_NAME,
        **_EXE_KWARGS,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name=_ONE_DIR_FOLDER,
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name=EXE_NAME,
        **_EXE_KWARGS,
    )
