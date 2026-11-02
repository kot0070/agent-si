# Lint + typecheck + tests (shared configs)

Target: project venv Python 3.13 (`python_version = "3.13"`).
Configs live at the workspace root (`ruff.toml`, `mypy.ini`); use
them read-only and never edit them.

## Check commands

Run each from the workspace root via
`cmd /c "cd /d <workspace-root> && ..."`
(see workspace AGENTS.md). Batch them into ONE
powershell call, plain `python -m` invocations joined with `;`
(no shell operators, pipes, or redirections).

`<venv python> -m ruff check --config ruff.toml src\agent_si tests`

`<venv python> -m mypy --config-file mypy.ini src\agent_si`

`<venv python> -m pytest tests -q -p no:cacheprovider --basetemp <task-tmp>\pt-<your-id>`

Note: the project hook blocks bare-directory runs, so the pytest
command is executed as the explicit file list covering all of
`tests` (see the coder return for the deviation record).
Waiver: interface.py findings via ruff.toml per-file-ignore; 26 cite-blocked product findings via same-line `# noqa` — reason: frozen file / frozen cites; full list: _task/LINT_WAIVERS.md.
