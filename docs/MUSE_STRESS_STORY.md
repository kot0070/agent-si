# How this build stress-tested Muse Code multi-agent work

A field report from building Agent SI (Oct 25 – Nov 1, 2026) with dozens of
concurrent Muse Code agent trees. Everything below is measured; every number
names its source. Where we could not verify a figure in files, it is labeled
as owner-observed.

## 1. The sandbox lock storm (os error 32)

Windows file locking (`os error 32`, deny_read_acl_state contention) became our
dominant failure mode once we parallelized. Two independent measurements:

- Standing rule, re-measured live: with 7–11 concurrent RUNs (trees) about 4%
  of shell calls fail with the sandbox lock error; with 12–19 concurrent RUNs
  about 30% fail. Source: build records (measured).
  Consequence encoded in the same rule: at most 11 live runs in total, starts
  at least 2 minutes apart, product lanes first.
- OS32A package audit (155 run folders scanned, 10-minute buckets,
  2026-10-26 12:00 to 2026-10-27 14:21 -0500): failure share by live-run count
  was 2: 6.9%, 3: 13.4%, 4: 2.8%, 5: 38.3%, 6: 35.1%, 7: 42.2%, 8: 53.4%,
  9: 45.9%, 10: 46.8%, 11: 39.6%, 12+: 38.9%. Recommended cap from the data:
  4. Sources: build records (by live-count table; status BLOCKED, no auditor
  PASS).
  Method note: the table counts os-error-32 over executed
  powershell/shell tool results in overlapping windows (build records);
  the build-records figures are per-shell-call lock error rates. Same storm,
  different lenses.

Single incidents that made the rule concrete:

- M-E4 Phase-A: the sandbox lock killed a tool launch twice; retry after
  60 s succeeded. Rule since then: launch OS-errors retry 60 s x5, then
  BLOCKED. Source: build records.
- Night of Oct 30: os32 share hit 41% in one hour, plus 2 runs stopped as
  `stopped_idle exit 1` and 3 K02 REJECT/BLOCKED verdicts. Source: build
  records.
- K04INT1 stalled before its coder even started on os32 retries, zero changes;
  K02R6 was stopped at 184 min against a 75+30 min cap. Neither was caught
  automatically — the human noticed by watching. Source: build records.

## 2. The Muse 5-run cap

Muse Code throughput collapsed long before the machine did. Measured useful
runs: 8 concurrent runs yielded ~3.3 useful; 5 yielded ~4.0; 4 yielded ~3.7.
Decision (build records): Muse runs max 5, product only, starts >= 2 min
apart, re-measured every 2 hours. Source: build records. Live
proof the cap holds: status/board lines repeatedly read "Muse 5/5 live"
(e.g. build records).

Cost scale of the experiment, read-only from session stores: $18.0695 over 505
runs, growing to $30.4658 over 865 runs (build records). A
healthy end-to-end lane (queue -> Manager -> coder -> auditor ->
HD request -> autocheck -> run end) took 6.1 min and $0.031
(build records).

## 3. Dead and hung sessions in the Muse app

What we saw from the outside, all file-evidenced except the last line:

- TH6 M-NAV: a Manager polled a coder that had been dead since 20:16 for
  ~50 minutes while sibling Managers kept writing, which hid the deadlock from
  tree-level progress signals. Sources: build records (waiter-scoped progress
  rule, fix).
- Mass death, 2026-10-29 07:27: four status.json files still said "running"
  with both recorded PIDs gone; the stale strings held the scheduler at cap 5
  while the real live count was 0+1. Fix: PID-validated liveness (OpenProcess
  + exit code + create time), fail-open. Source: build records.
- Owner-observed, not file-counted: on the order of 800–1000 open dead
  sessions visible in the Muse app, with sessions that no longer pick up
  tasks. No file counter for this figure was found; it is included as the
  owner's direct observation because it motivated the archival tooling below.

## 4. Orphan console windows

