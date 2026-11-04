# Evidence files

Copies of the real proof files from the build, with local paths, machine names and account details removed. Numbers and results are unchanged.

| file | what it proves |
|---|---|
| [video-run-timing.md](video-run-timing.md) | The run shown in the demo video: scene times on the PC clock, the speed-up factors (23x and 86x, labelled on screen), the auditor verdict, the checks that exited 0, the tokens per role (3,727 for the run plus 262 for the Watcher), the Ollama log showing only `muse-glimmer:30b` was called, the two aborted takes, and the defects found while filming (fixed and open). |
| [network-proof.md](network-proof.md) | One Team On run with every role pinned to the local Meta model: 148 samples (one every 3 seconds) of the app's network connections, no address outside this PC, no new DNS names. Verdict: only loopback. |
| [team-on-team-off-results.md](team-on-team-off-results.md) | The log lines with the Team On and Team Off results on the local model (24 min 13 s and 17 min 50 s, both success), a later Team On run with the token split per role, and two runs in a row (11.2 and 8.6 minutes). |
| [clean-install.md](clean-install.md) | The README Quick start run on a fresh clone: every step exited 0, the app answered 200 on `/firstrun`, every README link resolved. The first-run screen was not checked by eye in that test. |
| [release-hashes.md](release-hashes.md) | Sizes and SHA-256 hashes of the installer and the portable zip, the commit they were built from, the smoke checks, and the zip content scan. |
| [final-gate-summary.md](final-gate-summary.md) | The full gate on the integration build: backend tests (370 files), type check, frontend tests (1,343 passed), web build. It also shows what failed: the stub scan reported 2 rows, and one function has no code-level test. Kept as written. |

How to read them: each file was written during the build, not after it. Where a test could not be run, the file says so.

More about how the app was built: [../HOW_IT_WAS_BUILT.md](../HOW_IT_WAS_BUILT.md). Screenshots with captions: [../EVIDENCE.md](../EVIDENCE.md).
