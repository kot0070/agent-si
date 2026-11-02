# User guide — Agent SI

Plain words for each screen. Nothing here changes settings by itself except where the screen says so.

<<SHOT: app shell with left nav, chat, and right cards>>

## Chat (`/`)

The home screen. A message list, a composer box, and a send control.

- With no project, sending a message creates a project named from the first words, creates the first task, and selects the project.
- With a project, the chat is bound to that project. The status line shows progress, offline or degraded dots, and a stop control.
- If no model is bound yet, a hint with a link to Settings -> Models appears.

<<SHOT: chat screen>>

## Agents live (`/agents/live`)

One row per running agent: role, model, step, cost, and tokens. Empty when nothing runs. Retry is offered on load failure.

## Watcher (`/watcher`)

Status plus journal. A model selector (connected model, local model, or off) and a cloud-fallback switch. One card per rule. The journal gains an entry when the watcher acts.

<<SHOT: watcher screen>>

## Projects (`/projects`)

Project list with add, open, pause or resume, and archive.

- Add asks for a name and a folder. Choose fills the folder from the system dialog. Where no native dialog exists, the Choose control hides itself.
- Opening a project takes you to its chat.

## Project view (`/projects/:id/...`)

Tabs: overview, tasks, runs, time, AI usage, tokens, cost, local AI, cloud AI, models, routing decisions, audits, errors, reports, tests.

- Tasks hosts the task composer.
- Tests shows the latest run: served counters and one row per test. It never changes settings.
- Numbers come from stored records only. Missing data renders as empty or unknown.

<<SHOT: project tests tab>>

## Settings (`/settings`, `/settings/:section`)

Sections: general, appearance, local AI, models, routing, optimization, capability database, project, local bench, diagnostics.

- Appearance: theme switch.
- Local AI: read-only stored bench path, models, and endpoint.
- Models and routing: provider list, search, setup wizard, role pools, chat-model picker, leftover-key finder.
- Project: role profile editor, defaults bar, one-time risk acceptance switch.
- Local bench: scan and run benchmark for local models.
- Diagnostics: locale, telemetry, gateway, and history checks.

## First run (`/firstrun`)

Four steps in a card with a progress line: connect provider, one-click team, project and folder, first task. Next is disabled until the server confirms the step. Skip is shown where skipping is safe. The last step carries a quiet optional list (local AI, watcher preset, automations, knowledge bases), each skippable. Finishing marks the guide done and opens the chat.

<<SHOT: first-run guide>>

## About (`/about`)

Product name, copyright line, licence text, and the third-party list when enabled.

## Migration (`/migration`)

Copies previous stored keys into the current storage and shows a done line. Old copies are kept.

## How it works (`/how-it-works`)

A six-stage diagram (task, plan, split, agents write files, checks, audit) plus three short notes: runs, code tests, local tests.

## Top bar and side bar

- Top bar: product name, project switcher, watcher link with state badge, Stop all (two-step, answers to Escape), language selector, theme switch.
- Side bar: four entries only — New task, Projects, Results, Settings — each with a short purpose hint. Project buttons open that project chat and show a quiet unread dot.

## Right cards

Five live cards: team now, context (percent, window, per-role legend), results (last packages), background work (active task count), watcher (state, model, last action). Collapsed metric cards show tokens, tests, budget, providers, local AI, and apps. The panel polls live rows often and project numbers less often.
