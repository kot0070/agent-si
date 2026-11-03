# Agent SI

![Agent SI mark](src/agent_si/assets/mark_256.png)

Agent SI is a desktop app that takes one task in plain words and returns a checked result with evidence.
You describe the goal, the app plans the work, runs the checks, and a fresh audit gives the final verdict.
It uses connected model providers for the work and keeps every run, decision, and audit record with the project.

## Requirements

- Windows 10 or 11, 64-bit.
- WebView2 runtime. If it is missing, the app shows a message with the download link and also opens the app in the default browser.
- No Python install needed to run the app. Code tests on Python projects need a real Python: install Python (so `python` runs) or set `AGENT_SI_PYTHON` to a python executable. On Windows, a `python` that only opens the Microsoft Store never counts: the app skips that stub and tries the `py` launcher instead. No administrator rights needed. The portable build runs from its own folder.
- The bundle carries the licence text and the third-party notices; both are also shown on the About screen.

## Download and verify

Each release publishes an installer (`AgentSI-setup-0.1.0.exe`), a portable
zip (`AgentSI-portable-0.1.0.zip`), and a `SHA256SUMS.txt` index (one
`<sha256>  <filename>` line per file). Download the index together with
whichever package you use, and do not run anything if a hash differs.

### Installer (recommended)

1. Download `AgentSI-setup-0.1.0.exe` and `SHA256SUMS.txt`.
2. Check the hash in PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 AgentSI-setup-0.1.0.exe
```

3. Compare the value with the `AgentSI-setup-0.1.0.exe` line in
`SHA256SUMS.txt`.
4. Double-click the installer and follow the wizard. It installs per user
(no administrator rights needed), adds a Start-menu entry and a desktop
shortcut (both named 'Agent SI', both checked by default in the wizard,
opening AgentSI.exe in its folder), and can start the app at the end.
Uninstalling removes both shortcuts and keeps your data
folder unless you answer Yes to deleting it (see Remove below).

The build is unsigned, so Windows SmartScreen shows "Windows protected your PC" with publisher Unknown for the installer and again on first start.
This is expected for this release.
Click More info, then Run anyway - only after the SHA256 value matches the published SHA256SUMS.txt.
Do not run the app if it differs.

### Portable

1. Download `AgentSI-portable-0.1.0.zip` and `SHA256SUMS.txt`.
2. Check the hash in PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 AgentSI-portable-0.1.0.zip
```

3. Compare the value with the `AgentSI-portable-0.1.0.zip` line in
`SHA256SUMS.txt`. The zip holds one top folder `AgentSI/` and carries its
own `SHA256SUMS.txt` inside, with the hash of every file including
`AgentSI.exe` at the top folder root.
4. If the zip was downloaded, unblock it before unzipping: right-click the zip -> Properties -> check Unblock -> OK (or PowerShell: Unblock-File -LiteralPath .\AgentSI-portable-0.1.0.zip).
5. Unpack the zip into an empty folder, open the `AgentSI` folder inside it,
and run AgentSI.exe inside it by double-click (or run `Start-AgentSI.cmd`
beside it). Never copy the exe out of its folder: it needs its support
files beside it.

The same SmartScreen warning as above appears on first start (unsigned
build, publisher Unknown): More info, then Run anyway - only after the
hashes match.

## First run, step by step

The app opens a first-run guide with four steps. The guide reads its state from the server, never from local guesses. A step counts as done only when the server confirms it.

1. Connect a provider. The guide shows the provider rows and a Connect button for each. The Next button stays disabled until the server reports at least one connected provider. A Skip control moves on without connecting: the guide still finishes, but the chat waits for a provider (it shows "No model bound yet." with a link to Settings -> Models, and the status reads Blocked until you connect).
2. One-click team. Enter a team name and save. The app creates or reuses a project and saves Automatic for every role. Next moves on with or without saving.
3. Project and folder. Enter a folder value, optionally use Choose folder to pick it with the system dialog, then Create. The app creates the project through the real project service.
4. First task. Enter a task title and Create. The app creates the task through the real task service and shows the created task. The Continue control finishes the guide and opens the chat with the task title ready.

The last step also shows an optional quiet list: local AI, watcher preset, automations, and knowledge bases. Each can be skipped.

To open the guide again, go to `/firstrun`.

## Connect a provider

Go to Settings -> Models, or use the Setup wizard on the first-run screen.

1. Pick a provider row and choose Connect.
2. Enter the key in the password field and save.
3. The row shows the connected state. Disconnect removes the connection.

