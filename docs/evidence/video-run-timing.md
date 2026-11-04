# Video run: timing and evidence (candidate = take 3 + one extra result clip)

Film: candidate film, 2:57.2 (177.4 s), no voice. Source: take 3 of the recording plus one extra result clip.
Raw recording (real time, nothing cut): every screencast frame and timed still at its real duration, kept with the build records.
App under test: the portable AgentSI.exe built from commit faf33a6 (branch pkg/PLANB, built_from_commit in HASH.json matches), fresh data folder, fresh project folder, window driven only by CDP clicks (14 steps, all hits, misses 0).
Edits to the film: only the speed-up of scene e (burned labels "Sped up 23x" and "Sped up 86x", real-time PC clock bottom-right, drawn before the speed-up so it shows real time) and one substitution in scene f (see below).

## Speed factors
- Run part of scene e: real 491 s (8:11), film 21.4 s, factor **23x** (label "Sped up 23x").
- Waiting part of scene e: real 1029 s (17:09), film 12.0 s, factor **86x** (label "Sped up 86x"). The run itself ended at 03:39:44 (journal row DEVRUN_END); the rest is the wait for the Watcher's 20 minute window after the seed click at 03:31:19, then Evaluate again at 03:55:27 and one real watcher call (answer 03:56:36).
- The run took 8 minutes, not 24: the Director planned 1 part this time (one worker reply wrote and ran everything).

## Scenes (PC clock; T0 = 03:29:56)
| scene | what | real start | real end | real duration | film start | film end | film duration | speed |
|---|---|---|---|---|---|---|---|---|
| a | intro on the first screen (Welcome, providers Meta/OpenAI/Anthropic/Ollama), then project node-add created by clicks | 03:29:56 | 03:30:13 | 17.4 s | 0:00 | 0:17 | 16.8 s | 1x |
| b | Settings: providers list (Cloud list scrolled), Local LLM: Connect Ollama (no key field), Save, 29 models, filter "muse", tick muse-glimmer:30b, Done, pick it, Use for agents: every role listed on it | 03:30:13 | 03:30:49 | 36.0 s | 0:17 | 0:53 | 36.0 s | 1x |
| c | Role pools (Director..Auditor pinned, each its own picker), Watcher pinned to muse-glimmer:30b, Watcher tab: first Evaluate (seed) | 03:30:49 | 03:31:19 | 29.6 s | 0:53 | 1:22 | 29.6 s | 1x |
| d | New task, Team On, exact task text typed and sent | 03:31:19 | 03:31:32 | 13.0 s | 1:22 | 1:35 | 13.0 s | 1x |
| e | the whole run with the right panel (Team now: Director, Manager, Worker running), result line "Done", wait, second Evaluate on the Watcher tab | 03:31:32 | 03:56:52 | 25:20 | 1:35 | 2:09 | 33.4 s | 23x then 86x |
| f | result clip (checks, auditor verdict, Total tokens, run success, files, Watcher card), Tokens tab per role, Local LLM tab, Watcher card | 04:17:46 (clip) and 03:57:07-03:57:39 | | 17.0 + 9 + 9 + 11 s | 2:09 | 2:57 | 48.6 s | 1x |

Scene f detail: F_DETAILS clip film 2:09-2:26 (real 04:17:46, 17.0 s), F_TOKENS 2:26-2:37 (real 03:57:07), F_LOCALAI 2:37-2:46 (real 03:57:19), F_WATCHER 2:46-2:57 (real 03:57:28).
SUBSTITUTION (disclosed): take 3's own result step F_RESULT (real 03:56:52-03:57:07) never opened the Details log (my storyboard op saw a hidden node), so it showed only the verdict line, files and the Watcher card. No further retake was allowed, so the same still-running window and data were recorded again at 04:17:46 for 17 s (click Details, scroll to the checks) and that clip replaces F_RESULT in the film. The clock in the corner shows the real time (04:17), the run and data are the same. F_RESULT stays in the raw recording.

