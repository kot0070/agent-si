# User guide — Agent SI

Plain words for each screen. Nothing here changes settings by itself except where the screen says so.

## Chat (`/`)

The home screen. A message list, a composer box, and a send control.

- With no project, sending a message creates a project named from the start of the message, creates the first task, and selects the project.
- With a project, the chat is bound to that project. The status line shows progress, offline or degraded dots, and a stop control. Without a connected provider the status reads Blocked and sending asks you to connect first.
- If no model is bound yet, a hint with a link to Settings -> Models appears.

## Agents live (`/agents/live`)

One row per running agent: role, model, step, cost, and tokens. Empty when nothing runs. Retry is offered on load failure.

## Watcher (`/watcher`)

Status plus journal. A model selector (connected model, local model, or off) and a cloud-fallback switch. One card per rule. The journal gains an entry when the watcher acts.

## Projects (`/projects`)

Project list with add, open, pause or resume, and archive.

- Add asks for a name and a folder. Choose fills the folder from the system dialog. Where no native dialog exists, the Choose control hides itself.
- Opening a project takes you to its chat.

## Project view (`/projects/:id/...`)

Tabs: chat (this project's chat with its history), overview, tasks, runs, time, AI usage, tokens, cost, local LLM, cloud AI, models, routing decisions, audits, errors, reports, tests.

- Tasks hosts the task composer.
- Tests shows the latest run: served counters and one row per test. It never changes settings (the local-tests on/off switch lives on the overview tab).
- Numbers come from stored records only. Missing data renders as empty or unknown.

## Settings (`/settings`, `/settings/:section`)

Sections: general, appearance, local LLM, models, routing, optimization, capability database, project, local bench, diagnostics.

- Appearance: theme switch.
- Local LLM: read-only stored bench path, models, and endpoint.
- Models and routing: provider list, search, setup wizard, role pools, chat-model picker, leftover-key finder. Connecting is two-step — paste the key, press Check, then Save: only a checked key saves, a wrong key is refused in plain words and nothing is stored; only ticked models reach Auto, the role pools, and the chat picker.
- Capability database: model knowledge state per provider, last update time, and source. Update stages the shipped copy for every connected provider (each row names its real source and retrieval date, or says `shipped copy from <date>`) and applies it on the same screen; Check online fetches the official docs pages for stale providers (older than 90 days, fresh rows are never fetched) and stages a preview; From file uploads a `.json` file shaped like `docs/kb-update-example.json` (`{"models": [{"provider_id", "model_id", "fields": {...}}]}`) and stages a preview the same way. Every preview shows old values next to new ones with Apply and Reject; applying stacks a new version, rejecting leaves the version untouched. When nothing changed the screen reads Already up to date.
- Project: role profile editor, defaults bar, one-time risk acceptance switch.
- Local bench: scan and run benchmark for local models.
- Diagnostics: locale, telemetry, gateway, and history checks.

## First run (`/firstrun`)

Four steps in a card with a progress line: connect provider, one-click team, project and folder, first task. Next moves through the steps; on the provider step Next stays disabled until the server reports a connected provider, and a Skip control moves on without connecting. Skipping the provider still finishes the guide, but runs wait until a provider is connected. The last step carries a quiet optional list (local LLM, watcher preset, automations, knowledge bases), each skippable. Finishing marks the guide done and opens the chat; the guide stays available at `/firstrun`.

## About (`/about`)

Product name, copyright line, licence text, and the third-party list when enabled.

## Migration (`/migration`)

Copies previous stored data into the current storage and shows a done line. Old copies are kept.

## How it works (`/how-it-works`)

A six-stage diagram (one task, Director plans, Managers, agents write files, checks, fresh auditor) plus three short notes: runs, code tests, local tests.

## Top bar and side bar

- Top bar: product name, project switcher, watcher link with placement badge (hidden when unknown), Stop all (two-step, answers to Escape), language selector, theme switch.
- Side bar: four entries only — New task, Projects, Results, Settings — each with a short purpose hint. Project buttons open that project chat and show a quiet unread dot.

## Right cards

Five live cards: team now, context (percent, window, per-role legend), results (last packages), background work (active task count), watcher (state, model, last action). Collapsed metric cards show tokens, tests, budget, providers, local LLM, and apps. The panel polls live rows often and project numbers less often.