Search filters the list by provider or model name. Model checkboxes are enabled only when the provider is connected. An optional setup wizard, role pools, and a chat-model picker are on the same page.

The connect dialog shows the expected key format, and a key that does not fit shows "This key does not match the expected format." before you save (a warning only). Connecting itself is two steps: paste the key, press Check, then Save. Check tries the key against the live provider without storing anything: a good key answers "Key checked. Save to connect." and enables Save (local providers check at once, with no network). A wrong key answers "The provider refused this key. Paste the full key again." and nothing is stored — a failed replace keeps the old working key; an unreachable provider answers "Could not reach the provider.". Save stores the checked key (the server checks once more first) and only then reports "Connected {label}. Reference saved."; the local reference copy is written only after the server answers.

Model checkboxes switch models on and off for the team: only ticked models reach Auto, the role pools, and the chat picker. A fresh connect ticks only the default model. On the project Models route a team quick-fix card can apply the routing's suggested binding (Accept) or drop it (Dismiss).

Supported providers include a hosted Meta option, OpenAI, Anthropic, and local servers for local models.

## Keys: Windows credential store only

Provider keys are stored only in the Windows Credential Manager under the app namespace. The app never writes a key to a plain file, never shows it again, and never logs it. The settings and the browser storage hold only references, never key material. Disconnect deletes the stored entry.

## Where data lives

- Project data (projects, tasks, runs, decisions, audits, watcher journal, knowledge-base links) lives in the app data folder. The portable default is the `data` folder next to `AgentSI.exe`. If that folder is not writable, the app uses the per-user app data folder. Setting the `AGENT_SI_DATA_DIR` folder path overrides both. An empty value fails loudly instead of silently falling back.
- On first start the app copies previous settings and keys into the new data folder and keeps the originals untouched. A file that already exists at the destination is never overwritten.
- Interface preferences (first-run done flag, language, watcher display options) live in the browser local storage. Tab-only mirrors (role profiles, accepted risk) live in the session storage. Key material never lives there.
- Secret references live only in memory while the app runs.

## Remove and closing

- Remove: delete the app folder. Data lives in the `data` folder next to `AgentSI.exe` by default (`%LOCALAPPDATA%\AgentSI\data` when the app folder is not writable; the `AGENT_SI_DATA_DIR` folder path overrides both). Delete that data folder too for a full removal. Installed: Windows Settings -> Apps -> Agent SI -> Uninstall; the uninstaller keeps your data folder unless you answer Yes to deleting it. Provider keys live in the Windows Credential Manager under `app:<provider>` — Disconnect removes the entry.
- Closing is safe: history and records stay on disk and reappear on the next start. Closing the window ends the backend, so an active run stops with it.
- One copy at a time: starting the app again focuses the first window instead of starting a second copy.

## First task and Stop

1. Create or open a project.
2. Type the task in the chat box and send. With no project, sending creates a project named from the start of the message and then creates the task.
3. Watch progress in the chat, the team panel, and the Tests tab.
4. The result appears in the chat with its checks and the audit verdict. Reports and the evidence index stay with the project.

Stop: the top bar has Stop all. Stopping is a two-step control and also answers to the Escape key. It stops the active runs at once and keeps partial outputs and records.

## Known limits

- Unsigned build: SmartScreen warns. Verify hashes first.
- WebView2 is required for the desktop window. Without it the app shows the download notice and falls back to the browser.
- The folder picker needs a native window. Where no native dialog exists, the Choose control hides itself instead of failing.
- Local models need a running local server on the loopback address: Ollama at localhost:11434, LM Studio at localhost:1234/v1, any OpenAI-compatible server at localhost:8080/v1. If none answers, local checks report not configured.
- Budget starts at USD 5.00 per project with a soft limit of 4.00 and a hard limit of 5.00. When the budget is exhausted, new work is blocked with a plain message.
- Some screens show empty or unknown states until the server has records. The app never invents numbers.

## Licence

Agent SI ships under the MIT licence. Copyright (c) 2026 Ivan Soprun. See `LICENSE` at the checkout root. Third-party titles and licences are listed in `docs/third_party_notices/NOTICES.md` and shown on the About screen.

## How this was built

The stress points found while building Agent SI are recorded in a field report (owner-observed: over 100 agents at once; measured in the records: 1060 sessions, 545 recorded runs, peak 16 concurrent sessions). See [docs/MUSE_STRESS_STORY.md](docs/MUSE_STRESS_STORY.md).
