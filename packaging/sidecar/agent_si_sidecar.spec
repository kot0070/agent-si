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
# Frozen destination names: frontend / migrations / locale / kb-data / watcher.
# Only sources present on disk enter `datas`; a missing source is skipped with
# a build-log line and waits for its owning lane (never synthesized here).
#   frontend   <- K07 web build output (frontend/dist; build_app.ps1 stage 1)
#   migrations <- K13 additive-only migration scripts
#                 (src/agent_si/adapters/sqlite/migration_scripts)
#   locale     <- K07 language packs (frontend/src/locale)
#   kb-data    <- K04 model KB (src/agent_si/model_kb)
#                 + K09 shipped KB (src/agent_si/kb)
#   watcher    <- K08 watcher engine + standard scripts (src/agent_si/watcher)
_DATA_CANDIDATES = [
    ("frontend/dist", "frontend", "K07"),
    ("src/agent_si/adapters/sqlite/migration_scripts", "migrations", "K13"),
    ("frontend/src/locale", "locale", "K07"),
    ("src/agent_si/model_kb", "kb-data/model_kb", "K04"),
    ("src/agent_si/kb", "kb-data/kb", "K09"),
    ("src/agent_si/watcher", "watcher", "K08"),
]

datas = []
for _rel, _dest, _owner in _DATA_CANDIDATES:
    _abs = os.path.join(ROOT, _rel.replace("/", os.sep))
    if os.path.isdir(_abs):
        datas.append((_abs, _dest))
    else:
        print("sidecar spec: skip missing " + _owner + " input (owning lane pending): " + _rel)

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
    hiddenimports=["iface.frozen_manifest.manifest"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=EXE_NAME,
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
)
