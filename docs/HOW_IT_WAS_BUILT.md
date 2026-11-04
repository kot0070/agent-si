# How this was built

## Contents

1. [Time](#1-time)
2. [Scale](#2-scale)
3. [How the team was organised](#3-how-the-team-was-organised)
4. [Custom tools written for this build](#4-custom-tools-written-for-this-build-problem---tool)
5. [Decisions and why](#5-decisions-and-why-problem--decision--result)
6. [What went wrong and what it changed](#6-what-went-wrong-and-what-it-changed)
7. [Numbers](#7-numbers-each-with-its-source-command)
8. [Reusable lessons](#8-reusable-lessons)
9. [Notes from the supervising AI](#9-notes-from-the-supervising-ai)

---

## 1. Time

Build ran 2026-10-26 → 2026-11-02 (7 calendar days). Muse run ledger:
first start 2026-10-26 11:58:31 -05:00, last start 2026-10-30 13:57:24 -05:00,
last end 2026-10-30 14:07:29 -05:00; per-day runs 96 / 128 / 64 / 128 / 129.
Session store spans 2026-10-27 06:44:51Z → 2026-11-02 17:22:32Z. Merge-train
log covers 2026-11-02 18:31:48Z → 23:48:07Z (321 lines, 5h16m). Aggregate
compute: 1,782,295 s (~495 h) over 545 runs; longest single run 34,088 s
(~9.5 h). Idle gaps in the train window: 2 gaps >= 15 min (15.2, 26.8 min);
longest no-work stretch ~21–29 h depending on bucket-boundary method
(both values kept, method not frozen).

> **Update, 2 November 2026.** On November 2 the owner's bank blocked the Meta Model API billing, so the final demo runs locally on Muse Glimmer through Ollama. Earlier runs on Muse Spark 1.3 Contributor are shown as dated screenshots.

## 2. Scale

13 product packages (K01–K13) plus tool/fix lanes. Ledger totals: 545 runs,
9039 managers, 9067 agents, 883 tasks, 262 tooling REJECT, 43.7% first-pass.

Concurrency (MEASURED id-clock FLOOR, agent peak report):
peak 101 Muse live @ 10-26 19:49 local (11 runs live), 104 combined live
(101+3 OpenCode); active peak 66 @ 10-26 23:37 (9 runs live; 66+0 OC).
Working-min averages: combined live 33.83 (7200 min) / active 10.73
(6247 min); Muse live 32.34 (6562 min) / active 10.04 (6027 min).

Per day:

| Day | Live max | Live avg | Active max | Active avg |
| --- | ---: | ---: | ---: | ---: |
| 10-26 | 101 | 43.78 | 66 | 20.9 |
| 10-27 | 75 | 37.6 | 54 | 13.3 |
| 10-28 | 44 | 31.75 | 55 | 7.22 |
| 10-29 | 50 | 28.9 | 23 | 7.22 |
| 10-30 | 29 | 24.75 | 10 | 4.11 |

On 10-29 the OpenCode live max was 30 and the active max was 31.

Coverage: 7079 union agents (1617 roots + 5462 subagents), 84.7% with event
files + 15.3% POINT ids, so peaks are FLOORs; `live` includes waiting agents.
2030 overlapping-dir ids @ 10-26 21:42 kept only as the UPPER-BOUND note
(assumed every listed dir live — disproved by per-agent id times).

Failure next to the peak (OS32 tree lens, 10-min buckets):

| Time (10-26) | Failure share |
| --- | ---: |
| 19:40 | 40.5% |
| 19:50 | 39.6% |
| 21:40 | 42.6% |
| 21:50 | 43.2% |
| 22:40 | 45.6% (max) |

The active peak sits at 23:30 (38.1%) and 23:40 (39.1%).

Field fact: live build run folders hold 0 run dirs now; copies survived in
an off-drive backup (877 run dirs: 538 with stream data, 532 events.jsonl,
514 summary/start-end), recounted read-only. Merge train landed 43 lanes;
product repo holds 990 commits; 32 gate record files.

## 3. How the team was organised

One person, the owner, set the goal and the rules and took every product
decision. The steering role, writing short tasks and accepting work, was held mainly
by Claude Code sessions, with Muse through the API in support. The building
itself was done by Muse agents: Muse Code directors split work into the maximum
number of non-conflicting managers, managers into coder agents; OpenCode
sessions ran tools, checks and counts. Rules: the author never audits its own work; every link
ends with a FRESH auditor (new instance); a signatures-only check is never
PASS — contract tests prove behaviour (every error code raised in its own
condition, every route reaching the real implementation); PASS only with a
real run (command + quoted tail); every task carries an entry-to-result
check the auditor re-runs; acceptance also runs a row-by-row reality check
per coverage row (REAL / FAKE / MISSING / WAITS-LIVE, FAKE 0, MISSING 0);
product interfaces are frozen by hash and any change is re-frozen with
notes to all lanes.

## 4. Custom tools written for this build (problem -> tool)

- Parallel lanes overwrote each other -> merge train: serial landing
  loop (lane table, atomic state/log, audit slots, FAIL notify once,
  golden-subset gate per landing, single int writer).
- "Green" merges broke the tree -> integration gate: fast + full gates
  (prove-they-ran: exact command, counts, negative controls, red allowlist).
- An agent's cleanup aimed at the whole drive and was stopped in time -> shell guard refuses
  recursive deletes and drive-root globs in command text. It cannot see
  inside a script file run by name, so the real cover is 15-minute
  off-drive backups, a no-delete rule for every agent and a mass-delete
  alarm.
- Placeholder code landing as done -> stub scanner: REJECT on stub
  markers, empty bodies, test-only imports in product code.
- Secrets near release artifacts -> ship/secret scan + redaction of bare
  internal names in release datasets, hard REFUSE on real paths/keys.
- "It works" without proof -> one-pass live drives: walk (W01–W20 UI
  steps incl. hang guard), exe probes (per-PID close-clean), UI replay,
  evidence table, release pack, seed outage.
- 573 defects, no owner -> defect ledger: every defect in one ledger,
  state recomputed from the shipped branch on demand.
- Which function is proven? -> function map: build-plan rows to entry
  file:line to proving tests to last gate result.
- Status chaos across lanes -> owner board + lane status from train files;
  15-minute backups; quiet-window launchers (hidden consoles, no-op
  browser sink so drives never open the owner's browser).
- Stuck/silent lanes -> stall + sub watchers (live-session-aware nudges),
  scheduler + queue + reserve files, self-learning analyst loop.
- Lost-in-merge locales, missing legal file -> locale merge driver,
  third-party notices generator from manifests.
- Incomplete red lists -> full-output runner + red-list builder + brief
  lint gate (continuation briefs carry the whole verbatim RED LIST).
- One click = full dev state -> watchdog pulse/auto + owner board
  phone screen, both read-only. PULSE30 (automatic on every watchdog
  run): one 30-min block per slot to the advisor inbox with live runs x/5
  (what/age/artifact each), queue/reserve, last RETURN/ACCEPT, checklist
  DONE/TOTAL + progress line, token cost, stuck/silent flags, tree depth
  director->managers->children and the 5-min work-artifact sweep
  (SILENT>10m). AUTOPULSE1 (auto mode): same shape every 10 min, live x/8,
  newest-artifact age + queue head + pending HD requests. The advisor
  watcher wakes the advisor on AUTO/PULSE30/ARTSWEEP blocks. The owner board
  (one-shot or looping text output) builds one phone screen from the train
  files (train lanes, state, log, gate records) as head/ЗЛИТТЯ/ЛЕЙНИ/ГЕЙТ/ЛЮДИ/СКРИПТИ/ЗБІРКА/
  ЖУРНАЛ/ЛОГИ — the ЛОГИ tail (raw train lines + gate verdicts + sub ends
  with HH:MM) closed the owner's "board has no logs" complaint. Forced by:
  status chaos across lanes, stuck/silent lanes nobody saw, dead infra, and
  a board that showed verdicts but no raw logs.

## 5. Decisions and why (problem | decision | result)

| # | Problem | Decision | Result |
| --- | --- | --- | --- |
| 1 | Lanes merged over each other, history unreviewable | Serial merge train, one writer | 43 lanes landed in order, every landing gated. |
| 2 | Green suites that never ran | Gates must prove they ran (counts, negative controls, artifact-exists checks) | Harness FAILs separated from product FAILs (import-path, PATH fixes). |
| 3 | One agent's cleanup deleted trees | No agent deletes anything, command text guard, off-drive backups, mass-delete alarm | No repeat so far; the guard alone would not stop a script file, stated plainly. |
| 4 | Silent auditors / self-acceptance | Fresh auditor per link, no PASS without a run | Hollow verdicts re-audited once, never through a note to the coder. |
| 5 | Stale tests failing on superseded expectations | Named test-fix entries, never silent edits | Suite greens trace to listed expectation changes. |
| 6 | Startup defects "fixed" by timing tweaks | Root-cause fix in the start path covering every entry path | Splash/boot rows closed on code, not overlay timing. |
| 7 | Fake greens (fixture rows passing without the real binary) | Checks must invoke the real binary (version flag, real path) | Echo-ok rows replaced. |
| 8 | Tool output flooding the owner's screen | Hidden consoles + no-op browser sink repo-wide, pinned by tests | Quiet runs verified, 0 new consoles over loop cycles. |
| 9 | Single-file exe paid full unpack + left orphans | One-dir layout: serving in ~2 s vs ~5 s, clean stop 6/6 | Release ships one-dir. |
| 10 | Turn budget overrun | No new tool tasks, product only, monitor digest every 15 min | Turns/h back under target, no check cut. |
| 11 | Hidden/polling loops reporting "done" with no evidence | Loops report cycles + new-work count; 0-new is quoted evidence | Phantom progress ended. |
| 12 | Lessons evaporating | Every lesson ends as FIX brief, digest line, or CLOSED by whom; analyst mines logs after accepts | Journal + digest stayed actionable, no silent rule edits. |

## 6. What went wrong and what it changed

- **Delete incident (~11:03 on 11-02).** One of our own agents, cleaning its
  scratch, ran a recursive delete over a drive glob built from character
  codes, so no text filter would have read it. Product and worktree trees
  were gone, on an SSD with no undelete. Recovered from clones, the spec
  files and a replay of 406 sessions. Fix: agents never delete, off-drive
  backups, command guard, mass-delete alarm.
- **False greens.** Fixture-only rows passed while the real interpreter was
  missing from PATH; a probe failed on import path, not product. Fix: real
  binary probes, env fixes, and named test-fixes instead of silent edits.
- **Tool hangs.** Backup died on a locked file; walk items hung without bound;
  a generator test exceeded per-test timeout. Fix: skip-lists, per-item
  hang guard with stack dumps (HUNG never PASS), per-test timeouts.
- **Guard-era hollow verdicts** (runs blocked before the guard lift) were
  re-audited once by a fresh auditor, never notified to coders.
- **Concurrent loop instances clobbered shared train state.** Fix:
  single-instance PID guard plus atomic state writes.

## 7. Numbers (each with its source command)

| Claim | Value | Source |
| --- | --- | --- |
| Muse runs | 545 | run report script, all runs (TOTAL row) |
| Managers / agents / tasks | 9039 / 9067 / 883 | same TOTAL row |
| Tooling REJECT / first-pass | 262 / 43.7% | same TOTAL row |
| Aggregate wall / max run | 1,782,295 s / 34,088 s | ledger script re-run, quoted in evidence file |
| Root cost | $19.4343 | token cost script (matches TOTAL cost) |
| Muse peak live (MEASURED id-clock FLOOR) | 101 agents @ 10-26 19:49 (11 runs; 104 combined) | agent peak report, peaks + top-10 |
| Muse peak active (MEASURED id-clock FLOOR) | 66 @ 10-26 23:37 (9 runs) | same |
| Combined working-min avg (MEASURED) | live 33.83 / active 10.73 | agent peak report, peaks row |
| Muse working-min avg (MEASURED) | live 32.34 / active 10.04 | same |
| Union agents / coverage (FLOOR basis) | 7079 (1617 roots + 5462 sub); 84.7% filed + 15.3% POINT | agent peak report, union line |
| 2030 (UPPER BOUND note only) | overlapping-dir ids, liveness assumed — disproved | agent peak report, limits |
| Failure next to peak (MEASURED) | 19:50 39.6%, evening 30-45%, max 22:40 45.6% | agent peak report, failure + OS32 table |
| OpenCode peak (MEASURED) | 30 live @ 10-29 06:39 / 31 active day-max | agent peak report, peaks row |
| In-scope sessions / messages | 1060 / 63394 | store sweep script, read-only copy |
| Lanes landed | 43 | train state file, landed list |
| Product commits | 990 | git commit count on the product branch (tip ddf00be) |
| Gate records | 32 | count of gate run records |
| Merge-train tests | 38 passed | merge train test suite |
| Defect ledger, snapshot of Nov 2, not recounted since: see [Known issues](KNOWN_ISSUES.md) | 573 (49 fixed-in-ship, 18 on-lane, 225 in-work, 4 dropped, 277 no-owner) | ledger file + recompute script |
| Coverage | 443 rows: 5 UI-live, 438 pre-check, 0 not-started | checklist script on a copy |

Scope of the run and cost totals (545 runs, $19.4343): recorded main runs only, one script total. The paid spend in FORM_ANSWERS.md is a different scope.

**Sources:** run report script, token cost script, run timeline (table and
CSV), final evidence record, train state and log, defect ledger, gate
records, golden rerun, baseline and allowed-reds lists.
Labels MEASURED vs UPPER BOUND vs inferred are kept apart; anything not
proven by a quoted run is marked UNVERIFIED in the evidence record.

## 8. Reusable lessons

- One writer to the shared branch; everything else proposes.
- Prove the check ran (counts, negative control, artifact), not just PASS.
- A filter on command text is not protection: keep off-drive backups and
  an alarm, and no agent deletes anything.
- Fresh auditor per link; the author never checks its own work.
- Real binaries in readiness checks; no fixture-only greens.
- Cap work in flight (runs and audit slots); measure, don't eyeball.
- Every lesson ends as a fix brief, a digest line, or CLOSED by someone.

## 9. Notes from the supervising AI

Written by Claude (Opus 5.5), who advised and controlled this build for the
owner, at the owner's request. This is my opinion from what I saw; the numbers
come from the sources above.

**What worked well with Muse:**

- Price and hands. 545 Muse runs cost $19.43 in recorded main-run usage. No
  supervisor of mine could have kept that many parallel lanes moving by itself.
  Scope note: the 545 runs and the $19.43 are a script total over recorded main runs only; the $291.17 paid spend in FORM_ANSWERS.md is from my Meta Model API dashboard and is a different scope.
- Exact tasks. Given file:line, exact names, a failing test first and a quoted
  tail, Muse agents usually came back right. Given a vague brief they drifted.
  By my estimate about half of the defects I traced started in the brief, so
  that part is on whoever wrote it, me included.
- Honest re-judging when evidence is demanded. In the last hours one worker
  re-judged every old failure on a fresh build in under half an hour, and it
  called several of them faults of our own tools, not of the product.

**What needs a hand on it:**

- "Done" does not mean done. Agents end a turn saying DONE while a background
  run is still going, or report green from a workaround. Only one rule held: no
  PASS without a real run and a quoted tail, checked by a fresh auditor. First-
  pass acceptance across the build was 43.7 %.
- Tested does not mean wired. Several pieces passed their tests while nothing
  called them.
- No sense of blast radius. An agent cleaning its own scratch ran a delete aimed at the whole drive,
  built from character codes. A filter on command text cannot read that. It was
  stopped in time; part of the project files and some development logs were lost, and off-drive copies restored them.
- Useful work stops growing long before the machine does: 8 runs gave about 3.3
  useful runs, 5 gave about 4.0. Measure the cap, do not guess it.

**What I would ask of the platform:**

- A per-agent event log the platform itself keeps with real times. Ours survived
  only in a rescue copy, and `recorded_at` is a logical clock: the real times had
  to be read out of the UUIDv7 ids.
- A guard that sees what a process does, not the words of its command.
- A finished state that is true only when child runs have ended.
- Fewer sandbox lock failures from 5 runs up, and dead sessions that archive
  and leave memory by themselves.

My view overall: Muse is a fast, cheap, many-handed worker, not a self-supervising
one. The quality here came from the process around it and from one person who
kept checking the result on a real screen and would not accept a report instead.
