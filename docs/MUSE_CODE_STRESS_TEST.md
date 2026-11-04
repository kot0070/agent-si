# Muse Code under stress: what broke, what I built, what I would ask

I built Agent SI with Muse Code agents, running several agent trees at the same time on one Windows machine. Peak load in my scans was 12 or more live runs at once. This page is my field report for Meta engineers and hackathon judges. Muse carried most of this load. Most of the problems came from running many agents on one desktop, not from the model itself.

Every number below comes from a script that counted session logs. Each one is marked as **measured** or as a **standing rule**.

## At a glance

| Headline | Number | Type |
|---|---|---|
| Lock failure share with 5 to 11 live runs | 35 to 53 % of shell results | measured |
| Lock failure share with 4 live runs | 2.8 % | measured |
| Run folders scanned for the lock study | 155 (10-minute buckets) | measured |
| Experiment cost, 505 to 865 runs | $18.07 to $30.47 | measured |
| Healthy lane, end to end | 6.1 min, $0.031 | measured |
| Dead coder still polled while the tree looked busy | about 50 min | measured |
| Orphan console windows in one incident | 43/60 to 62/91 in about 5 min | measured |

## 1. Sandbox file locks ("os error 32")

**What happened.** Once I ran agents in parallel, Windows file locks became the main failure. Shell calls failed with `os error 32`. Launches were retried and then blocked.

**The number.** In a scan of 155 run folders (26 Oct 12:00 to 27 Oct 14:21, 10-minute buckets), the failure share rose sharply once five or more runs were live. See section 2.

**Single incidents:**

- A tool launch was killed by the lock twice. A retry after 60 seconds worked. The rule is now: retry launch errors 60 s, five times, then mark BLOCKED.
- On the night of 30 Oct, the failure share hit 41 % in one hour. Two runs stopped with `stopped_idle exit 1`, and three reviews ended in REJECT or BLOCKED.
- K04INT1 stalled before its coder started, because of lock retries. It made zero changes. K02R6 ran for 184 minutes against a 75 + 30 minute cap.

**What it means for Muse Code users.** When many agents share one machine, file locks show up as random failures, not as clear errors. A user will see a shell call fail and may not know why.

## 2. Failure rate against concurrent runs

| Live runs | Failure share, scan (measured) | Rule 13 rate (standing rule, not re-measured) |
|---|---|---|
| 2 | 6.9 % | - |
| 3 | 13.4 % | - |
| 4 | 2.8 % | - |
| 5 | 38.3 % | - |
| 6 | 35.1 % | - |
| 7 | 42.2 % | about 4 % (7 to 11 runs) |
| 8 | 53.4 % | about 4 % |
| 9 | 45.9 % | about 4 % |
| 10 | 46.8 % | about 4 % |
| 11 | 39.6 % | about 4 % |
| 12+ | 38.9 % | about 30 % (12 to 19 runs) |

```mermaid
xychart-beta
    title "Lock failure share by live runs (os error 32, measured)"
    x-axis ["2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12+"]
    y-axis "Failure share (%)" 0 --> 60
    bar [6.9, 13.4, 2.8, 38.3, 35.1, 42.2, 53.4, 45.9, 46.8, 39.6, 38.9]
```

The two lenses disagree. The scan counts `os error 32` in executed shell results within overlapping time windows. The rule counts lock errors per shell call. Both show the same storm, but the numbers are not the same measurement. I keep both and do not mix them.

**What it means for Muse Code users.** Concurrency has a hard ceiling on one machine. Past about five live runs, the scan shows that failures become common. Any agent tool that starts many shells at once should expect this.

## 3. Useful runs and the 5-run Muse cap

**What happened.** On 27 Oct I capped Muse runs at five, for product work only. Starts are at least two minutes apart, and I re-measure every two hours. Status lines read "Muse 5/5 live" many times after that.

**What it means for Muse Code users.** More concurrent runs did not give more finished work. Past a certain point, the extra runs mostly waited or failed. The cap is a standing rule, and I have not yet published a per-level count of useful runs.

## 4. Cost

**The number.** The experiment cost $18.07 over 505 runs and grew to $30.47 over 865 runs (read from session stores).

