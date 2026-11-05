# Full backend test run on the release code

The README's `pytest` command, run on November 4, 2026, with all tests in one process. Two full runs gave the same counts, in 24 min 54 s and 29 min 22 s. No commit after the release touches `src/`, `frontend/` or `packaging/`, so this is the release code.

**Result: 4,416 passed, 33 failed, 17 errors, 13 skipped, 36 expected failures.**

The final gate shows no red in its [PYTEST line](final-gate-summary.md) because it is a different run: 370 files in a pool, without the test files in subfolders of `tests/`. Frontend tests are not part of this command.

Each of the 50 reds is sorted below, by what was actually checked. No code was changed for this page.

| Category | Meaning | Count |
|---|---|---|
| Confirmed Defect | The test found a real fault in the app. | 0 |
| Outdated Test | The test expects older behaviour, and a named commit changed it. | 9 |
| Unverified / Environment | Not proven either way (2), or caused by how the tests run (39). | 41 |

0 confirmed here does not mean the app has no defects. Defects found in other ways are in [Known issues](../KNOWN_ISSUES.md).

This page is about the test suite. The app was also run on real models, and those runs are separate proof:

- **Muse Spark 1.3 Contributor:** [photos of finished runs](../EVIDENCE.md) with auditor PASS, and [timed runs](speed-spark-vs-glimmer.md).
- **Muse Glimmer:** [Team On and Team Off results](team-on-team-off-results.md), and [the demo video](final-film-scenes.md), where the team finishes a real task with auditor PASS and its checks at exit 0.

## Outdated Test (9)

| Test | It expects | The app now | Changed by |
|---|---|---|---|
| `tests/k04_lane_a/test_a1_providers.py::test_get_provider_exact_match_no_casefold` | Provider names match only in exact case. | `OPENAI` and `openai` are the same provider. | `4006106` |
| `tests/k04_lane_a/test_a1_providers.py::test_d10_facade_delegates_register_get_list` | The same. | The same. | `4006106` |
| `tests/k04_lane_a/test_a1_providers.py::test_d9_disconnect_models_chatmodels_and_mount` | A fixed set of model fields. | More fields, such as `listed` and `kb_known`. | `ef20760`, `00d17d4` |
| `tests/watcher/test_iface_contract.py::test_evaluate_rule_returns_decision` | A journal row on every Watcher check. | A normal check writes no row. | `80c5bb9`, `966e08f` |
| `tests/watcher/test_iface_contract.py::test_evaluate_rule_emits_journal_row` | The same. | The same. | `80c5bb9`, `966e08f` |
| `tests/watcher/test_iface_contract.py::test_engine_decide_commits_choice` | The same. | The same. | `80c5bb9`, `966e08f` |
| `tests/watcher/test_iface_contract.py::test_watcher_status_field_names` | A fixed list of status fields. | More fields, such as `watcher_model`. | `966e08f` |
| `tests/k04_lane_a/test_a1con_merge.py::test_a1con_served_routes_are_exactly_frozen` | Exactly 12 routes in one list. | Routes were added, and the profile route sits in a second list. It still answers in the running app. | `00d17d4`, `9036bb3` |
| `tests/capability_store/test_k05r3_evid_adapter.py::test_adapter_source_is_stdlib_only_no_sqlite` | Only a few allowed imports in the file. | The file also imports `datetime` and the app's own store inside one function. No `sqlite` import is among them. | `05f208f` |

## Unverified / Environment (41)

### Not proven (2)

| Test | What it shows | What was checked |
|---|---|---|
| `tests/k04_lane_a/test_k04g_coder2_served.py::test_k04g_coder2_bp03_9_picker_served` | On a fresh store the model picker route returns no options; the test expects two. | The app window does not call this route. Why the answer changed was not found. |
| `tests/k04_lane_a/test_k04g_coder2_served.py::test_k04g_coder2_sdk_114_suggest_served` | On a fresh store the suggest route answers 404; the test expects 200. | The same. |

### Caused by running all tests in one process (39)

These go red only in the full run. Each file was then run alone and every test in it passed. The errors point to state left behind by earlier tests in the same process. Which earlier test leaves each one was not traced.

| Error in the full run | Count | What it points to |
|---|---:|---|
| Playwright refuses to start, or `asyncio.run()` refuses: an event loop is already running. | 19 | A running event loop left in the process. The error says so itself. |
| `RecursionError: maximum recursion depth exceeded` | 12 | Wrappers built up after many apps in one process. Not traced further. |
| `SESSION_TOKEN_REFUSED: UI session token mismatch` | 4 | A session token from another app in the same process. |
| `'FakeApp' object has no attribute 'delete'` | 2 | A route table that earlier tests extended. |
| Busy check answers 200 instead of 409; a run history that should be empty is not. | 2 | Runs left by earlier tests. |

| File | Red in the full run | Alone |
|---|---|---|
| `tests/test_reachability_k08.py` | 12 failed | 17 passed |
| `tests/test_nf7k05a_toolbench.py` | 1 failed | 2 passed |
| `tests/test_k07next3_b_served.py` | 1 failed | 5 passed |
| `tests/test_k07http1_role_profiles.py` | 1 failed | 8 passed |
| `tests/test_k05batchk1b_capability.py` | 1 failed | 7 passed |
| `tests/test_fxresp_latency.py` | 1 failed | 3 passed |
| `tests/test_fxprovbe_served.py` | 1 failed | 33 passed |
| `tests/test_fxprov_served.py` | 1 failed | 5 passed |
| `tests/test_fxdesign8_perf.py` | 1 failed | 1 passed |
| `tests/test_fxconnect_routes.py` | 1 failed | 3 passed |
| `tests/k04_lane_a/test_pools_routes.py` | 1 failed | 43 passed |
| `tests/test_fxdesign8_shots.py` | 6 errors | 6 passed |
| `tests/test_fxshell1_visual.py` | 4 errors | 4 passed |
| `tests/test_fxlayout_visual.py` | 4 errors | 4 passed |
| `tests/test_fxshellv_sidebar800.py` | 2 errors | 2 passed |
| `tests/test_fxproj_shots.py` | 1 error | 1 passed |
