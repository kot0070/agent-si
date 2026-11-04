# Known issues, release 0.1.0

The current picture on November 4, 2026. The defect ledger in [How this was built](HOW_IT_WAS_BUILT.md) (573 defects, 277 with no owner) is a snapshot from November 2, during the build. It was not recounted after that, so its numbers are not the current state, and this page does not say how many of them are closed.

## What was checked on the release code

- Full test gate: 370 Python test files with no red, plus the frontend tests, type check and build, on the commit just before the small packaging and README fix in this release. The same gate shows FAIL on its stub scan (2 rows) and one listed coverage gap. Neither is a fault in how the app works: [what they mean](evidence/README.md#reading-the-two-flagged-lines).
- That gate does not run the 90 older test files in subfolders of `tests/`. Run on November 4 on the release code: 1,875 passed, 11 failed, 35 expected failures, 1 skipped. The 11 are in the table below.
- Clean install from the README, on an empty folder.
- Installer and portable zip: installed, started, first screen answered.
- A Team On run on Muse Glimmer with only loopback network connections seen.

## Open issues

| Area | Issue |
|---|---|
| Local model | Muse Glimmer on a home PC is slow and can fail. Measured on my PC: the same small task took about 9 to 24 minutes. Earlier versions failed some runs; the last 3 runs passed, a small sample. The Director's plan size varies from run to run. |
| Provider key | One lost key was seen in development. The error now names the provider, but the cause is unknown. |
| Watcher | The Watcher calls its model only on an abnormal event, so a healthy project shows no model call. False guard or tamper alerts are not proven fixed. |
| Watcher settings | The minute window can be set; the refresh interval cannot. |
| Watcher journal | The journal is kept in memory, so it is lost when the app restarts. |
| Older tests | 11 tests in `tests/k04_lane_a`, `tests/watcher` and `tests/capability_store` fail, and the README's `pytest` command runs them too. They date from October 27 to 31 and were not updated when the app changed. They expect fewer fields and imports, a journal row on every normal Watcher check, exact-case provider names, sample model options on an empty store, and a route in another list. Each was read against the code; none was found to be a fault in the app. |
| Worker protocol | The Worker replies in text JSON. Native tool calls are not used. |
| Windows build | Unsigned: Windows SmartScreen warns on first start. |
| Layout | Some settings pages still use the top strip. Some screens are less compact than planned. The Reports look is not finished. |
| Local benchmark | The decision record shows the estimated duration, not the real one (900 s against 393 s in the filmed run). The result rows ran their labels together and read 0 MB of hardware on a PC with a graphics card. |
| Local LLM page | The "no models" note can flash for a moment before the model count loads. |