**A healthy lane** (queue, manager, coder, auditor, review request, check, run end) took 6.1 minutes and cost $0.031.

**What it means for Muse Code users.** A healthy lane is cheap. The cost that hurt was time lost to stalled lanes, such as the 184-minute run in section 1.

## 5. Dead and hung sessions

- **Hidden deadlock.** A manager polled a coder that had been dead since 20:16 for about 50 minutes. Sibling managers kept writing, so tree-level progress signals looked healthy.
- **Stale "running" state.** On 29 Oct at 07:27, four status files still said "running" with both recorded process IDs gone. The stale strings held my scheduler at its cap of five, while the real live count was 1.

**What it means for Muse Code users.** A session can be dead while its parent and siblings look busy. Progress signals need to be per session, not per tree.

## 6. Orphan console windows

During one incident (09:41), OpenConsole and conhost counts rose from 43/60 to 62/91 in about five minutes. Every lane start and hook poll opened a visible console.

**Fix.** Every subprocess start on Windows now uses `CREATE_NO_WINDOW`, across 15 files (count from my own return text). A regression test passes 6/6.

**What it means for Muse Code users.** Any agent tool that runs subprocesses on Windows can flood the desktop with windows unless it hides them.

## 7. What I built, and what changed

- **Run cap and queue.** Built a scheduler with a cap, start spacing, a PID guard, a dead-letter queue, one owner per work tree, and a reserve of ready briefs. Changed: freed slots refill at once. Before the reserve existed, 658 of 1860 slot-minutes were idle.
- **Watcher.** Built a stuck ladder: silent flag at 20 and 40 minutes without task progress, one HD wake at 60 minutes, one Director note at 80 minutes, at most one per hour. Changed: 790 false provider-error events were removed by requiring status or HTTP context.
- **Heartbeat.** Built a per-agent activity ledger that maps each agent to its tree and prices cost from the session store. Changed: the first hook-based pricing put one lane at $0.754; the real cost was $0.042. Authority-not-ready errors are now fatal and never retried. The same call failing 3 times means: change approach.
- **PID-validated liveness.** Built a check that uses process handle, exit code and creation time. Changed: stale "running" strings no longer hold the scheduler.
- **Auto-merge and auto-free.** Built a 60-second tick. It merges only finished lanes with no open rows and quoted PASS evidence, and frees lanes silent for more than 10 minutes. Its test passes 24/24.
- **Session archiving.** Built a daily 03:00 job that archives session logs into compressed daily files. It never shrinks an archive and skips locked files.
- **Work trees.** Built package copies of the repository on their own branches. Changed: git worktrees failed inside the sandbox (access error 5 on the repository's `.git`), so I moved to copies.
- **Preflight.** Built checks that run before a lane starts: commit, clean tree, gateway reachable. Changed: a lane no longer burns an hour before a basic fact turns out wrong.

## 8. What I would ask the Muse Code team to improve

1. **Archive dead sessions in the app**, with an export path. I had to build external archiving, and dead sessions kept growing.
2. **Release memory from finished or orphaned sessions**, so one busy day does not slow the next.
3. **A session health API:** liveness, last activity, and failure-class counters per session. Today I rebuild these from logs and side effects.
4. **Clear handling of file-lock errors.** Retry them inside the tool, or report them as a separate class, and document a safe concurrency level for one machine.
5. **Hidden console windows by default** for subprocesses on Windows.

## Method note

- **Source.** A read-only copy of the Muse session store, filtered to this project, plus tool-output text found in session messages. Counts were made by script. Each claim was checked against the files on disk.
- **Measured.** Lock failure shares by live-run count (scan of 155 run folders), cost totals, lane time and cost, incident timings, and event counts.
- **Standing rules, not re-measured.** The 4 % and 30 % lock rates (rule 13), the five-run Muse cap, the two-minute start spacing, the 60-second launch retry, and the queue spacing values.
- **Not included.** Useful-run counts per concurrency level, and the number of dead sessions seen in the app. I could not verify either one from files.
- **Note.** The rule rates and the scan do not match, because they count different things (section 2).