Every lane start and hook poll spawned a visible console. Measured during the
WINFIX incident (09:41): OpenConsole/conhost counts rose 43/60 -> 47/65 ->
50/68 -> 62/91 within about five minutes (build records,
proof section). Fix: CREATE_NO_WINDOW (0x08000000) at every Popen site in 15
files (muse_launch, queue_runner, muse_audit, lessons_feed, hd_tick,
watchdog2, owner_board, lai_* pollers, muse_watch wake), muse_run.py:1033
carrying the comment "hidden console: hook cmd.exe children inherit it, no
Terminal window per hook". Proof: new tests_tools/test_winconsole_nowindow.py
6/6 PASS. Leftover proposal inside the same return: START.ps1 daemon
Start-Process calls still lack -WindowStyle Hidden (D3).

## 5. What we built to cope

- Run cap + queue. Scheduler (build records) enforces cap 5
  (later 11 total / 5 Muse) with start spacing (150 s, later 60 s), PID-guard,
  dead-letter queue, WSCLASH single-owner-per-WT guard, and a SLOTFILL reserve
  pool of lint-clean briefs so freed slots refill immediately. Sources:
  build records (60 s spacing; 658 of 1860 slot-minutes idle before the
  reserve existed).
- Watcher (muse_watch). Idle-tree silent rule, stuck ladder (no task progress
  20/40 min = silent flags, 60 = one HD wake, 80 = one Director note, max
  1/hour), ended-waiting notes (a child's SubagentStop pages every waiter
  polling its folder at once), chaos guards (repeat-test counts failing
  commands only; 790 false provider_error events killed by requiring
  status/http context). Sources: build records.
- Heartbeat. hooks/heartbeat.py maps every agent to its tree, records an
  activity ledger, prices cost from the session store (the hook-priced first
  version was 20x too high: T1-A $0.754 vs real $0.042), and surfaces native
  failure hints (AuthorityNotReady = fatal, never retried; same call failing
  3x = change approach). hb_reconcile heals the signal after hook outages.
  Sources: build records.
- auto_merge + auto-free. Pid-guarded 60 s tick loop: merges only DONE lanes
  with zero NOT-DONE rows and quoted PASS/ACCEPT evidence; frees DONE/BLOCKED
  lanes silent > 10 min (run age > 15 min, no live run < 3 min, HOLD veto).
  Sources: build records (merge tests up to 24/24).
- Session archiving. sessarch.py archives Muse session logs daily at 03:00
  into dated session-archive tarballs (jsonl/json/txt/log only,
  atomic, never shrinks, locked files skipped); the janitor provably deletes
  only regenerable items. Sources: build records.
- WT-clone lanes. Package workspaces are local clones of APP on pkg/<PKG>
  because git worktrees failed inside the Muse sandbox
  (SetNamedSecurityInfoW 5 on APP\.git); junctions + sandbox ACL + repo-local
  author per clone. Source: build records.
- Doctor + preflight. dev.py doctor/setup/drift checks (build records)
  and lane_preflight.py STEP-0 checks (int sha, clean tree, gateway HTTP)
  catch the checkable facts before a lane burns an hour (build records).

A parallel data point from the OpenCode side of the same build:
a session-doctor tool from the OpenCode side of the same build repairs broken
OpenCode sessions in place (strips hidden reasoning, reorders text before
commands, undo files per write) — session surgery without losing context.
Source: build records.

## 6. Our proposals for Meta

1. Auto-archive dead sessions in the app. We had to build external archival
   (sessarch.py, daily tar.gz) because dead sessions accumulate visibly
   (~800–1000 observed) and pin RAM with no in-app expiry. Ask: automatic
   archival/expiry of sessions with no live turn, with an on-disk escape hatch
   like ours.
2. Release RAM held by dead sessions. Our mitigation was entirely external
   (Job-Object memory guard memjob.py, scheduler RAM accounting
   need_ram = 3.0 + per_lane x (running+1)). Ask: bound or release memory of
   finished/orphaned sessions server-side so one busy day cannot degrade the
   next.
3. A session-health API. Everything we detect (stuck ladder, os32 share
   flags in analyst_flags.py, PID-validated liveness, heartbeat
   reconciliation) is reverse-engineered from logs and side effects. Ask: a
   supported endpoint reporting per-session liveness, last activity, and
   failure-class counters, so supervisors can stop polling folders and
   parsing JSONL.
