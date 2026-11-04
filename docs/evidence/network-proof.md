# Network proof: only Meta models at runtime

Run verdict: PASS. Task "Create a file hello.txt with the text hello", Team On, ended in 6.8 min (10:45:36 to 10:52:17).
hello.txt written with text "hello". Events 38. Telemetry: tokens_total 3578.
App: source tree of this repo (agent_si from src), fresh data folder, loopback port 127.0.0.1.
Roles pinned to ollama/muse-glimmer:30b: director, manager, worker, auditor, watcher (PUT roles/pools 200 each).
Monitor: 148 ticks every 3 s over the app PID tree (10:45:29 to end + 60 s tail, END-MARK 10:52:20).
Attempt 1 (10:43) failed at start (import path, no 'iface'); its data folder was kept and a clean second attempt ran.

Remote addresses seen (non-loopback, Established or SynSent): NONE SEEN.

DNS cache: Get-DnsClientCache empty before and after (0 names). New DNS names: NONE.

Ollama server log, 10:43 to 10:53:
- registry.ollama.ai/library/muse-glimmer:30b loaded at 10:46:02 (loaded runners count=1).
- registry.ollama.ai/library/sqlcoder:7b: 21 WARN lines, one every 30 s from 10:46:29 to 10:52:00. Not started by this run (all roles pinned to muse-glimmer); source not proven, see notes.
- model blob (sha256-71b5c9c9...): 3 lines, no name.

Notes:
- Watcher status read before any rule evaluation shows "Rules only" (the watcher pin is saved; the model binds on evaluate). Not tested in this run.
- Telemetry labels 5 calls as "cloud_calls"; all calls went to the local Ollama at localhost:11434 (loopback). Label defect to check.
- Team GET route returned 404 (unknown project); run went on without it.

VERDICT: ONLY LOOPBACK
