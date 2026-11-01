# Agent SI — one task in, honest result out
Agent SI is a desktop app (AgentSI.exe): you write one task, a Director plans it, Managers split the work, agents write files, the app runs the checks, and a fresh auditor gives an honest result — built on Meta Muse models through Fireworks, with optional OpenAI, Anthropic and local models.
Run: download the portable zip, verify the SHA256 file, unpack, start AgentSI.exe. No install.
Connect a provider: Settings -> Models -> Connect. The key is stored locally and sent only to that provider.
Evidence: every claim links to its run evidence — open the project Tests tab and the release evidence index shipped with the bundle (see Tests).
Demo: the 3-minute cut (opens with the F04 full chain, closes with the F14 clean smoke) run against the frozen exe — script SUBMISSION/K12/demo-script.md (no video file ships).
Status: 0.1.0 portable build (unsigned — Windows SmartScreen will warn); hashes verified per the Portable build section below.
Licence: MIT (Copyright (c) 2026 Ivan Soprun; licence texts in LICENSE and the third-party notices file).
Start: jury quick start below — verify hashes, double-click AgentSI.exe on an empty profile, connect a provider, open /firstrun, create a project, run the first task.
This README: Architecture (one diagram) · Screens · Tests (Runs vs code tests vs local tests) · Development · Limits and honest gaps.

## Jury quick start

1. Verify the hashes in the Portable build section below.
2. Double-click AgentSI.exe on an empty profile.
3. Connect a provider: Settings -> Models -> Connect (or the Setup wizard), then optionally pin role pools and the chat model.
4. Open /firstrun and finish connect-provider, one-click team, project+folder, first task.
5. Create a project and run the first task; open the Tests tab for its evidence.

## Architecture

task -> Director -> Managers -> agents -> checks -> fresh auditor -> honest result

You write one task; a Director plans it; Managers split the work; agents write files; the app runs the checks; a fresh auditor gives an honest result.

## Tour (what you see)

- Left nav (`frontend/src/shell/Sidebar.tsx:20-36`): New task, Projects, Results, Settings.
- Right cards (`frontend/src/shell/Inspector.tsx:1-6`): Team now, Context, Results, Background work, Watcher.
- Chat: hierarchy rows (Director, Manager, Agents) above the composer (`frontend/src/chat/HierarchyRows.tsx`, wired in `frontend/src/chat/index.tsx:404`).
- Tests tab per project at `/projects/:projectId/tests` (`frontend/src/app/App.tsx:88`), served by the tests-view board (`frontend/src/k07next3/TestsViewBoard.tsx`, `GET /api/v1/teststage/tests-view`).
- First run at `/firstrun`: 4 steps (`frontend/src/app/firstrun/FirstRunFlow.tsx:22-24`).
- How-it-works diagram (`frontend/src/app/HowItWorks.tsx`): one task in, honest result out.

## Connect a provider

Settings -> Models -> Setup wizard (or Connect {label}), then optionally pin role pools and the chat model; the key is stored locally and sent only to that provider (`frontend/src/settings/ProvidersPage/ProvidersPage.tsx`, labels in `frontend/src/locale/en.json` providers.page).

## Evidence

Every claim links to its run evidence — open the project Tests tab (`/projects/:projectId/tests`) and the release evidence index shipped with the bundle.

## Runtime components

Pinned manifest components: fastapi 0.162.0, openai-agents 0.20.0, react 19.3.1, react-router-dom 7.18.4, zod 4.6.7; plus the 5 frozen sidecar components pywebview 6.2.1, pythonnet 3.2.1, clr_loader 0.3.1, bottle 0.13.4, proxy_tools 0.1.0. Full texts in [docs/third_party_notices/NOTICES.md](docs/third_party_notices/NOTICES.md) and `docs/third_party_notices/licenses/`.

## Portable build

Windows portable build `AgentSI.exe` 0.1.0 ([dist/AgentSI-portable-0.1.0.zip](dist/AgentSI-portable-0.1.0.zip)): UNSIGNED — no certificate in this build, so Windows SmartScreen will warn. Unpack, verify the two SHA256 below against the SHA256SUMS file shipped in the bundle, then run AgentSI.exe.

Hashes below are for the frozen build from 6c01765 (`packaging/installer_manifest/HASH.json` built_from_commit); they are re-stamped on every release — never trust hashes older than int HEAD a8b5a57.

- `AgentSI.exe`: `f77114bd78e1ffe62286a5574e2e03eec5013d85fa4b258344098caa1a75de44`
- `packaging/installer_manifest` MANIFEST/HASH: `530b4b6190e1e6a7c5b70e49b6334d343738a28ce257039586c1066f350de028`

Verify and re-verify with [packaging/installer_manifest/gen_smoke.py](packaging/installer_manifest/gen_smoke.py) (`--root .`). See [packaging/README.md](packaging/README.md) for what the zip holds.

## Tests

- Runs: a run is one agent working on one task.
- Code tests: the project's own test suite.
- Local tests: catalog checks this machine runs before spend.

The Tests tab shows the latest run: served counters and one row per test. It never changes settings.

## Development

Build and test from the checkout: backend with the product virtual environment (`python -m pytest`), frontend with the checked-in `frontend/package-lock.json` (`vitest run`); installs run offline from the checked-in lockfiles, never from a registry. `tools/start.py --smoke` checks the start path on a clean profile. Fixture runs use `pytest -p no:cacheprovider` (see [docs/start-accept-notes.md](docs/start-accept-notes.md)). Per-package build reports: [docs/reports/README.md](docs/reports/README.md).

## Limits and honest gaps

Nothing unmeasured ships as proven: non-LIVE rows in [docs/release/RELEASE_CHECKLIST.md](docs/release/RELEASE_CHECKLIST.md) stay PENDING-REDRIVE, and the release notes carry the same limitation lines; no claim ships as proven without its DEFECTS line. Stale claims are marked PENDING-REDRIVE, never shipped as proven.

## Licence

Agent SI ships under the MIT licence; see [LICENSE](LICENSE) (MIT, Copyright (c) 2026 Ivan Soprun).
