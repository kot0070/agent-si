# Agent SI

Agent SI is built on the OpenAI Agents SDK and adds product-specific layers on top of it: Director, Manager, and worker governance; project, task, and run model; TaskPlanner; TaskRouter; ModelRouter; LOCAL, SPLIT, and CLOUD routing; local AI discovery and configuration; optional Capability DB; resource scheduling; deterministic verification; independent audit; telemetry and accounting; project analytics; report export; frontend.

Status: in development.

## Prerequisites

Installs start here: no install content stands before this section.
This checkout documents prerequisites, setup steps, demo commands,
fixture commands, task commands at the checkout root.

- Python 3.13 with the product virtual environment.
- Node.js with the checked-in `frontend/package-lock.json`.
- A checkout of this repository (all paths below are checkout-relative).

## Setup

1. Run `tools/start.py --smoke` on a clean profile first: it checks
   the whole start path without opening anything.
2. Configure from the environment example, then offline-install from
   the lockfiles (backend `pyproject.toml`, frontend
   `frontend/package-lock.json`).
3. Launch managers plus workers plus UI.

Installs run offline from the checked-in lockfiles against the pre-fetched tarball cache only, never from a registry.

## Demo and fixture command index

- Setup: `tools/start.py --smoke`
- Demo (bring the demo project to green): `POST /k10/start/demo`
- Fixtures: `pytest tests/test_k10ph2d_served.py -q -p no:cacheprovider`

- Data dir: the product start path takes the data dir from consumer-layer env `AGENT_SI_DATA_DIR`, never harness settings; blank fails loud.

See `docs/k10ph2d-start-accept-notes.md` for the startup idempotence
note, the restart note, the data-dir start path note, and the
frontend cached-tarballs note.

## License and third-party notices

Agent SI ships under the MIT license; see `LICENSE` (MIT,
Copyright (c) 2026 Ivan Soprun). Pinned third-party direct
dependencies (each package's own installed metadata carries its
licence text):

- fastapi 0.162.0
- openai-agents 0.20.0
- react 19.3.1
- react-router-dom 7.18.4
- zod 4.6.7

## Portable build (INSTALLB lane)

Windows portable build `AgentSI.exe` 0.1.0 (`dist/AgentSI-portable-0.1.0.zip`):
UNSIGNED — no certificate in this build, so Windows SmartScreen will warn.
Verify the SHA256 hashes before running (PowerShell):

- `AgentSI.exe`: `f77114bd78e1ffe62286a5574e2e03eec5013d85fa4b258344098caa1a75de44`
- `packaging/installer_manifest` MANIFEST/HASH: `530b4b6190e1e6a7c5b70e49b6334d343738a28ce257039586c1066f350de028`

Regenerate and re-verify with `packaging/installer_manifest/gen_smoke.py --root .`.
