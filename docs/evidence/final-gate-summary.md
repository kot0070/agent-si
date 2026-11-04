# Full gate on the integration build 9ceceec87b40 (text as written by the gate, paths shortened)

## G1 PASS wall=17s 0 lost
## G2 PASS wall=29s 0 hits 0 problems
## DEPS PASS wall=0s deps present
## PYTEST PASS wall=253s pool=10 files=370 reds=0 flaky=0 still=0
## TSC PASS wall=1s cmd=node node_modules/typescript/bin/tsc --noEmit -p . rc=0 files=442 include=[src] tsc PASS (neg-control 2026-11-02: injected TS2322 -> rc=1)
## VITEST PASS wall=202s cmd=node --preserve-symlinks-main node_modules/vitest/vitest.mjs run --maxWorkers=2 rc=0 testfiles=284 filesPassed=287 testsPassed=1343(expected>900)
## VITEBUILD PASS wall=1s cmd=node node_modules/vite/bin/vite.js build rc=0 dist_files=18 index=yes | [39m
## STUBSCAN FAIL wall=44s 2 rows // FROZEN-REAL 6 files, reachable-stubs 0, hash-mismatch 0 // NO-HASH src/agent_si/backend/orchestration/interface.py, iface/frozen_manifest/manifest.py, src/agent_si/watcher/interface.py, src/agent_si/automation/interface.py, tools/kb_validator/iface.py
- STUB <repo>/frontend/src/kb/DetachControl.tsx:4 stub-word
- STUB <repo>/src/agent_si/backend/app.py:4998 contract-import
## G4 PASS wall=0s backend-import OK; dist=present
- SKIP W08|W09|W10|W11 keyed/model: needs provider model: SKIP mock-boundary or skip
## G5 PASS wall=0s 63 mapped 1 gaps
- GAP F08 (no code-level test)

walls: {"G1": 16.5, "G2": 28.9, "DEPS": 0.0, "PYTEST": 253.2, "TSC": 0.9, "VITEST": 202.1, "VITEBUILD": 0.5, "STUBSCAN": 43.7, "G4": 0.5, "G5": 0.1}

## REDS TABLE
| id | group | first E |
|---|---|---|
| STUB <repo>/frontend/src/kb/DetachControl.tsx:4 | STUB <PATH> stub-word | STUB <repo>/frontend/src/kb/DetachControl.tsx:4 stub-word |
| STUB <repo>/src/agent_si/backend/app.py:4998 | STUB <PATH> contract-import | STUB <repo>/src/agent_si/backend/app.py:4998 contract-import |
