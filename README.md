# Agent SI

![Agent SI mark](src/agent_si/assets/mark_256.png)

Agent SI is a desktop app that takes one task in plain words and returns a checked result with evidence.
You describe the goal, the app plans the work, runs the checks, and a fresh audit gives the final verdict.
It uses connected model providers for the work and keeps every run, decision, and audit record with the project.

<<SHOT: main chat screen>>

## Requirements

- Windows 10 or 11, 64-bit.
- WebView2 runtime. If it is missing, the app shows a message with the download link and also opens the app in the default browser.
- No Python install needed. No administrator rights needed. The portable build runs from its own folder.
- The bundle carries the licence text and the third-party notices; both are also shown on the About screen.

## Download and verify

1. Download the portable zip and the `SHA256SUMS.txt` file published with the release.
2. Check the hashes in PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 AgentSI-portable-0.1.0.zip
Get-FileHash -Algorithm SHA256 AgentSI.exe
```

3. Compare both values with `SHA256SUMS.txt`. Do not run the app if they differ.
4. Unpack the zip into an empty folder and start `AgentSI.exe` by double-click.

<<FINAL: release hashes and file names are stamped at release time; re-verify against SHA256SUMS.txt in the bundle>>

The build is unsigned, so on first start Windows SmartScreen shows "Windows protected your PC" with publisher Unknown. This is expected for this release. Click More info, then Run anyway — only after the SHA256 values above match. Do not run the app if they differ.

## First run, step by step

The app opens a first-run guide with four steps. The guide reads its state from the server, never from local guesses. A step counts as done only when the server confirms it.

1. Connect a provider. The guide shows the provider rows and a Connect button for each. The Next button stays disabled until the server reports at least one connected provider. A Skip control is also shown.
2. One-click team. Enter a team name and save. The app creates or reuses a project and saves the default team setup for every role.
3. Project and folder. Enter a folder value, optionally use Choose folder to pick it with the system dialog, then Create. The app creates the project through the real project service.
4. First task. Enter a task title and Create. The app creates the task through the real task service and shows the created task. The Continue control finishes the guide and opens the chat with the task title ready.

The last step also shows an optional quiet list: local AI, watcher preset, automations, and knowledge bases. Each can be skipped.

To open the guide again, go to `/firstrun`.

<<SHOT: first-run guide>>

## Connect a provider

Go to Settings -> Models, or use the Setup wizard on the first-run screen.

1. Pick a provider row and choose Connect.
2. Enter the key in the password field and save.
3. The row shows the connected state. Disconnect removes the connection.

Search filters the list by provider or model name. Model checkboxes are enabled only when the provider is connected. An optional setup wizard, role pools, and a chat-model picker are on the same page.

Supported providers include a hosted Meta option, OpenAI, Anthropic, and local servers for local models.

<<SHOT: providers page>>

## Keys: Windows credential store only

Provider keys are stored only in the Windows Credential Manager under the app namespace. The app never writes a key to a plain file, never shows it again, and never logs it. The settings and the browser storage hold only references, never key material. Disconnect deletes the stored entry.

## Where data lives

- Project data (projects, tasks, runs, decisions, audits, watcher journal, knowledge-base links) lives in the app data folder. The portable default is the `data` folder next to `AgentSI.exe`. If that folder is not writable, the app uses the per-user app data folder. Setting the `AGENT_SI_DATA_DIR` folder path overrides both. An empty value fails loudly instead of silently falling back.
- On first start the app copies previous settings and keys into the new data folder and keeps the originals untouched. A file that already exists at the destination is never overwritten.
- Interface preferences (first-run done flag, language, watcher display options) live in the browser local storage. Tab-only mirrors (role profiles, accepted risk) live in the session storage. Key material never lives there.
- Secret references live only in memory while the app runs.

## Remove and closing

- Remove: delete the app folder. Data lives in the `data` folder next to `AgentSI.exe` by default (`%LOCALAPPDATA%\AgentSI\data` when the app folder is not writable; the `AGENT_SI_DATA_DIR` folder path overrides both). Delete that data folder too for a full removal. Provider keys live in the Windows Credential Manager under `app:<provider>` — Disconnect removes the entry.
- Closing is safe: history and records stay on disk and reappear on the next start. A run stops when the window closes (stop the whole `AgentSI.exe` tree, not just the starter).

## First task and Stop

1. Create or open a project.
2. Type the task in the chat box and send. With no project, sending creates a project named from the first words and then creates the task.
3. Watch progress in the chat, the team panel, and the Tests tab.
4. The result appears in the chat with its checks and the audit verdict. Reports and the evidence index stay with the project.

Stop: the top bar has Stop all. Stopping is a two-step control and also answers to the Escape key. It stops the active runs at once and keeps partial outputs and records.

<<SHOT: project view with tests tab>>

## Known limits

- Unsigned build: SmartScreen warns. Verify hashes first.
- WebView2 is required for the desktop window. Without it the app shows the download notice and falls back to the browser.
- The folder picker needs a native window. Where no native dialog exists, the Choose control hides itself instead of failing.
- Local models need a running local server on the loopback address. If none answers, local checks report not configured.
- Budget has a default currency and default soft and hard limits. When the budget is exhausted, new work is blocked with a plain message.
- Some screens show empty or unknown states until the server has records. The app never invents numbers.

<<FINAL: exact default budget numbers and local server addresses are verified against the release bundle at final pass>>

## Licence

Agent SI ships under the MIT licence. Copyright (c) 2026 Ivan Soprun. See `LICENSE` at the checkout root. Third-party titles and licences are listed in `docs/third_party_notices/NOTICES.md` and shown on the About screen.
