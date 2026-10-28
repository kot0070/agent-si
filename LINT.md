# K02 lint + typecheck + tests (M-CONF shared configs)

Target: project venv Python 3.13.15 (`py313` / `python_version = "3.13"`).
Configs live at the WT\K02 root (`ruff.toml`, `mypy.ini`); M-FIX uses
them read-only and never edits them.

## Check commands

Run each from the WT\K02 root via
`cmd /c "cd /d D:\AI_PROJECTS\AGENT_SI_BUILD\WT\K02 && ..."`
(see workspace AGENTS.md). Coder and auditor batch them into ONE
powershell call, plain `python -m` invocations joined with `;`
(no shell operators, pipes, or redirections).

`D:\MUSE_TOOLS\venv_agent_si\Scripts\python.exe -m ruff check --config ruff.toml src\agent_si tests`

`D:\MUSE_TOOLS\venv_agent_si\Scripts\python.exe -m mypy --config-file mypy.ini src\agent_si`

`D:\MUSE_TOOLS\venv_agent_si\Scripts\python.exe -m pytest tests -q -p no:cacheprovider --basetemp <task-tmp>\pt-<your-id>`

Note: the project hook blocks bare-directory runs, so the pytest
command is executed as the explicit 19-file list covering all of
`tests/` (see CODER_RETURN for the deviation record).
Waiver (HD VERDICT STUCK_K02L1FIX, option 1 narrowed): interface.py x37 (UP035+E501) via ruff.toml per-file-ignore; 26 cite-blocked product findings via same-line `# noqa` — reason: frozen file / frozen cites; full list: _task/LINT_WAIVERS.md.
