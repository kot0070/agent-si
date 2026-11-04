# Clean install: README Quick start on a fresh clone

clone: git clone -b int <local repo> <fresh folder> | exit 0 | ok
checkout: cloned fresh into an empty folder (an earlier test folder was not reused)
shell: PowerShell, working directory = the fresh checkout

| # | command (as in README) | exit | sec | last error |
|---|---|---|---|---|
| 1 | py -3.13 -m venv .venv | 0 | 5 | none |
| 2 | .\.venv\Scripts\python.exe -m pip install -e . | 0 | 41 | none (pip notice only: pip upgrade available) |
| 3 | npm.cmd --prefix frontend install | 0 | 3 | none (0 vulnerabilities) |
| 4 | npm.cmd --prefix frontend run build | 0 | 1 | none (build warnings only: MODULE_LEVEL_DIRECTIVE "use client" from react-router, INEFFECTIVE_DYNAMIC_IMPORT src/chat/index.tsx, chunk > 500 kB) |
| 5 | $env:AGENT_SI_DATA_DIR = "$PWD\data" | 0 | 0 | none (value = data folder inside the fresh checkout) |
| 6 | .\.venv\Scripts\python.exe -m agent_si.sidecar (started detached, Start-Process, hidden) | n/a (detached) | n/a | none |

Note step 6: README runs it in the foreground; it was started detached as the task asked. The launcher and its child (the app, listening on 127.0.0.1) were started detached.

## App check
- GET http://127.0.0.1:<port>/firstrun -> HTTP 200, 1539 bytes, SPA shell (title "Agent SI").
- Limit: the check confirms the HTML shell served; the first-run screen itself is rendered client-side and was not visually confirmed (no browser drive).
- Stop: the two processes started by the test were stopped; the port no longer listened.

## README relative links (markdown links)
- OK docs/EVIDENCE.md
- OK docs/HOW_IT_WAS_BUILT.md
- OK docs/MODEL_EVAL.md
- OK docs/MUSE_CODE_STRESS_TEST.md
- OK docs/MUSE_STRESS_STORY.md
- OK src/agent_si/assets/mark_256.png (image)
- Skipped: none (no http/mailto links)

Extra (backtick file refs, not links): LICENSE OK; docs/third_party_notices/NOTICES.md OK; frontend/package.json OK; pytest.ini OK; pyproject.toml OK; watcher/rules.py MISS at repo root but OK at src/agent_si/watcher/rules.py (README path is short form, not a link).

broken links: none

## defects
- none in Quick start. Only the README path note above (watcher/rules.py written without src/agent_si/ prefix).

CLEAN PASS (all 6 Quick start steps exit 0, app HTTP 200 on /firstrun, all README links resolve; first-run screen rendering not visually checked)
