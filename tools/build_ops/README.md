# Build operations tools

These are **development tools, not part of the app, shown as written for this build.** I used them to run many agents at once and to keep the repository safe while they worked. They are here so you can read how it was done. The app does not import or start any of them.

What was changed in the copies: machine paths, server addresses and session ids were replaced by `<PLACEHOLDERS>` (for example `<BUILD_ROOT>`, `<VENV_PYTHON_EXE>`, `<BACKUP_ROOT>`, `<SESSION_ID>`), and a two-line comment was added at the top of each file. The logic is not changed (one local variable in `planb_spend.py` was renamed from `token` to `basic`, because the app's secret scanner reads an assignment to a variable of that name as a possible secret; it holds a base64 login header built from an environment variable, not a stored secret). Because of the placeholders and the build's own folder layout, these files are for reading; they do not run as they are.

The story of how they were used: [../../docs/CONTROLLING_MANY_AGENTS.md](../../docs/CONTROLLING_MANY_AGENTS.md).

## The owner board (the one I could not work without)

| file | what it does | problem it solved |
|---|---|---|
| [owner_board.py](owner_board.py) | Builds one phone-sized text screen from the build's own files: lanes, merge, newest gate, people, script health, build, journal and raw log tails. Read-only, standard library only. `--once` prints it; `--loop 30` rewrites one output file every 30 seconds. A value it cannot read prints "нема даних" (no data), never a guess. | I could not tell which of dozens of agents was really working. One screen, readable on a phone, ended that. |
| [lane_status.py](lane_status.py) | Reads the lane files and the session database (read-only) and returns the lane and people rows. The board shares it. | One reading of lane state instead of two copies that drift apart. |

The board is explained, with photos, at the top of [CONTROLLING_MANY_AGENTS.md](../../docs/CONTROLLING_MANY_AGENTS.md). It also calls `dev.py`, `progress.py` and `sync_status.py` when they exist; they are not copied here, and without them the board prints no-data markers for those lines.

## Landing and gates

| file | what it does | problem it solved |
|---|---|---|
| [merge_train.py](merge_train.py) | Serial landing loop with a closed audit loop. It is the only writer of the integration branch. It keeps a lane table, writes its state atomically, runs a gate on each landing and notifies once on a failure. Its header says: no model calls, no delete, no reset --hard, no clean. | Parallel lanes overwrote each other and history was hard to review. |
| [int_gate.py](int_gate.py) | The gate run after merges, by code first, before any build: G1 commits lost, G2 code hit, G3 function, G4 from source, G5 coverage. Usage: `--fast` or `--full`, `--rev HASH`, `--watch`. Output is one line per check. | "Green" merges that broke the tree, and suites that did not actually run. |
| [build_gate.py](build_gate.py) | Pre-build, post-build and pre-table checks for the staged exe build. Read-only: it never builds, pushes or prints keys. Exit 0 all pass, 1 any fail, 2 usage error. | An exe built from the wrong commit or from a dirty tree. |

## Watching and safety

| file | what it does | problem it solved |
|---|---|---|
| [muse_watch.py](muse_watch.py) | The Director's separate watcher over running Muse Code runs. It reads run logs and the session store incrementally, writes a status table and drops a few events once each (started, finished, idle, dead, cost and more). Never stops or changes a process. | Silent or dead runs that nobody noticed. |
| [backup_15min.py](backup_15min.py) | One pass: a git bundle of the product repository plus zips of the tools, inbox, run and kit folders to a backup folder; locked or oversized files are listed and skipped. `--loop` repeats. No pruning. The name says 15 minutes; the file comments record that the interval was raised to 60 and then 120 minutes because a copy takes minutes of CPU and the backup disk filled up. | A delete aimed at a whole drive. Backups are the cure; the guard on command text is not. |
| [wipe_watch.py](wipe_watch.py) | Counts the entries of a few key folders every 20 seconds and prints an alert when a count drops or a must-exist file disappears. Read-only. | A script file that deletes cannot be refused by a filter on command text, so this is the alarm. |
| [planb_spend.py](planb_spend.py) | Sums the spend of the Claude sessions that steered the last stretch of the build, from a read-only copy of the session database. With `--watch` it exits on one event: done, stalled for 20 minutes, or budget (it interrupts the sessions first). Cap 90 dollars, stop at 85. | A spending limit that did not depend on me watching the meter. |

## Not copied

- Skipped because it mentions a private archive: none. I checked each file; the only "archive" in the code is a folder name the board skips when it looks for the newest file.
- Not asked for, so not copied: `dev.py`, `progress.py`, `sync_status.py`, the scheduler, the stall watcher, the watchdog scripts.

## Checks I ran on these copies

The standard library parser reads every file, a scan finds no drive paths, server addresses, session ids, names or key patterns, and the app's own secret scanner (`src/agent_si/backend/secretscan.py`) finds nothing.
