# User guide — Agent SI

Plain words for each screen. Nothing here changes settings by itself except where the screen says so.
Screen and section names are the English interface words.

## Chat (`/`)

The home screen. A message list, a composer box, and a send control.

- With no project, sending a message creates a project named from the start of the message, creates the
  first task, and selects the project.
- With a project, the chat is bound to that project. The status line shows progress, offline or degraded
  dots, and a stop control. Without a connected provider the status reads Blocked and sending asks you
  to connect first.
- If no model is bound yet, a hint with a link to Settings -> Models appears.

## Agents live (`/agents/live`)

One row per running agent: role, model, step, cost, and tokens. Empty when nothing runs. Retry is
offered on load failure.

## Watcher (`/watcher`)

Independent watch over agents: state, journal and rules.

- Rule cards: Hang, Guard and Tamper, each with what it looks for, the signal (Manager, Director, User)
  and the allowed power (Observe + notify, Restart once, Pause, Stop). Restart once, pause and stop need
  your approval before they act; I approve this one check unlocks one action.
- Presets: Cautious (only the hang card stays on), Standard (hang and guard on) and Strict (hang, guard
  and tamper on). Current marks the active one.
- Model: API, Local or Off. Cloud fallback has its own switch; off means the watcher never uses cloud
  models. Model calls and model tokens are counted on the same screen.
- Journal: one row per event, from Rule checks and Alerts to Decision, Guard block, Tamper attempt,
  Heartbeat, Automation run, Checkpoint, Recovery, Outage and run rows. No action yet means the watcher
  has not acted.
- Alerts, timers and integrity: show and refresh alerts, fire, pause or resume a timer with a pause
  reason, and check integrity (Integrity OK or Integrity mismatch).
- Apps and services: load the list to see what is in use, idle or safe to close, with UP, DOWN or
  DEGRADED per service.
- Watcher for this project turns watching on and off for the selected project.

## Automations (Settings -> Automations)

Small jobs on a schedule, a number or an event. Every run is recorded.

- Rules list, plus Templates and New rule. The rule builder asks for a name and a trigger: Schedule,
  Number or Event; an optional Only if condition under 500 characters; a Do action; and what happens
  if the run is missed (skip or run once). Preview shows the rule before you save it.
- Stop all automations and Stop automations for this project are the two stop switches. While a switch
  is on, nothing runs and the page answers "Automations are stopped - turn the stop switch off first."

## Projects (`/projects`)

Project list with add, open, pause or resume, and archive.

- Add asks for a name and a folder. Choose folder fills the folder from the system dialog. Where no
  native dialog exists, the Choose control hides itself.
- Opening a project takes you to its chat.

## Project view (`/projects/:projectId/...`)

Tabs: chat, overview, tasks, runs, time, AI usage, tokens, cost, local LLM, cloud AI, models, routing
decisions, audits, errors, reports, tests.

- Tasks hosts the task composer.
- Tests shows the latest run: served counters and one row per test (code tests, AI checks and human
  verdicts). It never changes settings (the local-tests on/off switch lives on the overview tab).
- Local LLM shows the work running on this machine, one row per agent, from served records.
- Numbers come from stored records only. Missing data renders as empty or unknown.

## Settings (`/settings`, `/settings/:section`)

The index groups the sections: Models and providers (Models, Routing, Local LLM, Capability Database),
Limits (Optimization, Project), App (General, Appearance, Diagnostics), Measure (Local benchmark), Help
(How it works, About, Migration), and the row group Watcher and automations (Automations).

- General: language switch, Reset the setup (shows the guided first run again).
- Appearance: theme switch, dark or light.
- Local LLM: one row per local preset, Ollama (`http://localhost:11434`) and LM Studio
  (`http://localhost:1234/v1`). Connect opens the same two-step dialog as the provider page: local rows
  need no key ("Local server: usually no key is needed."), and a stopped server reads "Local server is
  not running. Start Ollama first, then Check again." A connected row reads "Connected Ollama, N models.",
  lists the local models, and offers Use for agents, which pins the worker role to the chosen model and
  confirms "Worker model set to {model}." Below the rows, a read-only panel repeats the stored benchmark
  path, the models with their evidence, and the decision record.
- Models and Routing: provider list, search, setup wizard, role pools, chat-model picker, leftover-key
  finder. Connecting is two-step — paste the key, press Check, then Save: only a checked key saves, a
  wrong key is refused in plain words and nothing is stored; only ticked models reach Auto, the role
  pools, and the chat picker.
- Optimization: cost and speed trade-offs — weights, required quality, risk ceiling.
- Capability Database: model knowledge state per provider, last update time, and source. Update stages
  the shipped copy for every connected provider (each row names its real source and retrieval date, or
  says `shipped copy from <date>`) and applies it on the same screen; Check online fetches the official
  docs pages for stale providers (older than 90 days, fresh rows are never fetched) and stages a
  preview; From file uploads a `.json` file shaped like `docs/kb-update-example.json`
  (`{"models": [{"provider_id", "model_id", "fields": {...}}]}`) and stages a preview the same way.
  Every preview shows old values next to new ones with Apply and Reject; applying stacks a new version,
  rejecting leaves the version untouched. When nothing changed the screen reads Already up to date.
- Project: role profile editor, defaults bar, install grants, spend caps per provider, step limits,
  routine offload, parts running at the same time, team on or off, and the one-time risk acceptance
  switch.
- Local benchmark: scan a folder for local models and run a quick, standard or deep benchmark; each
  finished run is recorded in the decision record with its evidence and duration.
- Test catalog: which test catalog the app runs, and its versions — active version with its short sha,
  served counters (bases, tests, by kind CODE/AI/HUMAN), the version list, filters by group, kind and
  search, the changelog, and import or attach a base.
- Diagnostics: developer screens that read live app state — telemetry usage, telemetry themes, locale
  coverage, benchmark gateway, benchmark history, and the log files folder with Open log folder.
- Automations: see the Automations section above.

## First run (`/firstrun`)

Four steps in a card with a progress line: Connect a provider, Create your team in one click, Choose a
project folder, Run your first task. Next moves through the steps; on the provider step Next stays
disabled until the server reports a connected provider, and a Skip control moves on without connecting.
Skipping the provider still finishes the guide, but runs wait until a provider is connected. The last
step carries a quiet optional list (Local LLM, Watcher preset, Automations, Knowledge bases), each
skippable. Finishing marks the guide done and opens the chat; the guide stays available at `/firstrun`.

## About (`/about`)

Product name, copyright line, licence text, and the third-party list when enabled.

## Migration (`/migration`)

Copies previous stored data into the current storage and shows a done line. Old copies are kept.

## How it works (`/how-it-works`)

A six-stage diagram (one task, Director plans, Managers, agents write files, checks, fresh auditor) plus
three short notes: runs, code tests, local tests.

## Top bar and side bar

- Top bar: product name, project switcher, Watcher link, Stop all (two-step, answers to Escape, reads No
  runs active when idle), language selector, panel control.
- Side bar: four entries only — New task, Projects, Reports, Settings — each with a short purpose hint.
  Project buttons open that project chat and show a quiet unread dot; Reports points at the selected
  project's reports and says Select a project to see its reports when none is selected.

## Right cards

Five live cards: team now, context (percent, window, per-role legend), results (latest reports), background
work (active task count), watcher (state, model, last action). Collapsed metric cards show tokens, tests,
budget, providers, local LLM, and third-party apps. The panel polls live rows often and project numbers
less often.
