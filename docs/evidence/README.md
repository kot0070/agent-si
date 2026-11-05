# Evidence files

Copies of the real proof files from the build, with local paths, machine names and account details removed. Numbers and results are unchanged.

| file | what it proves |
|---|---|
| [final-film-scenes.md](final-film-scenes.md) | The final 2:55 video scene by scene: where each of the 14 functions appears, and whether it is shown live, as a run result, or as a screen. |
| [video-run-timing.md](video-run-timing.md) | The main run in the demo video, written for an earlier 2:57 cut: scene times on the PC clock, the speed-up factors (23x and 86x, labelled on screen), the auditor verdict, the checks that exited 0, the tokens per role (3,727 for the run plus 262 for the Watcher), the Ollama log showing only `muse-glimmer:30b` was called, the two aborted takes, and the defects found while filming (fixed and open). |
| [speed-spark-vs-glimmer.md](speed-spark-vs-glimmer.md) | How fast the team ran on Muse Spark through the API, how slow it runs on Muse Glimmer on my PC, and why the demo had to move there after my card was blocked. |
| [full-test-run.md](full-test-run.md) | The README's `pytest` command on the release code: 4,416 passed and 50 reds, each sorted as a confirmed defect (0), an outdated test (9) or unverified or environment (41). |
| [network-proof.md](network-proof.md) | One Team On run with every role pinned to the local Meta model: 148 samples (one every 3 seconds) of the app's network connections, no address outside this PC, no new DNS names. Verdict: only loopback. |
| [team-on-team-off-results.md](team-on-team-off-results.md) | The log lines with the Team On and Team Off results on the local model (24 min 13 s and 17 min 50 s, both success), a later Team On run with the token split per role, and two runs in a row (11.2 and 8.6 minutes). |
| [clean-install.md](clean-install.md) | The README Quick start run on a fresh clone: every step exited 0, the app answered 200 on `/firstrun`, every README link resolved. The first-run screen was not checked by eye in that test. |
| [release-hashes.md](release-hashes.md) | Sizes and SHA-256 hashes of the installer and the portable zip, the commit they were built from, the smoke checks, and the zip content scan. |
| [final-gate-summary.md](final-gate-summary.md) | The full gate on the integration build: backend tests (370 files), type check, frontend tests (1,343 passed), web build. It also shows two flagged lines: the stub scan reported 2 rows, and one function is listed as having no code-level test. Kept as written, and [explained below](#reading-the-two-flagged-lines). |

How to read them: each file was written during the build, not after it. Where a test could not be run, the file says so. The defect table in `video-run-timing.md` is a snapshot from filming: DEFECT-23, 24, 25, 27, 32, 33 and 34 are marked OPEN there and were fixed after it. The current state is in [Known issues](../KNOWN_ISSUES.md).

## Reading the two flagged lines

The gate summary is kept as the gate wrote it. Two of its lines look worse than they are, so here is what each one means.

**Stub scan: FAIL, 2 rows.** Both rows are still in the release code. Neither changes what the app does, and the same line reports 0 reachable stubs. I left them because fixing them would mean a new build of the released app with no change in behaviour.

- `frontend/src/kb/DetachControl.tsx:4`: the scan matched the word "fake" in a code comment.
- `src/agent_si/backend/app.py:4998`: an unused import of a file that only holds interface shapes. Nothing calls it.

**F08: no code-level test.** This is a limit of the checker, not a missing test. F08 is the provider catalog: connect with the key only. The check only looks for the literal label `F08`, and it only reads the first 400 test files ([`all_test_paths[:400]`](../../tools/build_ops/int_gate.py)), while the build has about 650. The one test file with that label, `fxmodal.test.tsx`, sits past that limit. The tests for this function carry other names, for example `fxconnect.test.tsx`, `ProvidersPage.test.tsx` and `firstrun_served.test.tsx`, and the same gate ran them with no red. This check never fails the gate on its own.

More about how the app was built: [../HOW_IT_WAS_BUILT.md](../HOW_IT_WAS_BUILT.md). Screenshots with captions: [../EVIDENCE.md](../EVIDENCE.md).