## Result of the run
- Verdict line: "Done - 1 part, 1 passed, files: package.json, add.js, add.test.js." Details: Part p1 attempt 1; Check p1 $ findstr "name": package.json -> exit 0; Check p1 $ findstr add add.js -> exit 0; Check p1 $ findstr node:test add.test.js -> exit 0; Check p1 $ node --test add.test.js -> exit 0; "Auditor for p1: PASS (package.json exists with name "node-add" and test script, verified by findstr)"; "Part p1: PASS (checks green, auditor PASS)"; "Total: 2560 input + 1167 output = 3727 tokens; cost not known (no price)"; "run success: all 1 parts PASS".
- Tests: the app ran `node --test add.test.js` itself, exit 0; the worker's own run output: tests 2, pass 2, fail 0 (add returns sum of two numbers; add handles floats).
- Files in the project folder: add.js, add.test.js, package.json.
- Tokens (Tokens tab, app telemetry): Auditor 1,356 (1 call), Director 1,216 (1), Manager 170 (1), Worker 985 (1), Watcher ("Other calls", model muse-glimmer:30b) 262 (1); total 3,989 (3,727 run + 262 watcher). Every row model muse-glimmer:30b.
- Watcher card (right panel, after the film's second Evaluate): "Model muse-glimmer:30b - Model calls: 1 - 262 tokens", journal row "03:56 Decision rule-guard ESCALATE model=muse-glimmer:30b action=scripts/guard_check.py".
- Local LLM tab: rows director-plan, manager-plan, worker-p1, all model ollama/muse-glimmer:30b, cost "free: a local model costs nothing".
- Verdict of this document: PASS for the run (auditor PASS, checks exit 0, tests 2/2), Watcher real call on the local model, no key field and no cloud name on any film screen except the provider list (Meta, OpenAI, Anthropic ... with Connect buttons, no key typed).

## Ollama server log: only muse-glimmer:30b was called (window 03:29:56-03:57:44, PC clock, the Ollama server log)
- POST /api/chat: 5 lines: 03:35:02 (3m30s, Director), 03:35:34 (30.26 s, Manager), 03:38:25 (2m40s, Worker), 03:39:44 (1m10s, Auditor), 03:56:36 (1m0s, Watcher).
- Model loads in the window: 2 (03:31:31 and 03:55:27, the second after the 5 min keep-alive), both `model=<blob path>/sha256-71b5c9c9...3f8b`, the FROM blob of muse-glimmer:30b (`ollama show --modelfile muse-glimmer:30b`); "template selection model=registry.ollama.ai/library/muse-glimmer:30b" after each load. No other model was loaded or called; `ollama ps` before the take was empty; nothing listened on port 1234 (LM Studio line in Settings reads "Local server is not running").
- The log also holds 64 WARN lines naming sqlcoder:7b ("model is missing tokenizer.chat_template"): they come with every GET /api/tags|/v1/models model listing (about every 30 s, by a listing client, plus the app's Local LLM page), not from a generation; there is no POST /api/chat for sqlcoder:7b and no load of it.

## Takes (retake budget: 2 used)
- Take 1 (T0 01:20:24, exe ade3afa): aborted at 02:08: Director planned 4 parts; part p2's worker looped 14 replies in 30 min. Scenes a-d all hit.
- Take 2 (retake 1, T0 02:08:50, same exe): aborted at 03:25: 4 parts again; p2 worker at reply 18 of 40 after 41 min, same loop.
- Cause fixed in source (DEFECT-30 hide .devrun from worker list_dir/read_file 0beeeab, DEFECT-31 worker brief faf33a6), exe rebuilt from faf33a6.
- Take 3 (retake 2, T0 03:29:56): the candidate. 1-part plan, PASS in 8 min.

## Commits on pkg/PLANB after 1a1e1d6 (author and committer Ivan Soprun)
274b84d V1 (DEFECT-14), 1dbeedc DEFECT-15, 709f4a9 DEFECT-16, 09ffcee DEFECT-17, 7970985 DEFECT-18, 17c49d4 DEFECT-19, 641d028 DEFECT-20, 047ff80 DEFECT-21, ade3afa DEFECT-22, 0beeeab DEFECT-30, faf33a6 DEFECT-31.

## Defects (ID | where | what (seen vs expected) | when | likely cause (file:line) | status)
Fixed in the repo, each with a test:

| ID | where | what | when | likely cause | status |
|---|---|---|---|---|---|
| DEFECT-14 | worker reply | `{"type":"write_file",...}` instead of `{"action":...}`: attempt wrote nothing | Glimmer worker, first reply | src/agent_si/runtime/devrun/protocol.py `_flatten_wrapped_action` (called by parse_agent_reply) | FIXED 274b84d, 9 tests in the file pass |
| DEFECT-15 | Settings > Local LLM > Connect Ollama | dialog showed an API key input for a keyless local preset | click Connect | frontend/src/settings/ProvidersPage/ConnectDialog.tsx:513 | FIXED 1dbeedc |
| DEFECT-16 | Settings > Local LLM > Use for agents | pinned roles only for the shared project "local"; a project made before showed Auto and "No model bound yet" | project node-add selected, then Use for agents | frontend/src/settings/ProvidersPage/LocalConnectSection.tsx handleUseForAgents, app/App.tsx:1008 | FIXED 709f4a9 |
| DEFECT-17 | chat composer | "No model bound yet. Connect a provider" stayed with Ollama connected and roles pinned | New task | frontend/src/chat/index.tsx:2171 readBoundModels | FIXED 09ffcee |
| DEFECT-18 | run stream | "Team: ... on ollama/ollama/muse-glimmer:30b" (provider doubled) | any local Team On run | src/agent_si/runtime/devrun/engine.py:1060 `_team_lines` | FIXED 7970985 |
| DEFECT-19 | right panel Team now | model shown as "30b" | local model with an Ollama tag | frontend/src/shell/Inspector.tsx:165 shortModelName | FIXED 17c49d4 |
| DEFECT-20 | chat verdict line | "files: none listed" while the Results card lists the files | Team On run | frontend/src/chat/index.tsx:817 summarizeEngineTurn | FIXED 641d028 |
| DEFECT-21 | project > Local LLM tab | two worker rows both show the role total | two worker rows | frontend/src/projects/ProjectView.tsx:1414 rowTokens | FIXED 047ff80 |
| DEFECT-22 | every Settings page | link strip printed as one run-on line | open Settings | frontend/src/app/App.tsx:630 | FIXED ade3afa |
| DEFECT-30 | worker steps | worker spent 3-6 replies per part on list_dir/read_file of the engine's .devrun folder | takes 1 and 2 | src/agent_si/runtime/devrun/engine.py:4507 | FIXED 0beeeab |
| DEFECT-31 | worker brief | part p2 (add.js) runs npm test, fails on add.test.js of part p3, tries to write it (refused), loops 18+ replies / 41 min (limit 40 per attempt) | 4-part plans | src/agent_si/runtime/devrun/engine.py:_worker_prompt | FIXED faf33a6 |
| VIDEO-TOOL | live_drive/demo_video.py (build tool) | CDP screencast sends no frame for a static page (2 frames in 100 s, none for the first screen); stitch at average fps cannot keep real time; 15 min wait cap; fixed 14 steps | any static scene, long run | ScreencastRecorder, MAX_WAIT_S | FIXED additively (timed stills, stamps, env cap, extra ops) |

Open (seen on screen or in the run, not fixed):

| ID | where | what | when | likely cause | status |
|---|---|---|---|---|---|
| DEFECT-23 | Watcher tab, guard card Evaluate (film scene c) | result line "Blocked a problem - Journal row: -" on a healthy project | first Evaluate on an empty journal | frontend/src/watcher/WatcherRuleCards.tsx:335 verdictLocaleKey(BLOCK) shows the resting verdict as an event | OPEN |
| DEFECT-24 | Settings > Local LLM card | "Use for agents" and "Disconnect" touch each other | Ollama connected | frontend/src/settings/ProvidersPage/LocalConnectSection.tsx button row | OPEN |
| DEFECT-25 | Settings > Local LLM | "No local models found in this folder yet." under a connected Ollama with 29 models | open Local LLM | frontend/src/app/App.tsx:175 LocalAiStoredPanel wording | OPEN |
| DEFECT-26 | Watcher model call | the card reads "not used yet" until an abnormal event; the real call needs a seed row older than the 20 min window (second Evaluate); the watcher journal is in memory and is lost on app restart | Evaluate twice, 20+ min apart, one app process | src/agent_si/watcher/rules.py:150 _heartbeat_stale | OPEN |
| DEFECT-27 | run stream | one "Waiting for the model" line every 15 s (about 100 in a long run) | long local run | backend/chat_stream.events_with_waiting | OPEN |
| DEFECT-28 | Director plan | plan size varies per run (1 part in take 3, 2 in the dry run, 4 in takes 1 and 2) and a plan once needed a re-ask for absolute paths | same task text | src/agent_si/runtime/devrun/engine.py _director_prompt | OPEN |
| DEFECT-29 | Settings > Models | every cloud model row reads "not known" next to an unticked box (no key connected) | open Models | frontend/src/settings/ProvidersPage row state | OPEN, honest state |
| DEFECT-32 | Settings > Routing > Role pools (film scene c) | choosing the "Pinned model" radio saves at once with no model: red line "Save failed for Watcher.: bad role pool: PINNED needs provider and model" until a model is picked | click Pinned on a role in Automatic | frontend/src/settings/ProvidersPage/RolePoolPicker.tsx emit() guards only an empty pool | OPEN |
| DEFECT-33 | right panel Team now (film scenes e, f) | model cut to "muse-glimmer:..." although the row has room | any local run | frontend/src/shell/Inspector.tsx row ellipsis | OPEN |
| DEFECT-34 | project chat after reopening it (film F_DETAILS) | the run (user message, Done line, Details log) is listed twice: stream copy and history copy | click the project in the sidebar after a run | frontend/src/chat/index.tsx history merge | OPEN |
| DEFECT-36 | film storyboard | take 3's F_RESULT never opened the Details log (ensure_open saw a hidden node) | take 3 review | storyboard script, step F_RESULT | FIXED in the extra clip (click_unless_text, scroll_to_text) |
| DEFECT-37 | tool kit | live_window.py start deletes nothing but its `stop` rmtree-s the throwaway root and `--exe` start needs --allow-stale for a branch behind int | every take | live_drive/live_window.py (build tool) | OPEN (stop never used, roots kept) |

## Frames looked at (every scene)
final2_A_INTRO, A_PROJECT, B_PROVIDERS, BL_41 (B_LOCAL), B_USE, C_ROLES, CW_65.5 (DEFECT-32 visible), final2_C_WATCHER (DEFECT-23 visible), D_NEW, D_TASK (exact text), final_E_RUN (Sped up 23x), final_E_RUN_WAIT (Sped up 86x), final2_F_DETAILS, F_TOKENS, F_LOCALAI, F_WATCHER. Nothing on any frame shows a key field or a made-up name; model name shown everywhere is muse-glimmer:30b.
